"""Mail rule management commands for Paperless-ngx."""

from dataclasses import dataclass
from enum import IntEnum

from paperless_cli.api import PaperlessClient
from paperless_cli.cli.formatter import print_table
from paperless_cli.models import MailRuleCreateRequest, MailRuleUpdateRequest


class MailAction(IntEnum):
    """Mail rule action types from Paperless-ngx."""

    DELETE = 1
    MOVE = 2
    MARK_READ = 3
    FLAG = 4
    TAG = 5


@dataclass
class MailRulesListCommand:
    """Mail rules list command."""


@dataclass
class MailRulesShowCommand:
    """Mail rules show command."""

    rule_id: int


@dataclass
class MailRulesCreateCommand:
    """Mail rules create command."""

    name: str
    order: int = 0
    enabled: bool = True
    account: int | None = None
    filter_from: str | None = None
    filter_to: str | None = None
    filter_subject: str | None = None
    filter_body: str | None = None
    filter_folder: str | None = None
    rule_action: MailAction | None = None
    action_parameter: str | None = None
    assign_title_from: int | None = None
    assign_correspondent_from: int | None = None
    assign_tags: str | None = None
    assign_document_type: int | None = None
    assign_correspondent: int | None = None


@dataclass
class MailRulesUpdateCommand:
    """Mail rules update command."""

    rule_id: int
    name: str | None = None
    order: int | None = None
    enabled: bool | None = None
    account: int | None = None
    filter_from: str | None = None
    filter_to: str | None = None
    filter_subject: str | None = None
    filter_body: str | None = None
    filter_folder: str | None = None
    rule_action: MailAction | None = None
    action_parameter: str | None = None
    assign_title_from: int | None = None
    assign_correspondent_from: int | None = None
    assign_tags: str | None = None
    assign_document_type: int | None = None
    assign_correspondent: int | None = None


@dataclass
class MailRulesDeleteCommand:
    """Mail rules delete command."""

    rule_id: int
    force: bool = False


def list_mail_rules(client: PaperlessClient) -> None:
    """List all mail rules."""
    rules = client.get_mail_rules()
    if not rules:
        print("No mail rules found.")
        return

    headers = ["ID", "Name", "Order", "Account", "Filter From", "Action", "Enabled"]
    rows = []
    for rule in rules:
        account_name = "Any"
        if rule.account:
            accounts = client.get_mail_accounts()
            account = next((a for a in accounts if a.id == rule.account), None)
            if account:
                account_name = account.name

        rows.append(
            [
                rule.id,
                rule.name,
                rule.order,
                account_name,
                rule.filter_from or "-",
                rule.action or "default",
                "Yes" if rule.enabled else "No",
            ]
        )
    print_table(headers, rows)


def show_mail_rule(client: PaperlessClient, rule_id: int) -> None:
    """Show details of a mail rule."""
    rule = client.get_mail_rule(rule_id)

    print(f"\nMail Rule Details (ID: {rule.id})")
    print("=" * 50)
    print(f"Name: {rule.name}")
    print(f"Order: {rule.order}")
    print(f"Enabled: {'Yes' if rule.enabled else 'No'}")

    if rule.account:
        accounts = client.get_mail_accounts()
        account = next((a for a in accounts if a.id == rule.account), None)
        if account:
            print(f"Account: {account.name}")
    else:
        print("Account: Any")

    print("\nFilters:")
    print("-" * 20)
    filters = [
        ("From", "filter_from"),
        ("To", "filter_to"),
        ("Subject", "filter_subject"),
        ("Body", "filter_body"),
        ("Folder", "filter_folder"),
    ]
    for label, key in filters:
        if hasattr(rule, key) and getattr(rule, key):
            print(f"{label}: {getattr(rule, key)}")

    print("\nActions:")
    print("-" * 20)
    print(f"Action: {rule.action or 'default'}")
    print(f"Action Parameter: {rule.action_parameter or '-'}")

    print("\nMetadata Assignment:")
    print("-" * 20)
    if rule.assign_title_from:
        print(f"Title From: {rule.assign_title_from}")
    if rule.assign_correspondent_from:
        print(f"Correspondent From: {rule.assign_correspondent_from}")

    if rule.assign_tags:
        tags = client.get_tags()
        tag_names = [tag.name for tag in tags if tag.id in rule.assign_tags]
        print(f"Tags: {', '.join(tag_names)}")

    if rule.assign_document_type:
        doc_types = client.get_document_types()
        doc_type = next(
            (dt for dt in doc_types if dt.id == rule.assign_document_type),
            None,
        )
        if doc_type:
            print(f"Document Type: {doc_type.name}")

    if rule.assign_correspondent:
        correspondents = client.get_correspondents()
        correspondent = next(
            (c for c in correspondents if c.id == rule.assign_correspondent),
            None,
        )
        if correspondent:
            print(f"Correspondent: {correspondent.name}")


def create_mail_rule(client: PaperlessClient, cmd: MailRulesCreateCommand) -> None:
    """Create a new mail rule."""
    create_request = MailRuleCreateRequest.from_command(cmd)
    rule = client.create_mail_rule(create_request)
    print(f"Created mail rule '{rule.name}' with ID {rule.id}")


def update_mail_rule(client: PaperlessClient, cmd: MailRulesUpdateCommand) -> None:
    """Update an existing mail rule."""
    # Get existing rule first
    rule = client.get_mail_rule(cmd.rule_id)

    # Create update request from command
    update_request = MailRuleUpdateRequest.from_command(cmd)

    # Update the rule
    updated_rule = client.update_mail_rule(cmd.rule_id, update_request, rule)
    print(f"Updated mail rule '{updated_rule.name}' (ID: {cmd.rule_id})")


def delete_mail_rule(client: PaperlessClient, rule_id: int, force: bool) -> None:
    """Delete a mail rule."""
    if not force:
        rule = client.get_mail_rule(rule_id)
        confirm = input(
            f"Are you sure you want to delete rule '{rule.name}' (ID: {rule_id})? [y/N]: "
        )
        if confirm.lower() != "y":
            print("Cancelled.")
            return

    client.delete_mail_rule(rule_id)
    print(f"Deleted mail rule with ID {rule_id}")
