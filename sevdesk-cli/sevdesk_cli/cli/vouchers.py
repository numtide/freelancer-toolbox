"""Voucher management commands for SevDesk."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sevdesk_api import (
    CreditDebit,
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


@dataclass
class VouchersCreateCommand:
    """Vouchers create command."""

    credit_debit: CreditDebit
    tax_type: TaxType
    voucher_type: VoucherType
    status: VoucherStatus
    voucher_date: datetime | None = None
    supplier_id: int | None = None
    supplier_name: str | None = None
    description: str | None = None
    pay_date: datetime | None = None
    currency: str = "EUR"
    positions: list[VoucherPositionInput] | None = None


@dataclass
class VouchersUpdateCommand:
    """Vouchers update command."""

    voucher_id: int
    status: VoucherStatus | None = None
    description: str | None = None
    pay_date: datetime | None = None
    supplier_name: str | None = None


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

    # Create voucher
    create_parser = voucher_subparsers.add_parser(
        "create",
        help="Create a new voucher",
    )
    create_parser.add_argument(
        "--credit-debit",
        required=True,
        type=lambda x: CreditDebit(x.upper()),
        choices=list(CreditDebit),
        help="Credit or debit",
    )
    create_parser.add_argument(
        "--tax-type",
        required=True,
        type=lambda x: TaxType(x.lower()),
        choices=list(TaxType),
        help="Tax type",
    )
    create_parser.add_argument(
        "--voucher-type",
        required=True,
        type=lambda x: VoucherType(x.upper()),
        choices=list(VoucherType),
        help="Voucher type",
    )
    create_parser.add_argument(
        "--status",
        type=parse_voucher_status,
        required=True,
        help="Status (DRAFT or UNPAID)",
    )
    create_parser.add_argument(
        "--voucher-date",
        type=parse_date,
        help="Date of the voucher (YYYY-MM-DD)",
    )
    create_parser.add_argument(
        "--supplier-id",
        type=int,
        help="ID of supplier contact",
    )
    create_parser.add_argument(
        "--supplier-name",
        help="Name of supplier (if no contact)",
    )
    create_parser.add_argument(
        "--description",
        help="Description/number of voucher",
    )
    create_parser.add_argument(
        "--pay-date",
        type=parse_date,
        help="Payment deadline (YYYY-MM-DD)",
    )
    create_parser.add_argument(
        "--currency",
        default="EUR",
        help="Currency code (default: EUR)",
    )
    create_parser.add_argument(
        "--positions-json",
        type=str,
        help="JSON file with positions data",
    )
    create_parser.add_argument(
        "--position",
        action="append",
        nargs=4,
        metavar=("NAME", "QUANTITY", "PRICE", "TAX_RATE"),
        help="Add a position: NAME QUANTITY PRICE TAX_RATE (can use multiple times)",
    )

    # Update voucher
    update_parser = voucher_subparsers.add_parser(
        "update",
        help="Update an existing voucher",
    )
    update_parser.add_argument("voucher_id", type=int, help="Voucher ID")
    update_parser.add_argument(
        "--status",
        type=parse_voucher_status,
        help="Update status (DRAFT=50, OPEN=100, PAID=1000)",
    )
    update_parser.add_argument(
        "--description",
        help="Update description",
    )
    update_parser.add_argument(
        "--pay-date",
        type=parse_date,
        help="Update payment date (YYYY-MM-DD)",
    )
    update_parser.add_argument(
        "--supplier-name",
        help="Update supplier name",
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
        status_text = {50: "Draft", 100: "Unpaid", 1000: "Paid"}.get(
            status_int,
            f"Unknown ({status})",
        )

        # Format type
        type_text = "Credit" if credit_debit == "C" else "Debit"

        print(f"ID: {voucher_id}")
        print(f"Description: {description}")
        print(f"Type: {type_text}")
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
    status_text = {50: "Draft", 100: "Unpaid", 1000: "Paid"}.get(
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
    output_lines.extend(_format_voucher_positions(api, cmd.voucher_id))

    # Print all lines
    for line in output_lines:
        print(line)


def create_voucher(api: SevDeskAPI, cmd: VouchersCreateCommand) -> None:
    """Create a new voucher."""
    # Convert position inputs to VoucherPosition objects
    positions = []
    if cmd.positions:
        for pos_input in cmd.positions:
            position = VoucherPosition(
                name=pos_input.name,
                quantity=pos_input.quantity,
                price=pos_input.price,
                tax_rate=pos_input.tax_rate,
                net=pos_input.net,
                text=pos_input.text,
            )
            positions.append(position)

    # Create voucher via API
    try:
        result = api.vouchers.create_voucher(
            credit_debit=cmd.credit_debit,
            tax_type=cmd.tax_type,
            voucher_type=cmd.voucher_type,
            status=cmd.status,
            voucher_date=cmd.voucher_date,
            supplier_id=cmd.supplier_id,
            supplier_name=cmd.supplier_name,
            description=cmd.description,
            pay_date=cmd.pay_date,
            currency=cmd.currency,
            voucher_positions=positions if positions else None,
        )
    except Exception as e:
        msg = f"Failed to create voucher: {e}"
        raise SevDeskCLIError(msg) from e

    # Parse response
    try:
        voucher = result.get("objects", {}).get("voucher", {})
        voucher_id = voucher.get("id")
        if not voucher_id:
            msg = "No voucher ID returned in response"
            raise SevDeskCLIError(msg)
    except (KeyError, TypeError) as e:
        msg = f"Invalid response format: {e}"
        raise SevDeskCLIError(msg) from e

    print(f"Successfully created voucher #{voucher_id}")


def update_voucher(api: SevDeskAPI, cmd: VouchersUpdateCommand) -> None:
    """Update an existing voucher."""
    try:
        result = api.vouchers.update_voucher(
            voucher_id=cmd.voucher_id,
            status=cmd.status,
            description=cmd.description,
            pay_date=cmd.pay_date,
            supplier_name=cmd.supplier_name,
        )
    except Exception as e:
        msg = f"Failed to update voucher {cmd.voucher_id}: {e}"
        raise SevDeskCLIError(msg) from e

    # Parse response
    try:
        voucher = result.get("objects", {})
        if isinstance(voucher, list) and voucher:
            voucher = voucher[0]
        voucher_id = voucher.get("id", cmd.voucher_id)
    except (KeyError, TypeError, IndexError) as e:
        msg = f"Invalid response format: {e}"
        raise SevDeskCLIError(msg) from e

    print(f"Successfully updated voucher #{voucher_id}")


def parse_voucher_command(
    args: argparse.Namespace,
) -> (
    VouchersListCommand
    | VouchersGetCommand
    | VouchersCreateCommand
    | VouchersUpdateCommand
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
        case "create":
            # Parse positions
            positions: list[VoucherPositionInput] = []

            # From JSON file
            if hasattr(args, "positions_json") and args.positions_json:
                with Path(args.positions_json).open() as f:
                    positions_data = json.load(f)
                    positions.extend(
                        VoucherPositionInput(**pos_data) for pos_data in positions_data
                    )

            # From command line arguments
            elif hasattr(args, "position") and args.position:
                for pos_args in args.position:
                    name, quantity, price, tax_rate = pos_args
                    positions.append(
                        VoucherPositionInput(
                            name=name,
                            quantity=float(quantity),
                            price=float(price),
                            tax_rate=float(tax_rate),
                        ),
                    )

            return VouchersCreateCommand(
                credit_debit=args.credit_debit,
                tax_type=args.tax_type,
                voucher_type=args.voucher_type,
                status=args.status,
                voucher_date=getattr(args, "voucher_date", None),
                supplier_id=getattr(args, "supplier_id", None),
                supplier_name=getattr(args, "supplier_name", None),
                description=getattr(args, "description", None),
                pay_date=getattr(args, "pay_date", None),
                currency=getattr(args, "currency", "EUR"),
                positions=positions if positions else None,
            )
        case "update":
            return VouchersUpdateCommand(
                voucher_id=args.voucher_id,
                status=getattr(args, "status", None),
                description=getattr(args, "description", None),
                pay_date=getattr(args, "pay_date", None),
                supplier_name=getattr(args, "supplier_name", None),
            )
        case _:
            return None
