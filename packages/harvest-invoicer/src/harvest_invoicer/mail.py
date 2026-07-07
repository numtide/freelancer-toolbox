"""Email delivery for generated invoices.

Non-secret SMTP settings (host, port, encryption, username, sender,
reply-to, message templates) live in the state database, edited on the
Settings > Email screen.  The **password is never persisted** — it comes
only from the environment:

- ``HARVEST_INVOICER_SMTP_PASSWORD``

Any field may also be overridden from the environment (handy for CI or
secret managers): ``HARVEST_INVOICER_SMTP_HOST`` / ``_PORT`` /
``_USERNAME`` / ``_FROM`` / ``_ENCRYPTION``.
"""

from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from typing import TYPE_CHECKING, Any

from harvest_invoicer.model import fmt_money

if TYPE_CHECKING:
    from harvest_invoicer.model import Invoice

_SMTP_TIMEOUT = 30
_ENCRYPTIONS = ("starttls", "ssl", "none")
_DEFAULT_PORTS = {"starttls": 587, "ssl": 465, "none": 25}

DEFAULT_SUBJECT_TEMPLATE = "{company} — Invoice {number}"
DEFAULT_MESSAGE_TEMPLATE = (
    "Hi,\n\nPlease find attached invoice {number} for {total}, due {due}.\n\nThank you."
)


class MailConfigError(Exception):
    """SMTP is not configured (or not configured enough) to send/test."""


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


def _cfg(config: dict[str, Any], key: str, env: str, default: str = "") -> str:
    """Environment override wins, then the stored config, then *default*."""
    return (
        os.environ.get(env, "").strip() or str(config.get(key) or "").strip() or default
    )


def _resolve_smtp(config: dict[str, Any]) -> dict[str, Any]:
    """Merge stored config + environment into concrete SMTP parameters.

    Raises :class:`MailConfigError` when required pieces are missing.
    """
    host = _cfg(config, "host", "HARVEST_INVOICER_SMTP_HOST")
    if not host:
        msg = "SMTP host is not configured — set it in Settings > Email."
        raise MailConfigError(msg)

    encryption = _cfg(
        config, "encryption", "HARVEST_INVOICER_SMTP_ENCRYPTION", "starttls"
    ).lower()
    if encryption not in _ENCRYPTIONS:
        encryption = "starttls"

    port_raw = _cfg(config, "port", "HARVEST_INVOICER_SMTP_PORT")
    try:
        port = int(port_raw) if port_raw else _DEFAULT_PORTS[encryption]
    except ValueError as exc:
        msg = "SMTP port must be a number (e.g. 587)."
        raise MailConfigError(msg) from exc

    return {
        "host": host,
        "port": port,
        "encryption": encryption,
        "username": _cfg(config, "username", "HARVEST_INVOICER_SMTP_USERNAME"),
        "password": os.environ.get("HARVEST_INVOICER_SMTP_PASSWORD", ""),
    }


def _connect(smtp: dict[str, Any]) -> smtplib.SMTP:
    """Open + secure + authenticate an SMTP connection per *smtp* config."""
    if smtp["encryption"] == "ssl":
        conn: smtplib.SMTP = smtplib.SMTP_SSL(
            smtp["host"], smtp["port"], timeout=_SMTP_TIMEOUT
        )
    else:
        conn = smtplib.SMTP(smtp["host"], smtp["port"], timeout=_SMTP_TIMEOUT)
        conn.ehlo()
        if smtp["encryption"] == "starttls" or conn.has_extn("starttls"):
            conn.starttls()
            conn.ehlo()
    if smtp["username"]:
        conn.login(smtp["username"], smtp["password"])
    return conn


def _sender(config: dict[str, Any], issuer: dict[str, object]) -> tuple[str, str]:
    """Return (from_name, from_address), falling back to the issuer."""
    address = (
        _cfg(config, "from_address", "HARVEST_INVOICER_SMTP_FROM")
        or str(issuer.get("email") or "").strip()
    )
    name = str(config.get("from_name") or issuer.get("name") or "").strip()
    if not address:
        msg = "No sender address — set a From address in Settings > Email."
        raise MailConfigError(msg)
    return name, address


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

    smtp = _resolve_smtp(config)
    from_name, from_address = _sender(config, issuer)

    email = EmailMessage()
    email["From"] = f"{from_name} <{from_address}>" if from_name else from_address
    email["To"] = recipient
    reply_to = _cfg(config, "reply_to", "HARVEST_INVOICER_SMTP_REPLY_TO")
    if reply_to:
        email["Reply-To"] = reply_to
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

    with _connect(smtp) as conn:
        conn.send_message(email, to_addrs=recipients)

    return recipient + (" (copy to you)" if copy_self else "")


def verify_smtp(config: dict[str, Any]) -> str:
    """Open + authenticate an SMTP connection without sending; return host.

    Raises :class:`MailConfigError` / ``OSError`` on failure — used by the
    "Send test email" button's connection check.
    """
    smtp = _resolve_smtp(config)
    with _connect(smtp) as conn:
        conn.noop()
    return str(smtp["host"])
