#!/usr/bin/env nix-shell
#!nix-shell -i python3 -p "python3.withPackages (ps: with ps; [ requests click rich ])"

import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

import click
import requests
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Constants
ECB_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist-90d.xml"
ECB_NAMESPACE = {"ns": "http://www.ecb.int/vocabulary/2002-08-01/eurofxref"}

console = Console()


def get_last_business_day(date_obj: datetime) -> datetime:
    """
    Gets the last business day (Monday to Friday) before or on the given date.
    """
    if date_obj.weekday() < 5:
        return date_obj
    if date_obj.weekday() == 5:
        return date_obj - timedelta(days=1)
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


def get_available_dates(root: ET.Element) -> list:
    """Gets the available dates from the parsed XML."""
    available_dates = []
    for cube in root.findall(".//ns:Cube[@time]", ECB_NAMESPACE):
        available_dates.append(cube.attrib.get("time"))
    available_dates.sort(reverse=True)
    return available_dates


def find_target_date(available_dates: list, date_str: str | None) -> str | None:
    """Finds the target date based on the available dates and the given date."""
    if not date_str:
        return available_dates[0]
    try:
        requested_date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        business_date_obj = get_last_business_day(requested_date_obj)
        business_date_str = business_date_obj.strftime("%Y-%m-%d")
        if business_date_str != date_str:
            console.print(
                f"[yellow]⚠️ {date_str} is a weekend. Using the previous Friday's rate: {business_date_str}[/yellow]"
            )
        if business_date_str in available_dates:
            return business_date_str
        if business_date_obj > datetime.strptime(available_dates[0], "%Y-%m-%d"):
            console.print(
                f"[yellow]⚠️ {business_date_str} is a future date. Using the most recent rate: {available_dates[0]}[/yellow]"
            )
            return available_dates[0]
        found = False
        for date in available_dates:
            if datetime.strptime(date, "%Y-%m-%d") <= business_date_obj:
                console.print(
                    f"[yellow]⚠️ No data available for {business_date_str}. Using the closest date: {date}[/yellow]"
                )
                found = True
                return date
        if not found:
            console.print(
                f"[yellow]⚠️ {business_date_str} is too old. Using the oldest available date: {available_dates[-1]}[/yellow]"
            )
            return available_dates[-1]
    except ValueError:
        console.print(
            f"[bold red]Error: Invalid date format: {date_str}. Use YYYY-MM-DD[/bold red]"
        )
        return None


def extract_exchange_rate(root: ET.Element, date_str: str) -> dict | None:
    """Extracts the exchange rate from the parsed XML."""
    available_dates = get_available_dates(root)
    if not available_dates:
        console.print("[bold red]Error: No exchange rate data found[/bold red]")
        return None
    target_date = find_target_date(available_dates, date_str)
    if target_date is None:
        return None
    xpath = f".//ns:Cube[@time='{target_date}']"
    cube_node = root.find(xpath, ECB_NAMESPACE)
    if cube_node is None:
        console.print(
            f"[bold red]Error: No information found for date {target_date}[/bold red]"
        )
        return None
    usd_node = cube_node.find(".//ns:Cube[@currency='USD']", ECB_NAMESPACE)
    if usd_node is not None:
        rate = float(usd_node.attrib.get("rate"))
        return {"date": target_date, "eur_usd": rate, "usd_eur": 1 / rate}
    console.print("[bold red]Error: No USD exchange rate found[/bold red]")
    return None


def get_exchange_data(date_str: str | None = None) -> dict | None:
    """Gets the USD/EUR exchange rate data from the ECB."""
    xml_data = fetch_ecb_data(ECB_URL)
    if xml_data is None:
        return None
    root = parse_ecb_xml(xml_data)
    if root is None:
        return None
    return extract_exchange_rate(root, date_str)


@click.command()
@click.argument("date", required=False)
@click.option(
    "--amount", "-a", type=float, default=25.0, help="Amount in USD to convert to EUR"
)
@click.option(
    "--reverse/--no-reverse",
    "-r/",
    default=False,
    help="Convert EUR to USD instead of USD to EUR",
)
@click.option("--verbose", "-v", is_flag=True, help="Display additional information")
def cli(date: str | None, amount: float, reverse: bool, verbose: bool) -> None:
    """
    Queries the USD/EUR exchange rate from the European Central Bank.
    DATE: Optional date in YYYY-MM-DD format. If not specified, uses the most recent date.
    """
    try:
        if date:
            if "-" not in date and len(date) >= 8:
                date = f"{date[:4]}-{date[4:6]}-{date[6:8]}"
            datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        console.print(
            f"[bold red]Error: Invalid date format: {date}. Use YYYY-MM-DD[/bold red]"
        )
        return
    with console.status("[bold green]Querying ECB exchange rates...[/bold green]"):
        data = get_exchange_data(date)
    if not data:
        return
    table = Table(show_header=True, header_style="bold magenta", box=box.ROUNDED)
    table.add_column("Date", style="cyan")
    table.add_column("Exchange Rate", style="green")
    table.add_column("Value", justify="right", style="cyan")
    if reverse:
        conversion_rate = data["eur_usd"]
        rate_str = f"1 EUR = {conversion_rate:.4f} USD"
        converted = amount * conversion_rate
        amount_str = f"{amount:.2f} EUR = {converted:.2f} USD"
    else:
        conversion_rate = data["usd_eur"]
        rate_str = f"1 USD = {conversion_rate:.4f} EUR"
        converted = amount * conversion_rate
        amount_str = f"{amount:.2f} USD = {converted:.2f} EUR"
    table.add_row(data["date"], rate_str, amount_str)
    console.print(
        Panel.fit(table, title="[bold]ECB Exchange Rate[/bold]", border_style="green")
    )
    if verbose:
        verbose_table = Table(show_header=True, box=box.SIMPLE)
        verbose_table.add_column("Currency", style="blue")
        verbose_table.add_column("Value", style="green")
        verbose_table.add_row("EUR/USD", f"{data['eur_usd']:.6f}")
        verbose_table.add_row("USD/EUR", f"{data['usd_eur']:.6f}")
        console.print(verbose_table)
        console.print("\n[dim]Notes:[/dim]")
        console.print(
            "[dim]- The ECB publishes daily reference exchange rates on business days (Monday to Friday).[/dim]"
        )
        console.print(
            "[dim]- For weekends and holidays, the previous business day's rate is used.[/dim]"
        )
        console.print("[dim]- Data is only available for the last 90 days.[/dim]")
        console.print("[dim]- Rates are published around 16:00 CET.[/dim]")


if __name__ == "__main__":
    cli()
