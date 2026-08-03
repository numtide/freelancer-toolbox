"""Tests for invoice i18n: key parity, resolution, rendered output."""

from __future__ import annotations

from datetime import date

from harvest_invoicer.i18n import (
    SUPPORTED_LANGUAGES,
    TRANSLATIONS,
    resolve_language,
    translator,
)
from harvest_invoicer.model import Invoice, InvoiceLine, fmt_tax_label
from harvest_invoicer.render import render_html


def _issuer(**kw: object) -> dict[str, object]:
    base: dict[str, object] = {
        "name": "Jane",
        "address_line1": "A",
        "address_line2": "B",
        "country": "C",
        "tax_id": "T",
        "phone": "P",
        "email": "e@x.y",
        "bank": {"iban": "I", "bic": "B"},
    }
    base.update(kw)
    return base


def _client(**kw: str) -> dict[str, str]:
    base: dict[str, str] = {
        "name": "Acme",
        "address_line1": "1",
        "address_line2": "2",
        "country": "UK",
        "tax_id": "G",
    }
    base.update(kw)
    return base


def _invoice() -> Invoice:
    return Invoice(
        number="2026-06",
        issue_date=date(2026, 7, 1),
        due_date=date(2026, 7, 16),
        lines=[InvoiceLine(concept="Dev", unit_price=100.0, quantity=10.0)],
    )


def test_all_languages_have_identical_keys() -> None:
    """Key parity: no language may miss (or invent) a string."""
    english = set(TRANSLATIONS["en"])
    for lang, table in TRANSLATIONS.items():
        assert set(table) == english, f"key mismatch in '{lang}'"


def test_supported_languages_match_tables() -> None:
    assert set(SUPPORTED_LANGUAGES) == set(TRANSLATIONS)


def test_translator_falls_back_to_english_then_key() -> None:
    t = translator("es")
    assert t("invoice") == "FACTURA"
    assert t("nonexistent-key") == "nonexistent-key"
    t_unknown = translator("fr")
    assert t_unknown("invoice") == "INVOICE"


def test_resolution_precedence() -> None:
    assert resolve_language(_client(language="es"), _issuer(language="en")) == "es"
    assert resolve_language(_client(), _issuer(language="es")) == "es"
    assert resolve_language(_client(), _issuer()) == "en"
    # Unknown languages degrade to English rather than erroring
    assert resolve_language(_client(language="xx"), _issuer()) == "en"


def test_spanish_invoice_renders_spanish() -> None:
    html = render_html(_invoice(), _issuer(), _client(language="es"))
    assert "FACTURA" in html
    assert "Facturar a" in html
    assert "IVA" in html
    assert "Transferencia bancaria" in html
    assert "Página" in html  # localized page footer
    assert "Bill to" not in html


def test_english_invoice_unchanged() -> None:
    html = render_html(_invoice(), _issuer(), _client())
    assert "INVOICE" in html
    assert "Bill to" in html
    assert "Bank Transfer" in html
    assert '"Page "' in html  # footer override in English
    assert "FACTURA" not in html


def test_issuer_language_is_the_default() -> None:
    html = render_html(_invoice(), _issuer(language="es"), _client())
    assert "FACTURA" in html


def test_tax_id_label_still_wins_over_translation() -> None:
    html = render_html(
        _invoice(),
        _issuer(),
        _client(language="es", tax_id_label="Identificador fiscal"),
    )
    assert "Identificador fiscal" in html


def test_html_lang_attribute_matches_invoice_language() -> None:
    """The <html lang> attribute follows the resolved invoice language."""
    es = render_html(_invoice(), _issuer(), _client(language="es"))
    assert '<html lang="es">' in es
    en = render_html(_invoice(), _issuer(), _client())
    assert '<html lang="en">' in en


def test_tax_id_label_map_localizes_per_language() -> None:
    """A per-language tax_id_label map picks the entry for the invoice language."""
    label_map = {"es": "Identificador fiscal", "en": "Tax reference"}
    es = render_html(
        _invoice(), _issuer(), _client(language="es", tax_id_label=label_map)
    )
    assert "Identificador fiscal" in es
    assert "Tax reference" not in es
    # The Spanish override must NOT leak into an English invoice.
    en = render_html(_invoice(), _issuer(), _client(tax_id_label=label_map))
    assert "Tax reference" in en
    assert "Identificador fiscal" not in en


def test_fmt_tax_label_resolution() -> None:
    # Plain string: verbatim in every language (backwards compatible).
    assert fmt_tax_label("Steuernummer", "es") == "Steuernummer"
    # Map: exact language wins, English is the fallback for a missing entry.
    label_map = {"es": "Identificador fiscal", "en": "Tax reference"}
    assert fmt_tax_label(label_map, "es") == "Identificador fiscal"
    assert fmt_tax_label(label_map, "en") == "Tax reference"
    assert fmt_tax_label(label_map, "fr") == "Tax reference"
    # Empty / absent override falls back to the translated default.
    assert fmt_tax_label("", "es") == translator("es")("tax_id")
    assert fmt_tax_label({}, "es") == translator("es")("tax_id")
