"""Common utilities for ECB exchange rate operations."""

import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

import requests
from rich.console import Console

from .constants import ECB_NAMESPACE

console = Console()


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
        response = requests.get(url, timeout=30)
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


def get_available_dates(root: ET.Element) -> list[str]:
    """Gets the available dates from the parsed XML."""
    available_dates = []
    for cube in root.findall(".//ns:Cube[@time]", ECB_NAMESPACE):
        available_dates.append(cube.attrib.get("time"))
    available_dates.sort(reverse=True)
    return available_dates


def format_date(date_str: str) -> str | None:
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
