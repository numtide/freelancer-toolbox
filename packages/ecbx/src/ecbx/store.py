"""Exchange rate storage and retrieval."""

import os
import sqlite3
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from .constants import AFTER, BEFORE, CLOSEST, ECB_NAMESPACE, ECB_URL_90D, ECB_URL_HIST
from .utils import console, fetch_ecb_data, parse_ecb_xml


def get_db_path() -> Path:
    """Get the database path using XDG standard."""
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    config_base = Path(xdg_config_home) if xdg_config_home else Path.home() / ".config"

    config_dir = config_base / "ecbx"
    config_dir.mkdir(parents=True, exist_ok=True)

    return config_dir / "rates.db"


class ExchangeRateStore:
    """
    A class to manage the storage and retrieval of exchange rates.
    """

    def __init__(self, db_path: str | None = None) -> None:
        """
        Initialize the exchange rate store.

        Args:
            db_path: Optional custom path to the database file.
        """
        if db_path is None:
            self.db_path = get_db_path()
        else:
            self.db_path = Path(db_path)

        self._initialize_connection()

    def _initialize_connection(self) -> None:
        """Initialize the database connection."""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.execute("PRAGMA foreign_keys = ON")
        # Set up proper decimal handling
        sqlite3.register_adapter(Decimal, str)
        sqlite3.register_converter("DECIMAL", lambda s: Decimal(s.decode("utf-8")))
        self.conn.row_factory = sqlite3.Row

    def _check_tables_exist(self) -> bool:
        """Check if the necessary tables exist in the database."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='rates'"
        )
        return cursor.fetchone() is not None

    def close(self) -> None:
        """Close the database connection."""
        if hasattr(self, "conn") and self.conn:
            self.conn.close()

    def initialize(self) -> tuple[int, int]:
        """
        Initialize the database, creating tables and importing historical data.

        Returns:
            Tuple of (rate_count, date_count) added to the database.
        """
        cursor = self.conn.cursor()

        # Create tables if they don't exist
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS currencies (
            code TEXT PRIMARY KEY,
            name TEXT
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS rates (
            date TEXT,
            base_currency TEXT,
            target_currency TEXT,
            rate DECIMAL(20, 10) NOT NULL,
            PRIMARY KEY (date, base_currency, target_currency)
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """)

        # Insert EUR as base currency
        cursor.execute(
            "INSERT OR IGNORE INTO currencies (code, name) VALUES (?, ?)",
            ("EUR", "Euro"),
        )

        # Fetch and parse historical data
        xml_data = fetch_ecb_data(ECB_URL_HIST)
        if xml_data is None:
            return (0, 0)

        root = parse_ecb_xml(xml_data)
        if root is None:
            return (0, 0)

        # Process all dates and rates
        rate_count = 0
        dates: set[str] = set()

        for date_node in root.findall(".//ns:Cube[@time]", ECB_NAMESPACE):
            date_str = date_node.attrib.get("time")
            if date_str is None:
                continue
            dates.add(date_str)

            # Insert rates for this date
            for currency_node in date_node.findall(
                ".//ns:Cube[@currency]", ECB_NAMESPACE
            ):
                currency = currency_node.attrib.get("currency")
                rate_str = currency_node.attrib.get("rate")
                if currency is None or rate_str is None:
                    continue
                rate = Decimal(rate_str)

                # EUR to target currency
                cursor.execute(
                    """
                INSERT OR REPLACE INTO rates (date, base_currency, target_currency, rate)
                VALUES (?, ?, ?, ?)
                """,
                    (date_str, "EUR", currency, rate),
                )

                # Target currency to EUR (inverse rate)
                cursor.execute(
                    """
                INSERT OR REPLACE INTO rates (date, base_currency, target_currency, rate)
                VALUES (?, ?, ?, ?)
                """,
                    (date_str, currency, "EUR", Decimal(1) / rate),
                )

                # Add the currency to the currencies table
                cursor.execute(
                    "INSERT OR IGNORE INTO currencies (code) VALUES (?)", (currency,)
                )

                rate_count += 2  # Counting both directions

        # Store the latest update date
        if dates:
            latest_date = max(dates)
            cursor.execute(
                """
            INSERT OR REPLACE INTO metadata (key, value)
            VALUES ('last_updated', ?)
            """,
                (latest_date,),
            )

            # Calculate cross-rates for all dates
            for date_str in dates:
                rate_count += self._calculate_cross_rates(date_str)

        self.conn.commit()
        return (rate_count, len(dates))

    def get_last_update_date(self) -> str | None:
        """
        Get the date of the last update.

        Returns:
            The date string of the last update, or None if not available.
        """
        if not self._check_tables_exist():
            return None

        cursor = self.conn.cursor()
        cursor.execute("SELECT value FROM metadata WHERE key = 'last_updated'")
        row = cursor.fetchone()

        if row:
            return str(row[0])
        return None

    def update(self) -> tuple[int, str | None]:
        """
        Update the database with the latest exchange rates.

        Returns:
            Tuple of (rate_count, latest_date) added to the database.
        """
        if not self._check_tables_exist():
            console.print(
                "[yellow]Database not initialized. Running initialization...[/yellow]"
            )
            rates, _ = self.initialize()
            return (rates, self.get_last_update_date())

        # Fetch the latest data
        xml_data = fetch_ecb_data(ECB_URL_90D)
        if xml_data is None:
            return (0, None)

        root = parse_ecb_xml(xml_data)
        if root is None:
            return (0, None)

        # Get the last update date
        last_update = self.get_last_update_date()

        cursor = self.conn.cursor()
        rate_count = 0
        latest_date: str | None = None

        for date_node in root.findall(".//ns:Cube[@time]", ECB_NAMESPACE):
            date_str = date_node.attrib.get("time")
            if date_str is None:
                continue

            # Skip if we already have this date
            if last_update and date_str <= last_update:
                continue

            if latest_date is None or date_str > latest_date:
                latest_date = date_str

            # Insert rates for this date
            for currency_node in date_node.findall(
                ".//ns:Cube[@currency]", ECB_NAMESPACE
            ):
                currency = currency_node.attrib.get("currency")
                rate_str = currency_node.attrib.get("rate")
                if currency is None or rate_str is None:
                    continue
                rate = Decimal(rate_str)

                # EUR to target currency
                cursor.execute(
                    """
                INSERT OR REPLACE INTO rates (date, base_currency, target_currency, rate)
                VALUES (?, ?, ?, ?)
                """,
                    (date_str, "EUR", currency, rate),
                )

                # Target currency to EUR (inverse rate)
                cursor.execute(
                    """
                INSERT OR REPLACE INTO rates (date, base_currency, target_currency, rate)
                VALUES (?, ?, ?, ?)
                """,
                    (date_str, currency, "EUR", Decimal(1) / rate),
                )

                # Add the currency to the currencies table
                cursor.execute(
                    "INSERT OR IGNORE INTO currencies (code) VALUES (?)", (currency,)
                )

                rate_count += 2  # Counting both directions

        # Calculate all cross-rates for this date
        if latest_date:
            rate_count += self._calculate_cross_rates(latest_date)

            # Update the latest update date
            cursor.execute(
                """
            INSERT OR REPLACE INTO metadata (key, value)
            VALUES ('last_updated', ?)
            """,
                (latest_date,),
            )

        self.conn.commit()
        return (rate_count, latest_date)

    def _calculate_cross_rates(self, date_str: str) -> int:
        """
        Calculate cross-rates between all currency pairs.

        Args:
            date_str: The date to calculate cross-rates for.

        Returns:
            Number of cross-rates calculated.
        """
        cursor = self.conn.cursor()

        # Get all currencies that have rates against EUR for this date
        cursor.execute(
            """
        SELECT DISTINCT target_currency
        FROM rates
        WHERE date = ? AND base_currency = 'EUR'
        """,
            (date_str,),
        )

        currencies = [row[0] for row in cursor.fetchall()]
        count = 0

        # Calculate cross-rates for all currency pairs
        for base in currencies:
            if base == "EUR":
                continue

            # Get the rate from base to EUR
            cursor.execute(
                """
            SELECT rate
            FROM rates
            WHERE date = ? AND base_currency = ? AND target_currency = 'EUR'
            """,
                (date_str, base),
            )

            base_to_eur_row = cursor.fetchone()
            if not base_to_eur_row:
                continue

            base_to_eur_rate = Decimal(str(base_to_eur_row[0]))

            for target in currencies:
                if target in {"EUR", base}:
                    continue

                # Get the rate from EUR to target
                cursor.execute(
                    """
                SELECT rate
                FROM rates
                WHERE date = ? AND base_currency = 'EUR' AND target_currency = ?
                """,
                    (date_str, target),
                )

                eur_to_target_row = cursor.fetchone()
                if not eur_to_target_row:
                    continue

                eur_to_target_rate = Decimal(str(eur_to_target_row[0]))

                # Calculate the cross-rate
                cross_rate = eur_to_target_rate * base_to_eur_rate

                # Insert the cross-rate
                cursor.execute(
                    """
                INSERT OR REPLACE INTO rates (date, base_currency, target_currency, rate)
                VALUES (?, ?, ?, ?)
                """,
                    (date_str, base, target, cross_rate),
                )

                count += 1

        return count

    def _query_closest_rate(
        self,
        cursor: sqlite3.Cursor,
        date_str: str,
        base_currency: str,
        target_currency: str,
        strategy: str,
    ) -> tuple[str | None, Decimal | None]:
        """Execute a nearest-rate SQL query for the given strategy."""
        if strategy == BEFORE:
            cursor.execute(
                """
            SELECT date, rate FROM rates
            WHERE date <= ? AND base_currency = ? AND target_currency = ?
            ORDER BY date DESC LIMIT 1
            """,
                (date_str, base_currency, target_currency),
            )
        elif strategy == AFTER:
            cursor.execute(
                """
            SELECT date, rate FROM rates
            WHERE date >= ? AND base_currency = ? AND target_currency = ?
            ORDER BY date ASC LIMIT 1
            """,
                (date_str, base_currency, target_currency),
            )
        elif strategy == CLOSEST:
            cursor.execute(
                """
            SELECT date, rate, ABS(julianday(date) - julianday(?)) as diff
            FROM rates
            WHERE base_currency = ? AND target_currency = ?
            ORDER BY diff ASC LIMIT 1
            """,
                (date_str, base_currency, target_currency),
            )
        else:
            return (date_str, None)

        row = cursor.fetchone()
        if row:
            return (str(row[0]), Decimal(str(row[1])))
        return (date_str, None)

    def get_rate(
        self,
        base_currency: str,
        target_currency: str,
        as_of_date: str | date = "latest",
        closest_rate: str | None = None,
    ) -> tuple[str | None, Decimal | None]:
        """
        Get the exchange rate from base_currency to target_currency.

        Args:
            base_currency: The base currency code.
            target_currency: The target currency code.
            as_of_date: The date to get the rate for (or 'latest').
            closest_rate: Strategy for getting the closest rate if exact date not available.
                          Options: 'before', 'after', 'closest', or None.

        Returns:
            Tuple of (date_str, rate) or (None, None) if not found.
        """
        if not self._check_tables_exist():
            console.print(
                "[yellow]Database not initialized. Run 'initialize' first.[/yellow]"
            )
            return (None, None)

        cursor = self.conn.cursor()

        # Normalize currency codes
        base_currency = base_currency.upper()
        target_currency = target_currency.upper()

        # Resolve 'latest' to a concrete date string
        if as_of_date == "latest":
            cursor.execute("SELECT value FROM metadata WHERE key = 'last_updated'")
            row = cursor.fetchone()
            if not row:
                return (None, None)
            date_str = str(row[0])
        elif isinstance(as_of_date, date):
            date_str = as_of_date.strftime("%Y-%m-%d")
        else:
            date_str = as_of_date

        # Try to get the rate for the exact date
        cursor.execute(
            """
        SELECT date, rate
        FROM rates
        WHERE date = ? AND base_currency = ? AND target_currency = ?
        """,
            (date_str, base_currency, target_currency),
        )

        row = cursor.fetchone()
        if row:
            return (str(row[0]), Decimal(str(row[1])))

        if not closest_rate:
            return (date_str, None)

        return self._query_closest_rate(
            cursor, date_str, base_currency, target_currency, closest_rate
        )

    def list_currencies(self) -> list[str]:
        """
        List all available currencies in the database.

        Returns:
            List of currency codes.
        """
        if not self._check_tables_exist():
            return []

        cursor = self.conn.cursor()
        cursor.execute("SELECT DISTINCT code FROM currencies ORDER BY code")
        return [str(row[0]) for row in cursor.fetchall()]

    def get_stats(self) -> dict[str, Any]:
        """
        Get statistics about the database.

        Returns:
            Dictionary with database statistics.
        """
        if not self._check_tables_exist():
            return {
                "initialized": False,
                "last_updated": None,
                "currency_count": 0,
                "rate_count": 0,
                "date_range": (None, None),
            }

        cursor = self.conn.cursor()

        # Get last update date
        cursor.execute("SELECT value FROM metadata WHERE key = 'last_updated'")
        last_updated = cursor.fetchone()

        # Count currencies
        cursor.execute("SELECT COUNT(DISTINCT code) FROM currencies")
        currency_count_row = cursor.fetchone()
        currency_count = int(currency_count_row[0]) if currency_count_row else 0

        # Count rates
        cursor.execute("SELECT COUNT(*) FROM rates")
        rate_count_row = cursor.fetchone()
        rate_count = int(rate_count_row[0]) if rate_count_row else 0

        # Get date range
        cursor.execute("SELECT MIN(date), MAX(date) FROM rates")
        date_range_row = cursor.fetchone()
        date_range: tuple[str | None, str | None] = (
            (
                str(date_range_row[0]) if date_range_row[0] is not None else None,
                str(date_range_row[1]) if date_range_row[1] is not None else None,
            )
            if date_range_row
            else (None, None)
        )

        return {
            "initialized": True,
            "last_updated": str(last_updated[0]) if last_updated else None,
            "currency_count": currency_count,
            "rate_count": rate_count,
            "date_range": date_range,
        }
