"""Email delivery for generated invoices.

Configuration is a :class:`~harvest_invoicer.config.SmtpSettings` model,
built from the stored (DB) values with ``HARVEST_INVOICER_SMTP_*``
environment overrides layered on top.  The password comes from the
environment only and is never persisted or echoed.
"""

from __future__ import annotations

import contextlib
import smtplib
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import parseaddr
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from harvest_invoicer.config import (
    DEFAULT_MESSAGE_TEMPLATE,
    DEFAULT_SUBJECT_TEMPLATE,
    SMTP_ENV,
    SmtpSettings,
    friendly_error,
    smtp_env_raw,
    validate_email_shape,
)
from harvest_invoicer.i18n import translator
from harvest_invoicer.model import fmt_money

if TYPE_CHECKING:
    from harvest_invoicer.model import Invoice

__all__ = [
    "DEFAULT_MESSAGE_TEMPLATE",
    "DEFAULT_SUBJECT_TEMPLATE",
    "SMTP_ENV",
    "MailConfigError",
    "MailDeliveryError",
    "SendResult",
    "archived_tokens",
    "email_templates",
    "env_value",
    "fill_tokens",
    "invoice_tokens",
    "parse_recipients",
    "resolve_tokens",
    "send_invoice_email",
    "send_pdf_email",
    "verify_smtp",
]

_SMTP_TIMEOUT = 30
# Recipients one send accepts (To: only; the self-copy is extra).
_MAX_RECIPIENTS = 10
_DEFAULT_PORTS = {"starttls": 587, "ssl": 465, "none": 25}


class MailConfigError(Exception):
    """SMTP is not configured (or not configured enough) to send/test."""


class MailDeliveryError(OSError):
    """The server took no recipient of the message (an SMTP-level failure)."""


@dataclass
class SendResult:
    """Who the server accepted the message for, and who it refused.

    Only the To recipients count: the sender's own (blind) copy is neither.
    """

    accepted: list[str]
    refused: list[str] = field(default_factory=list)


def env_value(key: str) -> str:
    """The environment override for *key*, or '' if unset/not env-backed."""
    return smtp_env_raw(key)


def fill_tokens(template: str, values: dict[str, str]) -> str:
    """Replace each ``{token}`` of *values* in *template* (others stay)."""
    out = template
    for token, value in values.items():
        out = out.replace("{" + token + "}", value)
    return out


def _period(start: object, end: object) -> str:
    return f"{start} → {end}" if start and end else ""


def invoice_tokens(
    invoice: Invoice,
    client: dict[str, str],
    issuer: dict[str, object],
) -> dict[str, str]:
    """Token values (``{company}``, ``{number}``, …) for the live invoice."""
    return {
        "company": str(client.get("name") or ""),
        "number": invoice.number,
        "total": f"{fmt_money(invoice.grand_total)} {invoice.currency}",
        "due": invoice.due_date.isoformat(),
        "issued": invoice.issue_date.isoformat(),
        "period": _period(
            invoice.period_start and invoice.period_start.isoformat(),
            invoice.period_end and invoice.period_end.isoformat(),
        ),
        "issuer": str(issuer.get("name") or ""),
    }


def resolve_tokens(
    template: str,
    invoice: Invoice,
    client: dict[str, str],
    issuer: dict[str, object],
) -> str:
    """Fill ``{company}``/``{number}``/… tokens against the live invoice."""
    return fill_tokens(template, invoice_tokens(invoice, client, issuer))


def archived_tokens(
    record: dict[str, object], issuer: dict[str, object]
) -> dict[str, str]:
    """Token values for an archived invoice (see :func:`resolve_tokens`)."""
    total = record.get("total")
    return {
        "company": str(record.get("client_name") or ""),
        "number": str(record.get("number") or ""),
        "total": f"{fmt_money(float(str(total or 0)))} {record.get('currency') or ''}",
        "due": str(record.get("due_date") or ""),
        "issued": str(record.get("issue_date") or ""),
        "period": _period(record.get("period_start"), record.get("period_end")),
        "issuer": str(issuer.get("name") or ""),
    }


def email_templates(
    config: dict[str, Any], lang: str, *, has_period: bool
) -> tuple[str, str]:
    """The (subject, message) templates for an invoice in *lang*.

    Templates customized in Settings > Email win; otherwise the invoice
    language's defaults apply, mentioning the period when there is one.
    The old English default counts as "not customized": the settings form
    used to save it back verbatim.
    """
    t = translator(lang)
    suffix = "_period" if has_period else ""
    subject = str(config.get("subject_template") or "")
    message = str(config.get("message_template") or "")
    if not subject or subject == DEFAULT_SUBJECT_TEMPLATE:
        subject = t("email_subject" + suffix)
    if not message or message == DEFAULT_MESSAGE_TEMPLATE:
        message = t("email_message" + suffix)
    return subject, message


def _plausible_address(addr: str) -> bool:
    try:
        validate_email_shape(addr)
    except ValueError:
        return False
    return bool(addr)


def parse_recipients(to: str) -> list[str]:
    """The comma-separated recipient addresses in *to*, validated.

    Each comma-separated entry must be one address (``a@x.test`` or
    ``Name <a@x.test>``; quoted names containing commas are not supported)
    — an unparsable entry is an error, never silently dropped.  Only the
    bare addresses are kept, and line breaks are refused outright: the
    values end up in a header.
    """
    # Line breaks of any kind (\r, \n, U+2028, \x85, …), NUL and other
    # control characters never reach the To: header or the envelope.
    if any(not ch.isprintable() for ch in to):
        msg = "Recipients must be on one line, without control characters."
        raise MailConfigError(msg)
    entries = [part.strip() for part in to.split(",") if part.strip()]
    if not entries:
        msg = "No recipient — enter an address to send to."
        raise MailConfigError(msg)
    if len(entries) > _MAX_RECIPIENTS:
        msg = f"Too many recipients (at most {_MAX_RECIPIENTS})."
        raise MailConfigError(msg)
    addresses: list[str] = []
    for entry in entries:
        addr = parseaddr(entry)[1]
        if not _plausible_address(addr):
            msg = f"Not a valid email address: {entry}"
            raise MailConfigError(msg)
        addresses.append(addr)
    return list(dict.fromkeys(addresses))


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
    # A verifying context (cert chain + hostname): smtplib otherwise defaults
    # to an *unauthenticated* TLS channel (CERT_NONE), which a MITM can
    # trivially intercept to harvest the SMTP credentials and the invoice PDF.
    context = ssl.create_default_context()
    if settings.encryption == "ssl":
        conn: smtplib.SMTP = smtplib.SMTP_SSL(
            settings.host, port, timeout=_SMTP_TIMEOUT, context=context
        )
    else:
        conn = smtplib.SMTP(settings.host, port, timeout=_SMTP_TIMEOUT)
        conn.ehlo()
        # Honor the explicit choice: only upgrade to TLS for "starttls".
        # "none" stays plaintext (for local relays / self-signed dev servers).
        if settings.encryption == "starttls":
            conn.starttls(context=context)
            conn.ehlo()
    if settings.username:
        conn.login(settings.username, settings.password.get_secret_value())
    return conn


def send_pdf_email(
    pdf: bytes,
    filename: str,
    issuer: dict[str, object],
    config: dict[str, Any],
    *,
    to: str,
    subject: str,
    message: str,
    copy_self: bool = False,
) -> SendResult:
    """Email *pdf* as the attachment *filename*.

    Returns which To recipients the server accepted and which it refused;
    the server refusing all of them (even if it took the sender's own
    copy) raises :class:`MailDeliveryError`.  Raises
    :class:`MailConfigError` for configuration problems or invalid input
    (recipients, a multi-line subject); other SMTP-level failures propagate
    as :class:`OSError` / ``smtplib.SMTPException``.  Once the message has
    been handed over, a failure while closing the session (e.g. on QUIT)
    no longer counts: the message was sent.
    """
    recipients = parse_recipients(to)
    subject = subject.strip()
    # splitlines() knows every line break (\v, \f, \x1c-\x1e, \x85,
    # U+2028/2029 too), not just \r and \n.
    if len(subject.splitlines()) > 1:
        msg = "The subject must be a single line."
        raise MailConfigError(msg)

    settings = _settings(config)
    from_address = settings.from_address or str(issuer.get("email") or "").strip()
    if not from_address:
        msg = "No sender address — set a From address in Settings > Email."
        raise MailConfigError(msg)
    from_name = settings.from_name or str(issuer.get("name") or "").strip()

    email = EmailMessage()
    to_addrs = list(recipients)
    try:
        email["From"] = f"{from_name} <{from_address}>" if from_name else from_address
        email["To"] = ", ".join(recipients)
        if settings.reply_to:
            email["Reply-To"] = settings.reply_to
        if copy_self and from_address not in recipients:
            # Blind copy: the self-copy is still delivered (it's in
            # ``to_addrs``), but ``send_message`` strips the Bcc header from
            # the transmitted message, so the client never sees it.
            email["Bcc"] = from_address
            to_addrs.append(from_address)
        email["Subject"] = subject or filename
    except ValueError as exc:  # the email package refusing a header value
        msg = f"Invalid email header: {exc}"
        raise MailConfigError(msg) from exc
    email.set_content(message.rstrip() + "\n")
    email.add_attachment(pdf, maintype="application", subtype="pdf", filename=filename)

    conn = _connect(settings)
    try:
        refused_map = conn.send_message(email, to_addrs=to_addrs) or {}
    except smtplib.SMTPRecipientsRefused as exc:
        conn.close()
        msg = f"The mail server refused every recipient: {', '.join(exc.recipients)}"
        raise MailDeliveryError(msg) from exc
    except BaseException:
        conn.close()
        raise
    # The message is with the server now; a failing QUIT changes nothing.
    with contextlib.suppress(OSError):
        conn.quit()
    conn.close()

    refused = [addr for addr in recipients if addr in refused_map]
    accepted = [addr for addr in recipients if addr not in refused_map]
    if not accepted:
        msg = f"The mail server refused every recipient: {', '.join(refused)}"
        raise MailDeliveryError(msg)
    return SendResult(accepted, refused)


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
) -> SendResult:
    """Send the live invoice's PDF (as ``invoice-<number>.pdf``).

    Errors as in :func:`send_pdf_email`.
    """
    return send_pdf_email(
        pdf,
        f"invoice-{invoice.number}.pdf",
        issuer,
        config,
        to=to,
        subject=subject.strip() or f"Invoice {invoice.number}",
        message=message,
        copy_self=copy_self,
    )


def verify_smtp(config: dict[str, Any]) -> str:
    """Open + authenticate an SMTP connection without sending; return host.

    Raises :class:`MailConfigError` / ``OSError`` on failure — used by the
    "Send test email" button's connection check.
    """
    settings = _settings(config)
    with _connect(settings) as conn:
        conn.noop()
    return settings.host
