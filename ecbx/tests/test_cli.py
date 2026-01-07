"""Tests for CLI commands."""

import json
import tempfile
from decimal import Decimal
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from ecbx.cli import cli
from ecbx.store import ExchangeRateStore


@pytest.fixture
def runner():
    """Create a Click test runner."""
    return CliRunner()


@pytest.fixture
def temp_db():
    """Create a temporary database file."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        yield f.name


@pytest.fixture
def sample_xml_data():
    """Sample ECB XML data for testing."""
    return b"""<?xml version="1.0" encoding="UTF-8"?>
    <gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01"
                     xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">
        <Cube>
            <Cube time="2024-01-05">
                <Cube currency="USD" rate="1.0955"/>
                <Cube currency="JPY" rate="157.89"/>
                <Cube currency="GBP" rate="0.85890"/>
            </Cube>
        </Cube>
    </gesmes:Envelope>"""


class TestCLI:
    """Test CLI commands."""

    def test_cli_help(self, runner):
        """Test CLI help command."""
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "Tool for fetching and querying exchange rates" in result.output

    @patch("ecbx.store.fetch_ecb_data")
    @patch("ecbx.store.parse_ecb_xml")
    def test_initialize_command(self, mock_parse, mock_fetch, runner, temp_db, sample_xml_data):
        """Test initialize command."""
        from ecbx.utils import parse_ecb_xml
        
        mock_fetch.return_value = sample_xml_data
        mock_parse.return_value = parse_ecb_xml(sample_xml_data)
        
        result = runner.invoke(cli, ["--db", temp_db, "initialize"])
        assert result.exit_code == 0
        assert "Initialized with" in result.output

    def test_status_uninitialized(self, runner, temp_db):
        """Test status command on uninitialized database."""
        result = runner.invoke(cli, ["--db", temp_db, "status"])
        assert result.exit_code == 0
        assert "Database not initialized" in result.output

    @patch("ecbx.store.fetch_ecb_data")
    @patch("ecbx.store.parse_ecb_xml")
    def test_status_initialized(self, mock_parse, mock_fetch, runner, temp_db, sample_xml_data):
        """Test status command on initialized database."""
        from ecbx.utils import parse_ecb_xml
        
        mock_fetch.return_value = sample_xml_data
        mock_parse.return_value = parse_ecb_xml(sample_xml_data)
        
        # Initialize first
        runner.invoke(cli, ["--db", temp_db, "initialize"])
        
        # Check status
        result = runner.invoke(cli, ["--db", temp_db, "status"])
        assert result.exit_code == 0
        assert "Exchange Rate Database Status" in result.output
        assert "Last Updated" in result.output
        assert "Currencies" in result.output

    @patch("ecbx.store.fetch_ecb_data")
    @patch("ecbx.store.parse_ecb_xml")
    def test_status_verbose(self, mock_parse, mock_fetch, runner, temp_db, sample_xml_data):
        """Test status command with verbose flag."""
        from ecbx.utils import parse_ecb_xml
        
        mock_fetch.return_value = sample_xml_data
        mock_parse.return_value = parse_ecb_xml(sample_xml_data)
        
        # Initialize first
        runner.invoke(cli, ["--db", temp_db, "initialize"])
        
        # Check verbose status
        result = runner.invoke(cli, ["--db", temp_db, "--verbose", "status"])
        assert result.exit_code == 0
        assert "Available Currencies:" in result.output
        assert "USD" in result.output

    @patch("ecbx.store.fetch_ecb_data")
    @patch("ecbx.store.parse_ecb_xml")
    def test_convert_command(self, mock_parse, mock_fetch, runner, temp_db, sample_xml_data):
        """Test convert command."""
        from ecbx.utils import parse_ecb_xml
        
        mock_fetch.return_value = sample_xml_data
        mock_parse.return_value = parse_ecb_xml(sample_xml_data)
        
        # Initialize first
        runner.invoke(cli, ["--db", temp_db, "initialize"])
        
        # Test conversion
        result = runner.invoke(cli, ["--db", temp_db, "convert", "EUR", "USD", "100"])
        assert result.exit_code == 0
        assert "ECB Exchange Rate" in result.output
        assert "100.00 EUR" in result.output

    @patch("ecbx.store.fetch_ecb_data")
    @patch("ecbx.store.parse_ecb_xml")
    def test_convert_with_date(self, mock_parse, mock_fetch, runner, temp_db, sample_xml_data):
        """Test convert command with specific date."""
        from ecbx.utils import parse_ecb_xml
        
        mock_fetch.return_value = sample_xml_data
        mock_parse.return_value = parse_ecb_xml(sample_xml_data)
        
        # Initialize first
        runner.invoke(cli, ["--db", temp_db, "initialize"])
        
        # Test conversion with date
        result = runner.invoke(cli, ["--db", temp_db, "convert", "2024-01-05", "EUR", "USD"])
        assert result.exit_code == 0
        assert "2024-01-05" in result.output

    def test_convert_uninitialized(self, runner, temp_db):
        """Test convert command on uninitialized database."""
        result = runner.invoke(cli, ["--db", temp_db, "convert", "EUR", "USD"])
        assert result.exit_code == 0
        assert "Database not initialized" in result.output

    @patch("ecbx.store.fetch_ecb_data")
    @patch("ecbx.store.parse_ecb_xml")
    def test_currencies_command(self, mock_parse, mock_fetch, runner, temp_db, sample_xml_data):
        """Test currencies command."""
        from ecbx.utils import parse_ecb_xml
        
        mock_fetch.return_value = sample_xml_data
        mock_parse.return_value = parse_ecb_xml(sample_xml_data)
        
        # Initialize first
        runner.invoke(cli, ["--db", temp_db, "initialize"])
        
        # List currencies
        result = runner.invoke(cli, ["--db", temp_db, "currencies"])
        assert result.exit_code == 0
        assert "Available Currencies" in result.output
        assert "USD" in result.output
        assert "EUR" in result.output

    @patch("ecbx.store.fetch_ecb_data")
    @patch("ecbx.store.parse_ecb_xml")
    def test_rates_command(self, mock_parse, mock_fetch, runner, temp_db, sample_xml_data):
        """Test rates command."""
        from ecbx.utils import parse_ecb_xml
        
        mock_fetch.return_value = sample_xml_data
        mock_parse.return_value = parse_ecb_xml(sample_xml_data)
        
        # Initialize first
        runner.invoke(cli, ["--db", temp_db, "initialize"])
        
        # Show rates
        result = runner.invoke(cli, ["--db", temp_db, "rates"])
        assert result.exit_code == 0
        assert "Exchange Rates for" in result.output
        assert "USD" in result.output

    @patch("ecbx.store.fetch_ecb_data")
    @patch("ecbx.store.parse_ecb_xml")
    def test_matrix_command_text(self, mock_parse, mock_fetch, runner, temp_db, sample_xml_data):
        """Test matrix command with text output."""
        from ecbx.utils import parse_ecb_xml
        
        mock_fetch.return_value = sample_xml_data
        mock_parse.return_value = parse_ecb_xml(sample_xml_data)
        
        # Initialize first
        runner.invoke(cli, ["--db", temp_db, "initialize"])
        
        # Show matrix
        result = runner.invoke(cli, ["--db", temp_db, "matrix", "EUR"])
        assert result.exit_code == 0
        assert "Exchange Rates for EUR" in result.output

    @patch("ecbx.store.fetch_ecb_data")
    @patch("ecbx.store.parse_ecb_xml")
    def test_matrix_command_json(self, mock_parse, mock_fetch, runner, temp_db, sample_xml_data):
        """Test matrix command with JSON output."""
        from ecbx.utils import parse_ecb_xml
        
        mock_fetch.return_value = sample_xml_data
        mock_parse.return_value = parse_ecb_xml(sample_xml_data)
        
        # Initialize first
        runner.invoke(cli, ["--db", temp_db, "initialize"])
        
        # Show matrix as JSON
        result = runner.invoke(cli, ["--db", temp_db, "matrix", "--format", "json", "EUR"])
        assert result.exit_code == 0
        
        # Parse JSON output
        output_json = json.loads(result.output)
        assert output_json["base"] == "EUR"
        assert "rates" in output_json
        assert "USD" in output_json["rates"]

    @patch("ecbx.store.fetch_ecb_data")
    def test_update_command(self, mock_fetch, runner, temp_db):
        """Test update command."""
        # Mock empty response (no new data)
        mock_fetch.return_value = b"""<?xml version="1.0" encoding="UTF-8"?>
        <gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01"
                         xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">
            <Cube></Cube>
        </gesmes:Envelope>"""
        
        result = runner.invoke(cli, ["--db", temp_db, "update"])
        assert result.exit_code == 0
        assert "No new rates to update" in result.output

    def test_validate_date_callback(self, runner, temp_db):
        """Test date validation in CLI."""
        result = runner.invoke(cli, ["--db", temp_db, "convert", "invalid-date", "EUR", "USD"])
        assert result.exit_code != 0
        assert "Invalid date format" in result.output

    def test_validate_date_compact_format(self, runner, temp_db):
        """Test compact date format support."""
        # This should not fail on date validation
        result = runner.invoke(cli, ["--db", temp_db, "convert", "20240105", "EUR", "USD"])
        # Will fail because DB not initialized, but not because of date format
        assert "Database not initialized" in result.output