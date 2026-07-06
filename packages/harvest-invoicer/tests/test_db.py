"""Tests for the SQLite state store."""

from __future__ import annotations

from typing import TYPE_CHECKING

from harvest_invoicer.db import (
    clear_draft,
    default_db_path,
    get_clients,
    get_draft,
    get_issuer,
    save_clients,
    save_draft,
    save_issuer,
)

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
