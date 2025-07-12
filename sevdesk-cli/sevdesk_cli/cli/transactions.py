"""Transaction management commands for SevDesk."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sevdesk_api import TransactionStatus

from sevdesk_cli.errors import SevDeskCLIError

if TYPE_CHECKING:
    from sevdesk_api import SevDeskAPI


def parse_date(date_string: str) -> datetime:
    """Parse a date string in YYYY-MM-DD format to a timezone-aware datetime."""
    try:
        return datetime.strptime(date_string, "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError as e:
        msg = f"Invalid date format '{date_string}'. Expected YYYY-MM-DD"
        raise argparse.ArgumentTypeError(msg) from e


def parse_transaction_status(value: str) -> TransactionStatus:
    """Parse transaction status from string or int."""
    # Handle string names
    status_map = {
        "CREATED": TransactionStatus.CREATED,
        "LINKED": TransactionStatus.LINKED,
        "PRIVATE": TransactionStatus.PRIVATE,
        "AUTO_BOOKED": TransactionStatus.AUTO_BOOKED,
        "BOOKED": TransactionStatus.BOOKED,
    }

    # Try to parse as name first
    upper_value = value.upper()
    if upper_value in status_map:
        return status_map[upper_value]

    # Try to parse as int
    try:
        status_int = int(value)
        return TransactionStatus(status_int)
    except ValueError as e:
        valid = ", ".join([f"{name}={s.value}" for name, s in status_map.items()])
        msg = f"Invalid status '{value}'. Valid options: {valid}"
        raise argparse.ArgumentTypeError(msg) from e


@dataclass
class TransactionsListCommand:
    """Transactions list command."""

    check_account_id: int | None = None
    status: TransactionStatus | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    limit: int | None = None
    offset: int | None = None


@dataclass
class TransactionsGetCommand:
    """Transactions get command."""

    transaction_id: int


@dataclass
class TransactionsCreateCommand:
    """Transactions create command."""

    check_account_id: int
    value_date: datetime
    amount: float
    status: TransactionStatus
    payee_payer_name: str
    entry_date: datetime | None = None
    paymt_purpose: str | None = None
    payee_payer_acct_no: str | None = None
    payee_payer_bank_code: str | None = None


@dataclass
class TransactionsUpdateCommand:
    """Transactions update command."""

    transaction_id: int
    value_date: datetime | None = None
    entry_date: datetime | None = None
    amount: float | None = None
    payee_payer_name: str | None = None
    paymt_purpose: str | None = None
    payee_payer_acct_no: str | None = None
    payee_payer_bank_code: str | None = None


@dataclass
class TransactionsDeleteCommand:
    """Transactions delete command."""

    transaction_id: int


@dataclass
class TransactionsEnshrineCommand:
    """Transactions enshrine command."""

    transaction_id: int


def add_transaction_subparser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Add transaction subcommands to the parser."""
    transaction_parser = subparsers.add_parser(
        "transactions",
        help="Manage check account transactions",
    )
    transaction_subparsers = transaction_parser.add_subparsers(
        dest="action",
        help="Transaction actions",
    )

    # List transactions
    list_parser = transaction_subparsers.add_parser("list", help="List transactions")
    list_parser.add_argument(
        "--check-account-id",
        type=int,
        help="Filter by check account ID",
    )
    list_parser.add_argument(
        "--status",
        type=parse_transaction_status,
        help="Filter by status (CREATED, LINKED, PRIVATE, AUTO_BOOKED, BOOKED)",
    )
    list_parser.add_argument(
        "--start-date",
        type=parse_date,
        help="Filter transactions from this date (YYYY-MM-DD)",
    )
    list_parser.add_argument(
        "--end-date",
        type=parse_date,
        help="Filter transactions until this date (YYYY-MM-DD)",
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

    # Get transaction
    get_parser = transaction_subparsers.add_parser(
        "get",
        help="Get transaction details",
    )
    get_parser.add_argument("transaction_id", type=int, help="Transaction ID")

    # Create transaction
    create_parser = transaction_subparsers.add_parser(
        "create",
        help="Create a new transaction",
    )
    create_parser.add_argument(
        "--check-account-id",
        type=int,
        required=True,
        help="Check account ID",
    )
    create_parser.add_argument(
        "--value-date",
        type=parse_date,
        required=True,
        help="Transaction date (YYYY-MM-DD)",
    )
    create_parser.add_argument(
        "--amount",
        type=float,
        required=True,
        help="Transaction amount (negative for expenses)",
    )
    create_parser.add_argument(
        "--status",
        type=parse_transaction_status,
        required=True,
        help="Status (CREATED, LINKED, PRIVATE, AUTO_BOOKED, BOOKED)",
    )
    create_parser.add_argument(
        "--payee",
        "--payee-payer-name",
        dest="payee_payer_name",
        required=True,
        help="Name of payee/payer",
    )
    create_parser.add_argument(
        "--entry-date",
        type=parse_date,
        help="Entry/import date (YYYY-MM-DD)",
    )
    create_parser.add_argument(
        "--purpose",
        "--paymt-purpose",
        dest="paymt_purpose",
        help="Payment purpose/description",
    )
    create_parser.add_argument(
        "--iban",
        "--payee-payer-acct-no",
        dest="payee_payer_acct_no",
        help="IBAN or account number",
    )
    create_parser.add_argument(
        "--bic",
        "--payee-payer-bank-code",
        dest="payee_payer_bank_code",
        help="BIC or bank code",
    )

    # Update transaction
    update_parser = transaction_subparsers.add_parser(
        "update",
        help="Update an existing transaction",
    )
    update_parser.add_argument("transaction_id", type=int, help="Transaction ID")
    update_parser.add_argument(
        "--value-date",
        type=parse_date,
        help="Transaction date (YYYY-MM-DD)",
    )
    update_parser.add_argument(
        "--entry-date",
        type=parse_date,
        help="Entry/import date (YYYY-MM-DD)",
    )
    update_parser.add_argument(
        "--amount",
        type=float,
        help="Transaction amount",
    )
    update_parser.add_argument(
        "--payee",
        "--payee-payer-name",
        dest="payee_payer_name",
        help="Name of payee/payer",
    )
    update_parser.add_argument(
        "--purpose",
        "--paymt-purpose",
        dest="paymt_purpose",
        help="Payment purpose/description",
    )
    update_parser.add_argument(
        "--iban",
        "--payee-payer-acct-no",
        dest="payee_payer_acct_no",
        help="IBAN or account number",
    )
    update_parser.add_argument(
        "--bic",
        "--payee-payer-bank-code",
        dest="payee_payer_bank_code",
        help="BIC or bank code",
    )

    # Delete transaction
    delete_parser = transaction_subparsers.add_parser(
        "delete",
        help="Delete a transaction",
    )
    delete_parser.add_argument("transaction_id", type=int, help="Transaction ID")

    # Enshrine transaction
    enshrine_parser = transaction_subparsers.add_parser(
        "enshrine",
        help="Enshrine (lock) a transaction",
    )
    enshrine_parser.add_argument("transaction_id", type=int, help="Transaction ID")


def list_transactions(api: SevDeskAPI, cmd: TransactionsListCommand) -> None:
    """List transactions."""
    try:
        result = api.transactions.get_transactions(
            check_account_id=cmd.check_account_id,
            status=cmd.status.value if cmd.status else None,
            start_date=cmd.start_date,
            end_date=cmd.end_date,
            limit=cmd.limit,
            offset=cmd.offset,
        )
    except Exception as e:
        msg = f"Failed to fetch transactions: {e}"
        raise SevDeskCLIError(msg) from e

    transactions = result.get("objects", [])
    if not transactions:
        print("No transactions found.")
        return

    # Display transactions
    print(f"Found {len(transactions)} transaction(s):")
    print("-" * 100)

    for transaction in transactions:
        _display_transaction_summary(transaction)
        print("-" * 100)


def _display_transaction_summary(transaction: dict[str, Any]) -> None:
    """Display a transaction summary."""
    transaction_id = transaction.get("id", "N/A")
    value_date = transaction.get("valueDate", "N/A")
    amount = transaction.get("amount", 0)
    payee_payer = transaction.get("payeePayerName", "N/A")
    purpose = transaction.get("paymtPurpose", "")
    status = transaction.get("status", "N/A")

    # Format status
    try:
        status_enum = TransactionStatus(int(status))
        status_text = f"{status_enum.name} ({status})"
    except (ValueError, TypeError):
        status_text = f"Unknown ({status})"

    # Format amount with color hint
    # Convert amount to float for comparison and formatting
    try:
        amount_float = float(amount)
        amount_str = f"{amount_float:,.2f}"
        if amount_float < 0:
            amount_display = f"{amount_str} (Expense)"
        else:
            amount_display = f"{amount_str} (Income)"
    except (ValueError, TypeError):
        amount_display = str(amount)

    print(f"ID: {transaction_id}")
    print(f"Date: {value_date}")
    print(f"Amount: {amount_display}")
    print(f"Payee/Payer: {payee_payer}")
    if purpose:
        print(f"Purpose: {purpose}")
    print(f"Status: {status_text}")

    # Check if enshrined
    enshrined = transaction.get("enshrined")
    if enshrined:
        print(f"Enshrined: Yes (on {enshrined})")

    # Show linked voucher if any
    source_transaction = transaction.get("sourceTransaction")
    if source_transaction and isinstance(source_transaction, dict):
        linked_id = source_transaction.get("id", "N/A")
        linked_object = source_transaction.get("objectName", "Unknown")
        print(f"Linked to: {linked_object} #{linked_id}")


def _format_transaction_status(status: str | int | None) -> str:
    """Format transaction status for display."""
    if status is None:
        return "Unknown (None)"
    try:
        status_enum = TransactionStatus(int(status))
    except (ValueError, TypeError):
        return f"Unknown ({status})"
    else:
        return f"{status_enum.name} ({status})"


def _format_amount(amount: float | str) -> str:
    """Format transaction amount with income/expense indicator."""
    try:
        amount_float = float(amount)
        formatted = f"{amount_float:,.2f}"
        return formatted + (" (Expense)" if amount_float < 0 else " (Income)")
    except (ValueError, TypeError):
        return str(amount)


def _format_basic_info(transaction: dict[str, Any], transaction_id: int) -> list[str]:
    """Format basic transaction information."""
    return [
        f"Transaction #{transaction_id}",
        "=" * 80,
        f"Value Date: {transaction.get('valueDate', 'N/A')}",
        f"Entry Date: {transaction.get('entryDate', 'N/A')}",
        f"Amount: {_format_amount(transaction.get('amount', 0))}",
        f"Status: {_format_transaction_status(transaction.get('status', 'N/A'))}",
    ]


def _format_payee_info(transaction: dict[str, Any]) -> list[str]:
    """Format payee/payer information."""
    lines = [f"\nPayee/Payer: {transaction.get('payeePayerName', 'N/A')}"]

    acct_no = transaction.get("payeePayerAcctNo")
    if acct_no:
        lines.append(f"IBAN/Account: {acct_no}")

    bank_code = transaction.get("payeePayerBankCode")
    if bank_code:
        lines.append(f"BIC/Bank Code: {bank_code}")

    return lines


def _format_purpose_info(transaction: dict[str, Any]) -> list[str]:
    """Format purpose and additional information."""
    lines = []

    purpose = transaction.get("paymtPurpose")
    if purpose:
        lines.append(f"\nPurpose: {purpose}")

    entry_text = transaction.get("entryText")
    if entry_text:
        lines.append(f"Entry Text: {entry_text}")

    gv_code = transaction.get("gvCode")
    if gv_code:
        lines.append(f"GV Code: {gv_code}")

    return lines


def _format_check_account(transaction: dict[str, Any]) -> list[str]:
    """Format check account information."""
    lines = []
    check_account = transaction.get("checkAccount")

    if check_account and isinstance(check_account, dict):
        # The API returns only id and objectName, not the full account details
        account_id = check_account.get("id", "N/A")
        lines.extend(
            [
                "\nCheck Account:",
                f"  ID: {account_id}",
            ],
        )
        # Note: To get the account name, we would need to make a separate API call
        # to fetch the check account details using the ID
    return lines


def _format_check_account_with_details(
    api: SevDeskAPI,
    transaction: dict[str, Any],
) -> list[str]:
    """Format check account information with details fetched from API."""
    lines = []
    check_account = transaction.get("checkAccount")

    if check_account and isinstance(check_account, dict):
        account_id = check_account.get("id")
        if account_id:
            # Try to fetch the check account details
            try:
                result = api.check_accounts.get_check_account(int(account_id))
                account_details = result.get("objects", [{}])[0]
                if account_details:
                    lines.extend(
                        [
                            "\nCheck Account:",
                            f"  ID: {account_id}",
                            f"  Name: {account_details.get('name', 'N/A')}",
                            f"  Type: {account_details.get('type', 'N/A')}",
                        ],
                    )
                else:
                    # Fallback if we can't get details
                    lines.extend(
                        [
                            "\nCheck Account:",
                            f"  ID: {account_id}",
                        ],
                    )
            except (KeyError, ValueError, SevDeskCLIError):
                # If fetching fails, just show the ID
                lines.extend(
                    [
                        "\nCheck Account:",
                        f"  ID: {account_id}",
                    ],
                )
        else:
            # No ID available
            lines.append("\nCheck Account: N/A")
    return lines


def _format_enshrined_status(transaction: dict[str, Any]) -> list[str]:
    """Format enshrined status."""
    enshrined = transaction.get("enshrined")
    if enshrined:
        return [f"\nEnshrined: Yes (on {enshrined})"]
    return ["\nEnshrined: No"]


def _format_linked_documents(transaction: dict[str, Any]) -> list[str]:
    """Format linked documents information."""
    lines = []
    source_transaction = transaction.get("sourceTransaction")
    target_transaction = transaction.get("targetTransaction")

    if source_transaction or target_transaction:
        lines.append("\nLinked Documents:")
        if source_transaction and isinstance(source_transaction, dict):
            lines.append(
                f"  Source: {source_transaction.get('objectName', 'Unknown')} "
                f"#{source_transaction.get('id', 'N/A')}",
            )
        if target_transaction and isinstance(target_transaction, dict):
            lines.append(
                f"  Target: {target_transaction.get('objectName', 'Unknown')} "
                f"#{target_transaction.get('id', 'N/A')}",
            )

    return lines


def get_transaction(api: SevDeskAPI, cmd: TransactionsGetCommand) -> None:
    """Get transaction details."""
    try:
        result = api.transactions.get_transaction(cmd.transaction_id)
    except Exception as e:
        msg = f"Failed to fetch transaction {cmd.transaction_id}: {e}"
        raise SevDeskCLIError(msg) from e

    # Parse transaction data
    try:
        transaction = result.get("objects", [{}])[0]
    except (IndexError, TypeError) as e:
        msg = f"Invalid response format for transaction {cmd.transaction_id}"
        raise SevDeskCLIError(msg) from e

    if not transaction:
        print(f"Transaction {cmd.transaction_id} not found.")
        return

    # Format and display detailed transaction information
    output_lines = []
    output_lines.extend(_format_basic_info(transaction, cmd.transaction_id))
    output_lines.extend(_format_payee_info(transaction))
    output_lines.extend(_format_purpose_info(transaction))
    output_lines.extend(_format_check_account_with_details(api, transaction))
    output_lines.extend(_format_enshrined_status(transaction))
    output_lines.extend(_format_linked_documents(transaction))

    for line in output_lines:
        print(line)


def create_transaction(api: SevDeskAPI, cmd: TransactionsCreateCommand) -> None:
    """Create a new transaction."""
    try:
        result = api.transactions.create_transaction(
            check_account_id=cmd.check_account_id,
            value_date=cmd.value_date,
            amount=cmd.amount,
            status=cmd.status.value,
            payee_payer_name=cmd.payee_payer_name,
            entry_date=cmd.entry_date,
            paymt_purpose=cmd.paymt_purpose,
            payee_payer_acct_no=cmd.payee_payer_acct_no,
            payee_payer_bank_code=cmd.payee_payer_bank_code,
        )
    except Exception as e:
        msg = f"Failed to create transaction: {e}"
        raise SevDeskCLIError(msg) from e

    # Parse response
    try:
        transaction = result.get("objects", {})
        transaction_id = transaction.get("id")
        if not transaction_id:
            msg = "No transaction ID returned in response"
            raise SevDeskCLIError(msg)
    except (KeyError, TypeError) as e:
        msg = f"Invalid response format: {e}"
        raise SevDeskCLIError(msg) from e

    print(f"Successfully created transaction #{transaction_id}")


def update_transaction(api: SevDeskAPI, cmd: TransactionsUpdateCommand) -> None:
    """Update an existing transaction."""
    try:
        api.transactions.update_transaction(
            transaction_id=cmd.transaction_id,
            value_date=cmd.value_date,
            entry_date=cmd.entry_date,
            amount=cmd.amount,
            payee_payer_name=cmd.payee_payer_name,
            paymt_purpose=cmd.paymt_purpose,
            payee_payer_acct_no=cmd.payee_payer_acct_no,
            payee_payer_bank_code=cmd.payee_payer_bank_code,
        )
    except Exception as e:
        msg = f"Failed to update transaction {cmd.transaction_id}: {e}"
        raise SevDeskCLIError(msg) from e

    print(f"Successfully updated transaction #{cmd.transaction_id}")


def delete_transaction(api: SevDeskAPI, cmd: TransactionsDeleteCommand) -> None:
    """Delete a transaction."""
    try:
        api.transactions.delete_transaction(cmd.transaction_id)
    except Exception as e:
        msg = f"Failed to delete transaction {cmd.transaction_id}: {e}"
        raise SevDeskCLIError(msg) from e

    print(f"Successfully deleted transaction #{cmd.transaction_id}")


def enshrine_transaction(api: SevDeskAPI, cmd: TransactionsEnshrineCommand) -> None:
    """Enshrine (lock) a transaction."""
    # The API doesn't have a direct enshrine method in TransactionOperations
    # We need to use the CheckAccountTransaction endpoint directly
    endpoint = f"CheckAccountTransaction/{cmd.transaction_id}/enshrine"

    try:
        api.transactions.client.put(endpoint)
    except Exception as e:
        msg = f"Failed to enshrine transaction {cmd.transaction_id}: {e}"
        raise SevDeskCLIError(msg) from e

    print(f"Successfully enshrined transaction #{cmd.transaction_id}")


def parse_transaction_command(  # noqa: PLR0911
    args: argparse.Namespace,
) -> (
    TransactionsListCommand
    | TransactionsGetCommand
    | TransactionsCreateCommand
    | TransactionsUpdateCommand
    | TransactionsDeleteCommand
    | TransactionsEnshrineCommand
    | None
):
    """Parse transaction command from argparse namespace."""
    if not hasattr(args, "action"):
        return None

    match args.action:
        case "list":
            return TransactionsListCommand(
                check_account_id=getattr(args, "check_account_id", None),
                status=getattr(args, "status", None),
                start_date=getattr(args, "start_date", None),
                end_date=getattr(args, "end_date", None),
                limit=getattr(args, "limit", None),
                offset=getattr(args, "offset", None),
            )
        case "get":
            return TransactionsGetCommand(
                transaction_id=args.transaction_id,
            )
        case "create":
            return TransactionsCreateCommand(
                check_account_id=args.check_account_id,
                value_date=args.value_date,
                amount=args.amount,
                status=args.status,
                payee_payer_name=args.payee_payer_name,
                entry_date=getattr(args, "entry_date", None),
                paymt_purpose=getattr(args, "paymt_purpose", None),
                payee_payer_acct_no=getattr(args, "payee_payer_acct_no", None),
                payee_payer_bank_code=getattr(args, "payee_payer_bank_code", None),
            )
        case "update":
            return TransactionsUpdateCommand(
                transaction_id=args.transaction_id,
                value_date=getattr(args, "value_date", None),
                entry_date=getattr(args, "entry_date", None),
                amount=getattr(args, "amount", None),
                payee_payer_name=getattr(args, "payee_payer_name", None),
                paymt_purpose=getattr(args, "paymt_purpose", None),
                payee_payer_acct_no=getattr(args, "payee_payer_acct_no", None),
                payee_payer_bank_code=getattr(args, "payee_payer_bank_code", None),
            )
        case "delete":
            return TransactionsDeleteCommand(
                transaction_id=args.transaction_id,
            )
        case "enshrine":
            return TransactionsEnshrineCommand(
                transaction_id=args.transaction_id,
            )
        case _:
            return None
