"""Tests for the SQLite state store."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from harvest_invoicer.db import (
    SCHEMA_VERSION,
    add_invoice,
    clear_draft,
    default_db_path,
    delete_invoice,
    get_clients,
    get_draft,
    get_email,
    get_invoice,
    get_issuer,
    latest_invoice,
    mark_invoice_sent,
    save_clients,
    save_draft,
    save_email,
    save_issuer,
)
from harvest_invoicer.db import list_invoices as state_db_list

if TYPE_CHECKING:
    from pathlib import Path


def test_issuer_roundtrip(tmp_path: Path) -> None:
    db = tmp_path / "state.db"
    assert get_issuer(db) is None  # empty store, no error
    issuer = {"name": "Aldo", "bank": {"iban": "ES64", "bic": "N"}, "language": "es"}
    save_issuer(db, issuer)
    assert get_issuer(db) == issuer
    issuer["name"] = "Aldo Borrero"
    save_issuer(db, issuer)  # upsert
    assert get_issuer(db)["name"] == "Aldo Borrero"


def test_clients_roundtrip_preserves_order(tmp_path: Path) -> None:
    db = tmp_path / "state.db"
    assert get_clients(db) == {}
    clients = {
        "numtide": {"name": "Numtide Sàrl", "vat_rate": 0.0},
        "acme": {"name": "Acme", "extra_lines": [{"concept": "Fee", "unit_price": 1}]},
    }
    save_clients(db, clients)
    loaded = get_clients(db)
    assert loaded == clients
    assert list(loaded) == ["numtide", "acme"]  # insertion order kept


def test_save_clients_replaces_the_set(tmp_path: Path) -> None:
    db = tmp_path / "state.db"
    save_clients(db, {"a": {"name": "A"}, "b": {"name": "B"}})
    save_clients(db, {"b": {"name": "B2"}})
    assert get_clients(db) == {"b": {"name": "B2"}}


def test_unicode_survives(tmp_path: Path) -> None:
    db = tmp_path / "state.db"
    save_clients(db, {"numtide": {"name": "Numtide Sàrl", "country": "España"}})
    assert get_clients(db)["numtide"]["country"] == "España"


def test_default_path_env_override(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setenv("HARVEST_INVOICER_DB", "/srv/x/state.db")
    assert str(default_db_path()) == "/srv/x/state.db"


def test_draft_roundtrip(tmp_path: Path) -> None:
    db = tmp_path / "state.db"
    assert get_draft(db) is None  # empty store, no error
    draft = {"key": "2026-06", "invoice": {"number": "2026-06", "lines": []}}
    save_draft(db, draft)
    assert get_draft(db) == draft
    save_draft(db, {"key": "2026-07"})  # single slot: overwritten
    assert get_draft(db) == {"key": "2026-07"}
    clear_draft(db)
    assert get_draft(db) is None


def test_v1_database_migrates_to_v2(tmp_path: Path) -> None:
    """A pre-draft (schema v1) database gains the draft table transparently."""
    import sqlite3  # noqa: PLC0415

    db = tmp_path / "state.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE issuer (id INTEGER PRIMARY KEY CHECK (id = 1), data TEXT NOT NULL);
        CREATE TABLE clients (key TEXT PRIMARY KEY, data TEXT NOT NULL,
                              position INTEGER NOT NULL);
        INSERT INTO issuer (id, data) VALUES (1, '{"name": "Jane"}');
        PRAGMA user_version = 1;
        """
    )
    conn.commit()
    conn.close()
    assert get_draft(db) is None  # migration ran, table exists
    save_draft(db, {"key": "x"})
    assert get_draft(db) == {"key": "x"}
    assert get_issuer(db) == {"name": "Jane"}  # existing data untouched


def test_email_roundtrip(tmp_path: Path) -> None:
    db = tmp_path / "state.db"
    assert get_email(db) is None
    cfg = {"host": "smtp.test", "port": "587", "encryption": "starttls"}
    save_email(db, cfg)
    assert get_email(db) == cfg


def test_v2_database_migrates_to_v3(tmp_path: Path) -> None:
    """A pre-email (schema v2) database gains the email table transparently."""
    import sqlite3  # noqa: PLC0415

    db = tmp_path / "state.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE issuer (id INTEGER PRIMARY KEY CHECK (id = 1), data TEXT NOT NULL);
        CREATE TABLE draft (id INTEGER PRIMARY KEY CHECK (id = 1), data TEXT NOT NULL);
        INSERT INTO issuer (id, data) VALUES (1, '{"name": "Jane"}');
        PRAGMA user_version = 2;
        """
    )
    conn.commit()
    conn.close()
    assert get_email(db) is None  # migration ran, table exists
    save_email(db, {"host": "smtp.test"})
    assert get_email(db) == {"host": "smtp.test"}
    assert get_issuer(db) == {"name": "Jane"}  # existing data untouched


def _invoice_record(
    invoice_id: str, created_at: str, **kw: object
) -> dict[str, object]:
    record: dict[str, object] = {
        "id": invoice_id,
        "number": "2026-06",
        "client_key": "acme",
        "client_name": "Acme",
        "period_start": "2026-06-01",
        "period_end": "2026-06-30",
        "issue_date": "2026-07-01",
        "due_date": "2026-07-16",
        "total": 1210.0,
        "currency": "EUR",
        "language": "en",
        "filename": f"2026-06_Acme_{invoice_id[:8]}.pdf",
        "sha256": "0" * 64,
        "created_at": created_at,
    }
    record.update(kw)
    return record


def test_invoices_roundtrip_and_order(tmp_path: Path) -> None:
    db = tmp_path / "state.db"
    assert state_db_list(db) == []
    add_invoice(db, _invoice_record("a" * 22, "2026-07-01T10:00:00"))
    add_invoice(db, _invoice_record("b" * 22, "2026-07-02T10:00:00", number="2026-07"))
    assert [r["id"] for r in state_db_list(db)] == ["b" * 22, "a" * 22]  # newest first
    assert get_invoice(db, "a" * 22)["client_name"] == "Acme"
    assert get_invoice(db, "missing") is None
    assert latest_invoice(db)["id"] == "b" * 22
    assert latest_invoice(db, "2026-06")["id"] == "a" * 22
    assert latest_invoice(db, "1999-01") is None


def test_mark_sent_and_delete(tmp_path: Path) -> None:
    db = tmp_path / "state.db"
    add_invoice(db, _invoice_record("a" * 22, "2026-07-01T10:00:00"))
    mark_invoice_sent(db, "a" * 22, "2026-07-03T09:00:00", "billing@acme.test")
    stored = get_invoice(db, "a" * 22)
    assert stored["sent_at"] == "2026-07-03T09:00:00"
    assert stored["sent_to"] == "billing@acme.test"
    delete_invoice(db, "a" * 22)
    assert get_invoice(db, "a" * 22) is None


def test_v3_database_migrates_to_v4(tmp_path: Path) -> None:
    """A pre-archive (schema v3) database gains the invoices table
    transparently, keeping its existing records."""
    import sqlite3  # noqa: PLC0415

    db = tmp_path / "state.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE issuer (id INTEGER PRIMARY KEY CHECK (id = 1), data TEXT NOT NULL);
        CREATE TABLE clients (key TEXT PRIMARY KEY, data TEXT NOT NULL,
                              position INTEGER NOT NULL);
        CREATE TABLE draft (id INTEGER PRIMARY KEY CHECK (id = 1), data TEXT NOT NULL);
        CREATE TABLE email (id INTEGER PRIMARY KEY CHECK (id = 1), data TEXT NOT NULL);
        INSERT INTO issuer (id, data) VALUES (1, '{"name": "Jane"}');
        INSERT INTO email (id, data) VALUES (1, '{"host": "smtp.test"}');
        PRAGMA user_version = 3;
        """
    )
    conn.commit()
    conn.close()
    assert state_db_list(db) == []  # migration ran, table exists
    add_invoice(db, _invoice_record("a" * 22, "2026-07-01T10:00:00"))
    assert get_invoice(db, "a" * 22) is not None
    assert get_issuer(db) == {"name": "Jane"}  # existing data untouched
    assert get_email(db) == {"host": "smtp.test"}
    conn = sqlite3.connect(db)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION == 4
    conn.close()
    # Re-opening a migrated database is a no-op.
    assert len(state_db_list(db)) == 1


def test_filenames_are_unique(tmp_path: Path) -> None:
    import sqlite3  # noqa: PLC0415

    db = tmp_path / "state.db"
    add_invoice(db, _invoice_record("a" * 22, "2026-07-01T10:00:00", filename="x.pdf"))
    with pytest.raises(sqlite3.IntegrityError):
        add_invoice(
            db, _invoice_record("b" * 22, "2026-07-01T10:00:00", filename="x.pdf")
        )
