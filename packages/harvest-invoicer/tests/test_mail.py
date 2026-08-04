"""Tests for mail.py: SMTP connections must verify the TLS certificate."""

from __future__ import annotations

import smtplib
import ssl

import pytest
from harvest_invoicer.config import SMTP_ENV, SmtpSettings
from harvest_invoicer.mail import _connect


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
