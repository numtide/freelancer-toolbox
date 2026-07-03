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
    "BulkEditRequest",
    "BulkEditResponse",
    "Correspondent",
    "CorrespondentListResponse",
    "Document",
    "DocumentListResponse",
    "DocumentSearchParams",
    "DocumentType",
    "DocumentTypeListResponse",
    "DocumentUpdateRequest",
    "MailAccount",
    "MailAccountListResponse",
    "MailRule",
    "MailRuleCreateRequest",
    "MailRuleListResponse",
    "MailRuleUpdateRequest",
    "PaginatedResponse",
    "Tag",
    "TagCreateRequest",
    "TagListResponse",
    "Task",
]
