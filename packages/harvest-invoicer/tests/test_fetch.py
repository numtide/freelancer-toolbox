"""Tests for fetch.py: agency mode wiring and is_external filtering (no network)."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import click
import pytest
from harvest_exporter.cli import NUMTIDE_RATE
from harvest_invoicer.fetch import fetch_lines

_JUNE = (date(2026, 6, 1), date(2026, 6, 30))


def _entry(
    *,
    user: str = "Alice",
    client: str = "Acme Corp",
    project: str = "Website",
    task: str = "Development",
    hours: float = 10.0,
    rate: float = 100.0,
    currency: str = "EUR",
) -> dict[str, object]:
    """Minimal Harvest API time-entry dict for unit testing."""
    return {
        "user": {"name": user},
        "client": {"name": client, "currency": currency},
        "project": {"name": project},
        "task": {"name": task},
        "rounded_hours": hours,
        "billable_rate": rate,
        "billable": True,
    }


@pytest.fixture(autouse=True)
def _harvest_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Inject fake Harvest credentials so fetch_lines skips the credential check."""
    monkeypatch.setenv("HARVEST_ACCOUNT_ID", "test-id")
    monkeypatch.setenv("HARVEST_BEARER_TOKEN", "test-token")


class TestAgencyModeWiring:
    def test_default_uses_numtide_rate(self) -> None:
        """Default (agency) mode passes NUMTIDE_RATE to aggregate_time_entries."""
        entries = [_entry()]
        with (
            patch("harvest.get_time_entries", return_value=entries),
            patch("harvest_exporter.aggregate_time_entries") as mock_agg,
        ):
            mock_agg.return_value = {}
            with pytest.raises(click.ClickException):
                fetch_lines(*_JUNE)
            mock_agg.assert_called_once()
            _args, kwargs = mock_agg.call_args
            assert kwargs["agency_rate"] == NUMTIDE_RATE

    def test_no_agency_passes_none(self) -> None:
        """use_agency=False passes None as agency_rate."""
        entries = [_entry()]
        with (
            patch("harvest.get_time_entries", return_value=entries),
            patch("harvest_exporter.aggregate_time_entries") as mock_agg,
        ):
            mock_agg.return_value = {}
            with pytest.raises(click.ClickException):
                fetch_lines(*_JUNE, use_agency=False)
            mock_agg.assert_called_once()
            _args, kwargs = mock_agg.call_args
            assert kwargs["agency_rate"] is None


class TestIsExternalFiltering:
    def test_agency_mode_excludes_external_clients(self) -> None:
        """External ('External - ') clients are excluded in agency mode without filter."""
        entries = [
            _entry(
                client="Acme Corp", project="Website", task="Development", hours=10.0
            ),
            _entry(
                client="External - OSS Project",
                project="OSS Project",
                task="Consulting",
                hours=5.0,
            ),
        ]
        with patch("harvest.get_time_entries", return_value=entries):
            lines = fetch_lines(*_JUNE, use_agency=True)

        # Only the internal Acme Corp entry should appear
        assert len(lines) == 1
        assert "Acme Corp" in lines[0].concept

    def test_agency_mode_includes_external_when_explicitly_filtered(self) -> None:
        """External client IS included when client_filter names it explicitly."""
        entries = [
            _entry(
                client="Acme Corp", project="Website", task="Development", hours=10.0
            ),
            _entry(
                client="External - OSS Project",
                project="OSS Project",
                task="Consulting",
                hours=5.0,
            ),
        ]
        with patch("harvest.get_time_entries", return_value=entries):
            # In agency mode, external clients use project name as client key
            lines = fetch_lines(*_JUNE, use_agency=True, client_filter="OSS Project")

        assert len(lines) == 1
        assert "OSS Project" in lines[0].concept

    def test_no_agency_mode_groups_by_project(self) -> None:
        """In no-agency mode, client_filter matches the project name."""
        entries = [
            _entry(
                client="Acme Corp", project="Website", task="Development", hours=10.0
            ),
        ]
        with patch("harvest.get_time_entries", return_value=entries):
            lines = fetch_lines(*_JUNE, use_agency=False, client_filter="Website")

        assert len(lines) == 1
        # Project-based grouping: concept starts with project name, not client name
        assert "Website" in lines[0].concept
