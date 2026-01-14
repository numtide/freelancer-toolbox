"""Tests for ExchangeRateStore class."""

import tempfile
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest

from ecbx.store import ExchangeRateStore


@pytest.fixture
def temp_db():
    """Create a temporary database file."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        yield f.name
    # Cleanup happens automatically when file goes out of scope


@pytest.fixture
def sample_xml_data():
    """Sample ECB XML data for testing."""
    return b"""<?xml version="1.0" encoding="UTF-8"?>
    <gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01"
                     xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">
        <gesmes:subject>Reference rates</gesmes:subject>
        <gesmes:Sender>
            <gesmes:name>European Central Bank</gesmes:name>
        </gesmes:Sender>
        <Cube>
            <Cube time="2024-01-05">
                <Cube currency="USD" rate="1.0955"/>
                <Cube currency="JPY" rate="157.89"/>
                <Cube currency="GBP" rate="0.85890"/>
            </Cube>
            <Cube time="2024-01-04">
                <Cube currency="USD" rate="1.0950"/>
                <Cube currency="JPY" rate="157.50"/>
                <Cube currency="GBP" rate="0.85850"/>
            </Cube>
        </Cube>
    </gesmes:Envelope>"""


class TestExchangeRateStore:
    """Test ExchangeRateStore class."""

    def test_init_with_custom_path(self, temp_db):
        """Test initialization with custom database path."""
        store = ExchangeRateStore(temp_db)
        assert store.db_path == Path(temp_db)
        store.close()

    @patch("ecbx.store.get_db_path")
    def test_init_with_default_path(self, mock_get_db_path):
        """Test initialization with default database path."""
        mock_path = Path("/tmp/test.db")
        mock_get_db_path.return_value = mock_path

        store = ExchangeRateStore()
        assert store.db_path == mock_path
        store.close()

    def test_check_tables_exist_empty_db(self, temp_db):
        """Test checking tables in empty database."""
        store = ExchangeRateStore(temp_db)
        assert not store._check_tables_exist()
        store.close()

    @patch("ecbx.store.fetch_ecb_data")
    @patch("ecbx.store.parse_ecb_xml")
    def test_initialize(self, mock_parse, mock_fetch, temp_db, sample_xml_data):
        """Test database initialization."""
        from ecbx.utils import parse_ecb_xml

        mock_fetch.return_value = sample_xml_data
        mock_parse.return_value = parse_ecb_xml(sample_xml_data)

        store = ExchangeRateStore(temp_db)
        rate_count, date_count = store.initialize()

        assert rate_count > 0
        assert date_count == 2
        assert store._check_tables_exist()

        # Check currencies were added
        currencies = store.list_currencies()
        assert "EUR" in currencies
        assert "USD" in currencies
        assert "JPY" in currencies
        assert "GBP" in currencies

        store.close()

    def test_get_rate_uninitialized_db(self, temp_db):
        """Test getting rate from uninitialized database."""
        store = ExchangeRateStore(temp_db)
        date, rate = store.get_rate("USD", "EUR")
        assert date is None
        assert rate is None
        store.close()

    @patch("ecbx.store.fetch_ecb_data")
    @patch("ecbx.store.parse_ecb_xml")
    def test_get_rate_exact_date(
        self, mock_parse, mock_fetch, temp_db, sample_xml_data
    ):
        """Test getting rate for exact date."""
        from ecbx.utils import parse_ecb_xml

        mock_fetch.return_value = sample_xml_data
        mock_parse.return_value = parse_ecb_xml(sample_xml_data)

        store = ExchangeRateStore(temp_db)
        store.initialize()

        # Test EUR to USD
        date, rate = store.get_rate("EUR", "USD", "2024-01-05")
        assert date == "2024-01-05"
        assert rate == Decimal("1.0955")

        # Test USD to EUR (inverse)
        date, rate = store.get_rate("USD", "EUR", "2024-01-05")
        assert date == "2024-01-05"
        assert abs(rate - (Decimal("1") / Decimal("1.0955"))) < Decimal("0.0001")

        store.close()

    @patch("ecbx.store.fetch_ecb_data")
    @patch("ecbx.store.parse_ecb_xml")
    def test_get_rate_latest(self, mock_parse, mock_fetch, temp_db, sample_xml_data):
        """Test getting latest rate."""
        from ecbx.utils import parse_ecb_xml

        mock_fetch.return_value = sample_xml_data
        mock_parse.return_value = parse_ecb_xml(sample_xml_data)

        store = ExchangeRateStore(temp_db)
        store.initialize()

        date, rate = store.get_rate("EUR", "USD", "latest")
        assert date == "2024-01-05"  # Latest date in sample data
        assert rate == Decimal("1.0955")

        store.close()

    @patch("ecbx.store.fetch_ecb_data")
    @patch("ecbx.store.parse_ecb_xml")
    def test_get_rate_closest_before(
        self, mock_parse, mock_fetch, temp_db, sample_xml_data
    ):
        """Test getting closest rate before a date."""
        from ecbx.utils import parse_ecb_xml

        mock_fetch.return_value = sample_xml_data
        mock_parse.return_value = parse_ecb_xml(sample_xml_data)

        store = ExchangeRateStore(temp_db)
        store.initialize()

        # Request date that doesn't exist
        date, rate = store.get_rate("EUR", "USD", "2024-01-06", closest_rate="before")
        assert date == "2024-01-05"  # Should get the previous date
        assert rate == Decimal("1.0955")

        store.close()

    @patch("ecbx.store.fetch_ecb_data")
    @patch("ecbx.store.parse_ecb_xml")
    def test_cross_rates(self, mock_parse, mock_fetch, temp_db, sample_xml_data):
        """Test cross-rate calculations."""
        from ecbx.utils import parse_ecb_xml

        mock_fetch.return_value = sample_xml_data
        mock_parse.return_value = parse_ecb_xml(sample_xml_data)

        store = ExchangeRateStore(temp_db)
        store.initialize()

        # Test USD to JPY (cross-rate)
        date, rate = store.get_rate("USD", "JPY", "2024-01-05")
        assert date == "2024-01-05"

        # Calculate expected cross-rate
        usd_rate = Decimal("1.0955")
        jpy_rate = Decimal("157.89")
        expected = jpy_rate / usd_rate

        assert abs(rate - expected) < Decimal("0.01")

        store.close()

    @patch("ecbx.store.fetch_ecb_data")
    @patch("ecbx.store.parse_ecb_xml")
    def test_get_stats(self, mock_parse, mock_fetch, temp_db, sample_xml_data):
        """Test getting database statistics."""
        from ecbx.utils import parse_ecb_xml

        mock_fetch.return_value = sample_xml_data
        mock_parse.return_value = parse_ecb_xml(sample_xml_data)

        store = ExchangeRateStore(temp_db)

        # Stats before initialization
        stats = store.get_stats()
        assert not stats["initialized"]
        assert stats["currency_count"] == 0
        assert stats["rate_count"] == 0

        # Initialize and check stats
        store.initialize()
        stats = store.get_stats()
        assert stats["initialized"]
        assert stats["last_updated"] == "2024-01-05"
        assert stats["currency_count"] == 4  # EUR, USD, JPY, GBP
        assert stats["rate_count"] > 0
        assert stats["date_range"] == ("2024-01-04", "2024-01-05")

        store.close()

    @patch("ecbx.store.fetch_ecb_data")
    def test_update_no_new_data(self, mock_fetch, temp_db):
        """Test update when no new data is available."""
        mock_fetch.return_value = None

        store = ExchangeRateStore(temp_db)
        rate_count, latest_date = store.update()

        assert rate_count == 0
        assert latest_date is None

        store.close()

    def test_list_currencies_empty_db(self, temp_db):
        """Test listing currencies from empty database."""
        store = ExchangeRateStore(temp_db)
        currencies = store.list_currencies()
        assert currencies == []
        store.close()

    def test_get_last_update_date_empty_db(self, temp_db):
        """Test getting last update date from empty database."""
        store = ExchangeRateStore(temp_db)
        date = store.get_last_update_date()
        assert date is None
        store.close()
