#!/usr/bin/env python3

from collections import OrderedDict, defaultdict
import sys
from typing import Dict, Any, List
from fractions import Fraction
from dataclasses import dataclass

from .transferwise import exchange_rate

NUMTIDE_RATE = 0.8

def convert_currency(amount: Fraction, source_currency: str, target_currency: str) -> Fraction:
    rate = exchange_rate(source_currency, target_currency)
    return amount * rate

@dataclass
class Project:
    # Use fractions here to avoid rounding errors, round to cents once on export
    rounded_hours: Fraction = Fraction(0)
    cost: Fraction = Fraction(0)
    hourly_rate: Fraction = Fraction(0)
    currency: str = ""

    def exchange_rate(self, currency: str) -> Fraction:
        return exchange_rate(self.currency, currency)

    def converted_cost(self, currency: str) -> Fraction:
        return convert_currency(self.cost, self.currency, currency)

    def converted_hourly_rate(self, currency: str) -> Fraction:
        return convert_currency(self.hourly_rate, self.currency, currency)


Aggregated = Dict[str, Dict[str, Project]]


def aggregate_time_entries(entries: List[Dict[str, Any]]) -> Aggregated:
    by_user_and_project: Dict[str, Dict[str, Project]] = defaultdict(
        lambda: defaultdict(lambda: Project())
    )
    for entry in entries:
        client_name = entry["client"]["name"]
        task_name = entry["task"]["name"]
        project_name = f"{client_name} - {task_name}"
        rate = entry["task_assignment"]["hourly_rate"]
        if rate == 0 or rate is None:
            print(
                f"WARNING, hourly rate for {client_name}{task_name}/{entry['task']['name']} is 0.0, skip for export",
                file=sys.stderr)
            continue

        project = by_user_and_project[entry["user"]["name"]][project_name]
        # the developer's hourly rate is what we charge to the customer, minus 20%
        project.hourly_rate = rate * NUMTIDE_RATE
        rounded_hours = Fraction(entry["rounded_hours"])
        project.rounded_hours += rounded_hours
        if project.currency == "":
            project.currency = entry["client"]["currency"]
        else:
            msg = f"Currency of customer changed from {project.currency} to {entry['client']['currency']} within the billing period. This is not supported!"
            assert project.currency == entry["client"]["currency"], msg
        project.cost += rounded_hours * Fraction(project.hourly_rate)

    for user, projects in by_user_and_project.items():
        by_user_and_project[user] = OrderedDict(sorted(projects.items()))
    return OrderedDict(sorted(by_user_and_project.items()))
