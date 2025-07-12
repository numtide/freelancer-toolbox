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

    def get_accounting_types(
        self,
        *,
        limit: int | None = None,
        offset: int | None = None,
        count_all: bool = False,
        depth: int | None = None,
        embed: list[str] | None = None,
    ) -> dict[str, Any]:
        """Get accounting types (AccountDatev).

        Args:
            limit: Limit number of results
            offset: Skip number of results
            count_all: Return total count
            depth: Depth for nested objects
            embed: Embed related objects

        Returns:
            Response with accounting types

        """
        params: dict[str, Any] = {}

        if limit is not None:
            params["limit"] = limit
        if offset is not None:
            params["offset"] = offset
        if count_all:
            params["countAll"] = "true"
        if depth is not None:
            params["depth"] = depth
        if embed:
            params["embed"] = ",".join(embed)

        return self.client.get("AccountDatev", params=params)

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

        # Fetch all accounting types
        # Use a large limit to get all in one request
        batch_size = 1000
        result = self.get_accounting_types(limit=batch_size, count_all=True)
        total = int(result.get("total", 0))

        if total > batch_size:
            # Need to fetch in batches
            for offset in range(batch_size, total, batch_size):
                batch = self.get_accounting_types(limit=batch_size, offset=offset)
                result["objects"].extend(batch.get("objects", []))

        # Build the cache
        for acc_type in result.get("objects", []):
            number = acc_type.get("number")
            if number:
                self._skr_cache[str(number)] = acc_type

    def clear_cache(self) -> None:
        """Clear the SKR cache."""
        self._skr_cache = None
