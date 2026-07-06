"""Flask editor application for interactive invoice editing."""

from __future__ import annotations

import contextlib
import copy
import json
import os
import threading
from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from flask import Flask, Response, render_template, request
from markupsafe import escape

if TYPE_CHECKING:
    from collections.abc import Callable

from harvest_invoicer.model import (
    DEFAULT_PAYMENT_TERM_DAYS,
    Invoice,
    InvoiceLine,
    fmt_date,
    fmt_money,
    fmt_qty,
    merge_duplicate_lines,
)
from harvest_invoicer.render import _effective_base_url, render_html

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_STATIC_DIR = Path(__file__).parent / "static"


def _make_invoice(
    lines: list[InvoiceLine],
    number: str,
    issuer: dict[str, object],
    currency: str = "EUR",
    payment_term_days: int = DEFAULT_PAYMENT_TERM_DAYS,
    period_start: date | None = None,
    period_end: date | None = None,
) -> Invoice:
    """Construct the initial Invoice from lines and defaults."""
    today = date.today()
    due = today + timedelta(days=payment_term_days)
    legal_note = issuer.get("legal_note")
    return Invoice(
        number=number,
        issue_date=today,
        due_date=due,
        lines=list(lines),
        legal_note=str(legal_note) if legal_note else None,
        currency=currency,
        period_start=period_start,
        period_end=period_end,
    )


def create_app(
    lines: list[InvoiceLine],
    issuer: dict[str, object],
    client: dict[str, str],
    invoice_number: str,
    output_path: Path,
    user_templates_dir: Path | None = None,
    currency: str = "EUR",
    period_start: date | None = None,
    period_end: date | None = None,
    fetch_callback: Callable[[date, date], list[InvoiceLine]] | None = None,
    clients: dict[str, dict[str, str]] | None = None,
    issuer_path: Path | None = None,
    clients_path: Path | None = None,
) -> Flask:
    """Create and configure the Flask editor application.

    State (the current invoice) lives on ``app.state`` — a plain object that
    is mutated in-place by htmx POST handlers.  The app is single-user and
    binds to 127.0.0.1 only; no auth, no persistence.

    When *user_templates_dir* is supplied the ChoiceLoader (in render.py)
    checks that directory first, falling back to the packaged templates.

    ``fetch_callback`` re-imports line items for a (start, end) date range —
    the editor's "Fetch from Harvest" button.  When ``None`` the button
    reports that re-fetching is unavailable.

    ``clients`` is the full clients.json mapping (for the settings page);
    ``issuer_path`` / ``clients_path`` are the config files the settings
    routes write back to.  When a path is ``None`` (demo mode, tests)
    settings edits apply to the running session only.
    """
    app = Flask(
        __name__,
        template_folder=str(_TEMPLATES_DIR),
        static_folder=str(_STATIC_DIR),
        static_url_path="/static",
    )

    invoice = _make_invoice(
        lines,
        invoice_number,
        issuer,
        currency,
        period_start=period_start,
        period_end=period_end,
    )

    # Mutable state bag on the app object — ephemeral, single-user.
    # "undo" holds a single-level snapshot of the line items taken before
    # the most recent mutation; undoing swaps it with the current lines,
    # so pressing Undo twice acts as redo.
    if clients is None:
        clients = {}
    # Key of the invoice's client inside the clients mapping (by identity, so
    # in-place edits through the settings page propagate to the preview).
    current_client_key = next((k for k, v in clients.items() if v is client), None)

    app.state = {  # type: ignore[attr-defined]
        "invoice": invoice,
        "issuer": issuer,
        "client": client,
        "clients": clients,
        "current_client_key": current_client_key,
        "output_path": output_path,
        "user_templates_dir": user_templates_dir,
        "undo": None,
    }

    date_format = str(issuer.get("date_format") or "%Y-%m-%d")

    # ------------------------------------------------------------------
    # Template helpers
    # ------------------------------------------------------------------

    def _render_rows(inv: Invoice) -> str:
        return render_template(
            "partials/rows.html",
            invoice=inv,
            fmt_money=fmt_money,
            fmt_qty=fmt_qty,
        )

    def _render_totals(inv: Invoice) -> str:
        return render_template(
            "partials/totals.html",
            invoice=inv,
            fmt_money=fmt_money,
        )

    def _snapshot_lines(inv: Invoice) -> None:
        """Remember the current lines so the next Undo can restore them."""
        app.state["undo"] = copy.deepcopy(inv.lines)  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # Routes
    # ------------------------------------------------------------------

    @app.get("/")
    def index() -> str:
        inv: Invoice = app.state["invoice"]  # type: ignore[attr-defined]
        return render_template(
            "editor.html",
            invoice=inv,
            issuer=issuer,
            client=client,
            fmt_money=fmt_money,
            fmt_qty=fmt_qty,
            fmt_date=lambda d: fmt_date(d, date_format),
            output_path=str(output_path),
        )

    @app.get("/static/htmx.min.js")
    def htmx_js() -> Response:
        return app.send_static_file("htmx.min.js")

    @app.get("/preview")
    def preview() -> str:
        inv: Invoice = app.state["invoice"]  # type: ignore[attr-defined]
        utd: Path | None = app.state["user_templates_dir"]  # type: ignore[attr-defined]
        return render_html(inv, issuer, client, utd)

    @app.get("/preview.pdf")
    def preview_pdf() -> Response:
        """True-to-output preview: the exact WeasyPrint render, in memory.

        Byte-identical to what the Generate PDF button writes, so the PDF
        preview shows real pagination, fonts, and page footers.
        """
        inv: Invoice = app.state["invoice"]  # type: ignore[attr-defined]
        utd: Path | None = app.state["user_templates_dir"]  # type: ignore[attr-defined]
        from harvest_invoicer.render import render_pdf_bytes  # noqa: PLC0415

        try:
            pdf = render_pdf_bytes(inv, issuer, client, utd)
        except Exception as exc:  # noqa: BLE001 — surface render errors in the pane
            return Response(
                f"<p>PDF preview unavailable: {escape(str(exc))}</p>",
                status=503,
                mimetype="text/html",
            )
        return Response(
            pdf,
            mimetype="application/pdf",
            headers={
                "Content-Disposition": "inline; filename=preview.pdf",
                "Cache-Control": "no-store",
            },
        )

    @app.get("/style.css")
    def style_css() -> Response:
        """Serve the effective style.css used by the PDF renderer.

        Uses the same ChoiceLoader-like lookup as *render.py*: the user's
        templates directory takes precedence when it contains a ``style.css``,
        falling back to the packaged one.
        """
        utd: Path | None = app.state["user_templates_dir"]  # type: ignore[attr-defined]
        css_path = Path(_effective_base_url(utd)) / "style.css"
        return Response(css_path.read_text(encoding="utf-8"), mimetype="text/css")

    @app.get("/favicon.ico")
    def favicon() -> Response:
        """Return 204 to silence browser favicon requests."""
        return Response(status=204)

    @app.get("/pdf")
    def serve_pdf() -> Response:
        """Serve the last generated PDF (the Generate button's output file)."""
        out: Path = app.state["output_path"]  # type: ignore[attr-defined]
        if not out.exists():
            return Response(
                "<p>No PDF generated yet. Click Generate PDF first.</p>",
                status=404,
                mimetype="text/html",
            )
        return Response(
            out.read_bytes(),
            mimetype="application/pdf",
            headers={
                "Content-Disposition": f"inline; filename={out.name}",
                "Cache-Control": "no-store",
            },
        )

    # --- Line mutations ---

    @app.post("/lines/update/<int:idx>")
    def update_line(idx: int) -> Response:
        inv: Invoice = app.state["invoice"]  # type: ignore[attr-defined]
        if 0 <= idx < len(inv.lines):
            _snapshot_lines(inv)
            line = inv.lines[idx]
            line.concept = request.form.get("concept", line.concept)
            with contextlib.suppress(ValueError):
                line.quantity = float(request.form.get("quantity", str(line.quantity)))
            with contextlib.suppress(ValueError):
                line.unit_price = float(
                    request.form.get("unit_price", str(line.unit_price))
                )
        rows_html = _render_rows(inv)
        totals_html = _render_totals(inv)
        return Response(
            rows_html + totals_html,
            content_type="text/html",
        )

    @app.post("/lines/drop/<int:idx>")
    def drop_line(idx: int) -> Response:
        inv: Invoice = app.state["invoice"]  # type: ignore[attr-defined]
        if 0 <= idx < len(inv.lines):
            _snapshot_lines(inv)
            inv.lines.pop(idx)
        rows_html = _render_rows(inv)
        totals_html = _render_totals(inv)
        return Response(rows_html + totals_html, content_type="text/html")

    @app.post("/lines/add")
    def add_line() -> Response:
        inv: Invoice = app.state["invoice"]  # type: ignore[attr-defined]
        _snapshot_lines(inv)
        inv.lines.append(InvoiceLine(concept="New item", unit_price=0.0, quantity=1.0))
        rows_html = _render_rows(inv)
        totals_html = _render_totals(inv)
        return Response(rows_html + totals_html, content_type="text/html")

    @app.post("/lines/merge")
    def merge_lines() -> Response:
        """Merge checked lines: sum hours, weighted-average rate."""
        inv: Invoice = app.state["invoice"]  # type: ignore[attr-defined]
        selected_str = request.form.getlist("selected")
        selected_idx = {int(s) for s in selected_str if s.isdigit()}
        if len(selected_idx) < 2:
            rows_html = _render_rows(inv)
            totals_html = _render_totals(inv)
            return Response(rows_html + totals_html, content_type="text/html")

        to_merge = [
            (i, inv.lines[i]) for i in sorted(selected_idx) if i < len(inv.lines)
        ]
        total_hours = sum(ln.quantity for _, ln in to_merge)
        weighted_rate = (
            sum(ln.unit_price * ln.quantity for _, ln in to_merge) / total_hours
            if total_hours > 0
            else 0.0
        )
        first_idx, first_line = to_merge[0]
        merged = InvoiceLine(
            concept=first_line.concept,
            unit_price=round(weighted_rate, 4),
            quantity=round(total_hours, 4),
            vat_rate=first_line.vat_rate,
        )
        _snapshot_lines(inv)
        # Remove selected (highest index first to preserve positions)
        for i in sorted(selected_idx, reverse=True):
            if i < len(inv.lines):
                inv.lines.pop(i)
        inv.lines.insert(first_idx, merged)
        rows_html = _render_rows(inv)
        totals_html = _render_totals(inv)
        return Response(rows_html + totals_html, content_type="text/html")

    def _fetch_status(message: str, *, error: bool = False) -> str:
        """OOB status span swapped into #fetch-status next to the button."""
        css = "fetch-err" if error else "fetch-ok"
        return (
            f'<span id="fetch-status" hx-swap-oob="outerHTML" class="{css}">'
            f"{escape(message)}</span>"
        )

    @app.post("/lines/fetch")
    def fetch_lines_route() -> Response:
        """Re-import line items from Harvest for the selected period.

        Reads period_start/period_end from the form, replaces the invoice
        lines with freshly fetched data, and updates the invoice period.
        Errors are reported inline without touching the current lines.
        """
        inv: Invoice = app.state["invoice"]  # type: ignore[attr-defined]

        def _respond(status: str, *, error: bool = False) -> Response:
            rows_html = _render_rows(inv)
            totals_html = _render_totals(inv)
            return Response(
                rows_html + totals_html + _fetch_status(status, error=error),
                content_type="text/html",
            )

        try:
            ps = date.fromisoformat(request.form.get("period_start", "").strip())
            pe = date.fromisoformat(request.form.get("period_end", "").strip())
        except ValueError:
            return _respond("Select a valid period start and end first.", error=True)
        if pe < ps:
            return _respond("Period end must not be before period start.", error=True)
        if fetch_callback is None:
            return _respond("Re-fetching is not available in this session.", error=True)

        try:
            new_lines = fetch_callback(ps, pe)
        except Exception as exc:  # noqa: BLE001 — surface fetch errors inline
            return _respond(str(exc), error=True)

        raw_count = len(new_lines)
        merged_note = ""
        if request.form.get("merge_duplicates") == "on":
            new_lines = merge_duplicate_lines(new_lines)
            if len(new_lines) != raw_count:
                merged_note = f" ({raw_count} before merging duplicates)"

        _snapshot_lines(inv)
        inv.lines[:] = new_lines
        inv.period_start = ps
        inv.period_end = pe
        return _respond(
            f"Imported {len(new_lines)} lines{merged_note} for {ps} to {pe}."
        )

    @app.post("/lines/merge-duplicates")
    def merge_duplicates_route() -> Response:
        """Collapse lines with identical concept, rate, and VAT into one."""
        inv: Invoice = app.state["invoice"]  # type: ignore[attr-defined]
        _snapshot_lines(inv)
        inv.lines[:] = merge_duplicate_lines(inv.lines)
        rows_html = _render_rows(inv)
        totals_html = _render_totals(inv)
        return Response(rows_html + totals_html, content_type="text/html")

    @app.post("/lines/undo")
    def undo_lines() -> Response:
        """Restore the line items from before the last change.

        The current lines become the new snapshot, so a second Undo
        re-applies the change (acts as redo).  No-op without history.
        """
        inv: Invoice = app.state["invoice"]  # type: ignore[attr-defined]
        snapshot = app.state["undo"]  # type: ignore[attr-defined]
        if snapshot is not None:
            app.state["undo"] = copy.deepcopy(inv.lines)  # type: ignore[attr-defined]
            inv.lines[:] = snapshot
        rows_html = _render_rows(inv)
        totals_html = _render_totals(inv)
        return Response(rows_html + totals_html, content_type="text/html")

    # --- Metadata edits ---

    @app.post("/meta/update")
    def update_meta() -> str:
        inv: Invoice = app.state["invoice"]  # type: ignore[attr-defined]
        number_val = request.form.get("number", "").strip()
        if number_val:
            inv.number = number_val
        issue_val = request.form.get("issue_date", "").strip()
        if issue_val:
            with contextlib.suppress(ValueError):
                inv.issue_date = date.fromisoformat(issue_val)
        due_val = request.form.get("due_date", "").strip()
        if due_val:
            with contextlib.suppress(ValueError):
                inv.due_date = date.fromisoformat(due_val)
        # Service period is customizable; clearing a field removes it.
        if "period_start" in request.form:
            ps_val = request.form.get("period_start", "").strip()
            if ps_val:
                with contextlib.suppress(ValueError):
                    inv.period_start = date.fromisoformat(ps_val)
            else:
                inv.period_start = None
        if "period_end" in request.form:
            pe_val = request.form.get("period_end", "").strip()
            if pe_val:
                with contextlib.suppress(ValueError):
                    inv.period_end = date.fromisoformat(pe_val)
            else:
                inv.period_end = None
        legal_val = request.form.get("legal_note", "").strip()
        inv.legal_note = legal_val or None
        return render_template(
            "partials/meta.html",
            invoice=inv,
            fmt_date=lambda d: fmt_date(d, date_format),
        )

    # --- Settings ---

    def _persist_json(
        path: Path | None, data: dict[str, object] | dict[str, dict[str, object]]
    ) -> str:
        """Write config back to disk; describe where (or that we couldn't)."""
        if path is None:
            return " (this session only; no config file to write)"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return f" and written to {path}"

    def _render_clients_block(status: str | None = None, *, error: bool = False) -> str:
        return render_template(
            "partials/settings_clients.html",
            clients=app.state["clients"],  # type: ignore[attr-defined]
            current_client_key=app.state["current_client_key"],  # type: ignore[attr-defined]
            status=status,
            status_error=error,
        )

    @app.get("/settings")
    def settings_page() -> str:
        return render_template(
            "settings.html",
            issuer=issuer,
            clients=app.state["clients"],  # type: ignore[attr-defined]
            current_client_key=app.state["current_client_key"],  # type: ignore[attr-defined]
            status=None,
            status_error=False,
        )

    @app.post("/settings/issuer")
    def settings_issuer_save() -> str:
        """Validate and save the issuer config (file + running session)."""

        def _status(msg: str, *, error: bool = False) -> str:
            css = "status-err" if error else "status-ok"
            return f'<span id="issuer-status" class="{css}">{escape(msg)}</span>'

        text_fields = (
            "name",
            "address_line1",
            "address_line2",
            "country",
            "tax_id",
            "tax_id_label",
            "phone",
            "email",
            "date_format",
            "legal_note",
            "number_template",
        )
        values = {f: request.form.get(f, "").strip() for f in text_fields}
        iban = request.form.get("iban", "").strip()
        bic = request.form.get("bic", "").strip()

        required = (
            "name",
            "address_line1",
            "address_line2",
            "country",
            "tax_id",
            "phone",
            "email",
        )
        missing = [f for f in required if not values[f]]
        if not iban:
            missing.append("iban")
        if not bic:
            missing.append("bic")
        if missing:
            return _status("Missing required fields: " + ", ".join(missing), error=True)

        # Mutate the shared issuer dict in place so the preview updates too.
        for f in text_fields:
            if values[f]:
                issuer[f] = values[f]
            else:
                issuer.pop(f, None)
        bank = issuer.get("bank")
        if not isinstance(bank, dict):
            bank = {}
            issuer["bank"] = bank
        bank["iban"] = iban
        bank["bic"] = bic

        suffix = _persist_json(issuer_path, issuer)
        return _status("Issuer saved" + suffix)

    @app.post("/settings/clients/save")
    def settings_clients_save() -> str:
        """Add or update a clients.json entry (file + running session)."""
        clients_map: dict[str, dict[str, object]] = app.state["clients"]  # type: ignore[attr-defined]
        original = request.form.get("original_key", "").strip()
        new_key = request.form.get("key", "").strip()
        if not new_key:
            return _render_clients_block(
                "Harvest client name (key) is required.", error=True
            )

        fields = (
            "name",
            "address_line1",
            "address_line2",
            "country",
            "tax_id",
            "tax_id_label",
        )
        values = {f: request.form.get(f, "").strip() for f in fields}
        required = ("name", "address_line1", "address_line2", "country", "tax_id")
        missing = [f for f in required if not values[f]]
        if missing:
            return _render_clients_block(
                "Missing required fields: " + ", ".join(missing), error=True
            )

        vat_raw = request.form.get("vat_rate", "").strip()
        vat_val: float | None = None
        if vat_raw:
            try:
                vat_val = float(vat_raw)
            except ValueError:
                vat_val = -1.0
            if not 0.0 <= vat_val <= 1.0:
                return _render_clients_block(
                    "VAT rate must be a number between 0 and 1 (e.g. 0.21).",
                    error=True,
                )

        # Recurring extra lines: "description ; unit price [; quantity]"
        extra_items: list[dict[str, object]] = []
        for lineno, row in enumerate(
            request.form.get("extra_lines", "").splitlines(), start=1
        ):
            text = row.strip()
            if not text:
                continue
            parts = [p.strip() for p in text.split(";")]
            if len(parts) not in (2, 3) or not parts[0]:
                return _render_clients_block(
                    f"Extra line {lineno}: expected "
                    "'description ; unit price ; quantity'.",
                    error=True,
                )
            try:
                price = float(parts[1])
                qty = float(parts[2]) if len(parts) == 3 else 1.0
            except ValueError:
                return _render_clients_block(
                    f"Extra line {lineno}: unit price and quantity must be numbers.",
                    error=True,
                )
            extra_items.append(
                {"concept": parts[0], "unit_price": price, "quantity": qty}
            )

        # Reuse the existing entry object so the current invoice's client
        # (same object) picks up the edits immediately.
        if original and original in clients_map:
            entry = clients_map.pop(original)
        elif new_key in clients_map:
            entry = clients_map.pop(new_key)
        else:
            entry = {}
        for f in fields:
            if values[f]:
                entry[f] = values[f]
            else:
                entry.pop(f, None)
        if vat_val is not None:
            entry["vat_rate"] = vat_val
        else:
            entry.pop("vat_rate", None)
        if extra_items:
            entry["extra_lines"] = extra_items
        else:
            entry.pop("extra_lines", None)
        clients_map[new_key] = entry

        if original and original == app.state["current_client_key"]:  # type: ignore[attr-defined]
            app.state["current_client_key"] = new_key  # type: ignore[attr-defined]

        suffix = _persist_json(clients_path, clients_map)
        return _render_clients_block(f"Client '{new_key}' saved{suffix}")

    @app.post("/settings/clients/delete")
    def settings_clients_delete() -> str:
        """Remove a clients.json entry (guarding the invoice's client)."""
        clients_map: dict[str, dict[str, object]] = app.state["clients"]  # type: ignore[attr-defined]
        original = request.form.get("original_key", "").strip()
        if original == app.state["current_client_key"]:  # type: ignore[attr-defined]
            return _render_clients_block(
                "Cannot delete the client used by the current invoice.",
                error=True,
            )
        if original not in clients_map:
            return _render_clients_block(f"Client '{original}' not found.", error=True)
        del clients_map[original]
        suffix = _persist_json(clients_path, clients_map)
        return _render_clients_block(f"Client '{original}' deleted{suffix}")

    # --- PDF render ---

    @app.post("/render")
    def render_pdf_route() -> str:
        inv: Invoice = app.state["invoice"]  # type: ignore[attr-defined]
        out: Path = app.state["output_path"]  # type: ignore[attr-defined]
        utd: Path | None = app.state["user_templates_dir"]  # type: ignore[attr-defined]
        from harvest_invoicer.render import render_pdf  # noqa: PLC0415

        render_pdf(inv, issuer, client, out, utd)
        return render_template("partials/render_done.html", output_path=str(out))

    # --- Quit ---

    @app.post("/quit")
    def quit_server() -> str:
        """Shut down the Werkzeug dev server gracefully."""

        def _stop() -> None:
            import time  # noqa: PLC0415

            time.sleep(0.2)
            os._exit(0)

        t = threading.Thread(target=_stop, daemon=True)
        t.start()
        return "<p>Server shutting down…</p>"

    return app
