"""Invoice archive: every PDF the editor generates, kept with its metadata.

Metadata rows live in the state database (``invoices`` table, see db.py);
the PDFs live in the invoices directory — ``--invoices-dir`` /
``HARVEST_INVOICER_INVOICES_DIR``, by default ``invoices/`` next to the
database.  Each entry has an unguessable id (its link,
``/invoices/<id>.pdf``) and a readable, unique file name
(``<number>_<client>_<random>.pdf``).

File names are built from slugs restricted to ``[A-Za-z0-9-]`` and are
re-checked whenever a stored name is turned back into a path, so no
record can point outside the invoices directory.
"""

from __future__ import annotations

import contextlib
import hashlib
import logging
import os
import re
import secrets
import sqlite3
import unicodedata
from datetime import datetime
from typing import TYPE_CHECKING

from harvest_invoicer.db import add_invoice, delete_invoice, get_invoice, latest_invoice
from harvest_invoicer.i18n import resolve_language

if TYPE_CHECKING:
    from pathlib import Path

    from harvest_invoicer.model import Invoice

# token_urlsafe(16): 128 random bits, 22 URL-safe characters.
_ID_BYTES = 16
# Ids as issued (and anything a future, longer id could look like); a
# request path that does not match never reaches the database.
_ID_RE = re.compile(r"[A-Za-z0-9_-]{16,64}")
# The only shape a stored file name may have.
_FILENAME_RE = re.compile(r"[A-Za-z0-9-]+(?:_[A-Za-z0-9-]+)*\.pdf")
_SLUG_MAX = 48
# Tries at a fresh random suffix if a file name ever collides.
_NAME_ATTEMPTS = 5

_log = logging.getLogger(__name__)

# Not every platform has O_NOFOLLOW; without it the resolve() check in
# invoice_path still keeps reads inside the directory.
_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)


def now_iso() -> str:
    """The current local time as ISO 8601 with its UTC offset."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def default_invoices_dir(db_path: Path) -> Path:
    """The archive's default location: ``invoices/`` beside the database."""
    return db_path.parent / "invoices"


def is_invoice_id(value: str) -> bool:
    return bool(_ID_RE.fullmatch(value))


def slugify(text: str, fallback: str) -> str:
    """ASCII ``[A-Za-z0-9-]`` slug of *text* (accents folded), or *fallback*.

    Everything else — path separators, dots, spaces, underscores (the file
    name's field separator) — collapses into single dashes.
    """
    ascii_text = (
        unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    )
    slug = re.sub(r"[^A-Za-z0-9]+", "-", ascii_text).strip("-")
    return slug[:_SLUG_MAX].strip("-") or fallback


def build_filename(number: str, client_name: str) -> str:
    """``<number>_<client>_<random>.pdf`` — readable, and unique in practice.

    The random part is independent of the invoice id, so a shared file
    name never reveals any of the link's secret.
    """
    return (
        f"{slugify(number, 'invoice')}_{slugify(client_name, 'client')}_"
        f"{secrets.token_hex(4)}.pdf"
    )


def invoice_path(invoices_dir: Path, filename: str) -> Path:
    """The archived file for a stored *filename*, kept inside the directory.

    Raises :class:`ValueError` for a name that is not one this module
    generates, or that would resolve outside *invoices_dir*.  The returned
    path is the directory entry itself (not resolved), so opening it with
    ``O_NOFOLLOW`` or unlinking it never acts on a symlink's target.
    """
    if not _FILENAME_RE.fullmatch(filename):
        msg = f"Invalid archived file name: {filename!r}"
        raise ValueError(msg)
    root = invoices_dir.resolve()
    path = root / filename
    if path.resolve().parent != root:
        msg = f"Archived file escapes the invoices directory: {filename!r}"
        raise ValueError(msg)
    return path


def ensure_private_dir(invoices_dir: Path) -> None:
    """Create the invoices directory owner-only (``0700``) if it is missing.

    An existing directory is never changed — its owner and mode are the
    deployment's choice — but one that other users can reach gets a
    warning in the log.
    """
    if not invoices_dir.exists():
        invoices_dir.parent.mkdir(parents=True, exist_ok=True)
        invoices_dir.mkdir(mode=0o700, exist_ok=True)
        return
    if invoices_dir.stat().st_mode & 0o077:
        _log.warning(
            "Invoices directory %s is accessible to other users; restrict it "
            "to the service user (chmod 700).",
            invoices_dir,
        )


def _write_new(path: Path, data: bytes) -> None:
    """Write *data* durably to a new, owner-only file at *path*.

    ``O_EXCL`` never overwrites another invoice.  A partial file is
    removed on failure; nothing links to the file before its row exists,
    so no reader ever sees one half-written.  The file (and, best effort,
    its directory entry) is flushed to disk before the row is added.
    """
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    _fsync_dir(path.parent)


def _fsync_dir(directory: Path) -> None:
    """Flush a directory entry to disk, where the platform allows it."""
    try:
        dir_fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        with contextlib.suppress(OSError):
            os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def archive_pdf(
    db_path: Path,
    invoices_dir: Path,
    pdf: bytes,
    invoice: Invoice,
    client: dict[str, str],
    client_key: str | None,
    issuer: dict[str, object],
) -> tuple[dict[str, object], bool]:
    """Archive *pdf* for *invoice*; return ``(record, reused)``.

    When the newest archived PDF for the same invoice number has the same
    content, that entry is returned (``reused``) instead of a duplicate.
    Callers serialize calls (the check-then-insert is not atomic).
    """
    digest = hashlib.sha256(pdf).hexdigest()
    newest = latest_invoice(db_path, invoice.number)
    if (
        newest is not None
        and newest["sha256"] == digest
        # The file on disk must still be that PDF (not lost or altered).
        and read_invoice(invoices_dir, newest) is not None
    ):
        return newest, True

    ensure_private_dir(invoices_dir)
    client_name = str(client.get("name") or "")
    record: dict[str, object] = {
        "id": secrets.token_urlsafe(_ID_BYTES),
        "number": invoice.number,
        "client_key": client_key,
        "client_name": client_name,
        "period_start": invoice.period_start.isoformat()
        if invoice.period_start
        else None,
        "period_end": invoice.period_end.isoformat() if invoice.period_end else None,
        "issue_date": invoice.issue_date.isoformat(),
        "due_date": invoice.due_date.isoformat(),
        "total": round(invoice.grand_total, 2),
        "currency": invoice.currency,
        "language": resolve_language(client, issuer),
        "sha256": digest,
        "created_at": now_iso(),
        "sent_at": None,
        "sent_to": None,
    }
    for attempt in range(_NAME_ATTEMPTS):
        filename = build_filename(invoice.number, client_name)
        path = invoice_path(invoices_dir, filename)
        try:
            _write_new(path, pdf)
        except FileExistsError:
            if attempt == _NAME_ATTEMPTS - 1:
                raise
            continue
        record["filename"] = filename
        try:
            add_invoice(db_path, record)
        except sqlite3.Error:
            path.unlink(missing_ok=True)
            raise
        return record, False
    msg = "Could not pick a unique archive file name."  # pragma: no cover
    raise RuntimeError(msg)  # pragma: no cover


def invoice_file(invoices_dir: Path, record: dict[str, object]) -> Path | None:
    """The record's PDF on disk, or ``None`` when it is missing or invalid."""
    try:
        path = invoice_path(invoices_dir, str(record["filename"]))
    except ValueError:
        return None
    return path if path.is_file() and not path.is_symlink() else None


def _verified_bytes(
    invoices_dir: Path, record: dict[str, object]
) -> tuple[bytes | None, str]:
    """``(bytes, "ok")``, or ``(None, "missing" | "damaged")``.

    "damaged": the file exists but no longer matches the sha256 recorded
    when it was archived.  Invalid names and symlinks count as missing.
    """
    try:
        path = invoice_path(invoices_dir, str(record["filename"]))
        fd = os.open(path, os.O_RDONLY | _O_NOFOLLOW)
    except (ValueError, OSError):
        return None, "missing"
    with os.fdopen(fd, "rb") as fh:
        data = fh.read()
    if hashlib.sha256(data).hexdigest() != record.get("sha256"):
        return None, "damaged"
    return data, "ok"


def file_state(invoices_dir: Path, record: dict[str, object]) -> str:
    """Whether the record's PDF is usable: "ok", "missing" or "damaged"."""
    return _verified_bytes(invoices_dir, record)[1]


def read_invoice(invoices_dir: Path, record: dict[str, object]) -> bytes | None:
    """The record's PDF bytes, or ``None`` when they can't be trusted.

    ``None`` when the file is missing, invalid, a symlink, or no longer
    matches the sha256 recorded when it was archived (logged: only the
    file name, nothing else about the invoice).
    """
    data, state = _verified_bytes(invoices_dir, record)
    if state == "damaged":
        _log.warning(
            "Archived invoice file %s does not match its recorded checksum; "
            "treating it as missing.",
            record.get("filename"),
        )
    return data


def lookup(db_path: Path, invoice_id: str) -> dict[str, object] | None:
    """The archived invoice for a link id (``None`` for malformed ids too)."""
    if not is_invoice_id(invoice_id):
        return None
    return get_invoice(db_path, invoice_id)


def remove(db_path: Path, invoices_dir: Path, record: dict[str, object]) -> None:
    """Delete an archived invoice: its file first, then its row.

    A file that is already gone is fine.  Any other failure to remove it
    (e.g. permissions) propagates as :class:`OSError` and keeps the row,
    so no PDF is ever left behind without an entry pointing at it.
    """
    try:
        path = invoice_path(invoices_dir, str(record["filename"]))
    except ValueError:
        path = None  # a tampered name: never touch the filesystem
    if path is not None:
        with contextlib.suppress(FileNotFoundError):
            path.unlink()
    delete_invoice(db_path, str(record["id"]))
