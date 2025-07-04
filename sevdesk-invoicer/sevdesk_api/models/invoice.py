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

    def __init__(self, resolver: Any) -> None:
        """Initialize with an ObjectResolver instance."""
        self._resolver = resolver
        self._cache: dict[str, Unity] = {}

    def _get_unity(self, translation_code: str) -> Unity:
        """Get or create a Unity object for the given translation code."""
        unity_data = self._resolver.get_unity_by_translation_code(translation_code)
        if translation_code not in self._cache:
            self._cache[translation_code] = Unity(
                id=unity_data["id"],
                name=unity_data["name"],
                object_name=unity_data.get("objectName", "Unity"),
            )
        return self._cache[translation_code]

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
class TaxRule:
    """Tax rule object from SevDesk API."""

    id: int
    name: str
    code: str
    object_name: str = "TaxRule"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for API requests."""
        return {"id": self.id, "objectName": self.object_name}


class DynamicTaxRules:
    """Dynamic tax rules that fetch from the API."""

    def __init__(self, resolver: Any) -> None:
        """Initialize with an ObjectResolver instance."""
        self._resolver = resolver
        self._cache: dict[str, TaxRule] = {}
        self._cache_by_id: dict[int, TaxRule] = {}

    def _get_tax_rule_by_code(self, code: str) -> TaxRule:
        """Get or create a TaxRule object for the given code."""
        if code not in self._cache:
            tax_rule_data = self._resolver.get_tax_rule_by_code(code)
            tax_rule = TaxRule(
                id=int(tax_rule_data["id"]),
                name=tax_rule_data["name"],
                code=tax_rule_data["code"],
                object_name=tax_rule_data.get("objectName", "TaxRule"),
            )
            self._cache[code] = tax_rule
            self._cache_by_id[tax_rule.id] = tax_rule
        return self._cache[code]

    def _get_tax_rule_by_id(self, rule_id: int) -> TaxRule:
        """Get or create a TaxRule object for the given ID."""
        if rule_id not in self._cache_by_id:
            tax_rule_data = self._resolver.get_tax_rule_by_id(rule_id)
            tax_rule = TaxRule(
                id=int(tax_rule_data["id"]),
                name=tax_rule_data["name"],
                code=tax_rule_data["code"],
                object_name=tax_rule_data.get("objectName", "TaxRule"),
            )
            self._cache[tax_rule.code] = tax_rule
            self._cache_by_id[rule_id] = tax_rule
        return self._cache_by_id[rule_id]

    def get_by_id(self, rule_id: int) -> TaxRule:
        """Get tax rule by ID."""
        return self._get_tax_rule_by_id(rule_id)

    def get_by_code(self, code: str) -> TaxRule:
        """Get tax rule by code."""
        return self._get_tax_rule_by_code(code)

    # Revenue tax rules
    @property
    def taxable_revenue(self) -> TaxRule:
        """Umsatzsteuerpflichtige Umsätze."""
        return self._get_tax_rule_by_code("USTPFL_UMS_EINN")

    @property
    def exports(self) -> TaxRule:
        """Ausfuhren."""
        return self._get_tax_rule_by_code("AUSFUHREN")

    @property
    def intra_community_supply(self) -> TaxRule:
        """Innergemeinschaftliche Lieferungen."""
        return self._get_tax_rule_by_code("INNERGEM_LIEF")

    @property
    def tax_free_revenue(self) -> TaxRule:
        """Steuerfreie Umsätze §4 UStG."""
        return self._get_tax_rule_by_code("STFREIE_UMS_P4")

    @property
    def reverse_charge_13b(self) -> TaxRule:
        """Reverse Charge gem. §13b UStG."""
        return self._get_tax_rule_by_code("REV_CHARGE_13B_1")

    @property
    def small_business(self) -> TaxRule:
        """Steuer nicht erhoben nach §19UStG."""
        return self._get_tax_rule_by_code("KLEINUNTERNEHMER_P19")

    @property
    def not_taxable_in_country(self) -> TaxRule:
        """Nicht im Inland steuerbare Leistung."""
        return self._get_tax_rule_by_code("NICHT_IM_INLAND_STEUERBAR")

    @property
    def oss_goods(self) -> TaxRule:
        """One Stop Shop (goods)."""
        return self._get_tax_rule_by_code("OSS_GOODS")

    @property
    def oss_electronic_service(self) -> TaxRule:
        """One Stop Shop (electronic service)."""
        return self._get_tax_rule_by_code("OSS_SERVICES")

    @property
    def oss_other_service(self) -> TaxRule:
        """One Stop Shop (other service)."""
        return self._get_tax_rule_by_code("OSS_OTHER")

    @property
    def reverse_charge_18b(self) -> TaxRule:
        """Reverse Charge gem. §18b UStG."""
        return self._get_tax_rule_by_code("REV_CHARGE_13B_1_USTG")

    # Expense tax rules
    @property
    def intra_community_acquisition(self) -> TaxRule:
        """Innergemeinschaftliche Erwerbe."""
        return self._get_tax_rule_by_code("INNERGEM_ERWERB")

    @property
    def deductible_expenses(self) -> TaxRule:
        """Vorsteuerabziehbare Aufwendungen."""
        return self._get_tax_rule_by_code("VORST_ABZUGSF_AUFW")

    @property
    def non_deductible_expenses(self) -> TaxRule:
        """Nicht vorsteuerabziehbare Aufwendungen."""
        return self._get_tax_rule_by_code("NICHT_VORST_ABZUGSF_AUFW")

    @property
    def reverse_charge_13b_with_deduction(self) -> TaxRule:
        """Reverse Charge gem. §13b Abs. 2 UStG mit Vorsteuerabzug."""
        return self._get_tax_rule_by_code("REV_CHARGE_13B_MIT_VORST_ABZUG_0")

    @property
    def reverse_charge_13b_without_deduction(self) -> TaxRule:
        """Reverse Charge gem. §13b UStG ohne Vorsteuerabzug."""
        return self._get_tax_rule_by_code("REV_CHARGE_13B_OHNE_VORST_ABZUG_0")

    @property
    def reverse_charge_13b_eu(self) -> TaxRule:
        """Reverse Charge gem. §13b Abs. 1 EU Umsätze."""
        return self._get_tax_rule_by_code("REV_CHARGE_13B_EU_0")


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
            data["taxRule"] = self.tax_rule.to_dict()

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
            # Create a minimal TaxRule object from the response
            # In practice, this would be fetched via the dynamic tax rules
            tax_rule_data = data["taxRule"]
            invoice.tax_rule = TaxRule(
                id=int(tax_rule_data["id"]),
                name=tax_rule_data.get("name", ""),
                code=tax_rule_data.get("code", ""),
                object_name=tax_rule_data.get("objectName", "TaxRule"),
            )
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
