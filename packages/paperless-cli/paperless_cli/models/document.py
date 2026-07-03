"""Document models for Paperless-ngx API."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from paperless_cli.models.base import PaginatedResponse


@dataclass
class Document:
    """Represents a document in Paperless-ngx."""

    id: int
    correspondent: int | None
    document_type: int | None
    storage_path: int | None
    title: str
    content: str
    tags: list[int]
    created: datetime
    created_date: datetime | None
    modified: datetime
    added: datetime
    archive_serial_number: int | None
    original_file_name: str
    archived_file_name: str | None
    owner: int | None
    user_can_change: bool = True
    is_shared_by_requester: bool = False
    notes: list[Any] = field(default_factory=list)
    custom_fields: list[Any] = field(default_factory=list)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "Document":
        """Create a Document instance from API response data."""
        return cls(
            id=data["id"],
            correspondent=data.get("correspondent"),
            document_type=data.get("document_type"),
            storage_path=data.get("storage_path"),
            title=data["title"],
            content=data.get("content", ""),
            tags=data.get("tags", []),
            created=datetime.fromisoformat(data["created"].replace("Z", "+00:00")),
            created_date=datetime.fromisoformat(data["created_date"].replace("Z", "+00:00"))
            if data.get("created_date")
            else None,
            modified=datetime.fromisoformat(data["modified"].replace("Z", "+00:00")),
            added=datetime.fromisoformat(data["added"].replace("Z", "+00:00")),
            archive_serial_number=data.get("archive_serial_number"),
            original_file_name=data["original_file_name"],
            archived_file_name=data.get("archived_file_name"),
            owner=data.get("owner"),
            user_can_change=data.get("user_can_change", True),
            is_shared_by_requester=data.get("is_shared_by_requester", False),
            notes=data.get("notes", []),
            custom_fields=data.get("custom_fields", []),
        )


@dataclass
class DocumentSearchParams:
    """Parameters for searching documents."""

    query: str | None = None
    tags__id__in: list[int] | None = None
    page: int = 1
    page_size: int = 25
    ordering: str | None = None

    def to_params(self) -> dict[str, Any]:
        """Convert to URL parameters."""
        params: dict[str, Any] = {
            "page": self.page,
            "page_size": self.page_size,
        }
        if self.query:
            params["query"] = self.query
        if self.tags__id__in:
            params["tags__id__in"] = ",".join(str(tag_id) for tag_id in self.tags__id__in)
        if self.ordering:
            params["ordering"] = self.ordering
        return params


@dataclass
class DocumentUpdateRequest:
    """Request to update a document."""

    title: str | None = None
    correspondent: int | None = None
    document_type: int | None = None
    storage_path: int | None = None
    tags: list[int] | None = None
    created_date: datetime | None = None
    archive_serial_number: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API request."""
        data: dict[str, Any] = {}
        if self.title is not None:
            data["title"] = self.title
        if self.correspondent is not None:
            data["correspondent"] = self.correspondent
        if self.document_type is not None:
            data["document_type"] = self.document_type
        if self.storage_path is not None:
            data["storage_path"] = self.storage_path
        if self.tags is not None:
            data["tags"] = self.tags
        if self.created_date is not None:
            data["created_date"] = self.created_date.isoformat()
        if self.archive_serial_number is not None:
            data["archive_serial_number"] = self.archive_serial_number
        return data


@dataclass
class BulkEditRequest:
    """Request for bulk editing documents."""

    documents: list[int]
    method: Literal["add_tag", "remove_tag", "modify_tags", "delete"]
    parameters: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API request."""
        return {
            "documents": self.documents,
            "method": self.method,
            "parameters": self.parameters,
        }


@dataclass
class BulkEditResponse:
    """Response from bulk edit operation."""

    affected_documents: list[int]


DocumentListResponse = PaginatedResponse[Document]
