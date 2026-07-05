"""Tests for cli.py: Click command validation via CliRunner."""

from __future__ import annotations

from datetime import date, datetime

from click.testing import CliRunner
from harvest_invoicer.cli import _resolve_period, main


def test_generate_demo_invalid_month() -> None:
    """generate --demo rejects a non-YYYY-MM month string with exit code != 0."""
    runner = CliRunner()
    result = runner.invoke(main, ["generate", "--demo", "--month", "junk"])
    assert result.exit_code != 0


def test_edit_demo_invalid_month() -> None:
    """edit --demo rejects a non-YYYY-MM month string with exit code != 0."""
    runner = CliRunner()
    result = runner.invoke(main, ["edit", "--demo", "--month", "junk", "--no-browser"])
    assert result.exit_code != 0


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
