from dataclasses import dataclass
from fractions import Fraction
from typing import TypeVar

from kimai.jsonserializer import JsonSerializable

T = TypeVar("T", bound="JsonSerializable")

# ruff: noqa: N815


@dataclass
class UserInfo(JsonSerializable):
    apiToken: bool
    initials: str
    id: int
    alias: str
    title: str | None
    username: str
    accountNumber: str | None
    enabled: bool
    color: str | None


@dataclass
class CustomerInfo(JsonSerializable):
    id: int
    name: str
    number: str
    comment: str | None
    visible: bool
    billable: bool
    company: str | None
    vatId: str | None
    contact: str | None
    address: str | None
    country: str
    currency: str
    phone: str | None
    fax: str | None
    mobile: str | None
    email: str | None
    homepage: str | None
    timezone: str
    metaFields: list
    teams: list
    budget: float
    timeBudget: float
    budgetType: str | None
    color: str


@dataclass
class ProjectInfo(JsonSerializable):
    parentTitle: str
    customer: int
    id: int
    name: str
    start: str
    end: str | None
    comment: str | None
    visible: bool
    billable: bool
    metaFields: list
    teams: list
    globalActivities: bool
    number: str
    color: str


@dataclass
class TimeEntry(JsonSerializable):
    activity: int
    project: int
    user: int
    tags: list
    id: int
    begin: str
    end: str
    duration: Fraction
    description: str | None
    rate: Fraction
    internalRate: Fraction
    exported: bool
    billable: bool
    metaFields: list


@dataclass
class TimeEntryFull(JsonSerializable):
    activity: int
    project: int
    user: int
    tags: list
    id: int
    begin: str
    end: str
    duration: Fraction
    description: str | None
    rate: Fraction
    hourlyRate: Fraction
    internalRate: Fraction
    exported: bool
    billable: bool
    metaFields: list


@dataclass
class ActivityInfo(JsonSerializable):
    parentTitle: str | None
    project: int | None
    id: int
    name: str
    comment: str | None
    visible: bool
    billable: bool
    metaFields: list
    teams: list
    number: str
    budget: float
    timeBudget: float
    budgetType: str | None
    color: str
