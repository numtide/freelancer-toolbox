"""SevDesk API client package."""

from .accounting_types import AccountingTypeOperations
from .api import SevDeskAPI
from .check_accounts import CheckAccountOperations
from .client import SevDeskClient, SevDeskError
from .contacts import ContactOperations
from .invoices import InvoiceOperations
from .models import (
    CheckAccount,
    CheckAccountStatus,
    CheckAccountTransaction,
    CheckAccountType,
    Contact,
    ContactCategory,
    Invoice,
    InvoicePosition,
    InvoiceStatus,
    InvoiceType,
    TaxRule,
    TransactionStatus,
    Unity,
)
from .transactions import TransactionOperations
from .vouchers import (
    CreditDebit,
    DocumentDownload,
    TaxType,
    VoucherOperations,
    VoucherPosition,
    VoucherStatus,
    VoucherType,
)

__all__ = [
    "AccountingTypeOperations",
    "CheckAccount",
    "CheckAccountOperations",
    "CheckAccountStatus",
    "CheckAccountTransaction",
    "CheckAccountType",
    "Contact",
    "ContactCategory",
    "ContactOperations",
    "CreditDebit",
    "DocumentDownload",
    "Invoice",
    "InvoiceOperations",
    "InvoicePosition",
    "InvoiceStatus",
    "InvoiceType",
    "SevDeskAPI",
    "SevDeskClient",
    "SevDeskError",
    "TaxRule",
    "TaxType",
    "TransactionOperations",
    "TransactionStatus",
    "Unity",
    "VoucherOperations",
    "VoucherPosition",
    "VoucherStatus",
    "VoucherType",
]
