"""Base classes and utilities for SevDesk API models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


def parse_iso_date(date_str: str) -> datetime:
    """Parse ISO format date string from API.

    The API returns dates in ISO format with timezone like '2025-07-03T00:00:00+02:00'.
    """
    return datetime.fromisoformat(date_str)


@dataclass
class SevDeskObject:
    """Base class for SevDesk objects."""

    id: int | None = None
    object_name: str | None = None
    create: datetime | None = None
    update: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for API requests."""
        data = {}
        if self.id is not None:
            data["id"] = self.id
        if self.object_name:
            data["objectName"] = self.object_name
        return data
