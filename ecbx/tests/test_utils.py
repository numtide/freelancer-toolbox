"""Tests for utils module."""

import xml.etree.ElementTree as ET
from datetime import datetime
from unittest.mock import Mock, patch

import pytest
import requests

from ecbx.utils import (
    fetch_ecb_data,
    format_date,
    get_available_dates,
    get_last_business_day,
    parse_date,
    parse_ecb_xml,
)


class TestGetLastBusinessDay:
    """Test get_last_business_day function."""

    def test_monday_returns_monday(self):
        """Monday should return itself."""
        monday = datetime(2024, 1, 1)  # Monday
        assert get_last_business_day(monday) == monday

    def test_friday_returns_friday(self):
        """Friday should return itself."""
        friday = datetime(2024, 1, 5)  # Friday
        assert get_last_business_day(friday) == friday

    def test_saturday_returns_friday(self):
        """Saturday should return previous Friday."""
        saturday = datetime(2024, 1, 6)  # Saturday
        expected = datetime(2024, 1, 5)  # Friday
        assert get_last_business_day(saturday) == expected

    def test_sunday_returns_friday(self):
        """Sunday should return previous Friday."""
        sunday = datetime(2024, 1, 7)  # Sunday
        expected = datetime(2024, 1, 5)  # Friday
        assert get_last_business_day(sunday) == expected


class TestFetchEcbData:
    """Test fetch_ecb_data function."""

    @patch("ecbx.utils.requests.get")
    def test_successful_fetch(self, mock_get):
        """Test successful data fetch."""
        mock_response = Mock()
        mock_response.content = b"<xml>test data</xml>"
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        result = fetch_ecb_data("http://test.url")
        assert result == b"<xml>test data</xml>"
        mock_get.assert_called_once_with("http://test.url")

    @patch("ecbx.utils.requests.get")
    @patch("ecbx.utils.console")
    def test_request_exception(self, mock_console, mock_get):
        """Test handling of request exceptions."""
        mock_get.side_effect = requests.exceptions.RequestException("Network error")

        result = fetch_ecb_data("http://test.url")
        assert result is None
        mock_console.print.assert_called_once()

    @patch("ecbx.utils.requests.get")
    @patch("ecbx.utils.console")
    def test_http_error(self, mock_console, mock_get):
        """Test handling of HTTP errors."""
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("404")
        mock_get.return_value = mock_response

        result = fetch_ecb_data("http://test.url")
        assert result is None
        mock_console.print.assert_called_once()


class TestParseEcbXml:
    """Test parse_ecb_xml function."""

    def test_valid_xml(self):
        """Test parsing valid XML."""
        xml_data = b"<root><child>test</child></root>"
        result = parse_ecb_xml(xml_data)
        assert result is not None
        assert result.tag == "root"
        assert result.find("child").text == "test"

    @patch("ecbx.utils.console")
    def test_invalid_xml(self, mock_console):
        """Test handling of invalid XML."""
        xml_data = b"<invalid xml"
        result = parse_ecb_xml(xml_data)
        assert result is None
        mock_console.print.assert_called_once()


class TestGetAvailableDates:
    """Test get_available_dates function."""

    def test_extract_dates_from_xml(self):
        """Test extracting dates from ECB XML structure."""
        xml_string = """
        <gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01"
                         xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">
            <Cube>
                <Cube time="2024-01-05">
                    <Cube currency="USD" rate="1.0955"/>
                </Cube>
                <Cube time="2024-01-04">
                    <Cube currency="USD" rate="1.0950"/>
                </Cube>
                <Cube time="2024-01-03">
                    <Cube currency="USD" rate="1.0945"/>
                </Cube>
            </Cube>
        </gesmes:Envelope>
        """
        root = ET.fromstring(xml_string)
        dates = get_available_dates(root)
        assert dates == ["2024-01-05", "2024-01-04", "2024-01-03"]

    def test_empty_xml(self):
        """Test with XML containing no dates."""
        xml_string = "<root></root>"
        root = ET.fromstring(xml_string)
        dates = get_available_dates(root)
        assert dates == []


class TestFormatDate:
    """Test format_date function."""

    def test_already_formatted_date(self):
        """Test date already in correct format."""
        assert format_date("2024-01-15") == "2024-01-15"

    def test_compact_date_format(self):
        """Test converting compact date format."""
        assert format_date("20240115") == "2024-01-15"

    def test_none_input(self):
        """Test None input."""
        assert format_date(None) is None

    def test_empty_string(self):
        """Test empty string."""
        assert format_date("") is None

    def test_short_string(self):
        """Test string too short to be a date."""
        assert format_date("2024") == "2024"


class TestParseDate:
    """Test parse_date function."""

    def test_valid_date_string(self):
        """Test parsing valid date string."""
        result = parse_date("2024-01-15")
        assert result == datetime(2024, 1, 15)

    def test_compact_date_format(self):
        """Test parsing compact date format."""
        result = parse_date("20240115")
        assert result == datetime(2024, 1, 15)

    def test_none_input(self):
        """Test None input."""
        assert parse_date(None) is None

    def test_empty_string(self):
        """Test empty string."""
        assert parse_date("") is None

    @patch("ecbx.utils.console")
    def test_invalid_date_format(self, mock_console):
        """Test invalid date format."""
        result = parse_date("invalid-date")
        assert result is None
        mock_console.print.assert_called_once()

    @patch("ecbx.utils.console")
    def test_invalid_date_values(self, mock_console):
        """Test invalid date values."""
        result = parse_date("2024-13-45")  # Invalid month and day
        assert result is None
        mock_console.print.assert_called_once()