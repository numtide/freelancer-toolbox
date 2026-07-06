"""Email delivery for generated invoices.

SMTP settings come exclusively from environment variables — like the
Harvest credentials, they are never written to the state database:

- ``HARVEST_INVOICER_SMTP_HOST``      (required to enable sending)
- ``HARVEST_INVOICER_SMTP_PORT``      (default 587; 465 switches to implicit TLS)
- ``HARVEST_INVOICER_SMTP_USERNAME``  (optional; enables AUTH)
- ``HARVEST_INVOICER_SMTP_PASSWORD``  (optional)
- ``HARVEST_INVOICER_SMTP_FROM``      (default: the issuer's email)
"""

from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from typing import TYPE_CHECKING

from harvest_invoicer.model import fmt_money

if TYPE_CHECKING:
    from harvest_invoicer.model import Invoice

_SMTP_TIMEOUT = 30
_SSL_PORT = 465


class MailConfigError(Exception):
    """SMTP is not configured (or not configured enough) to send."""


def send_invoice_email(
    pdf: bytes,
    invoice: Invoice,
    issuer: dict[str, object],
    client: dict[str, str],
) -> str:
    """Email the invoice PDF to the bill-to client; return the recipient.

    Raises :class:`MailConfigError` with an actionable message when the
    client has no email or SMTP is unconfigured.  SMTP-level failures
    propagate as :class:`smtplib.SMTPException` / ``OSError`` for the
    caller to surface.
    """
    recipient = str(client.get("email") or "").strip()
    if not recipient:
        msg = (
            "The bill-to client has no email address — "
            "add one in Settings > Clients first."
        )
        raise MailConfigError(msg)
    host = os.environ.get("HARVEST_INVOICER_SMTP_HOST", "").strip()
    if not host:
        msg = (
            "SMTP is not configured — set HARVEST_INVOICER_SMTP_HOST "
            "(and _PORT/_USERNAME/_PASSWORD as needed) before starting."
        )
        raise MailConfigError(msg)
    try:
        port = int(os.environ.get("HARVEST_INVOICER_SMTP_PORT", "587").strip())
    except ValueError as exc:
        msg = "HARVEST_INVOICER_SMTP_PORT must be a number (e.g. 587)."
        raise MailConfigError(msg) from exc
    username = os.environ.get("HARVEST_INVOICER_SMTP_USERNAME", "").strip()
    password = os.environ.get("HARVEST_INVOICER_SMTP_PASSWORD", "")
    issuer_name = str(issuer.get("name") or "").strip()
    sender = (
        os.environ.get("HARVEST_INVOICER_SMTP_FROM", "").strip()
        or str(issuer.get("email") or "").strip()
    )
    if not sender:
        msg = (
            "No sender address — set HARVEST_INVOICER_SMTP_FROM "
            "or the issuer email in Settings."
        )
        raise MailConfigError(msg)

    message = EmailMessage()
    message["From"] = f"{issuer_name} <{sender}>" if issuer_name else sender
    message["To"] = recipient
    message["Subject"] = f"Invoice {invoice.number}" + (
        f" from {issuer_name}" if issuer_name else ""
    )
    total = f"{fmt_money(invoice.grand_total)} {invoice.currency}"
    message.set_content(
        f"Hello,\n\n"
        f"Please find attached invoice {invoice.number} "
        f"for {total}, due {invoice.due_date.isoformat()}.\n\n"
        f"Best regards,\n{issuer_name or sender}\n"
    )
    message.add_attachment(
        pdf,
        maintype="application",
        subtype="pdf",
        filename=f"invoice-{invoice.number}.pdf",
    )

    smtp_cls = smtplib.SMTP_SSL if port == _SSL_PORT else smtplib.SMTP
    with smtp_cls(host, port, timeout=_SMTP_TIMEOUT) as smtp:
        if smtp_cls is smtplib.SMTP:
            # Opportunistic TLS: encrypt whenever the server offers it,
            # but keep plain local relays (e.g. a dev catch-all) working.
            smtp.ehlo()
            if smtp.has_extn("starttls"):
                smtp.starttls()
                smtp.ehlo()
        if username:
            smtp.login(username, password)
        smtp.send_message(message)
    return recipient
