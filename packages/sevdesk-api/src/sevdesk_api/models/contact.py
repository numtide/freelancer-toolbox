"""Contact model and related enums for SevDesk API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
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
        """Set object name after initialization."""
        self.object_name = "Contact"

    def _add_basic_fields(self, data: dict[str, Any]) -> None:
        """Add basic name and description fields."""
        field_mapping = {
            "name": "name",
            "surename": "surename",
            "familyname": "familyname",
            "name2": "name2",
            "customer_number": "customerNumber",
            "description": "description",
        }
        for attr, key in field_mapping.items():
            value = getattr(self, attr, None)
            if value:
                data[key] = value

    def _add_financial_fields(self, data: dict[str, Any]) -> None:
        """Add financial and tax fields."""
        if self.tax_number:
            data["taxNumber"] = self.tax_number
        if self.vat_number:
            data["vatNumber"] = self.vat_number
        data["exemptVat"] = self.exempt_vat

        # Default payment terms
        field_mapping = {
            "default_time_to_pay": "defaultTimeToPay",
            "default_cashback_time": "defaultCashbackTime",
            "default_cashback_percent": "defaultCashbackPercent",
            "default_discount_amount": "defaultDiscountAmount",
        }
        for attr, key in field_mapping.items():
            value = getattr(self, attr, None)
            if value is not None:
                data[key] = value
        data["defaultDiscountPercentage"] = self.default_discount_percentage

    def _add_personal_fields(self, data: dict[str, Any]) -> None:
        """Add individual-specific fields."""
        if self.birthday:
            data["birthday"] = int(self.birthday.timestamp())
        field_mapping = {
            "gender": "gender",
            "academic_title": "academicTitle",
            "titel": "titel",
            "bank_account": "bankAccount",
            "bank_number": "bankNumber",
        }
        for attr, key in field_mapping.items():
            value = getattr(self, attr, None)
            if value:
                data[key] = value

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for API requests."""
        data = super().to_dict()

        # Add all field groups
        self._add_basic_fields(data)
        self._add_financial_fields(data)
        self._add_personal_fields(data)

        # Special handling for category
        if self.category:
            data["category"] = {"id": self.category.value, "objectName": "Category"}

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
            "defaultDiscountPercentage",
            False,
        )

        # Banking
        contact.bank_account = data.get("bankAccount")
        contact.bank_number = data.get("bankNumber")

        # Individual
        if data.get("birthday"):
            contact.birthday = datetime.fromtimestamp(data["birthday"], tz=UTC)
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
