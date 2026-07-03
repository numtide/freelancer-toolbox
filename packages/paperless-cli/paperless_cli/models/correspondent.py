"""Correspondent and DocumentType models for Paperless-ngx API."""

from dataclasses import dataclass
from typing import Any

from paperless_cli.models.base import PaginatedResponse


@dataclass
class Correspondent:
    """Represents a correspondent in Paperless-ngx."""

    id: int
    name: str
    slug: str
    match: str | None = None
    matching_algorithm: int | None = None
    is_insensitive: bool = False
    document_count: int = 0
    last_correspondence: str | None = None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "Correspondent":
        """Create a Correspondent instance from API response data."""
        return cls(
            id=data["id"],
            name=data["name"],
            slug=data["slug"],
            match=data.get("match"),
            matching_algorithm=data.get("matching_algorithm"),
            is_insensitive=data.get("is_insensitive", False),
            document_count=data.get("document_count", 0),
            last_correspondence=data.get("last_correspondence"),
        )


@dataclass
class DocumentType:
    """Represents a document type in Paperless-ngx."""

    id: int
    name: str
    slug: str
    match: str | None = None
    matching_algorithm: int | None = None
    is_insensitive: bool = False
    document_count: int = 0

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "DocumentType":
        """Create a DocumentType instance from API response data."""
        return cls(
            id=data["id"],
            name=data["name"],
            slug=data["slug"],
            match=data.get("match"),
            matching_algorithm=data.get("matching_algorithm"),
            is_insensitive=data.get("is_insensitive", False),
            document_count=data.get("document_count", 0),
        )


CorrespondentListResponse = PaginatedResponse[Correspondent]
DocumentTypeListResponse = PaginatedResponse[DocumentType]
