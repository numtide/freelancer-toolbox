"""Check account models and related enums for SevDesk API."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

from .base import SevDeskObject

if TYPE_CHECKING:
    from datetime import datetime


class CheckAccountType(Enum):
    """Check account types."""

    OFFLINE = "offline"  # Clearing account
    ONLINE = "online"  # Bank account
    REGISTER = "register"  # Cash register


class CheckAccountStatus(Enum):
    """Check account status."""

    ARCHIVED = 0
    ACTIVE = 100


class TransactionStatus(Enum):
    """Transaction status."""

    CREATED = 100
    LINKED = 200
    PRIVATE = 300
    AUTO_BOOKED = 350
    BOOKED = 400


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
    iban: str | None = None

    def __post_init__(self) -> None:
        """Set object name after initialization."""
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
        if self.iban:
            data["iban"] = self.iban

        return data


@dataclass
class CheckAccountTransaction(SevDeskObject):
    """Check account transaction model."""

    value_date: datetime | None = None
    entry_date: datetime | None = None
    paymt_purpose: str | None = None
    amount: float = 0.0
    payee_payer_name: str | None = None
    payee_payer_acct_no: str | None = None
    payee_payer_bank_code: str | None = None
    gv_code: str | None = None
    entry_text: str | None = None
    prima_nota_no: str | None = None
    check_account: CheckAccount | None = None
    status: TransactionStatus = TransactionStatus.CREATED
    enshrined: bool = False
    source_transaction: dict[str, Any] | None = None
    target_transaction: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        """Set object name after initialization."""
        self.object_name = "CheckAccountTransaction"

    def _add_optional_fields(self, data: dict[str, Any]) -> None:
        """Add optional fields to the data dict."""
        field_mapping = {
            "paymt_purpose": "paymtPurpose",
            "payee_payer_name": "payeePayerName",
            "payee_payer_acct_no": "payeePayerAcctNo",
            "payee_payer_bank_code": "payeePayerBankCode",
            "gv_code": "gvCode",
            "entry_text": "entryText",
            "prima_nota_no": "primaNotaNo",
            "source_transaction": "sourceTransaction",
            "target_transaction": "targetTransaction",
        }

        for attr, key in field_mapping.items():
            value = getattr(self, attr, None)
            if value is not None:
                data[key] = value

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for API requests."""
        data = super().to_dict()

        # Handle date fields
        if self.value_date:
            data["valueDate"] = self.value_date.strftime("%Y-%m-%d %H:%M:%S")
        if self.entry_date:
            data["entryDate"] = self.entry_date.strftime("%Y-%m-%d %H:%M:%S")

        # Required fields
        data["amount"] = self.amount
        data["status"] = self.status.value
        data["enshrined"] = self.enshrined

        # Handle nested object
        if self.check_account:
            data["checkAccount"] = self.check_account.to_dict()

        # Add optional fields
        self._add_optional_fields(data)

        return data
