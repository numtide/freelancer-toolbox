from dataclasses import dataclass
from fractions import Fraction

from kimai.data import JsonSerializable


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
