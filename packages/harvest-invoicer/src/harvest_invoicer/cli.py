"""Command-line interface for harvest-invoicer."""

from __future__ import annotations

import os
import webbrowser
from collections.abc import Callable
from datetime import date, datetime, timedelta
from pathlib import Path

import click

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

_DEFAULT_PORT = 8321

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
        "clients.json key of the client to bill. Decoupled from "
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


def _previous_month() -> str:
    today = date.today()
    if today.month == 1:
        return f"{today.year - 1}-12"
    return f"{today.year}-{today.month - 1:02d}"


def _xdg_config_dir() -> Path:
    """Return the app's XDG config directory (~/.config/harvest-invoicer)."""
    base = os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")
    return Path(base) / "harvest-invoicer"


def _resolve_config_path(explicit: str | None, filename: str) -> Path | None:
    """Locate a config file: explicit flag/env > ./<filename> > XDG dir.

    Returns ``None`` when nothing was passed explicitly and neither the
    current directory nor the XDG config directory has the file.
    """
    if explicit:
        return Path(explicit)
    cwd_candidate = Path(filename)
    if cwd_candidate.exists():
        return cwd_candidate
    xdg_candidate = _xdg_config_dir() / filename
    if xdg_candidate.exists():
        return xdg_candidate
    return None


def _blank_issuer() -> dict[str, object]:
    """Empty issuer skeleton so the editor can render before configuration."""
    issuer: dict[str, object] = dict.fromkeys(
        sorted(REQUIRED_ISSUER_FIELDS - {"bank"}), ""
    )
    issuer["bank"] = {"iban": "", "bic": ""}
    return issuer


def _missing_config_message() -> str:
    return (
        "No issuer.json / clients.json found. Searched the current directory "
        f"and {_xdg_config_dir()}. Run 'harvest-invoicer edit' to configure "
        "interactively, or pass --issuer/--clients."
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


@main.command("edit")
@click.option(
    "--month",
    default=None,
    metavar="YYYY-MM",
    help="Month to invoice (default: previous month).",
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
@click.option(
    "--issuer",
    "issuer_path",
    envvar="INVOICE_ISSUER_FILE",
    default=None,
    type=click.Path(),
    help="Path to issuer.json (default: ./issuer.json, then ~/.config/harvest-invoicer/).",
)
@click.option(
    "--clients",
    "clients_path",
    envvar="INVOICE_CLIENTS_FILE",
    default=None,
    type=click.Path(),
    help="Path to clients.json (default: ./clients.json, then ~/.config/harvest-invoicer/).",
)
@_TEMPLATES_DIR_OPTION
@click.option(
    "--number",
    "number_override",
    default=None,
    help="Invoice number (pre-filled with YYYY-MM when omitted).",
)
@click.option(
    "--output",
    "output_path",
    default=None,
    type=click.Path(),
    help="PDF output path (default: invoice-<number>.pdf).",
)
@click.option("--port", default=_DEFAULT_PORT, show_default=True, type=int)
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
@_period_options
@_MERGE_DUPLICATES_OPTION
@_BILL_TO_OPTION
def edit(
    month: str | None,
    client_filter: str | None,
    user_filter: str | None,
    issuer_path: str | None,
    clients_path: str | None,
    templates_dir: Path | None,
    number_override: str | None,
    output_path: str | None,
    port: int,
    no_browser: bool,
    currency: str,
    no_agency: bool,
    demo: bool,
    period_start: datetime | None,
    period_end: datetime | None,
    merge_duplicates: bool,
    bill_to: str | None,
) -> None:
    """Launch the interactive invoice editor in a local browser."""
    month = month or _previous_month()
    parse_month(month)  # validate format early; raises ClickException on bad input
    p_start, p_end = _resolve_period(month, period_start, period_end)

    issuer_file = _resolve_config_path(issuer_path, "issuer.json")
    clients_file = _resolve_config_path(clients_path, "clients.json")
    # First run without config: skip fetching and open Settings to create it.
    onboarding = not demo and (issuer_file is None or clients_file is None)

    if demo:
        issuer = load_issuer(str(_ISSUER_EXAMPLE))
        clients = load_clients(str(_CLIENTS_EXAMPLE))
    else:
        issuer = load_issuer(str(issuer_file)) if issuer_file else _blank_issuer()
        clients = load_clients(str(clients_file)) if clients_file else {}

    # Persistent defaults from issuer.json: the flags always win.
    default_bill_to = str(issuer.get("default_bill_to") or "").strip() or None

    if demo:

        def _fetch(ps: date, pe: date) -> list[InvoiceLine]:
            return make_demo_lines()
    else:

        def _fetch(ps: date, pe: date) -> list[InvoiceLine]:
            # Resolve the user filter at call time: harvest_user set in the
            # editor (Settings or a warning's click-to-pick button) applies
            # to re-fetches without restarting.
            cur_user = user_filter or (
                str(issuer.get("harvest_user") or "").strip() or None
            )
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
            if merge_duplicates:
                lines = merge_duplicate_lines(lines)
        client_entry = _resolve_bill_to_lenient(bill_to, default_bill_to, clients)
        lines = apply_client_vat(lines + client_extra_lines(client_entry), client_entry)

    number = resolve_invoice_number(
        month,
        number_override=number_override,
        number_template=str(issuer.get("number_template") or ""),
    )
    out_path = Path(output_path or f"invoice-{number}.pdf")

    from harvest_invoicer.app import create_app  # noqa: PLC0415

    # Settings saves land where the config was found; on first run they
    # default to the XDG config directory.  Demo config lives inside the
    # package and is never written back.
    if demo:
        eff_issuer_path = eff_clients_path = None
    else:
        eff_issuer_path = issuer_file or _xdg_config_dir() / "issuer.json"
        eff_clients_path = clients_file or _xdg_config_dir() / "clients.json"

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
        issuer_path=eff_issuer_path,
        clients_path=eff_clients_path,
        import_raw=raw_import,
        import_merge=merge_duplicates,
    )

    url = (
        f"http://127.0.0.1:{port}/settings"
        if onboarding
        else f"http://127.0.0.1:{port}/"
    )
    if onboarding:
        click.echo(
            "No configuration found — opening Settings to create it "
            f"(saved to {_xdg_config_dir()})."
        )
    click.echo(f"Starting editor at {url}")
    click.echo("Press Ctrl-C to stop.")
    if not no_browser:
        webbrowser.open(url)

    # threaded: a ~1s WeasyPrint preview render must not block edits.
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)


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
@click.option(
    "--issuer",
    "issuer_path",
    envvar="INVOICE_ISSUER_FILE",
    default=None,
    type=click.Path(),
    help="Path to issuer.json (default: ./issuer.json, then ~/.config/harvest-invoicer/).",
)
@click.option(
    "--clients",
    "clients_path",
    envvar="INVOICE_CLIENTS_FILE",
    default=None,
    type=click.Path(),
    help="Path to clients.json (default: ./clients.json, then ~/.config/harvest-invoicer/).",
)
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
    issuer_path: str | None,
    clients_path: str | None,
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
        issuer_path = str(_ISSUER_EXAMPLE)
        clients_path = str(_CLIENTS_EXAMPLE)
    else:
        issuer_file = _resolve_config_path(issuer_path, "issuer.json")
        clients_file = _resolve_config_path(clients_path, "clients.json")
        if issuer_file is None or clients_file is None:
            raise click.ClickException(_missing_config_message())
        issuer_path = str(issuer_file)
        clients_path = str(clients_file)

    issuer = load_issuer(issuer_path)
    clients = load_clients(clients_path)
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
