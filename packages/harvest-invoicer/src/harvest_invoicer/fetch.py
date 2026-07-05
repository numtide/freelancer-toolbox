"""Fetch Harvest time data and convert it to a list of InvoiceLine objects."""

from __future__ import annotations

import calendar
import os
from datetime import date, datetime

import click

from harvest_invoicer.model import COST_TOLERANCE, InvoiceLine


def _previous_month() -> str:
    """Return the previous calendar month as ``YYYY-MM``."""
    today = date.today()
    if today.month == 1:
        return f"{today.year - 1}-12"
    return f"{today.year}-{today.month - 1:02d}"


def parse_month(month_str: str) -> tuple[str, str]:
    """Parse a ``YYYY-MM`` string into (start_date, end_date) strings.

    Returns dates as ``YYYY-MM-DD`` strings suitable for the Harvest API.
    """
    try:
        parsed = datetime.strptime(month_str, "%Y-%m")
    except ValueError:
        msg = f"Invalid month format '{month_str}'. Expected YYYY-MM."
        raise click.ClickException(msg) from None
    last_day = calendar.monthrange(parsed.year, parsed.month)[1]
    start = parsed.date().replace(day=1)
    end = parsed.date().replace(day=last_day)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def fetch_lines(
    period_start: date,
    period_end: date,
    *,
    client_filter: str | None = None,
    user_filter: str | None = None,
    currency: str = "EUR",
    vat_rate: float = 0.0,
    use_agency: bool = True,
) -> list[InvoiceLine]:
    """Fetch Harvest entries between the two dates and return InvoiceLines.

    The inclusive date range drives the Harvest API query directly, so the
    imported data always matches the invoice's service period.

    Requires the ``HARVEST_ACCOUNT_ID`` and ``HARVEST_BEARER_TOKEN``
    environment variables.  Both a ``--client`` filter and a ``--user``
    filter are supported and applied before building lines.

    Agency mode (default, ``use_agency=True``): aggregation uses
    ``NUMTIDE_RATE`` imported from ``harvest_exporter.cli``.  The multiplier
    is applied to each developer's rate and entries are grouped by real
    Harvest client name.  "External - " prefixed clients are excluded unless
    ``client_filter`` explicitly targets them.

    Direct-billing mode (``use_agency=False``): ``agency_rate`` is ``None``
    and all entries are grouped by project name.  ``client_filter`` must be
    the project name and is required to select which entries to bill.

    Raises ClickException on credential errors or empty result sets.
    """
    # Deferred imports so tests that never call fetch_lines do not need live
    # Harvest credentials or the harvest package installed.
    from harvest import get_time_entries  # noqa: PLC0415
    from harvest_exporter import aggregate_time_entries  # noqa: PLC0415
    from harvest_exporter.cli import NUMTIDE_RATE  # noqa: PLC0415

    account_id = os.environ.get("HARVEST_ACCOUNT_ID", "")
    token = os.environ.get("HARVEST_BEARER_TOKEN", "")
    if not account_id or not token:
        msg = "HARVEST_ACCOUNT_ID and HARVEST_BEARER_TOKEN environment variables are required."
        raise click.ClickException(msg)

    start, end = period_start.isoformat(), period_end.isoformat()
    entries = get_time_entries(account_id, token, start, end)
    if not entries:
        msg = f"No time entries found between {start} and {end}."
        raise click.ClickException(msg)

    agency_rate = NUMTIDE_RATE if use_agency else None
    users = aggregate_time_entries(entries, hourly_rate=None, agency_rate=agency_rate)

    lines: list[InvoiceLine] = []
    for user_name, user in users.items():
        if user_filter and user_name != user_filter:
            continue
        for client_name, client in user.clients.items():
            if client_filter and client_name != client_filter:
                continue  # explicit filter: include only the matching client
            for task_name, task in client.tasks.items():
                if not client_filter and task.is_external:
                    continue  # agency mode: skip "External -" clients without explicit filter
                qty = float(task.rounded_hours)
                rate = float(task.converted_hourly_rate(currency))
                if qty <= 0:
                    continue

                expected_cost = float(task.converted_cost(currency))
                actual_cost = qty * rate
                if abs(actual_cost - expected_cost) > COST_TOLERANCE:
                    click.echo(
                        f"  warn: cost mismatch for {client_name}/{task_name}: "
                        f"expected {expected_cost:.2f}, got {actual_cost:.2f}",
                        err=True,
                    )

                description = f"{client_name} - {task_name}"
                lines.append(
                    InvoiceLine(
                        concept=description,
                        unit_price=rate,
                        quantity=qty,
                        vat_rate=vat_rate,
                    )
                )

    if not lines:
        client_info = f" (client={client_filter})" if client_filter else ""
        user_info = f" (user={user_filter})" if user_filter else ""
        msg = (
            f"No billable entries found between {start} and {end}"
            f"{client_info}{user_info}."
        )
        raise click.ClickException(msg)
    return lines


def make_demo_lines() -> list[InvoiceLine]:
    """Return synthetic invoice lines for the --demo / smoke-test mode."""
    return [
        InvoiceLine(
            concept="Acme Corp - Backend Development", unit_price=120.0, quantity=40.0
        ),
        InvoiceLine(concept="Acme Corp - Code Review", unit_price=120.0, quantity=8.0),
        InvoiceLine(
            concept="Acme Corp - Infrastructure", unit_price=100.0, quantity=4.0
        ),
    ]


def default_invoice_number(month: str) -> str:
    """Return the deterministic default invoice number for *month*.

    The default is simply the invoiced month string ``YYYY-MM``.
    An issuer.json ``number_template`` field (with ``{year}`` / ``{month}``
    placeholders) or the ``--number`` CLI flag overrides this.
    """
    return month


def resolve_invoice_number(
    month: str,
    *,
    number_override: str | None = None,
    number_template: str | None = None,
) -> str:
    """Determine the invoice number from override, template, or default.

    Priority: explicit ``--number`` > issuer ``number_template`` > ``YYYY-MM``.
    """
    if number_override:
        return number_override
    if number_template:
        try:
            year, mon = month.split("-")
            return number_template.format(year=year, month=mon)
        except (ValueError, KeyError):
            click.echo(
                f"  warn: number_template '{number_template}' could not be rendered "
                f"for month '{month}'; using default.",
                err=True,
            )
    return default_invoice_number(month)


def load_issuer(issuer_file: str) -> dict[str, object]:
    """Load and validate issuer.json, raising ClickException on errors."""
    import json  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    from harvest_invoicer.model import (  # noqa: PLC0415
        REQUIRED_ISSUER_BANK_FIELDS,
        REQUIRED_ISSUER_FIELDS,
    )

    p = Path(issuer_file)
    if not p.exists():
        msg = f"Issuer config not found: {p}"
        raise click.ClickException(msg)
    data: object = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        msg = f"{issuer_file} must be a JSON object."
        raise click.ClickException(msg)
    missing = REQUIRED_ISSUER_FIELDS - set(data.keys())
    if missing:
        msg = f"issuer.json missing required fields: {', '.join(sorted(missing))}"
        raise click.ClickException(msg)
    bank = data.get("bank")
    if not isinstance(bank, dict):
        msg = "issuer.bank must be an object."
        raise click.ClickException(msg)
    missing_bank = REQUIRED_ISSUER_BANK_FIELDS - set(bank.keys())
    if missing_bank:
        msg = f"issuer.bank missing required fields: {', '.join(sorted(missing_bank))}"
        raise click.ClickException(msg)
    return data


def load_clients(clients_file: str) -> dict[str, dict[str, str]]:
    """Load clients.json (a dict keyed by Harvest client name).

    Each value must have at minimum: name, address_line1, address_line2,
    country, tax_id. ``tax_id_label`` is optional (default "Tax ID").
    """
    import json  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    p = Path(clients_file)
    if not p.exists():
        msg = f"Clients config not found: {p}"
        raise click.ClickException(msg)
    data: object = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        msg = f"{clients_file} must be a JSON object."
        raise click.ClickException(msg)
    result: dict[str, dict[str, str]] = {}
    for key, entry in data.items():
        if not isinstance(entry, dict):
            msg = f"clients.json entry for '{key}' must be an object."
            raise click.ClickException(msg)
        vat = entry.get("vat_rate")
        if vat is not None:
            try:
                vat_val = float(vat)
            except (TypeError, ValueError):
                vat_val = -1.0
            if not 0.0 <= vat_val <= 1.0:
                msg = (
                    f"clients.json entry for '{key}': vat_rate must be a number "
                    f"between 0 and 1 (e.g. 0.21 for 21%), got {vat!r}."
                )
                raise click.ClickException(msg)
        result[key] = entry
    return result


def apply_client_vat(
    lines: list[InvoiceLine],
    client_entry: dict[str, str],
) -> list[InvoiceLine]:
    """Apply the client's optional ``vat_rate`` (clients.json) to every line.

    Lines keep their existing rate when the client entry has no
    ``vat_rate``.  Returns the same list for chaining.
    """
    vat_raw = client_entry.get("vat_rate")
    if vat_raw is None:
        return lines
    vat = float(vat_raw)
    for line in lines:
        line.vat_rate = vat
    return lines


def resolve_client(
    client_filter: str | None,
    clients: dict[str, dict[str, str]],
    lines: list[InvoiceLine],
) -> dict[str, str]:
    """Pick the correct client entry from clients.json.

    When a ``--client`` filter is given, look it up directly.
    Otherwise, infer the client name from the first line's concept prefix.
    """
    if client_filter:
        if client_filter not in clients:
            available = ", ".join(sorted(clients.keys())) or "(none)"
            msg = (
                f"Client '{client_filter}' not found in clients.json.\n"
                f"  Available keys: {available}"
            )
            raise click.ClickException(msg)
        return clients[client_filter]

    # Auto-detect from first line
    if lines:
        first_concept = lines[0].concept
        # concept format: "<client_name> - <task_name>"
        client_name_guess = first_concept.split(" - ")[0].strip()
        if client_name_guess in clients:
            return clients[client_name_guess]

    # Fall back to single-entry dict
    if len(clients) == 1:
        return next(iter(clients.values()))

    available = ", ".join(sorted(clients.keys())) or "(none)"
    msg = (
        f"Could not determine client automatically. "
        f"Use --client with one of: {available}"
    )
    raise click.ClickException(msg)
