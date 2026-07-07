"""Tests for app.py: Flask test client, htmx mutations, preview."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Self

import pytest
from harvest_invoicer import db as state_db
from harvest_invoicer.app import create_app
from harvest_invoicer.model import InvoiceLine

if TYPE_CHECKING:
    from collections.abc import Generator

    from flask.testing import FlaskClient
    from werkzeug.test import TestResponse


def _toast_kind(resp: TestResponse) -> str | None:
    """The kind ('ok'/'err') of the toast an HX-Trigger header carries, if any."""
    header = resp.headers.get("HX-Trigger")
    if not header:
        return None
    payload = json.loads(header).get("showtoast")
    return payload.get("kind") if payload else None


def _toast_payload(resp: TestResponse) -> dict:
    """The full showtoast payload ({} if none)."""
    header = resp.headers.get("HX-Trigger")
    if not header:
        return {}
    return json.loads(header).get("showtoast") or {}


def _toast_msg(resp: TestResponse) -> str:
    """The toast's title+body text an HX-Trigger header carries ('' if none)."""
    payload = _toast_payload(resp)
    return f"{payload.get('title', '')} {payload.get('body', '')}".strip()


def _fake_issuer() -> dict[str, object]:
    return {
        "name": "Jane Doe Consulting",
        "address_line1": "12 Example St",
        "address_line2": "10115 Berlin",
        "country": "Germany",
        "tax_id": "DE000000000",
        "tax_id_label": "VAT ID",
        "phone": "+49 30 0000",
        "email": "jane@example.com",
        "bank": {"iban": "DE00 0000 0000 0000 0000 00", "bic": "EXAMPLEXXX"},
    }


def _fake_client() -> dict[str, str]:
    return {
        "name": "Acme Corp Ltd.",
        "address_line1": "1 Acme Blvd",
        "address_line2": "EC1A 1BB London",
        "country": "United Kingdom",
        "tax_id": "GB000000000",
        "tax_id_label": "VAT No.",
    }


def _fake_lines() -> list[InvoiceLine]:
    return [
        InvoiceLine(concept="Backend Development", unit_price=120.0, quantity=40.0),
        InvoiceLine(concept="Code Review", unit_price=120.0, quantity=8.0),
    ]


@pytest.fixture
def client(tmp_path: Path) -> Generator[FlaskClient]:
    app = create_app(
        lines=_fake_lines(),
        issuer=_fake_issuer(),
        client=_fake_client(),
        invoice_number="2026-06",
        output_path=tmp_path / "invoice-2026-06.pdf",
    )
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


class TestEditorIndex:
    def test_get_editor_200(self, client: FlaskClient) -> None:
        resp = client.get("/")
        assert resp.status_code == 200

    def test_editor_contains_htmx(self, client: FlaskClient) -> None:
        resp = client.get("/")
        assert b"htmx" in resp.data.lower()

    def test_editor_contains_line_item(self, client: FlaskClient) -> None:
        resp = client.get("/")
        assert b"Backend Development" in resp.data


class TestLineEdits:
    def test_update_line_description(self, client: FlaskClient) -> None:
        resp = client.post(
            "/lines/update/0",
            data={"concept": "Updated Task", "quantity": "40.0", "unit_price": "120.0"},
        )
        assert resp.status_code == 200
        assert b"Updated Task" in resp.data

    def test_drop_line(self, client: FlaskClient) -> None:
        resp = client.post("/lines/drop/0")
        assert resp.status_code == 200
        # After dropping index 0, "Backend Development" should be gone
        assert b"Backend Development" not in resp.data

    def test_add_line(self, client: FlaskClient) -> None:
        resp = client.post("/lines/add")
        assert resp.status_code == 200
        # A blank row is appended (2 fixture rows + 1 new)
        assert resp.data.count(b'class="row-check"') == 3

    def test_merge_lines(self, client: FlaskClient) -> None:
        resp = client.post("/lines/merge", data={"selected": ["0", "1"]})
        assert resp.status_code == 200
        # After merging 2 lines there should be exactly 1 checkbox (one row)
        assert resp.data.count(b'class="row-check"') == 1


class TestPreview:
    def test_preview_200(self, client: FlaskClient) -> None:
        resp = client.get("/preview")
        assert resp.status_code == 200

    def test_preview_reflects_edit(self, client: FlaskClient) -> None:
        """After a line edit the preview page should contain the new description."""
        client.post(
            "/lines/update/0",
            data={
                "concept": "Unique Edited Task XYZ",
                "quantity": "40",
                "unit_price": "120",
            },
        )
        resp = client.get("/preview")
        assert b"Unique Edited Task XYZ" in resp.data


class TestStaticAssets:
    """Guards against future corruption of vendored/packaged static files."""

    def test_htmx_sha256_matches_notice(self) -> None:
        """Packaged htmx.min.js must match the SHA-256 recorded in the NOTICE file."""
        static_dir = (
            Path(__file__).parent.parent / "src" / "harvest_invoicer" / "static"
        )
        js_path = static_dir / "htmx.min.js"
        notice_path = static_dir / "htmx.min.js.NOTICE"

        assert js_path.exists(), "htmx.min.js is missing"
        assert notice_path.exists(), "htmx.min.js.NOTICE is missing"

        actual = hashlib.sha256(js_path.read_bytes()).hexdigest()
        notice_text = notice_path.read_text(encoding="utf-8")
        expected = next(
            line.split(":", 1)[1].strip()
            for line in notice_text.splitlines()
            if line.startswith("SHA-256:")
        )
        assert actual == expected, (
            f"htmx.min.js sha256 mismatch: got {actual}, NOTICE says {expected}"
        )

    def test_htmx_no_control_chars(self) -> None:
        """htmx.min.js must not contain ASCII control characters other than \\n and \\t."""
        static_dir = (
            Path(__file__).parent.parent / "src" / "harvest_invoicer" / "static"
        )
        data = (static_dir / "htmx.min.js").read_bytes()
        bad = [b for b in data if b < 0x20 and b not in (0x09, 0x0A)]
        assert not bad, (
            f"htmx.min.js contains unexpected control bytes: {[hex(b) for b in bad[:10]]}"
        )

    def test_theme_js_served(self, client: FlaskClient) -> None:
        resp = client.get("/static/theme.js")
        assert resp.status_code == 200
        assert b"invoicer_theme" in resp.data
        assert b"toggleTheme" in resp.data


class TestTheme:
    """Light/dark theme toggle, shared across both screens."""

    def test_editor_has_theme_toggle_and_loader(self, client: FlaskClient) -> None:
        resp = client.get("/")
        assert b'src="/static/theme.js"' in resp.data
        assert b"data-theme-toggle" in resp.data
        assert b"toggleTheme()" in resp.data

    def test_settings_has_theme_toggle_and_loader(self, client: FlaskClient) -> None:
        resp = client.get("/settings")
        assert b'src="/static/theme.js"' in resp.data
        assert b"data-theme-toggle" in resp.data

    def test_settings_back_link_below_header_not_in_bar(
        self, client: FlaskClient
    ) -> None:
        resp = client.get("/settings")
        body = resp.data
        # Back-to-editor moved to a standalone row below the header.
        assert b'class="back-row"' in body
        assert b'class="back-link"' in body
        # ...and is no longer the old top-bar outline button.
        assert b'class="btn-outline" href="/"' not in body

    def test_dark_theme_tokens_present_in_stylesheet(self) -> None:
        static_dir = (
            Path(__file__).parent.parent / "src" / "harvest_invoicer" / "static"
        )
        css = (static_dir / "app.css").read_text(encoding="utf-8")
        assert 'html[data-theme="dark"]' in css
        assert "--ink-tint" in css
        # The totals bar is a semantic dark band — it must NOT flip with the
        # theme, so it uses the fixed brand ink, not var(--ink).
        assert "background: #1D1E1C;" in css


class TestResponsive:
    """The layout must adapt below laptop width."""

    def test_both_pages_have_viewport_meta(self, client: FlaskClient) -> None:
        # Without this the media queries never fire on mobile browsers.
        meta = b'name="viewport" content="width=device-width, initial-scale=1"'
        assert meta in client.get("/").data
        assert meta in client.get("/settings").data

    def test_stylesheet_has_responsive_breakpoints(self) -> None:
        static_dir = (
            Path(__file__).parent.parent / "src" / "harvest_invoicer" / "static"
        )
        css = (static_dir / "app.css").read_text(encoding="utf-8")
        for bp in ("max-width: 1024px", "max-width: 720px", "max-width: 560px"):
            assert f"@media ({bp})" in css


class TestDropdownA11y:
    """The custom dropdowns expose listbox semantics and keyboard support."""

    def test_terms_dropdown_has_listbox_roles(self, client: FlaskClient) -> None:
        body = client.get("/").data
        assert b'aria-haspopup="listbox"' in body
        assert b'role="listbox"' in body
        assert b'role="option"' in body
        assert b'aria-expanded="false"' in body

    def test_client_picker_has_listbox_roles(self, tmp_path: Path) -> None:
        clients = {"acme": {"name": "Acme", "address_line2": "1 St, London"}}
        c = _make_app(tmp_path, clients=clients, client=clients["acme"]).test_client()
        body = c.get("/").data
        assert b'aria-label="Bill to client"' in body
        assert b'id="client-listbox"' in body
        assert b'aria-selected="true"' in body  # the current client's option

    def test_keyboard_handler_wired(self, client: FlaskClient) -> None:
        body = client.get("/").data.decode()
        # Escape-to-close and arrow navigation are present in the editor JS.
        assert 'e.key === "Escape"' in body
        assert 'e.key === "ArrowDown"' in body


class TestSettingsUnsavedGuard:
    """Leaving Settings with pending edits must warn before losing them."""

    def test_beforeunload_guard_present(self, client: FlaskClient) -> None:
        body = client.get("/settings").data.decode()
        assert "beforeunload" in body
        # Discard clears the flag so it never double-prompts.
        assert "discarding is intentional" in body


def _weasyprint_available() -> bool:
    """WeasyPrint imports its native libs (pango, gobject) at import time."""
    try:
        import weasyprint  # noqa: F401, PLC0415
    except Exception:  # noqa: BLE001 — raises OSError/Exception on missing libs
        return False
    return True


class TestPreviewPdf:
    def test_preview_pdf_is_real_pdf(self, client: FlaskClient) -> None:
        """/preview.pdf serves the WeasyPrint render with the PDF magic bytes."""
        if not _weasyprint_available():
            pytest.skip("WeasyPrint native libraries unavailable in this environment")
        resp = client.get("/preview.pdf")
        assert resp.status_code == 200
        assert resp.mimetype == "application/pdf"
        assert resp.data.startswith(b"%PDF")

    def test_preview_pdf_unavailable_returns_503(self, client: FlaskClient) -> None:
        """When WeasyPrint cannot render, the route degrades to a 503 message."""
        if _weasyprint_available():
            pytest.skip("WeasyPrint works here; failure path not reachable")
        resp = client.get("/preview.pdf")
        assert resp.status_code == 503
        assert b"PDF preview unavailable" in resp.data

    def test_editor_has_preview_toggle(self, client: FlaskClient) -> None:
        resp = client.get("/")
        assert b'id="mode-html"' in resp.data
        assert b'id="mode-pdf"' in resp.data
        # PDF is the default preview mode
        assert b'src="/preview.pdf#toolbar=0"' in resp.data
        assert b'id="preview-open"' in resp.data
        assert b'id="preview-toggle"' in resp.data

    def test_editor_chrome(self, client: FlaskClient) -> None:
        resp = client.get("/")
        # Logo links back to the editor
        assert b'class="brand-link" href="/"' in resp.data
        # Settings icon button, split-button dropdown with Send invoice
        assert b'aria-label="Settings"' in resp.data
        assert b"Send invoice" in resp.data
        assert b'class="split-main"' in resp.data
        # Generate PDF lives only on the primary button, not in the dropdown
        assert resp.data.count(b"Generate PDF") == 1
        assert b'rel="icon"' in resp.data
        # Dark totals bar and ghost add button per the design handoff
        assert b'class="totals-bar"' in resp.data
        assert b"Add line item" in resp.data


class TestServicePeriod:
    """Service period: month-derived default, customizable in the editor."""

    def _make_app(self, tmp_path: Path):  # noqa: ANN202
        app = create_app(
            lines=_fake_lines(),
            issuer=_fake_issuer(),
            client=_fake_client(),
            invoice_number="2026-06",
            output_path=tmp_path / "invoice.pdf",
            period_start=date(2026, 6, 1),
            period_end=date(2026, 6, 30),
        )
        app.config["TESTING"] = True
        return app

    def test_period_appears_in_preview(self, tmp_path: Path) -> None:
        app = self._make_app(tmp_path)
        with app.test_client() as c:
            resp = c.get("/preview")
        assert b"Period" in resp.data
        assert b"2026-06-01" in resp.data
        assert b"2026-06-30" in resp.data

    def test_period_editable(self, tmp_path: Path) -> None:
        """Customizing the period via the editor updates the invoice."""
        app = self._make_app(tmp_path)
        with app.test_client() as c:
            resp = c.post(
                "/meta/update",
                data={"period_start": "2026-06-10", "period_end": "2026-06-25"},
            )
            assert resp.status_code == 200
        inv = app.state["invoice"]  # type: ignore[attr-defined]
        assert inv.period_start == date(2026, 6, 10)
        assert inv.period_end == date(2026, 6, 25)

    def test_period_clearable(self, tmp_path: Path) -> None:
        """Clearing both period fields removes the row from the invoice."""
        app = self._make_app(tmp_path)
        with app.test_client() as c:
            c.post("/meta/update", data={"period_start": "", "period_end": ""})
            resp = c.get("/preview")
        inv = app.state["invoice"]  # type: ignore[attr-defined]
        assert inv.period_start is None
        assert inv.period_end is None
        assert b"Period" not in resp.data

    def test_no_period_by_default(self, client: FlaskClient) -> None:
        """create_app without period args produces an invoice without one."""
        resp = client.get("/preview")
        assert b"Period" not in resp.data


class TestFetchFromEditor:
    """POST /lines/fetch re-imports lines for the selected period."""

    def _make_app(self, tmp_path: Path, fetch_callback=None):  # noqa: ANN001, ANN202
        app = create_app(
            lines=_fake_lines(),
            issuer=_fake_issuer(),
            client=_fake_client(),
            invoice_number="2026-06",
            output_path=tmp_path / "invoice.pdf",
            period_start=date(2026, 6, 1),
            period_end=date(2026, 6, 30),
            fetch_callback=fetch_callback,
        )
        app.config["TESTING"] = True
        return app

    def test_first_sync_seeds_lines_keeps_period(self, tmp_path: Path) -> None:
        def fake_fetch(ps: date, pe: date) -> list[InvoiceLine]:
            assert ps == date(2026, 5, 1)
            assert pe == date(2026, 5, 31)
            return [InvoiceLine(concept="May Work", unit_price=100.0, quantity=10.0)]

        app = self._make_app(tmp_path, fake_fetch)
        with app.test_client() as c:
            resp = c.post(
                "/lines/fetch",
                data={"fetch_start": "2026-05-01", "fetch_end": "2026-05-31"},
            )
        assert resp.status_code == 200
        assert b"May Work" in resp.data
        assert _toast_kind(resp) == "ok"
        assert "Synced from Harvest" in _toast_msg(resp)
        inv = app.state["invoice"]  # type: ignore[attr-defined]
        assert len(inv.lines) == 1
        # The invoice's service period is independent of the import range.
        assert inv.period_start == date(2026, 6, 1)
        assert inv.period_end == date(2026, 6, 30)

    def test_empty_draft_is_not_restored(self, tmp_path: Path) -> None:
        """A draft with no line items is dropped, not silently restored into
        a confusing 'synced but empty' state."""
        db = tmp_path / "state.db"
        state_db.save_draft(
            db,
            {
                "key": "2026-06",
                "invoice": {"lines": [], "period_start": "2026-05-01"},
                "import_raw": [{"concept": "X", "unit_price": 1, "quantity": 1}],
            },
        )
        app = _make_app(tmp_path, db_path=db)
        with app.test_client() as c:
            resp = c.get("/")
        assert resp.status_code == 200
        assert not app.state["import_raw"]  # type: ignore[attr-defined]  # not restored
        assert state_db.get_draft(db) is None  # degenerate draft dropped

    def test_sync_seeds_when_synced_but_no_lines(self, tmp_path: Path) -> None:
        """Regression: a state that recorded an import but has zero line
        items (e.g. a restored draft) must still seed on sync, not fall
        through to the no-op 'already up to date' re-sync path."""

        def fetch(ps: date, pe: date) -> list[InvoiceLine]:
            return [InvoiceLine(concept="Fresh", unit_price=100.0, quantity=8.0)]

        app = self._make_app(tmp_path, fetch)
        # Simulate the stale state: import recorded, but no current lines.
        app.state["import_raw"] = [  # type: ignore[attr-defined]
            InvoiceLine(concept="Prev", unit_price=100.0, quantity=5.0, user="Al")
        ]
        app.state["invoice"].lines[:] = []  # type: ignore[attr-defined]
        with app.test_client() as c:
            resp = c.post(
                "/lines/fetch",
                data={"fetch_start": "2026-06-01", "fetch_end": "2026-06-30"},
            )
        assert len(app.state["invoice"].lines) > 0  # type: ignore[attr-defined]
        assert _toast_payload(resp)["title"] == "Synced from Harvest"

    def test_resync_preserves_edited_lines(self, tmp_path: Path) -> None:
        """A re-sync must never clobber hand-edited rows."""
        calls = {"n": 0}

        def fetch(ps: date, pe: date) -> list[InvoiceLine]:
            calls["n"] += 1
            rows = [InvoiceLine(concept="Work", unit_price=100.0, quantity=10.0)]
            if calls["n"] >= 2:  # a new entry appears on the second sync
                rows.append(InvoiceLine(concept="Extra", unit_price=50.0, quantity=2.0))
            return rows

        app = self._make_app(tmp_path, fetch)
        with app.test_client() as c:
            c.post(
                "/lines/fetch",
                data={"fetch_start": "2026-06-01", "fetch_end": "2026-06-30"},
            )
            app.state["invoice"].lines[0].concept = "EDITED BY HAND"  # type: ignore[attr-defined]
            resp = c.post(
                "/lines/fetch",
                data={"fetch_start": "2026-06-01", "fetch_end": "2026-06-30"},
            )
        inv = app.state["invoice"]  # type: ignore[attr-defined]
        assert any(ln.concept == "EDITED BY HAND" for ln in inv.lines)  # kept
        assert _toast_kind(resp) == "ok"

    def test_fetch_error_keeps_lines(self, tmp_path: Path) -> None:
        def failing_fetch(ps: date, pe: date) -> list[InvoiceLine]:
            msg = "No time entries found between 2026-05-01 and 2026-05-31."
            raise RuntimeError(msg)

        app = self._make_app(tmp_path, failing_fetch)
        with app.test_client() as c:
            resp = c.post(
                "/lines/fetch",
                data={"fetch_start": "2026-05-01", "fetch_end": "2026-05-31"},
            )
        assert resp.status_code == 200
        assert _toast_kind(resp) == "err"
        assert "No time entries found" in _toast_msg(resp)
        inv = app.state["invoice"]  # type: ignore[attr-defined]
        assert len(inv.lines) == 2  # original lines untouched
        assert inv.period_start == date(2026, 6, 1)  # period untouched

    def test_fetch_invalid_dates_rejected(self, tmp_path: Path) -> None:
        app = self._make_app(tmp_path, lambda *_args: [])
        with app.test_client() as c:
            resp = c.post("/lines/fetch", data={"fetch_start": "", "fetch_end": ""})
        assert _toast_kind(resp) == "err"
        assert "valid import range" in _toast_msg(resp)

    def test_fetch_end_before_start_rejected(self, tmp_path: Path) -> None:
        app = self._make_app(tmp_path, lambda *_args: [])
        with app.test_client() as c:
            resp = c.post(
                "/lines/fetch",
                data={"fetch_start": "2026-06-30", "fetch_end": "2026-06-01"},
            )
        assert "must not be before" in _toast_msg(resp)

    def test_fetch_without_callback_reports_unavailable(self, tmp_path: Path) -> None:
        app = self._make_app(tmp_path, None)
        with app.test_client() as c:
            resp = c.post(
                "/lines/fetch",
                data={"fetch_start": "2026-06-01", "fetch_end": "2026-06-30"},
            )
        assert "not available" in _toast_msg(resp)

    def test_editor_has_source_bar(self, client: FlaskClient) -> None:
        resp = client.get("/")
        assert b'id="source-bar"' in resp.data
        assert b"Sync from Harvest" in resp.data
        assert b"Harvest source" in resp.data
        assert b'id="merge-on-fetch"' in resp.data
        assert b'id="fetch-start"' in resp.data
        assert b'id="fetch-end"' in resp.data

    def test_fetch_merges_duplicates_when_checked(self, tmp_path: Path) -> None:
        def dup_fetch(ps: date, pe: date) -> list[InvoiceLine]:
            return [
                InvoiceLine(concept="Programming", unit_price=172.5, quantity=92.0),
                InvoiceLine(concept="Programming", unit_price=172.5, quantity=160.0),
                InvoiceLine(concept="Infra", unit_price=172.5, quantity=47.5),
            ]

        app = self._make_app(tmp_path, dup_fetch)
        with app.test_client() as c:
            resp = c.post(
                "/lines/fetch",
                data={
                    "fetch_start": "2026-06-01",
                    "fetch_end": "2026-06-30",
                    "merge_duplicates": "on",
                },
            )
        inv = app.state["invoice"]  # type: ignore[attr-defined]
        assert len(inv.lines) == 2
        assert inv.lines[0].quantity == pytest.approx(252.0)
        assert "2 line items added" in _toast_msg(resp)

    def test_fetch_keeps_raw_lines_when_unchecked(self, tmp_path: Path) -> None:
        def dup_fetch(ps: date, pe: date) -> list[InvoiceLine]:
            return [
                InvoiceLine(concept="Programming", unit_price=172.5, quantity=92.0),
                InvoiceLine(concept="Programming", unit_price=172.5, quantity=160.0),
            ]

        app = self._make_app(tmp_path, dup_fetch)
        with app.test_client() as c:
            c.post(
                "/lines/fetch",
                data={"fetch_start": "2026-06-01", "fetch_end": "2026-06-30"},
            )
        inv = app.state["invoice"]  # type: ignore[attr-defined]
        assert len(inv.lines) == 2


class TestSourceBar:
    """The Harvest source bar: sync-state pill and Manage panel toggle."""

    def _make_app(self, tmp_path: Path, **kwargs):  # noqa: ANN003, ANN202
        app = create_app(
            lines=[],
            issuer=_fake_issuer(),
            client=_fake_client(),
            invoice_number="2026-06",
            output_path=tmp_path / "invoice.pdf",
            period_start=date(2026, 6, 1),
            period_end=date(2026, 6, 30),
            fetch_callback=lambda *_a: [
                InvoiceLine(concept="W", unit_price=100.0, quantity=10.0, user="Al")
            ],
            **kwargs,
        )
        app.config["TESTING"] = True
        return app

    def test_starts_not_synced(self, tmp_path: Path) -> None:
        with self._make_app(tmp_path).test_client() as c:
            body = c.get("/").data
        assert b"Not synced" in body
        assert b">Synced<" not in body
        assert b"No hours imported yet" in body

    def test_manage_toggle_is_server_tracked(self, tmp_path: Path) -> None:
        app = self._make_app(tmp_path)
        with app.test_client() as c:
            assert b"source-manage open" not in c.get("/").data
            opened = c.post("/source/toggle").data
            assert b"source-manage open" in opened
            assert app.state["source_open"] is True  # type: ignore[attr-defined]
            closed = c.post("/source/toggle").data
            assert b"source-manage open" not in closed

    def test_sync_flips_pill_and_collapses_panel(self, tmp_path: Path) -> None:
        app = self._make_app(tmp_path)
        with app.test_client() as c:
            c.post("/source/toggle")  # open the panel
            resp = c.post(
                "/lines/fetch",
                data={"fetch_start": "2026-06-01", "fetch_end": "2026-06-30"},
            )
        assert b">Synced<" in resp.data
        assert b"Re-sync" in resp.data
        assert b"source-manage open" not in resp.data  # collapsed after sync
        assert app.state["source_open"] is False  # type: ignore[attr-defined]

    def test_sync_toast_has_title_and_body(self, tmp_path: Path) -> None:
        app = self._make_app(tmp_path)
        with app.test_client() as c:
            resp = c.post(
                "/lines/fetch",
                data={"fetch_start": "2026-06-01", "fetch_end": "2026-06-30"},
            )
        payload = _toast_payload(resp)
        assert payload["kind"] == "ok"
        assert payload["title"] == "Synced from Harvest"
        assert "line items added" in payload["body"]


class TestBillToSwitch:
    """POST /invoice/client switches the invoiced client mid-session."""

    def _clients(self) -> dict[str, dict[str, object]]:
        return {
            "Numtide": {
                "name": "Numtide Sarl",
                "address_line1": "Rue X 1",
                "address_line2": "1003 Lausanne",
                "country": "Switzerland",
                "tax_id": "CHE-000",
            },
            "Domestic": {
                "name": "Domestic S.L.",
                "address_line1": "Calle Y 2",
                "address_line2": "28000 Madrid",
                "country": "Spain",
                "tax_id": "B0000",
                "vat_rate": 0.21,
                "extra_lines": [{"concept": "Retainer", "unit_price": 100.0}],
            },
        }

    def _make_app(self, tmp_path: Path):  # noqa: ANN202
        clients = self._clients()
        app = create_app(
            lines=_fake_lines(),
            issuer=_fake_issuer(),
            client=clients["Numtide"],
            invoice_number="2026-06",
            output_path=tmp_path / "invoice.pdf",
            clients=clients,
        )
        app.config["TESTING"] = True
        return app

    def test_switch_updates_preview_billto(self, tmp_path: Path) -> None:
        app = self._make_app(tmp_path)
        with app.test_client() as c:
            assert b"Numtide Sarl" in c.get("/preview").data
            resp = c.post("/invoice/client", data={"client_key": "Domestic"})
            assert resp.status_code == 200
            preview = c.get("/preview")
        assert b"Domestic S.L." in preview.data
        assert b"Numtide Sarl" not in preview.data

    def test_switch_applies_vat_and_extras_keeps_lines(self, tmp_path: Path) -> None:
        app = self._make_app(tmp_path)
        with app.test_client() as c:
            # Edit a harvest line first: the edit must survive the switch
            c.post(
                "/lines/update/0",
                data={"concept": "Edited Task", "quantity": "40", "unit_price": "120"},
            )
            c.post("/invoice/client", data={"client_key": "Domestic"})
        inv = app.state["invoice"]  # type: ignore[attr-defined]
        concepts = [line.concept for line in inv.lines]
        assert "Edited Task" in concepts  # manual edit preserved, no re-fetch
        assert "Retainer" in concepts  # new client's extra line added
        assert all(line.vat_rate == 0.21 for line in inv.lines)

    def test_switch_back_removes_vat_and_extras(self, tmp_path: Path) -> None:
        app = self._make_app(tmp_path)
        with app.test_client() as c:
            c.post("/invoice/client", data={"client_key": "Domestic"})
            c.post("/invoice/client", data={"client_key": "Numtide"})
        inv = app.state["invoice"]  # type: ignore[attr-defined]
        concepts = [line.concept for line in inv.lines]
        assert "Retainer" not in concepts  # other client's extras removed
        assert all(line.vat_rate == 0.0 for line in inv.lines)

    def test_unknown_key_is_noop(self, tmp_path: Path) -> None:
        app = self._make_app(tmp_path)
        with app.test_client() as c:
            resp = c.post("/invoice/client", data={"client_key": "Nope"})
            assert resp.status_code == 200
        assert app.state["current_client_key"] == "Numtide"  # type: ignore[attr-defined]

    def test_refetch_follows_switched_client(self, tmp_path: Path) -> None:
        clients = self._clients()
        app = create_app(
            lines=_fake_lines(),
            issuer=_fake_issuer(),
            client=clients["Numtide"],
            invoice_number="2026-06",
            output_path=tmp_path / "invoice.pdf",
            clients=clients,
            fetch_callback=lambda *_args: [
                InvoiceLine(concept="Fresh", unit_price=100.0, quantity=1.0)
            ],
        )
        app.config["TESTING"] = True
        with app.test_client() as c:
            c.post("/invoice/client", data={"client_key": "Domestic"})
            c.post(
                "/lines/fetch",
                data={"fetch_start": "2026-06-01", "fetch_end": "2026-06-30"},
            )
        inv = app.state["invoice"]  # type: ignore[attr-defined]
        concepts = [line.concept for line in inv.lines]
        assert "Fresh" in concepts
        assert "Retainer" in concepts  # switched client's extras applied
        assert all(line.vat_rate == 0.21 for line in inv.lines)

    def test_undo_after_switch_restores_client_too(self, tmp_path: Path) -> None:
        """Undo of a bill-to switch must restore the client with the lines."""
        app = self._make_app(tmp_path)
        with app.test_client() as c:
            c.post("/invoice/client", data={"client_key": "Domestic"})
            resp = c.post("/lines/undo")
            preview = c.get("/preview")
        # Bill-to and lines are consistent again: Numtide, no VAT, no extras
        assert app.state["current_client_key"] == "Numtide"  # type: ignore[attr-defined]
        assert app.state["client"] is app.state["clients"]["Numtide"]  # type: ignore[attr-defined]
        inv = app.state["invoice"]  # type: ignore[attr-defined]
        assert all(line.vat_rate == 0.0 for line in inv.lines)
        assert all(line.origin != "extra" for line in inv.lines)
        assert b"Numtide Sarl" in preview.data
        # The response carries the picker/inset refresh for the UI
        assert b"client-inset" in resp.data
        # Redo: back to Domestic with its VAT and extras
        with app.test_client() as c:
            c.post("/lines/redo")
        assert app.state["current_client_key"] == "Domestic"  # type: ignore[attr-defined]
        inv = app.state["invoice"]  # type: ignore[attr-defined]
        assert any(line.origin == "extra" for line in inv.lines)
        assert all(line.vat_rate == 0.21 for line in inv.lines)

    def test_editor_renders_picker(self, tmp_path: Path) -> None:
        app = self._make_app(tmp_path)
        with app.test_client() as c:
            resp = c.get("/")
        assert b'id="client-picker"' in resp.data
        assert b"client_key" in resp.data  # picker rows post the key
        assert b"Numtide Sarl" in resp.data
        assert b"Domestic S.L." in resp.data

    def test_editor_without_clients_links_settings(self, client: FlaskClient) -> None:
        resp = client.get("/")
        assert b"No clients configured yet" in resp.data


class TestExtraLinesInEditor:
    """Extra-origin lines survive fetch+merge and are marked in the editor."""

    def test_fetch_with_merge_keeps_extras(self, tmp_path: Path) -> None:
        def fetch_with_extras(ps: date, pe: date) -> list[InvoiceLine]:
            return [
                InvoiceLine(concept="Dev", unit_price=100.0, quantity=10.0),
                InvoiceLine(concept="Dev", unit_price=100.0, quantity=5.0),
                InvoiceLine(
                    concept="Retainer", unit_price=500.0, quantity=1.0, origin="extra"
                ),
            ]

        app = create_app(
            lines=_fake_lines(),
            issuer=_fake_issuer(),
            client=_fake_client(),
            invoice_number="2026-06",
            output_path=tmp_path / "invoice.pdf",
            fetch_callback=fetch_with_extras,
        )
        app.config["TESTING"] = True
        with app.test_client() as c:
            c.post(
                "/lines/fetch",
                data={
                    "fetch_start": "2026-06-01",
                    "fetch_end": "2026-06-30",
                    "merge_duplicates": "on",
                },
            )
        inv = app.state["invoice"]  # type: ignore[attr-defined]
        assert len(inv.lines) == 2
        extras = [ln for ln in inv.lines if ln.origin == "extra"]
        assert len(extras) == 1
        assert extras[0].concept == "Retainer"

    def test_editor_marks_extra_lines(self, tmp_path: Path) -> None:
        app = create_app(
            lines=[
                InvoiceLine(concept="Dev", unit_price=100.0, quantity=10.0),
                InvoiceLine(
                    concept="Retainer", unit_price=500.0, quantity=1.0, origin="extra"
                ),
            ],
            issuer=_fake_issuer(),
            client=_fake_client(),
            invoice_number="2026-06",
            output_path=tmp_path / "invoice.pdf",
        )
        app.config["TESTING"] = True
        with app.test_client() as c:
            resp = c.get("/")
        assert resp.data.count(b"pill-extra") == 1

    def test_settings_saves_extra_lines(self, tmp_path: Path) -> None:
        issuer = _fake_issuer()
        clients = {"Acme Corp": _fake_client()}
        clients_path = tmp_path / "state.db"
        state_db.save_clients(clients_path, clients)
        app = create_app(
            lines=_fake_lines(),
            issuer=issuer,
            client=clients["Acme Corp"],
            invoice_number="2026-06",
            output_path=tmp_path / "invoice.pdf",
            clients=clients,
            db_path=clients_path,
        )
        app.config["TESTING"] = True
        form = {
            "original_key": "Acme Corp",
            "key": "Acme Corp",
            "name": "Acme Corp Ltd.",
            "address_line1": "1 Acme Blvd",
            "address_line2": "EC1A 1BB London",
            "country": "United Kingdom",
            "tax_id": "GB000000000",
            "tax_id_label": "",
            "vat_rate": "",
            "extra_lines": "Monthly retainer ; 500 ; 1\nLicense ; 20 ; 3",
        }
        with app.test_client() as c:
            resp = c.post("/settings/clients/save", data=form)
            assert b"saved" in resp.data
            # Round-trips into the re-rendered textarea
            assert b"Monthly retainer ; 500.0 ; 1.0" in resp.data
        saved = state_db.get_clients(clients_path)
        assert saved["Acme Corp"]["extra_lines"] == [
            {"concept": "Monthly retainer", "unit_price": 500.0, "quantity": 1.0},
            {"concept": "License", "unit_price": 20.0, "quantity": 3.0},
        ]

    def test_settings_rejects_bad_extra_lines(self, tmp_path: Path) -> None:
        app = create_app(
            lines=_fake_lines(),
            issuer=_fake_issuer(),
            client=_fake_client(),
            invoice_number="2026-06",
            output_path=tmp_path / "invoice.pdf",
            clients={"Acme Corp": _fake_client()},
        )
        app.config["TESTING"] = True
        form = {
            "original_key": "Acme Corp",
            "key": "Acme Corp",
            "name": "Acme",
            "address_line1": "A",
            "address_line2": "B",
            "country": "C",
            "tax_id": "T",
            "extra_lines": "Retainer ; lots",
        }
        with app.test_client() as c:
            resp = c.post("/settings/clients/save", data=form)
        assert b"must be" in resp.data or b"expected" in resp.data


class TestServePdf:
    """GET /pdf serves the last generated file."""

    def test_pdf_404_before_generate(self, client: FlaskClient) -> None:
        resp = client.get("/pdf")
        assert resp.status_code == 404
        assert b"No PDF generated yet" in resp.data

    def test_pdf_served_when_present(self, tmp_path: Path) -> None:
        out = tmp_path / "invoice-2026-06.pdf"
        out.write_bytes(b"%PDF-1.7 fake for test")
        app = create_app(
            lines=_fake_lines(),
            issuer=_fake_issuer(),
            client=_fake_client(),
            invoice_number="2026-06",
            output_path=out,
        )
        app.config["TESTING"] = True
        with app.test_client() as c:
            resp = c.get("/pdf")
        assert resp.status_code == 200
        assert resp.mimetype == "application/pdf"
        assert resp.data.startswith(b"%PDF")
        assert "invoice-2026-06.pdf" in resp.headers["Content-Disposition"]

    def test_render_status_links_pdf(self, tmp_path: Path) -> None:
        """The success partial contains the open link."""
        app = create_app(
            lines=_fake_lines(),
            issuer=_fake_issuer(),
            client=_fake_client(),
            invoice_number="2026-06",
            output_path=tmp_path / "invoice.pdf",
        )
        with app.test_request_context():
            from flask import render_template  # noqa: PLC0415

            html = render_template(
                "partials/render_done.html", output_path="invoice.pdf"
            )
        assert 'href="/pdf"' in html
        assert 'target="_blank"' in html


class TestSettings:
    """In-app settings: issuer and clients managed through the editor."""

    def _make_app(self, tmp_path: Path):  # noqa: ANN202
        issuer = _fake_issuer()
        clients = {"Acme Corp": _fake_client(), "Other Client": _fake_client()}
        db_path = tmp_path / "state.db"
        state_db.save_issuer(db_path, issuer)
        state_db.save_clients(db_path, clients)
        app = create_app(
            lines=_fake_lines(),
            issuer=issuer,
            client=clients["Acme Corp"],
            invoice_number="2026-06",
            output_path=tmp_path / "invoice.pdf",
            clients=clients,
            db_path=db_path,
        )
        app.config["TESTING"] = True
        return app, db_path, db_path

    def _issuer_form(self, **overrides: str) -> dict[str, str]:
        base = {
            "name": "Jane Doe Consulting",
            "address_line1": "12 Example St",
            "address_line2": "10115 Berlin",
            "country": "Germany",
            "tax_id": "DE000000000",
            "tax_id_label": "VAT ID",
            "phone": "+49 30 0000",
            "email": "jane@example.com",
            "iban": "DE00 0000 0000 0000 0000 00",
            "bic": "EXAMPLEXXX",
            "date_format": "",
            "legal_note": "",
            "number_template": "",
        }
        base.update(overrides)
        return base

    def _client_form(self, **overrides: str) -> dict[str, str]:
        base = {
            "original_key": "",
            "key": "New Client",
            "name": "New Client Ltd.",
            "address_line1": "9 New St",
            "address_line2": "00000 Town",
            "country": "Norway",
            "tax_id": "NO000",
            "tax_id_label": "",
            "language": "",
            "vat_rate": "",
        }
        base.update(overrides)
        return base

    def test_settings_page_renders(self, tmp_path: Path) -> None:
        app, _, _ = self._make_app(tmp_path)
        with app.test_client() as c:
            resp = c.get("/settings")
        assert resp.status_code == 200
        assert b"Jane Doe Consulting" in resp.data
        assert b"Acme Corp" in resp.data
        assert b"Other Client" in resp.data

    def test_editor_links_settings(self, client: FlaskClient) -> None:
        resp = client.get("/")
        assert b'href="/settings"' in resp.data

    def test_issuer_save_updates_session_and_file(self, tmp_path: Path) -> None:
        app, issuer_path, _ = self._make_app(tmp_path)
        with app.test_client() as c:
            resp = c.post(
                "/settings/issuer",
                data=self._issuer_form(name="New Name S.L."),
            )
            assert b"Issuer saved" in resp.data
            # The preview reflects the new issuer immediately
            preview = c.get("/preview")
        assert b"New Name S.L." in preview.data
        assert state_db.get_issuer(issuer_path)["name"] == "New Name S.L."

    def test_issuer_save_missing_required_rejected(self, tmp_path: Path) -> None:
        app, issuer_path, _ = self._make_app(tmp_path)
        before = state_db.get_issuer(issuer_path)
        with app.test_client() as c:
            resp = c.post("/settings/issuer", data=self._issuer_form(name=""))
        assert b"Missing required fields" in resp.data
        assert state_db.get_issuer(issuer_path) == before  # untouched

    def test_client_edit_updates_current_invoice(self, tmp_path: Path) -> None:
        app, _, clients_path = self._make_app(tmp_path)
        with app.test_client() as c:
            resp = c.post(
                "/settings/clients/save",
                data=self._client_form(
                    original_key="Acme Corp",
                    key="Acme Corp",
                    name="Acme Corp International",
                ),
            )
            assert b"saved" in resp.data
            preview = c.get("/preview")
        assert b"Acme Corp International" in preview.data
        saved = state_db.get_clients(clients_path)
        assert saved["Acme Corp"]["name"] == "Acme Corp International"

    def test_client_add_and_delete(self, tmp_path: Path) -> None:
        app, _, clients_path = self._make_app(tmp_path)
        with app.test_client() as c:
            c.post("/settings/clients/save", data=self._client_form())
            assert "New Client" in state_db.get_clients(clients_path)
            resp = c.post(
                "/settings/clients/delete", data={"original_key": "New Client"}
            )
            assert b"deleted" in resp.data
        assert "New Client" not in state_db.get_clients(clients_path)

    def test_delete_current_client_rejected(self, tmp_path: Path) -> None:
        app, _, clients_path = self._make_app(tmp_path)
        with app.test_client() as c:
            resp = c.post(
                "/settings/clients/delete", data={"original_key": "Acme Corp"}
            )
        assert b"Cannot delete" in resp.data
        assert "Acme Corp" in state_db.get_clients(clients_path)

    def test_client_language_saved_and_validated(self, tmp_path: Path) -> None:
        app, _, clients_path = self._make_app(tmp_path)
        with app.test_client() as c:
            resp = c.post(
                "/settings/clients/save",
                data=self._client_form(
                    original_key="Acme Corp", key="Acme Corp", language="es"
                ),
            )
            assert b"saved" in resp.data
            resp = c.post(
                "/settings/clients/save",
                data=self._client_form(
                    original_key="Acme Corp", key="Acme Corp", language="xx"
                ),
            )
            assert b"Unsupported language" in resp.data
        saved = state_db.get_clients(clients_path)
        assert saved["Acme Corp"]["language"] == "es"

    def test_settings_saves_emit_toast_headers(self, tmp_path: Path) -> None:
        app, _, _ = self._make_app(tmp_path)
        with app.test_client() as c:
            ok = c.post("/settings/issuer", data=self._issuer_form())
            assert _toast_kind(ok) == "ok"
            bad = c.post("/settings/issuer", data=self._issuer_form(name=""))
            assert _toast_kind(bad) == "err"
            saved = c.post("/settings/clients/save", data=self._client_form())
            assert _toast_kind(saved) == "ok"
            deleted = c.post(
                "/settings/clients/delete", data={"original_key": "New Client"}
            )
            assert _toast_kind(deleted) == "ok"

    def test_client_invalid_vat_rejected(self, tmp_path: Path) -> None:
        app, _, _ = self._make_app(tmp_path)
        with app.test_client() as c:
            resp = c.post(
                "/settings/clients/save",
                data=self._client_form(vat_rate="21"),
            )
        assert b"between 0 and 1" in resp.data

    def test_rename_onto_existing_key_rejected(self, tmp_path: Path) -> None:
        """Renaming a client to another client's key must not overwrite it."""
        app, _, clients_path = self._make_app(tmp_path)
        before = state_db.get_clients(clients_path)
        with app.test_client() as c:
            resp = c.post(
                "/settings/clients/save",
                data=self._client_form(
                    original_key="Other Client",
                    key="Acme Corp",  # collides with the existing entry
                    name="Other Client Renamed",
                ),
            )
        assert b"already exists" in resp.data
        assert state_db.get_clients(clients_path) == before
        assert set(state_db.get_clients(clients_path)) == {
            "Acme Corp",
            "Other Client",
        }

    def test_saved_client_stays_open(self, tmp_path: Path) -> None:
        """M2: the accordion of the just-saved client remains open."""
        app, _, _ = self._make_app(tmp_path)
        with app.test_client() as c:
            resp = c.post(
                "/settings/clients/save",
                data=self._client_form(original_key="Other Client", key="Other Client"),
            )
        html = resp.data.decode()
        open_idx = html.index('class="acc-item open"')
        assert "Other Client" in html[open_idx : open_idx + 900]

    def test_client_email_saved(self, tmp_path: Path) -> None:
        app, _, clients_path = self._make_app(tmp_path)
        with app.test_client() as c:
            resp = c.post(
                "/settings/clients/save",
                data=self._client_form(
                    original_key="Acme Corp",
                    key="Acme Corp",
                    email="billing@acme.example",
                ),
            )
            assert b"saved" in resp.data
        saved = state_db.get_clients(clients_path)
        assert saved["Acme Corp"]["email"] == "billing@acme.example"

    def test_client_invalid_email_rejected(self, tmp_path: Path) -> None:
        app, _, clients_path = self._make_app(tmp_path)
        before = state_db.get_clients(clients_path)
        with app.test_client() as c:
            resp = c.post(
                "/settings/clients/save",
                data=self._client_form(
                    original_key="Acme Corp", key="Acme Corp", email="not-an-email"
                ),
            )
        assert b"valid address" in resp.data
        assert state_db.get_clients(clients_path) == before

    def test_no_paths_saves_session_only(self, tmp_path: Path) -> None:
        """Demo mode: settings apply in memory, nothing written anywhere."""
        app = create_app(
            lines=_fake_lines(),
            issuer=_fake_issuer(),
            client=_fake_client(),
            invoice_number="2026-06",
            output_path=tmp_path / "invoice.pdf",
        )
        app.config["TESTING"] = True
        with app.test_client() as c:
            resp = c.post(
                "/settings/issuer", data=self._issuer_form(name="Session Only")
            )
            preview = c.get("/preview")
        assert b"this session only" in resp.data
        assert b"Session Only" in preview.data


class TestUndo:
    """Multi-level undo/redo history for line-item mutations."""

    def test_undo_restores_dropped_line(self, client: FlaskClient) -> None:
        client.post("/lines/drop/0")
        resp = client.post("/lines/undo")
        assert resp.status_code == 200
        assert b"Backend Development" in resp.data
        assert resp.data.count(b'class="row-check"') == 2

    def test_redo_reapplies_undone_change(self, client: FlaskClient) -> None:
        client.post("/lines/drop/0")
        client.post("/lines/undo")  # restore
        resp = client.post("/lines/redo")  # re-apply the drop
        assert b"Backend Development" not in resp.data

    def test_multi_level_undo_walks_back_several_edits(
        self, client: FlaskClient
    ) -> None:
        # Three structural edits, then three undos should peel each back.
        client.post("/lines/add")  # 3 rows
        client.post("/lines/add")  # 4 rows
        client.post("/lines/drop/0")  # 3 rows (Backend gone)
        assert client.post("/lines/undo").data.count(b'class="row-check"') == 4
        assert client.post("/lines/undo").data.count(b'class="row-check"') == 3
        resp = client.post("/lines/undo")
        assert resp.data.count(b'class="row-check"') == 2  # back to the start
        assert b"Backend Development" in resp.data

    def test_new_edit_clears_redo(self, client: FlaskClient) -> None:
        client.post("/lines/drop/0")
        client.post("/lines/undo")  # redo now available
        client.post("/lines/add")  # a fresh edit invalidates redo
        resp = client.post("/lines/redo")  # no-op
        # Still the post-add state: Backend restored + the added blank row.
        assert b"Backend Development" in resp.data
        assert resp.data.count(b'class="row-check"') == 3

    def test_undo_without_history_is_noop(self, client: FlaskClient) -> None:
        resp = client.post("/lines/undo")
        assert resp.status_code == 200
        assert b"Backend Development" in resp.data
        assert resp.data.count(b'class="row-check"') == 2

    def test_redo_without_history_is_noop(self, client: FlaskClient) -> None:
        resp = client.post("/lines/redo")
        assert resp.status_code == 200
        assert resp.data.count(b'class="row-check"') == 2

    def test_undo_restores_lines_after_fetch(self, tmp_path: Path) -> None:
        app = create_app(
            lines=_fake_lines(),
            issuer=_fake_issuer(),
            client=_fake_client(),
            invoice_number="2026-06",
            output_path=tmp_path / "invoice.pdf",
            fetch_callback=lambda *_args: [
                InvoiceLine(concept="Fetched", unit_price=1.0, quantity=1.0)
            ],
        )
        app.config["TESTING"] = True
        with app.test_client() as c:
            c.post(
                "/lines/fetch",
                data={"fetch_start": "2026-06-01", "fetch_end": "2026-06-30"},
            )
            resp = c.post("/lines/undo")
        assert b"Backend Development" in resp.data
        inv = app.state["invoice"]  # type: ignore[attr-defined]
        assert len(inv.lines) == 2

    def test_undo_restores_edited_line(self, client: FlaskClient) -> None:
        client.post(
            "/lines/update/0",
            data={"concept": "Changed", "quantity": "40", "unit_price": "120"},
        )
        resp = client.post("/lines/undo")
        assert b"Backend Development" in resp.data
        assert b"Changed" not in resp.data

    def test_editor_has_undo_and_redo_buttons(self, client: FlaskClient) -> None:
        resp = client.get("/")
        assert b"/lines/undo" in resp.data
        assert b"/lines/redo" in resp.data
        assert b'id="redo-btn"' in resp.data


class TestReviewPolish:
    """M1/M2/L2 from the adversarial review."""

    def test_stale_range_guard_in_editor_js(self, client: FlaskClient) -> None:
        """M1: fetching with use-period on and an empty period is blocked."""
        resp = client.get("/")
        assert b"Never fall back to a stale range" in resp.data
        assert b"Set the invoice billing period first" in resp.data

    def test_custom_terms_label_when_due_before_issue(
        self, client: FlaskClient
    ) -> None:
        """L2: due date before issue renders Custom, not 'Net -N'."""
        resp = client.post(
            "/meta/update",
            data={
                "number": "2026-06",
                "issue_date": "2026-07-06",
                "due_date": "2026-07-01",
                "legal_note": "",
            },
        )
        assert b"Custom" in resp.data
        assert b"Net -" not in resp.data
        assert b"in -" not in resp.data

    def test_number_shown_once_and_crumb_follows_edits(
        self, client: FlaskClient
    ) -> None:
        """The details card must not repeat the Number input's value; the
        header crumb is the single display and follows meta edits."""
        page = client.get("/").data
        assert b"inv-no-head" not in page  # old duplicate label is gone
        # Number renders as the crumb and as the input value, nothing else.
        assert page.count(b"Invoice 2026-06") == 1
        assert b'id="inv-no-crumb"' in page
        resp = client.post("/meta/update", data={"number": "INV-99"})
        assert b'id="inv-no-crumb"' in resp.data
        assert b"/ Invoice INV-99" in resp.data


class TestMergeDuplicates:
    """One-click consolidation of per-user duplicate lines."""

    def _make_app(self, lines: list[InvoiceLine], tmp_path: Path):  # noqa: ANN202
        app = create_app(
            lines=lines,
            issuer=_fake_issuer(),
            client=_fake_client(),
            invoice_number="2026-06",
            output_path=tmp_path / "invoice.pdf",
        )
        app.config["TESTING"] = True
        return app

    def test_identical_lines_are_summed(self, tmp_path: Path) -> None:
        lines = [
            InvoiceLine(concept="Acme - Programming", unit_price=172.5, quantity=92.0),
            InvoiceLine(concept="Acme - Infra", unit_price=172.5, quantity=183.99),
            InvoiceLine(concept="Acme - Programming", unit_price=172.5, quantity=160.0),
            InvoiceLine(concept="Acme - Programming", unit_price=172.5, quantity=90.0),
        ]
        app = self._make_app(lines, tmp_path)
        with app.test_client() as c:
            resp = c.post("/lines/merge-duplicates")
            assert resp.status_code == 200
        inv = app.state["invoice"]  # type: ignore[attr-defined]
        assert len(inv.lines) == 2
        # First-occurrence order preserved; quantities summed
        assert inv.lines[0].concept == "Acme - Programming"
        assert inv.lines[0].quantity == pytest.approx(342.0)
        assert inv.lines[1].concept == "Acme - Infra"
        assert inv.lines[1].quantity == pytest.approx(183.99)

    def test_different_rates_stay_separate(self, tmp_path: Path) -> None:
        lines = [
            InvoiceLine(concept="Acme - Programming", unit_price=172.5, quantity=10.0),
            InvoiceLine(concept="Acme - Programming", unit_price=150.0, quantity=5.0),
        ]
        app = self._make_app(lines, tmp_path)
        with app.test_client() as c:
            c.post("/lines/merge-duplicates")
        inv = app.state["invoice"]  # type: ignore[attr-defined]
        assert len(inv.lines) == 2

    def test_totals_unchanged_by_merge(self, tmp_path: Path) -> None:
        lines = [
            InvoiceLine(concept="Acme - Programming", unit_price=172.5, quantity=92.0),
            InvoiceLine(concept="Acme - Programming", unit_price=172.5, quantity=160.0),
            InvoiceLine(concept="Acme - Infra", unit_price=172.5, quantity=47.5),
        ]
        app = self._make_app(lines, tmp_path)
        before = app.state["invoice"].grand_total  # type: ignore[attr-defined]
        with app.test_client() as c:
            c.post("/lines/merge-duplicates")
        after = app.state["invoice"].grand_total  # type: ignore[attr-defined]
        assert after == pytest.approx(before)


class TestLogo:
    def test_logo_served(self, client: FlaskClient) -> None:
        resp = client.get("/static/harvest-logo.svg")
        assert resp.status_code == 200
        assert b"<svg" in resp.data

    def test_editor_references_logo(self, client: FlaskClient) -> None:
        resp = client.get("/")
        assert b"/static/harvest-logo.svg" in resp.data


class TestStyleCss:
    def test_style_css_200(self, client: FlaskClient) -> None:
        resp = client.get("/style.css")
        assert resp.status_code == 200
        assert resp.content_type.startswith("text/css")

    def test_style_css_contains_known_selector(self, client: FlaskClient) -> None:
        resp = client.get("/style.css")
        assert b"table.items" in resp.data

    def test_favicon_served(self, client: FlaskClient) -> None:
        resp = client.get("/favicon.ico")
        assert resp.status_code == 200
        assert resp.mimetype == "image/svg+xml"
        assert b"<svg" in resp.data


class TestImportRoster:
    """Person chips: choose whose hours the invoice includes."""

    def _team_fetch(self, ps: date, pe: date) -> list[InvoiceLine]:
        return [
            InvoiceLine(concept="Dev", unit_price=100.0, quantity=10.0, user="Alice"),
            InvoiceLine(concept="Ops", unit_price=90.0, quantity=5.0, user="Bob"),
        ]

    def _make_app(self, tmp_path: Path, **kwargs):  # noqa: ANN003, ANN202
        app = create_app(
            lines=_fake_lines(),
            issuer=_fake_issuer(),
            client=_fake_client(),
            invoice_number="2026-06",
            output_path=tmp_path / "invoice.pdf",
            **kwargs,
        )
        app.config["TESTING"] = True
        return app

    def test_startup_roster_rendered(self, tmp_path: Path) -> None:
        raw = self._team_fetch(date(2026, 6, 1), date(2026, 6, 30))
        app = self._make_app(tmp_path, import_raw=raw)
        with app.test_client() as c:
            resp = c.get("/")
        assert resp.data.count(b'class="roster-row on') == 2
        assert b"Alice" in resp.data
        assert b"Bob" in resp.data
        assert b"Who to include" in resp.data

    def test_fetch_renders_roster(self, tmp_path: Path) -> None:
        app = self._make_app(tmp_path, fetch_callback=self._team_fetch)
        with app.test_client() as c:
            resp = c.post(
                "/lines/fetch",
                data={"fetch_start": "2026-06-01", "fetch_end": "2026-06-30"},
            )
        assert b'id="source-bar"' in resp.data  # the bar is refreshed OOB
        assert resp.data.count(b'class="roster-row on') == 2
        assert b">Synced<" in resp.data  # status pill flips to Synced

    def test_single_person_import(self, tmp_path: Path) -> None:
        def solo(ps: date, pe: date) -> list[InvoiceLine]:
            return [
                InvoiceLine(concept="Dev", unit_price=100.0, quantity=8.0, user="Al")
            ]

        app = self._make_app(tmp_path, fetch_callback=solo)
        with app.test_client() as c:
            resp = c.post(
                "/lines/fetch",
                data={"fetch_start": "2026-06-01", "fetch_end": "2026-06-30"},
            )
        assert resp.data.count(b'class="roster-row') == 1
        assert b"Al" in resp.data

    def test_toggle_excludes_person(self, tmp_path: Path) -> None:
        app = self._make_app(tmp_path, fetch_callback=self._team_fetch)
        with app.test_client() as c:
            c.post(
                "/lines/fetch",
                data={"fetch_start": "2026-06-01", "fetch_end": "2026-06-30"},
            )
            resp = c.post("/lines/people", data={"toggle": "Bob"})
        inv = app.state["invoice"]  # type: ignore[attr-defined]
        assert [ln.user for ln in inv.lines] == ["Alice"]
        assert b"1 of 2" in resp.data
        # Toggle back in re-derives both, without re-fetching
        with app.test_client() as c:
            c.post("/lines/people", data={"toggle": "Bob"})
        assert len(app.state["invoice"].lines) == 2  # type: ignore[attr-defined]

    def test_everyone_and_clear(self, tmp_path: Path) -> None:
        app = self._make_app(tmp_path, fetch_callback=self._team_fetch)
        with app.test_client() as c:
            c.post(
                "/lines/fetch",
                data={"fetch_start": "2026-06-01", "fetch_end": "2026-06-30"},
            )
            resp = c.post("/lines/people", data={"none": "1"})
            assert b"0 of 2" in resp.data
            assert app.state["invoice"].lines == []  # type: ignore[attr-defined]
            resp = c.post("/lines/people", data={"all": "1"})
            assert b"2 of 2" in resp.data
        assert len(app.state["invoice"].lines) == 2  # type: ignore[attr-defined]

    def test_source_bar_renders_once(self, tmp_path: Path) -> None:
        """The source bar is a single top-level OOB fragment on a sync."""
        app = self._make_app(tmp_path, fetch_callback=self._team_fetch)
        with app.test_client() as c:
            resp = c.post(
                "/lines/fetch",
                data={"fetch_start": "2026-06-01", "fetch_end": "2026-06-30"},
            )
        assert resp.data.decode().count('id="source-bar"') == 1

    def test_manual_row_survives_rederive(self, tmp_path: Path) -> None:
        """H1: rows added by hand are preserved when chips re-slice."""
        app = self._make_app(tmp_path, fetch_callback=self._team_fetch)
        with app.test_client() as c:
            c.post(
                "/lines/fetch",
                data={"fetch_start": "2026-06-01", "fetch_end": "2026-06-30"},
            )
            c.post("/lines/add")
            c.post(
                "/lines/update/2",
                data={"concept": "Hand-added fee", "quantity": "1", "unit_price": "50"},
            )
            c.post("/lines/people", data={"toggle": "Bob"})
        inv = app.state["invoice"]  # type: ignore[attr-defined]
        concepts = [ln.concept for ln in inv.lines]
        assert "Hand-added fee" in concepts  # manual row survived
        assert "Ops" not in concepts  # Bob's imported line excluded

    def test_dirty_edit_shows_passive_roster_hint(self, tmp_path: Path) -> None:
        """H1: editing an imported line surfaces a passive caveat (not a
        blocking confirm) near the roster."""
        app = self._make_app(tmp_path, fetch_callback=self._team_fetch)
        with app.test_client() as c:
            resp = c.post(
                "/lines/fetch",
                data={"fetch_start": "2026-06-01", "fetch_end": "2026-06-30"},
            )
            assert b'class="roster-hint"' not in resp.data  # clean after fetch
            # No blocking confirm dialog anywhere on the sync/roster path.
            assert b"hx-confirm" not in resp.data
            resp = c.post(
                "/lines/update/0",
                data={"concept": "Edited", "quantity": "10", "unit_price": "100"},
            )
            assert b'class="roster-hint"' in resp.data  # passive hint shown
            assert b"hx-confirm" not in resp.data
            # A re-derive clears the dirty flag again
            resp = c.post("/lines/people", data={"toggle": "Bob"})
            assert b'class="roster-hint"' not in resp.data

    def test_undo_restores_import_generation(self, tmp_path: Path) -> None:
        """H2: undo after a second fetch restores the earlier import too."""

        def by_range(ps: date, pe: date) -> list[InvoiceLine]:
            if ps.month == 6:
                return [
                    InvoiceLine(
                        concept="June", unit_price=100.0, quantity=10.0, user="Alice"
                    ),
                    InvoiceLine(
                        concept="JuneOps", unit_price=90.0, quantity=5.0, user="Bob"
                    ),
                ]
            return [
                InvoiceLine(
                    concept="July", unit_price=100.0, quantity=7.0, user="Carol"
                )
            ]

        app = self._make_app(tmp_path, fetch_callback=by_range)
        with app.test_client() as c:
            c.post(
                "/lines/fetch",
                data={"fetch_start": "2026-06-01", "fetch_end": "2026-06-30"},
            )
            c.post(
                "/lines/fetch",
                data={"fetch_start": "2026-07-01", "fetch_end": "2026-07-31"},
            )
            resp = c.post("/lines/undo")
            # The roster note reflects the restored June import (15h, 2 people)
            assert b"15h" in resp.data
            assert b"2 people" in resp.data
            # A chip toggle now derives from the June import, not July
            c.post("/lines/people", data={"toggle": "Bob"})
        inv = app.state["invoice"]  # type: ignore[attr-defined]
        assert [ln.concept for ln in inv.lines] == ["June"]
        assert app.state["last_fetch_range"] == (  # type: ignore[attr-defined]
            date(2026, 6, 1),
            date(2026, 6, 30),
        )

    def test_toggle_is_undoable(self, tmp_path: Path) -> None:
        app = self._make_app(tmp_path, fetch_callback=self._team_fetch)
        with app.test_client() as c:
            c.post(
                "/lines/fetch",
                data={"fetch_start": "2026-06-01", "fetch_end": "2026-06-30"},
            )
            c.post("/lines/people", data={"none": "1"})
            c.post("/lines/undo")
        assert len(app.state["invoice"].lines) == 2  # type: ignore[attr-defined]


class TestIssuerDefaultsSettings:
    """harvest_user / default_bill_to editable through Settings."""

    def _make_app(self, tmp_path: Path):  # noqa: ANN202
        issuer = _fake_issuer()
        clients = {"Numtide": _fake_client()}
        issuer_path = tmp_path / "state.db"
        state_db.save_issuer(issuer_path, issuer)
        app = create_app(
            lines=_fake_lines(),
            issuer=issuer,
            client=clients["Numtide"],
            invoice_number="2026-06",
            output_path=tmp_path / "invoice.pdf",
            clients=clients,
            db_path=issuer_path,
        )
        app.config["TESTING"] = True
        return app, issuer_path

    def _form(self, **overrides: str) -> dict[str, str]:
        base = {
            "name": "Jane Doe Consulting",
            "address_line1": "12 Example St",
            "address_line2": "10115 Berlin",
            "country": "Germany",
            "tax_id": "DE000000000",
            "tax_id_label": "",
            "phone": "+49 30 0000",
            "email": "jane@example.com",
            "iban": "DE00",
            "bic": "EXX",
            "date_format": "",
            "legal_note": "",
            "number_template": "",
            "harvest_user": "",
            "default_bill_to": "",
        }
        base.update(overrides)
        return base

    def test_defaults_saved(self, tmp_path: Path) -> None:
        app, issuer_path = self._make_app(tmp_path)
        with app.test_client() as c:
            resp = c.post(
                "/settings/issuer",
                data=self._form(harvest_user="Aldo Borrero", default_bill_to="Numtide"),
            )
            assert b"Issuer saved" in resp.data
        saved = state_db.get_issuer(issuer_path)
        assert saved["harvest_user"] == "Aldo Borrero"
        assert saved["default_bill_to"] == "Numtide"

    def test_unknown_default_bill_to_rejected(self, tmp_path: Path) -> None:
        app, issuer_path = self._make_app(tmp_path)
        before = state_db.get_issuer(issuer_path)
        with app.test_client() as c:
            resp = c.post("/settings/issuer", data=self._form(default_bill_to="Nope"))
        assert b"not a clients.json key" in resp.data
        assert state_db.get_issuer(issuer_path) == before

    def test_settings_page_shows_default_fields(self, tmp_path: Path) -> None:
        app, _ = self._make_app(tmp_path)
        with app.test_client() as c:
            resp = c.get("/settings")
        assert b'name="harvest_user"' in resp.data
        assert b'name="default_bill_to"' in resp.data


class TestCsrfGuard:
    """Mutating requests must be same-origin (local editor only)."""

    def test_cross_origin_post_rejected(self, client: FlaskClient) -> None:
        resp = client.post("/lines/add", headers={"Origin": "https://evil.example"})
        assert resp.status_code == 403

    def test_cross_origin_referer_rejected(self, client: FlaskClient) -> None:
        resp = client.post(
            "/settings/issuer", headers={"Referer": "https://evil.example/x"}
        )
        assert resp.status_code == 403

    def test_local_origin_allowed(self, client: FlaskClient) -> None:
        resp = client.post("/lines/add", headers={"Origin": "http://localhost"})
        assert resp.status_code == 200

    def test_no_origin_allowed(self, client: FlaskClient) -> None:
        """htmx same-origin posts may omit Origin; those stay allowed."""
        resp = client.post("/lines/add")
        assert resp.status_code == 200

    def test_get_unaffected(self, client: FlaskClient) -> None:
        resp = client.get("/", headers={"Origin": "https://evil.example"})
        assert resp.status_code == 200


class TestReorder:
    """POST /lines/reorder applies the drag-and-drop order."""

    def test_reorder_applies_permutation(self, client: FlaskClient) -> None:
        resp = client.post("/lines/reorder", data={"order": "1,0"})
        assert resp.status_code == 200
        # "Code Review" (was index 1) now renders before "Backend Development"
        assert resp.data.index(b"Code Review") < resp.data.index(b"Backend Development")

    def test_reorder_is_undoable(self, client: FlaskClient) -> None:
        client.post("/lines/reorder", data={"order": "1,0"})
        resp = client.post("/lines/undo")
        assert resp.data.index(b"Backend Development") < resp.data.index(b"Code Review")

    def test_incomplete_or_bad_order_ignored(self, client: FlaskClient) -> None:
        for bad in ("0", "0,0", "0,2", "a,b", ""):
            resp = client.post("/lines/reorder", data={"order": bad})
            assert resp.status_code == 200
            assert resp.data.index(b"Backend Development") < resp.data.index(
                b"Code Review"
            )

    def test_editor_has_drag_handles(self, client: FlaskClient) -> None:
        resp = client.get("/")
        assert resp.data.count(b'class="drag-handle"') == 2
        assert b"/lines/reorder" in resp.data


def _make_app(tmp_path: Path, **overrides: object):  # noqa: ANN202
    kwargs: dict[str, object] = {
        "lines": _fake_lines(),
        "issuer": _fake_issuer(),
        "client": _fake_client(),
        "invoice_number": "2026-06",
        "output_path": tmp_path / "invoice-2026-06.pdf",
    }
    kwargs.update(overrides)
    app = create_app(**kwargs)  # type: ignore[arg-type]
    app.config["TESTING"] = True
    return app


class TestDraftPersistence:
    """Edits autosave to the state DB and resume in the next session."""

    def test_edit_autosaves_draft(self, tmp_path: Path) -> None:
        db = tmp_path / "state.db"
        c = _make_app(tmp_path, db_path=db).test_client()
        c.post(
            "/lines/update/0",
            data={"concept": "Edited Concept", "quantity": "40", "unit_price": "120"},
        )
        draft = state_db.get_draft(db)
        assert draft is not None
        assert draft["key"] == "2026-06"
        assert draft["invoice"]["lines"][0]["concept"] == "Edited Concept"

    def test_next_session_restores_matching_draft_silently(
        self, tmp_path: Path
    ) -> None:
        db = tmp_path / "state.db"
        c1 = _make_app(tmp_path, db_path=db).test_client()
        c1.post(
            "/lines/update/0",
            data={"concept": "Edited Concept", "quantity": "40", "unit_price": "120"},
        )
        c2 = _make_app(tmp_path, db_path=db).test_client()
        resp = c2.get("/")
        # Silent restore: the edit is back, but there is no banner.
        assert b"Edited Concept" in resp.data
        assert b"Draft restored" not in resp.data

    def test_renamed_invoice_still_resumes(self, tmp_path: Path) -> None:
        """The draft key is the seed number, so editing the visible invoice
        number does not orphan the draft on restart."""
        db = tmp_path / "state.db"
        c1 = _make_app(tmp_path, db_path=db).test_client()
        c1.post("/meta/update", data={"number": "FINAL-042"})
        c2 = _make_app(tmp_path, db_path=db).test_client()
        resp = c2.get("/")
        assert b"FINAL-042" in resp.data

    def test_other_months_draft_is_ignored(self, tmp_path: Path) -> None:
        db = tmp_path / "state.db"
        c1 = _make_app(tmp_path, db_path=db).test_client()
        c1.post(
            "/lines/update/0",
            data={"concept": "Edited Concept", "quantity": "40", "unit_price": "120"},
        )
        c2 = _make_app(tmp_path, db_path=db, invoice_number="2026-07").test_client()
        resp = c2.get("/")
        assert b"Draft restored" not in resp.data
        assert b"Edited Concept" not in resp.data
        assert b"Backend Development" in resp.data  # fresh seed lines

    def test_discard_returns_to_fresh_state(self, tmp_path: Path) -> None:
        db = tmp_path / "state.db"
        c1 = _make_app(tmp_path, db_path=db).test_client()
        c1.post(
            "/lines/update/0",
            data={"concept": "Edited Concept", "quantity": "40", "unit_price": "120"},
        )
        c2 = _make_app(tmp_path, db_path=db).test_client()
        resp = c2.post("/draft/discard")
        assert resp.status_code == 200
        assert "Draft discarded" in _toast_msg(resp)
        assert b"Edited Concept" not in resp.data
        assert b"Backend Development" in resp.data
        assert state_db.get_draft(db) is None

    def test_no_db_means_no_draft_and_discard_is_safe(self, tmp_path: Path) -> None:
        c = _make_app(tmp_path).test_client()  # db_path=None (demo/tests)
        resp = c.get("/")
        assert b"Draft restored" not in resp.data
        assert c.post("/lines/add").status_code == 200
        assert c.post("/draft/discard").status_code == 200

    def test_corrupt_draft_is_ignored_and_cleared(self, tmp_path: Path) -> None:
        """A malformed draft record must not prevent the editor starting."""
        db = tmp_path / "state.db"
        state_db.save_draft(
            db,
            {
                "key": "2026-06",
                "invoice": {"lines": [{"concept": "X", "unit_price": "not-a-number"}]},
            },
        )
        c = _make_app(tmp_path, db_path=db).test_client()
        resp = c.get("/")
        assert resp.status_code == 200
        assert b"Draft restored" not in resp.data
        assert b"Backend Development" in resp.data  # fresh seed lines
        assert state_db.get_draft(db) is None  # bad record dropped

    def test_noop_posts_leave_no_draft(self, tmp_path: Path) -> None:
        """A session that never changes anything must not create a draft
        (e.g. onboarding, where only settings are saved)."""
        db = tmp_path / "state.db"
        c = _make_app(tmp_path, db_path=db).test_client()
        c.post("/lines/reorder", data={"order": "0,1"})  # identity order
        assert state_db.get_draft(db) is None

    def test_draft_survives_roster_and_range_state(self, tmp_path: Path) -> None:
        """The import generation (roster, range, merge flag) round-trips."""
        db = tmp_path / "state.db"
        raw = [
            InvoiceLine(concept="Dev", unit_price=100.0, quantity=10.0, user="Jane"),
            InvoiceLine(concept="Dev", unit_price=100.0, quantity=5.0, user="Bob"),
        ]
        app1 = _make_app(
            tmp_path,
            db_path=db,
            import_raw=raw,
            period_start=date(2026, 6, 1),
            period_end=date(2026, 6, 30),
        )
        c1 = app1.test_client()
        c1.post("/lines/people", data={"toggle": "Bob"})  # deselect Bob
        app2 = _make_app(tmp_path, db_path=db, import_raw=raw)
        c2 = app2.test_client()
        c2.get("/")
        assert app2.state["selected_people"] == {"Jane"}  # type: ignore[attr-defined]
        assert app2.state["last_fetch_range"] == (  # type: ignore[attr-defined]
            date(2026, 6, 1),
            date(2026, 6, 30),
        )


class TestPdfCache:
    """Unchanged invoices reuse the last WeasyPrint render."""

    def test_preview_pdf_cached_until_state_changes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[str] = []

        def fake_pdf(html: str, utd: Path | None = None) -> bytes:
            calls.append(html)
            return b"%PDF-fake"

        monkeypatch.setattr("harvest_invoicer.app.pdf_from_html", fake_pdf)
        c = _make_app(tmp_path).test_client()
        assert c.get("/preview.pdf").data == b"%PDF-fake"
        assert c.get("/preview.pdf").data == b"%PDF-fake"
        assert len(calls) == 1  # second hit served from cache
        c.post(
            "/lines/update/0",
            data={"concept": "Changed", "quantity": "40", "unit_price": "120"},
        )
        c.get("/preview.pdf")
        assert len(calls) == 2  # state change invalidated the cache

    def test_generate_reuses_preview_render(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[str] = []

        def fake_pdf(html: str, utd: Path | None = None) -> bytes:
            calls.append(html)
            return b"%PDF-fake"

        monkeypatch.setattr("harvest_invoicer.app.pdf_from_html", fake_pdf)
        c = _make_app(tmp_path).test_client()
        c.get("/preview.pdf")
        resp = c.post("/render")
        assert resp.status_code == 200
        assert len(calls) == 1  # Generate reused the preview's bytes
        assert (tmp_path / "invoice-2026-06.pdf").read_bytes() == b"%PDF-fake"


class TestSendInvoice:
    """POST /send emails the PDF to the bill-to client via env-configured SMTP."""

    @pytest.fixture(autouse=True)
    def _fake_renderer(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "harvest_invoicer.app.pdf_from_html",
            lambda _html, _utd=None: b"%PDF-fake",
        )
        for var in ("HOST", "PORT", "USERNAME", "PASSWORD", "FROM"):
            monkeypatch.delenv(f"HARVEST_INVOICER_SMTP_{var}", raising=False)

    def test_send_without_smtp_config_reports_inline(self, tmp_path: Path) -> None:
        client_entry = _fake_client() | {"email": "billing@acme.test"}
        c = _make_app(tmp_path, client=client_entry).test_client()
        resp = c.post("/send")
        assert resp.status_code == 200
        assert b"render-err" in resp.data
        assert b"SMTP is not configured" in resp.data

    def test_send_without_client_email_reports_inline(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HARVEST_INVOICER_SMTP_HOST", "smtp.test")
        c = _make_app(tmp_path).test_client()
        resp = c.post("/send")
        assert b"render-err" in resp.data
        assert b"no email address" in resp.data

    def test_send_success_attaches_pdf(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import smtplib  # noqa: PLC0415

        sent = []

        class FakeSMTP:
            def __init__(self, host: str, port: int, timeout: int = 0) -> None:
                self.host, self.port = host, port

            def __enter__(self) -> Self:
                return self

            def __exit__(self, *exc: object) -> None:
                return None

            def ehlo(self) -> None:
                pass

            def has_extn(self, _name: str) -> bool:
                return False

            def login(self, _user: str, _password: str) -> None:
                pass

            def send_message(self, msg: object) -> None:
                sent.append(msg)

        monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
        monkeypatch.setenv("HARVEST_INVOICER_SMTP_HOST", "smtp.test")
        client_entry = _fake_client() | {"email": "billing@acme.test"}
        c = _make_app(tmp_path, client=client_entry).test_client()
        resp = c.post("/send")
        assert b"emailed to billing@acme.test" in resp.data
        assert len(sent) == 1
        msg = sent[0]
        assert msg["To"] == "billing@acme.test"
        assert "Invoice 2026-06" in msg["Subject"]
        attachments = list(msg.iter_attachments())
        assert attachments[0].get_filename() == "invoice-2026-06.pdf"
        assert attachments[0].get_content() == b"%PDF-fake"

    def test_smtp_failure_reports_inline(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import smtplib  # noqa: PLC0415

        def boom(*_args: object, **_kwargs: object) -> object:
            raise smtplib.SMTPConnectError(421, "unreachable")

        monkeypatch.setattr(smtplib, "SMTP", boom)
        monkeypatch.setenv("HARVEST_INVOICER_SMTP_HOST", "smtp.test")
        client_entry = _fake_client() | {"email": "billing@acme.test"}
        c = _make_app(tmp_path, client=client_entry).test_client()
        resp = c.post("/send")
        assert b"render-err" in resp.data
        assert b"Send failed" in resp.data

    def test_bad_smtp_port_reports_inline(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HARVEST_INVOICER_SMTP_HOST", "smtp.test")
        monkeypatch.setenv("HARVEST_INVOICER_SMTP_PORT", "not-a-port")
        client_entry = _fake_client() | {"email": "billing@acme.test"}
        c = _make_app(tmp_path, client=client_entry).test_client()
        resp = c.post("/send")
        assert resp.status_code == 200
        assert b"render-err" in resp.data
        assert b"SMTP_PORT must be a number" in resp.data

    def test_send_button_wired_in_editor(self, client: FlaskClient) -> None:
        resp = client.get("/")
        assert b'hx-post="/send"' in resp.data


class TestToasts:
    """Committed actions return an HX-Trigger showtoast header."""

    def test_toast_js_served_and_loaded(self, client: FlaskClient) -> None:
        served = client.get("/static/toast.js")
        assert served.status_code == 200
        assert b"showtoast" in served.data
        assert b'src="/static/toast.js"' in client.get("/").data
        assert b'src="/static/toast.js"' in client.get("/settings").data

    def test_generate_pdf_emits_ok_toast(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "harvest_invoicer.app.pdf_from_html", lambda _h, _u=None: b"%PDF-fake"
        )
        c = _make_app(tmp_path).test_client()
        resp = c.post("/render")
        assert resp.status_code == 200
        assert _toast_kind(resp) == "ok"

    def test_send_failure_emits_err_toast(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "harvest_invoicer.app.pdf_from_html", lambda _h, _u=None: b"%PDF-fake"
        )
        monkeypatch.delenv("HARVEST_INVOICER_SMTP_HOST", raising=False)
        client_entry = _fake_client() | {"email": "billing@acme.test"}
        c = _make_app(tmp_path, client=client_entry).test_client()
        resp = c.post("/send")
        assert _toast_kind(resp) == "err"

    def test_line_edits_do_not_toast(self, client: FlaskClient) -> None:
        # Frequent silent mutations must not spam toasts.
        resp = client.post(
            "/lines/update/0",
            data={"concept": "X", "quantity": "1", "unit_price": "1"},
        )
        assert _toast_kind(resp) is None


class TestEmptyStates:
    """Zero line items / zero clients show a friendly empty state."""

    def test_unsynced_shows_sync_empty_state(self, tmp_path: Path) -> None:
        c = _make_app(tmp_path, lines=[]).test_client()  # no import_raw -> unsynced
        body = c.get("/").data
        assert b"No hours imported yet" in body
        # The column header is suppressed when there is nothing to label.
        assert b'class="li-grid-head"' not in body
        # ...but both ways to populate it stay available.
        assert b"or add a line manually" in body
        assert b"Sync from Harvest" in body

    def test_header_returns_and_empty_state_clears_after_add(
        self, tmp_path: Path
    ) -> None:
        c = _make_app(tmp_path, lines=[]).test_client()
        resp = c.post("/lines/add")
        assert resp.status_code == 200
        assert b'class="li-grid-head"' in resp.data
        assert b"No hours imported yet" not in resp.data

    def test_empty_state_returns_when_last_line_removed(self, tmp_path: Path) -> None:
        c = _make_app(
            tmp_path,
            lines=[InvoiceLine(concept="Only", unit_price=1.0, quantity=1.0)],
        ).test_client()
        resp = c.post("/lines/drop/0")
        assert b"No hours imported yet" in resp.data  # unsynced empty state
        assert b'class="li-grid-head"' not in resp.data

    def test_settings_hints_when_no_clients(self, tmp_path: Path) -> None:
        # The module-level _make_app seeds no clients mapping.
        c = _make_app(tmp_path).test_client()
        assert b"No clients yet" in c.get("/settings").data

    def test_editor_picker_hints_when_no_clients(self, tmp_path: Path) -> None:
        body = _make_app(tmp_path).test_client().get("/").data
        assert b"No clients configured yet" in body


class TestStateLock:
    """Concurrent requests must not corrupt app.state (threaded server)."""

    def test_parallel_edits_stay_consistent(self, tmp_path: Path) -> None:
        import threading  # noqa: PLC0415

        app = _make_app(tmp_path)
        errors: list[int] = []

        def hammer() -> None:
            c = app.test_client()
            for i in range(25):
                r = c.post(
                    "/lines/update/0",
                    data={"concept": f"C{i}", "quantity": "1", "unit_price": "1"},
                )
                if r.status_code != 200:
                    errors.append(r.status_code)

        threads = [threading.Thread(target=hammer) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        assert len(app.state["invoice"].lines) == 2  # type: ignore[attr-defined]
