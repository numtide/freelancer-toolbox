"""Tests for model.py: totals, VAT, formatting helpers."""

from __future__ import annotations

from datetime import date

import pytest
from harvest_invoicer.model import (
    Invoice,
    InvoiceLine,
    fmt_date,
    fmt_money,
    fmt_qty,
    fmt_vat_cell,
    merge_duplicate_lines,
)

# --------------------------------------------------------------------------
# InvoiceLine arithmetic
# --------------------------------------------------------------------------


def test_invoice_line_base() -> None:
    line = InvoiceLine(concept="Test", unit_price=100.0, quantity=8.0)
    assert line.base == pytest.approx(800.0)


def test_invoice_line_vat_zero() -> None:
    line = InvoiceLine(concept="Test", unit_price=100.0, quantity=8.0, vat_rate=0.0)
    assert line.vat == pytest.approx(0.0)
    assert line.total == pytest.approx(800.0)


def test_invoice_line_vat_nonzero() -> None:
    line = InvoiceLine(concept="Test", unit_price=100.0, quantity=8.0, vat_rate=0.21)
    assert line.vat == pytest.approx(168.0)
    assert line.total == pytest.approx(968.0)


# --------------------------------------------------------------------------
# Invoice totals
# --------------------------------------------------------------------------


def test_invoice_totals() -> None:
    lines = [
        InvoiceLine(concept="A", unit_price=100.0, quantity=5.0),
        InvoiceLine(concept="B", unit_price=50.0, quantity=2.0),
    ]
    inv = Invoice(
        number="2026-06",
        issue_date=date(2026, 7, 1),
        due_date=date(2026, 7, 16),
        lines=lines,
    )
    assert inv.subtotal == pytest.approx(600.0)
    assert inv.vat_total == pytest.approx(0.0)
    assert inv.grand_total == pytest.approx(600.0)


def test_invoice_no_legal_note_by_default() -> None:
    """legal_note defaults to None — ensures the template section is skipped."""
    inv = Invoice(
        number="2026-06",
        issue_date=date(2026, 7, 1),
        due_date=date(2026, 7, 16),
        lines=[InvoiceLine(concept="A", unit_price=10.0, quantity=1.0)],
    )
    assert inv.legal_note is None


# --------------------------------------------------------------------------
# Formatting helpers
# --------------------------------------------------------------------------


def test_fmt_money_default() -> None:
    assert fmt_money(1234.56) == "1,234.56"


def test_fmt_money_zero() -> None:
    assert fmt_money(0.0) == "0.00"


def test_fmt_qty() -> None:
    assert fmt_qty(40.0) == "40.00"


def test_fmt_date_iso_default() -> None:
    d = date(2026, 6, 1)
    assert fmt_date(d) == "2026-06-01"


def test_fmt_date_custom_format() -> None:
    """Custom date_format from issuer config is applied correctly."""
    d = date(2026, 6, 1)
    assert fmt_date(d, "%d/%m/%Y") == "01/06/2026"


def test_fmt_date_german_format() -> None:
    """German date format works without locale dependency."""
    d = date(2026, 6, 15)
    assert fmt_date(d, "%d.%m.%Y") == "15.06.2026"


def test_fmt_vat_cell_zero() -> None:
    line = InvoiceLine(concept="x", unit_price=100.0, quantity=1.0, vat_rate=0.0)
    result = fmt_vat_cell(line)
    assert "0%" in result


def test_fmt_vat_cell_nonzero() -> None:
    line = InvoiceLine(concept="x", unit_price=100.0, quantity=1.0, vat_rate=0.21)
    result = fmt_vat_cell(line)
    assert "21%" in result
    assert "21.00" in result


def test_merge_duplicates_preserves_extra_lines() -> None:
    """Extra-origin lines are never merged, even with identical fields."""
    lines = [
        InvoiceLine(concept="Dev", unit_price=100.0, quantity=10.0),
        InvoiceLine(concept="Dev", unit_price=100.0, quantity=5.0),
        InvoiceLine(concept="Dev", unit_price=100.0, quantity=1.0, origin="extra"),
    ]
    merged = merge_duplicate_lines(lines)
    assert len(merged) == 2
    harvest = [ln for ln in merged if ln.origin == "harvest"]
    extras = [ln for ln in merged if ln.origin == "extra"]
    assert harvest[0].quantity == 15.0
    assert extras[0].quantity == 1.0


def test_totals_match_displayed_line_amounts() -> None:
    """Per-line cents rounding: displayed lines must add up to the totals.

    1.005 stored as float is just below 1.005, so each line displays 1.00;
    an unrounded sum would show a 2.01 subtotal next to two 1.00 lines.
    """
    inv = Invoice(
        number="X",
        issue_date=date(2026, 6, 1),
        due_date=date(2026, 6, 15),
        lines=[
            InvoiceLine(concept="A", unit_price=1.005, quantity=1.0),
            InvoiceLine(concept="B", unit_price=1.005, quantity=1.0),
        ],
    )
    per_line = [fmt_money(round(line.base, 2)) for line in inv.lines]
    assert per_line == ["1.00", "1.00"]
    assert fmt_money(inv.subtotal) == "2.00"
    assert fmt_money(inv.grand_total) == "2.00"
