"""Email delivery for generated invoices.

Configuration is a :class:`~harvest_invoicer.config.SmtpSettings` model,
built from the stored (DB) values with ``HARVEST_INVOICER_SMTP_*``
environment overrides layered on top.  The password comes from the
environment only and is never persisted or echoed.
"""

from __future__ import annotations

import smtplib
from email.message import EmailMessage
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from harvest_invoicer.config import (
    DEFAULT_MESSAGE_TEMPLATE,
    DEFAULT_SUBJECT_TEMPLATE,
    SMTP_ENV,
    SmtpSettings,
    friendly_error,
    smtp_env_raw,
)
from harvest_invoicer.model import fmt_money

if TYPE_CHECKING:
    from harvest_invoicer.model import Invoice

__all__ = [
    "DEFAULT_MESSAGE_TEMPLATE",
    "DEFAULT_SUBJECT_TEMPLATE",
    "SMTP_ENV",
    "MailConfigError",
    "env_value",
    "resolve_tokens",
    "send_invoice_email",
    "verify_smtp",
]

_SMTP_TIMEOUT = 30
_DEFAULT_PORTS = {"starttls": 587, "ssl": 465, "none": 25}


class MailConfigError(Exception):
    """SMTP is not configured (or not configured enough) to send/test."""


def env_value(key: str) -> str:
    """The environment override for *key*, or '' if unset/not env-backed."""
    return smtp_env_raw(key)


def resolve_tokens(
    template: str,
    invoice: Invoice,
    client: dict[str, str],
    issuer: dict[str, object],
) -> str:
    """Fill ``{company}``/``{number}``/… tokens against the live invoice."""
    period = ""
    if invoice.period_start and invoice.period_end:
        period = (
            f"{invoice.period_start.isoformat()} → {invoice.period_end.isoformat()}"
        )
    values = {
        "company": str(client.get("name") or ""),
        "number": invoice.number,
        "total": f"{fmt_money(invoice.grand_total)} {invoice.currency}",
        "due": invoice.due_date.isoformat(),
        "issued": invoice.issue_date.isoformat(),
        "period": period,
        "issuer": str(issuer.get("name") or ""),
    }
    out = template
    for token, value in values.items():
        out = out.replace("{" + token + "}", value)
    return out


def _settings(config: dict[str, Any]) -> SmtpSettings:
    """Build the effective SMTP settings (env over stored)."""
    try:
        return SmtpSettings(**config)
    except ValidationError as exc:  # e.g. a non-numeric port
        raise MailConfigError(friendly_error(exc)) from exc


def _connect(settings: SmtpSettings) -> smtplib.SMTP:
    """Open + secure + authenticate an SMTP connection per *settings*."""
    if not settings.host:
        msg = "SMTP host is not configured — set it in Settings > Email."
        raise MailConfigError(msg)
    port = settings.port or _DEFAULT_PORTS[settings.encryption]
    if settings.encryption == "ssl":
        conn: smtplib.SMTP = smtplib.SMTP_SSL(
            settings.host, port, timeout=_SMTP_TIMEOUT
        )
    else:
        conn = smtplib.SMTP(settings.host, port, timeout=_SMTP_TIMEOUT)
        conn.ehlo()
        if settings.encryption == "starttls" or conn.has_extn("starttls"):
            conn.starttls()
            conn.ehlo()
    if settings.username:
        conn.login(settings.username, settings.password.get_secret_value())
    return conn


def send_invoice_email(
    pdf: bytes,
    invoice: Invoice,
    issuer: dict[str, object],
    client: dict[str, str],
    config: dict[str, Any],
    *,
    to: str,
    subject: str,
    message: str,
    copy_self: bool = False,
) -> str:
    """Send the invoice PDF; return a human description of the recipients.

    Raises :class:`MailConfigError` for configuration problems; SMTP-level
    failures propagate as :class:`OSError` / ``smtplib.SMTPException``.
    """
    recipient = to.strip()
    if not recipient:
        msg = "No recipient — enter an address to send to."
        raise MailConfigError(msg)

    settings = _settings(config)
    from_address = settings.from_address or str(issuer.get("email") or "").strip()
    if not from_address:
        msg = "No sender address — set a From address in Settings > Email."
        raise MailConfigError(msg)
    from_name = settings.from_name or str(issuer.get("name") or "").strip()

    email = EmailMessage()
    email["From"] = f"{from_name} <{from_address}>" if from_name else from_address
    email["To"] = recipient
    if settings.reply_to:
        email["Reply-To"] = settings.reply_to
    recipients = [recipient]
    if copy_self and from_address and from_address != recipient:
        email["Cc"] = from_address
        recipients.append(from_address)
    email["Subject"] = subject.strip() or f"Invoice {invoice.number}"
    email.set_content(message.rstrip() + "\n")
    email.add_attachment(
        pdf,
        maintype="application",
        subtype="pdf",
        filename=f"invoice-{invoice.number}.pdf",
    )

    with _connect(settings) as conn:
        conn.send_message(email, to_addrs=recipients)

    return recipient + (" (copy to you)" if copy_self else "")


def verify_smtp(config: dict[str, Any]) -> str:
    """Open + authenticate an SMTP connection without sending; return host.

    Raises :class:`MailConfigError` / ``OSError`` on failure — used by the
    "Send test email" button's connection check.
    """
    settings = _settings(config)
    with _connect(settings) as conn:
        conn.noop()
    return settings.host
