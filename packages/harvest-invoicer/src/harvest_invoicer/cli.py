"""Command-line interface for harvest-invoicer."""

from __future__ import annotations

import webbrowser
from collections.abc import Callable
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import click
from pydantic import SecretStr, ValidationError

from harvest_invoicer.config import DEFAULT_OIDC_SCOPES, OidcSettings, friendly_error
from harvest_invoicer.db import (
    default_db_path,
    get_clients,
    get_email,
    get_issuer,
)
from harvest_invoicer.fetch import (
    apply_client_vat,
    client_extra_lines,
    fetch_lines,
    format_user_names,
    load_clients,
    load_issuer,
    make_demo_lines,
    parse_month,
    resolve_client,
    resolve_invoice_number,
)
from harvest_invoicer.model import (
    DEFAULT_PAYMENT_TERM_DAYS,
    REQUIRED_ISSUER_FIELDS,
    Invoice,
    InvoiceLine,
    merge_duplicate_lines,
)

if TYPE_CHECKING:
    from types import FrameType

_DEFAULT_PORT = 8321

# Worker threads for waitress.  One process only: the editor state lives in
# process memory, so it must never be split across workers.
_DEFAULT_THREADS = 8

# The app only takes form posts (no file uploads); 1 MiB is far beyond the
# largest settings or line-item submission.
_MAX_REQUEST_BODY = 1024 * 1024

_EXAMPLES_DIR = Path(__file__).parent / "examples"
_ISSUER_EXAMPLE = _EXAMPLES_DIR / "issuer.example.json"
_CLIENTS_EXAMPLE = _EXAMPLES_DIR / "clients.example.json"

_TEMPLATES_DIR_OPTION = click.option(
    "--templates-dir",
    "templates_dir",
    envvar="INVOICE_TEMPLATES_DIR",
    default=None,
    type=click.Path(file_okay=False, path_type=Path),
    help=(
        "Custom templates directory (invoice.html, style.css). "
        "Packaged defaults are used as fallback on a per-file basis."
    ),
)

_DB_OPTION = click.option(
    "--db",
    "db_path",
    envvar="HARVEST_INVOICER_DB",
    default=None,
    type=click.Path(dir_okay=False, path_type=Path),
    help="State database (default: ~/.local/share/harvest-invoicer/state.db).",
)

_MERGE_DUPLICATES_OPTION = click.option(
    "--merge-duplicates",
    "merge_duplicates",
    is_flag=True,
    help=(
        "Collapse lines with identical description, rate, and VAT after "
        "import (sums quantities across team members)."
    ),
)

_BILL_TO_OPTION = click.option(
    "--bill-to",
    "bill_to",
    default=None,
    metavar="KEY",
    help=(
        "Configured client key to bill. Decoupled from "
        "--harvest-client (the fetch filter). Default: issuer.json "
        "default_bill_to, then auto-detect from fetched data, then the "
        "single clients.json entry."
    ),
)


def _resolve_bill_to(
    bill_to: str | None,
    default_bill_to: str | None,
    client_filter: str | None,
    clients: dict[str, dict[str, str]],
    lines: list[InvoiceLine],
) -> dict[str, str]:
    """Pick the invoice's bill-to entry.

    Precedence: --bill-to flag > issuer.json default_bill_to > auto-detect
    from fetched data > single clients.json entry.
    """
    chosen = bill_to or default_bill_to
    if chosen:
        if chosen not in clients:
            available = ", ".join(sorted(clients.keys())) or "(none)"
            source = "--bill-to" if bill_to else "issuer.json default_bill_to"
            msg = (
                f"{source} '{chosen}' not found in clients.json.\n"
                f"  Available keys: {available}"
            )
            raise click.ClickException(msg)
        return clients[chosen]
    return resolve_client(client_filter, clients, lines)


def _resolve_bill_to_lenient(
    bill_to: str | None,
    default_bill_to: str | None,
    clients: dict[str, dict[str, str]],
) -> dict[str, str]:
    """Bill-to for the editor's lazy start (no fetched data to detect from).

    Explicit choices still fail loudly on unknown keys; otherwise fall back
    to the first clients.json entry — the editor's Bill-to dropdown can
    switch it at any time.
    """
    chosen = bill_to or default_bill_to
    if chosen:
        if chosen not in clients:
            available = ", ".join(sorted(clients.keys())) or "(none)"
            source = "--bill-to" if bill_to else "issuer.json default_bill_to"
            msg = (
                f"{source} '{chosen}' not found in clients.json.\n"
                f"  Available keys: {available}"
            )
            raise click.ClickException(msg)
        return clients[chosen]
    if clients:
        return next(iter(clients.values()))
    return {}


def _multi_user_warning(
    lines: list[InvoiceLine], user_filter: str | None
) -> str | None:
    """Warn when an unfiltered import mixes several people's hours."""
    if user_filter:
        return None
    people = {line.user for line in lines if line.user}
    if len(people) <= 1:
        return None
    return (
        f"Imported hours for {len(people)} people "
        f"({format_user_names(people)}) — set harvest_user in Settings or "
        "pass --user to import only your own."
    )


def _read_secret(value: str | None, path: Path | None, option: str) -> str:
    """A secret given inline or as a file (e.g. a mounted Kubernetes secret)."""
    if value and path:
        msg = f"Pass {option} or {option}-file, not both."
        raise click.ClickException(msg)
    if path:
        # Mounted secrets usually end with a newline; it is never part of it.
        return path.read_text(encoding="utf-8").strip()
    return value or ""


def _split_values(values: tuple[str, ...]) -> list[str]:
    """Repeatable option values, each of which may be a comma-separated list
    (the form an environment variable takes)."""
    return [v.strip() for raw in values for v in raw.split(",") if v.strip()]


def _oidc_settings(
    issuer: str | None,
    client_id: str | None,
    client_secret: str | None,
    client_secret_file: Path | None,
    allowed_emails: tuple[str, ...],
    allowed_subjects: tuple[str, ...],
    allow_any_user: bool,
    scopes: str,
    public_url: str | None,
    session_secret: str | None,
    session_secret_file: Path | None,
    secure_cookies: bool,
    session_lifetime: int,
) -> OidcSettings | None:
    """Validated OIDC settings, or ``None`` when login is not configured.

    OIDC is on exactly when an issuer is set.  Any other OIDC option without
    an issuer is an error rather than silently serving without login.
    """
    if not issuer:
        stray = [
            client_id,
            client_secret,
            client_secret_file,
            allowed_emails,
            allowed_subjects,
            allow_any_user,
            public_url,
            session_secret,
            session_secret_file,
        ]
        if any(stray):
            msg = (
                "OIDC options were given but no issuer: set --oidc-issuer "
                "(HARVEST_INVOICER_OIDC_ISSUER) to enable login."
            )
            raise click.ClickException(msg)
        return None
    try:
        return OidcSettings(
            issuer=issuer,
            client_id=client_id or "",
            client_secret=SecretStr(
                _read_secret(client_secret, client_secret_file, "--oidc-client-secret")
            ),
            allowed_emails=frozenset(_split_values(allowed_emails)),
            allowed_subjects=frozenset(_split_values(allowed_subjects)),
            allow_any_user=allow_any_user,
            scopes=scopes,
            public_url=public_url or "",
            session_secret=SecretStr(
                _read_secret(session_secret, session_secret_file, "--session-secret")
            ),
            secure_cookies=secure_cookies,
            session_lifetime_hours=session_lifetime,
        )
    except ValidationError as exc:
        raise click.ClickException(friendly_error(exc)) from exc


def _oidc_options[F: Callable[..., None]](cmd: F) -> F:
    """serve's OIDC login options (server deployment); all env-configurable."""
    secret_file = click.Path(exists=True, dir_okay=False, path_type=Path)
    options = [
        click.option(
            "--oidc-issuer",
            envvar="HARVEST_INVOICER_OIDC_ISSUER",
            metavar="URL",
            help=(
                "OpenID provider issuer URL. Setting it enables OIDC login "
                "for every request (server deployment)."
            ),
        ),
        click.option(
            "--oidc-client-id",
            envvar="HARVEST_INVOICER_OIDC_CLIENT_ID",
            help="OIDC client ID.",
        ),
        click.option(
            "--oidc-client-secret",
            envvar="HARVEST_INVOICER_OIDC_CLIENT_SECRET",
            help=(
                "OIDC client secret (omit for a PKCE-only public client). "
                "Prefer the env var or --oidc-client-secret-file: command-line "
                "values show in the process list."
            ),
        ),
        click.option(
            "--oidc-client-secret-file",
            envvar="HARVEST_INVOICER_OIDC_CLIENT_SECRET_FILE",
            type=secret_file,
            help="Read the OIDC client secret from this file.",
        ),
        click.option(
            "--oidc-allowed-email",
            "oidc_allowed_emails",
            envvar="HARVEST_INVOICER_OIDC_ALLOWED_EMAILS",
            multiple=True,
            metavar="EMAIL",
            help=(
                "Verified email allowed to sign in (repeatable or "
                "comma-separated; case-insensitive)."
            ),
        ),
        click.option(
            "--oidc-allowed-subject",
            "oidc_allowed_subjects",
            envvar="HARVEST_INVOICER_OIDC_ALLOWED_SUBJECTS",
            multiple=True,
            metavar="SUB",
            help="OIDC subject (sub claim) allowed to sign in (repeatable).",
        ),
        click.option(
            "--oidc-allow-any-user",
            envvar="HARVEST_INVOICER_OIDC_ALLOW_ANY_USER",
            is_flag=True,
            help=(
                "Admit every account the provider authenticates (no "
                "allow-list). Without it an empty allow-list is an error."
            ),
        ),
        click.option(
            "--oidc-scopes",
            envvar="HARVEST_INVOICER_OIDC_SCOPES",
            default=DEFAULT_OIDC_SCOPES,
            show_default=True,
            help="Scopes requested at login.",
        ),
        click.option(
            "--public-url",
            envvar="HARVEST_INVOICER_PUBLIC_URL",
            metavar="URL",
            help=(
                "Public origin of the editor (e.g. https://invoicer.example.com); "
                "required with OIDC. The redirect URIs are built from it, and "
                "the CSRF guard accepts its host."
            ),
        ),
        click.option(
            "--session-secret",
            envvar="HARVEST_INVOICER_SESSION_SECRET",
            help=(
                "Key signing the login session cookie (required with OIDC; "
                "at least 32 characters, e.g. `openssl rand -hex 32`). Prefer "
                "the env var or --session-secret-file. Rotating it signs "
                "everyone out."
            ),
        ),
        click.option(
            "--session-secret-file",
            envvar="HARVEST_INVOICER_SESSION_SECRET_FILE",
            type=secret_file,
            help="Read the session secret from this file.",
        ),
        click.option(
            "--session-lifetime",
            envvar="HARVEST_INVOICER_SESSION_LIFETIME",
            type=click.IntRange(min=1, max=720),
            default=12,
            show_default=True,
            metavar="HOURS",
            help="Hours a login lasts before signing in again.",
        ),
        click.option(
            "--trusted-proxies",
            envvar="HARVEST_INVOICER_TRUSTED_PROXIES",
            type=click.IntRange(min=0),
            default=None,
            metavar="N",
            help=(
                "Reverse proxies whose X-Forwarded-* headers are trusted "
                "(default: 1 with OIDC, else 0)."
            ),
        ),
        click.option(
            "--secure-cookies",
            envvar="HARVEST_INVOICER_SECURE_COOKIES",
            is_flag=True,
            help=(
                "Always mark the session cookie Secure (default: only when "
                "the request is https)."
            ),
        ),
    ]
    for option in reversed(options):
        cmd = option(cmd)
    return cmd


def _serve_waitress(app: object, host: str, port: int, threads: int) -> None:
    """Serve *app* with waitress: one process, *threads* worker threads.

    Forwarded headers are left to the app's ProxyFix (``--trusted-proxies``):
    waitress' own ``trusted_proxy`` handling stays off, and so does its
    default of stripping X-Forwarded-* headers it does not trust, which
    would hide them from ProxyFix.
    """
    import logging  # noqa: PLC0415
    import signal  # noqa: PLC0415

    import waitress  # noqa: PLC0415

    # waitress and the app log through `logging`; show INFO and up.
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    # Kubernetes stops a pod with SIGTERM, which by default kills Python
    # outright.  As SystemExit, waitress stops accepting connections and
    # lets in-flight requests finish (a few seconds at most) before exiting.
    def _on_sigterm(_signum: int, _frame: FrameType | None) -> None:
        raise SystemExit(0)

    previous = signal.signal(signal.SIGTERM, _on_sigterm)
    try:
        waitress.serve(
            app,
            host=host,
            port=port,
            threads=threads,
            ident="harvest-invoicer",  # Server header without a version
            clear_untrusted_proxy_headers=False,
            channel_timeout=60,
            connection_limit=100,
            max_request_header_size=64 * 1024,
            max_request_body_size=_MAX_REQUEST_BODY,
        )
    finally:
        signal.signal(signal.SIGTERM, previous)


def _previous_month() -> str:
    today = date.today()
    if today.month == 1:
        return f"{today.year - 1}-12"
    return f"{today.year}-{today.month - 1:02d}"


def _blank_issuer() -> dict[str, object]:
    """Empty issuer skeleton so the editor can render before configuration."""
    issuer: dict[str, object] = dict.fromkeys(
        sorted(REQUIRED_ISSUER_FIELDS - {"bank"}), ""
    )
    issuer["bank"] = {"iban": "", "bic": ""}
    return issuer


def _missing_config_message(db_file: Path) -> str:
    return (
        f"No configuration found in {db_file}. Run 'harvest-invoicer serve' "
        "to configure interactively (or point --db/HARVEST_INVOICER_DB at "
        "an existing state database)."
    )


def _build_invoice(
    lines: list[InvoiceLine],
    number: str,
    issuer: dict[str, object],
    currency: str = "EUR",
    payment_term_days: int = DEFAULT_PAYMENT_TERM_DAYS,
    period_start: date | None = None,
    period_end: date | None = None,
) -> Invoice:
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


def _resolve_period(
    month: str,
    period_start: datetime | None,
    period_end: datetime | None,
) -> tuple[date, date]:
    """Service period: explicit --period-start/--period-end win over --month."""
    default_start, default_end = parse_month(month)
    return (
        period_start.date() if period_start else date.fromisoformat(default_start),
        period_end.date() if period_end else date.fromisoformat(default_end),
    )


def _period_options[F: Callable[..., None]](cmd: F) -> F:
    """Shared --period-start / --period-end options."""
    start_option = click.option(
        "--period-start",
        "period_start",
        default=None,
        type=click.DateTime(formats=["%Y-%m-%d"]),
        help="Service period start shown on the invoice (default: first day of the month).",
    )
    end_option = click.option(
        "--period-end",
        "period_end",
        default=None,
        type=click.DateTime(formats=["%Y-%m-%d"]),
        help="Service period end shown on the invoice (default: last day of the month).",
    )
    return start_option(end_option(cmd))


@click.group()
def main() -> None:
    """harvest-invoicer: fetch Harvest time data and generate invoice PDFs."""


# ---------------------------------------------------------------------------
# edit command
# ---------------------------------------------------------------------------


@main.command("serve")
@click.option(
    "--harvest-client",
    "--client",
    "client_filter",
    default=None,
    help=(
        "Only import hours logged under this Harvest client "
        "(--client is a deprecated alias; unrelated to the invoiced client)."
    ),
)
@_DB_OPTION
@_TEMPLATES_DIR_OPTION
@click.option(
    "--output",
    "output_path",
    default=None,
    type=click.Path(),
    help="PDF output path (default: invoice-<number>.pdf).",
)
@click.option(
    "--host",
    default="127.0.0.1",
    show_default=True,
    envvar="HARVEST_INVOICER_HOST",
    help=(
        "Address to bind the editor to. Use 0.0.0.0 to reach it from other "
        "devices on your network (the app is unauthenticated unless "
        "--oidc-issuer is set — see --allowed-host)."
    ),
)
@click.option(
    "--allowed-host",
    "allowed_hosts",
    multiple=True,
    metavar="HOST",
    help=(
        "Extra Host value(s) the CSRF guard accepts (repeatable). Needed when "
        "binding to 0.0.0.0 and reaching the app via a specific hostname/IP."
    ),
)
@click.option("--port", default=_DEFAULT_PORT, show_default=True, type=int)
@click.option(
    "--server",
    envvar="HARVEST_INVOICER_SERVER",
    type=click.Choice(["auto", "werkzeug", "waitress"]),
    default="auto",
    show_default=True,
    help=(
        "HTTP server: waitress (production, used with --oidc-issuer) or the "
        "Werkzeug development server (local editor). auto picks by OIDC."
    ),
)
@click.option(
    "--threads",
    envvar="HARVEST_INVOICER_THREADS",
    type=click.IntRange(min=1, max=64),
    default=_DEFAULT_THREADS,
    show_default=True,
    help="waitress worker threads (always a single process).",
)
@click.option("--no-browser", is_flag=True, help="Don't open browser automatically.")
@click.option(
    "--currency",
    "currency",
    default="EUR",
    show_default=True,
    help="ISO currency code (e.g. EUR, USD, CHF).",
)
@click.option(
    "--no-agency",
    "no_agency",
    is_flag=True,
    help=(
        "Disable agency rate (direct-billing mode). "
        "Entries are grouped by project name; --client must be the project name. "
        "Default: agency mode groups by Harvest client name and applies the agency multiplier."
    ),
)
@click.option(
    "--demo",
    is_flag=True,
    help="Use synthetic data (no Harvest credentials required).",
)
@_oidc_options
def serve(
    client_filter: str | None,
    db_path: Path | None,
    templates_dir: Path | None,
    output_path: str | None,
    host: str,
    allowed_hosts: tuple[str, ...],
    port: int,
    server: str,
    threads: int,
    no_browser: bool,
    currency: str,
    no_agency: bool,
    demo: bool,
    oidc_issuer: str | None,
    oidc_client_id: str | None,
    oidc_client_secret: str | None,
    oidc_client_secret_file: Path | None,
    oidc_allowed_emails: tuple[str, ...],
    oidc_allowed_subjects: tuple[str, ...],
    oidc_allow_any_user: bool,
    oidc_scopes: str,
    public_url: str | None,
    session_secret: str | None,
    session_secret_file: Path | None,
    session_lifetime: int,
    trusted_proxies: int | None,
    secure_cookies: bool,
) -> None:
    """Serve the interactive invoice editor in a local browser.

    The invoice itself — number, dates, bill-to, whose hours to include —
    is edited live on the page, so the command takes no per-invoice flags:
    it seeds from the previous month and configured defaults, then hands
    over to the UI.

    With --oidc-issuer it becomes a server deployment: every request needs
    an allow-listed OpenID Connect login.
    """
    # Validate the login config before anything else, so a misconfigured
    # deployment fails fast instead of serving without auth.
    oidc = _oidc_settings(
        oidc_issuer,
        oidc_client_id,
        oidc_client_secret,
        oidc_client_secret_file,
        oidc_allowed_emails,
        oidc_allowed_subjects,
        oidc_allow_any_user,
        oidc_scopes,
        public_url,
        session_secret,
        session_secret_file,
        secure_cookies,
        session_lifetime,
    )
    if trusted_proxies is None:
        trusted_proxies = 1 if oidc else 0

    month = _previous_month()
    p_start, p_end = _resolve_period(month, None, None)

    db_file = db_path or default_db_path()
    if demo:
        onboarding = False
        issuer = load_issuer(str(_ISSUER_EXAMPLE))
        clients = load_clients(str(_CLIENTS_EXAMPLE))
        email_config: dict[str, object] = {}
    else:
        stored_issuer = get_issuer(db_file)
        # First run (no issuer configured): skip fetching and open Settings.
        onboarding = stored_issuer is None
        issuer = stored_issuer or _blank_issuer()
        clients = get_clients(db_file)
        email_config = get_email(db_file) or {}

    # Persistent defaults from issuer.json: the flags always win.
    default_bill_to = str(issuer.get("default_bill_to") or "").strip() or None

    if demo:

        def _fetch(ps: date, pe: date) -> list[InvoiceLine]:
            return make_demo_lines()
    else:

        def _fetch(ps: date, pe: date) -> list[InvoiceLine]:
            # Resolve the user filter at call time: harvest_user edited in
            # Settings applies to the next fetch without restarting.
            cur_user = str(issuer.get("harvest_user") or "").strip() or None
            return fetch_lines(
                ps,
                pe,
                client_filter=client_filter,
                user_filter=cur_user,
                currency=currency,
                use_agency=not no_agency,
            )

    # The editor starts without touching the Harvest API: lines are imported
    # from the web page (Fetch from Harvest). --month still seeds the invoice
    # number, the billing period, and the default import range.  Demo mode
    # keeps the eager load so the sample invoice appears immediately.
    raw_import: list[InvoiceLine] = []
    lines: list[InvoiceLine] = []
    if onboarding:
        client_entry: dict[str, str] = {}
    else:
        if demo:
            raw_import = _fetch(p_start, p_end)
            lines = list(raw_import)
        client_entry = _resolve_bill_to_lenient(None, default_bill_to, clients)
        lines = apply_client_vat(lines + client_extra_lines(client_entry), client_entry)

    number = resolve_invoice_number(
        month,
        number_override=None,
        number_template=str(issuer.get("number_template") or ""),
    )
    out_path = Path(output_path or f"invoice-{number}.pdf")

    # CSRF-guard allowlist: any explicit --allowed-host, plus the bind host
    # itself when it is a concrete address; a wildcard bind (0.0.0.0/::)
    # accepts any Host via "*" and relies on the same-origin check.
    wildcard_hosts = {"0.0.0.0", "::", ""}  # noqa: S104 — matched, not bound
    allowed = set(allowed_hosts)
    if host in wildcard_hosts:
        allowed.add("*")
    else:
        allowed.add(host)
    is_loopback = host in ("127.0.0.1", "localhost", "::1")

    from harvest_invoicer.app import create_app  # noqa: PLC0415

    app = create_app(
        lines,
        issuer,
        client_entry,
        number,
        out_path,
        templates_dir,
        currency,
        period_start=p_start,
        period_end=p_end,
        # Raw Harvest fetch; the editor applies the current bill-to
        # client's vat_rate and extra lines per request.
        fetch_callback=_fetch,
        clients=clients,
        # Demo state lives inside the package; never written back.
        db_path=None if demo else db_file,
        import_raw=raw_import,
        # Matches the default-checked "Auto-merge duplicate entries" box.
        import_merge=True,
        allowed_hosts=frozenset(allowed),
        email_config=email_config,
        oidc=oidc,
        trusted_proxies=trusted_proxies,
    )

    # A concrete bind host is browsable directly; a wildcard bind is reached
    # via one of the machine's real addresses, so point the browser at loopback.
    display_host = "127.0.0.1" if host in wildcard_hosts else host
    path = "/settings" if onboarding else "/"
    url = f"http://{display_host}:{port}{path}"
    if oidc and oidc.public_url:
        url = f"{oidc.public_url}{path}"
    if onboarding:
        click.echo(
            "No configuration found — opening Settings to create it "
            f"(saved to {db_file})."
        )
    if oidc:
        click.echo(f"OIDC login required (issuer {oidc.issuer}).")
    elif not is_loopback:
        click.echo(
            f"WARNING: binding to {host} exposes this unauthenticated editor "
            "to your network. Only do this on a trusted network."
        )
    click.echo(f"Starting editor at {url}")
    click.echo("Press Ctrl-C to stop.")
    if not no_browser:
        webbrowser.open(url)

    if server == "waitress" or (server == "auto" and oidc is not None):
        _serve_waitress(app, host, port, threads)
    else:
        # threaded: a ~1s WeasyPrint preview render must not block edits.
        app.run(host=host, port=port, debug=False, threaded=True)


# ---------------------------------------------------------------------------
# generate command
# ---------------------------------------------------------------------------


@main.command("generate")
@click.option(
    "--month",
    "months",
    multiple=True,
    metavar="YYYY-MM",
    help="Month(s) to invoice (repeatable; default: previous month).",
)
@click.option(
    "--harvest-client",
    "--client",
    "client_filter",
    default=None,
    help=(
        "Only import hours logged under this Harvest client "
        "(--client is a deprecated alias; unrelated to the invoiced client)."
    ),
)
@click.option(
    "--user",
    "user_filter",
    default=None,
    help=(
        "Only import hours logged by this Harvest user "
        "(default: issuer.json harvest_user, else everyone)."
    ),
)
@_DB_OPTION
@_TEMPLATES_DIR_OPTION
@click.option(
    "--number",
    "number_override",
    default=None,
    help="Invoice number (single-month only; pre-filled with YYYY-MM when omitted).",
)
@click.option(
    "--output-dir",
    "output_dir",
    default=".",
    show_default=True,
    type=click.Path(),
)
@click.option(
    "--currency",
    "currency",
    default="EUR",
    show_default=True,
    help="ISO currency code (e.g. EUR, USD, CHF).",
)
@click.option(
    "--no-agency",
    "no_agency",
    is_flag=True,
    help=(
        "Disable agency rate (direct-billing mode). "
        "Entries are grouped by project name; --client must be the project name. "
        "Default: agency mode groups by Harvest client name and applies the agency multiplier."
    ),
)
@click.option(
    "--demo",
    is_flag=True,
    help="Use synthetic data (no Harvest credentials required).",
)
@_period_options
@_MERGE_DUPLICATES_OPTION
@_BILL_TO_OPTION
def generate(
    months: tuple[str, ...],
    client_filter: str | None,
    user_filter: str | None,
    db_path: Path | None,
    templates_dir: Path | None,
    number_override: str | None,
    output_dir: str,
    currency: str,
    no_agency: bool,
    demo: bool,
    period_start: datetime | None,
    period_end: datetime | None,
    merge_duplicates: bool,
    bill_to: str | None,
) -> None:
    """Headless: fetch → render → PDF for one or more months (no browser)."""
    from harvest_invoicer.render import render_pdf  # noqa: PLC0415

    if demo:
        issuer = load_issuer(str(_ISSUER_EXAMPLE))
        clients = load_clients(str(_CLIENTS_EXAMPLE))
    else:
        db_file = db_path or default_db_path()
        stored_issuer = get_issuer(db_file)
        if stored_issuer is None:
            raise click.ClickException(_missing_config_message(db_file))
        issuer = stored_issuer
        clients = get_clients(db_file)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Persistent defaults from issuer.json: the flags always win.
    effective_user = user_filter or (
        str(issuer.get("harvest_user") or "").strip() or None
    )
    default_bill_to = str(issuer.get("default_bill_to") or "").strip() or None

    resolved_months = list(months) if months else [_previous_month()]

    if number_override and len(resolved_months) > 1:
        msg = "--number can only be used with a single --month."
        raise click.ClickException(msg)

    if (period_start or period_end) and len(resolved_months) > 1:
        msg = "--period-start/--period-end can only be used with a single --month."
        raise click.ClickException(msg)

    errors: list[str] = []
    for month in resolved_months:
        try:
            parse_month(month)  # validate format before demo branch
            p_start, p_end = _resolve_period(month, period_start, period_end)
            if demo:
                lines = make_demo_lines()
            else:
                lines = fetch_lines(
                    p_start,
                    p_end,
                    client_filter=client_filter,
                    user_filter=effective_user,
                    currency=currency,
                    use_agency=not no_agency,
                )
            warning = _multi_user_warning(lines, effective_user)
            if warning:
                click.echo(f"  warning: {warning}", err=True)
            if merge_duplicates:
                lines = merge_duplicate_lines(lines)
            client_entry = _resolve_bill_to(
                bill_to, default_bill_to, client_filter, clients, lines
            )
            lines = apply_client_vat(
                lines + client_extra_lines(client_entry), client_entry
            )
            number = resolve_invoice_number(
                month,
                number_override=number_override,
                number_template=str(issuer.get("number_template") or ""),
            )
            invoice = _build_invoice(
                lines,
                number,
                issuer,
                currency,
                period_start=p_start,
                period_end=p_end,
            )
            pdf_path = out_dir / f"invoice-{number}.pdf"
            render_pdf(invoice, issuer, client_entry, pdf_path, templates_dir)
            click.echo(f"  {month} -> {pdf_path}")
        except click.ClickException as exc:
            errors.append(f"{month}: {exc.format_message()}")
            click.echo(f"  ERROR {month}: {exc.format_message()}", err=True)

    if errors:
        raise SystemExit(1)


# ---------------------------------------------------------------------------
# templates commands
# ---------------------------------------------------------------------------


@main.group("templates")
def templates() -> None:
    """Manage custom invoice templates."""


@templates.command("init")
@click.argument(
    "directory",
    default="invoice-templates",
    type=click.Path(file_okay=False, path_type=Path),
)
@click.option("--force", is_flag=True, help="Overwrite existing files.")
def templates_init(directory: Path, force: bool) -> None:
    """Scaffold DIRECTORY with editable copies of the packaged templates.

    Copies ``invoice.html`` and ``style.css`` as a starting point for
    customization.  Point the tool at the directory with ``--templates-dir``
    (or ``INVOICE_TEMPLATES_DIR``); any file you delete falls back to the
    packaged version, so you can keep only what you change.
    """
    from harvest_invoicer.render import _PACKAGED_TEMPLATES_DIR  # noqa: PLC0415

    directory.mkdir(parents=True, exist_ok=True)
    for name in ("invoice.html", "style.css"):
        dest = directory / name
        if dest.exists() and not force:
            click.echo(f"  skipped {dest} (exists; use --force to overwrite)")
            continue
        dest.write_bytes((_PACKAGED_TEMPLATES_DIR / name).read_bytes())
        click.echo(f"  created {dest}")

    click.echo(
        f"\nEdit the files, then use them with:\n"
        f"  harvest-invoicer edit --templates-dir {directory} ...\n"
        f"  harvest-invoicer generate --templates-dir {directory} ...\n"
        f"or set INVOICE_TEMPLATES_DIR={directory}.\n"
        f"Missing files fall back to the packaged templates per-file."
    )


if __name__ == "__main__":
    main()
