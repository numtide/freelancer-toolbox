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
        if self.payee_payer_acct_no:
            data["payeePayerAcctNo"] = self.payee_payer_acct_no
        if self.payee_payer_bank_code:
            data["payeePayerBankCode"] = self.payee_payer_bank_code
        if self.gv_code:
            data["gvCode"] = self.gv_code
        if self.entry_text:
            data["entryText"] = self.entry_text
        if self.prima_nota_no:
            data["primaNotaNo"] = self.prima_nota_no
        if self.check_account:
            data["checkAccount"] = self.check_account.to_dict()
        data["status"] = self.status.value
        data["enshrined"] = self.enshrined

        if self.source_transaction:
            data["sourceTransaction"] = self.source_transaction
        if self.target_transaction:
            data["targetTransaction"] = self.target_transaction

        return data
