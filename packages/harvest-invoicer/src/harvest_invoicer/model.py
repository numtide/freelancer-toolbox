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
    """A single billable line on the invoice.

    ``origin`` distinguishes where the line came from: ``"harvest"`` for
    imported time entries, ``"extra"`` for recurring lines configured per
    client settings.  Extra lines are never merged with Harvest
    lines and are re-added on every import.
    """

    concept: str
    unit_price: float
    quantity: float
    vat_rate: float = 0.0
    origin: str = "harvest"
    user: str | None = None  # Harvest user the hours belong to (provenance)

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
        """Sum of all line bases (before VAT).

        Each line is rounded to cents first — the invoice displays rounded
        per-line amounts, and those must add up exactly to the totals.
        """
        return sum(round(line.base, 2) for line in self.lines)

    @property
    def vat_total(self) -> float:
        """Sum of all line VAT amounts (each rounded to cents first)."""
        return sum(round(line.vat, 2) for line in self.lines)

    @property
    def grand_total(self) -> float:
        """Total including VAT."""
        return self.subtotal + self.vat_total


# --------------------------------------------------------------------------
# Line transforms
# --------------------------------------------------------------------------


def merge_duplicate_lines(lines: list[InvoiceLine]) -> list[InvoiceLine]:
    """Collapse Harvest lines with identical concept, rate, and VAT into one.

    Harvest aggregation is per team member, so several people logging the
    same task at the same rate yield visually identical rows.  Quantities
    are summed; order of first occurrence is preserved.  Lines with a
    non-Harvest origin (recurring extras) are never merged — each passes
    through unchanged.
    """
    result: list[InvoiceLine] = []
    grouped: dict[tuple[str, float, float], InvoiceLine] = {}
    for line in lines:
        if line.origin != "harvest":
            result.append(
                InvoiceLine(
                    concept=line.concept,
                    unit_price=line.unit_price,
                    quantity=line.quantity,
                    vat_rate=line.vat_rate,
                    origin=line.origin,
                )
            )
            continue
        key = (line.concept, line.unit_price, line.vat_rate)
        existing = grouped.get(key)
        if existing is None:
            merged = InvoiceLine(
                concept=line.concept,
                unit_price=line.unit_price,
                quantity=line.quantity,
                vat_rate=line.vat_rate,
                user=line.user,
            )
            grouped[key] = merged
            result.append(merged)
        else:
            existing.quantity = round(existing.quantity + line.quantity, 4)
            if existing.user != line.user:
                existing.user = None  # merged across people
    return result


# --------------------------------------------------------------------------
# Formatting helpers
# --------------------------------------------------------------------------


def fmt_money(n: float) -> str:
    """Format a monetary value as 1,234.56 (English locale, comma thousands, period decimal)."""
    # ``+ 0.0`` collapses a negative zero (a tiny negative that rounds to
    # 0.00) so an amount never prints as "-0.00".
    return f"{round(n, 2) + 0.0:,.2f}"


def fmt_qty(n: float) -> str:
    """Format a quantity value (same style as fmt_money)."""
    return f"{round(n, 2) + 0.0:,.2f}"


def fmt_date(d: date, date_format: str = "%Y-%m-%d") -> str:
    """Format a date using the supplied strftime pattern.

    The pattern comes from the issuer config ``date_format`` field.
    Default is ISO 8601 (``%Y-%m-%d``).
    """
    return d.strftime(date_format)


def fmt_rate_pct(rate: float) -> str:
    """Format a VAT rate as a percentage without spurious trailing zeros.

    Keeps fractional rates honest instead of rounding the label to a whole
    number: ``0.21`` -> ``"21"``, ``0.075`` -> ``"7.5"``, ``0.001`` ->
    ``"0.1"``.  (The amount was always exact; only the printed percent was
    being rounded, which produced legally wrong labels like ``7.50 (8%)``.)
    """
    return f"{rate * 100:.2f}".rstrip("0").rstrip(".")


def fmt_vat_cell(line: InvoiceLine) -> str:
    """Render the VAT cell: amount and rate percentage."""
    if line.vat_rate == 0:
        return f"{fmt_money(0.0)} (0%)"
    return f"{fmt_money(line.vat)} ({fmt_rate_pct(line.vat_rate)}%)"


def fmt_tax_label(override: object, lang: str) -> str:
    """Resolve the tax-ID label for *lang*.

    ``override`` is the issuer/client ``tax_id_label`` field, which may be:

    * a plain string — used verbatim in every language (e.g. a fixed
      "VAT No."), the historical behaviour; or
    * a per-language mapping such as ``{"en": "Tax ID", "es":
      "Identificador fiscal"}`` — the entry for *lang* is used, falling
      back to the English entry so a label set for one language never
      leaks into another.

    An absent or empty override falls back to the translated default
    (``t('tax_id')``), so a client with no override is still localized.
    """
    from collections.abc import Mapping  # noqa: PLC0415

    from harvest_invoicer.i18n import translator  # noqa: PLC0415

    if isinstance(override, Mapping):
        label = override.get(lang) or override.get("en")
        if label:
            return str(label)
    elif isinstance(override, str) and override:
        return override
    return translator(lang)("tax_id")
