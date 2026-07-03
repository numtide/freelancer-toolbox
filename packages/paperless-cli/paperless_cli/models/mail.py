"""Mail-related models for Paperless-ngx API."""

from dataclasses import dataclass, field
from typing import Any

from paperless_cli.models.base import PaginatedResponse


@dataclass
class MailAccount:
    """Represents a mail account in Paperless-ngx."""

    id: int
    name: str
    imap_server: str
    imap_port: int
    imap_security: str
    username: str
    password: str
    character_set: str | None = None
    owner: int | None = None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "MailAccount":
        """Create a MailAccount instance from API response data."""
        return cls(
            id=data["id"],
            name=data["name"],
            imap_server=data["imap_server"],
            imap_port=data["imap_port"],
            imap_security=data["imap_security"],
            username=data["username"],
            password=data["password"],
            character_set=data.get("character_set"),
            owner=data.get("owner"),
        )


@dataclass
class MailRule:
    """Represents a mail rule in Paperless-ngx."""

    id: int
    name: str
    account: int
    folder: str
    filter_from: str | None = None
    filter_to: str | None = None
    filter_subject: str | None = None
    filter_body: str | None = None
    filter_attachment_filename: str | None = None
    maximum_age: int = 30
    action: str = "mark_read"
    action_parameter: str | None = None
    assign_title_from: int | None = None
    assign_correspondent_from: int | None = None
    assign_tags: list[int] | None = None
    assign_document_type: int | None = None
    assign_correspondent: int | None = None
    owner: int | None = None
    order: int = 0
    attachment_type: int = 1
    filter_attachment_filename_include: str | None = None
    filter_attachment_filename_exclude: str | None = None
    consumption_scope: int = 1
    enabled: bool = True

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "MailRule":
        """Create a MailRule instance from API response data."""
        return cls(
            id=data["id"],
            name=data["name"],
            account=data["account"],
            folder=data["folder"],
            filter_from=data.get("filter_from"),
            filter_to=data.get("filter_to"),
            filter_subject=data.get("filter_subject"),
            filter_body=data.get("filter_body"),
            filter_attachment_filename=data.get("filter_attachment_filename"),
            maximum_age=data.get("maximum_age", 30),
            action=data.get("action", "mark_read"),
            action_parameter=data.get("action_parameter"),
            assign_title_from=data.get("assign_title_from"),
            assign_correspondent_from=data.get("assign_correspondent_from"),
            assign_tags=data.get("assign_tags"),
            assign_document_type=data.get("assign_document_type"),
            assign_correspondent=data.get("assign_correspondent"),
            owner=data.get("owner"),
            order=data.get("order", 0),
            attachment_type=data.get("attachment_type", 1),
            filter_attachment_filename_include=data.get("filter_attachment_filename_include"),
            filter_attachment_filename_exclude=data.get("filter_attachment_filename_exclude"),
            consumption_scope=data.get("consumption_scope", 1),
            enabled=data.get("enabled", True),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API request."""
        data: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "account": self.account,
            "folder": self.folder,
            "order": self.order,
        }
        if self.filter_from is not None:
            data["filter_from"] = self.filter_from
        if self.filter_to is not None:
            data["filter_to"] = self.filter_to
        if self.filter_subject is not None:
            data["filter_subject"] = self.filter_subject
        if self.filter_body is not None:
            data["filter_body"] = self.filter_body
        if self.filter_attachment_filename is not None:
            data["filter_attachment_filename"] = self.filter_attachment_filename
        if self.maximum_age != 30:
            data["maximum_age"] = self.maximum_age
        if self.action != "mark_read":
            data["action"] = self.action
        if self.action_parameter is not None:
            data["action_parameter"] = self.action_parameter
        if self.assign_title_from is not None:
            data["assign_title_from"] = self.assign_title_from
        if self.assign_correspondent_from is not None:
            data["assign_correspondent_from"] = self.assign_correspondent_from
        if self.assign_tags is not None:
            data["assign_tags"] = self.assign_tags
        if self.assign_document_type is not None:
            data["assign_document_type"] = self.assign_document_type
        if self.assign_correspondent is not None:
            data["assign_correspondent"] = self.assign_correspondent
        if self.owner is not None:
            data["owner"] = self.owner
        if self.attachment_type != 1:
            data["attachment_type"] = self.attachment_type
        if self.filter_attachment_filename_include is not None:
            data["filter_attachment_filename_include"] = self.filter_attachment_filename_include
        if self.filter_attachment_filename_exclude is not None:
            data["filter_attachment_filename_exclude"] = self.filter_attachment_filename_exclude
        if self.consumption_scope != 1:
            data["consumption_scope"] = self.consumption_scope
        if not self.enabled:
            data["enabled"] = self.enabled
        return data


@dataclass
class MailRuleCreateRequest:
    """Request to create a new mail rule."""

    name: str
    order: int = 0
    enabled: bool = True
    account: int | None = None
    folder: str = "INBOX"
    filter_from: str | None = None
    filter_to: str | None = None
    filter_subject: str | None = None
    filter_body: str | None = None
    filter_attachment_filename: str | None = None
    maximum_age: int = 30
    action: str = "mark_read"
    action_parameter: str | None = None
    assign_title_from: int | None = None
    assign_correspondent_from: int | None = None
    assign_tags: list[int] = field(default_factory=list)
    assign_document_type: int | None = None
    assign_correspondent: int | None = None
    owner: int | None = None
    attachment_type: int = 1
    filter_attachment_filename_include: str | None = None
    filter_attachment_filename_exclude: str | None = None
    consumption_scope: int = 1

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API request."""
        data: dict[str, Any] = {
            "name": self.name,
            "order": self.order,
            "enabled": self.enabled,
            "folder": self.folder,
        }

        # Add optional fields
        if self.account is not None:
            data["account"] = self.account
        if self.filter_from is not None:
            data["filter_from"] = self.filter_from
        if self.filter_to is not None:
            data["filter_to"] = self.filter_to
        if self.filter_subject is not None:
            data["filter_subject"] = self.filter_subject
        if self.filter_body is not None:
            data["filter_body"] = self.filter_body
        if self.filter_attachment_filename is not None:
            data["filter_attachment_filename"] = self.filter_attachment_filename
        if self.maximum_age != 30:
            data["maximum_age"] = self.maximum_age
        if self.action != "mark_read":
            data["action"] = self.action
        if self.action_parameter is not None:
            data["action_parameter"] = self.action_parameter
        if self.assign_title_from is not None:
            data["assign_title_from"] = self.assign_title_from
        if self.assign_correspondent_from is not None:
            data["assign_correspondent_from"] = self.assign_correspondent_from
        if self.assign_tags:
            data["assign_tags"] = self.assign_tags
        if self.assign_document_type is not None:
            data["assign_document_type"] = self.assign_document_type
        if self.assign_correspondent is not None:
            data["assign_correspondent"] = self.assign_correspondent
        if self.owner is not None:
            data["owner"] = self.owner
        if self.attachment_type != 1:
            data["attachment_type"] = self.attachment_type
        if self.filter_attachment_filename_include is not None:
            data["filter_attachment_filename_include"] = self.filter_attachment_filename_include
        if self.filter_attachment_filename_exclude is not None:
            data["filter_attachment_filename_exclude"] = self.filter_attachment_filename_exclude
        if self.consumption_scope != 1:
            data["consumption_scope"] = self.consumption_scope

        return data

    @classmethod
    def from_command(cls, cmd: Any) -> "MailRuleCreateRequest":
        """Create from CLI command object."""
        request = cls(
            name=cmd.name,
            order=cmd.order,
            enabled=cmd.enabled,
        )

        # Map optional fields from command
        if hasattr(cmd, "account") and cmd.account is not None:
            request.account = cmd.account
        if hasattr(cmd, "filter_from") and cmd.filter_from:
            request.filter_from = cmd.filter_from
        if hasattr(cmd, "filter_to") and cmd.filter_to:
            request.filter_to = cmd.filter_to
        if hasattr(cmd, "filter_subject") and cmd.filter_subject:
            request.filter_subject = cmd.filter_subject
        if hasattr(cmd, "filter_body") and cmd.filter_body:
            request.filter_body = cmd.filter_body
        if hasattr(cmd, "filter_folder") and cmd.filter_folder:
            request.folder = cmd.filter_folder
        if hasattr(cmd, "rule_action") and cmd.rule_action:
            request.action = str(cmd.rule_action.value)
        if hasattr(cmd, "action_parameter") and cmd.action_parameter:
            request.action_parameter = cmd.action_parameter
        if hasattr(cmd, "assign_title_from") and cmd.assign_title_from is not None:
            request.assign_title_from = cmd.assign_title_from
        if hasattr(cmd, "assign_correspondent_from") and cmd.assign_correspondent_from is not None:
            request.assign_correspondent_from = cmd.assign_correspondent_from
        if hasattr(cmd, "assign_tags") and cmd.assign_tags:
            request.assign_tags = [int(tag_id) for tag_id in cmd.assign_tags.split(",")]
        if hasattr(cmd, "assign_document_type") and cmd.assign_document_type is not None:
            request.assign_document_type = cmd.assign_document_type
        if hasattr(cmd, "assign_correspondent") and cmd.assign_correspondent is not None:
            request.assign_correspondent = cmd.assign_correspondent

        return request


@dataclass
class MailRuleUpdateRequest:
    """Request to update a mail rule."""

    rule_id: int
    name: str | None = None
    order: int | None = None
    enabled: bool | None = None
    account: int | None = None
    folder: str | None = None
    filter_from: str | None = None
    filter_to: str | None = None
    filter_subject: str | None = None
    filter_body: str | None = None
    filter_attachment_filename: str | None = None
    maximum_age: int | None = None
    action: str | None = None
    action_parameter: str | None = None
    assign_title_from: int | None = None
    assign_correspondent_from: int | None = None
    assign_tags: list[int] | None = None
    assign_document_type: int | None = None
    assign_correspondent: int | None = None
    owner: int | None = None
    attachment_type: int | None = None
    filter_attachment_filename_include: str | None = None
    filter_attachment_filename_exclude: str | None = None
    consumption_scope: int | None = None

    def apply_to_rule(self, rule: MailRule) -> dict[str, Any]:
        """Apply updates to an existing rule and return the updated data."""
        # Start with the existing rule data
        data = rule.to_dict()

        # Apply updates
        if self.name is not None:
            data["name"] = self.name
        if self.order is not None:
            data["order"] = self.order
        if self.enabled is not None:
            data["enabled"] = self.enabled
        if self.account is not None:
            data["account"] = self.account
        if self.folder is not None:
            data["folder"] = self.folder
        if self.filter_from is not None:
            data["filter_from"] = self.filter_from
        if self.filter_to is not None:
            data["filter_to"] = self.filter_to
        if self.filter_subject is not None:
            data["filter_subject"] = self.filter_subject
        if self.filter_body is not None:
            data["filter_body"] = self.filter_body
        if self.filter_attachment_filename is not None:
            data["filter_attachment_filename"] = self.filter_attachment_filename
        if self.maximum_age is not None:
            data["maximum_age"] = self.maximum_age
        if self.action is not None:
            data["action"] = self.action
        if self.action_parameter is not None:
            data["action_parameter"] = self.action_parameter
        if self.assign_title_from is not None:
            data["assign_title_from"] = self.assign_title_from
        if self.assign_correspondent_from is not None:
            data["assign_correspondent_from"] = self.assign_correspondent_from
        if self.assign_tags is not None:
            data["assign_tags"] = self.assign_tags
        if self.assign_document_type is not None:
            data["assign_document_type"] = self.assign_document_type
        if self.assign_correspondent is not None:
            data["assign_correspondent"] = self.assign_correspondent
        if self.owner is not None:
            data["owner"] = self.owner
        if self.attachment_type is not None:
            data["attachment_type"] = self.attachment_type
        if self.filter_attachment_filename_include is not None:
            data["filter_attachment_filename_include"] = self.filter_attachment_filename_include
        if self.filter_attachment_filename_exclude is not None:
            data["filter_attachment_filename_exclude"] = self.filter_attachment_filename_exclude
        if self.consumption_scope is not None:
            data["consumption_scope"] = self.consumption_scope

        return data

    @classmethod
    def from_command(cls, cmd: Any) -> "MailRuleUpdateRequest":
        """Create from CLI command object."""
        request = cls(rule_id=cmd.rule_id)

        # Map optional fields from command
        if hasattr(cmd, "name") and cmd.name is not None:
            request.name = cmd.name
        if hasattr(cmd, "order") and cmd.order is not None:
            request.order = cmd.order
        if hasattr(cmd, "enabled") and cmd.enabled is not None:
            request.enabled = cmd.enabled
        if hasattr(cmd, "account") and cmd.account is not None:
            request.account = cmd.account
        if hasattr(cmd, "filter_from") and cmd.filter_from is not None:
            request.filter_from = cmd.filter_from
        if hasattr(cmd, "filter_to") and cmd.filter_to is not None:
            request.filter_to = cmd.filter_to
        if hasattr(cmd, "filter_subject") and cmd.filter_subject is not None:
            request.filter_subject = cmd.filter_subject
        if hasattr(cmd, "filter_body") and cmd.filter_body is not None:
            request.filter_body = cmd.filter_body
        if hasattr(cmd, "filter_folder") and cmd.filter_folder is not None:
            request.folder = cmd.filter_folder
        if hasattr(cmd, "rule_action") and cmd.rule_action is not None:
            request.action = str(cmd.rule_action.value)
        if hasattr(cmd, "action_parameter") and cmd.action_parameter is not None:
            request.action_parameter = cmd.action_parameter
        if hasattr(cmd, "assign_title_from") and cmd.assign_title_from is not None:
            request.assign_title_from = cmd.assign_title_from
        if hasattr(cmd, "assign_correspondent_from") and cmd.assign_correspondent_from is not None:
            request.assign_correspondent_from = cmd.assign_correspondent_from
        if hasattr(cmd, "assign_tags") and cmd.assign_tags is not None:
            request.assign_tags = [int(tag_id) for tag_id in cmd.assign_tags.split(",")]
        if hasattr(cmd, "assign_document_type") and cmd.assign_document_type is not None:
            request.assign_document_type = cmd.assign_document_type
        if hasattr(cmd, "assign_correspondent") and cmd.assign_correspondent is not None:
            request.assign_correspondent = cmd.assign_correspondent

        return request


MailAccountListResponse = PaginatedResponse[MailAccount]
MailRuleListResponse = PaginatedResponse[MailRule]
