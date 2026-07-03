"""Tag models for Paperless-ngx API."""

from dataclasses import dataclass
from typing import Any

from paperless_cli.models.base import PaginatedResponse


@dataclass
class Tag:
    """Represents a tag in Paperless-ngx."""

    id: int
    name: str
    slug: str
    color: str | None = None
    match: str | None = None
    matching_algorithm: int | None = None
    is_insensitive: bool = False
    is_inbox_tag: bool = False
    document_count: int = 0

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "Tag":
        """Create a Tag instance from API response data."""
        return cls(
            id=data["id"],
            name=data["name"],
            slug=data["slug"],
            color=data.get("color"),
            match=data.get("match"),
            matching_algorithm=data.get("matching_algorithm"),
            is_insensitive=data.get("is_insensitive", False),
            is_inbox_tag=data.get("is_inbox_tag", False),
            document_count=data.get("document_count", 0),
        )


@dataclass
class TagCreateRequest:
    """Request to create a new tag."""

    name: str
    color: str | None = None
    match: str | None = None
    matching_algorithm: int | None = None
    is_insensitive: bool = False
    is_inbox_tag: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API request."""
        data: dict[str, Any] = {"name": self.name}
        if self.color:
            data["color"] = self.color
        if self.match:
            data["match"] = self.match
        if self.matching_algorithm is not None:
            data["matching_algorithm"] = self.matching_algorithm
        if self.is_insensitive:
            data["is_insensitive"] = self.is_insensitive
        if self.is_inbox_tag:
            data["is_inbox_tag"] = self.is_inbox_tag
        return data


TagListResponse = PaginatedResponse[Tag]
