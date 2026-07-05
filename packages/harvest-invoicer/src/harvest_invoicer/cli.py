"""Command-line interface for harvest-invoicer."""

from __future__ import annotations

import webbrowser
from collections.abc import Callable
from datetime import date, datetime, timedelta
from pathlib import Path

import click

from harvest_invoicer.fetch import (
    fetch_lines,
    load_clients,
    load_issuer,
    make_demo_lines,
    parse_month,
    resolve_client,
    resolve_invoice_number,
)
from harvest_invoicer.model import (
    DEFAULT_PAYMENT_TERM_DAYS,
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


def _previous_month() -> str:
    today = date.today()
    if today.month == 1:
        return f"{today.year - 1}-12"
    return f"{today.year}-{today.month - 1:02d}"


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
    "--client", "client_filter", default=None, help="Harvest client name filter."
)
@click.option("--user", "user_filter", default=None, help="Harvest user name filter.")
@click.option(
    "--issuer",
    "issuer_path",
    envvar="INVOICE_ISSUER_FILE",
    default="issuer.json",
    show_default=True,
    type=click.Path(),
)
@click.option(
    "--clients",
    "clients_path",
    envvar="INVOICE_CLIENTS_FILE",
    default="clients.json",
    show_default=True,
    type=click.Path(),
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
def edit(
    month: str | None,
    client_filter: str | None,
    user_filter: str | None,
    issuer_path: str,
    clients_path: str,
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
) -> None:
    """Launch the interactive invoice editor in a local browser."""
    month = month or _previous_month()
    parse_month(month)  # validate format early; raises ClickException on bad input
    p_start, p_end = _resolve_period(month, period_start, period_end)

    if demo:
        issuer_path = str(_ISSUER_EXAMPLE)
        clients_path = str(_CLIENTS_EXAMPLE)

    issuer = load_issuer(issuer_path)
    clients = load_clients(clients_path)

    if demo:

        def _fetch(ps: date, pe: date) -> list[InvoiceLine]:
            return make_demo_lines()
    else:

        def _fetch(ps: date, pe: date) -> list[InvoiceLine]:
            return fetch_lines(
                ps,
                pe,
                client_filter=client_filter,
                user_filter=user_filter,
                currency=currency,
                use_agency=not no_agency,
            )

    lines = _fetch(p_start, p_end)
    if merge_duplicates:
        lines = merge_duplicate_lines(lines)

    client_entry = resolve_client(client_filter, clients, lines)
    number = resolve_invoice_number(
        month,
        number_override=number_override,
        number_template=str(issuer.get("number_template") or ""),
    )
    out_path = Path(output_path or f"invoice-{number}.pdf")

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
        fetch_callback=_fetch,
    )

    url = f"http://127.0.0.1:{port}/"
    click.echo(f"Starting editor at {url}")
    click.echo("Press Ctrl-C to stop.")
    if not no_browser:
        webbrowser.open(url)

    app.run(host="127.0.0.1", port=port, debug=False)


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
    "--client", "client_filter", default=None, help="Harvest client name filter."
)
@click.option("--user", "user_filter", default=None, help="Harvest user name filter.")
@click.option(
    "--issuer",
    "issuer_path",
    envvar="INVOICE_ISSUER_FILE",
    default="issuer.json",
    show_default=True,
    type=click.Path(),
)
@click.option(
    "--clients",
    "clients_path",
    envvar="INVOICE_CLIENTS_FILE",
    default="clients.json",
    show_default=True,
    type=click.Path(),
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
def generate(
    months: tuple[str, ...],
    client_filter: str | None,
    user_filter: str | None,
    issuer_path: str,
    clients_path: str,
    templates_dir: Path | None,
    number_override: str | None,
    output_dir: str,
    currency: str,
    no_agency: bool,
    demo: bool,
    period_start: datetime | None,
    period_end: datetime | None,
    merge_duplicates: bool,
) -> None:
    """Headless: fetch → render → PDF for one or more months (no browser)."""
    from harvest_invoicer.render import render_pdf  # noqa: PLC0415

    if demo:
        issuer_path = str(_ISSUER_EXAMPLE)
        clients_path = str(_CLIENTS_EXAMPLE)

    issuer = load_issuer(issuer_path)
    clients = load_clients(clients_path)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

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
                    user_filter=user_filter,
                    currency=currency,
                    use_agency=not no_agency,
                )
            if merge_duplicates:
                lines = merge_duplicate_lines(lines)
            client_entry = resolve_client(client_filter, clients, lines)
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
