"""Check Account operations for SevDesk API."""

from __future__ import annotations

from typing import Any

from .client import SevDeskClient


class CheckAccountOperations:
    """Operations for check accounts in SevDesk."""

    def __init__(self, client: SevDeskClient) -> None:
        """Initialize check account operations.

        Args:
            client: The SevDesk client instance
        """
        self.client = client

    def get_check_accounts(
        self,
        limit: int | None = None,
        offset: int | None = None,
        embed: list[str] | None = None,
    ) -> dict[str, Any]:
        """Get all check accounts.

        Args:
            limit: Limit number of results
            offset: Skip number of results
            embed: Embed related objects

        Returns:
            Response with check accounts
        """
        params = {}
        if limit is not None:
            params["limit"] = limit
        if offset is not None:
            params["offset"] = offset
        if embed:
            params["embed"] = ",".join(embed)

        return self.client.get("CheckAccount", params=params)

    def get_check_account(self, check_account_id: int) -> dict[str, Any]:
        """Get a specific check account.

        Args:
            check_account_id: ID of the check account

        Returns:
            Check account data
        """
        return self.client.get(f"CheckAccount/{check_account_id}")

    def create_file_import_account(
        self,
        name: str,
        import_type: str = "CSV",
        iban: str | None = None,
        accounting_number: int | None = None,
    ) -> dict[str, Any]:
        """Create a new file import account.

        Args:
            name: Name of the check account
            import_type: Import type (CSV or MT940)
            iban: IBAN of the bank account (optional)
            accounting_number: The booking account number (optional)

        Returns:
            Created check account data
        """
        data = {
            "name": name,
            "importType": import_type,
        }
        
        if iban:
            data["iban"] = iban
        if accounting_number is not None:
            data["accountingNumber"] = accounting_number

        return self.client.post("CheckAccount/Factory/fileImportAccount", json_data=data)

    def create_clearing_account(
        self,
        name: str,
        accounting_number: int | None = None,
    ) -> dict[str, Any]:
        """Create a new clearing account.

        Args:
            name: Name of the check account
            accounting_number: The booking account number (optional)

        Returns:
            Created check account data
        """
        data = {
            "name": name,
        }
        
        if accounting_number is not None:
            data["accountingNumber"] = accounting_number

        return self.client.post("CheckAccount/Factory/clearingAccount", json_data=data)