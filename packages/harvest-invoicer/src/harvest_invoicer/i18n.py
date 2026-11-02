"""Invoice-facing (and invoice-archive UI) string translations.

Deliberately a plain dict rather than gettext: ~25 keys, few languages,
no extraction/compile step, and a key-parity test guarantees no language
misses a string.  The invoice language resolves per recipient:
``client.language`` > ``issuer.language`` > English.

:data:`UI_TRANSLATIONS` holds the editor strings of the invoice archive
(the Invoices page, the generated-PDF panel, the send modal).  The UI
speaks the issuer's language — the person using the editor — not the
recipient's.

Number and date formatting are intentionally NOT localized here: dates
follow the issuer's ``date_format`` and amounts keep one consistent
notation across all invoices (see the README).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        "invoice": "INVOICE",
        "invoice_word": "Invoice",
        "number": "No.",
        "issued": "Issued",
        "due": "Due",
        "period": "Period",
        "bill_to": "Bill to",
        "description": "Description",
        "unit_price": "Unit Price",
        "qty": "Qty",
        "subtotal": "Subtotal",
        "vat": "VAT",
        "total": "Total",
        "payment": "Payment",
        "payment_method": "Method",
        "bank_transfer": "Bank Transfer",
        "iban": "IBAN",
        "bic": "BIC / SWIFT",
        "account_holder": "Account Holder",
        "reference": "Reference",
        "tax_id": "Tax ID",
        "tel": "Tel.",
        "email": "Email",
        "page": "Page",
        "page_of": "of",
        # Default email for sending the invoice (tokens: see mail.py).
        "email_subject": "Invoice {number}",
        "email_subject_period": "Invoice {number} ({period})",
        "email_message": (
            "Hello,\n\nPlease find attached invoice {number} for {total}, "
            "due {due}.\n\nKind regards,\n{issuer}"
        ),
        "email_message_period": (
            "Hello,\n\nPlease find attached invoice {number} for the period "
            "{period}, for {total}, due {due}.\n\nKind regards,\n{issuer}"
        ),
    },
    "es": {
        "invoice": "FACTURA",
        "invoice_word": "Factura",
        "number": "N.º",
        "issued": "Emitida",
        "due": "Vencimiento",
        "period": "Periodo",
        "bill_to": "Facturar a",
        "description": "Concepto",
        "unit_price": "Precio unit.",
        "qty": "Cant.",
        "subtotal": "Subtotal",
        "vat": "IVA",
        "total": "Total",
        "payment": "Pago",
        "payment_method": "Método",
        "bank_transfer": "Transferencia bancaria",
        "iban": "IBAN",
        "bic": "BIC / SWIFT",
        "account_holder": "Titular",
        "reference": "Referencia",
        "tax_id": "NIF",
        "tel": "Tel.",
        "email": "Email",
        "page": "Página",
        "page_of": "de",
        "email_subject": "Factura {number}",
        "email_subject_period": "Factura {number} ({period})",
        "email_message": (
            "Hola,\n\nAdjunto la factura {number} por un importe de {total}, "
            "con vencimiento el {due}.\n\nUn saludo,\n{issuer}"
        ),
        "email_message_period": (
            "Hola,\n\nAdjunto la factura {number} correspondiente al periodo "
            "{period}, por un importe de {total}, con vencimiento el {due}."
            "\n\nUn saludo,\n{issuer}"
        ),
    },
}

UI_TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        "invoices": "Invoices",
        "back_to_editor": "Back to editor",
        "archive_sub": "Every generated PDF, newest first. Links are private to signed-in users.",
        "col_date": "Created",
        "col_number": "Number",
        "col_client": "Client",
        "col_total": "Total",
        "col_status": "Status",
        "col_actions": "Actions",
        "status_sent": "Sent",
        "status_not_sent": "Not sent",
        "sent_to_on": "Sent to {to} on {date}",
        "open": "Open",
        "download": "Download",
        "send": "Send by email",
        "send_again": "Send again",
        "delete": "Delete",
        "close": "Close",
        "cancel": "Cancel",
        "all_invoices": "All invoices",
        "empty_title": "No invoices yet",
        "empty_sub": "Every PDF you generate in the editor is archived here.",
        "generated_title": "Invoice PDF generated",
        "generated_reused": "Same content as the last PDF for this number — reused it.",
        "generated_copy": "Also saved to {path}.",
        "smtp_disabled": "Sending is off: set up SMTP in Settings > Email.",
        "confirm_delete": "Delete invoice {number} ({file})? The PDF is removed permanently.",
        "confirm_delete_sent": "It was already sent to {to}; deleting it does not recall that email.",
        "confirm_resend": "Invoice {number} was already sent to {to}. Send it again?",
        "deleted": "Invoice deleted",
        "not_found": "Invoice not found",
        "file_missing": "The archived PDF file is missing.",
        "send_title": "Send invoice",
        "send_to": "To",
        "send_to_hint": "Separate several addresses with commas.",
        "send_subject": "Subject",
        "send_message": "Message",
        "send_copy_self": "Send me a copy",
        "send_attached": "The invoice PDF will be attached automatically.",
        "send_attached_file": "Attached: {file}",
        "send_already": "Already sent to {to} on {date}.",
        "send_button": "Send invoice",
        "sent": "Invoice sent",
        "sent_body": "Sent to {to}",
        "sent_partial": "Sent, but some recipients were refused",
        "sent_partial_body": "Delivered to {to}. Refused by the mail server: {refused}",
        "cant_send": "Can't send invoice",
        "send_failed": "Send failed",
        "archived": "Invoice PDF archived",
        "cfg_title": "The invoice can't be rendered yet",
        "cfg_issuer": "Your issuer details have no name. Add it in Settings > Issuer.",
        "cfg_client": "No bill-to client with a name is selected. Add or pick one in Settings > Clients.",
        "cfg_link": "Open Settings",
    },
    "es": {
        "invoices": "Facturas",
        "back_to_editor": "Volver al editor",
        "archive_sub": "Todos los PDF generados, del más reciente al más antiguo. Los enlaces solo los abren usuarios con sesión iniciada.",
        "col_date": "Creada",
        "col_number": "Número",
        "col_client": "Cliente",
        "col_total": "Total",
        "col_status": "Estado",
        "col_actions": "Acciones",
        "status_sent": "Enviada",
        "status_not_sent": "Sin enviar",
        "sent_to_on": "Enviada a {to} el {date}",
        "open": "Abrir",
        "download": "Descargar",
        "send": "Enviar por email",
        "send_again": "Reenviar",
        "delete": "Eliminar",
        "close": "Cerrar",
        "cancel": "Cancelar",
        "all_invoices": "Todas las facturas",
        "empty_title": "Aún no hay facturas",
        "empty_sub": "Cada PDF que generes en el editor se archiva aquí.",
        "generated_title": "PDF de la factura generado",
        "generated_reused": "Mismo contenido que el último PDF de este número: se ha reutilizado.",
        "generated_copy": "También guardado en {path}.",
        "smtp_disabled": "El envío está desactivado: configura el SMTP en Ajustes > Email.",
        "confirm_delete": "¿Eliminar la factura {number} ({file})? El PDF se borra definitivamente.",
        "confirm_delete_sent": "Ya se envió a {to}; eliminarla no anula ese email.",
        "confirm_resend": "La factura {number} ya se envió a {to}. ¿Enviarla de nuevo?",
        "deleted": "Factura eliminada",
        "not_found": "Factura no encontrada",
        "file_missing": "Falta el archivo PDF archivado.",
        "send_title": "Enviar factura",
        "send_to": "Para",
        "send_to_hint": "Separa varias direcciones con comas.",
        "send_subject": "Asunto",
        "send_message": "Mensaje",
        "send_copy_self": "Enviarme una copia",
        "send_attached": "El PDF de la factura se adjunta automáticamente.",
        "send_attached_file": "Adjunto: {file}",
        "send_already": "Ya enviada a {to} el {date}.",
        "send_button": "Enviar factura",
        "sent": "Factura enviada",
        "sent_body": "Enviada a {to}",
        "sent_partial": "Enviada, pero se rechazaron algunos destinatarios",
        "sent_partial_body": "Entregada a {to}. Rechazados por el servidor de correo: {refused}",
        "cant_send": "No se puede enviar la factura",
        "send_failed": "Error al enviar",
        "archived": "PDF de la factura archivado",
        "cfg_title": "Todavía no se puede generar la factura",
        "cfg_issuer": "Tus datos de emisor no tienen nombre. Añádelo en Ajustes > Emisor.",
        "cfg_client": "No hay seleccionado ningún cliente con nombre al que facturar. Añade o elige uno en Ajustes > Clientes.",
        "cfg_link": "Abrir ajustes",
    },
}

SUPPORTED_LANGUAGES: tuple[str, ...] = tuple(TRANSLATIONS)


def resolve_language(client: dict[str, str], issuer: dict[str, object]) -> str:
    """Invoice language: client wins, issuer is the default, else English."""
    lang = str(client.get("language") or issuer.get("language") or "en").strip().lower()
    return lang if lang in TRANSLATIONS else "en"


def ui_language(issuer: dict[str, object]) -> str:
    """Language of the editor's archive UI: the issuer's, else English."""
    lang = str(issuer.get("language") or "en").strip().lower()
    return lang if lang in UI_TRANSLATIONS else "en"


def translator(
    lang: str, tables: dict[str, dict[str, str]] = TRANSLATIONS
) -> Callable[[str], str]:
    """Return ``t(key)`` for *lang*, falling back to English, then the key.

    *tables* selects the string set: the invoice's (default) or
    :data:`UI_TRANSLATIONS`.
    """
    table = tables.get(lang, tables["en"])
    english = tables["en"]

    def t(key: str) -> str:
        return table.get(key, english.get(key, key))

    return t
