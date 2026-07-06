"""Tests for app.py: Flask test client, htmx mutations, preview."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from harvest_invoicer.app import create_app
from harvest_invoicer.model import InvoiceLine

if TYPE_CHECKING:
    from collections.abc import Generator

    from flask.testing import FlaskClient


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
        assert b"New item" in resp.data

    def test_merge_lines(self, client: FlaskClient) -> None:
        resp = client.post("/lines/merge", data={"selected": ["0", "1"]})
        assert resp.status_code == 200
        # After merging 2 lines there should be exactly 1 checkbox (one row)
        assert resp.data.count(b'type="checkbox"') == 1


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
        assert b"/preview.pdf" in resp.data


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

    def test_fetch_replaces_lines_and_period(self, tmp_path: Path) -> None:
        def fake_fetch(ps: date, pe: date) -> list[InvoiceLine]:
            assert ps == date(2026, 5, 1)
            assert pe == date(2026, 5, 31)
            return [InvoiceLine(concept="May Work", unit_price=100.0, quantity=10.0)]

        app = self._make_app(tmp_path, fake_fetch)
        with app.test_client() as c:
            resp = c.post(
                "/lines/fetch",
                data={"period_start": "2026-05-01", "period_end": "2026-05-31"},
            )
        assert resp.status_code == 200
        assert b"May Work" in resp.data
        assert b"Imported 1 lines" in resp.data
        inv = app.state["invoice"]  # type: ignore[attr-defined]
        assert len(inv.lines) == 1
        assert inv.period_start == date(2026, 5, 1)
        assert inv.period_end == date(2026, 5, 31)

    def test_fetch_error_keeps_lines(self, tmp_path: Path) -> None:
        def failing_fetch(ps: date, pe: date) -> list[InvoiceLine]:
            msg = "No time entries found between 2026-05-01 and 2026-05-31."
            raise RuntimeError(msg)

        app = self._make_app(tmp_path, failing_fetch)
        with app.test_client() as c:
            resp = c.post(
                "/lines/fetch",
                data={"period_start": "2026-05-01", "period_end": "2026-05-31"},
            )
        assert resp.status_code == 200
        assert b"No time entries found" in resp.data
        inv = app.state["invoice"]  # type: ignore[attr-defined]
        assert len(inv.lines) == 2  # original lines untouched
        assert inv.period_start == date(2026, 6, 1)  # period untouched

    def test_fetch_invalid_dates_rejected(self, tmp_path: Path) -> None:
        app = self._make_app(tmp_path, lambda *_args: [])
        with app.test_client() as c:
            resp = c.post("/lines/fetch", data={"period_start": "", "period_end": ""})
        assert b"valid period" in resp.data

    def test_fetch_end_before_start_rejected(self, tmp_path: Path) -> None:
        app = self._make_app(tmp_path, lambda *_args: [])
        with app.test_client() as c:
            resp = c.post(
                "/lines/fetch",
                data={"period_start": "2026-06-30", "period_end": "2026-06-01"},
            )
        assert b"must not be before" in resp.data

    def test_fetch_without_callback_reports_unavailable(self, tmp_path: Path) -> None:
        app = self._make_app(tmp_path, None)
        with app.test_client() as c:
            resp = c.post(
                "/lines/fetch",
                data={"period_start": "2026-06-01", "period_end": "2026-06-30"},
            )
        assert b"not available" in resp.data

    def test_editor_has_fetch_button(self, client: FlaskClient) -> None:
        resp = client.get("/")
        assert b"Fetch from Harvest" in resp.data
        assert b'id="fetch-status"' in resp.data
        assert b'id="merge-on-fetch"' in resp.data
        assert b'id="fetch-indicator"' in resp.data

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
                    "period_start": "2026-06-01",
                    "period_end": "2026-06-30",
                    "merge_duplicates": "on",
                },
            )
        inv = app.state["invoice"]  # type: ignore[attr-defined]
        assert len(inv.lines) == 2
        assert inv.lines[0].quantity == pytest.approx(252.0)
        assert b"Imported 2 lines (3 before merging duplicates)" in resp.data

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
                data={"period_start": "2026-06-01", "period_end": "2026-06-30"},
            )
        inv = app.state["invoice"]  # type: ignore[attr-defined]
        assert len(inv.lines) == 2


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
        issuer_path = tmp_path / "issuer.json"
        clients_path = tmp_path / "clients.json"
        issuer_path.write_text(json.dumps(issuer))
        clients_path.write_text(json.dumps(clients))
        app = create_app(
            lines=_fake_lines(),
            issuer=issuer,
            client=clients["Acme Corp"],
            invoice_number="2026-06",
            output_path=tmp_path / "invoice.pdf",
            clients=clients,
            issuer_path=issuer_path,
            clients_path=clients_path,
        )
        app.config["TESTING"] = True
        return app, issuer_path, clients_path

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
        assert json.loads(issuer_path.read_text())["name"] == "New Name S.L."

    def test_issuer_save_missing_required_rejected(self, tmp_path: Path) -> None:
        app, issuer_path, _ = self._make_app(tmp_path)
        before = issuer_path.read_text()
        with app.test_client() as c:
            resp = c.post("/settings/issuer", data=self._issuer_form(name=""))
        assert b"Missing required fields" in resp.data
        assert issuer_path.read_text() == before  # untouched

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
        saved = json.loads(clients_path.read_text())
        assert saved["Acme Corp"]["name"] == "Acme Corp International"

    def test_client_add_and_delete(self, tmp_path: Path) -> None:
        app, _, clients_path = self._make_app(tmp_path)
        with app.test_client() as c:
            c.post("/settings/clients/save", data=self._client_form())
            assert "New Client" in json.loads(clients_path.read_text())
            resp = c.post(
                "/settings/clients/delete", data={"original_key": "New Client"}
            )
            assert b"deleted" in resp.data
        assert "New Client" not in json.loads(clients_path.read_text())

    def test_delete_current_client_rejected(self, tmp_path: Path) -> None:
        app, _, clients_path = self._make_app(tmp_path)
        with app.test_client() as c:
            resp = c.post(
                "/settings/clients/delete", data={"original_key": "Acme Corp"}
            )
        assert b"Cannot delete" in resp.data
        assert "Acme Corp" in json.loads(clients_path.read_text())

    def test_client_invalid_vat_rejected(self, tmp_path: Path) -> None:
        app, _, _ = self._make_app(tmp_path)
        with app.test_client() as c:
            resp = c.post(
                "/settings/clients/save",
                data=self._client_form(vat_rate="21"),
            )
        assert b"between 0 and 1" in resp.data

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
    """Single-level undo for line-item mutations (second undo = redo)."""

    def test_undo_restores_dropped_line(self, client: FlaskClient) -> None:
        client.post("/lines/drop/0")
        resp = client.post("/lines/undo")
        assert resp.status_code == 200
        assert b"Backend Development" in resp.data
        assert resp.data.count(b'type="checkbox"') == 2

    def test_undo_twice_is_redo(self, client: FlaskClient) -> None:
        client.post("/lines/drop/0")
        client.post("/lines/undo")  # restore
        resp = client.post("/lines/undo")  # redo the drop
        assert b"Backend Development" not in resp.data

    def test_undo_without_history_is_noop(self, client: FlaskClient) -> None:
        resp = client.post("/lines/undo")
        assert resp.status_code == 200
        assert b"Backend Development" in resp.data
        assert resp.data.count(b'type="checkbox"') == 2

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
                data={"period_start": "2026-06-01", "period_end": "2026-06-30"},
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

    def test_editor_has_undo_button(self, client: FlaskClient) -> None:
        resp = client.get("/")
        assert b"/lines/undo" in resp.data


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

    def test_favicon_204(self, client: FlaskClient) -> None:
        resp = client.get("/favicon.ico")
        assert resp.status_code == 204
