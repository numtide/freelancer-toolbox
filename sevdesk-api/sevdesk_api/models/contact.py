"""Contact model and related enums for SevDesk API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from .base import SevDeskObject, parse_iso_date


class ContactCategory(Enum):
    """Contact categories."""

    SUPPLIER = 2
    CUSTOMER = 3
    PARTNER = 4
    PROSPECT_CUSTOMER = 28


@dataclass
class Contact(SevDeskObject):
    """Contact model."""

    # Organization fields
    name: str | None = None

    # Individual fields
    surename: str | None = None
    familyname: str | None = None
    name2: str | None = None

    # Common fields
    category: ContactCategory | None = None
    customer_number: str | None = None
    description: str | None = None

    # Financial fields
    tax_number: str | None = None
    vat_number: str | None = None
    exempt_vat: bool = False
    default_time_to_pay: int | None = None
    default_cashback_time: int | None = None
    default_cashback_percent: float | None = None
    default_discount_amount: float | None = None
    default_discount_percentage: bool = False

    # Banking
    bank_account: str | None = None
    bank_number: str | None = None

    # Individual specific
    birthday: datetime | None = None
    gender: str | None = None
    academic_title: str | None = None
    titel: str | None = None  # Position in organization

    # Organization relationship
    parent: Contact | None = None

    def __post_init__(self) -> None:
        self.object_name = "Contact"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for API requests."""
        data = super().to_dict()

        # Add fields
        if self.name:
            data["name"] = self.name
        if self.surename:
            data["surename"] = self.surename
        if self.familyname:
            data["familyname"] = self.familyname
        if self.name2:
            data["name2"] = self.name2

        if self.category:
            data["category"] = {"id": self.category.value, "objectName": "Category"}

        if self.customer_number:
            data["customerNumber"] = self.customer_number
        if self.description:
            data["description"] = self.description

        # Financial fields
        if self.tax_number:
            data["taxNumber"] = self.tax_number
        if self.vat_number:
            data["vatNumber"] = self.vat_number
        data["exemptVat"] = self.exempt_vat

        if self.default_time_to_pay is not None:
            data["defaultTimeToPay"] = self.default_time_to_pay
        if self.default_cashback_time is not None:
            data["defaultCashbackTime"] = self.default_cashback_time
        if self.default_cashback_percent is not None:
            data["defaultCashbackPercent"] = self.default_cashback_percent
        if self.default_discount_amount is not None:
            data["defaultDiscountAmount"] = self.default_discount_amount
        data["defaultDiscountPercentage"] = self.default_discount_percentage

        # Banking
        if self.bank_account:
            data["bankAccount"] = self.bank_account
        if self.bank_number:
            data["bankNumber"] = self.bank_number

        # Individual specific
        if self.birthday:
            data["birthday"] = int(self.birthday.timestamp())
        if self.gender:
            data["gender"] = self.gender
        if self.academic_title:
            data["academicTitle"] = self.academic_title
        if self.titel:
            data["titel"] = self.titel

        # Parent organization
        if self.parent:
            data["parent"] = self.parent.to_dict()

        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Contact:
        """Create Contact from API response."""
        contact = cls()

        # Base fields
        contact.id = data.get("id")
        contact.object_name = data.get("objectName")

        # Organization/Individual fields
        contact.name = data.get("name")
        contact.surename = data.get("surename")
        contact.familyname = data.get("familyname")
        contact.name2 = data.get("name2")

        # Category
        if data.get("category"):
            cat_id = data["category"].get("id")
            if cat_id:
                contact.category = ContactCategory(int(cat_id))

        # Common fields
        contact.customer_number = data.get("customerNumber")
        contact.description = data.get("description")

        # Financial
        contact.tax_number = data.get("taxNumber")
        contact.vat_number = data.get("vatNumber")
        contact.exempt_vat = data.get("exemptVat", False)
        contact.default_time_to_pay = data.get("defaultTimeToPay")
        contact.default_cashback_time = data.get("defaultCashbackTime")
        contact.default_cashback_percent = data.get("defaultCashbackPercent")
        contact.default_discount_amount = data.get("defaultDiscountAmount")
        contact.default_discount_percentage = data.get(
            "defaultDiscountPercentage", False
        )

        # Banking
        contact.bank_account = data.get("bankAccount")
        contact.bank_number = data.get("bankNumber")

        # Individual
        if data.get("birthday"):
            contact.birthday = datetime.fromtimestamp(data["birthday"])
        contact.gender = data.get("gender")
        contact.academic_title = data.get("academicTitle")
        contact.titel = data.get("titel")

        # Parent
        if data.get("parent"):
            contact.parent = Contact.from_dict(data["parent"])

        # Timestamps
        if data.get("create"):
            contact.create = parse_iso_date(data["create"])
        if data.get("update"):
            contact.update = parse_iso_date(data["update"])

        return contact
