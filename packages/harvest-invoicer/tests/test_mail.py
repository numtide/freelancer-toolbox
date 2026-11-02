"""Tests for mail.py: verified TLS, recipient/subject validation, templates
and delivery through a real local SMTP server."""

from __future__ import annotations

import smtplib
import ssl
from typing import TYPE_CHECKING

import pytest
from harvest_invoicer.config import (
    DEFAULT_MESSAGE_TEMPLATE,
    DEFAULT_SUBJECT_TEMPLATE,
    SMTP_ENV,
    SmtpSettings,
)
from harvest_invoicer.mail import (
    MailConfigError,
    MailDeliveryError,
    SendResult,
    _connect,
    archived_tokens,
    check_subject,
    email_templates,
    fill_tokens,
    parse_recipients,
    send_pdf_email,
)

if TYPE_CHECKING:
    from tests.conftest import SmtpServer


@pytest.fixture(autouse=True)
def _clear_smtp_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate SmtpSettings from any ambient HARVEST_INVOICER_SMTP_* vars."""
    for var in SMTP_ENV.values():
        monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv("HARVEST_INVOICER_SMTP_PASSWORD", raising=False)


class _FakeConn:
    def __init__(self, *_args: object, context: object = None, **_kw: object) -> None:
        self.init_context = context
        self.starttls_context: object = "unset"

    def ehlo(self) -> None:
        pass

    def starttls(self, *, context: object = None) -> None:
        self.starttls_context = context

    def login(self, *_a: object) -> None:  # pragma: no cover - no creds in tests
        pass


def _assert_verifying(ctx: object) -> None:
    assert isinstance(ctx, ssl.SSLContext)
    assert ctx.check_hostname is True
    assert ctx.verify_mode == ssl.CERT_REQUIRED


def test_ssl_connection_verifies_certificate(monkeypatch: pytest.MonkeyPatch) -> None:
    created: dict[str, _FakeConn] = {}

    def fake_ssl(host: str, port: int, *, timeout: float, context: object) -> _FakeConn:
        conn = _FakeConn(context=context)
        created["conn"] = conn
        return conn

    monkeypatch.setattr(smtplib, "SMTP_SSL", fake_ssl)
    _connect(SmtpSettings(host="mail.example", encryption="ssl"))
    _assert_verifying(created["conn"].init_context)


def test_starttls_connection_verifies_certificate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = _FakeConn()
    monkeypatch.setattr(smtplib, "SMTP", lambda *_a, **_k: conn)
    _connect(SmtpSettings(host="mail.example", encryption="starttls"))
    _assert_verifying(conn.starttls_context)


class TestRecipients:
    def test_single_and_multiple(self) -> None:
        assert parse_recipients(" a@x.test ") == ["a@x.test"]
        assert parse_recipients("a@x.test, Bob <b@y.test>,, a@x.test") == [
            "a@x.test",
            "b@y.test",
        ]

    @pytest.mark.parametrize(
        ("to", "error"),
        [
            ("", "No recipient"),
            ("  ,  ", "No recipient"),
            ("a@x.test\r\nBcc: e@vil.test", "one line"),
            ("a@x.test\nb@y.test", "one line"),
            ("nope", "Not a valid email"),
            ("a@x.test, b@", "Not a valid email"),
            (",".join(f"u{i}@x.test" for i in range(11)), "Too many"),
        ],
    )
    def test_rejected(self, to: str, error: str) -> None:
        with pytest.raises(MailConfigError, match=error):
            parse_recipients(to)


class TestTemplates:
    def test_language_defaults_with_period(self) -> None:
        subject, message = email_templates({}, "es", has_period=True)
        assert subject == "Factura {number} ({period})"
        assert "{period}" in message

    def test_language_defaults_without_period(self) -> None:
        subject, message = email_templates({}, "en", has_period=False)
        assert subject == "Invoice {number}"
        assert "{period}" not in message

    def test_customized_template_wins(self) -> None:
        cfg = {"subject_template": "X {number}", "message_template": "Body"}
        assert email_templates(cfg, "es", has_period=True) == ("X {number}", "Body")

    def test_old_english_default_counts_as_unset(self) -> None:
        cfg = {
            "subject_template": DEFAULT_SUBJECT_TEMPLATE,
            "message_template": DEFAULT_MESSAGE_TEMPLATE,
        }
        subject, _ = email_templates(cfg, "es", has_period=False)
        assert subject == "Factura {number}"

    def test_archived_tokens(self) -> None:
        record = {
            "number": "2026-06",
            "client_name": "Acme",
            "total": 1210.5,
            "currency": "EUR",
            "issue_date": "2026-07-01",
            "due_date": "2026-07-16",
            "period_start": "2026-06-01",
            "period_end": "2026-06-30",
        }
        tokens = archived_tokens(record, {"name": "Jane"})
        assert fill_tokens("{number}|{company}|{period}|{due}|{issuer}", tokens) == (
            "2026-06|Acme|2026-06-01 → 2026-06-30|2026-07-16|Jane"
        )
        assert tokens["total"].endswith(" EUR")


class TestSendPdfEmail:
    """send_pdf_email against a real SMTP server on loopback."""

    def test_delivers_attachment(self, smtp_server: SmtpServer) -> None:
        to = send_pdf_email(
            b"%PDF-1.7 test",
            "2026-06_Acme_0a1b2c3d.pdf",
            {"name": "Jane", "email": "jane@example.com"},
            smtp_server.config(from_address="", reply_to="ar@example.com"),
            to="billing@acme.test",
            subject="Invoice 2026-06",
            message="Hello",
        )
        assert to == SendResult(["billing@acme.test"], [])
        (delivery,) = smtp_server.received
        msg = delivery.message
        assert delivery.mail_from == "jane@example.com"  # issuer email fallback
        assert msg["From"] == "Jane <jane@example.com>"
        assert msg["Reply-To"] == "ar@example.com"
        (att,) = list(msg.iter_attachments())
        assert att.get_filename() == "2026-06_Acme_0a1b2c3d.pdf"
        assert att.get_content() == b"%PDF-1.7 test"

    def test_header_injection_never_reaches_the_server(
        self, smtp_server: SmtpServer
    ) -> None:
        with pytest.raises(MailConfigError, match="single line"):
            send_pdf_email(
                b"%PDF",
                "x.pdf",
                {"name": "Jane"},
                smtp_server.config(),
                to="billing@acme.test",
                subject="Hi\r\nBcc: evil@example.com",
                message="M",
            )
        assert smtp_server.received == []

    def test_unconfigured(self) -> None:
        with pytest.raises(MailConfigError, match="host is not configured"):
            send_pdf_email(
                b"%PDF",
                "x.pdf",
                {"name": "Jane", "email": "jane@example.com"},
                {},
                to="billing@acme.test",
                subject="S",
                message="M",
            )


class TestDeliveryResult:
    def _send(self, smtp: SmtpServer, to: str, **kw: object) -> SendResult:
        return send_pdf_email(
            b"%PDF",
            "x.pdf",
            {"name": "Jane"},
            smtp.config(),
            to=to,
            subject="S",
            message="M",
            **kw,
        )

    def test_partial_refusal(self, smtp_server: SmtpServer) -> None:
        smtp_server.refuse = {"b@x.test"}
        result = self._send(smtp_server, "a@x.test, b@x.test")
        assert result == SendResult(["a@x.test"], ["b@x.test"])

    def test_self_copy_does_not_count(self, smtp_server: SmtpServer) -> None:
        smtp_server.refuse = {"a@x.test"}
        with pytest.raises(
            MailDeliveryError, match=r"refused every recipient: a@x\.test"
        ):
            self._send(smtp_server, "a@x.test", copy_self=True)
        assert [d.rcpt_tos for d in smtp_server.received] == [["jane@example.com"]]

    @pytest.mark.parametrize("to", ["a@x.test\x00", "a@x.test\u2028b@x.test"])
    def test_control_characters_rejected(self, to: str) -> None:
        with pytest.raises(MailConfigError, match="control characters"):
            parse_recipients(to)


class TestSender:
    @pytest.mark.parametrize("name", ["Doe, Jane", "Acme, Inc.", 'Jane "JD" Doe'])
    def test_display_name_with_specials(
        self, smtp_server: SmtpServer, name: str
    ) -> None:
        send_pdf_email(
            b"%PDF",
            "x.pdf",
            {"name": name},
            smtp_server.config(from_address="billing@jane.test"),
            to="a@x.test",
            subject="S",
            message="M",
        )
        (delivery,) = smtp_server.received
        assert delivery.mail_from == "billing@jane.test"  # envelope: bare address
        (mailbox,) = delivery.message["From"].addresses  # one mailbox, not two
        assert mailbox.addr_spec == "billing@jane.test"
        assert mailbox.display_name == name

    def test_attachment_name_from_free_text_number(self) -> None:
        from datetime import date  # noqa: PLC0415

        from harvest_invoicer.mail import send_invoice_email  # noqa: PLC0415
        from harvest_invoicer.model import Invoice  # noqa: PLC0415

        inv = Invoice(
            number="2026\n06/../x",
            issue_date=date(2026, 7, 1),
            due_date=date(2026, 7, 16),
            lines=[],
        )
        with pytest.raises(MailConfigError, match="host is not configured"):
            # Reaching the SMTP step means the message (and its attachment
            # name) was built without error.
            send_invoice_email(
                b"%PDF",
                inv,
                {"name": "J", "email": "j@x.test"},
                {},
                {},
                to="a@x.test",
                subject="S",
                message="M",
            )

    def test_check_subject(self) -> None:
        assert check_subject("  Invoice 1  ") == "Invoice 1"
        for bad in ("a\nb", "a\u2028b", "a\x85b", "a\x0bb"):
            with pytest.raises(MailConfigError, match="single line"):
                check_subject(bad)
