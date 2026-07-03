"""Paperless-ngx API models."""

from paperless_cli.models.base import PaginatedResponse
from paperless_cli.models.correspondent import (
    Correspondent,
    CorrespondentListResponse,
    DocumentType,
    DocumentTypeListResponse,
)
from paperless_cli.models.document import (
    BulkEditRequest,
    BulkEditResponse,
    Document,
    DocumentListResponse,
    DocumentSearchParams,
    DocumentUpdateRequest,
)
from paperless_cli.models.mail import (
    MailAccount,
    MailAccountListResponse,
    MailRule,
    MailRuleCreateRequest,
    MailRuleListResponse,
    MailRuleUpdateRequest,
)
from paperless_cli.models.tag import Tag, TagCreateRequest, TagListResponse
from paperless_cli.models.task import Task

__all__ = [
    "PaginatedResponse",
    "Document",
    "DocumentListResponse",
    "DocumentSearchParams",
    "DocumentUpdateRequest",
    "BulkEditRequest",
    "BulkEditResponse",
    "Tag",
    "TagCreateRequest",
    "TagListResponse",
    "Task",
    "MailAccount",
    "MailAccountListResponse",
    "MailRule",
    "MailRuleCreateRequest",
    "MailRuleUpdateRequest",
    "MailRuleListResponse",
    "Correspondent",
    "CorrespondentListResponse",
    "DocumentType",
    "DocumentTypeListResponse",
]
