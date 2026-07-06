"""Tests for the SQLite state store."""

from __future__ import annotations

from typing import TYPE_CHECKING

from harvest_invoicer.db import (
    default_db_path,
    get_clients,
    get_issuer,
    save_clients,
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
