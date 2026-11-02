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

SCHEMA_VERSION = 4

# Columns of an archived invoice, in table order (see :func:`_migrate`).
INVOICE_COLUMNS = (
    "id",
    "number",
    "client_key",
    "client_name",
    "period_start",
    "period_end",
    "issue_date",
    "due_date",
    "total",
    "currency",
    "language",
    "filename",
    "sha256",
    "created_at",
    "sent_at",
    "sent_to",
)


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
    if version < 2:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS draft (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                data TEXT NOT NULL
            );
            PRAGMA user_version = 2;
            """
        )
    if version < 3:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS email (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                data TEXT NOT NULL
            );
            PRAGMA user_version = 3;
            """
        )
    if version < 4:
        # The invoice archive: one row per generated PDF (the file itself
        # lives in the invoices directory, see archive.py).  ``id`` is the
        # unguessable token in the invoice's link; dates are ISO strings.
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS invoices (
                id TEXT PRIMARY KEY,
                number TEXT NOT NULL,
                client_key TEXT,
                client_name TEXT NOT NULL DEFAULT '',
                period_start TEXT,
                period_end TEXT,
                issue_date TEXT,
                due_date TEXT,
                total REAL NOT NULL,
                currency TEXT NOT NULL,
                language TEXT NOT NULL DEFAULT 'en',
                filename TEXT NOT NULL UNIQUE,
                sha256 TEXT NOT NULL,
                created_at TEXT NOT NULL,
                sent_at TEXT,
                sent_to TEXT
            );
            CREATE INDEX IF NOT EXISTS invoices_number
                ON invoices (number, created_at);
            PRAGMA user_version = 4;
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


def get_email(path: Path | str) -> dict[str, object] | None:
    """The email/SMTP config record, or ``None`` before configuration.

    Never holds the SMTP password — that stays in the environment only.
    """
    with _connect(path) as conn:
        row = conn.execute("SELECT data FROM email WHERE id = 1").fetchone()
    return json.loads(row[0]) if row else None


def save_email(path: Path | str, email: dict[str, object]) -> None:
    with _connect(path) as conn:
        conn.execute(
            "INSERT INTO email (id, data) VALUES (1, ?) "
            "ON CONFLICT (id) DO UPDATE SET data = excluded.data",
            (json.dumps(email, ensure_ascii=False),),
        )


def get_draft(path: Path | str) -> dict[str, object] | None:
    """The autosaved editing draft, or ``None`` when there is none."""
    with _connect(path) as conn:
        row = conn.execute("SELECT data FROM draft WHERE id = 1").fetchone()
    return json.loads(row[0]) if row else None


def save_draft(path: Path | str, data: dict[str, object]) -> None:
    """Autosave the editing draft (a single slot, overwritten each time)."""
    with _connect(path) as conn:
        conn.execute(
            "INSERT INTO draft (id, data) VALUES (1, ?) "
            "ON CONFLICT (id) DO UPDATE SET data = excluded.data",
            (json.dumps(data, ensure_ascii=False),),
        )


def clear_draft(path: Path | str) -> None:
    with _connect(path) as conn:
        conn.execute("DELETE FROM draft")


def _invoice_row(row: tuple[object, ...] | None) -> dict[str, object] | None:
    return dict(zip(INVOICE_COLUMNS, row, strict=True)) if row else None


_INVOICE_SELECT = f"SELECT {', '.join(INVOICE_COLUMNS)} FROM invoices"  # noqa: S608 — constant columns


def add_invoice(path: Path | str, record: dict[str, object]) -> None:
    """Insert an archived invoice (*record* carries every column but sent_*)."""
    cols = [c for c in INVOICE_COLUMNS if c in record]
    with _connect(path) as conn:
        conn.execute(
            f"INSERT INTO invoices ({', '.join(cols)}) "  # noqa: S608 — constant columns
            f"VALUES ({', '.join('?' for _ in cols)})",
            [record[c] for c in cols],
        )


def get_invoice(path: Path | str, invoice_id: str) -> dict[str, object] | None:
    with _connect(path) as conn:
        row = conn.execute(f"{_INVOICE_SELECT} WHERE id = ?", (invoice_id,)).fetchone()
    return _invoice_row(row)


def list_invoices(path: Path | str) -> list[dict[str, object]]:
    """All archived invoices, newest first.

    Insertion order is creation order; the ``created_at`` strings may carry
    different UTC offsets (DST), so they are not sorted as text.
    """
    with _connect(path) as conn:
        rows = conn.execute(f"{_INVOICE_SELECT} ORDER BY rowid DESC").fetchall()
    return [r for r in (_invoice_row(row) for row in rows) if r]


def latest_invoice(
    path: Path | str, number: str | None = None
) -> dict[str, object] | None:
    """The newest archived invoice (for *number*, when given)."""
    where, args = ("WHERE number = ?", (number,)) if number is not None else ("", ())
    with _connect(path) as conn:
        row = conn.execute(
            f"{_INVOICE_SELECT} {where} ORDER BY rowid DESC LIMIT 1",
            args,
        ).fetchone()
    return _invoice_row(row)


def delete_invoice(path: Path | str, invoice_id: str) -> None:
    with _connect(path) as conn:
        conn.execute("DELETE FROM invoices WHERE id = ?", (invoice_id,))


def mark_invoice_sent(
    path: Path | str, invoice_id: str, sent_at: str, sent_to: str
) -> None:
    """Record the latest delivery (a resend overwrites the previous one)."""
    with _connect(path) as conn:
        conn.execute(
            "UPDATE invoices SET sent_at = ?, sent_to = ? WHERE id = ?",
            (sent_at, sent_to, invoice_id),
        )
