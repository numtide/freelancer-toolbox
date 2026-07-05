"""Tests for cli.py: Click command validation via CliRunner."""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from click.testing import CliRunner
from harvest_invoicer.cli import _resolve_period, main
from harvest_invoicer.render import _PACKAGED_TEMPLATES_DIR

if TYPE_CHECKING:
    from pathlib import Path


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


def test_merge_duplicates_flag_available() -> None:
    """Both commands expose --merge-duplicates."""
    runner = CliRunner()
    for cmd in ("edit", "generate"):
        result = runner.invoke(main, [cmd, "--help"])
        assert result.exit_code == 0
        assert "--merge-duplicates" in result.output


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
