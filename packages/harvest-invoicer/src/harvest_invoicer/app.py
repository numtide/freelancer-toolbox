"""Flask editor application for interactive invoice editing."""

from __future__ import annotations

import contextlib
import copy
import hashlib
import json
import os
import threading
from collections import deque
from dataclasses import asdict
from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from flask import Flask, Response, g, render_template, request
from markupsafe import escape

from harvest_invoicer.db import (
    clear_draft,
    get_draft,
    save_clients,
    save_draft,
    save_email,
    save_issuer,
)
from harvest_invoicer.fetch import apply_client_vat, client_extra_lines
from harvest_invoicer.i18n import SUPPORTED_LANGUAGES
from harvest_invoicer.model import (
    DEFAULT_PAYMENT_TERM_DAYS,
    Invoice,
    InvoiceLine,
    fmt_money,
    merge_duplicate_lines,
)
from harvest_invoicer.render import _effective_base_url, pdf_from_html, render_html

if TYPE_CHECKING:
    from collections.abc import Callable

_LOCAL_HOSTNAMES = ("127.0.0.1", "localhost")

# Depth of the undo/redo history stacks.
_UNDO_LIMIT = 20

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_STATIC_DIR = Path(__file__).parent / "static"


def _toast_header(kind: str, title: str, body: str = "") -> dict[str, str]:
    """HX-Trigger header that pops a transient toast on the client.

    ``kind`` is "ok" or "err". The toast renders a bold *title* and an
    optional muted *body* line; static/toast.js listens for the
    ``showtoast`` event htmx dispatches from this header.
    """
    payload = {"title": title, "body": body, "kind": kind}
    return {"HX-Trigger": json.dumps({"showtoast": payload})}


def _line_from_dict(data: dict[str, Any]) -> InvoiceLine:
    """Rebuild an InvoiceLine from its draft (JSON) representation."""
    return InvoiceLine(
        concept=str(data.get("concept", "")),
        unit_price=float(data.get("unit_price", 0.0)),
        quantity=float(data.get("quantity", 0.0)),
        vat_rate=float(data.get("vat_rate", 0.0)),
        origin=str(data.get("origin", "harvest")),
        user=str(data["user"]) if data.get("user") else None,
    )


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
    db_path: Path | None = None,
    import_raw: list[InvoiceLine] | None = None,
    import_merge: bool = True,
    allowed_hosts: frozenset[str] = frozenset(),
    email_config: dict[str, object] | None = None,
) -> Flask:
    """Create and configure the Flask editor application.

    State (the current invoice) lives on ``app.state`` — a plain object that
    is mutated in-place by htmx POST handlers.  The app is single-user with
    no auth; a CSRF guard restricts mutating requests to the served host(s).
    ``allowed_hosts`` extends the loopback default (e.g. when binding to a
    LAN address); a literal ``"*"`` accepts any Host (wildcard binds).

    When *user_templates_dir* is supplied the ChoiceLoader (in render.py)
    checks that directory first, falling back to the packaged templates.

    ``fetch_callback`` re-imports line items for a (start, end) date range —
    the editor's "Fetch from Harvest" button.  When ``None`` the button
    reports that re-fetching is unavailable.

    ``clients`` is the full client mapping (for the settings page);
    ``db_path`` is the state database the settings routes persist to.
    When ``None`` (demo mode, tests) settings edits apply to the running
    session only.

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
    # "undo_stack"/"redo_stack" hold bounded histories of editing snapshots:
    # each mutation pushes the pre-change state onto undo (clearing redo);
    # Undo/Redo move a snapshot between the two stacks.
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
        "undo_stack": deque(maxlen=_UNDO_LIMIT),
        "redo_stack": deque(maxlen=_UNDO_LIMIT),
        "last_fetch_range": (period_start, period_end)
        if period_start and period_end
        else None,
        "import_raw": copy.deepcopy(import_raw) if import_raw else [],
        "selected_people": {ln.user for ln in (import_raw or []) if ln.user},
        "import_merge": import_merge,
        # True once imported (origin "harvest") lines were hand-edited;
        # roster re-derives then ask for confirmation before discarding.
        "lines_dirty": False,
        # Whether the Harvest source bar's "Manage" panel is expanded.
        # Server-tracked so it survives the bar's OOB refreshes.
        "source_open": False,
        # Non-secret email/SMTP config (Settings > Email); the password is
        # never stored here — it comes from the environment only.
        "email": dict(email_config) if email_config else {},
        # (key, bytes) of the last WeasyPrint render, keyed on the rendered
        # HTML + effective style.css, so unchanged previews are instant.
        "pdf_cache": None,
        # True when a previous session's autosaved draft was resumed.
        "draft_restored": False,
    }

    # Hostnames the CSRF guard accepts, beyond loopback. A literal "*"
    # (set when binding to a wildcard address) accepts any Host and falls
    # back to a same-origin check for Origin/Referer.
    allowed = frozenset(_LOCAL_HOSTNAMES) | allowed_hosts
    allow_any_host = "*" in allowed

    @app.before_request
    def _reject_cross_origin() -> Response | None:
        """CSRF guard: mutating requests must come from the editor's origin.

        The server has no auth, so a malicious web page could otherwise fire
        state-changing (and config-writing) POSTs at it.  Require the Host to
        be one the server was told to serve (loopback by default, plus any
        configured host), and require a present Origin/Referer to be the
        same origin.  When bound to a wildcard address ("*"), any Host is
        accepted but Origin/Referer must still match it.
        """
        if request.method not in ("POST", "PUT", "DELETE", "PATCH"):
            return None
        host = request.host.rsplit(":", 1)[0]
        if not allow_any_host and host not in allowed:
            return Response("Forbidden: unrecognized Host.", status=403)
        origin = request.headers.get("Origin") or request.headers.get("Referer")
        if origin:
            origin_host = urlparse(origin).hostname
            same_origin = allow_any_host and origin_host == host
            if origin_host not in allowed and not same_origin:
                return Response("Forbidden: cross-origin request rejected.", status=403)
        return None

    # The dev server runs threaded so slow PDF renders don't block edits,
    # but app.state is a plain dict — serialize every state-touching
    # request on one lock.  The PDF/asset endpoints stay parallel: they
    # take the lock themselves just long enough to snapshot state, then
    # run WeasyPrint outside it.
    state_lock = threading.RLock()
    unserialized_endpoints = {
        "static",
        "htmx_js",
        "style_css",
        "favicon",
        "serve_pdf",
        "preview_pdf",
        "render_pdf_route",
        "send_invoice",
        "send_test",  # SMTP handshake — must not hold the state lock
    }

    @app.before_request
    def _acquire_state_lock() -> None:
        if request.endpoint not in unserialized_endpoints:
            state_lock.acquire()
            g.state_locked = True

    @app.teardown_request
    def _release_state_lock(_exc: BaseException | None) -> None:
        if g.pop("state_locked", False):
            state_lock.release()

    # ------------------------------------------------------------------
    # Template helpers
    # ------------------------------------------------------------------

    def _render_rows(inv: Invoice) -> str:
        return render_template(
            "partials/rows.html",
            invoice=inv,
            fmt_money=fmt_money,
            synced=bool(app.state["import_raw"]),  # type: ignore[attr-defined]
        )

    def _render_totals(inv: Invoice) -> str:
        return render_template(
            "partials/totals.html",
            invoice=inv,
            fmt_money=fmt_money,
        )

    def _capture_state(inv: Invoice) -> dict[str, Any]:
        """A deep snapshot of the editing state Undo/Redo must restore.

        Lines alone are not enough: a bill-to switch changes VAT/extras on
        the lines, so a snapshot also carries the client, roster selection,
        and import generation the lines belong to.
        """
        return {
            "lines": copy.deepcopy(inv.lines),
            "client_key": app.state["current_client_key"],  # type: ignore[attr-defined]
            "selected_people": set(app.state["selected_people"]),  # type: ignore[attr-defined]
            "import_raw": copy.deepcopy(app.state["import_raw"]),  # type: ignore[attr-defined]
            "import_merge": app.state["import_merge"],  # type: ignore[attr-defined]
            "last_fetch_range": app.state["last_fetch_range"],  # type: ignore[attr-defined]
            "lines_dirty": app.state["lines_dirty"],  # type: ignore[attr-defined]
        }

    def _restore_state(inv: Invoice, snapshot: dict[str, Any]) -> None:
        """Apply a snapshot from :func:`_capture_state` to the live state."""
        inv.lines[:] = snapshot["lines"]
        clients_map: dict[str, dict[str, str]] = app.state["clients"]  # type: ignore[attr-defined]
        key = snapshot["client_key"]
        if key is not None and key in clients_map:
            app.state["client"] = clients_map[key]  # type: ignore[attr-defined]
            app.state["current_client_key"] = key  # type: ignore[attr-defined]
        app.state["selected_people"] = snapshot["selected_people"]  # type: ignore[attr-defined]
        app.state["import_raw"] = snapshot["import_raw"]  # type: ignore[attr-defined]
        app.state["import_merge"] = snapshot["import_merge"]  # type: ignore[attr-defined]
        app.state["last_fetch_range"] = snapshot["last_fetch_range"]  # type: ignore[attr-defined]
        app.state["lines_dirty"] = snapshot["lines_dirty"]  # type: ignore[attr-defined]

    def _snapshot_lines(inv: Invoice) -> None:
        """Push the pre-mutation state onto the undo stack (a new edit
        invalidates any redo history)."""
        app.state["undo_stack"].append(_capture_state(inv))  # type: ignore[attr-defined]
        app.state["redo_stack"].clear()  # type: ignore[attr-defined]

    _undo_svg = (
        '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.7"><path d="M3 7v6h6"></path>'
        '<path d="M3.5 13a9 9 0 1 0 2.3-7.7L3 8"></path></svg>'
    )
    _redo_svg = (
        '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.7"><path d="M21 7v6h-6"></path>'
        '<path d="M20.5 13a9 9 0 1 1-2.3-7.7L21 8"></path></svg>'
    )

    def _history_btn(kind: str, enabled: bool) -> str:
        cls = "icon-btn-sm" if enabled else "icon-btn-sm is-disabled"
        svg = _undo_svg if kind == "undo" else _redo_svg
        return (
            f'<button id="{kind}-btn" hx-swap-oob="outerHTML" type="button" '
            f'class="{cls}" title="{kind.capitalize()} last change" '
            f'hx-post="/lines/{kind}" hx-target="#line-rows" hx-swap="outerHTML">'
            f"{svg}</button>"
        )

    def _oob_extras(inv: Invoice) -> str:
        """OOB fragments riding along with every line mutation response:
        the line-items header meta, the preview count, and the undo/redo
        buttons (greyed out when their stack is empty)."""
        count = len(inv.lines)
        meta = (
            f'<span id="items-meta" hx-swap-oob="outerHTML" class="hv-num card-meta">'
            f"{count} · {fmt_money(inv.grand_total)} {escape(inv.currency)}"
            f"</span>"
        )
        pcount = (
            f'<span id="preview-count" hx-swap-oob="outerHTML" class="hv-num preview-count">'
            f"{count} line items</span>"
        )
        undo = _history_btn("undo", bool(app.state["undo_stack"]))  # type: ignore[attr-defined]
        redo = _history_btn("redo", bool(app.state["redo_stack"]))  # type: ignore[attr-defined]
        return meta + pcount + undo + redo + _source_bar_oob()

    def _store_import(raw_lines: list[InvoiceLine], merge: bool) -> None:
        """Remember the raw per-person import for chip-based re-derives."""
        app.state["import_raw"] = copy.deepcopy(raw_lines)  # type: ignore[attr-defined]
        app.state["selected_people"] = {  # type: ignore[attr-defined]
            ln.user for ln in raw_lines if ln.user
        }
        app.state["import_merge"] = merge  # type: ignore[attr-defined]
        app.state["lines_dirty"] = False  # type: ignore[attr-defined]

    def _derive_from_import(inv: Invoice) -> None:
        """Rebuild the invoice lines from the stored import + selection.

        Imported ("harvest") lines are rebuilt from the raw import; rows the
        user added by hand (origin "manual") are preserved as-is; the
        client's recurring extras are re-appended.  Rebuilding discards any
        hand edits to imported lines, so callers gate on ``lines_dirty``.
        """
        raw: list[InvoiceLine] = app.state["import_raw"]  # type: ignore[attr-defined]
        selected: set[str] = app.state["selected_people"]  # type: ignore[attr-defined]
        lines = [copy.deepcopy(ln) for ln in raw if not ln.user or ln.user in selected]
        if app.state["import_merge"]:  # type: ignore[attr-defined]
            lines = merge_duplicate_lines(lines)
        manual = [ln for ln in inv.lines if ln.origin == "manual"]
        cur_client: dict[str, str] = app.state["client"]  # type: ignore[attr-defined]
        inv.lines[:] = apply_client_vat(
            lines + manual + client_extra_lines(cur_client), cur_client
        )
        app.state["lines_dirty"] = False  # type: ignore[attr-defined]

    def _source_ctx() -> dict[str, object]:
        """Context for the Harvest source bar (status, roster, sync range).

        ``synced`` is true once an import exists; the roster carries each
        person's hours plus a bar-fill percentage relative to the busiest
        person, for the "Who to include" list.
        """
        raw: list[InvoiceLine] = app.state["import_raw"]  # type: ignore[attr-defined]
        selected: set[str] = app.state["selected_people"]  # type: ignore[attr-defined]
        you = str(issuer.get("harvest_user") or "").strip()
        hours: dict[str, float] = {}
        for ln in raw:
            if ln.user:
                hours[ln.user] = hours.get(ln.user, 0.0) + ln.quantity
        ordered = sorted(hours.items())
        peak = max(hours.values(), default=0.0)
        roster = [
            {
                "name": name,
                "hours": h,
                "is_you": name == you,
                "selected": name in selected,
                "bar_pct": round(100 * h / peak) if peak else 0,
            }
            for name, h in ordered
        ]
        synced = bool(raw)
        lfr = app.state["last_fetch_range"]  # type: ignore[attr-defined]
        total = round(sum(hours.values()), 2)
        sel_hours = round(sum(h for n, h in ordered if n in selected), 2)
        if synced:
            period = f"{lfr[0]:%b %Y}" if lfr else ""
            parts = [f"{total:g}h"]
            if period:
                parts.append(period)
            parts.append(f"{len(selected)} of {len(roster)} people")
            parts.append("last synced just now")
            summary = " · ".join(parts)
        else:
            summary = "Not connected — no hours imported for this invoice yet"
        return {
            "synced": synced,
            "source_open": app.state["source_open"],  # type: ignore[attr-defined]
            "status_label": "Synced" if synced else "Not synced",
            "sync_summary": summary,
            "sync_btn_label": "Re-sync" if synced else "Sync from Harvest",
            "roster": roster,
            "selected_count": len(selected),
            "roster_count": len(roster),
            "total_hours": total,
            "selected_hours": sel_hours,
            "lines_dirty": app.state["lines_dirty"],  # type: ignore[attr-defined]
            "fetch_start": lfr[0].isoformat()
            if lfr
            else (period_start.isoformat() if period_start else ""),
            "fetch_end": lfr[1].isoformat()
            if lfr
            else (period_end.isoformat() if period_end else ""),
            "import_merge": app.state["import_merge"],  # type: ignore[attr-defined]
        }

    def _source_bar_oob() -> str:
        return render_template("partials/source_bar.html", oob=True, **_source_ctx())

    def _lines_response(inv: Invoice, status_html: str = "") -> Response:
        """Standard response for line mutations: rows + totals + OOB extras."""
        return Response(
            _render_rows(inv) + _render_totals(inv) + _oob_extras(inv) + status_html,
            content_type="text/html",
        )

    # ------------------------------------------------------------------
    # Draft autosave: every edit persists the editing state to the state
    # database, so a crashed or closed session resumes where it left off.
    # ------------------------------------------------------------------

    def _draft_dump() -> dict[str, Any]:
        """Serialize the editing state to a JSON-safe draft record.

        ``key`` is the invoice number the session started with — a later
        session only resumes the draft when it computes the same number,
        so a new month never inherits the previous month's edits.
        """
        inv: Invoice = app.state["invoice"]  # type: ignore[attr-defined]
        lfr = app.state["last_fetch_range"]  # type: ignore[attr-defined]
        return {
            "key": invoice_number,
            "invoice": {
                "number": inv.number,
                "issue_date": inv.issue_date.isoformat(),
                "due_date": inv.due_date.isoformat(),
                "legal_note": inv.legal_note,
                "currency": inv.currency,
                "period_start": inv.period_start.isoformat()
                if inv.period_start
                else None,
                "period_end": inv.period_end.isoformat() if inv.period_end else None,
                "lines": [asdict(ln) for ln in inv.lines],
            },
            "client_key": app.state["current_client_key"],  # type: ignore[attr-defined]
            "selected_people": sorted(app.state["selected_people"]),  # type: ignore[attr-defined]
            "import_raw": [
                asdict(ln)
                for ln in app.state["import_raw"]  # type: ignore[attr-defined]
            ],
            "import_merge": app.state["import_merge"],  # type: ignore[attr-defined]
            "last_fetch_range": [lfr[0].isoformat(), lfr[1].isoformat()]
            if lfr
            else None,
            "lines_dirty": app.state["lines_dirty"],  # type: ignore[attr-defined]
        }

    def _apply_draft(data: dict[str, Any]) -> None:
        """Restore the editing state from a draft record (inverse of dump)."""
        inv: Invoice = app.state["invoice"]  # type: ignore[attr-defined]
        d: dict[str, Any] = data.get("invoice") or {}
        if d.get("number"):
            inv.number = str(d["number"])
        for attr in ("issue_date", "due_date"):
            if d.get(attr):
                with contextlib.suppress(ValueError):
                    setattr(inv, attr, date.fromisoformat(str(d[attr])))
        for attr in ("period_start", "period_end"):
            value = d.get(attr)
            with contextlib.suppress(ValueError):
                setattr(inv, attr, date.fromisoformat(str(value)) if value else None)
        inv.legal_note = str(d["legal_note"]) if d.get("legal_note") else None
        inv.lines[:] = [_line_from_dict(x) for x in d.get("lines") or []]
        clients_map: dict[str, dict[str, str]] = app.state["clients"]  # type: ignore[attr-defined]
        client_key = data.get("client_key")
        if client_key and client_key in clients_map:
            app.state["client"] = clients_map[client_key]  # type: ignore[attr-defined]
            app.state["current_client_key"] = client_key  # type: ignore[attr-defined]
        app.state["selected_people"] = set(  # type: ignore[attr-defined]
            data.get("selected_people") or []
        )
        app.state["import_raw"] = [  # type: ignore[attr-defined]
            _line_from_dict(x) for x in data.get("import_raw") or []
        ]
        app.state["import_merge"] = bool(data.get("import_merge", True))  # type: ignore[attr-defined]
        lfr = data.get("last_fetch_range")
        with contextlib.suppress(ValueError, IndexError, TypeError):
            app.state["last_fetch_range"] = (  # type: ignore[attr-defined]
                (date.fromisoformat(lfr[0]), date.fromisoformat(lfr[1]))
                if lfr
                else None
            )
        app.state["lines_dirty"] = bool(data.get("lines_dirty", False))  # type: ignore[attr-defined]

    # The just-seeded state, kept so a corrupt/degenerate draft can roll
    # back to it.  Must be captured before the draft applies.
    fresh_state = _draft_dump()
    if db_path is not None:
        stored_draft = get_draft(db_path)
        # Only resume a draft with actual line items: a draft that recorded
        # an import but has zero rows is not meaningful work to restore, and
        # (restored silently) would strand the editor in a confusing
        # "synced but empty" state.  Drop it and start fresh instead.
        invoice_data = stored_draft.get("invoice") if stored_draft else None
        has_lines = (
            bool(invoice_data.get("lines")) if isinstance(invoice_data, dict) else False
        )
        if stored_draft and stored_draft.get("key") == invoice_number and has_lines:
            try:
                _apply_draft(stored_draft)
                app.state["draft_restored"] = True  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001 — a corrupt draft must never
                # prevent the editor from starting.  Roll back whatever was
                # partially applied and drop the bad record.
                app.logger.warning("Ignoring corrupt draft", exc_info=True)
                _apply_draft(fresh_state)
                clear_draft(db_path)
        elif stored_draft and not has_lines:
            clear_draft(db_path)

    # Endpoints that never change the invoice's editing state; everything
    # else autosaves the draft after a successful POST.
    # (settings_clients_save is NOT skipped: renaming the current client
    # changes the draft's client_key.)
    draft_skip_endpoints = {
        "settings_issuer_save",
        "settings_email_save",
        "settings_clients_delete",
        "render_pdf_route",
        "send_invoice",
        "send_test",
        "discard_draft",
        "quit_server",
    }

    @app.after_request
    def _autosave_draft(resp: Response) -> Response:
        if (
            db_path is not None
            and request.method == "POST"
            and resp.status_code < 400
            and request.endpoint not in draft_skip_endpoints
        ):
            data = _draft_dump()
            if data == fresh_state:
                # Nothing worth resuming (e.g. a settings-only session, or
                # a no-op edit): don't create a junk draft, and don't let
                # an older draft shadow a state that is back to fresh.
                clear_draft(db_path)
            else:
                save_draft(db_path, data)
        return resp

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
            output_path=str(output_path),
            has_undo=bool(app.state["undo_stack"]),  # type: ignore[attr-defined]
            has_redo=bool(app.state["redo_stack"]),  # type: ignore[attr-defined]
            send_available=_smtp_enabled(),
            default_action=_default_action(),
            **_source_ctx(),
        )

    @app.get("/static/htmx.min.js")
    def htmx_js() -> Response:
        return app.send_static_file("htmx.min.js")

    @app.get("/preview")
    def preview() -> Response:
        inv: Invoice = app.state["invoice"]  # type: ignore[attr-defined]
        utd: Path | None = app.state["user_templates_dir"]  # type: ignore[attr-defined]
        cur_client: dict[str, str] = app.state["client"]  # type: ignore[attr-defined]
        try:
            return Response(render_html(inv, issuer, cur_client, utd))
        except Exception as exc:  # noqa: BLE001 — a broken custom template
            # must degrade to a readable message in the preview pane, not a
            # crash (essential once templates become editable from the UI).
            return Response(
                f"<pre>Template error: {escape(str(exc))}</pre>",
                status=500,
                mimetype="text/html",
            )

    def _style_fingerprint(utd: Path | None) -> str:
        """Identity of the effective style.css (path + mtime + size).

        The stylesheet is resolved by WeasyPrint at conversion time, so it
        must be part of the PDF cache key — editing a custom style.css has
        to invalidate a cache keyed only on the rendered HTML.
        """
        css = Path(_effective_base_url(utd)) / "style.css"
        try:
            st = css.stat()
        except OSError:
            return str(css)
        return f"{css}:{st.st_mtime_ns}:{st.st_size}"

    def _invoice_pdf_bytes() -> bytes:
        """The current invoice as PDF, cached on its rendered content.

        Renders the HTML under the state lock (fast), then runs the slow
        WeasyPrint conversion outside it so edits stay responsive.  When
        neither the HTML nor the stylesheet changed since the last render
        the cached bytes are returned immediately.
        """
        utd: Path | None = app.state["user_templates_dir"]  # type: ignore[attr-defined]
        with state_lock:
            html = render_html(
                app.state["invoice"],  # type: ignore[attr-defined]
                issuer,
                app.state["client"],  # type: ignore[attr-defined]
                utd,
            )
            key = hashlib.sha256(
                (html + "\x00" + _style_fingerprint(utd)).encode()
            ).hexdigest()
            cached = app.state["pdf_cache"]  # type: ignore[attr-defined]
            if cached and cached[0] == key:
                return bytes(cached[1])
        pdf = pdf_from_html(html, utd)
        with state_lock:
            app.state["pdf_cache"] = (key, pdf)  # type: ignore[attr-defined]
        return pdf

    @app.get("/preview.pdf")
    def preview_pdf() -> Response:
        """True-to-output preview: the exact WeasyPrint render, in memory.

        Byte-identical to what the Generate PDF button writes, so the PDF
        preview shows real pagination, fonts, and page footers.
        """
        try:
            pdf = _invoice_pdf_bytes()
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
            if line.origin == "harvest":
                # Hand edit to an imported line: roster re-derives would
                # discard it, so they must confirm from now on.
                app.state["lines_dirty"] = True  # type: ignore[attr-defined]
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
            if inv.lines[idx].origin == "harvest":
                app.state["lines_dirty"] = True  # type: ignore[attr-defined]
            inv.lines.pop(idx)
        return _lines_response(inv)

    @app.post("/lines/add")
    def add_line() -> Response:
        inv: Invoice = app.state["invoice"]  # type: ignore[attr-defined]
        _snapshot_lines(inv)
        inv.lines.append(
            InvoiceLine(concept="", unit_price=0.0, quantity=0.0, origin="manual")
        )
        return _lines_response(inv)

    @app.post("/lines/delete-selected")
    def delete_selected_lines() -> Response:
        """Remove all checked rows (the selection bar's Delete action)."""
        inv: Invoice = app.state["invoice"]  # type: ignore[attr-defined]
        selected = {int(s) for s in request.form.getlist("selected") if s.isdigit()}
        valid = sorted((i for i in selected if i < len(inv.lines)), reverse=True)
        if valid:
            _snapshot_lines(inv)
            if any(inv.lines[i].origin == "harvest" for i in valid):
                app.state["lines_dirty"] = True  # type: ignore[attr-defined]
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
        app.state["lines_dirty"] = True  # type: ignore[attr-defined]
        # Remove selected (highest index first to preserve positions)
        for i in sorted(selected_idx, reverse=True):
            if i < len(inv.lines):
                inv.lines.pop(i)
        inv.lines.insert(first_idx, merged)
        return _lines_response(inv)

    @app.post("/source/toggle")
    def toggle_source() -> Response:
        """Expand/collapse the source bar's Manage panel (server-tracked)."""
        app.state["source_open"] = not app.state["source_open"]  # type: ignore[attr-defined]
        return Response(_source_bar_oob(), content_type="text/html")

    @app.post("/lines/fetch")
    def fetch_lines_route() -> Response:
        """Sync line items from Harvest for the import range (the source bar).

        First sync seeds the line items.  A re-sync is edit-safe: it
        refreshes the roster/import generation but preserves the current
        (possibly hand-edited) line items, reporting only what changed.
        The invoice's service period is independent and never touched here.
        Feedback rides a toast; errors keep the current lines intact.
        """
        inv: Invoice = app.state["invoice"]  # type: ignore[attr-defined]

        def _toast_response(kind: str, title: str, body: str = "") -> Response:
            resp = _lines_response(inv)
            resp.headers.update(_toast_header(kind, title, body))
            return resp

        try:
            ps = date.fromisoformat(request.form.get("fetch_start", "").strip())
            pe = date.fromisoformat(request.form.get("fetch_end", "").strip())
        except ValueError:
            return _toast_response("err", "Select a valid import range first.")
        if pe < ps:
            return _toast_response("err", "Import end must not be before import start.")
        if fetch_callback is None:
            return _toast_response("err", "Syncing is not available in this session.")

        try:
            raw_lines = fetch_callback(ps, pe)
        except Exception as exc:  # noqa: BLE001 — surface sync errors as a toast
            return _toast_response("err", "Sync failed", str(exc))

        merge = request.form.get("merge_duplicates") == "on"
        # Seed (rebuild) the lines on a first sync, and also whenever there
        # are no line items to preserve — a stale/empty state (e.g. a
        # restored draft that recorded an import but no rows) must still
        # import, not fall through to the no-op re-sync path.
        first_sync = not app.state["import_raw"] or not inv.lines  # type: ignore[attr-defined]
        # Snapshot before mutating: undo restores the previous import
        # generation together with the previous lines.
        _snapshot_lines(inv)
        # Collapse the Manage panel once a sync completes (matches v2).
        app.state["source_open"] = False  # type: ignore[attr-defined]

        if first_sync:
            _store_import(raw_lines, merge)
            _derive_from_import(inv)
            app.state["last_fetch_range"] = (ps, pe)  # type: ignore[attr-defined]
            sc = _source_ctx()
            return _toast_response(
                "ok",
                "Synced from Harvest",
                f"{sc['selected_hours']:g}h · {sc['selected_count']} people · "
                f"{len(inv.lines)} line items added",
            )

        # Edit-safe re-sync: refresh the roster/import generation and range
        # but keep the current line items (never clobber edited rows).
        prev_names = {
            ln.user
            for ln in app.state["import_raw"]  # type: ignore[attr-defined]
            if ln.user
        }
        new_names = {ln.user for ln in raw_lines if ln.user}
        app.state["import_raw"] = copy.deepcopy(raw_lines)  # type: ignore[attr-defined]
        app.state["import_merge"] = merge  # type: ignore[attr-defined]
        app.state["selected_people"] = {  # type: ignore[attr-defined]
            n
            for n in app.state["selected_people"]  # type: ignore[attr-defined]
            if n in new_names
        }
        app.state["last_fetch_range"] = (ps, pe)  # type: ignore[attr-defined]
        added = new_names - prev_names
        if added:
            noun = "member" if len(added) == 1 else "members"
            title = "Re-synced"
            body = f"{len(added)} new team {noun} available · existing line items kept"
        else:
            title = "Already up to date"
            body = "No new entries since last sync"
        return _toast_response("ok", title, body)

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
        _snapshot_lines(inv)
        app.state["selected_people"] = selected  # type: ignore[attr-defined]
        _derive_from_import(inv)
        return _lines_response(inv)

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
        if len(merge_duplicate_lines(inv.lines)) != len(inv.lines):
            app.state["lines_dirty"] = True  # type: ignore[attr-defined]
        inv.lines[:] = merge_duplicate_lines(inv.lines)
        return _lines_response(inv)

    @app.post("/lines/undo")
    def undo_lines() -> Response:
        """Step back one edit, pushing the current state onto the redo stack.

        Restores the lines together with the bill-to client and roster
        selection they were derived from.  No-op without history.
        """
        inv: Invoice = app.state["invoice"]  # type: ignore[attr-defined]
        undo_stack = app.state["undo_stack"]  # type: ignore[attr-defined]
        if not undo_stack:
            return _lines_response(inv)
        app.state["redo_stack"].append(_capture_state(inv))  # type: ignore[attr-defined]
        _restore_state(inv, undo_stack.pop())
        return _lines_response(inv, _client_inset_oob())

    @app.post("/lines/redo")
    def redo_lines() -> Response:
        """Re-apply an undone edit, pushing the current state back onto undo."""
        inv: Invoice = app.state["invoice"]  # type: ignore[attr-defined]
        redo_stack = app.state["redo_stack"]  # type: ignore[attr-defined]
        if not redo_stack:
            return _lines_response(inv)
        app.state["undo_stack"].append(_capture_state(inv))  # type: ignore[attr-defined]
        _restore_state(inv, redo_stack.pop())
        return _lines_response(inv, _client_inset_oob())

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
            if order != list(range(len(inv.lines))):
                app.state["lines_dirty"] = True  # type: ignore[attr-defined]
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
        # Keep the header crumb (the only other place the number shows)
        # in sync with the Number field.
        crumb_oob = (
            f'<span id="inv-no-crumb" hx-swap-oob="outerHTML" class="crumb">'
            f"/ Invoice {escape(inv.number)}</span>"
        )
        return (
            render_template("partials/meta.html", invoice=inv)
            + render_template("partials/period.html", invoice=inv)
            + crumb_oob
        )

    # --- Settings ---

    def _persist_issuer() -> str:
        """Persist the issuer record; note when running session-only."""
        if db_path is None:
            return " (this session only)"
        save_issuer(db_path, issuer)
        return ""

    def _persist_clients() -> str:
        """Persist the full client mapping in one transaction."""
        if db_path is None:
            return " (this session only)"
        save_clients(db_path, app.state["clients"])  # type: ignore[attr-defined]
        return ""

    def _render_clients_block(
        status: str | None = None,
        *,
        error: bool = False,
        open_key: str | None = None,
    ) -> Response:
        html = render_template(
            "partials/settings_clients.html",
            clients=app.state["clients"],  # type: ignore[attr-defined]
            current_client_key=app.state["current_client_key"],  # type: ignore[attr-defined]
            status=status,
            status_error=error,
            open_key=open_key,
        )
        headers = _toast_header("err" if error else "ok", status) if status else {}
        return Response(html, content_type="text/html", headers=headers)

    email_fields = (
        "from_name",
        "from_address",
        "reply_to",
        "host",
        "port",
        "encryption",
        "username",
        "subject_template",
        "message_template",
        "default_action",
    )

    def _smtp_enabled() -> bool:
        """Whether sending is configured (host set in the DB or the env)."""
        cfg: dict[str, object] = app.state["email"]  # type: ignore[attr-defined]
        return bool(str(cfg.get("host") or "").strip()) or bool(
            os.environ.get("HARVEST_INVOICER_SMTP_HOST", "").strip()
        )

    def _default_action() -> str:
        """Which action the split-button's primary runs: 'generate' or 'send'.

        Only 'send' when sending is actually enabled.
        """
        cfg: dict[str, object] = app.state["email"]  # type: ignore[attr-defined]
        action = str(cfg.get("default_action") or "generate")
        return "send" if action == "send" and _smtp_enabled() else "generate"

    @app.get("/settings")
    def settings_page() -> str:
        from harvest_invoicer.mail import (  # noqa: PLC0415
            DEFAULT_MESSAGE_TEMPLATE,
            DEFAULT_SUBJECT_TEMPLATE,
        )

        cfg: dict[str, object] = app.state["email"]  # type: ignore[attr-defined]
        email: dict[str, object] = {f: str(cfg.get(f) or "") for f in email_fields}
        email["encryption"] = email["encryption"] or "starttls"
        email["subject_template"] = (
            email["subject_template"] or DEFAULT_SUBJECT_TEMPLATE
        )
        email["message_template"] = (
            email["message_template"] or DEFAULT_MESSAGE_TEMPLATE
        )
        email["default_action"] = email["default_action"] or "generate"
        # Whether a password is available from the environment (never shown).
        email["password_set"] = bool(
            os.environ.get("HARVEST_INVOICER_SMTP_PASSWORD", "").strip()
        )
        email["smtp_enabled"] = _smtp_enabled()
        return render_template(
            "settings.html",
            issuer=issuer,
            clients=app.state["clients"],  # type: ignore[attr-defined]
            current_client_key=app.state["current_client_key"],  # type: ignore[attr-defined]
            email=email,
            status=None,
            status_error=False,
        )

    @app.post("/settings/email")
    def settings_email_save() -> Response:
        """Persist the non-secret email/SMTP config (password stays in env)."""
        values = {f: request.form.get(f, "").strip() for f in email_fields}
        if values["encryption"] not in ("starttls", "ssl", "none"):
            values["encryption"] = "starttls"

        def _status(msg: str, *, error: bool = False) -> Response:
            css = "status-err" if error else "status-ok"
            return Response(
                f'<span id="email-status" class="{css}">{escape(msg)}</span>',
                content_type="text/html",
                headers=_toast_header("err" if error else "ok", msg),
            )

        if values["port"]:
            try:
                int(values["port"])
            except ValueError:
                return _status("Port must be a number (e.g. 587).", error=True)
        if values["from_address"] and "@" not in values["from_address"]:
            return _status("From address must be a valid email.", error=True)

        cfg: dict[str, object] = app.state["email"]  # type: ignore[attr-defined]
        cfg.clear()
        cfg.update({k: v for k, v in values.items() if v})
        if db_path is not None:
            save_email(db_path, cfg)
        return _status("Settings saved")

    @app.post("/send/test")
    def send_test() -> Response:
        """Verify the SMTP connection without sending an invoice."""
        from harvest_invoicer.mail import MailConfigError, verify_smtp  # noqa: PLC0415

        # Save the current form first so the test uses unsaved edits.
        values = {f: request.form.get(f, "").strip() for f in email_fields}
        try:
            host = verify_smtp(values)
        except MailConfigError as exc:
            return Response(status=204, headers=_toast_header("err", str(exc)))
        except OSError as exc:
            return Response(
                status=204,
                headers=_toast_header("err", "Connection failed", str(exc)),
            )
        return Response(
            status=204,
            headers=_toast_header("ok", "Connection verified", f"Reached {host}"),
        )

    @app.post("/settings/issuer")
    def settings_issuer_save() -> Response:
        """Validate and save the issuer config (file + running session)."""

        def _status(msg: str, *, error: bool = False) -> Response:
            css = "status-err" if error else "status-ok"
            return Response(
                f'<span id="issuer-status" class="{css}">{escape(msg)}</span>',
                content_type="text/html",
                headers=_toast_header("err" if error else "ok", msg),
            )

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
            "language",
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
        if values["language"] and values["language"] not in SUPPORTED_LANGUAGES:
            return _status(
                f"Unsupported language '{values['language']}'. "
                f"Supported: {', '.join(SUPPORTED_LANGUAGES)}.",
                error=True,
            )
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

        suffix = _persist_issuer()
        return _status("Settings saved" + suffix)

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
    def settings_clients_save() -> Response:
        """Add or update a clients.json entry (file + running session)."""
        clients_map: dict[str, dict[str, object]] = app.state["clients"]  # type: ignore[attr-defined]
        original = request.form.get("original_key", "").strip()
        new_key = request.form.get("key", "").strip()
        key_error: str | None = None
        if not new_key:
            key_error = "Harvest client name (key) is required."
        elif original and new_key != original and new_key in clients_map:
            key_error = (
                f"A client named '{new_key}' already exists — renaming "
                f"'{original}' to it would overwrite that entry."
            )
        if key_error:
            return _render_clients_block(key_error, error=True)

        fields = (
            "name",
            "address_line1",
            "address_line2",
            "country",
            "tax_id",
            "tax_id_label",
            "email",
            "language",
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
        field_error: str | None = None
        if values["email"] and "@" not in values["email"]:
            field_error = "Email must be a valid address (missing '@')."
        elif values["language"] and values["language"] not in SUPPORTED_LANGUAGES:
            field_error = (
                f"Unsupported language '{values['language']}'. "
                f"Supported: {', '.join(SUPPORTED_LANGUAGES)}."
            )
        elif vat_raw:
            try:
                vat_val = float(vat_raw)
            except ValueError:
                vat_val = -1.0
            if not 0.0 <= vat_val <= 1.0:
                field_error = "VAT rate must be a number between 0 and 1 (e.g. 0.21)."
        if field_error:
            return _render_clients_block(field_error, error=True)

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

        suffix = _persist_clients()
        return _render_clients_block(
            f"Client '{new_key}' saved{suffix}", open_key=new_key
        )

    @app.post("/settings/clients/delete")
    def settings_clients_delete() -> Response:
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
        suffix = _persist_clients()
        return _render_clients_block(f"Client '{original}' deleted{suffix}")

    # --- PDF render ---

    @app.post("/render")
    def render_pdf_route() -> Response:
        out: Path = app.state["output_path"]  # type: ignore[attr-defined]
        out.write_bytes(_invoice_pdf_bytes())
        html = render_template("partials/render_done.html", output_path=str(out))
        return Response(
            html,
            content_type="text/html",
            headers=_toast_header("ok", f"Invoice PDF saved to {out.name}."),
        )

    # --- Send by email ---

    def _email_ctx() -> dict[str, object]:
        """Seed values for the send modal, resolved against the live invoice."""
        from harvest_invoicer.mail import (  # noqa: PLC0415
            DEFAULT_MESSAGE_TEMPLATE,
            DEFAULT_SUBJECT_TEMPLATE,
            resolve_tokens,
        )

        cfg: dict[str, object] = app.state["email"]  # type: ignore[attr-defined]
        inv: Invoice = app.state["invoice"]  # type: ignore[attr-defined]
        cur_client: dict[str, str] = app.state["client"]  # type: ignore[attr-defined]
        subject_tpl = str(cfg.get("subject_template") or DEFAULT_SUBJECT_TEMPLATE)
        message_tpl = str(cfg.get("message_template") or DEFAULT_MESSAGE_TEMPLATE)
        from_address = str(cfg.get("from_address") or issuer.get("email") or "").strip()
        return {
            "email_to": str(cur_client.get("email") or ""),
            "email_subject": resolve_tokens(subject_tpl, inv, cur_client, issuer),
            "email_message": resolve_tokens(message_tpl, inv, cur_client, issuer),
            "email_from": from_address,
            "invoice": inv,
            "fmt_money": fmt_money,
        }

    @app.get("/send/modal")
    def send_modal() -> str:
        """Render the send-invoice modal, prefilled from templates + client."""
        return render_template("partials/send_modal.html", **_email_ctx())

    @app.post("/send")
    def send_invoice() -> Response:
        """Email the invoice PDF using the modal's fields + stored SMTP config.

        The SMTP password is read from the environment only; every other
        setting comes from Settings > Email.  Feedback rides a toast.
        """
        from harvest_invoicer.mail import (  # noqa: PLC0415
            MailConfigError,
            send_invoice_email,
        )

        def _toast(kind: str, title: str, body: str = "") -> Response:
            headers = _toast_header(kind, title, body)
            if kind == "err":
                # Keep the modal open (don't swap) so edits survive a retry.
                headers["HX-Reswap"] = "none"
                return Response("", content_type="text/html", headers=headers)
            # Success: empty body clears #modal-root (closes the modal).
            return Response("", content_type="text/html", headers=headers)

        to = request.form.get("to", "")
        subject = request.form.get("subject", "")
        message = request.form.get("message", "")
        copy_self = request.form.get("copy_self") == "on"
        # Snapshot under the lock so the email metadata matches the PDF
        # even if another tab edits concurrently.
        with state_lock:
            inv_copy: Invoice = copy.deepcopy(app.state["invoice"])  # type: ignore[attr-defined]
            cur_client = dict(app.state["client"])  # type: ignore[attr-defined]
            cfg = dict(app.state["email"])  # type: ignore[attr-defined]
        try:
            pdf = _invoice_pdf_bytes()
            recipient = send_invoice_email(
                pdf,
                inv_copy,
                issuer,
                cur_client,
                cfg,
                to=to,
                subject=subject,
                message=message,
                copy_self=copy_self,
            )
        except MailConfigError as exc:
            return _toast("err", "Can't send invoice", str(exc))
        except OSError as exc:  # SMTPException subclasses OSError
            return _toast("err", "Send failed", str(exc))
        return _toast("ok", "Invoice sent", f"Sent to {recipient}")

    # --- Draft ---

    @app.post("/draft/discard")
    def discard_draft() -> Response:
        """Drop the restored draft and return to the freshly seeded state."""
        if db_path is not None:
            clear_draft(db_path)
        _apply_draft(fresh_state)
        app.state["undo_stack"].clear()  # type: ignore[attr-defined]
        app.state["redo_stack"].clear()  # type: ignore[attr-defined]
        app.state["draft_restored"] = False  # type: ignore[attr-defined]
        inv: Invoice = app.state["invoice"]  # type: ignore[attr-defined]
        resp = _lines_response(inv, _client_inset_oob())
        resp.headers.update(
            _toast_header("ok", "Draft discarded — back to the fresh session state.")
        )
        return resp

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
