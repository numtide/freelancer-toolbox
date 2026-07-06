"""Tests for cli.py: Click command validation via CliRunner."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import click
import pytest
from click.testing import CliRunner
from harvest_invoicer.cli import (
    _blank_issuer,
    _multi_user_warning,
    _resolve_bill_to,
    _resolve_bill_to_lenient,
    _resolve_period,
    main,
)
from harvest_invoicer.db import default_db_path
from harvest_invoicer.model import REQUIRED_ISSUER_FIELDS, InvoiceLine
from harvest_invoicer.render import _PACKAGED_TEMPLATES_DIR


def test_generate_demo_invalid_month() -> None:
    """generate --demo rejects a non-YYYY-MM month string with exit code != 0."""
    runner = CliRunner()
    result = runner.invoke(main, ["generate", "--demo", "--month", "junk"])
    assert result.exit_code != 0


def test_serve_has_no_per_invoice_flags() -> None:
    """serve hands per-invoice choices to the UI; only session flags remain."""
    runner = CliRunner()
    result = runner.invoke(main, ["serve", "--demo", "--month", "2026-06"])
    assert result.exit_code != 0
    assert "No such option" in result.output
    help_out = runner.invoke(main, ["serve", "--help"]).output
    for gone in (
        "--month",
        "--period-start",
        "--user",
        "--number",
        "--bill-to",
        "--merge-duplicates",
    ):
        assert gone not in help_out
    for kept in ("--harvest-client", "--templates-dir", "--output", "--demo"):
        assert kept in help_out


def test_edit_command_renamed_to_serve() -> None:
    """The old edit name is gone; serve is the editor entrypoint."""
    runner = CliRunner()
    result = runner.invoke(main, ["edit", "--help"])
    assert result.exit_code != 0
    assert "serve" in runner.invoke(main, ["--help"]).output


def test_resolve_period_defaults_to_month() -> None:
    """Without overrides the period spans the whole month."""
    start, end = _resolve_period("2026-06", None, None)
    assert start == date(2026, 6, 1)
    assert end == date(2026, 6, 30)


def test_resolve_period_overrides_win() -> None:
    """--period-start/--period-end take precedence over the month bounds."""
    start, end = _resolve_period(
        "2026-06",
        datetime(2026, 6, 10),
        datetime(2026, 6, 25),
    )
    assert start == date(2026, 6, 10)
    assert end == date(2026, 6, 25)


def test_generate_period_flags_require_single_month() -> None:
    """Explicit period with multiple months is rejected."""
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "generate",
            "--demo",
            "--month",
            "2026-05",
            "--month",
            "2026-06",
            "--period-start",
            "2026-05-01",
        ],
    )
    assert result.exit_code != 0
    assert "single --month" in result.output


def test_merge_duplicates_flag_available() -> None:
    """Headless generate exposes --merge-duplicates (serve uses the checkbox)."""
    runner = CliRunner()
    result = runner.invoke(main, ["generate", "--help"])
    assert result.exit_code == 0
    assert "--merge-duplicates" in result.output


class TestStateResolution:
    """State database resolution: env override, else the XDG data dir."""

    def test_env_override_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HARVEST_INVOICER_DB", "/srv/invoicer/state.db")
        assert default_db_path() == Path("/srv/invoicer/state.db")

    def test_xdg_data_home_default(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("HARVEST_INVOICER_DB", raising=False)
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        assert default_db_path() == tmp_path / "harvest-invoicer" / "state.db"

    def test_blank_issuer_has_required_fields(self) -> None:
        issuer = _blank_issuer()
        assert issuer["name"] == ""
        assert issuer["bank"] == {"iban": "", "bic": ""}
        missing = REQUIRED_ISSUER_FIELDS - set(issuer.keys())
        assert not missing

    def test_generate_without_config_errors_helpfully(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HARVEST_INVOICER_DB", str(tmp_path / "empty.db"))
        runner = CliRunner()
        result = runner.invoke(main, ["generate", "--month", "2026-06"])
        assert result.exit_code != 0
        assert "No configuration found" in result.output
        assert "harvest-invoicer serve" in result.output


class TestTemplatesInit:
    def test_creates_folder_with_packaged_copies(self, tmp_path: Path) -> None:
        """templates init scaffolds the directory with both template files."""
        target = tmp_path / "my-templates"
        runner = CliRunner()
        result = runner.invoke(main, ["templates", "init", str(target)])
        assert result.exit_code == 0
        for name in ("invoice.html", "style.css"):
            copied = target / name
            assert copied.exists()
            assert copied.read_bytes() == (_PACKAGED_TEMPLATES_DIR / name).read_bytes()
        assert "--templates-dir" in result.output

    def test_existing_files_preserved_without_force(self, tmp_path: Path) -> None:
        """A second run must not clobber user edits."""
        target = tmp_path / "my-templates"
        runner = CliRunner()
        runner.invoke(main, ["templates", "init", str(target)])
        (target / "style.css").write_text("/* customized */")
        result = runner.invoke(main, ["templates", "init", str(target)])
        assert result.exit_code == 0
        assert "skipped" in result.output
        assert (target / "style.css").read_text() == "/* customized */"

    def test_force_overwrites(self, tmp_path: Path) -> None:
        """--force restores the packaged versions."""
        target = tmp_path / "my-templates"
        runner = CliRunner()
        runner.invoke(main, ["templates", "init", str(target)])
        (target / "style.css").write_text("/* customized */")
        result = runner.invoke(main, ["templates", "init", str(target), "--force"])
        assert result.exit_code == 0
        assert (target / "style.css").read_bytes() == (
            _PACKAGED_TEMPLATES_DIR / "style.css"
        ).read_bytes()


def test_bill_to_flag_available() -> None:
    """Headless generate exposes --bill-to (serve uses the dropdown)."""
    runner = CliRunner()
    result = runner.invoke(main, ["generate", "--help"])
    assert result.exit_code == 0
    assert "--bill-to" in result.output


def test_generate_bill_to_unknown_key_errors() -> None:
    """--bill-to with a key missing from clients.json fails with the keys listed."""
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["generate", "--demo", "--month", "2026-06", "--bill-to", "Nonexistent"],
    )
    assert result.exit_code != 0
    assert "Nonexistent" in result.output
    assert "Available keys" in result.output


class TestPersistentDefaults:
    """issuer.json harvest_user / default_bill_to and the multi-user warning."""

    def test_bill_to_flag_beats_default(self) -> None:
        clients = {"A": {"name": "A"}, "B": {"name": "B"}}
        entry = _resolve_bill_to("A", "B", None, clients, [])
        assert entry is clients["A"]

    def test_default_bill_to_used_without_flag(self) -> None:
        clients = {"A": {"name": "A"}, "B": {"name": "B"}}
        entry = _resolve_bill_to(None, "B", None, clients, [])
        assert entry is clients["B"]

    def test_default_bill_to_unknown_key_errors(self) -> None:
        clients = {"A": {"name": "A"}}
        with pytest.raises(click.ClickException, match="default_bill_to"):
            _resolve_bill_to(None, "Nope", None, clients, [])

    def test_multi_user_warning_without_filter(self) -> None:
        lines = [
            InvoiceLine(concept="X", unit_price=1.0, quantity=1.0, user="Alice"),
            InvoiceLine(concept="Y", unit_price=1.0, quantity=1.0, user="Bob"),
        ]
        warning = _multi_user_warning(lines, None)
        assert warning is not None
        assert "2 people" in warning
        assert "Alice" in warning
        assert "Bob" in warning

    def test_no_warning_with_filter_or_single_user(self) -> None:
        lines = [
            InvoiceLine(concept="X", unit_price=1.0, quantity=1.0, user="Alice"),
            InvoiceLine(concept="Y", unit_price=1.0, quantity=1.0, user="Bob"),
        ]
        assert _multi_user_warning(lines, "Alice") is None
        single = [InvoiceLine(concept="X", unit_price=1.0, quantity=1.0, user="Al")]
        assert _multi_user_warning(single, None) is None


def test_harvest_client_flag_and_alias() -> None:
    """--harvest-client is the primary name; --client still parses."""
    runner = CliRunner()
    result = runner.invoke(main, ["generate", "--help"])
    assert "--harvest-client" in result.output
    for flag in ("--harvest-client", "--client"):
        result = runner.invoke(
            main, ["generate", "--demo", "--month", "junk", flag, "X"]
        )
        # Fails on the month, never on the option name
        assert "No such option" not in result.output
        assert result.exit_code != 0


class TestLenientBillTo:
    """Editor lazy start: bill-to resolves without fetched data."""

    def test_explicit_key_wins(self) -> None:
        clients = {"a": {"name": "A"}, "b": {"name": "B"}}
        assert _resolve_bill_to_lenient("b", None, clients) is clients["b"]

    def test_unknown_explicit_key_errors(self) -> None:
        with pytest.raises(click.ClickException, match="Available keys"):
            _resolve_bill_to_lenient("nope", None, {"a": {"name": "A"}})

    def test_default_bill_to_used(self) -> None:
        clients = {"a": {"name": "A"}, "b": {"name": "B"}}
        assert _resolve_bill_to_lenient(None, "b", clients) is clients["b"]

    def test_falls_back_to_first_entry(self) -> None:
        clients = {"first": {"name": "F"}, "second": {"name": "S"}}
        assert _resolve_bill_to_lenient(None, None, clients) is clients["first"]

    def test_empty_clients_gives_empty_entry(self) -> None:
        assert _resolve_bill_to_lenient(None, None, {}) == {}
