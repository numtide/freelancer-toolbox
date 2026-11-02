"""Shared fixtures: a real SMTP server on loopback (aiosmtpd)."""

from __future__ import annotations

import socket
from dataclasses import dataclass, field
from email import message_from_bytes, policy
from typing import TYPE_CHECKING, Any

import pytest
from aiosmtpd.controller import Controller

if TYPE_CHECKING:
    from collections.abc import Generator
    from email.message import EmailMessage


@dataclass
class Delivery:
    """One message as the server received it (envelope + parsed content)."""

    mail_from: str
    rcpt_tos: list[str]
    message: EmailMessage


@dataclass
class SmtpServer:
    host: str
    port: int
    received: list[Delivery] = field(default_factory=list)
    # Recipients the server answers RCPT TO with 550 (unknown mailbox).
    refuse: set[str] = field(default_factory=set)

    def config(self, **overrides: object) -> dict[str, object]:
        """Settings > Email values pointing at this server (plaintext)."""
        return {
            "host": self.host,
            "port": str(self.port),
            "encryption": "none",
            "from_address": "jane@example.com",
            **overrides,
        }


class _Inbox:
    def __init__(self, server: SmtpServer) -> None:
        self.server = server

    async def handle_RCPT(  # noqa: N802 — aiosmtpd hook name
        self,
        _server: Any,
        _session: Any,
        envelope: Any,
        address: str,
        _rcpt_options: list[str],
    ) -> str:
        if address in self.server.refuse:
            return "550 5.1.1 Mailbox unavailable"
        envelope.rcpt_tos.append(address)
        return "250 OK"

    async def handle_DATA(self, _server: Any, _session: Any, envelope: Any) -> str:  # noqa: N802 — aiosmtpd hook name
        msg = message_from_bytes(envelope.original_content, policy=policy.default)
        self.server.received.append(
            Delivery(envelope.mail_from, list(envelope.rcpt_tos), msg)
        )
        return "250 Message accepted"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture
def smtp_server(monkeypatch: pytest.MonkeyPatch) -> Generator[SmtpServer]:
    """A local SMTP server that records every message it accepts."""
    for var in (
        "HOST",
        "PORT",
        "USERNAME",
        "PASSWORD",
        "FROM_ADDRESS",
        "ENCRYPTION",
        "REPLY_TO",
    ):
        monkeypatch.delenv(f"HARVEST_INVOICER_SMTP_{var}", raising=False)
    server = SmtpServer("127.0.0.1", _free_port())
    controller = Controller(_Inbox(server), hostname=server.host, port=server.port)
    controller.start()
    try:
        yield server
    finally:
        controller.stop()
