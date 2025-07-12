"""SevDesk API client package."""

from .api import SevDeskAPI
from .check_accounts import CheckAccountOperations
from .client import SevDeskClient, SevDeskError
from .contacts import ContactOperations
from .invoices import InvoiceOperations
from .models import (
    CheckAccount,
    CheckAccountTransaction,
    Contact,
    ContactCategory,
    Invoice,
    InvoicePosition,
    InvoiceStatus,
    InvoiceType,
    TaxRule,
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
    "CheckAccount",
    "CheckAccountOperations",
    "CheckAccountTransaction",
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
    "Unity",
    "VoucherOperations",
    "VoucherPosition",
    "VoucherStatus",
    "VoucherType",
]
