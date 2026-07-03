#!/usr/bin/env python3

import sys
from collections import OrderedDict, defaultdict
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from .transferwise import exchange_rate


def convert_currency(
    amount: Fraction, source_currency: str, target_currency: str
) -> Fraction:
    rate = exchange_rate(source_currency, target_currency)
    return amount * rate


@dataclass
class Task:
    name: str = ""
    client: str = ""
    # Use fractions here to avoid rounding errors, round to cents once on export
    rounded_hours: Fraction = Fraction(0)
    cost: Fraction = Fraction(0)
    hourly_rate: Fraction = Fraction(0)
    currency: str = ""
    is_external: bool = False

    def exchange_rate(self, currency: str) -> Fraction:
        return exchange_rate(self.currency, currency)

    def converted_cost(self, currency: str) -> Fraction:
        return convert_currency(self.cost, self.currency, currency)

    def converted_hourly_rate(self, currency: str) -> Fraction:
        return convert_currency(self.hourly_rate, self.currency, currency)

    @property
    def agency(self) -> str:
        if self.is_external:
            return "none"
        return "Numtide Sàrl"


class Client:
    def __init__(self) -> None:
        self.tasks: dict[str, Task] = defaultdict(Task)

    def sort(self) -> None:
        self.tasks = OrderedDict(sorted(self.tasks.items()))


class User:
    def __init__(self) -> None:
        self.clients: dict[str, Client] = defaultdict(Client)

    def sort(self) -> None:
        self.clients = OrderedDict(sorted(self.clients.items()))
        for client in self.clients.values():
            client.sort()


def process_entry(
    entry: dict[str, Any],
    users: dict[str, User],
    hourly_rate: Fraction | None,
    agency_rate: Fraction | None,
) -> None:
    task_name = entry["task"]["name"]
    is_external = (
        entry["client"]["name"].startswith("External - ") or agency_rate is None
    )

    if is_external:
        client_name = entry["project"]["name"]
        project_name = ""
    else:
        client_name = entry["client"]["name"]
        project_name = entry["project"]["name"]

    if hourly_rate is not None:
        rate = hourly_rate
    else:
        rate = entry["billable_rate"]
        if rate == 0 or rate is None:
            if entry["billable"]:
                print(
                    f"WARNING, hourly rate for {client_name}/{project_name}/{task_name} is 0.0, skip for export",
                    file=sys.stderr,
                )
            return

    task = users[entry["user"]["name"]].clients[client_name].tasks[task_name]
    task.name = task_name
    task.client = client_name
    task.is_external = is_external
    if task.is_external:
        task.hourly_rate = rate
    else:
        assert agency_rate is not None
        # the developer's hourly rate is what we charge to the customer, minus 25%
        task.hourly_rate = rate * agency_rate
    rounded_hours = Fraction(entry["rounded_hours"])
    task.rounded_hours += rounded_hours
    task.is_external = is_external

    if task.currency == "":
        task.currency = entry["client"]["currency"]
    else:
        msg = f"Currency of customer changed from {task.currency} to {entry['client']['currency']} within the billing period. This is not supported!"
        assert task.currency == entry["client"]["currency"], msg
    task.cost += rounded_hours * Fraction(task.hourly_rate)


def aggregate_time_entries(
    entries: list[dict[str, Any]],
    hourly_rate: Fraction | None,
    agency_rate: Fraction | None,
) -> dict[str, User]:
    users: dict[str, User] = defaultdict(User)
    for entry in entries:
        process_entry(entry, users, hourly_rate, agency_rate)

    for user in users.values():
        user.sort()
    return OrderedDict(sorted(users.items()))
