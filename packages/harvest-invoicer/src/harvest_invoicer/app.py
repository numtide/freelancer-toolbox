"""Flask editor application for interactive invoice editing."""

from __future__ import annotations

import contextlib
import copy
import hashlib
import io
import json
import os
import sqlite3
import threading
from collections import deque
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from flask import Flask, Response, g, render_template, request, send_file
from markupsafe import escape
from pydantic import ValidationError
from werkzeug.middleware.proxy_fix import ProxyFix

from harvest_invoicer.archive import (
    archive_pdf,
    default_invoices_dir,
    invoice_file,
    lookup,
    now_iso,
    read_invoice,
    remove,
)
from harvest_invoicer.config import SmtpSettings
from harvest_invoicer.db import (
    clear_draft,
    get_draft,
    invoice_sends,
    latest_invoice,
    list_invoices,
    mark_invoice_sent,
    save_clients,
    save_draft,
    save_email,
    save_issuer,
    send_counts,
)
from harvest_invoicer.fetch import apply_client_vat, client_extra_lines
from harvest_invoicer.i18n import (
    SUPPORTED_LANGUAGES,
    UI_TRANSLATIONS,
    resolve_language,
    translator,
    ui_language,
)
from harvest_invoicer.model import (
    DEFAULT_PAYMENT_TERM_DAYS,
    Invoice,
    InvoiceLine,
    fmt_money,
    fmt_rate_pct,
    merge_duplicate_lines,
)
from harvest_invoicer.render import _effective_base_url, pdf_from_html, render_html

if TYPE_CHECKING:
    from collections.abc import Callable

    from harvest_invoicer.config import OidcSettings
    from harvest_invoicer.mail import SendResult

_LOCAL_HOSTNAMES = ("127.0.0.1", "localhost", "::1")

# Depth of the undo/redo history stacks.
_UNDO_LIMIT = 20

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_STATIC_DIR = Path(__file__).parent / "static"


def host_key(authority: str) -> str:
    """Normalize a host (``Host`` header, ``--allowed-host``, URL authority).

    Lowercase, without port, IPv6 brackets or a trailing dot, so that
    ``Box.LAN``, ``box.lan:8321`` and ``box.lan.`` compare equal and
    ``[fe80::1]:8321`` matches ``[fe80::1]`` (or a bare ``fe80::1``).  A
    malformed value gives ``""``, which matches nothing; ``"*"`` stays.
    """
    value = authority.strip().lower()
    if value == "*":
        return value
    if value.count(":") > 1 and not value.startswith("["):
        return value  # a bare IPv6 address, no port possible
    try:
        parts = urlsplit("//" + value)
        _ = parts.port  # validates it: "box.lan:x" is malformed
        host = parts.hostname or ""
    except ValueError:  # e.g. an unclosed "[::1" or a bad port
        return ""
    return host.rstrip(".")


def _origin_host(origin: str) -> str:
    """The normalized host of an Origin/Referer URL (``""`` if malformed)."""
    try:
        return host_key(urlsplit(origin).netloc)
    except ValueError:
        return ""


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
    output_path: Path | None,
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
    oidc: OidcSettings | None = None,
    trusted_proxies: int = 0,
    invoices_dir: Path | None = None,
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

    ``oidc`` turns the editor into a server app: every request needs an
    allow-listed OpenID Connect login (see auth.py).  ``None`` keeps the
    local, unauthenticated editor.  ``trusted_proxies`` is how many reverse
    proxies' X-Forwarded-* headers to honor (0: none).

    With a ``db_path`` every generated PDF is archived (archive.py) under
    ``invoices_dir`` (default: ``invoices/`` beside the database), each
    with its own link; ``output_path``, when set, also receives a copy.
    Without a database (demo mode, tests) Generate writes ``output_path``
    only (default ``invoice-<number>.pdf``), as before the archive.
    """
    app = Flask(
        __name__,
        template_folder=str(_TEMPLATES_DIR),
        static_folder=str(_STATIC_DIR),
        static_url_path="/static",
    )
    # Same VAT-rate formatting the invoice PDF uses, so the editor's rate
    # badge never disagrees with the rendered document (e.g. 7.5% vs "8%").
    app.jinja_env.filters["rate_pct"] = fmt_rate_pct
    # Render a stored tax_id_label (plain string or per-language map) back
    # into its settings text field without flattening a map to its repr.
    from harvest_invoicer.config import tax_id_label_field  # noqa: PLC0415

    app.jinja_env.filters["tax_id_label_field"] = tax_id_label_field

    invoice = _make_invoice(
        lines,
        invoice_number,
        issuer,
        currency,
        period_start=period_start,
        period_end=period_end,
    )

    # The invoice archive needs the state database for its metadata.
    archive_dir: Path | None = None
    if db_path is not None:
        archive_dir = invoices_dir or default_invoices_dir(db_path)
    elif output_path is None:
        output_path = Path(f"invoice-{invoice_number}.pdf")
    # Serializes archive writes: the dedupe check-then-insert, deletes and
    # sent marks (the archive is independent of the editing state lock).
    archive_lock = threading.Lock()

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
        # Archive id of the PDF this editor session generated last (/pdf).
        "last_archived_id": None,
    }

    # Hosts the Host guard (reads and writes) accepts beyond loopback, as
    # host_key()s.  A literal "*" (a wildcard bind without --allowed-host
    # or OIDC) accepts any Host and falls back to a same-origin check for
    # Origin/Referer.
    allowed = frozenset(host_key(h) for h in (*_LOCAL_HOSTNAMES, *allowed_hosts))
    if oidc is not None and oidc.public_url:
        allowed |= {host_key(urlsplit(oidc.public_url).netloc)}
    allowed -= {""}  # a malformed --allowed-host matches nothing
    allow_any_host = "*" in allowed

    if trusted_proxies:
        # Behind a reverse proxy (e.g. Traefik terminating TLS): take the
        # client's scheme/host from X-Forwarded-*, so redirect URIs, the
        # Secure cookie flag and the CSRF guard see the public origin.
        app.wsgi_app = ProxyFix(  # type: ignore[method-assign]
            app.wsgi_app,
            x_for=trusted_proxies,
            x_proto=trusted_proxies,
            x_host=trusted_proxies,
            x_port=trusted_proxies,
        )

    def _request_host() -> str:
        return host_key(request.host)

    @app.get("/healthz")
    def healthz() -> Response:
        """Liveness/readiness probe: a constant 200, nothing else.

        Exempt from the Host check and the login guard (by endpoint name),
        so it reveals nothing — no version, no config — and touches no
        lock, database or file.
        """
        return Response(
            "ok", mimetype="text/plain", headers={"Cache-Control": "no-store"}
        )

    @app.before_request
    def _reject_unknown_host() -> Response | None:
        """DNS-rebinding guard: every request — reads too — must name a Host
        the server was told to serve (loopback by default, plus any
        configured host).  Otherwise a malicious page could rebind its own
        domain to this server and read the editor (invoices, settings) as
        same-origin.  A wildcard bind ("*") accepts any Host.  Registered
        first, so it runs even before the login guard.  The health probe is
        exempt (by endpoint): kubelet probes send the pod IP as Host.
        """
        if request.endpoint == "healthz":
            return None
        if not allow_any_host and _request_host() not in allowed:
            return Response("Forbidden: unrecognized Host.", status=403)
        return None

    if oidc is not None:
        from harvest_invoicer.auth import init_oidc  # noqa: PLC0415

        # Right after the Host check, so its login guard runs before every
        # other hook.
        init_oidc(app, oidc)

    @app.before_request
    def _reject_cross_origin() -> Response | None:
        """CSRF guard: mutating requests must come from the editor's origin.

        The Host was already checked (:func:`_reject_unknown_host`); a
        present Origin/Referer must also be the same origin, so a malicious
        page cannot fire state-changing (and config-writing) POSTs at the
        server.  When bound to a wildcard address ("*"), any Host is
        accepted but Origin/Referer must still match it.
        """
        if request.method not in ("POST", "PUT", "DELETE", "PATCH"):
            return None
        host = _request_host()
        origin = request.headers.get("Origin") or request.headers.get("Referer")
        if origin:
            origin_host = _origin_host(origin)
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
        "healthz",
        "htmx_js",
        "style_css",
        "favicon",
        "serve_pdf",
        "preview_pdf",
        "render_pdf_route",
        "send_invoice",
        "send_modal",  # renders the PDF (resend check) — locks itself
        "send_test",  # SMTP handshake — must not hold the state lock
        # Archive: file IO and SMTP, guarded by archive_lock instead.
        "invoice_pdf",
        "invoice_send",
        "invoice_delete",
        # Login flow: talks to the OIDC provider, touches no editor state.
        "oidc_login",
        "oidc_callback",
        "oidc_logout",
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

    def _tr() -> Callable[[str], str]:
        """Translator for the archive UI strings, in the issuer's language."""
        return translator(ui_language(issuer), UI_TRANSLATIONS)

    @app.context_processor
    def _ui_context() -> dict[str, object]:
        return {
            "tr": _tr(),
            "ui_lang": ui_language(issuer),
            "archive_enabled": archive_dir is not None,
        }

    def _config_problem() -> str | None:
        """Why the invoice cannot be rendered yet, or ``None``.

        ``"issuer"`` when the issuer has no name, ``"client"`` when no
        bill-to client with a name is selected — a fresh setup then gets a
        pointer to Settings instead of a template error.  Call it under the
        state lock.
        """
        if not str(issuer.get("name") or "").strip():
            return "issuer"
        cur_client: dict[str, str] = app.state["client"]  # type: ignore[attr-defined]
        if not str((cur_client or {}).get("name") or "").strip():
            return "client"
        return None

    def _locked_config_problem() -> str | None:
        with state_lock:
            return _config_problem()

    def _config_problem_page(problem: str) -> Response:
        """The friendly "configure first" page shown in the preview pane."""
        return Response(
            render_template("config_problem.html", problem=problem),
            mimetype="text/html",
        )

    def _config_problem_modal(problem: str) -> Response:
        """The same message as a modal (Generate / Send), plus a toast."""
        tr = _tr()
        return Response(
            render_template("partials/config_problem_modal.html", problem=problem),
            content_type="text/html",
            headers=_toast_header("err", tr("cfg_title"), tr("cfg_" + problem)),
        )

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
        "invoice_send",
        "invoice_delete",
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
            output_label=str(archive_dir or output_path),
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
        problem = _config_problem()
        if problem:
            return _config_problem_page(problem)
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

    def _render_snapshot() -> tuple[bytes, Invoice, dict[str, str], str | None]:
        """The current invoice as PDF, plus the state it was rendered from.

        Renders the HTML under the state lock (fast), then runs the slow
        WeasyPrint conversion outside it so edits stay responsive.  When
        neither the HTML nor the stylesheet changed since the last render
        the cached bytes are returned immediately.  The invoice, client and
        client key returned are copies taken together with the HTML, so
        archive metadata always matches the PDF.
        """
        utd: Path | None = app.state["user_templates_dir"]  # type: ignore[attr-defined]
        with state_lock:
            inv: Invoice = copy.deepcopy(app.state["invoice"])  # type: ignore[attr-defined]
            cur_client: dict[str, str] = dict(app.state["client"])  # type: ignore[attr-defined]
            client_key: str | None = app.state["current_client_key"]  # type: ignore[attr-defined]
            html = render_html(inv, issuer, cur_client, utd)
            key = hashlib.sha256(
                (html + "\x00" + _style_fingerprint(utd)).encode()
            ).hexdigest()
            cached = app.state["pdf_cache"]  # type: ignore[attr-defined]
            if cached and cached[0] == key:
                return bytes(cached[1]), inv, cur_client, client_key
        pdf = pdf_from_html(html, utd)
        with state_lock:
            app.state["pdf_cache"] = (key, pdf)  # type: ignore[attr-defined]
        return pdf, inv, cur_client, client_key

    def _invoice_pdf_bytes() -> bytes:
        """The current invoice as PDF (see :func:`_render_snapshot`)."""
        return _render_snapshot()[0]

    @app.get("/preview.pdf")
    def preview_pdf() -> Response:
        """True-to-output preview: the exact WeasyPrint render, in memory.

        Byte-identical to what the Generate PDF button writes, so the PDF
        preview shows real pagination, fonts, and page footers.
        """
        problem = _locked_config_problem()
        if problem:
            return _config_problem_page(problem)
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

    def _send_pdf(data: bytes, filename: str, *, download: bool) -> Response:
        """A PDF response: inline, or as an attachment named *filename*.

        Flask quotes the name in Content-Disposition (and adds an RFC 5987
        ``filename*`` for non-ASCII names).  Invoices are private: never
        cached by anything but the browser's current view.
        """
        resp = send_file(
            io.BytesIO(data),
            mimetype="application/pdf",
            as_attachment=download,
            download_name=filename,
            conditional=False,
            etag=False,
        )
        resp.headers["Cache-Control"] = "private, no-store"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        return resp

    def _archived(invoice_id: str) -> tuple[dict[str, object] | None, bytes | None]:
        """The archived invoice behind a link id and its PDF (if present).

        Looked up and read under the archive lock, so a concurrent delete
        can't remove the file between the two.
        """
        if db_path is None or archive_dir is None:
            return None, None
        with archive_lock:
            record = lookup(db_path, invoice_id)
            if record is None:
                return None, None
            return record, read_invoice(archive_dir, record)

    @app.get("/pdf")
    def serve_pdf() -> Response:
        """Serve the last generated PDF (legacy link, kept for bookmarks).

        With the archive that is the PDF this editor session generated
        last (not whatever is newest in the shared archive); without it,
        the Generate button's output file.
        """
        download = request.args.get("download") == "1"
        if db_path is not None and archive_dir is not None:
            last_id = app.state["last_archived_id"]  # type: ignore[attr-defined]
            record, data = _archived(last_id) if last_id else (None, None)
            if record is not None and data is not None:
                return _send_pdf(data, str(record["filename"]), download=download)
        else:
            out: Path = app.state["output_path"]  # type: ignore[attr-defined]
            if out.exists():
                return _send_pdf(out.read_bytes(), out.name, download=download)
        return Response(
            "<p>No PDF generated yet. Click Generate PDF first.</p>",
            status=404,
            mimetype="text/html",
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
        # Rebuild the lines from the fetched data unless the user has hand-
        # edited imported rows.  We seed on a first sync, on an empty/stale
        # state (e.g. a restored draft that recorded an import but no rows),
        # and on any re-sync of a *clean* invoice — only genuinely edited
        # lines (``lines_dirty``) are preserved, so a clean re-sync of a new
        # range actually refreshes the numbers instead of silently keeping
        # the old month's.
        first_sync = (
            not app.state["import_raw"]  # type: ignore[attr-defined]
            or not inv.lines
            or not app.state["lines_dirty"]  # type: ignore[attr-defined]
        )
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
        # This path only runs for a hand-edited invoice, so the import
        # generation is refreshed but the edited rows are deliberately kept.
        # Never claim "up to date" — the underlying data may well differ.
        added = new_names - prev_names
        if added:
            noun = "member" if len(added) == 1 else "members"
            body = (
                f"{len(added)} new team {noun} available · "
                "your edited line items were kept"
            )
        else:
            body = (
                "Your edited line items were kept — use the roster to pull in new data"
            )
        return _toast_response("ok", "Re-synced", body)

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
        # The new client's effective VAT applies to Harvest/manual lines (0
        # when unset, replacing any rate inherited from the previous client).
        # Extras are skipped — client_extra_lines already gave them the right
        # rate (their own, or the new client's inherited rate).
        vat = float(str(entry.get("vat_rate") or 0.0))
        for line in inv.lines:
            if line.origin == "extra":
                continue
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

    def _smtp_settings() -> SmtpSettings:
        """The effective SMTP settings (stored + env), tolerant of bad data.

        A malformed stored record or SMTP environment variable (e.g. a bad
        encryption/port) must never crash the pages that render config —
        fall back to safe, env-free defaults (which reads as "not
        configured"; the actual error surfaces on Send / Send test).
        """
        try:
            return SmtpSettings(**app.state["email"])  # type: ignore[attr-defined]
        except ValidationError:
            return SmtpSettings.model_construct()

    def _smtp_enabled() -> bool:
        """Whether sending is configured (host set in the DB or the env)."""
        return bool(_smtp_settings().host)

    def _default_action() -> str:
        """Which action the split-button's primary runs: 'generate' or 'send'.

        Only 'send' when sending is actually enabled.
        """
        settings = _smtp_settings()
        return (
            "send"
            if settings.default_action == "send" and settings.host
            else "generate"
        )

    @app.get("/settings")
    def settings_page() -> str:
        from harvest_invoicer.config import smtp_env_raw  # noqa: PLC0415

        # The effective (env-over-stored) SMTP settings drive the UI: fields
        # the environment controls are shown read-only, and the password is
        # reported as set/unset but never echoed.
        s = _smtp_settings()
        email: dict[str, object] = {
            "from_name": s.from_name,
            "from_address": s.from_address,
            "reply_to": s.reply_to,
            "host": s.host,
            "port": str(s.port) if s.port else "",
            "encryption": s.encryption,
            "username": s.username,
            "subject_template": s.subject_template,
            "message_template": s.message_template,
            "default_action": s.default_action,
        }
        for f in email_fields:
            email[f + "_env"] = bool(smtp_env_raw(f))
        email["password_set"] = bool(s.password.get_secret_value())
        email["smtp_enabled"] = bool(s.host)
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
        from harvest_invoicer.config import (  # noqa: PLC0415
            friendly_error,
            smtp_env_raw,
        )

        cfg: dict[str, object] = app.state["email"]  # type: ignore[attr-defined]
        values = {f: request.form.get(f, "").strip() for f in email_fields}

        def _status(msg: str, *, error: bool = False) -> Response:
            css = "status-err" if error else "status-ok"
            return Response(
                f'<span id="email-status" class="{css}">{escape(msg)}</span>',
                content_type="text/html",
                headers=_toast_header("err" if error else "ok", msg),
            )

        # Validate the submitted values through the model (port, encryption,
        # etc.); env layering does not affect whether the form itself is valid.
        try:
            SmtpSettings.model_validate(values)
        except ValidationError as exc:
            return _status(friendly_error(exc), error=True)
        if values["from_address"] and "@" not in values["from_address"]:
            return _status("From address must be a valid email.", error=True)

        # Persist non-empty, non-env-controlled fields; env-controlled fields
        # are read-only in the UI, so leave their stored value untouched.
        stored = dict(cfg)
        for f in email_fields:
            if smtp_env_raw(f):
                continue
            if values[f]:
                stored[f] = values[f]
            else:
                stored.pop(f, None)
        cfg.clear()
        cfg.update({k: v for k, v in stored.items() if v})
        if db_path is not None:
            save_email(db_path, cfg)
        return _status("Settings saved")

    @app.post("/send/test")
    def send_test() -> Response:
        """Verify the SMTP connection without sending an invoice."""
        from harvest_invoicer.mail import MailConfigError, verify_smtp  # noqa: PLC0415

        # Test against the current (possibly unsaved) form values, without
        # persisting them; env overrides still apply, password comes from env.
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

        from harvest_invoicer.config import (  # noqa: PLC0415
            IssuerConfig,
            friendly_error,
            parse_tax_id_label,
        )

        # tax_id_label may be a plain string or a per-language JSON map.
        label = parse_tax_id_label(request.form.get("tax_id_label", ""))

        # The model is the schema/validation authority (email shape, types).
        try:
            IssuerConfig.model_validate(
                {**values, "tax_id_label": label, "bank": {"iban": iban, "bic": bic}}
            )
        except ValidationError as exc:
            return _status(friendly_error(exc), error=True)

        # Mutate the shared issuer dict in place so the preview updates too.
        for f in text_fields:
            if f == "tax_id_label":
                continue  # handled below (may be a map, not a plain string)
            if values[f]:
                issuer[f] = values[f]
            else:
                issuer.pop(f, None)
        if label:
            issuer["tax_id_label"] = label
        else:
            issuer.pop("tax_id_label", None)
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
            # Split from the right so a ';' inside the description survives:
            # only the trailing price (and optional quantity) are separated.
            parts = [p.strip() for p in stripped.rsplit(";", 2)]
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
        from harvest_invoicer.config import (  # noqa: PLC0415
            ClientConfig,
            friendly_error,
            parse_tax_id_label,
        )

        values = {f: request.form.get(f, "").strip() for f in fields}
        required = ("name", "address_line1", "address_line2", "country", "tax_id")
        missing = [f for f in required if not values[f]]
        if missing:
            return _render_clients_block(
                "Missing required fields: " + ", ".join(missing), error=True
            )
        if values["language"] and values["language"] not in SUPPORTED_LANGUAGES:
            return _render_clients_block(
                f"Unsupported language '{values['language']}'. "
                f"Supported: {', '.join(SUPPORTED_LANGUAGES)}.",
                error=True,
            )

        extra_items, extra_err = _parse_extra_lines(request.form.get("extra_lines", ""))
        if extra_err:
            return _render_clients_block(extra_err, error=True)

        # Validate the record through the model (email shape, VAT range,
        # extra-line types); a ValidationError yields a readable message.
        try:
            model = ClientConfig.model_validate(
                {
                    **values,
                    "tax_id_label": parse_tax_id_label(
                        request.form.get("tax_id_label", "")
                    ),
                    "vat_rate": request.form.get("vat_rate", "").strip(),
                    "extra_lines": extra_items,
                }
            )
        except ValidationError as exc:
            return _render_clients_block(friendly_error(exc), error=True)

        # Reuse the existing entry object so the current invoice's client
        # (same object) picks up the edits immediately.
        if original and original in clients_map:
            entry = clients_map.pop(original)
        elif new_key in clients_map:
            entry = clients_map.pop(new_key)
        else:
            entry = {}
        entry.clear()
        entry.update(
            {k: v for k, v in model.model_dump().items() if v not in ("", None, [])}
        )
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

    def _archive(
        pdf: bytes, inv: Invoice, cur_client: dict[str, str], client_key: str | None
    ) -> tuple[dict[str, object], bool] | None:
        """Archive a rendered PDF; ``None`` when the archive is off."""
        if db_path is None or archive_dir is None:
            return None
        with archive_lock:
            archived = archive_pdf(
                db_path, archive_dir, pdf, inv, cur_client, client_key, issuer
            )
        app.state["last_archived_id"] = archived[0]["id"]  # type: ignore[attr-defined]
        return archived

    def _sent_entry(pdf: bytes, number: str) -> dict[str, object] | None:
        """The archived entry *pdf* would reuse, if it was already sent.

        That is the newest entry for *number* with the same content (what
        Generate/Send would reuse), when it has been emailed before.
        """
        if db_path is None:
            return None
        digest = hashlib.sha256(pdf).hexdigest()
        with archive_lock:
            newest = latest_invoice(db_path, number)
        if newest is None or newest["sha256"] != digest or not newest["sent_at"]:
            return None
        return newest

    @app.post("/render")
    def render_pdf_route() -> Response:
        """Generate the PDF and show the result panel (into #modal-root).

        With the archive the PDF becomes a new archived invoice — or reuses
        the newest one for the same number when the content is identical —
        and an explicit ``--output`` also receives a copy.  Without it the
        PDF overwrites the single output file, as before the archive.
        """
        tr = _tr()
        problem = _locked_config_problem()
        if problem:
            return _config_problem_modal(problem)
        pdf, inv, cur_client, client_key = _render_snapshot()
        out: Path | None = app.state["output_path"]  # type: ignore[attr-defined]
        if out is not None:
            out.write_bytes(pdf)
        archived = _archive(pdf, inv, cur_client, client_key)
        if archived is not None:
            record, reused = archived
            filename = str(record["filename"])
            url = f"/invoices/{record['id']}.pdf"
            send_url = f"/invoices/{record['id']}/send"
            toast = _toast_header("ok", tr("archived"), filename)
        else:
            reused = False
            filename = out.name if out is not None else ""
            url, send_url = "/pdf", "/send/modal"
            toast = _toast_header("ok", f"Invoice PDF saved to {filename}.")
        html = render_template(
            "partials/render_done.html",
            invoice=inv,
            fmt_money=fmt_money,
            filename=filename,
            open_url=url,
            download_url=url + "?download=1",
            send_url=send_url,
            send_available=_smtp_enabled(),
            reused=reused,
            # Only the name: the server's filesystem layout stays private.
            copy_path=out.name if archived is not None and out is not None else None,
        )
        return Response(html, content_type="text/html", headers=toast)

    # --- Send by email ---

    def _send_response(
        kind: str, title: str, body: str = "", *, status: int = 200, extra: str = ""
    ) -> Response:
        """Feedback for the send modal's form, as a toast.

        An error keeps the modal open (no swap) so edits survive a retry;
        success returns an empty body (plus any OOB fragments in *extra*),
        which clears #modal-root and so closes the modal.
        """
        headers = _toast_header(kind, title, body)
        if kind == "err":
            headers["HX-Reswap"] = "none"
        return Response(extra, status=status, content_type="text/html", headers=headers)

    def _send_modal(
        *,
        action: str,
        subtitle: str,
        email_to: str,
        tokens: dict[str, str],
        lang: str,
        has_period: bool,
        attachment: str = "",
        record: dict[str, object] | None = None,
    ) -> str:
        """Render the send modal, prefilled from the per-language templates."""
        from harvest_invoicer.mail import email_templates, fill_tokens  # noqa: PLC0415

        tr = _tr()
        cfg: dict[str, object] = app.state["email"]  # type: ignore[attr-defined]
        subject_tpl, message_tpl = email_templates(cfg, lang, has_period=has_period)
        from_address = (
            _smtp_settings().from_address or str(issuer.get("email") or "").strip()
        )
        sent_note = confirm = ""
        if record is not None and record.get("sent_at"):
            sent_to = str(record.get("sent_to") or "")
            sent_note = tr("send_already").format(
                to=sent_to, date=_fmt_ts(record["sent_at"])
            )
            confirm = tr("confirm_resend").format(number=record["number"], to=sent_to)
        return render_template(
            "partials/send_modal.html",
            send_action=action,
            subtitle=subtitle,
            email_to=email_to,
            email_subject=fill_tokens(subject_tpl, tokens),
            email_message=fill_tokens(message_tpl, tokens),
            email_from=from_address,
            attachment=attachment,
            sent_note=sent_note,
            confirm=confirm,
        )

    @app.get("/send/modal")
    def send_modal() -> Response | str:
        """Render the send-invoice modal for the live invoice."""
        from harvest_invoicer.mail import invoice_tokens  # noqa: PLC0415

        problem = _locked_config_problem()
        if problem:
            return _config_problem_modal(problem)
        with state_lock:
            inv: Invoice = copy.deepcopy(app.state["invoice"])  # type: ignore[attr-defined]
            cur_client: dict[str, str] = dict(app.state["client"])  # type: ignore[attr-defined]
        record = None
        if archive_dir is not None:
            # Render what Send would send: if that exact PDF was already
            # emailed, the modal warns and asks before sending it again.
            try:
                pdf, inv, cur_client, _key = _render_snapshot()
            except Exception:  # noqa: BLE001 — the send itself reports render errors
                pdf = b""
            record = _sent_entry(pdf, inv.number) if pdf else None
        return _send_modal(
            action="/send",
            subtitle=f"{inv.number} · {fmt_money(inv.grand_total)} {inv.currency}",
            email_to=str(cur_client.get("email") or ""),
            tokens=invoice_tokens(inv, cur_client, issuer),
            lang=resolve_language(cur_client, issuer),
            has_period=bool(inv.period_start and inv.period_end),
            record=record,
        )

    def _deliver(
        record: dict[str, object], pdf: bytes, cfg: dict[str, object]
    ) -> Response:
        """Email an archived invoice per the modal's form; record the delivery.

        Nothing about the message is logged: recipients, subject and body
        only travel to the SMTP server (and the recipients to the archive).
        """
        from harvest_invoicer.mail import (  # noqa: PLC0415
            MailConfigError,
            send_pdf_email,
        )

        tr = _tr()
        if record.get("sent_at") and request.form.get("confirm_resend") != "1":
            # Sent since the modal was opened (or never confirmed): ask first.
            return _send_response(
                "err",
                tr("cant_send"),
                tr("send_already").format(
                    to=record.get("sent_to") or "", date=_fmt_ts(record["sent_at"])
                ),
            )
        try:
            result = send_pdf_email(
                pdf,
                str(record["filename"]),
                issuer,
                cfg,
                to=request.form.get("to", ""),
                subject=request.form.get("subject", ""),
                message=request.form.get("message", ""),
                copy_self=request.form.get("copy_self") == "on",
            )
        except MailConfigError as exc:
            return _send_response("err", tr("cant_send"), str(exc))
        except OSError as exc:  # SMTPException subclasses OSError
            return _send_response("err", tr("send_failed"), str(exc))
        # Only the addresses the server accepted count as sent.
        sent_to = ", ".join(result.accepted)
        extra = ""
        if db_path is not None:
            try:
                with archive_lock:
                    mark_invoice_sent(db_path, str(record["id"]), now_iso(), sent_to)
                    fresh = lookup(db_path, str(record["id"]))
            except (sqlite3.Error, OSError):
                # The email is out: still report success.  No recipients or
                # link ids in the log — the file name identifies the invoice.
                app.logger.warning(
                    "Invoice %s was sent, but recording the delivery failed",
                    record["filename"],
                    exc_info=True,
                )
                fresh = None
            # On the Invoices page, refresh the row's sent status in place.
            on_list = urlsplit(request.headers.get("HX-Current-URL", "")).path
            if fresh is not None and on_list == "/invoices":
                extra = _invoice_row(fresh, oob=True)
        return _sent_response(result, extra)

    def _sent_response(result: SendResult, extra: str = "") -> Response:
        """Success toast; a warning naming any recipients the server refused."""
        tr = _tr()
        sent_to = ", ".join(result.accepted)
        if result.refused:
            return _send_response(
                "warn",
                tr("sent_partial"),
                tr("sent_partial_body").format(
                    to=sent_to, refused=", ".join(result.refused)
                ),
                extra=extra,
            )
        return _send_response(
            "ok", tr("sent"), tr("sent_body").format(to=sent_to), extra=extra
        )

    def _unsendable(to: str, subject: str) -> str | None:
        """Why a send would fail before reaching SMTP, or ``None``."""
        from harvest_invoicer.mail import (  # noqa: PLC0415
            MailConfigError,
            check_subject,
            parse_recipients,
        )

        try:
            parse_recipients(to)
            check_subject(subject)
        except MailConfigError as exc:
            return str(exc)
        return None if _smtp_enabled() else _tr()("smtp_disabled")

    @app.post("/send")
    def send_invoice() -> Response:
        """Email the invoice PDF using the modal's fields + stored SMTP config.

        With the archive the PDF is archived first (or the identical newest
        entry reused) and the delivery recorded on that entry, so the
        Invoices page shows what was sent.  The SMTP password is read from
        the environment only; every other setting comes from Settings >
        Email.  Feedback rides a toast.
        """
        from harvest_invoicer.mail import (  # noqa: PLC0415
            MailConfigError,
            send_invoice_email,
        )

        tr = _tr()
        problem = _locked_config_problem()
        if problem:
            return _send_response("err", tr("cfg_title"), tr("cfg_" + problem))
        with state_lock:
            cfg = dict(app.state["email"])  # type: ignore[attr-defined]
        to = request.form.get("to", "")
        subject = request.form.get("subject", "")
        unsendable = _unsendable(to, subject) if archive_dir is not None else None
        if unsendable:
            # Refused before anything is archived.
            return _send_response("err", tr("cant_send"), unsendable)
        # Snapshot together with the PDF, so the email metadata matches it
        # even if another tab edits concurrently.
        pdf, inv, cur_client, client_key = _render_snapshot()
        archived = _archive(pdf, inv, cur_client, client_key)
        if archived is not None:
            return _deliver(archived[0], pdf, cfg)
        try:
            result = send_invoice_email(
                pdf,
                inv,
                issuer,
                cur_client,
                cfg,
                to=to,
                subject=request.form.get("subject", ""),
                message=request.form.get("message", ""),
                copy_self=request.form.get("copy_self") == "on",
            )
        except MailConfigError as exc:
            return _send_response("err", tr("cant_send"), str(exc))
        except OSError as exc:  # SMTPException subclasses OSError
            return _send_response("err", tr("send_failed"), str(exc))
        return _sent_response(result)

    # --- Invoice archive ---

    def _fmt_ts(value: object) -> str:
        """An ISO timestamp as ``YYYY-MM-DD HH:MM`` in the server's local time.

        Stored values carry their UTC offset; a naive one is taken as local.
        """
        try:
            stamp = datetime.fromisoformat(str(value))
        except ValueError:
            return str(value or "")
        return stamp.astimezone().strftime("%Y-%m-%d %H:%M")

    def _row_ctx(
        record: dict[str, object], sends: int | None = None
    ) -> dict[str, object]:
        """An archived invoice, plus its display values, for the row template.

        *sends* is how often it was emailed (looked up when not given).
        """
        row = dict(record)
        if sends is None and db_path is not None:
            sends = len(invoice_sends(db_path, str(record["id"])))
        row["send_count"] = sends or 0
        row["created"] = _fmt_ts(record["created_at"])
        row["sent"] = _fmt_ts(record["sent_at"]) if record.get("sent_at") else ""
        row["total_fmt"] = fmt_money(float(str(record["total"])))
        row["has_file"] = (
            archive_dir is not None and invoice_file(archive_dir, record) is not None
        )
        return row

    def _invoice_row(record: dict[str, object], *, oob: bool = False) -> str:
        """One row of the Invoices table (``oob`` to refresh it in place)."""
        return render_template(
            "partials/invoice_row.html",
            inv=_row_ctx(record),
            send_available=_smtp_enabled(),
            oob=oob,
        )

    def _not_found() -> Response:
        tr = _tr()
        return _send_response("err", tr("not_found"), status=404)

    @app.get("/invoices")
    def invoices_page() -> Response | str:
        """The archive: every generated invoice, newest first."""
        if db_path is None:
            return Response("Not found.", status=404)
        counts = send_counts(db_path)
        return render_template(
            "invoices.html",
            invoices=[
                _row_ctx(r, counts.get(str(r["id"]), 0)) for r in list_invoices(db_path)
            ],
            send_available=_smtp_enabled(),
            oob=False,
        )

    @app.get("/invoices/<invoice_id>.pdf")
    def invoice_pdf(invoice_id: str) -> Response:
        """An archived invoice's PDF; ``?download=1`` as an attachment."""
        record, data = _archived(invoice_id)
        if record is None or data is None:
            return Response("Not found.", status=404, mimetype="text/plain")
        download = request.args.get("download") == "1"
        return _send_pdf(data, str(record["filename"]), download=download)

    @app.get("/invoices/<invoice_id>/send")
    def invoice_send_modal(invoice_id: str) -> Response | str:
        """The send modal for an archived invoice, in the invoice's language."""
        from harvest_invoicer.mail import archived_tokens  # noqa: PLC0415

        if db_path is None or archive_dir is None:
            return _not_found()
        record = lookup(db_path, invoice_id)
        if record is None:
            return _not_found()
        if invoice_file(archive_dir, record) is None:
            tr = _tr()
            return _send_response("err", tr("cant_send"), tr("file_missing"))
        clients_map: dict[str, dict[str, str]] = app.state["clients"]  # type: ignore[attr-defined]
        client_entry = clients_map.get(str(record.get("client_key") or "")) or {}
        tokens = archived_tokens(record, issuer)
        return _send_modal(
            action=f"/invoices/{record['id']}/send",
            subtitle=f"{record['number']} · {tokens['total']}",
            email_to=str(client_entry.get("email") or ""),
            tokens=tokens,
            lang=str(record.get("language") or "en"),
            has_period=bool(record.get("period_start") and record.get("period_end")),
            attachment=str(record["filename"]),
            record=record,
        )

    @app.post("/invoices/<invoice_id>/send")
    def invoice_send(invoice_id: str) -> Response:
        """Email an archived invoice (its stored PDF, byte for byte)."""
        # The bytes are read with the lookup (under the archive lock): a
        # delete racing this send leaves either the whole PDF or a 404.
        record, data = _archived(invoice_id)
        if record is None:
            return _not_found()
        if data is None:
            tr = _tr()
            return _send_response("err", tr("cant_send"), tr("file_missing"))
        with state_lock:
            cfg = dict(app.state["email"])  # type: ignore[attr-defined]
        return _deliver(record, data, cfg)

    @app.post("/invoices/<invoice_id>/delete")
    def invoice_delete(invoice_id: str) -> Response:
        """Delete an archived invoice: its row and its PDF.

        The response body is empty, so the Invoices page's row (the htmx
        target) disappears; a missing file is not an error.
        """
        if db_path is None or archive_dir is None:
            return _not_found()
        with archive_lock:
            record = lookup(db_path, invoice_id)
            if record is None:
                return _not_found()
            try:
                remove(db_path, archive_dir, record)
            except OSError as exc:
                # The file stays, and so does its row (nothing dangles).
                tr = _tr()
                return _send_response("err", tr("delete_failed"), exc.strerror or "")
        tr = _tr()
        return Response(
            "",
            content_type="text/html",
            headers=_toast_header("ok", tr("deleted"), str(record["filename"])),
        )

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
    def quit_server() -> Response | str:
        """Shut down the Werkzeug dev server gracefully."""
        if oidc is not None:
            # A server deployment is stopped by its supervisor, not a user.
            return Response("Not found.", status=404)

        def _stop() -> None:
            import time  # noqa: PLC0415

            time.sleep(0.2)
            os._exit(0)

        t = threading.Thread(target=_stop, daemon=True)
        t.start()
        return "<p>Server shutting down…</p>"

    return app
