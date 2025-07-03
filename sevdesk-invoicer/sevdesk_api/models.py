"""SevDesk API Models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class ContactCategory(Enum):
    """Contact categories."""

    SUPPLIER = 2
    CUSTOMER = 3
    PARTNER = 4
    PROSPECT_CUSTOMER = 28


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


class Unity(Enum):
    """Unity types for invoice positions."""

    PIECE = {"id": 1, "name": "Stück", "objectName": "Unity"}  # noqa: RUF012
    HOUR = {"id": 2, "name": "Stunde", "objectName": "Unity"}  # noqa: RUF012
    DAY = {"id": 3, "name": "Tag", "objectName": "Unity"}  # noqa: RUF012
    KILOGRAM = {"id": 4, "name": "Kilogramm", "objectName": "Unity"}  # noqa: RUF012
    CUBIC_METER = {"id": 5, "name": "Kubikmeter", "objectName": "Unity"}  # noqa: RUF012
    METER = {"id": 6, "name": "Meter", "objectName": "Unity"}  # noqa: RUF012
    SQUARE_METER = {"id": 7, "name": "Quadratmeter", "objectName": "Unity"}  # noqa: RUF012
    KILOMETER = {"id": 8, "name": "Kilometer", "objectName": "Unity"}  # noqa: RUF012
    MONTH = {"id": 9, "name": "Monat", "objectName": "Unity"}  # noqa: RUF012
    MINUTE = {"id": 10, "name": "Minute", "objectName": "Unity"}  # noqa: RUF012
    LITER = {"id": 11, "name": "Liter", "objectName": "Unity"}  # noqa: RUF012
    PARCEL = {"id": 12, "name": "Pauschal", "objectName": "Unity"}  # noqa: RUF012

    @property
    def id(self) -> int:
        return self.value["id"]

    @property
    def name(self) -> str:
        return self.value["name"]

    def to_dict(self) -> dict[str, Any]:
        return self.value.copy()


class CheckAccountType(Enum):
    """Check account types."""

    OFFLINE = "offline"  # Clearing account
    ONLINE = "online"  # Bank account
    REGISTER = "register"  # Cash register


class CheckAccountStatus(Enum):
    """Check account status."""

    ACTIVE = 0
    INACTIVE = 100


class TransactionStatus(Enum):
    """Transaction status."""

    UNPAID = 100
    PAID = 200
    DELETED = 300
    PARTIAL = 400


@dataclass
class SevDeskObject:
    """Base class for SevDesk objects."""

    id: int | None = None
    object_name: str | None = None
    create: datetime | None = None
    update: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for API requests."""
        data = {}
        if self.id is not None:
            data["id"] = self.id
        if self.object_name:
            data["objectName"] = self.object_name
        return data


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
            contact.create = datetime.fromisoformat(
                data["create"]
            )
        if data.get("update"):
            contact.update = datetime.fromisoformat(
                data["update"]
            )

        return contact


@dataclass
class InvoicePosition:
    """Invoice position/line item."""

    id: int | None = None
    object_name: str = "InvoicePos"
    quantity: float = 1.0
    price: float = 0.0
    name: str = ""
    unity: Unity = Unity.PIECE
    position_number: int | None = None
    text: str | None = None
    discount: float | None = None
    tax_rate: float = 19.0
    sum_discount: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for API requests."""
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
    positions: list[InvoicePosition] = None

    def __post_init__(self) -> None:
        self.object_name = "Invoice"
        if self.positions is None:
            self.positions = []

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

        # Dates
        if data.get("invoiceDate"):
            # Handle date string format
            invoice.invoice_date = datetime.strptime(data["invoiceDate"], "%d.%m.%Y")
        if data.get("deliveryDate"):
            invoice.delivery_date = datetime.strptime(data["deliveryDate"], "%d.%m.%Y")
        if data.get("deliveryDateUntil"):
            invoice.delivery_date_until = datetime.strptime(
                data["deliveryDateUntil"], "%d.%m.%Y"
            )

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
            invoice.tax_rule = TaxRule(data["taxRule"])
        invoice.tax_type = data.get("taxType")
        invoice.tax_rate = float(data.get("taxRate", 19.0))

        # Type
        if data.get("invoiceType"):
            invoice.invoice_type = InvoiceType(data["invoiceType"])

        # Timestamps
        if data.get("create"):
            invoice.create = datetime.fromisoformat(
                data["create"]
            )
        if data.get("update"):
            invoice.update = datetime.fromisoformat(
                data["update"]
            )

        return invoice


@dataclass
class CheckAccount(SevDeskObject):
    """Check account model."""

    name: str = ""
    type: CheckAccountType = CheckAccountType.OFFLINE
    currency: str = "EUR"
    status: CheckAccountStatus = CheckAccountStatus.ACTIVE
    import_type: str | None = None
    default_account: int | None = None
    bank_server: str | None = None
    auto_map_transactions: int | None = None

    def __post_init__(self) -> None:
        self.object_name = "CheckAccount"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for API requests."""
        data = super().to_dict()

        data["name"] = self.name
        data["type"] = self.type.value
        data["currency"] = self.currency
        data["status"] = self.status.value

        if self.import_type:
            data["importType"] = self.import_type
        if self.default_account is not None:
            data["defaultAccount"] = self.default_account
        if self.bank_server:
            data["bankServer"] = self.bank_server
        if self.auto_map_transactions is not None:
            data["autoMapTransactions"] = self.auto_map_transactions

        return data


@dataclass
class CheckAccountTransaction(SevDeskObject):
    """Check account transaction model."""

    value_date: datetime = None
    entry_date: datetime | None = None
    paymt_purpose: str | None = None
    amount: float = 0.0
    payee_payer_name: str | None = None
    check_account: CheckAccount | None = None
    status: TransactionStatus = TransactionStatus.UNPAID
    enshrined: bool = False
    source_transaction: dict[str, Any] | None = None
    target_transaction: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        self.object_name = "CheckAccountTransaction"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for API requests."""
        data = super().to_dict()

        if self.value_date:
            data["valueDate"] = self.value_date.strftime("%Y-%m-%d %H:%M:%S")
        if self.entry_date:
            data["entryDate"] = self.entry_date.strftime("%Y-%m-%d %H:%M:%S")
        if self.paymt_purpose:
            data["paymtPurpose"] = self.paymt_purpose
        data["amount"] = self.amount
        if self.payee_payer_name:
            data["payeePayerName"] = self.payee_payer_name
        if self.check_account:
            data["checkAccount"] = self.check_account.to_dict()
        data["status"] = self.status.value
        data["enshrined"] = self.enshrined

        if self.source_transaction:
            data["sourceTransaction"] = self.source_transaction
        if self.target_transaction:
            data["targetTransaction"] = self.target_transaction

        return data
