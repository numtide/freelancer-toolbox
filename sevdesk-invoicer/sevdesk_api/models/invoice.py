"""Invoice models and related enums for SevDesk API."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

from .base import SevDeskObject, parse_iso_date
from .contact import Contact

if TYPE_CHECKING:
    from datetime import datetime


class InvoiceStatus(Enum):
    """Invoice status values."""

    DRAFT = 100
    OPEN = 200
    PAID = 1000


class InvoiceType(Enum):
    """Invoice types."""

    RE = "RE"  # Regular invoice
    AR = "AR"  # Advance invoice
    TR = "TR"  # Partial invoice
    ER = "ER"  # Final invoice
    MA = "MA"  # Dunning


class TaxRule(Enum):
    """Tax rules for sevdesk-Update 2.0."""

    # Revenue tax rules
    TAXABLE_REVENUE = 1  # Umsatzsteuerpflichtige Umsätze
    EXPORTS = 2  # Ausfuhren
    INTRA_COMMUNITY_SUPPLY = 3  # Innergemeinschaftliche Lieferungen
    TAX_FREE_REVENUE = 4  # Steuerfreie Umsätze §4 UStG
    REVERSE_CHARGE_13B = 5  # Reverse Charge gem. §13b UStG
    SMALL_BUSINESS = 11  # Steuer nicht erhoben nach §19UStG
    NOT_TAXABLE_IN_COUNTRY = 17  # Nicht im Inland steuerbare Leistung
    OSS_GOODS = 18  # One Stop Shop (goods)
    OSS_ELECTRONIC_SERVICE = 19  # One Stop Shop (electronic service)
    OSS_OTHER_SERVICE = 20  # One Stop Shop (other service)
    REVERSE_CHARGE_18B = 21  # Reverse Charge gem. §18b UStG

    # Expense tax rules
    INTRA_COMMUNITY_ACQUISITION = 8  # Innergemeinschaftliche Erwerbe
    DEDUCTIBLE_EXPENSES = 9  # Vorsteuerabziehbare Aufwendungen
    NON_DEDUCTIBLE_EXPENSES = 10  # Nicht vorsteuerabziehbare Aufwendungen
    REVERSE_CHARGE_13B_WITH_DEDUCTION = (
        12  # Reverse Charge gem. §13b Abs. 2 UStG mit Vorsteuerabzug
    )
    REVERSE_CHARGE_13B_WITHOUT_DEDUCTION = (
        13  # Reverse Charge gem. §13b UStG ohne Vorsteuerabzug
    )
    REVERSE_CHARGE_13B_EU = 14  # Reverse Charge gem. §13b Abs. 1 EU Umsätze


@dataclass
class Unity:
    """Unity type for invoice positions."""

    id: int
    name: str
    object_name: str = "Unity"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for API requests."""
        return {"id": self.id, "name": self.name, "objectName": self.object_name}



class DynamicUnityTypes:
    """Dynamic unity types that fetch IDs from the API."""

    def __init__(self, unity_resolver: Any) -> None:
        """Initialize with a UnityResolver instance."""
        self._resolver = unity_resolver
        self._cache: dict[str, Unity] = {}

    def _get_unity(self, translation_code: str) -> Unity:
        """Get or create a Unity object for the given translation code."""
        return self._resolver.get_unity_by_translation_code(translation_code)

    @property
    def hour(self) -> Unity:
        """Get Unity for hours."""
        return self._get_unity("UNITY_HOUR")

    @property
    def piece(self) -> Unity:
        """Get Unity for pieces."""
        return self._get_unity("UNITY_PIECE")

    @property
    def day(self) -> Unity:
        """Get Unity for days."""
        return self._get_unity("UNITY_DAYS")

    @property
    def kilogram(self) -> Unity:
        """Get Unity for kilograms."""
        return self._get_unity("UNITY_KILOGRAM")

    @property
    def cubic_meter(self) -> Unity:
        """Get Unity for cubic meters."""
        return self._get_unity("UNITY_CUBIC_METER")

    @property
    def meter(self) -> Unity:
        """Get Unity for meters."""
        return self._get_unity("UNITY_METER")

    @property
    def square_meter(self) -> Unity:
        """Get Unity for square meters."""
        return self._get_unity("UNITY_SQUARE_METER")

    @property
    def kilometer(self) -> Unity:
        """Get Unity for kilometers."""
        return self._get_unity("UNITY_KILOMETER")

    @property
    def month(self) -> Unity:
        """Get Unity for months."""
        return self._get_unity("UNITY_MONTH")

    @property
    def minute(self) -> Unity:
        """Get Unity for minutes."""
        return self._get_unity("UNITY_MINUTE")

    @property
    def liter(self) -> Unity:
        """Get Unity for liters."""
        return self._get_unity("UNITY_L")

    @property
    def parcel(self) -> Unity:
        """Get Unity for flat rate/parcel."""
        return self._get_unity("UNITY_BLANKET")


@dataclass
class InvoicePosition:
    """Invoice position/line item."""

    id: int | None = None
    object_name: str = "InvoicePos"
    quantity: float = 1.0
    price: float = 0.0
    name: str = ""
    unity: Unity | None = None
    position_number: int | None = None
    text: str | None = None
    discount: float | None = None
    tax_rate: float = 19.0
    sum_discount: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for API requests."""
        if self.unity is None:
            msg = "Unity must be set before converting to dict"
            raise ValueError(msg)

        data = {
            "objectName": self.object_name,
            "quantity": self.quantity,
            "price": self.price,
            "name": self.name,
            "unity": self.unity.to_dict(),
            "taxRate": self.tax_rate,
            "mapAll": True,
        }

        if self.id is not None:
            data["id"] = self.id
        if self.position_number is not None:
            data["positionNumber"] = self.position_number
        if self.text:
            data["text"] = self.text
        if self.discount is not None:
            data["discount"] = self.discount
        if self.sum_discount is not None:
            data["sumDiscount"] = self.sum_discount

        return data


@dataclass
class Invoice(SevDeskObject):
    """Invoice model."""

    invoice_number: str | None = None
    contact: Contact | None = None
    invoice_date: datetime | None = None
    header: str | None = None
    head_text: str | None = None
    foot_text: str | None = None
    time_to_pay: int | None = None
    discount_time: int | None = None
    discount: float = 0.0
    address_country: dict[str, Any] | None = None
    pay_date: datetime | None = None
    delivery_date: datetime | None = None
    delivery_date_until: datetime | None = None
    status: InvoiceStatus = InvoiceStatus.DRAFT
    small_settlement: bool = False
    contact_person: dict[str, Any] | None = None
    tax_rate: float = 19.0
    tax_set: dict[str, Any] | None = None
    tax_text: str = "Umsatzsteuer 19%"
    tax_type: str | None = None
    tax_rule: TaxRule | None = None
    invoice_type: InvoiceType = InvoiceType.RE
    currency: str = "EUR"
    origin: dict[str, Any] | None = None
    customer_internal_note: str | None = None
    show_net: bool = False
    send_date: datetime | None = None
    reference: str | None = None

    # Related objects
    positions: list[InvoicePosition] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.object_name = "Invoice"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for API requests."""
        data = super().to_dict()

        if self.invoice_number:
            data["invoiceNumber"] = self.invoice_number
        if self.contact:
            data["contact"] = self.contact.to_dict()
        if self.invoice_date:
            data["invoiceDate"] = self.invoice_date.strftime("%d.%m.%Y")
        if self.header:
            data["header"] = self.header
        if self.head_text:
            data["headText"] = self.head_text
        if self.foot_text:
            data["footText"] = self.foot_text
        if self.time_to_pay is not None:
            data["timeToPay"] = self.time_to_pay
        if self.discount_time is not None:
            data["discountTime"] = self.discount_time
        data["discount"] = self.discount

        if self.address_country:
            data["addressCountry"] = self.address_country
        if self.pay_date:
            data["payDate"] = self.pay_date.strftime("%d.%m.%Y")
        if self.delivery_date:
            data["deliveryDate"] = self.delivery_date.strftime("%d.%m.%Y")
        if self.delivery_date_until:
            data["deliveryDateUntil"] = self.delivery_date_until.strftime("%d.%m.%Y")

        data["status"] = str(self.status.value)
        data["smallSettlement"] = self.small_settlement

        if self.contact_person:
            data["contactPerson"] = self.contact_person
        else:
            data["contactPerson"] = None

        data["taxRate"] = self.tax_rate
        if self.tax_set:
            data["taxSet"] = self.tax_set
        data["taxText"] = self.tax_text
        if self.tax_type:
            data["taxType"] = self.tax_type
        if self.tax_rule:
            data["taxRule"] = {"id": self.tax_rule.value, "objectName": "TaxRule"}

        data["invoiceType"] = self.invoice_type.value
        data["currency"] = self.currency

        if self.origin:
            data["origin"] = self.origin
        if self.customer_internal_note:
            data["customerInternalNote"] = self.customer_internal_note
        data["showNet"] = self.show_net
        if self.send_date:
            data["sendDate"] = self.send_date.strftime("%d.%m.%Y")
        if self.reference:
            data["reference"] = self.reference

        data["mapAll"] = True

        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Invoice:
        """Create Invoice from API response."""
        invoice = cls()

        # Base fields
        invoice.id = data.get("id")
        invoice.object_name = data.get("objectName")
        invoice.invoice_number = data.get("invoiceNumber")

        # Contact
        if data.get("contact"):
            invoice.contact = Contact.from_dict(data["contact"])

        # Dates - API returns ISO format with timezone
        if data.get("invoiceDate"):
            invoice.invoice_date = parse_iso_date(data["invoiceDate"])
        if data.get("deliveryDate"):
            invoice.delivery_date = parse_iso_date(data["deliveryDate"])
        if data.get("deliveryDateUntil"):
            invoice.delivery_date_until = parse_iso_date(data["deliveryDateUntil"])

        # Status
        if data.get("status"):
            invoice.status = InvoiceStatus(int(data["status"]))

        # Other fields
        invoice.header = data.get("header")
        invoice.head_text = data.get("headText")
        invoice.foot_text = data.get("footText")
        invoice.time_to_pay = data.get("timeToPay")
        invoice.currency = data.get("currency", "EUR")
        invoice.reference = data.get("reference")

        # Tax
        if data.get("taxRule"):
            invoice.tax_rule = TaxRule(int(data["taxRule"]["id"]))
        invoice.tax_type = data.get("taxType")
        invoice.tax_rate = float(data.get("taxRate", 19.0))

        # Type
        if data.get("invoiceType"):
            invoice.invoice_type = InvoiceType(data["invoiceType"])

        # Timestamps
        if data.get("create"):
            invoice.create = parse_iso_date(data["create"])
        if data.get("update"):
            invoice.update = parse_iso_date(data["update"])

        return invoice
