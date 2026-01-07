"""CLI interface for ecbx."""

import json
from datetime import datetime
from decimal import Decimal

import click
from rich import box
from rich.panel import Panel
from rich.table import Table

from .constants import BEFORE, DEFAULT_AMOUNT
from .store import ExchangeRateStore
from .utils import console, format_date


def validate_date(ctx, param, value):
    """Validate and format date parameter."""
    if not value:
        return None
    try:
        value = format_date(value)
        datetime.strptime(value, "%Y-%m-%d")
        return value
    except ValueError:
        raise click.BadParameter(f"Invalid date format: {value}. Use YYYY-MM-DD")


@click.group()
@click.option("--db", "-d", help="Custom database path")
@click.option("--verbose", "-v", is_flag=True, help="Display additional information")
@click.pass_context
def cli(ctx, db, verbose):
    """
    Tool for fetching and querying exchange rates from the European Central Bank.
    """
    ctx.ensure_object(dict)
    ctx.obj["VERBOSE"] = verbose

    # Initialize the database connection
    store = ExchangeRateStore(db)
    ctx.obj["STORE"] = store


@cli.command()
@click.pass_context
def initialize(ctx):
    """Initialize the database with historical exchange rate data."""
    store = ctx.obj["STORE"]

    with console.status(
        "[bold green]Initializing database with historical data...[/bold green]"
    ):
        rates, dates = store.initialize()

    console.print(
        f"[green]Initialized with {rates} rates covering {dates} days[/green]"
    )


@cli.command()
@click.pass_context
def update(ctx):
    """Update the database with the latest exchange rates."""
    store = ctx.obj["STORE"]

    with console.status("[bold green]Updating exchange rates...[/bold green]"):
        rates, latest_date = store.update()

    if rates > 0:
        console.print(f"[green]Updated {rates} rates for {latest_date}[/green]")
    else:
        console.print("[yellow]No new rates to update[/yellow]")


@cli.command()
@click.pass_context
def status(ctx):
    """Show the status of the exchange rate database."""
    store = ctx.obj["STORE"]
    stats = store.get_stats()

    if not stats["initialized"]:
        console.print(
            "[yellow]Database not initialized. Run 'initialize' first.[/yellow]"
        )
        return

    table = Table(title="Exchange Rate Database Status", box=box.ROUNDED)
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Last Updated", stats["last_updated"] or "Never")
    table.add_row("Currencies", str(stats["currency_count"]))
    table.add_row("Exchange Rates", str(stats["rate_count"]))

    if stats["date_range"][0] and stats["date_range"][1]:
        date_range = f"{stats['date_range'][0]} to {stats['date_range'][1]}"
    else:
        date_range = "N/A"
    table.add_row("Date Range", date_range)

    console.print(table)

    if ctx.obj["VERBOSE"]:
        currencies = store.list_currencies()
        console.print("\n[bold]Available Currencies:[/bold]")

        # Create a compact grid of currencies
        for i in range(0, len(currencies), 8):
            console.print("  ".join(currencies[i : i + 8]))


@cli.command()
@click.argument("date", required=False, callback=validate_date)
@click.argument("base_currency")
@click.argument("target_currency")
@click.argument("amount", required=False, type=click.FLOAT)
@click.option(
    "--closest",
    "-c",
    type=click.Choice(["before", "after", "closest"]),
    default="before",
    help="Strategy for finding closest rate if exact date not found",
)
@click.pass_context
def convert(ctx, date, base_currency, target_currency, amount, closest):
    """
    Convert an amount from BASE_CURRENCY to TARGET_CURRENCY.

    DATE is the date to use for conversion (defaults to latest available date).
    If an AMOUNT is provided, it will be converted using the rate.
    """
    store = ctx.obj["STORE"]
    verbose = ctx.obj["VERBOSE"]

    base_currency = base_currency.upper()
    target_currency = target_currency.upper()

    if date is None:
        date = "latest"

    with console.status(
        f"[bold green]Getting exchange rate for {base_currency} to {target_currency}...[/bold green]"
    ):
        actual_date, rate = store.get_rate(
            base_currency, target_currency, date, closest
        )

    if rate is None:
        console.print(
            f"[bold red]No exchange rate found for {base_currency} to {target_currency}[/bold red]"
        )
        return

    table = Table(show_header=True, header_style="bold magenta", box=box.ROUNDED)
    table.add_column("Date", style="cyan")
    table.add_column("Exchange Rate", style="green")

    if amount is not None:
        table.add_column("Conversion", justify="right", style="cyan")
        converted = Decimal(str(amount)) * rate
        amount_str = f"{amount:.2f} {base_currency} = {converted:.2f} {target_currency}"
        table.add_row(
            actual_date, f"1 {base_currency} = {rate:.6f} {target_currency}", amount_str
        )
    else:
        table.add_row(actual_date, f"1 {base_currency} = {rate:.6f} {target_currency}")

    console.print(
        Panel.fit(table, title="[bold]ECB Exchange Rate[/bold]", border_style="green")
    )

    if verbose:
        console.print("\n[dim]Notes:[/dim]")
        console.print(
            "[dim]- The ECB publishes daily reference exchange rates for the Euro on business days.[/dim]"
        )
        console.print(
            "[dim]- For weekends and holidays, the previous business day's rate is used.[/dim]"
        )
        console.print(
            "[dim]- Cross-rates between non-EUR currencies are calculated from their respective EUR rates.[/dim]"
        )
        console.print("[dim]- Rates are published by the ECB around 16:00 CET.[/dim]")


@cli.command()
@click.pass_context
def currencies(ctx):
    """List all available currencies."""
    store = ctx.obj["STORE"]
    currencies = store.list_currencies()

    if not currencies:
        console.print("[yellow]No currencies found. Run 'initialize' first.[/yellow]")
        return

    table = Table(title="Available Currencies", box=box.ROUNDED)
    table.add_column("Code", style="cyan")

    # Arrange currencies in columns
    for currency in currencies:
        table.add_row(currency)

    console.print(table)


@cli.command()
@click.argument("date", required=False, callback=validate_date)
@click.pass_context
def rates(ctx, date):
    """
    Show all exchange rates for a specific date.

    DATE is the date to show rates for (defaults to latest available date).
    """
    store = ctx.obj["STORE"]

    if date is None:
        date = "latest"

    # Get the actual date
    actual_date, _ = store.get_rate("EUR", "USD", date, BEFORE)

    if not actual_date:
        console.print(f"[bold red]No rates found for {date}[/bold red]")
        return

    # Get all EUR based rates for this date
    cursor = store.conn.cursor()
    cursor.execute(
        """
    SELECT target_currency, rate
    FROM rates
    WHERE date = ? AND base_currency = 'EUR'
    ORDER BY target_currency
    """,
        (actual_date,),
    )

    rates = list(cursor.fetchall())

    if not rates:
        console.print(f"[bold red]No rates found for {actual_date}[/bold red]")
        return

    table = Table(title=f"Exchange Rates for {actual_date}", box=box.ROUNDED)
    table.add_column("Currency", style="cyan")
    table.add_column("Rate (EUR base)", style="green", justify="right")

    for rate in rates:
        table.add_row(rate[0], f"{rate[1]:.6f}")

    console.print(table)


@cli.command()
@click.option(
    "--format",
    "-f",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format",
)
@click.argument("date", required=False, callback=validate_date)
@click.argument("base_currency")
@click.pass_context
def matrix(ctx, output_format, date, base_currency):
    """
    Show a matrix of exchange rates for a specific base currency.

    DATE is the date to show rates for (defaults to latest available date).
    BASE_CURRENCY is the base currency to use.
    """
    store = ctx.obj["STORE"]
    base_currency = base_currency.upper()

    if date is None:
        date = "latest"

    # Get the actual date
    actual_date, _ = store.get_rate(base_currency, "EUR", date, BEFORE)

    if not actual_date:
        console.print(f"[bold red]No rates found for {date}[/bold red]")
        return

    # Get all rates for this base currency on this date
    cursor = store.conn.cursor()
    cursor.execute(
        """
    SELECT target_currency, rate
    FROM rates
    WHERE date = ? AND base_currency = ?
    ORDER BY target_currency
    """,
        (actual_date, base_currency),
    )

    rates = list(cursor.fetchall())

    if not rates:
        console.print(
            f"[bold red]No rates found for {base_currency} on {actual_date}[/bold red]"
        )
        return

    if output_format == "json":
        result = {
            "date": actual_date,
            "base": base_currency,
            "rates": {r[0]: float(r[1]) for r in rates},
        }
        console.print(json.dumps(result, indent=2))
    else:
        table = Table(
            title=f"Exchange Rates for {base_currency} on {actual_date}",
            box=box.ROUNDED,
        )
        table.add_column("Currency", style="cyan")
        table.add_column("Rate", style="green", justify="right")

        for rate in rates:
            table.add_row(rate[0], f"{rate[1]:.6f}")

        console.print(table)


def main():
    """Main entry point with proper cleanup."""
    try:
        cli()
    except Exception as e:
        console.print(f"[bold red]Error: {e}[/bold red]")
    finally:
        # Close any open database connections
        try:
            ctx = click.get_current_context(silent=True)
            if ctx and ctx.obj:
                store = ctx.obj.get("STORE")
                if store:
                    store.close()
        except RuntimeError:
            pass