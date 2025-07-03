"""Main SevDesk API interface."""

from __future__ import annotations

from .client import SevDeskClient, SevDeskError
from .contacts import ContactOperations
from .invoices import InvoiceOperations
from .check_accounts import CheckAccountOperations
from .transactions import TransactionOperations
from .vouchers import VoucherOperations


class SevDeskAPI:
    """Main interface for interacting with the SevDesk API."""

    def __init__(self, api_token: str, base_url: str = "https://my.sevdesk.de/api/v1/") -> None:
        """Initialize the SevDesk API.

        Args:
            api_token: The API token for authentication
            base_url: The base URL for the API
        """
        self.client = SevDeskClient(api_token, base_url)
        self.contacts = ContactOperations(self.client)
        self.invoices = InvoiceOperations(self.client)
        self.check_accounts = CheckAccountOperations(self.client)
        self.transactions = TransactionOperations(self.client)
        self.vouchers = VoucherOperations(self.client)

    def check_connection(self) -> bool:
        """Check if the API connection is working.

        Returns:
            True if connection is successful
        """
        try:
            # Try to get user info
            response = self.client.get("SevUser")
        except SevDeskError:
            return False
        else:
            return "objects" in response
