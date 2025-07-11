"""Invoice operations for SevDesk API."""

from typing import Any

from .client import SevDeskClient
from .models import Invoice, InvoicePosition, InvoiceStatus


class InvoiceOperations:
    """Operations for managing invoices."""

    def __init__(self, client: SevDeskClient) -> None:
        """Initialize InvoiceOperations.

        Args:
            client: SevDeskClient instance

        """
        self.client = client

    def create_invoice(
        self,
        invoice: Invoice,
        positions: list[InvoicePosition] | None = None,
    ) -> Invoice:
        """Create a new invoice with positions.

        Args:
            invoice: Invoice object to create
            positions: List of invoice positions (line items)

        Returns:
            Created invoice with ID

        """
        # Use provided positions or invoice's positions
        if positions is None:
            positions = invoice.positions or []

        # Prepare invoice data
        invoice_data = invoice.to_dict()

        # Prepare positions data
        invoice_pos_save = []
        for i, pos in enumerate(positions):
            pos_data = pos.to_dict()
            if "positionNumber" not in pos_data:
                pos_data["positionNumber"] = i + 1
            invoice_pos_save.append(pos_data)

        # Create request body
        request_data = {"invoice": invoice_data, "invoicePosSave": invoice_pos_save}

        response = self.client.post(
            "Invoice/Factory/saveInvoice",
            json_data=request_data,
        )

        if "objects" in response and "invoice" in response["objects"]:
            return Invoice.from_dict(response["objects"]["invoice"])
        msg = "Failed to create invoice"
        raise ValueError(msg)

    def get_invoices(
        self,
        limit: int = 100,
        offset: int = 0,
        status: InvoiceStatus | None = None,
        contact_id: int | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[Invoice]:
        """Get a list of invoices.

        Args:
            limit: Number of results to return
            offset: Offset for pagination
            status: Filter by status
            contact_id: Filter by contact ID
            start_date: Filter by start date (YYYY-MM-DD)
            end_date: Filter by end date (YYYY-MM-DD)

        Returns:
            List of Invoice objects

        """
        params: dict[str, Any] = {
            "limit": limit,
            "offset": offset,
        }

        if status:
            params["status"] = status.value
        if contact_id:
            params["contact[id]"] = contact_id
            params["contact[objectName]"] = "Contact"
        if start_date:
            params["startDate"] = start_date
        if end_date:
            params["endDate"] = end_date

        response = self.client.get("Invoice", params=params)
        invoices = []

        if "objects" in response:
            for invoice_data in response["objects"]:
                # Note: This returns basic invoice data without positions
                # Use get_invoice() to get full details with positions
                invoice = Invoice()
                invoice.id = invoice_data.get("id")
                invoice.object_name = invoice_data.get("objectName")
                invoice.invoice_number = invoice_data.get("invoiceNumber")
                invoice.status = InvoiceStatus(int(invoice_data.get("status", 100)))
                invoice.invoice_date = invoice_data.get("invoiceDate")
                invoice.header = invoice_data.get("header")
                invoice.currency = invoice_data.get("currency")
                invoices.append(invoice)

        return invoices

    def get_invoice(self, invoice_id: int) -> Invoice:
        """Get a specific invoice by ID.

        Args:
            invoice_id: The invoice ID

        Returns:
            Invoice object with positions

        """
        response = self.client.get(f"Invoice/{invoice_id}")

        if response.get("objects"):
            invoice_data = response["objects"][0]
            # TODO: Create proper from_dict method for Invoice
            invoice = Invoice()
            invoice.id = invoice_data.get("id")
            invoice.object_name = invoice_data.get("objectName")
            invoice.invoice_number = invoice_data.get("invoiceNumber")
            invoice.status = InvoiceStatus(int(invoice_data.get("status", 100)))
            invoice.header = invoice_data.get("header")

            # Get positions
            positions_response = self.client.get(
                "InvoicePos",
                params={"invoice[id]": invoice_id, "invoice[objectName]": "Invoice"},
            )

            if "objects" in positions_response:
                invoice.positions = []
                for pos_data in positions_response["objects"]:
                    # Create position from data
                    position = InvoicePosition()
                    position.id = pos_data.get("id")
                    position.quantity = float(pos_data.get("quantity", 0))
                    position.price = float(pos_data.get("price", 0))
                    position.name = pos_data.get("name", "")
                    position.tax_rate = float(pos_data.get("taxRate", 19))
                    invoice.positions.append(position)

            return invoice
        msg = f"Invoice with ID {invoice_id} not found"
        raise ValueError(msg)

    def send_invoice_by_email(
        self,
        invoice_id: int,
        email: str,
        subject: str | None = None,
        text: str | None = None,
        cc: str | None = None,
        bcc: str | None = None,
    ) -> dict:
        """Send invoice by email.

        Args:
            invoice_id: The invoice ID
            email: Recipient email address
            subject: Email subject (optional)
            text: Email text (optional)
            cc: CC email addresses (optional)
            bcc: BCC email addresses (optional)

        Returns:
            Response from API

        """
        data = {
            "toEmail": email,
            "subject": subject or "Invoice",
            "text": text or "Please find the invoice attached.",
        }

        if cc:
            data["ccEmail"] = cc
        if bcc:
            data["bccEmail"] = bcc

        return self.client.post(f"Invoice/{invoice_id}/sendViaEmail", json_data=data)

    def book_invoice(
        self,
        invoice_id: int,
        amount: float,
        date: str,
        check_account_id: int,
        check_account_transaction_id: int | None = None,
    ) -> dict:
        """Book an invoice payment.

        Args:
            invoice_id: The invoice ID
            amount: Payment amount
            date: Payment date (YYYY-MM-DD)
            check_account_id: Check account ID
            check_account_transaction_id: Transaction ID (optional)

        Returns:
            Response from API

        """
        data = {
            "amount": amount,
            "date": date,
            "type": "N",
            "checkAccount": {"id": check_account_id, "objectName": "CheckAccount"},
        }

        if check_account_transaction_id:
            data["checkAccountTransaction"] = {
                "id": check_account_transaction_id,
                "objectName": "CheckAccountTransaction",
            }

        return self.client.put(f"Invoice/{invoice_id}/bookAmount", json_data=data)

    def create_invoice_from_order(
        self,
        order_id: int,
        invoice_data: dict | None = None,
    ) -> Invoice:
        """Create an invoice from an order.

        Args:
            order_id: The order ID
            invoice_data: Optional invoice data overrides

        Returns:
            Created invoice

        """
        data = {"order": {"id": order_id, "objectName": "Order"}}

        if invoice_data:
            data["invoice"] = invoice_data

        response = self.client.post(
            "Invoice/Factory/createInvoiceFromOrder",
            json_data=data,
        )

        if response.get("objects"):
            # TODO: Proper from_dict implementation
            invoice = Invoice()
            invoice.id = response["objects"].get("id")
            return invoice
        msg = "Failed to create invoice from order"
        raise ValueError(msg)
