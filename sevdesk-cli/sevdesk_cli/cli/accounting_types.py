"""Accounting type management commands for SevDesk."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sevdesk_cli.errors import SevDeskCLIError

if TYPE_CHECKING:
    import argparse

    from sevdesk_api import SevDeskAPI


@dataclass
class AccountingTypesListCommand:
    """Accounting types list command."""


def add_accounting_type_subparser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Add accounting type subcommands to the parser."""
    accounting_type_parser = subparsers.add_parser(
        "accounting-types",
        help="Manage accounting types (booking accounts)",
    )
    accounting_type_subparsers = accounting_type_parser.add_subparsers(
        dest="action",
        help="Accounting type actions",
    )

    # List accounting types
    accounting_type_subparsers.add_parser(
        "list",
        help="List accounting types",
    )


def list_accounting_types(api: SevDeskAPI, cmd: AccountingTypesListCommand) -> None:  # noqa: ARG001
    """List accounting types."""
    try:
        result = api.accounting_types.get_accounting_types()
    except Exception as e:
        msg = f"Failed to fetch accounting types: {e}"
        raise SevDeskCLIError(msg) from e

    accounting_types = result.get("objects", [])

    if not accounting_types:
        print("No accounting types found.")
        return

    # Display accounting types
    print(f"Found {len(accounting_types)} accounting type(s):")
    print("-" * 80)

    for acc_type in accounting_types:
        _display_accounting_type_summary(acc_type)
        print("-" * 80)


def _display_accounting_type_summary(acc_type: dict[str, Any]) -> None:
    """Display an accounting type summary."""
    acc_id = acc_type.get("accountDatevId", "N/A")
    name = acc_type.get("accountName", "N/A")
    number = acc_type.get("accountNumber", "N/A")

    # Get account type description
    type_field = acc_type.get("accountGuideType", "")
    type_desc_map = {
        "ASSET": "Asset",
        "EXPENSE": "Expense",
        "REVENUE": "Revenue",
        "REGULAR": "Regular",
        "EQUITYOUT": "Equity Out (Privatentnahme)",
        "EQUITYIN": "Equity In (Privateinlage)",
    }
    type_desc = type_desc_map.get(type_field, type_field or "General")

    print(f"ID: {acc_id}")
    print(f"Number: {number}")
    print(f"Name: {name}")
    print(f"Type: {type_desc}")

    # Show if favorite
    if acc_type.get("favorite"):
        print("Favorite: Yes")

    # Show if hidden
    if acc_type.get("hidden"):
        print("Status: Hidden")

    # Show description if available
    description = acc_type.get("description")
    if description:
        print(f"Description: {description}")

    # Show allowed tax rules
    tax_rules = acc_type.get("allowedTaxRules", [])
    if tax_rules:
        tax_rule_names = [rule.get("name", "") for rule in tax_rules]
        print(f"Allowed tax rules: {', '.join(tax_rule_names)}")


def parse_accounting_type_command(
    args: argparse.Namespace,
) -> AccountingTypesListCommand | None:
    """Parse accounting type command from argparse namespace."""
    if not hasattr(args, "action"):
        return None

    match args.action:
        case "list":
            return AccountingTypesListCommand()
        case _:
            return None
