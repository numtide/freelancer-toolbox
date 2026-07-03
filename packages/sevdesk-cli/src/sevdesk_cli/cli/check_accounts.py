"""Check account management commands for SevDesk."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sevdesk_api import CheckAccountStatus

from sevdesk_cli.errors import SevDeskCLIError

if TYPE_CHECKING:
    import argparse

    from sevdesk_api import SevDeskAPI


@dataclass
class CheckAccountsListCommand:
    """Check accounts list command."""

    limit: int | None = None
    offset: int | None = None


@dataclass
class CheckAccountsGetCommand:
    """Check accounts get command."""

    check_account_id: int


@dataclass
class CheckAccountsCreateClearingCommand:
    """Check accounts create clearing command."""

    name: str
    accounting_number: int | None = None


@dataclass
class CheckAccountsBalanceCommand:
    """Check accounts balance command."""

    check_account_id: int


def add_check_account_subparser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Add check account subcommands to the parser."""
    check_account_parser = subparsers.add_parser(
        "check-accounts",
        help="Manage check accounts",
    )
    check_account_subparsers = check_account_parser.add_subparsers(
        dest="action",
        help="Check account actions",
    )

    # List check accounts
    list_parser = check_account_subparsers.add_parser(
        "list",
        help="List check accounts",
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

    # Get check account
    get_parser = check_account_subparsers.add_parser(
        "get",
        help="Get check account details",
    )
    get_parser.add_argument("check_account_id", type=int, help="Check account ID")

    # Create clearing account
    clearing_parser = check_account_subparsers.add_parser(
        "create-clearing",
        help="Create a clearing account",
    )
    clearing_parser.add_argument(
        "name",
        help="Name of the check account",
    )
    clearing_parser.add_argument(
        "--accounting-number",
        type=int,
        help="Booking account number",
    )

    # Get balance
    balance_parser = check_account_subparsers.add_parser(
        "balance",
        help="Get check account balance",
    )
    balance_parser.add_argument("check_account_id", type=int, help="Check account ID")


def list_check_accounts(api: SevDeskAPI, cmd: CheckAccountsListCommand) -> None:
    """List check accounts."""
    try:
        result = api.check_accounts.get_check_accounts(
            limit=cmd.limit,
            offset=cmd.offset,
        )
    except Exception as e:
        msg = f"Failed to fetch check accounts: {e}"
        raise SevDeskCLIError(msg) from e

    accounts = result.get("objects", [])
    if not accounts:
        print("No check accounts found.")
        return

    # Display check accounts
    print(f"Found {len(accounts)} check account(s):")
    print("-" * 80)

    for account in accounts:
        _display_check_account_summary(account)
        print("-" * 80)


def _display_check_account_summary(account: dict[str, Any]) -> None:
    """Display a check account summary."""
    account_id = account.get("id", "N/A")
    name = account.get("name", "N/A")
    account_type = account.get("type", "N/A")
    currency = account.get("currency", "EUR")
    status = account.get("status", "N/A")
    iban = account.get("iban", "")

    # Format type
    type_display = {
        "online": "Bank Account",
        "offline": "Clearing Account",
        "register": "Cash Register",
    }.get(account_type, account_type)

    # Format status
    try:
        status_int = int(status)
        status_enum = CheckAccountStatus(status_int)
        status_text = f"{status_enum.name} ({status})"
    except (ValueError, TypeError):
        status_text = f"Unknown ({status})"

    print(f"ID: {account_id}")
    print(f"Name: {name}")
    print(f"Type: {type_display}")
    print(f"Currency: {currency}")
    print(f"Status: {status_text}")
    if iban:
        print(f"IBAN: {iban}")

    # Show current balance if available
    current_balance = account.get("currentBalance")
    if current_balance is not None:
        print(f"Current Balance: {current_balance:,.2f} {currency}")


def _format_account_type(account_type: str) -> str:
    """Format account type for display."""
    type_mapping = {
        "online": "Bank Account",
        "offline": "Clearing Account",
        "register": "Cash Register",
    }
    return type_mapping.get(account_type, account_type)


def _format_account_status(status: str | int | None) -> str:
    """Format account status for display."""
    if status is None:
        return "Unknown (None)"
    try:
        status_int = int(status)
        status_enum = CheckAccountStatus(status_int)
    except (ValueError, TypeError):
        return f"Unknown ({status})"
    else:
        return f"{status_enum.name} ({status})"


def _format_basic_info(account: dict[str, Any], check_account_id: int) -> list[str]:
    """Format basic account information."""
    return [
        f"Check Account #{check_account_id}",
        "=" * 80,
        f"Name: {account.get('name', 'N/A')}",
        f"Type: {_format_account_type(account.get('type', 'N/A'))}",
        f"Status: {_format_account_status(account.get('status', 'N/A'))}",
    ]


def _format_financial_info(account: dict[str, Any]) -> list[str]:
    """Format financial information."""
    lines = []
    currency = account.get("currency", "EUR")
    lines.append(f"\nCurrency: {currency}")

    current_balance = account.get("currentBalance")
    if current_balance is not None:
        lines.append(f"Current Balance: {current_balance:,.2f} {currency}")

    return lines


def _format_bank_details(account: dict[str, Any]) -> list[str]:
    """Format bank details."""
    lines = []
    iban = account.get("iban")
    if iban:
        lines.append(f"\nIBAN: {iban}")

    bank_server = account.get("bankServer")
    if bank_server:
        lines.append(f"Bank Server: {bank_server}")

    return lines


def _format_import_settings(account: dict[str, Any]) -> list[str]:
    """Format import settings."""
    lines = []
    import_type = account.get("importType")
    if import_type:
        lines.append(f"\nImport Type: {import_type}")

    auto_map = account.get("autoMapTransactions")
    if auto_map is not None:
        lines.append(f"Auto Map Transactions: {'Yes' if auto_map else 'No'}")

    return lines


def _format_accounting_info(account: dict[str, Any]) -> list[str]:
    """Format accounting information."""
    lines = []
    default_account = account.get("defaultAccount")
    if default_account:
        lines.append(f"\nDefault Booking Account: {default_account}")

    return lines


def _format_dates(account: dict[str, Any]) -> list[str]:
    """Format creation and update dates."""
    lines = []
    create_date = account.get("create")
    if create_date:
        lines.append(f"\nCreated: {create_date}")

    update_date = account.get("update")
    if update_date:
        lines.append(f"Updated: {update_date}")

    return lines


def get_check_account(api: SevDeskAPI, cmd: CheckAccountsGetCommand) -> None:
    """Get check account details."""
    try:
        result = api.check_accounts.get_check_account(cmd.check_account_id)
    except Exception as e:
        msg = f"Failed to fetch check account {cmd.check_account_id}: {e}"
        raise SevDeskCLIError(msg) from e

    # Parse account data
    try:
        account = result.get("objects", [{}])[0]
    except (IndexError, TypeError) as e:
        msg = f"Invalid response format for check account {cmd.check_account_id}"
        raise SevDeskCLIError(msg) from e

    if not account:
        print(f"Check account {cmd.check_account_id} not found.")
        return

    # Format and display detailed check account information
    output_lines = []
    output_lines.extend(_format_basic_info(account, cmd.check_account_id))
    output_lines.extend(_format_financial_info(account))
    output_lines.extend(_format_bank_details(account))
    output_lines.extend(_format_import_settings(account))
    output_lines.extend(_format_accounting_info(account))
    output_lines.extend(_format_dates(account))

    for line in output_lines:
        print(line)


def create_clearing_account(
    api: SevDeskAPI,
    cmd: CheckAccountsCreateClearingCommand,
) -> None:
    """Create a clearing account."""
    try:
        result = api.check_accounts.create_clearing_account(
            name=cmd.name,
            accounting_number=cmd.accounting_number,
        )
    except Exception as e:
        msg = f"Failed to create clearing account: {e}"
        raise SevDeskCLIError(msg) from e

    # Parse response
    try:
        account = result.get("objects", {})
        account_id = account.get("id")
        if not account_id:
            msg = "No account ID returned in response"
            raise SevDeskCLIError(msg)
    except (KeyError, TypeError) as e:
        msg = f"Invalid response format: {e}"
        raise SevDeskCLIError(msg) from e

    print(f"Successfully created clearing account #{account_id}")
    print(f"Name: {cmd.name}")


def get_check_account_balance(
    api: SevDeskAPI,
    cmd: CheckAccountsBalanceCommand,
) -> None:
    """Get check account balance."""
    # First get the account to show current balance
    try:
        result = api.check_accounts.get_check_account(cmd.check_account_id)
    except Exception as e:
        msg = f"Failed to fetch check account {cmd.check_account_id}: {e}"
        raise SevDeskCLIError(msg) from e

    # Parse account data
    try:
        account = result.get("objects", [{}])[0]
    except (IndexError, TypeError) as e:
        msg = f"Invalid response format for check account {cmd.check_account_id}"
        raise SevDeskCLIError(msg) from e

    if not account:
        print(f"Check account {cmd.check_account_id} not found.")
        return

    # Display balance information
    name = account.get("name", "N/A")
    currency = account.get("currency", "EUR")
    current_balance = account.get("currentBalance", 0)

    print(f"Check Account: {name} (#{cmd.check_account_id})")
    print(f"Current Balance: {current_balance:,.2f} {currency}")

    # We could also fetch recent transactions to show more context
    print("\nNote: To see transaction history, use:")
    print(f"  sevdesk transactions list --check-account-id {cmd.check_account_id}")


def parse_check_account_command(
    args: argparse.Namespace,
) -> (
    CheckAccountsListCommand
    | CheckAccountsGetCommand
    | CheckAccountsCreateClearingCommand
    | CheckAccountsBalanceCommand
    | None
):
    """Parse check account command from argparse namespace."""
    if not hasattr(args, "action"):
        return None

    match args.action:
        case "list":
            return CheckAccountsListCommand(
                limit=getattr(args, "limit", None),
                offset=getattr(args, "offset", None),
            )
        case "get":
            return CheckAccountsGetCommand(
                check_account_id=args.check_account_id,
            )
        case "create-clearing":
            return CheckAccountsCreateClearingCommand(
                name=args.name,
                accounting_number=getattr(args, "accounting_number", None),
            )
        case "balance":
            return CheckAccountsBalanceCommand(
                check_account_id=args.check_account_id,
            )
        case _:
            return None
