"""Round Harvest time entries to the nearest increment (default: 15 minutes)."""

from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from rest import http_request


@dataclass
class TimeEntry:
    """Represents a Harvest time entry with rounding information."""

    id: int
    date: str
    hours: Fraction
    rounded_hours: Fraction
    notes: str
    project: str
    task: str
    client: str
    user: str

    @property
    def needs_rounding(self) -> bool:
        """Check if this entry needs to be rounded."""
        return self.hours != self.rounded_hours

    @property
    def difference(self) -> Fraction:
        """Return the difference between rounded and original hours."""
        return self.rounded_hours - self.hours


def round_to_increment(hours: Fraction, increment_minutes: int = 15) -> Fraction:
    """Round hours up to the next increment.

    Args:
        hours: The number of hours as a Fraction
        increment_minutes: The increment in minutes (default: 15)

    Returns:
        Hours rounded up to the next increment as a Fraction
    """
    # Convert increment from minutes to hours as a fraction
    increment_hours = Fraction(increment_minutes, 60)

    # If hours is zero, return zero
    if hours == 0:
        return Fraction(0)

    # Calculate how many increments fit into the hours
    # We use ceiling division to round up
    increments = hours / increment_hours

    # If it's already an exact multiple, return as-is
    if increments.denominator == 1:
        return hours

    # Otherwise, round up to next increment
    rounded_increments = int(increments) + 1
    return increment_hours * rounded_increments


def parse_time_entry(entry: dict[str, Any], increment_minutes: int = 15) -> TimeEntry:
    """Parse a Harvest API time entry into a TimeEntry object.

    Args:
        entry: Raw time entry from the Harvest API
        increment_minutes: The increment in minutes for rounding

    Returns:
        A TimeEntry object with original and rounded hours
    """
    hours = Fraction(entry["hours"]).limit_denominator(1000)
    rounded_hours = round_to_increment(hours, increment_minutes)

    return TimeEntry(
        id=entry["id"],
        date=entry["spent_date"],
        hours=hours,
        rounded_hours=rounded_hours,
        notes=entry.get("notes") or "",
        project=entry["project"]["name"],
        task=entry["task"]["name"],
        client=entry["client"]["name"],
        user=entry["user"]["name"],
    )


def get_time_entries(
    account_id: str,
    access_token: str,
    from_date: int,
    to_date: int,
    increment_minutes: int = 15,
) -> list[TimeEntry]:
    """Fetch time entries from Harvest and parse them.

    Args:
        account_id: Harvest account ID
        access_token: Harvest bearer token
        from_date: Start date as YYYYMMDD integer
        to_date: End date as YYYYMMDD integer
        increment_minutes: The increment in minutes for rounding

    Returns:
        List of TimeEntry objects
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Harvest-Account-id": account_id,
    }
    url = f"https://api.harvestapp.com/v2/time_entries?from={from_date}&to={to_date}"
    entries: list[TimeEntry] = []
    while url is not None:
        resp = http_request(url, headers=headers)
        entries.extend(
            parse_time_entry(entry, increment_minutes) for entry in resp["time_entries"]
        )
        url = resp["links"]["next"]
    return entries


def update_time_entry(
    account_id: str,
    access_token: str,
    entry_id: int,
    hours: Fraction,
) -> dict[str, Any]:
    """Update a time entry's hours in Harvest.

    Args:
        account_id: Harvest account ID
        access_token: Harvest bearer token
        entry_id: The ID of the time entry to update
        hours: The new hours value

    Returns:
        The updated time entry from the API
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Harvest-Account-id": account_id,
        "Content-Type": "application/json",
    }
    url = f"https://api.harvestapp.com/v2/time_entries/{entry_id}"

    return http_request(
        url,
        method="PATCH",
        headers=headers,
        data={"hours": float(hours)},
    )
