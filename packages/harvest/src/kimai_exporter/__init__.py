from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from kimai.data import JsonSerializable

if TYPE_CHECKING:
    from fractions import Fraction


@dataclass
class ProjectReport(JsonSerializable):
    agency: str | None
    client: str
    task: str
    user: str
    source_hourly_rate: Fraction
    target_hourly_rate: Fraction
    exchange_rate: float
    rounded_hours: Fraction
    source_cost: Fraction
    source_currency: str
    target_cost: Fraction
    target_currency: str
    start_date: str
    end_date: str
