"""Voucher operations for SevDesk API."""

from __future__ import annotations

import mimetypes
from typing import TYPE_CHECKING, Any, BinaryIO

from .client import SevDeskClient

if TYPE_CHECKING:
    from datetime import datetime


class VoucherOperations:
    """Operations for vouchers in SevDesk."""

    def __init__(self, client: SevDeskClient) -> None:
        """Initialize voucher operations.

        Args:
            client: The SevDesk client instance
        """
        self.client = client

    def get_vouchers(
        self,
        status: int | None = None,
        credit_debit: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        supplier_id: int | None = None,
        limit: int | None = None,
        offset: int | None = None,
        embed: list[str] | None = None,
    ) -> dict[str, Any]:
        """Get vouchers.

        Args:
            status: Filter by status (50=Draft, 100=Unpaid, 1000=Paid)
            credit_debit: Filter by credit/debit (C=Credit, D=Debit)
            start_date: Filter by start date
            end_date: Filter by end date
            supplier_id: Filter by supplier contact ID
            limit: Limit number of results
            offset: Skip number of results
            embed: Embed related objects

        Returns:
            Response with vouchers
        """
        params = {}
        if status is not None:
            params["status"] = status
        if credit_debit:
            params["creditDebit"] = credit_debit
        if start_date:
            params["startDate"] = int(start_date.timestamp())
        if end_date:
            params["endDate"] = int(end_date.timestamp())
        if supplier_id is not None:
            params["supplier[id]"] = supplier_id
            params["supplier[objectName]"] = "Contact"
        if limit is not None:
            params["limit"] = limit
        if offset is not None:
            params["offset"] = offset
        if embed:
            params["embed"] = ",".join(embed)

        return self.client.get("Voucher", params=params)

    def get_voucher(self, voucher_id: int) -> dict[str, Any]:
        """Get a specific voucher.

        Args:
            voucher_id: ID of the voucher

        Returns:
            Voucher data
        """
        return self.client.get(f"Voucher/{voucher_id}")

    def upload_temp_file(self, file: BinaryIO, filename: str) -> dict[str, Any]:
        """Upload a temporary file for later attachment to a voucher.

        Args:
            file: File object to upload
            filename: Name of the file

        Returns:
            Response with uploaded file info including internal filename
        """
        import uuid

        # Prepare multipart/form-data manually
        boundary = f"----WebKitFormBoundary{uuid.uuid4().hex[:16]}"

        # Read file content
        file_content = file.read()

        # Guess content type
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

        # Build multipart body as bytes
        body_parts = []
        body_parts.append(f"------{boundary}".encode())
        body_parts.append(
            f'Content-Disposition: form-data; name="file"; filename="{filename}"'.encode()
        )
        body_parts.append(f"Content-Type: {content_type}".encode())
        body_parts.append(b"")
        body_parts.append(
            file_content if isinstance(file_content, bytes) else file_content.encode()
        )
        body_parts.append(f"------{boundary}--".encode())

        body = b"\r\n".join(body_parts)

        # Override headers for multipart
        headers = self.client.headers.copy()
        headers["Content-Type"] = f"multipart/form-data; boundary=----{boundary}"

        # Make request with custom headers
        conn = self.client._get_connection()
        try:
            path = f"{self.client.base_path}/Voucher/Factory/uploadTempFile"
            conn.request("POST", path, body=body, headers=headers)
            response = conn.getresponse()
            response_body = response.read().decode("utf-8")

            if response.status >= 400:
                msg = f"Upload failed: {response_body}"
                raise SevDeskError(msg, response.status, response_body)

            import json

            return json.loads(response_body)
        finally:
            conn.close()

    def create_voucher(
        self,
        credit_debit: str,
        tax_type: str,
        voucher_type: str,
        status: int,
        voucher_date: datetime | None = None,
        supplier_id: int | None = None,
        supplier_name: str | None = None,
        description: str | None = None,
        pay_date: datetime | None = None,
        sum_net: float | None = None,
        sum_tax: float | None = None,
        sum_gross: float | None = None,
        currency: str = "EUR",
        tax_rule: int | None = None,
        voucher_positions: list[dict[str, Any]] | None = None,
        filename: str | None = None,
    ) -> dict[str, Any]:
        """Create a new voucher.

        Args:
            credit_debit: Credit or debit (C/D)
            tax_type: Tax type (default, eu, noteu, custom, ss)
            voucher_type: Voucher type (VOU, RV)
            status: Status (50=Draft, 100=Unpaid)
            voucher_date: Date of the voucher
            supplier_id: ID of supplier contact
            supplier_name: Name of supplier (if no contact)
            description: Description/number of voucher
            pay_date: Payment deadline
            sum_net: Net amount
            sum_tax: Tax amount
            sum_gross: Gross amount
            currency: Currency code
            tax_rule: Tax rule ID (overrides tax_type)
            voucher_positions: List of voucher positions
            filename: Internal filename from upload_temp_file

        Returns:
            Created voucher data
        """
        voucher_data = {
            "objectName": "Voucher",
            "mapAll": True,
            "creditDebit": credit_debit,
            "taxType": tax_type,
            "voucherType": voucher_type,
            "status": status,
            "currency": currency,
        }

        if voucher_date:
            voucher_data["voucherDate"] = voucher_date.strftime("%d.%m.%Y")
        if supplier_id:
            voucher_data["supplier"] = {
                "id": supplier_id,
                "objectName": "Contact",
            }
        if supplier_name:
            voucher_data["supplierName"] = supplier_name
        if description:
            voucher_data["description"] = description
        if pay_date:
            voucher_data["payDate"] = pay_date.strftime("%Y-%m-%dT%H:%M:%S+00:00")
        if sum_net is not None:
            voucher_data["sumNet"] = sum_net
        if sum_tax is not None:
            voucher_data["sumTax"] = sum_tax
        if sum_gross is not None:
            voucher_data["sumGross"] = sum_gross
        if tax_rule is not None:
            voucher_data["taxRule"] = tax_rule

        # Build request data
        request_data = {
            "voucher": voucher_data,
            "voucherPosDelete": None,
        }

        # Add voucher positions
        if voucher_positions:
            request_data["voucherPosSave"] = voucher_positions
        else:
            request_data["voucherPosSave"] = []

        # Add filename if provided
        if filename:
            request_data["filename"] = filename

        return self.client.post("Voucher/Factory/saveVoucher", json_data=request_data)

    def update_voucher(
        self,
        voucher_id: int,
        voucher_data: dict[str, Any],
        voucher_positions: list[dict[str, Any]] | None = None,
        positions_to_delete: list[int] | None = None,
    ) -> dict[str, Any]:
        """Update an existing voucher.

        Args:
            voucher_id: ID of the voucher to update
            voucher_data: Voucher data to update
            voucher_positions: Voucher positions to save/update
            positions_to_delete: IDs of positions to delete

        Returns:
            Updated voucher data
        """
        # Ensure required fields
        voucher_data["id"] = voucher_id
        voucher_data["objectName"] = "Voucher"
        voucher_data["mapAll"] = True

        request_data = {
            "voucher": voucher_data,
            "voucherPosSave": voucher_positions or [],
            "voucherPosDelete": positions_to_delete,
        }

        return self.client.post("Voucher/Factory/saveVoucher", json_data=request_data)

    def book_voucher(
        self,
        voucher_id: int,
        check_account_transaction_id: int,
        amount: float | None = None,
    ) -> dict[str, Any]:
        """Book a voucher with a payment transaction.

        Args:
            voucher_id: ID of the voucher
            check_account_transaction_id: ID of the payment transaction
            amount: Amount to book (optional, defaults to full amount)

        Returns:
            Booking response
        """
        data = {
            "checkAccountTransaction": {
                "id": check_account_transaction_id,
                "objectName": "CheckAccountTransaction",
            },
        }

        if amount is not None:
            data["amount"] = amount

        return self.client.post(f"Voucher/{voucher_id}/bookAmount", json_data=data)


from .client import SevDeskError  # Import at the end to avoid circular import
