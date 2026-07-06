"""SQLite state store: one file owns all app-managed configuration.

Config records keep their dict shapes (stored as JSON rows), so the rest
of the app is storage-agnostic.  Connections are short-lived per
operation — safe under the threaded dev server — with WAL enabled.

Path resolution: ``HARVEST_INVOICER_DB`` (or --db) > the XDG data dir
(``~/.local/share/harvest-invoicer/state.db``).  State lives in the data
dir, not the config dir: the app owns every write through the UI.
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

SCHEMA_VERSION = 1


def default_db_path() -> Path:
    """Resolve the state database path (env override, else XDG data dir)."""
    env = os.environ.get("HARVEST_INVOICER_DB", "").strip()
    if env:
        return Path(env)
    base = os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")
    return Path(base) / "harvest-invoicer" / "state.db"


@contextmanager
def _connect(path: Path | str) -> Iterator[sqlite3.Connection]:
    if isinstance(path, Path):
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        _migrate(conn)
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def _migrate(conn: sqlite3.Connection) -> None:
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version < 1:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS issuer (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                data TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS clients (
                key TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                position INTEGER NOT NULL
            );
            PRAGMA user_version = 1;
            """
        )


def get_issuer(path: Path | str) -> dict[str, object] | None:
    """The issuer record, or ``None`` before first configuration."""
    with _connect(path) as conn:
        row = conn.execute("SELECT data FROM issuer WHERE id = 1").fetchone()
    return json.loads(row[0]) if row else None


def save_issuer(path: Path | str, issuer: dict[str, object]) -> None:
    with _connect(path) as conn:
        conn.execute(
            "INSERT INTO issuer (id, data) VALUES (1, ?) "
            "ON CONFLICT (id) DO UPDATE SET data = excluded.data",
            (json.dumps(issuer, ensure_ascii=False),),
        )


def get_clients(path: Path | str) -> dict[str, dict[str, str]]:
    """All client records, in their stable insertion order."""
    with _connect(path) as conn:
        rows = conn.execute(
            "SELECT key, data FROM clients ORDER BY position"
        ).fetchall()
    return {key: json.loads(data) for key, data in rows}


def save_clients(path: Path | str, clients: dict[str, dict[str, object]]) -> None:
    """Replace the client set in one transaction (mirrors the mapping)."""
    with _connect(path) as conn:
        conn.execute("DELETE FROM clients")
        conn.executemany(
            "INSERT INTO clients (key, data, position) VALUES (?, ?, ?)",
            [
                (key, json.dumps(entry, ensure_ascii=False), pos)
                for pos, (key, entry) in enumerate(clients.items())
            ],
        )
