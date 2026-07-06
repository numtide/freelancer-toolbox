"""Tests for fetch.py: agency mode wiring and is_external filtering (no network)."""

from __future__ import annotations

import json
from datetime import date
from typing import TYPE_CHECKING
from unittest.mock import patch

import click
import pytest
from harvest_exporter.cli import NUMTIDE_RATE
from harvest_invoicer.fetch import (
    apply_client_vat,
    client_extra_lines,
    fetch_lines,
    load_clients,
)
from harvest_invoicer.model import InvoiceLine

if TYPE_CHECKING:
    from pathlib import Path

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


class TestClientVat:
    """Per-client vat_rate from clients.json."""

    def test_apply_client_vat_sets_rate(self) -> None:
        lines = [
            InvoiceLine(concept="Dev", unit_price=100.0, quantity=10.0),
            InvoiceLine(concept="Review", unit_price=100.0, quantity=2.0),
        ]
        entry = {"name": "Domestic Client", "vat_rate": 0.21}
        result = apply_client_vat(lines, entry)  # type: ignore[arg-type]
        assert all(line.vat_rate == 0.21 for line in result)
        # Totals reflect VAT: 1200 base + 21%
        assert sum(line.total for line in result) == pytest.approx(1452.0)

    def test_apply_client_vat_absent_keeps_rate(self) -> None:
        lines = [InvoiceLine(concept="Dev", unit_price=100.0, quantity=10.0)]
        result = apply_client_vat(lines, {"name": "Reverse Charge Client"})
        assert result[0].vat_rate == 0.0

    def test_load_clients_accepts_valid_vat_rate(self, tmp_path: Path) -> None:
        p = tmp_path / "clients.json"
        p.write_text(json.dumps({"Acme": {"name": "Acme Ltd", "vat_rate": 0.21}}))
        clients = load_clients(str(p))
        assert clients["Acme"]["vat_rate"] == 0.21

    def test_load_clients_rejects_out_of_range_vat(self, tmp_path: Path) -> None:
        p = tmp_path / "clients.json"
        p.write_text(json.dumps({"Acme": {"name": "Acme Ltd", "vat_rate": 21}}))
        with pytest.raises(click.ClickException, match="vat_rate"):
            load_clients(str(p))

    def test_load_clients_rejects_non_numeric_vat(self, tmp_path: Path) -> None:
        p = tmp_path / "clients.json"
        p.write_text(json.dumps({"Acme": {"name": "Acme Ltd", "vat_rate": "lots"}}))
        with pytest.raises(click.ClickException, match="vat_rate"):
            load_clients(str(p))


class TestExtraLines:
    """Recurring per-client extra lines from clients.json."""

    def test_builds_lines_with_extra_origin(self) -> None:
        entry = {
            "name": "Acme",
            "extra_lines": [
                {"concept": "Monthly retainer", "unit_price": 500.0},
                {"concept": "License", "unit_price": 20.0, "quantity": 3.0},
            ],
        }
        lines = client_extra_lines(entry)  # type: ignore[arg-type]
        assert len(lines) == 2
        assert all(line.origin == "extra" for line in lines)
        assert lines[0].quantity == 1.0  # quantity defaults to 1
        assert lines[1].total == pytest.approx(60.0)

    def test_absent_config_gives_no_lines(self) -> None:
        assert client_extra_lines({"name": "Acme"}) == []

    def test_load_clients_accepts_valid_extra_lines(self, tmp_path: Path) -> None:
        p = tmp_path / "clients.json"
        p.write_text(
            json.dumps(
                {
                    "Acme": {
                        "name": "Acme Ltd",
                        "extra_lines": [{"concept": "Fee", "unit_price": 10}],
                    }
                }
            )
        )
        clients = load_clients(str(p))
        assert clients["Acme"]["extra_lines"][0]["concept"] == "Fee"

    def test_load_clients_rejects_bad_extra_lines(self, tmp_path: Path) -> None:
        p = tmp_path / "clients.json"
        p.write_text(
            json.dumps(
                {
                    "Acme": {
                        "name": "Acme Ltd",
                        "extra_lines": [{"concept": "Fee"}],  # missing unit_price
                    }
                }
            )
        )
        with pytest.raises(click.ClickException, match="extra_lines"):
            load_clients(str(p))

    def test_load_clients_rejects_non_list_extra_lines(self, tmp_path: Path) -> None:
        p = tmp_path / "clients.json"
        p.write_text(json.dumps({"Acme": {"name": "Acme Ltd", "extra_lines": "nope"}}))
        with pytest.raises(click.ClickException, match="must be a list"):
            load_clients(str(p))
