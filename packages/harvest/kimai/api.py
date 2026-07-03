#!/usr/bin/env python3

import urllib
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from kimai.data import (
    ActivityInfo,
    CustomerInfo,
    TimeEntryFull,
    UserInfo,
)
from rest import http_request2


class KimaiError(Exception):
    pass


@dataclass
class KimaiAPI:
    access_token: str
    api_url: str

    def kimai_request(
        self, endpoint: str, data: dict[str, Any]
    ) -> list[dict[str, Any]]:
        # Don't mutate the caller's dict.
        data = dict(data)
        data["page"] = 1
        headers = {
            "Authorization": f"Bearer {self.access_token}",
        }
        all_entries = []
        while True:
            url = f"{self.api_url}{endpoint}"
            resp = http_request2(url, headers=headers, data=data)
            if isinstance(resp.json, dict):
                all_entries.append(resp.json)
            else:
                all_entries.extend(resp.json)

            total_pages = int(resp.headers.get("X-Total-Pages", 1))
            if data["page"] >= total_pages:
                break

            data["page"] += 1

        return all_entries

    def get_visible_projects(self, billable: bool = False) -> list[dict[str, Any]]:
        endpoint = "/api/projects"
        data: dict[str, Any] = {
            "visible": 1,
        }
        if billable:
            data["billable"] = 1
        return self.kimai_request(endpoint, data)

    def get_visible_users(self) -> list[dict[str, Any]]:
        endpoint = "/api/users"
        data = {
            "visible": 1,
        }
        return self.kimai_request(endpoint, data)

    def get_customer(self, customer_id: int) -> CustomerInfo:
        endpoint = f"/api/customers/{customer_id}"
        custom_data = self.kimai_request(endpoint, {})
        return CustomerInfo.from_json(custom_data[0])

    def get_user(self, user_id: int) -> UserInfo:
        endpoint = f"/api/users/{user_id}"
        user_data = self.kimai_request(endpoint, {})
        return UserInfo.from_json(user_data[0])

    def get_activity(self, activity_id: int) -> ActivityInfo:
        endpoint = f"/api/activities/{activity_id}"
        activity_data = self.kimai_request(endpoint, {})
        return ActivityInfo.from_json(activity_data[0])

    def get_time_entries(
        self,
        from_date: datetime,
        to_date: datetime,
        user_id: int,
        customer_id: int,
        project_id: int,
        billable: bool = True,
    ) -> list[dict[str, Any]]:
        endpoint = "/api/timesheets"
        data = {
            "user": user_id,
            "customer": customer_id,
            "project": project_id,
            "begin": from_date.strftime("%Y-%m-%dT%H:%M:%S"),
            "end": to_date.strftime("%Y-%m-%dT%H:%M:%S"),
            "billable": int(billable),
        }
        try:
            return self.kimai_request(endpoint, data)
        except urllib.error.HTTPError as e:
            msg = f"Failed to get time entries: {data}"
            raise KimaiError(msg) from e

    def get_time_entry(self, entry_id: int) -> TimeEntryFull:
        endpoint = f"/api/timesheets/{entry_id}"
        entry_data = self.kimai_request(endpoint, {})
        return TimeEntryFull.from_json(entry_data[0])
