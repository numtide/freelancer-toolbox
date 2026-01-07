import json
import os
import sqlite3
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import click
import requests
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Constants
ECB_URL_90D = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist-90d.xml"
ECB_URL_HIST = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.xml"
ECB_NAMESPACE = {"ns": "http://www.ecb.int/vocabulary/2002-08-01/eurofxref"}

console = Console()

# Direction constants for closest rate
BEFORE = "before"
AFTER = "after"
CLOSEST = "closest"


def get_db_path() -> Path:
    """Get the database path using XDG standard."""
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    if not xdg_config_home:
        home = os.path.expanduser("~")
        xdg_config_home = os.path.join(home, ".config")

    config_dir = os.path.join(xdg_config_home, "ecbx")
    os.makedirs(config_dir, exist_ok=True)

    return Path(os.path.join(config_dir, "rates.db"))


def get_last_business_day(date_obj: datetime) -> datetime:
    """
    Gets the last business day (Monday to Friday) before or on the given date.
    """
    if date_obj.weekday() < 5:
        return date_obj
    if date_obj.weekday() == 5:  # Saturday
        return date_obj - timedelta(days=1)
    # Sunday
    return date_obj - timedelta(days=2)


def fetch_ecb_data(url: str) -> str | None:
    """Fetches the ECB's XML data."""
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.content
    except requests.exceptions.RequestException as e:
        console.print(f"[bold red]Error fetching data: {e}[/bold red]")
        return None


def parse_ecb_xml(xml_data: str) -> ET.Element | None:
    """Parses the ECB's XML data."""
    try:
        return ET.fromstring(xml_data)
    except ET.ParseError as e:
        console.print(f"[bold red]Error parsing XML: {e}[/bold red]")
        return None


def get_available_currencies(root: ET.Element) -> list[str]:
    """Gets all available currencies from the parsed XML."""
    currencies = set()
    for cube in root.findall(".//ns:Cube[@currency]", ECB_NAMESPACE):
        currencies.add(cube.attrib.get("currency"))
    return sorted(list(currencies))


def get_available_dates(root: ET.Element) -> list[str]:
    """Gets the available dates from the parsed XML."""
    available_dates = []
    for cube in root.findall(".//ns:Cube[@time]", ECB_NAMESPACE):
        available_dates.append(cube.attrib.get("time"))
    available_dates.sort(reverse=True)
    return available_dates


def format_date(date_str: str) -> str:
    """Formats a date string to YYYY-MM-DD."""
    if not date_str:
        return None
    if "-" not in date_str and len(date_str) >= 8:
        return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
    return date_str


def parse_date(date_str: str) -> datetime | None:
    """Parses a date string to a datetime object."""
    if not date_str:
        return None
    try:
        date_str = format_date(date_str)
        return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        console.print(
            f"[bold red]Error: Invalid date format: {date_str}. Use YYYY-MM-DD[/bold red]"
        )
        return None


class ExchangeRateStore:
    """
    A class to manage the storage and retrieval of exchange rates.
    """

    def __init__(self, db_path: str | None = None):
        """
        Initialize the exchange rate store.

        Args:
            db_path: Optional custom path to the database file.
        """
        if db_path is None:
            self.db_path = get_db_path()
        else:
            self.db_path = Path(db_path)

        self._initialize_connection()

    def _initialize_connection(self):
        """Initialize the database connection."""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.execute("PRAGMA foreign_keys = ON")
        # Set up proper decimal handling
        sqlite3.register_adapter(Decimal, lambda d: str(d))
        sqlite3.register_converter("DECIMAL", lambda s: Decimal(s.decode("utf-8")))
        self.conn.row_factory = sqlite3.Row

    def _check_tables_exist(self) -> bool:
        """Check if the necessary tables exist in the database."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='rates'"
        )
        return cursor.fetchone() is not None

    def close(self):
        """Close the database connection."""
        if hasattr(self, "conn") and self.conn:
            self.conn.close()

    def initialize(self) -> tuple[int, int]:
        """
        Initialize the database, creating tables and importing historical data.

        Returns:
            Tuple of (rate_count, date_count) added to the database.
        """
        cursor = self.conn.cursor()

        # Create tables if they don't exist
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS currencies (
            code TEXT PRIMARY KEY,
            name TEXT
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS rates (
            date TEXT,
            base_currency TEXT,
            target_currency TEXT,
            rate DECIMAL(20, 10) NOT NULL,
            PRIMARY KEY (date, base_currency, target_currency)
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """)

        # Insert EUR as base currency
        cursor.execute(
            "INSERT OR IGNORE INTO currencies (code, name) VALUES (?, ?)",
            ("EUR", "Euro"),
        )

        # Fetch and parse historical data
        xml_data = fetch_ecb_data(ECB_URL_HIST)
        if xml_data is None:
            return (0, 0)

        root = parse_ecb_xml(xml_data)
        if root is None:
            return (0, 0)

        # Process all dates and rates
        rate_count = 0
        dates = set()

        for date_node in root.findall(".//ns:Cube[@time]", ECB_NAMESPACE):
            date_str = date_node.attrib.get("time")
            dates.add(date_str)

            # Insert rates for this date
            for currency_node in date_node.findall(
                ".//ns:Cube[@currency]", ECB_NAMESPACE
            ):
                currency = currency_node.attrib.get("currency")
                rate_str = currency_node.attrib.get("rate")
                rate = Decimal(rate_str)

                # EUR to target currency
                cursor.execute(
                    """
                INSERT OR REPLACE INTO rates (date, base_currency, target_currency, rate)
                VALUES (?, ?, ?, ?)
                """,
                    (date_str, "EUR", currency, rate),
                )

                # Target currency to EUR (inverse rate)
                cursor.execute(
                    """
                INSERT OR REPLACE INTO rates (date, base_currency, target_currency, rate)
                VALUES (?, ?, ?, ?)
                """,
                    (date_str, currency, "EUR", Decimal(1) / rate),
                )

                # Add the currency to the currencies table
                cursor.execute(
                    "INSERT OR IGNORE INTO currencies (code) VALUES (?)", (currency,)
                )

                rate_count += 2  # Counting both directions

        # Store the latest update date
        if dates:
            latest_date = max(dates)
            cursor.execute(
                """
            INSERT OR REPLACE INTO metadata (key, value)
            VALUES ('last_updated', ?)
            """,
                (latest_date,),
            )

        self.conn.commit()
        return (rate_count, len(dates))

    def get_last_update_date(self) -> str | None:
        """
        Get the date of the last update.

        Returns:
            The date string of the last update, or None if not available.
        """
        if not self._check_tables_exist():
            return None

        cursor = self.conn.cursor()
        cursor.execute("SELECT value FROM metadata WHERE key = 'last_updated'")
        row = cursor.fetchone()

        if row:
            return row[0]
        return None

    def update(self) -> tuple[int, str]:
        """
        Update the database with the latest exchange rates.

        Returns:
            Tuple of (rate_count, latest_date) added to the database.
        """
        if not self._check_tables_exist():
            console.print(
                "[yellow]Database not initialized. Running initialization...[/yellow]"
            )
            rates, dates = self.initialize()
            return (rates, self.get_last_update_date())

        # Fetch the latest data
        xml_data = fetch_ecb_data(ECB_URL_90D)
        if xml_data is None:
            return (0, None)

        root = parse_ecb_xml(xml_data)
        if root is None:
            return (0, None)

        # Get the last update date
        last_update = self.get_last_update_date()

        cursor = self.conn.cursor()
        rate_count = 0
        latest_date = None

        for date_node in root.findall(".//ns:Cube[@time]", ECB_NAMESPACE):
            date_str = date_node.attrib.get("time")

            # Skip if we already have this date
            if last_update and date_str <= last_update:
                continue

            if latest_date is None or date_str > latest_date:
                latest_date = date_str

            # Insert rates for this date
            for currency_node in date_node.findall(
                ".//ns:Cube[@currency]", ECB_NAMESPACE
            ):
                currency = currency_node.attrib.get("currency")
                rate_str = currency_node.attrib.get("rate")
                rate = Decimal(rate_str)

                # EUR to target currency
                cursor.execute(
                    """
                INSERT OR REPLACE INTO rates (date, base_currency, target_currency, rate)
                VALUES (?, ?, ?, ?)
                """,
                    (date_str, "EUR", currency, rate),
                )

                # Target currency to EUR (inverse rate)
                cursor.execute(
                    """
                INSERT OR REPLACE INTO rates (date, base_currency, target_currency, rate)
                VALUES (?, ?, ?, ?)
                """,
                    (date_str, currency, "EUR", Decimal(1) / rate),
                )

                # Add the currency to the currencies table
                cursor.execute(
                    "INSERT OR IGNORE INTO currencies (code) VALUES (?)", (currency,)
                )

                rate_count += 2  # Counting both directions

        # Calculate all cross-rates for this date
        if latest_date:
            rate_count += self._calculate_cross_rates(latest_date)

            # Update the latest update date
            cursor.execute(
                """
            INSERT OR REPLACE INTO metadata (key, value)
            VALUES ('last_updated', ?)
            """,
                (latest_date,),
            )

        self.conn.commit()
        return (rate_count, latest_date)

    def _calculate_cross_rates(self, date_str: str) -> int:
        """
        Calculate cross-rates between all currency pairs.

        Args:
            date_str: The date to calculate cross-rates for.

        Returns:
            Number of cross-rates calculated.
        """
        cursor = self.conn.cursor()

        # Get all currencies that have rates against EUR for this date
        cursor.execute(
            """
        SELECT DISTINCT target_currency
        FROM rates
        WHERE date = ? AND base_currency = 'EUR'
        """,
            (date_str,),
        )

        currencies = [row[0] for row in cursor.fetchall()]
        count = 0

        # Calculate cross-rates for all currency pairs
        for base in currencies:
            if base == "EUR":
                continue

            # Get the rate from base to EUR
            cursor.execute(
                """
            SELECT rate
            FROM rates
            WHERE date = ? AND base_currency = ? AND target_currency = 'EUR'
            """,
                (date_str, base),
            )

            base_to_eur = cursor.fetchone()
            if not base_to_eur:
                continue

            base_to_eur_rate = base_to_eur[0]

            for target in currencies:
                if target == "EUR" or target == base:
                    continue

                # Get the rate from EUR to target
                cursor.execute(
                    """
                SELECT rate
                FROM rates
                WHERE date = ? AND base_currency = 'EUR' AND target_currency = ?
                """,
                    (date_str, target),
                )

                eur_to_target = cursor.fetchone()
                if not eur_to_target:
                    continue

                eur_to_target_rate = eur_to_target[0]

                # Calculate the cross-rate
                cross_rate = eur_to_target_rate * base_to_eur_rate

                # Insert the cross-rate
                cursor.execute(
                    """
                INSERT OR REPLACE INTO rates (date, base_currency, target_currency, rate)
                VALUES (?, ?, ?, ?)
                """,
                    (date_str, base, target, cross_rate),
                )

                count += 1

        return count

    def get_rate(
        self,
        base_currency: str,
        target_currency: str,
        as_of_date: str | datetime.date = "latest",
        closest_rate: str | None = None,
    ) -> tuple[str, Decimal | None]:
        """
        Get the exchange rate from base_currency to target_currency.

        Args:
            base_currency: The base currency code.
            target_currency: The target currency code.
            as_of_date: The date to get the rate for (or 'latest').
            closest_rate: Strategy for getting the closest rate if exact date not available.
                          Options: 'before', 'after', 'closest', or None.

        Returns:
            Tuple of (date_str, rate) or (date_str, None) if not found.
        """
        if not self._check_tables_exist():
            console.print(
                "[yellow]Database not initialized. Run 'initialize' first.[/yellow]"
            )
            return (None, None)

        cursor = self.conn.cursor()

        # Normalize currency codes
        base_currency = base_currency.upper()
        target_currency = target_currency.upper()

        # Handle 'latest' date
        if as_of_date == "latest":
            cursor.execute("SELECT value FROM metadata WHERE key = 'last_updated'")
            row = cursor.fetchone()
            if not row:
                return (None, None)
            date_str = row[0]
        elif isinstance(as_of_date, datetime.date):
            date_str = as_of_date.strftime("%Y-%m-%d")
        else:
            date_str = as_of_date

        # Try to get the rate for the exact date
        cursor.execute(
            """
        SELECT date, rate
        FROM rates
        WHERE date = ? AND base_currency = ? AND target_currency = ?
        """,
            (date_str, base_currency, target_currency),
        )

        row = cursor.fetchone()
        if row:
            return (row[0], row[1])

        # If exact date not found and no closest strategy, return None
        if not closest_rate:
            return (date_str, None)

        # Get closest rate based on strategy
        if closest_rate == BEFORE:
            cursor.execute(
                """
            SELECT date, rate
            FROM rates
            WHERE date <= ? AND base_currency = ? AND target_currency = ?
            ORDER BY date DESC
            LIMIT 1
            """,
                (date_str, base_currency, target_currency),
            )
        elif closest_rate == AFTER:
            cursor.execute(
                """
            SELECT date, rate
            FROM rates
            WHERE date >= ? AND base_currency = ? AND target_currency = ?
            ORDER BY date ASC
            LIMIT 1
            """,
                (date_str, base_currency, target_currency),
            )
        elif closest_rate == CLOSEST:
            # This is more complex - get the closest date on either side
            cursor.execute(
                """
            SELECT date, rate, ABS(julianday(date) - julianday(?)) as diff
            FROM rates
            WHERE base_currency = ? AND target_currency = ?
            ORDER BY diff ASC
            LIMIT 1
            """,
                (date_str, base_currency, target_currency),
            )
        else:
            return (date_str, None)

        row = cursor.fetchone()
        if row:
            return (row[0], row[1])

        return (date_str, None)

    def list_currencies(self) -> list[str]:
        """
        List all available currencies in the database.

        Returns:
            List of currency codes.
        """
        if not self._check_tables_exist():
            return []

        cursor = self.conn.cursor()
        cursor.execute("SELECT DISTINCT code FROM currencies ORDER BY code")
        return [row[0] for row in cursor.fetchall()]

    def get_stats(self) -> dict:
        """
        Get statistics about the database.

        Returns:
            Dictionary with database statistics.
        """
        if not self._check_tables_exist():
            return {
                "initialized": False,
                "last_updated": None,
                "currency_count": 0,
                "rate_count": 0,
                "date_range": (None, None),
            }

        cursor = self.conn.cursor()

        # Get last update date
        cursor.execute("SELECT value FROM metadata WHERE key = 'last_updated'")
        last_updated = cursor.fetchone()

        # Count currencies
        cursor.execute("SELECT COUNT(DISTINCT code) FROM currencies")
        currency_count = cursor.fetchone()[0]

        # Count rates
        cursor.execute("SELECT COUNT(*) FROM rates")
        rate_count = cursor.fetchone()[0]

        # Get date range
        cursor.execute("SELECT MIN(date), MAX(date) FROM rates")
        date_range = cursor.fetchone()

        return {
            "initialized": True,
            "last_updated": last_updated[0] if last_updated else None,
            "currency_count": currency_count,
            "rate_count": rate_count,
            "date_range": date_range,
        }


def validate_date(ctx, param, value):
    """Validate and format date parameter."""
    if not value:
        return None
    try:
        if "-" not in value and len(value) >= 8:
            value = f"{value[:4]}-{value[4:6]}-{value[6:8]}"
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
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format",
)
@click.argument("date", required=False, callback=validate_date)
@click.argument("base_currency")
@click.pass_context
def matrix(ctx, format, date, base_currency):
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

    if format == "json":
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


if __name__ == "__main__":
    try:
        cli(obj={})
    except Exception as e:
        console.print(f"[bold red]Error: {e}[/bold red]")
    finally:
        # Close any open database connections
        store = click.get_current_context().obj.get("STORE")
        if store:
            store.close()
