"""Base models for Paperless-ngx API."""

from dataclasses import dataclass
from typing import Any, Generic, TypeVar

T = TypeVar("T")


@dataclass
class PaginatedResponse(Generic[T]):
    """Generic paginated response from the API."""

    count: int
    next: str | None
    previous: str | None
    results: list[T]

    @classmethod
    def from_api(cls, data: dict[str, Any], items: list[T]) -> "PaginatedResponse[T]":
        """Create a PaginatedResponse instance from API response data."""
        return cls(
            count=data["count"],
            next=data.get("next"),
            previous=data.get("previous"),
            results=items,
        )
