"""Accounting type/AccountDatev operations for SevDesk API."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .client import SevDeskClient


class AccountingTypeOperations:
    """Operations for accounting types (AccountDatev) in SevDesk."""

    def __init__(self, client: SevDeskClient) -> None:
        """Initialize accounting type operations.

        Args:
            client: The SevDesk client instance

        """
        self.client = client
        self._skr_cache: dict[str, dict[str, Any]] | None = None

    def get_accounting_types(self) -> dict[str, Any]:
        """Get accounting types from selectableAccounts endpoint.

        Returns:
            Response with accounting types

        """
        # Get selectable accounts - this endpoint returns all accounts
        return self.client.get("Account/Factory/selectableAccounts")

    def get_accounting_type_by_skr(self, skr_number: str) -> dict[str, Any] | None:
        """Get accounting type by SKR account number.

        Args:
            skr_number: The SKR account number (e.g., "5400")

        Returns:
            Accounting type data if found, None otherwise

        """
        # Build cache if not already done
        if self._skr_cache is None:
            self._build_skr_cache()

        # Cache is guaranteed to be not None after _build_skr_cache
        if self._skr_cache is None:
            return None
        return self._skr_cache.get(skr_number)

    def _build_skr_cache(self) -> None:
        """Build cache of SKR numbers to accounting types."""
        self._skr_cache = {}

        # Fetch all accounting types - selectableAccounts returns all at once
        result = self.get_accounting_types()

        # Build the cache using the accountNumber field
        for acc_type in result.get("objects", []):
            number = acc_type.get("accountNumber")
            if number:
                # Store with accountDatevId as the id for voucher creation
                cached_entry = acc_type.copy()
                cached_entry["id"] = acc_type.get("accountDatevId")
                self._skr_cache[str(number)] = cached_entry

    def clear_cache(self) -> None:
        """Clear the SKR cache."""
        self._skr_cache = None
