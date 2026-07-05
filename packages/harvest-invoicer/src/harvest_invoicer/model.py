"""Data model: InvoiceLine, Invoice dataclasses and formatting helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import date

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------

DEFAULT_PAYMENT_TERM_DAYS: int = 15
COST_TOLERANCE: float = 0.01

REQUIRED_ISSUER_FIELDS: frozenset[str] = frozenset(
    {
        "name",
        "address_line1",
        "address_line2",
        "country",
        "tax_id",
        "phone",
        "email",
        "bank",
    }
)
REQUIRED_ISSUER_BANK_FIELDS: frozenset[str] = frozenset({"iban", "bic"})


# --------------------------------------------------------------------------
# Dataclasses
# --------------------------------------------------------------------------


@dataclass
class InvoiceLine:
    """A single billable line on the invoice."""

    concept: str
    unit_price: float
    quantity: float
    vat_rate: float = 0.0

    @property
    def base(self) -> float:
        """Line subtotal before VAT."""
        return self.unit_price * self.quantity

    @property
    def vat(self) -> float:
        """VAT amount for this line."""
        return self.base * self.vat_rate

    @property
    def total(self) -> float:
        """Line total including VAT."""
        return self.base + self.vat


@dataclass
class Invoice:
    """An invoice with lines and metadata.

    ``period_start`` / ``period_end`` describe the service period the
    invoice covers (the invoiced month).  When set, the rendered invoice
    shows a "Period" row so line totals are unambiguous.
    """

    number: str
    issue_date: date
    due_date: date
    lines: list[InvoiceLine] = field(default_factory=list)
    legal_note: str | None = None
    currency: str = "EUR"
    period_start: date | None = None
    period_end: date | None = None

    @property
    def subtotal(self) -> float:
        """Sum of all line bases (before VAT)."""
        return sum(line.base for line in self.lines)

    @property
    def vat_total(self) -> float:
        """Sum of all line VAT amounts."""
        return sum(line.vat for line in self.lines)

    @property
    def grand_total(self) -> float:
        """Total including VAT."""
        return self.subtotal + self.vat_total


# --------------------------------------------------------------------------
# Line transforms
# --------------------------------------------------------------------------


def merge_duplicate_lines(lines: list[InvoiceLine]) -> list[InvoiceLine]:
    """Collapse lines with identical concept, rate, and VAT into one.

    Harvest aggregation is per team member, so several people logging the
    same task at the same rate yield visually identical rows.  Quantities
    are summed; order of first occurrence is preserved.
    """
    grouped: dict[tuple[str, float, float], InvoiceLine] = {}
    for line in lines:
        key = (line.concept, line.unit_price, line.vat_rate)
        existing = grouped.get(key)
        if existing is None:
            grouped[key] = InvoiceLine(
                concept=line.concept,
                unit_price=line.unit_price,
                quantity=line.quantity,
                vat_rate=line.vat_rate,
            )
        else:
            existing.quantity = round(existing.quantity + line.quantity, 4)
    return list(grouped.values())


# --------------------------------------------------------------------------
# Formatting helpers
# --------------------------------------------------------------------------


def fmt_money(n: float) -> str:
    """Format a monetary value as 1,234.56 (English locale, comma thousands, period decimal)."""
    return f"{n:,.2f}"


def fmt_qty(n: float) -> str:
    """Format a quantity value (same style as fmt_money)."""
    return f"{n:,.2f}"


def fmt_date(d: date, date_format: str = "%Y-%m-%d") -> str:
    """Format a date using the supplied strftime pattern.

    The pattern comes from the issuer config ``date_format`` field.
    Default is ISO 8601 (``%Y-%m-%d``).
    """
    return d.strftime(date_format)


def fmt_vat_cell(line: InvoiceLine) -> str:
    """Render the VAT cell: amount and rate percentage."""
    if line.vat_rate == 0:
        return f"{fmt_money(0.0)} (0%)"
    return f"{fmt_money(line.vat)} ({line.vat_rate * 100:.0f}%)"
