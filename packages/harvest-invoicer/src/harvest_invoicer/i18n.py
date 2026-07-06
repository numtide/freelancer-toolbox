"""Invoice-facing string translations.

Deliberately a plain dict rather than gettext: ~25 keys, few languages,
no extraction/compile step, and a key-parity test guarantees no language
misses a string.  The invoice language resolves per recipient:
``client.language`` > ``issuer.language`` > English.

Number and date formatting are intentionally NOT localized here: dates
follow the issuer's ``date_format`` and amounts keep one consistent
notation across all invoices (see the README).
"""

from __future__ import annotations

from collections.abc import Callable

TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        "invoice": "INVOICE",
        "invoice_word": "Invoice",
        "number": "No.",
        "issued": "Issued",
        "due": "Due",
        "period": "Period",
        "bill_to": "Bill to",
        "description": "Description",
        "unit_price": "Unit Price",
        "qty": "Qty",
        "subtotal": "Subtotal",
        "vat": "VAT",
        "total": "Total",
        "payment": "Payment",
        "payment_method": "Method",
        "bank_transfer": "Bank Transfer",
        "iban": "IBAN",
        "bic": "BIC / SWIFT",
        "account_holder": "Account Holder",
        "reference": "Reference",
        "tax_id": "Tax ID",
        "tel": "Tel.",
        "email": "Email",
        "page": "Page",
        "page_of": "of",
    },
    "es": {
        "invoice": "FACTURA",
        "invoice_word": "Factura",
        "number": "N.º",
        "issued": "Emitida",
        "due": "Vencimiento",
        "period": "Periodo",
        "bill_to": "Facturar a",
        "description": "Concepto",
        "unit_price": "Precio unit.",
        "qty": "Cant.",
        "subtotal": "Subtotal",
        "vat": "IVA",
        "total": "Total",
        "payment": "Pago",
        "payment_method": "Método",
        "bank_transfer": "Transferencia bancaria",
        "iban": "IBAN",
        "bic": "BIC / SWIFT",
        "account_holder": "Titular",
        "reference": "Referencia",
        "tax_id": "NIF",
        "tel": "Tel.",
        "email": "Email",
        "page": "Página",
        "page_of": "de",
    },
}

SUPPORTED_LANGUAGES: tuple[str, ...] = tuple(TRANSLATIONS)


def resolve_language(client: dict[str, str], issuer: dict[str, object]) -> str:
    """Invoice language: client wins, issuer is the default, else English."""
    lang = str(client.get("language") or issuer.get("language") or "en").strip().lower()
    return lang if lang in TRANSLATIONS else "en"


def translator(lang: str) -> Callable[[str], str]:
    """Return ``t(key)`` for *lang*, falling back to English, then the key."""
    table = TRANSLATIONS.get(lang, TRANSLATIONS["en"])
    english = TRANSLATIONS["en"]

    def t(key: str) -> str:
        return table.get(key, english.get(key, key))

    return t
