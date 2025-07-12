"""Voucher management commands for SevDesk."""

from __future__ import annotations

import argparse
import json
import shlex
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from sevdesk_api import (
    CreditDebit,
    SevDeskError,
    TaxType,
    VoucherPosition,
    VoucherStatus,
    VoucherType,
)

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


def parse_voucher_status(value: str) -> VoucherStatus:
    """Parse voucher status from string or int."""
    try:
        # Try to parse as int first
        status_int = int(value)
        return VoucherStatus(status_int)
    except ValueError:
        # Try to parse as name
        try:
            return VoucherStatus[value.upper()]
        except KeyError as e:
            valid = ", ".join([f"{s.name}={s.value}" for s in VoucherStatus])
            msg = f"Invalid status '{value}'. Valid options: {valid}"
            raise argparse.ArgumentTypeError(msg) from e


def parse_position_args(arg_string: str) -> VoucherPositionInput:
    """Parse position arguments in key=value format.

    Examples:
        name='Office supplies' price=50 skr=6815
        name='Laptop' qty=1 price=1200 tax=19 skr=0670 asset=true

    """
    # Default values with proper types
    defaults: dict[str, Any] = {
        "quantity": 1.0,
        "tax_rate": 19.0,
        "is_asset": False,
        "net": True,
        "text": None,
        "accounting_type_skr": None,
        "name": None,
        "price": None,
    }

    # Parse arguments using shlex to handle quoted values
    args = shlex.split(arg_string)
    parsed: dict[str, Any] = defaults.copy()

    # Key mappings (short to full names)
    key_map = {
        "name": "name",
        "qty": "quantity",
        "quantity": "quantity",
        "price": "price",
        "tax": "tax_rate",
        "tax_rate": "tax_rate",
        "skr": "accounting_type_skr",
        "asset": "is_asset",
        "is_asset": "is_asset",
        "text": "text",
        "net": "net",
    }

    for arg in args:
        if "=" not in arg:
            msg = f"Invalid position argument '{arg}'. Expected format: key=value"
            raise argparse.ArgumentTypeError(msg)

        key, value = arg.split("=", 1)
        key = key.lower()

        if key not in key_map:
            valid_keys = sorted(set(key_map.keys()))
            msg = (
                f"Unknown parameter '{key}'. Valid parameters: {', '.join(valid_keys)}"
            )
            raise argparse.ArgumentTypeError(msg)

        mapped_key = key_map[key]

        # Convert values based on expected type
        try:
            if mapped_key in ("quantity", "price", "tax_rate"):
                parsed[mapped_key] = float(value)
            elif mapped_key in ("is_asset", "net"):
                parsed[mapped_key] = value.lower() in ("true", "1", "yes", "on")
            else:
                parsed[mapped_key] = value
        except ValueError as e:
            msg = f"Invalid value '{value}' for parameter '{key}': {e}"
            raise argparse.ArgumentTypeError(msg) from e

    # Check required fields
    if parsed.get("name") is None:
        msg = "Missing required parameter 'name'"
        raise argparse.ArgumentTypeError(msg)
    if parsed.get("price") is None:
        msg = "Missing required parameter 'price'"
        raise argparse.ArgumentTypeError(msg)
    if parsed.get("accounting_type_skr") is None:
        msg = "Missing required parameter 'skr' (SKR account number)"
        raise argparse.ArgumentTypeError(msg)

    return VoucherPositionInput(
        name=parsed["name"],
        quantity=parsed["quantity"],
        price=parsed["price"],
        tax_rate=parsed["tax_rate"],
        net=parsed["net"],
        text=parsed["text"],
        accounting_type_skr=parsed["accounting_type_skr"],
        is_asset=parsed["is_asset"],
    )


@dataclass
class VouchersListCommand:
    """Vouchers list command."""

    status: VoucherStatus | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    limit: int | None = None
    offset: int | None = None


@dataclass
class VouchersGetCommand:
    """Vouchers get command."""

    voucher_id: int


@dataclass
class VoucherPositionInput:
    """Input for a voucher position."""

    name: str
    quantity: float
    price: float
    tax_rate: float
    net: bool = True
    text: str | None = None
    accounting_type_skr: str | None = None
    is_asset: bool = False


@dataclass
class VouchersSaveCommand:
    """Vouchers save command - unified create/update command."""

    voucher_id: int | None = None  # None for new vouchers
    credit_debit: CreditDebit | None = None
    tax_type: TaxType | None = None
    voucher_type: VoucherType | None = None
    status: VoucherStatus | None = None
    voucher_date: datetime | None = None
    supplier_id: int | None = None
    supplier_name: str | None = None
    description: str | None = None
    pay_date: datetime | None = None
    currency: str = "EUR"
    positions: list[VoucherPositionInput] | None = None
    tax_rule: str | None = None


@dataclass
class VouchersBookCommand:
    """Vouchers book command."""

    voucher_id: int
    transaction_id: int
    amount: float | None = None


@dataclass
class VouchersUnbookCommand:
    """Vouchers unbook command."""

    voucher_id: int


@dataclass
class VouchersResetCommand:
    """Vouchers reset command."""

    voucher_id: int
    to_status: str  # "draft" or "open"


def add_voucher_subparser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Add voucher subcommands to the parser."""
    voucher_parser = subparsers.add_parser("vouchers", help="Manage vouchers")
    voucher_subparsers = voucher_parser.add_subparsers(
        dest="action",
        help="Voucher actions",
    )

    # List vouchers
    list_parser = voucher_subparsers.add_parser("list", help="List vouchers")
    list_parser.add_argument(
        "--status",
        type=parse_voucher_status,
        help="Filter by status (DRAFT=50, UNPAID=100, PAID=1000)",
    )
    list_parser.add_argument(
        "--start-date",
        type=parse_date,
        help="Filter vouchers from this date (YYYY-MM-DD)",
    )
    list_parser.add_argument(
        "--end-date",
        type=parse_date,
        help="Filter vouchers until this date (YYYY-MM-DD)",
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

    # Get voucher
    get_parser = voucher_subparsers.add_parser(
        "get",
        help="Get voucher details",
    )
    get_parser.add_argument("voucher_id", type=int, help="Voucher ID")

    # Save voucher (unified create/update command)
    save_parser = voucher_subparsers.add_parser(
        "save",
        help="Create or update a voucher",
    )
    save_parser.add_argument(
        "voucher_id",
        type=int,
        nargs="?",
        help="Voucher ID (omit for new voucher)",
    )
    save_parser.add_argument(
        "--credit-debit",
        type=lambda x: CreditDebit(x.upper()),
        choices=list(CreditDebit),
        help="Credit or debit (required for new vouchers)",
    )
    save_parser.add_argument(
        "--tax-type",
        type=lambda x: TaxType(x.lower()),
        choices=list(TaxType),
        default=TaxType.EU,
        help="Tax type (default: eu)",
    )
    save_parser.add_argument(
        "--voucher-type",
        type=lambda x: VoucherType(x.upper()),
        choices=list(VoucherType),
        help="Voucher type (required for new vouchers)",
    )
    save_parser.add_argument(
        "--status",
        type=parse_voucher_status,
        help="Status (DRAFT=50, UNPAID=100, PAID=1000)",
    )
    save_parser.add_argument(
        "--voucher-date",
        type=parse_date,
        help="Voucher date (YYYY-MM-DD)",
    )
    save_parser.add_argument(
        "--supplier-id",
        type=int,
        help="ID of supplier contact",
    )
    save_parser.add_argument(
        "--supplier-name",
        help="Name of supplier",
    )
    save_parser.add_argument(
        "--description",
        help="Description/number of voucher",
    )
    save_parser.add_argument(
        "--pay-date",
        type=parse_date,
        help="Payment deadline (YYYY-MM-DD)",
    )
    save_parser.add_argument(
        "--currency",
        default="EUR",
        help="Currency code (default: EUR)",
    )
    save_parser.add_argument(
        "--tax-rule",
        type=str,
        help="Tax rule code (e.g., VORST_ABZUGSF_AUFW for deductible expenses)",
    )
    save_parser.add_argument(
        "--positions-json",
        type=str,
        help="JSON file with positions data",
    )
    save_parser.add_argument(
        "--position",
        action="append",
        type=parse_position_args,
        help=(
            "Add a position using key=value format. Required: name, price, skr. "
            "Optional: qty (default: 1), tax (default: 19), asset (default: false), "
            "text, net. Example: --position \"name='Office supplies' price=50 "
            "skr=6815\" --position \"name='Laptop' qty=1 price=1200 tax=19 "
            'skr=0670 asset=true"'
        ),
    )

    # Book voucher
    book_parser = voucher_subparsers.add_parser(
        "book",
        help="Book a voucher with a payment transaction",
    )
    book_parser.add_argument("voucher_id", type=int, help="Voucher ID")
    book_parser.add_argument(
        "transaction_id",
        type=int,
        help="Check account transaction ID",
    )
    book_parser.add_argument(
        "--amount",
        type=float,
        help="Amount to book (defaults to full voucher amount)",
    )

    # Unbook voucher
    unbook_parser = voucher_subparsers.add_parser(
        "unbook",
        help="Unbook a voucher (reset to unpaid status)",
    )
    unbook_parser.add_argument("voucher_id", type=int, help="Voucher ID")

    # Reset voucher status
    reset_parser = voucher_subparsers.add_parser(
        "reset",
        help="Reset voucher status to draft or open",
    )
    reset_parser.add_argument("voucher_id", type=int, help="Voucher ID")
    reset_parser.add_argument(
        "to_status",
        choices=["draft", "open"],
        help="Target status (draft=50, open=100)",
    )


def list_vouchers(api: SevDeskAPI, cmd: VouchersListCommand) -> None:
    """List vouchers."""
    # Get vouchers
    try:
        result = api.vouchers.get_vouchers(
            status=cmd.status,
            start_date=cmd.start_date,
            end_date=cmd.end_date,
            limit=cmd.limit,
            offset=cmd.offset,
        )
    except Exception as e:
        msg = f"Failed to fetch vouchers: {e}"
        raise SevDeskCLIError(msg) from e

    vouchers = result.get("objects", [])
    if not vouchers:
        print("No vouchers found.")
        return

    # Display vouchers
    print(f"Found {len(vouchers)} voucher(s):")
    print("-" * 80)

    for voucher in vouchers:
        voucher_id = voucher.get("id", "N/A")
        description = voucher.get("description", "No description")
        status = voucher.get("status", "N/A")
        sum_gross = voucher.get("sumGross", 0)
        currency = voucher.get("currency", "EUR")
        voucher_date = voucher.get("voucherDate", "N/A")
        credit_debit = voucher.get("creditDebit", "N/A")

        # Format status
        try:
            status_int = int(status) if status != "N/A" else status
        except (ValueError, TypeError):
            status_int = status
        status_text = {
            50: "Draft",
            100: "Unpaid",
            750: "Partially Paid",
            1000: "Paid",
        }.get(
            status_int,
            f"Unknown ({status})",
        )

        # Format type
        type_text = "Credit" if credit_debit == "C" else "Debit"

        # Get tax rule info
        tax_rule_text = ""
        tax_rule = voucher.get("taxRule")
        if tax_rule and isinstance(tax_rule, dict):
            rule_id = tax_rule.get("id")
            if rule_id:
                try:
                    tax_rule_obj = api.tax_rules.get_by_id(int(rule_id))
                    tax_rule_text = f" | Tax: {tax_rule_obj.code}"
                except (ValueError, KeyError, AttributeError, SevDeskError):
                    tax_rule_text = f" | Tax: ID {rule_id}"

        print(f"ID: {voucher_id}")
        print(f"Description: {description}")
        print(f"Type: {type_text}{tax_rule_text}")
        print(f"Status: {status_text}")
        print(f"Amount: {sum_gross} {currency}")
        print(f"Date: {voucher_date}")
        print("-" * 80)


def _format_voucher_status(voucher: dict[str, Any]) -> str:
    """Format voucher status information."""
    status = voucher.get("status", "N/A")
    # Convert to int if it's a string
    try:
        status_int = int(status) if status != "N/A" else status
    except (ValueError, TypeError):
        status_int = status
    status_text = {50: "Draft", 100: "Unpaid", 750: "Partially Paid", 1000: "Paid"}.get(
        status_int,
        f"Unknown ({status})",
    )
    return f"Status: {status_text}"


def _format_voucher_position(pos: dict[str, Any], position_number: int) -> list[str]:
    """Format a single voucher position."""
    lines = []
    # The API returns different field names than we send
    comment = pos.get("comment", "")
    name = comment if comment else "Position"  # Use comment as name if available
    tax_rate = pos.get("taxRate", 0)
    sum_net = pos.get("sumNet", 0)
    sum_tax = pos.get("sumTax", 0)
    sum_gross = pos.get("sumGross", 0)

    # Get account/category information
    account_datev = pos.get("accountDatev", {})
    account_id = account_datev.get("id", "N/A") if account_datev else "N/A"

    lines.append(f"Position {position_number}: {name}")
    if comment and comment != name:
        lines.append(f"  Comment: {comment}")
    lines.append(f"  Account/Category ID: {account_id}")
    lines.append(f"  Tax Rate: {tax_rate}%")
    lines.append(f"  Net: {sum_net}, Tax: {sum_tax}, Gross: {sum_gross}")
    lines.append("-" * 60)
    return lines


def _format_voucher_positions(api: SevDeskAPI, voucher_id: int) -> list[str]:
    """Format voucher positions."""
    try:
        positions_result = api.vouchers.get_voucher_positions(voucher_id)
        positions = positions_result.get("objects", [])
    except (AttributeError, KeyError, SevDeskCLIError) as e:
        return [f"\nWarning: Could not fetch positions: {e}"]

    if not positions:
        return []

    lines = ["\nPositions:", "-" * 60]
    for i, pos in enumerate(positions, 1):
        lines.extend(_format_voucher_position(pos, i))
    return lines


def _format_voucher_financial_info(voucher: dict[str, Any]) -> list[str]:
    """Format voucher financial information."""
    return [
        "\nFinancial Information:",
        f"  Net Amount: {voucher.get('sumNet', 0)}",
        f"  Tax Amount: {voucher.get('sumTax', 0)}",
        f"  Gross Amount: {voucher.get('sumGross', 0)}",
        f"  Currency: {voucher.get('currency', 'EUR')}",
    ]


def _format_voucher_basic_info(voucher: dict[str, Any]) -> list[str]:
    """Format basic voucher information."""
    return [
        f"Description: {voucher.get('description', 'N/A')}",
        f"Type: {'Credit' if voucher.get('creditDebit') == 'C' else 'Debit'}",
        f"Voucher Type: {voucher.get('voucherType', 'N/A')}",
        f"Tax Type: {voucher.get('taxType', 'N/A')}",
        _format_voucher_status(voucher),
        f"Voucher Date: {voucher.get('voucherDate', 'N/A')}",
        f"Pay Date: {voucher.get('payDate', 'N/A')}",
    ]


def _format_voucher_supplier(voucher: dict[str, Any]) -> list[str]:
    """Format voucher supplier information."""
    supplier = voucher.get("supplier")
    if supplier:
        return [
            "\nSupplier:",
            f"  ID: {supplier.get('id', 'N/A')}",
            f"  Name: {voucher.get('supplierName', 'N/A')}",
        ]
    return []


def _format_voucher_tax_rule(api: SevDeskAPI, voucher: dict[str, Any]) -> list[str]:
    """Format voucher tax rule information."""
    tax_rule = voucher.get("taxRule")
    if not tax_rule or not isinstance(tax_rule, dict):
        return []

    rule_id = tax_rule.get("id")
    if not rule_id:
        return []

    try:
        # Look up the tax rule details
        tax_rule_obj = api.tax_rules.get_by_id(int(rule_id))
        lines = [
            "\nTax Rule:",
            f"  Code: {tax_rule_obj.code}",
            f"  Name: {tax_rule_obj.name}",
        ]
    except (ValueError, KeyError, AttributeError, SevDeskError):
        # Fallback if lookup fails
        lines = [f"\nTax Rule: ID {rule_id}"]
    return lines


def get_voucher(api: SevDeskAPI, cmd: VouchersGetCommand) -> None:
    """Get voucher details."""
    # Fetch voucher from API
    try:
        result = api.vouchers.get_voucher(cmd.voucher_id)
    except Exception as e:
        msg = f"Failed to fetch voucher {cmd.voucher_id}: {e}"
        raise SevDeskCLIError(msg) from e

    # Parse voucher data
    try:
        voucher = result.get("objects", [{}])[0]
    except (IndexError, TypeError) as e:
        msg = f"Invalid response format for voucher {cmd.voucher_id}"
        raise SevDeskCLIError(msg) from e

    if not voucher:
        print(f"Voucher {cmd.voucher_id} not found.")
        return

    # Display detailed voucher information
    print(f"Voucher #{cmd.voucher_id}")
    print("=" * 80)

    # Format and display all voucher sections
    output_lines = []
    output_lines.extend(_format_voucher_basic_info(voucher))
    output_lines.extend(_format_voucher_financial_info(voucher))
    output_lines.extend(_format_voucher_supplier(voucher))
    output_lines.extend(_format_voucher_tax_rule(api, voucher))
    output_lines.extend(_format_voucher_positions(api, cmd.voucher_id))

    # Print all lines
    for line in output_lines:
        print(line)


def _build_new_voucher_data(cmd: VouchersSaveCommand) -> dict[str, Any]:
    """Build voucher data for new voucher creation."""
    if not all([cmd.credit_debit, cmd.voucher_type]):
        msg = "credit_debit and voucher_type are required for new vouchers"
        raise SevDeskCLIError(msg)

    # These are guaranteed to be non-None by the check above
    # Using cast to satisfy mypy
    credit_debit = cast("CreditDebit", cmd.credit_debit)
    voucher_type = cast("VoucherType", cmd.voucher_type)
    # tax_type has a default value, so it should always be set
    tax_type = cmd.tax_type if cmd.tax_type else TaxType.EU

    return {
        "creditDebit": credit_debit.value,
        "taxType": tax_type.value,
        "voucherType": voucher_type.value,
        "status": int(cmd.status) if cmd.status else int(VoucherStatus.DRAFT),
        "currency": cmd.currency,
    }


def _add_optional_voucher_fields(
    voucher_data: dict[str, Any],
    cmd: VouchersSaveCommand,
    api: SevDeskAPI,
) -> None:
    """Add optional fields to voucher data."""
    if cmd.description is not None:
        voucher_data["description"] = cmd.description
    if cmd.voucher_date is not None:
        voucher_data["voucherDate"] = cmd.voucher_date.strftime("%d.%m.%Y")
    if cmd.pay_date is not None:
        voucher_data["payDate"] = cmd.pay_date.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    if cmd.supplier_id is not None:
        voucher_data["supplier"] = {
            "id": cmd.supplier_id,
            "objectName": "Contact",
        }
    if cmd.supplier_name is not None:
        voucher_data["supplierName"] = cmd.supplier_name
    if cmd.status is not None and cmd.voucher_id is not None:
        voucher_data["status"] = int(cmd.status)
    if cmd.tax_rule is not None:
        # Look up the tax rule by code
        try:
            tax_rule = api.tax_rules.get_by_code(cmd.tax_rule)
            voucher_data["taxRule"] = {
                "id": tax_rule.id,
                "objectName": "TaxRule",
            }
        except (ValueError, KeyError, AttributeError, SevDeskError) as e:
            msg = f"Failed to find tax rule '{cmd.tax_rule}': {e}"
            raise SevDeskCLIError(msg) from e


def _convert_position_inputs(position_inputs: list[Any]) -> list[VoucherPosition]:
    """Convert position input data to VoucherPosition objects."""
    positions = []
    for pos_input in position_inputs:
        position = VoucherPosition(
            name=pos_input.name,
            quantity=pos_input.quantity,
            price=pos_input.price,
            tax_rate=pos_input.tax_rate,
            net=pos_input.net,
            text=pos_input.text,
            accounting_type_skr=pos_input.accounting_type_skr,
            is_asset=pos_input.is_asset,
        )
        positions.append(position)
    return positions


def save_voucher(api: SevDeskAPI, cmd: VouchersSaveCommand) -> None:
    """Save/create/update a voucher using the unified saveVoucher endpoint."""
    # Build voucher data
    voucher_data: dict[str, Any] = {}

    # For new vouchers, add required fields
    if cmd.voucher_id is None:
        voucher_data = _build_new_voucher_data(cmd)

    # Add optional fields
    _add_optional_voucher_fields(voucher_data, cmd, api)

    # Convert positions
    positions = None
    if cmd.positions:
        positions = _convert_position_inputs(cmd.positions)

    # Make API call
    try:
        result = api.vouchers.save_voucher(
            voucher_id=cmd.voucher_id,
            voucher_data=voucher_data,
            voucher_positions=positions,
        )
    except (ValueError, KeyError, TypeError, SevDeskError) as e:
        action = (
            "create" if cmd.voucher_id is None else f"save voucher {cmd.voucher_id}"
        )
        msg = f"Failed to {action}: {e}"
        raise SevDeskCLIError(msg) from e

    # Parse response
    try:
        voucher = result.get("objects", {}).get("voucher", {})
        voucher_id = voucher.get("id", cmd.voucher_id)
    except (KeyError, TypeError) as e:
        msg = f"Invalid response format: {e}"
        raise SevDeskCLIError(msg) from e

    action = "created" if cmd.voucher_id is None else "saved"
    print(f"Successfully {action} voucher #{voucher_id}")


def book_voucher(api: SevDeskAPI, cmd: VouchersBookCommand) -> None:
    """Book a voucher with a payment transaction."""
    try:
        api.vouchers.book_voucher(
            voucher_id=cmd.voucher_id,
            check_account_transaction_id=cmd.transaction_id,
            amount=cmd.amount,
        )
    except Exception as e:
        msg = f"Failed to book voucher {cmd.voucher_id}: {e}"
        raise SevDeskCLIError(msg) from e

    print(
        f"Successfully booked voucher #{cmd.voucher_id} with transaction "
        f"#{cmd.transaction_id}",
    )


def unbook_voucher(api: SevDeskAPI, cmd: VouchersUnbookCommand) -> None:
    """Unbook a voucher (reset to unpaid status)."""
    try:
        api.vouchers.reset_to_open(cmd.voucher_id)
    except Exception as e:
        msg = f"Failed to unbook voucher {cmd.voucher_id}: {e}"
        raise SevDeskCLIError(msg) from e

    print(f"Successfully unbooked voucher #{cmd.voucher_id} (reset to unpaid status)")


def reset_voucher(api: SevDeskAPI, cmd: VouchersResetCommand) -> None:
    """Reset voucher status to draft or open."""
    try:
        if cmd.to_status == "draft":
            api.vouchers.reset_to_draft(cmd.voucher_id)
            status_text = "draft"
        else:  # "open"
            api.vouchers.reset_to_open(cmd.voucher_id)
            status_text = "open/unpaid"
    except Exception as e:
        msg = f"Failed to reset voucher {cmd.voucher_id} to {cmd.to_status}: {e}"
        raise SevDeskCLIError(msg) from e

    print(f"Successfully reset voucher #{cmd.voucher_id} to {status_text} status")


def parse_voucher_command(  # noqa: PLR0911
    args: argparse.Namespace,
) -> (
    VouchersListCommand
    | VouchersGetCommand
    | VouchersSaveCommand
    | VouchersBookCommand
    | VouchersUnbookCommand
    | VouchersResetCommand
    | None
):
    """Parse voucher command from argparse namespace."""
    if not hasattr(args, "action"):
        return None

    match args.action:
        case "list":
            return VouchersListCommand(
                status=getattr(args, "status", None),
                start_date=getattr(args, "start_date", None),
                end_date=getattr(args, "end_date", None),
                limit=getattr(args, "limit", None),
                offset=getattr(args, "offset", None),
            )
        case "get":
            return VouchersGetCommand(
                voucher_id=args.voucher_id,
            )
        case "save":
            # Parse positions
            positions: list[VoucherPositionInput] = []

            # From JSON file
            if hasattr(args, "positions_json") and args.positions_json:
                with Path(args.positions_json).open() as f:
                    positions_data = json.load(f)
                    positions.extend(
                        VoucherPositionInput(**pos_data) for pos_data in positions_data
                    )

            # From command line arguments (already parsed)
            elif hasattr(args, "position") and args.position:
                positions.extend(args.position)

            return VouchersSaveCommand(
                voucher_id=getattr(args, "voucher_id", None),
                credit_debit=getattr(args, "credit_debit", None),
                tax_type=args.tax_type if hasattr(args, "tax_type") else TaxType.EU,
                voucher_type=getattr(args, "voucher_type", None),
                status=getattr(args, "status", None),
                voucher_date=getattr(args, "voucher_date", None),
                supplier_id=getattr(args, "supplier_id", None),
                supplier_name=getattr(args, "supplier_name", None),
                description=getattr(args, "description", None),
                pay_date=getattr(args, "pay_date", None),
                currency=getattr(args, "currency", "EUR"),
                positions=positions if positions else None,
                tax_rule=getattr(args, "tax_rule", None),
            )
        case "book":
            return VouchersBookCommand(
                voucher_id=args.voucher_id,
                transaction_id=args.transaction_id,
                amount=getattr(args, "amount", None),
            )
        case "unbook":
            return VouchersUnbookCommand(
                voucher_id=args.voucher_id,
            )
        case "reset":
            return VouchersResetCommand(
                voucher_id=args.voucher_id,
                to_status=args.to_status,
            )
        case _:
            return None
