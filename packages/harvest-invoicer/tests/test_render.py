"""Tests for render.py: HTML render with fake issuer/client/lines."""

from __future__ import annotations

from datetime import date

from harvest_invoicer.model import Invoice, InvoiceLine
from harvest_invoicer.render import render_html


def _fake_issuer(**kwargs: object) -> dict[str, object]:
    base: dict[str, object] = {
        "name": "Jane Doe Consulting",
        "address_line1": "12 Example St",
        "address_line2": "10115 Berlin",
        "country": "Germany",
        "tax_id": "DE000000000",
        "tax_id_label": "VAT ID",
        "phone": "+49 30 0000",
        "email": "jane@example.com",
        "bank": {"iban": "DE00 0000 0000 0000 0000 00", "bic": "EXAMPLEXXX"},
    }
    base.update(kwargs)
    return base


def _fake_client(**kwargs: str) -> dict[str, str]:
    base: dict[str, str] = {
        "name": "Acme Corp Ltd.",
        "address_line1": "1 Acme Blvd",
        "address_line2": "EC1A 1BB London",
        "country": "United Kingdom",
        "tax_id": "GB000000000",
        "tax_id_label": "VAT No.",
    }
    base.update(kwargs)
    return base


def _fake_invoice(**kwargs: object) -> Invoice:
    lines = [
        InvoiceLine(concept="Backend Development", unit_price=120.0, quantity=40.0),
        InvoiceLine(concept="Code Review", unit_price=120.0, quantity=8.0),
    ]
    base: dict[str, object] = {
        "number": "2026-06",
        "issue_date": date(2026, 7, 1),
        "due_date": date(2026, 7, 16),
        "lines": lines,
    }
    base.update(kwargs)
    return Invoice(**base)  # type: ignore[arg-type]


class TestRenderHtml:
    def test_invoice_number_present(self) -> None:
        html = render_html(_fake_invoice(), _fake_issuer(), _fake_client())
        assert "2026-06" in html

    def test_grand_total_present(self) -> None:
        inv = _fake_invoice()
        html = render_html(inv, _fake_issuer(), _fake_client())
        assert f"{inv.grand_total:,.2f}" in html

    def test_client_name_present(self) -> None:
        html = render_html(_fake_invoice(), _fake_issuer(), _fake_client())
        assert "Acme Corp Ltd." in html

    def test_issuer_name_present(self) -> None:
        html = render_html(_fake_invoice(), _fake_issuer(), _fake_client())
        assert "Jane Doe Consulting" in html

    def test_no_legal_note_section_absent(self) -> None:
        """When legal_note is None, the legal-note paragraph must not appear."""
        inv = _fake_invoice(legal_note=None)
        html = render_html(inv, _fake_issuer(), _fake_client())
        assert 'class="legal-note"' not in html

    def test_legal_note_present_when_set(self) -> None:
        inv = _fake_invoice(legal_note="Payment within 30 days.")
        html = render_html(inv, _fake_issuer(), _fake_client())
        assert "Payment within 30 days." in html

    def test_custom_date_format(self) -> None:
        """date_format from issuer config is applied to rendered dates."""
        issuer = _fake_issuer(date_format="%d/%m/%Y")
        inv = _fake_invoice(issue_date=date(2026, 7, 1))
        html = render_html(inv, issuer, _fake_client())
        # Issued date should appear in day/month/year format
        assert "01/07/2026" in html

    def test_custom_tax_id_label(self) -> None:
        """tax_id_label from clients.json is rendered, not a hardcoded label."""
        client = _fake_client(tax_id_label="Steuernummer")
        html = render_html(_fake_invoice(), _fake_issuer(), client)
        assert "Steuernummer" in html
        assert "NIF" not in html

    def test_no_nif_literal(self) -> None:
        """The template must never emit the literal string NIF."""
        html = render_html(_fake_invoice(), _fake_issuer(), _fake_client())
        assert "NIF" not in html

    def test_default_number_scheme(self) -> None:
        """The invoice number YYYY-MM is used when no override is given."""
        inv = _fake_invoice(number="2026-06")
        html = render_html(inv, _fake_issuer(), _fake_client())
        assert "2026-06" in html

    def test_currency_code_in_html(self) -> None:
        """The ISO currency code appears in column headers and totals block."""
        inv = _fake_invoice(currency="USD")
        html = render_html(inv, _fake_issuer(), _fake_client())
        assert "USD" in html

    def test_period_shown_when_set(self) -> None:
        """The service period row appears when period dates are set."""
        inv = _fake_invoice(
            period_start=date(2026, 6, 1),
            period_end=date(2026, 6, 30),
        )
        html = render_html(inv, _fake_issuer(), _fake_client())
        assert "Period" in html
        assert "2026-06-01" in html
        assert "2026-06-30" in html

    def test_period_absent_when_unset(self) -> None:
        """No period row when the invoice has no period dates."""
        html = render_html(_fake_invoice(), _fake_issuer(), _fake_client())
        assert "Period" not in html

    def test_period_uses_issuer_date_format(self) -> None:
        """The period dates honor the issuer's date_format."""
        issuer = _fake_issuer(date_format="%d/%m/%Y")
        inv = _fake_invoice(
            period_start=date(2026, 6, 1),
            period_end=date(2026, 6, 30),
        )
        html = render_html(inv, issuer, _fake_client())
        assert "01/06/2026" in html
        assert "30/06/2026" in html
