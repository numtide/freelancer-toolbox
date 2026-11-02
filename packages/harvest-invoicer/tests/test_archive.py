"""Tests for archive.py: file names, path safety, archiving and dedupe."""

from __future__ import annotations

import re
import stat
from datetime import date
from typing import TYPE_CHECKING

import pytest
from harvest_invoicer import db as state_db
from harvest_invoicer.archive import (
    archive_pdf,
    build_filename,
    default_invoices_dir,
    invoice_file,
    invoice_path,
    is_invoice_id,
    lookup,
    remove,
    slugify,
)
from harvest_invoicer.model import Invoice, InvoiceLine

if TYPE_CHECKING:
    from pathlib import Path


def _invoice(number: str = "2026-06", qty: float = 10.0) -> Invoice:
    return Invoice(
        number=number,
        issue_date=date(2026, 7, 1),
        due_date=date(2026, 7, 16),
        lines=[InvoiceLine(concept="Dev", unit_price=100.0, quantity=qty)],
        period_start=date(2026, 6, 1),
        period_end=date(2026, 6, 30),
    )


_CLIENT = {"name": "Numtide Sàrl", "language": "es"}
_ISSUER: dict[str, object] = {"name": "Jane"}


def _archive(tmp_path: Path, pdf: bytes, number: str = "2026-06"):  # noqa: ANN202
    return archive_pdf(
        tmp_path / "state.db",
        tmp_path / "invoices",
        pdf,
        _invoice(number),
        _CLIENT,
        "numtide",
        _ISSUER,
    )


class TestNames:
    @pytest.mark.parametrize(
        ("text", "slug"),
        [
            ("2026/06", "2026-06"),
            ("../../etc/passwd", "etc-passwd"),
            ("Numtide Sàrl", "Numtide-Sarl"),
            ("a_b.c d", "a-b-c-d"),
            ("..", "x"),
            ("", "x"),
            ("日本", "x"),
        ],
    )
    def test_slugify(self, text: str, slug: str) -> None:
        assert slugify(text, "x") == slug

    def test_slug_is_bounded(self) -> None:
        assert len(slugify("a" * 500, "x")) <= 48

    def test_filename_shape_and_uniqueness(self) -> None:
        names = {build_filename("2026/06", "Acme / Corp") for _ in range(50)}
        assert len(names) == 50
        for name in names:
            assert re.fullmatch(r"2026-06_Acme-Corp_[0-9a-f]{8}\.pdf", name)

    @pytest.mark.parametrize(
        "name",
        [
            "../x.pdf",
            "a/b.pdf",
            "x.txt",
            "/etc/passwd",
            ".pdf",
            "x.pdf/..",
            "a\x00.pdf",
        ],
    )
    def test_invoice_path_rejects_unsafe_names(self, tmp_path: Path, name: str) -> None:
        with pytest.raises(ValueError, match="Invalid archived file name"):
            invoice_path(tmp_path, name)

    def test_invoice_path_rejects_symlink_escape(self, tmp_path: Path) -> None:
        (tmp_path / "inv").mkdir()
        (tmp_path / "secret.pdf").write_bytes(b"secret")
        (tmp_path / "inv" / "link.pdf").symlink_to(tmp_path / "secret.pdf")
        with pytest.raises(ValueError, match="escapes"):
            invoice_path(tmp_path / "inv", "link.pdf")

    def test_default_dir_is_next_to_db(self, tmp_path: Path) -> None:
        assert default_invoices_dir(tmp_path / "state.db") == tmp_path / "invoices"


class TestArchive:
    def test_creates_file_and_record(self, tmp_path: Path) -> None:
        record, reused = _archive(tmp_path, b"%PDF-one")
        assert not reused
        assert is_invoice_id(str(record["id"]))
        assert len(str(record["id"])) >= 22  # token_urlsafe(16)
        path = tmp_path / "invoices" / str(record["filename"])
        assert path.read_bytes() == b"%PDF-one"
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert str(record["filename"]).startswith("2026-06_Numtide-Sarl_")
        stored = state_db.get_invoice(tmp_path / "state.db", str(record["id"]))
        assert stored is not None
        assert stored["client_key"] == "numtide"
        assert stored["client_name"] == "Numtide Sàrl"
        assert stored["period_start"] == "2026-06-01"
        assert stored["period_end"] == "2026-06-30"
        assert stored["total"] == 1000.0
        assert stored["currency"] == "EUR"
        assert stored["language"] == "es"
        assert stored["sent_at"] is None
        assert len(str(stored["sha256"])) == 64
        # The random file-name part never reveals the link id.
        assert str(record["id"])[:8] not in str(record["filename"])

    def test_identical_content_reuses_newest_entry(self, tmp_path: Path) -> None:
        first, _ = _archive(tmp_path, b"%PDF-same")
        again, reused = _archive(tmp_path, b"%PDF-same")
        assert reused
        assert again["id"] == first["id"]
        assert len(state_db.list_invoices(tmp_path / "state.db")) == 1
        assert len(list((tmp_path / "invoices").iterdir())) == 1

    def test_changed_content_adds_an_entry(self, tmp_path: Path) -> None:
        first, _ = _archive(tmp_path, b"%PDF-one")
        second, reused = _archive(tmp_path, b"%PDF-two")
        assert not reused
        assert second["id"] != first["id"]
        assert second["filename"] != first["filename"]
        assert len(state_db.list_invoices(tmp_path / "state.db")) == 2

    def test_dedupe_only_against_newest_for_the_number(self, tmp_path: Path) -> None:
        _archive(tmp_path, b"%PDF-A")
        _archive(tmp_path, b"%PDF-B")
        _, reused = _archive(tmp_path, b"%PDF-A")  # newest is B
        assert not reused
        _, reused = _archive(tmp_path, b"%PDF-A", number="2026-07")
        assert not reused  # another number never reuses
        assert len(state_db.list_invoices(tmp_path / "state.db")) == 4

    def test_missing_file_is_not_reused(self, tmp_path: Path) -> None:
        first, _ = _archive(tmp_path, b"%PDF-same")
        (tmp_path / "invoices" / str(first["filename"])).unlink()
        again, reused = _archive(tmp_path, b"%PDF-same")
        assert not reused
        assert again["id"] != first["id"]

    def test_lookup_rejects_malformed_ids(self, tmp_path: Path) -> None:
        record, _ = _archive(tmp_path, b"%PDF")
        db = tmp_path / "state.db"
        assert lookup(db, str(record["id"])) is not None
        for bad in ("", "short", "../" + str(record["id"]), str(record["id"]) + "/x"):
            assert lookup(db, bad) is None

    def test_remove_deletes_row_and_file(self, tmp_path: Path) -> None:
        record, _ = _archive(tmp_path, b"%PDF")
        path = tmp_path / "invoices" / str(record["filename"])
        remove(tmp_path / "state.db", tmp_path / "invoices", record)
        assert not path.exists()
        assert state_db.get_invoice(tmp_path / "state.db", str(record["id"])) is None

    def test_remove_tolerates_missing_file(self, tmp_path: Path) -> None:
        record, _ = _archive(tmp_path, b"%PDF")
        (tmp_path / "invoices" / str(record["filename"])).unlink()
        remove(tmp_path / "state.db", tmp_path / "invoices", record)
        assert state_db.list_invoices(tmp_path / "state.db") == []

    def test_tampered_filename_never_leaves_the_dir(self, tmp_path: Path) -> None:
        """A record whose stored name points elsewhere is treated as missing
        and its "file" is never deleted."""
        record, _ = _archive(tmp_path, b"%PDF")
        victim = tmp_path / "victim.pdf"
        victim.write_bytes(b"keep me")
        record["filename"] = "../victim.pdf"
        assert invoice_file(tmp_path / "invoices", record) is None
        remove(tmp_path / "state.db", tmp_path / "invoices", record)
        assert victim.read_bytes() == b"keep me"
