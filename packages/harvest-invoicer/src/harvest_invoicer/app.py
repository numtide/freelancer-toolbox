"""Flask editor application for interactive invoice editing."""

from __future__ import annotations

import contextlib
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
    app.state = {  # type: ignore[attr-defined]
        "invoice": invoice,
        "issuer": issuer,
        "client": client,
        "output_path": output_path,
        "user_templates_dir": user_templates_dir,
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

    # --- Line mutations ---

    @app.post("/lines/update/<int:idx>")
    def update_line(idx: int) -> Response:
        inv: Invoice = app.state["invoice"]  # type: ignore[attr-defined]
        if 0 <= idx < len(inv.lines):
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
            inv.lines.pop(idx)
        rows_html = _render_rows(inv)
        totals_html = _render_totals(inv)
        return Response(rows_html + totals_html, content_type="text/html")

    @app.post("/lines/add")
    def add_line() -> Response:
        inv: Invoice = app.state["invoice"]  # type: ignore[attr-defined]
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
        inv.lines[:] = merge_duplicate_lines(inv.lines)
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
