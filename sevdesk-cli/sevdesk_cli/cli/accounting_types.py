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

    limit: int | None = None
    offset: int | None = None


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
    list_parser = accounting_type_subparsers.add_parser(
        "list",
        help="List accounting types",
    )
    list_parser.add_argument(
        "--limit",
        type=int,
        help="Limit number of results",
    )
    list_parser.add_argument(
        "--offset",
        type=int,
        help="Skip number of results",
    )


def list_accounting_types(api: SevDeskAPI, cmd: AccountingTypesListCommand) -> None:
    """List accounting types."""
    try:
        result = api.accounting_types.get_accounting_types(
            limit=cmd.limit,
            offset=cmd.offset,
            count_all=True,
        )
    except Exception as e:
        msg = f"Failed to fetch accounting types: {e}"
        raise SevDeskCLIError(msg) from e

    accounting_types = result.get("objects", [])
    total = result.get("total", len(accounting_types))

    if not accounting_types:
        print("No accounting types found.")
        return

    # Display accounting types
    print(f"Found {len(accounting_types)} accounting type(s) (Total: {total}):")
    print("-" * 80)

    for acc_type in accounting_types:
        _display_accounting_type_summary(acc_type)
        print("-" * 80)


def _display_accounting_type_summary(acc_type: dict[str, Any]) -> None:
    """Display an accounting type summary."""
    acc_id = acc_type.get("id", "N/A")
    name = acc_type.get("name", "N/A")
    number = acc_type.get("number", "N/A")

    # Determine account type based on fields
    expense_account = acc_type.get("expenseAccount")
    revenue_account = acc_type.get("revenueAccount")
    asset_account = acc_type.get("assetAccount", "0")
    balance_side = acc_type.get("balanceSide", "")

    type_desc = "General"
    if asset_account == "1":
        type_desc = "Asset"
    elif expense_account == "1":
        type_desc = "Expense"
    elif revenue_account == "1":
        type_desc = "Revenue"
    elif balance_side:
        type_desc = f"Balance ({balance_side})"

    print(f"ID: {acc_id}")
    print(f"Number: {number}")
    print(f"Name: {name}")
    print(f"Type: {type_desc}")

    # Show if deprecated or hidden
    deprecated = acc_type.get("deprecated", "0")
    hidden = acc_type.get("hidden", "0")
    deactivated = acc_type.get("deactivated", "0")

    status_parts = []
    if deprecated == "1":
        status_parts.append("Deprecated")
    if hidden == "1":
        status_parts.append("Hidden")
    if deactivated == "1":
        status_parts.append("Deactivated")

    if status_parts:
        print(f"Status: {', '.join(status_parts)}")

    # Show description if available
    simple_desc = acc_type.get("simpleDescription")
    if simple_desc:
        print(f"Description: {simple_desc}")


def parse_accounting_type_command(
    args: argparse.Namespace,
) -> AccountingTypesListCommand | None:
    """Parse accounting type command from argparse namespace."""
    if not hasattr(args, "action"):
        return None

    match args.action:
        case "list":
            return AccountingTypesListCommand(
                limit=getattr(args, "limit", None),
                offset=getattr(args, "offset", None),
            )
        case _:
            return None
