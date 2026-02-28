#!/usr/bin/env python3

from typing import Any

from rest import http_request


def get_current_user(account_id: str, access_token: str) -> str:
    """Get the name of the currently authenticated user.

    Args:
        account_id: Harvest account ID
        access_token: Harvest bearer token

    Returns:
        The full name of the current user
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Harvest-Account-id": account_id,
    }
    resp = http_request("https://api.harvestapp.com/v2/users/me", headers=headers)
    return f"{resp['first_name']} {resp['last_name']}"


def get_time_entries(
    account_id: str, access_token: str, from_date: str, to_date: str
) -> list[dict[str, Any]]:
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Harvest-Account-id": account_id,
    }
    url = f"https://api.harvestapp.com/v2/time_entries?from={from_date}&to={to_date}"
    entries = []
    while url is not None:
        resp = http_request(
            url,
            headers=headers,
        )
        entries.extend(resp["time_entries"])
        url = resp["links"]["next"]
    return entries
