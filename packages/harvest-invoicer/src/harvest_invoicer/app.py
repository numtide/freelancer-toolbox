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

from harvest_invoicer.fetch import apply_client_vat, client_extra_lines
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
    import_raw: list[InvoiceLine] | None = None,
    import_merge: bool = True,
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

    ``import_raw`` is the raw per-person result of the initial Harvest
    fetch (pre merge/VAT/extras).  It feeds the import roster: person chips
    that choose whose hours the invoice includes, re-derived locally
    without re-hitting the API.  ``import_merge`` records whether duplicate
    merging applies when re-deriving.
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
        "last_fetch_range": (period_start, period_end)
        if period_start and period_end
        else None,
        "import_raw": copy.deepcopy(import_raw) if import_raw else [],
        "selected_people": {ln.user for ln in (import_raw or []) if ln.user},
        "import_merge": import_merge,
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

    _undo_svg = (
        '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.7"><path d="M3 7v6h6"></path>'
        '<path d="M3.5 13a9 9 0 1 0 2.3-7.7L3 8"></path></svg>'
    )

    def _oob_extras(inv: Invoice) -> str:
        """OOB fragments riding along with every line mutation response:
        the line-items header meta, the preview count, and the undo button
        (greyed out while there is no history)."""
        count = len(inv.lines)
        meta = (
            f'<span id="items-meta" hx-swap-oob="outerHTML" class="hv-num card-meta">'
            f"{count} · {fmt_money(inv.grand_total)} {escape(inv.currency)} EUR"
            f"</span>"
        )
        # currency displayed once; strip duplicate token
        meta = (
            f'<span id="items-meta" hx-swap-oob="outerHTML" class="hv-num card-meta">'
            f"{count} · {fmt_money(inv.grand_total)} {escape(inv.currency)}"
            f"</span>"
        )
        pcount = (
            f'<span id="preview-count" hx-swap-oob="outerHTML" class="hv-num preview-count">'
            f"{count} line items</span>"
        )
        has_undo = app.state["undo"] is not None  # type: ignore[attr-defined]
        undo_cls = "icon-btn-sm" if has_undo else "icon-btn-sm is-disabled"
        undo = (
            f'<button id="undo-btn" hx-swap-oob="outerHTML" type="button" '
            f'class="{undo_cls}" title="Undo last change" '
            f'hx-post="/lines/undo" hx-target="#line-rows" hx-swap="outerHTML">'
            f"{_undo_svg}</button>"
        )
        return meta + pcount + undo

    def _store_import(raw_lines: list[InvoiceLine], merge: bool) -> None:
        """Remember the raw per-person import for chip-based re-derives."""
        app.state["import_raw"] = copy.deepcopy(raw_lines)  # type: ignore[attr-defined]
        app.state["selected_people"] = {  # type: ignore[attr-defined]
            ln.user for ln in raw_lines if ln.user
        }
        app.state["import_merge"] = merge  # type: ignore[attr-defined]

    def _derive_from_import(inv: Invoice) -> None:
        """Rebuild the invoice lines from the stored import + selection."""
        raw: list[InvoiceLine] = app.state["import_raw"]  # type: ignore[attr-defined]
        selected: set[str] = app.state["selected_people"]  # type: ignore[attr-defined]
        lines = [copy.deepcopy(ln) for ln in raw if not ln.user or ln.user in selected]
        if app.state["import_merge"]:  # type: ignore[attr-defined]
            lines = merge_duplicate_lines(lines)
        cur_client: dict[str, str] = app.state["client"]  # type: ignore[attr-defined]
        inv.lines[:] = apply_client_vat(
            lines + client_extra_lines(cur_client), cur_client
        )

    def _import_note_ctx() -> dict[str, object]:
        raw: list[InvoiceLine] = app.state["import_raw"]  # type: ignore[attr-defined]
        selected: set[str] = app.state["selected_people"]  # type: ignore[attr-defined]
        hours: dict[str, float] = {}
        for ln in raw:
            if ln.user:
                hours[ln.user] = hours.get(ln.user, 0.0) + ln.quantity
        roster = sorted(hours.items())
        return {
            "roster": roster,
            "selected": selected,
            "you": str(issuer.get("harvest_user") or "").strip(),
            "total_hours": round(sum(hours.values()), 2),
            "selected_hours": round(sum(h for n, h in roster if n in selected), 2),
        }

    def _import_note_oob() -> str:
        return render_template(
            "partials/import_note.html", oob=True, **_import_note_ctx()
        )

    def _lines_response(inv: Invoice, status_html: str = "") -> Response:
        """Standard response for line mutations: rows + totals + OOB extras."""
        return Response(
            _render_rows(inv) + _render_totals(inv) + _oob_extras(inv) + status_html,
            content_type="text/html",
        )

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
            client=app.state["client"],  # type: ignore[attr-defined]
            clients=app.state["clients"],  # type: ignore[attr-defined]
            current_client_key=app.state["current_client_key"],  # type: ignore[attr-defined]
            fmt_money=fmt_money,
            fmt_qty=fmt_qty,
            fmt_date=lambda d: fmt_date(d, date_format),
            output_path=str(output_path),
            has_undo=app.state["undo"] is not None,  # type: ignore[attr-defined]
            **_import_note_ctx(),
        )

    @app.get("/static/htmx.min.js")
    def htmx_js() -> Response:
        return app.send_static_file("htmx.min.js")

    @app.get("/preview")
    def preview() -> str:
        inv: Invoice = app.state["invoice"]  # type: ignore[attr-defined]
        utd: Path | None = app.state["user_templates_dir"]  # type: ignore[attr-defined]
        cur_client: dict[str, str] = app.state["client"]  # type: ignore[attr-defined]
        return render_html(inv, issuer, cur_client, utd)

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
            pdf = render_pdf_bytes(
                inv,
                issuer,
                app.state["client"],  # type: ignore[attr-defined]
                utd,
            )
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
        """Serve the vendored Harvest favicon."""
        return Response(
            (_STATIC_DIR / "favicon.svg").read_bytes(),
            mimetype="image/svg+xml",
            headers={"Cache-Control": "public, max-age=86400"},
        )

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
        return _lines_response(inv)

    @app.post("/lines/drop/<int:idx>")
    def drop_line(idx: int) -> Response:
        inv: Invoice = app.state["invoice"]  # type: ignore[attr-defined]
        if 0 <= idx < len(inv.lines):
            _snapshot_lines(inv)
            inv.lines.pop(idx)
        return _lines_response(inv)

    @app.post("/lines/add")
    def add_line() -> Response:
        inv: Invoice = app.state["invoice"]  # type: ignore[attr-defined]
        _snapshot_lines(inv)
        inv.lines.append(InvoiceLine(concept="", unit_price=0.0, quantity=0.0))
        return _lines_response(inv)

    @app.post("/lines/delete-selected")
    def delete_selected_lines() -> Response:
        """Remove all checked rows (the selection bar's Delete action)."""
        inv: Invoice = app.state["invoice"]  # type: ignore[attr-defined]
        selected = {int(s) for s in request.form.getlist("selected") if s.isdigit()}
        valid = sorted((i for i in selected if i < len(inv.lines)), reverse=True)
        if valid:
            _snapshot_lines(inv)
            for i in valid:
                inv.lines.pop(i)
        return _lines_response(inv)

    @app.post("/lines/merge")
    def merge_lines() -> Response:
        """Merge checked lines: sum hours, weighted-average rate."""
        inv: Invoice = app.state["invoice"]  # type: ignore[attr-defined]
        selected_str = request.form.getlist("selected")
        selected_idx = {int(s) for s in selected_str if s.isdigit()}
        if len(selected_idx) < 2:
            return _lines_response(inv)

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
        return _lines_response(inv)

    def _fetch_status(
        message: str, *, error: bool = False, extra_html: str = ""
    ) -> str:
        """OOB status span swapped into #fetch-status next to the button.

        ``extra_html`` must already be escaped/safe markup (e.g. the
        click-to-pick user buttons).
        """
        css = "fetch-err" if error else "fetch-ok"
        return (
            f'<span id="fetch-status" hx-swap-oob="outerHTML" class="{css}">'
            f"{escape(message)}{extra_html}</span>"
        )

    @app.post("/lines/fetch")
    def fetch_lines_route() -> Response:
        """Re-import line items from Harvest for the import range.

        Reads fetch_start/fetch_end from the form and replaces the invoice
        lines with freshly fetched data.  The invoice's service period is
        independent and never modified here — edit it in the details form.
        Errors are reported inline without touching the current lines.
        """
        inv: Invoice = app.state["invoice"]  # type: ignore[attr-defined]

        def _respond(
            status: str, *, error: bool = False, extra_html: str = ""
        ) -> Response:
            return _lines_response(
                inv, _fetch_status(status, error=error, extra_html=extra_html)
            )

        try:
            ps = date.fromisoformat(request.form.get("fetch_start", "").strip())
            pe = date.fromisoformat(request.form.get("fetch_end", "").strip())
        except ValueError:
            return _respond("Select a valid import range first.", error=True)
        if pe < ps:
            return _respond("Import end must not be before import start.", error=True)
        if fetch_callback is None:
            return _respond("Re-fetching is not available in this session.", error=True)

        try:
            raw_lines = fetch_callback(ps, pe)
        except Exception as exc:  # noqa: BLE001 — surface fetch errors inline
            return _respond(str(exc), error=True)

        _store_import(raw_lines, request.form.get("merge_duplicates") == "on")
        _snapshot_lines(inv)
        _derive_from_import(inv)
        app.state["last_fetch_range"] = (ps, pe)  # type: ignore[attr-defined]

        return _respond(
            f"Imported {len(inv.lines)} lines for {ps} to {pe}.",
            extra_html=_import_note_oob(),
        )

    @app.post("/lines/people")
    def toggle_people() -> Response:
        """Choose whose hours the invoice includes (import roster chips).

        Re-derives the lines from the stored import — never re-fetches.
        """
        inv: Invoice = app.state["invoice"]  # type: ignore[attr-defined]
        raw: list[InvoiceLine] = app.state["import_raw"]  # type: ignore[attr-defined]
        roster_names = {ln.user for ln in raw if ln.user}
        selected: set[str] = set(app.state["selected_people"])  # type: ignore[attr-defined]
        if request.form.get("all"):
            selected = set(roster_names)
        elif request.form.get("none"):
            selected = set()
        else:
            name = request.form.get("toggle", "").strip()
            if name in selected:
                selected.discard(name)
            elif name in roster_names:
                selected.add(name)
        app.state["selected_people"] = selected  # type: ignore[attr-defined]
        _snapshot_lines(inv)
        _derive_from_import(inv)
        return _lines_response(inv, _import_note_oob())

    @app.post("/settings/harvest-user")
    def pick_harvest_user() -> Response:
        """Set harvest_user from a warning button and re-import.

        Persists the choice to issuer.json (when a config path exists) and
        re-fetches the last import range so the table immediately shows
        only the picked person's hours.
        """
        inv: Invoice = app.state["invoice"]  # type: ignore[attr-defined]

        def _respond2(status: str, *, error: bool = False) -> Response:
            return _lines_response(inv, _fetch_status(status, error=error))

        name = request.form.get("user", "").strip()
        if not name:
            return _respond2("No user name given.", error=True)
        issuer["harvest_user"] = name
        suffix = _persist_json(issuer_path, issuer)

        rng = app.state["last_fetch_range"]  # type: ignore[attr-defined]
        if fetch_callback is None or rng is None:
            return _respond2(f"harvest_user set to '{name}'{suffix}.")
        ps, pe = rng
        try:
            raw_lines = fetch_callback(ps, pe)
        except Exception as exc:  # noqa: BLE001 — surface fetch errors inline
            return _respond2(str(exc), error=True)
        _store_import(raw_lines, merge=True)
        _snapshot_lines(inv)
        _derive_from_import(inv)
        return _lines_response(
            inv,
            _fetch_status(
                f"harvest_user set to '{name}'{suffix}; imported "
                f"{len(inv.lines)} lines for {ps} to {pe}."
            )
            + _import_note_oob(),
        )

    def _client_inset_oob() -> str:
        """OOB re-render of the client picker and details inset."""
        ctx = {
            "client": app.state["client"],  # type: ignore[attr-defined]
            "clients": app.state["clients"],  # type: ignore[attr-defined]
            "current_client_key": app.state["current_client_key"],  # type: ignore[attr-defined]
            "invoice": app.state["invoice"],  # type: ignore[attr-defined]
            "oob": True,
        }
        return render_template("partials/client_inset.html", **ctx) + render_template(
            "partials/client_picker.html", **ctx
        )

    @app.post("/invoice/client")
    def switch_client() -> Response:
        """Switch the invoice's bill-to client (from the editor dropdown).

        Keeps the current Harvest lines and any manual edits; swaps the
        recurring extra lines to the new client's set and applies its
        vat_rate uniformly.  Never re-fetches.
        """
        inv: Invoice = app.state["invoice"]  # type: ignore[attr-defined]
        clients_map: dict[str, dict[str, str]] = app.state["clients"]  # type: ignore[attr-defined]
        key = request.form.get("client_key", "").strip()
        entry = clients_map.get(key)

        if entry is None:
            return _lines_response(inv)

        _snapshot_lines(inv)
        app.state["client"] = entry  # type: ignore[attr-defined]
        app.state["current_client_key"] = key  # type: ignore[attr-defined]

        # Old client's recurring extras out, new client's in.
        kept = [line for line in inv.lines if line.origin != "extra"]
        inv.lines[:] = kept + client_extra_lines(entry)
        # The new client's effective VAT applies to all lines (0 when unset,
        # replacing any rate inherited from the previous client).
        vat = float(str(entry.get("vat_rate") or 0.0))
        for line in inv.lines:
            line.vat_rate = vat
        return _lines_response(inv, _client_inset_oob())

    @app.post("/lines/merge-duplicates")
    def merge_duplicates_route() -> Response:
        """Collapse lines with identical concept, rate, and VAT into one."""
        inv: Invoice = app.state["invoice"]  # type: ignore[attr-defined]
        _snapshot_lines(inv)
        inv.lines[:] = merge_duplicate_lines(inv.lines)
        return _lines_response(inv)

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
        return _lines_response(inv)

    @app.post("/lines/reorder")
    def reorder_lines() -> Response:
        """Apply a new line order from the editor's drag-and-drop.

        ``order`` is a comma-separated list of the current indices in their
        new sequence; anything that is not a complete permutation is
        ignored (the table is re-rendered as-is).
        """
        inv: Invoice = app.state["invoice"]  # type: ignore[attr-defined]
        raw = request.form.get("order", "")
        try:
            order = [int(s) for s in raw.split(",") if s.strip() != ""]
        except ValueError:
            order = []
        if order and sorted(order) == list(range(len(inv.lines))):
            _snapshot_lines(inv)
            inv.lines[:] = [inv.lines[i] for i in order]
        return _lines_response(inv)

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
        head_oob = (
            f'<span id="inv-no-head" hx-swap-oob="outerHTML" class="hv-num card-meta">'
            f"Invoice {escape(inv.number)}</span>"
        )
        return (
            render_template("partials/meta.html", invoice=inv)
            + render_template("partials/period.html", invoice=inv)
            + head_oob
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
            "harvest_user",
            "default_bill_to",
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
        dbt = values["default_bill_to"]
        clients_map_i: dict[str, dict[str, object]] = app.state["clients"]  # type: ignore[attr-defined]
        if dbt and dbt not in clients_map_i:
            available = ", ".join(sorted(clients_map_i.keys())) or "(none)"
            return _status(
                f"default_bill_to '{dbt}' is not a clients.json key. "
                f"Available: {available}.",
                error=True,
            )

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

    def _parse_extra_lines(
        text: str,
    ) -> tuple[list[dict[str, object]], str | None]:
        """Parse 'description ; unit price [; quantity]' rows -> (items, error)."""
        items: list[dict[str, object]] = []
        for lineno, row in enumerate(text.splitlines(), start=1):
            stripped = row.strip()
            if not stripped:
                continue
            parts = [p.strip() for p in stripped.split(";")]
            if len(parts) not in (2, 3) or not parts[0]:
                return [], (
                    f"Extra line {lineno}: expected "
                    "'description ; unit price ; quantity'."
                )
            try:
                price = float(parts[1])
                qty = float(parts[2]) if len(parts) == 3 else 1.0
            except ValueError:
                return [], (
                    f"Extra line {lineno}: unit price and quantity must be numbers."
                )
            items.append({"concept": parts[0], "unit_price": price, "quantity": qty})
        return items, None

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
            "email",
        )
        values = {f: request.form.get(f, "").strip() for f in fields}
        required = ("name", "address_line1", "address_line2", "country", "tax_id")
        missing = [f for f in required if not values[f]]
        if missing:
            return _render_clients_block(
                "Missing required fields: " + ", ".join(missing), error=True
            )
        if values["email"] and "@" not in values["email"]:
            return _render_clients_block(
                "Email must be a valid address (missing '@').", error=True
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

        extra_items, extra_err = _parse_extra_lines(request.form.get("extra_lines", ""))
        if extra_err:
            return _render_clients_block(extra_err, error=True)

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

        cur_client: dict[str, str] = app.state["client"]  # type: ignore[attr-defined]
        render_pdf(inv, issuer, cur_client, out, utd)
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
