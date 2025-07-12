"""SevDesk CLI - Command line interface for SevDesk API."""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from sevdesk_api import SevDeskAPI, SevDeskError

from sevdesk_cli.cli.vouchers import (
    VoucherPositionInput,
    VouchersCreateCommand,
    VouchersGetCommand,
    VouchersListCommand,
    add_voucher_subparser,
    create_voucher,
    get_voucher,
    list_vouchers,
)
from sevdesk_cli.errors import (
    AuthenticationError,
    ConfigError,
    SevDeskCLIError,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger(__name__)

Command = VouchersListCommand | VouchersGetCommand | VouchersCreateCommand


@dataclass
class Options:
    """Parsed command line options."""

    url: str | None = None
    token: str | None = None
    token_command: str | None = None
    debug: bool = False
    command: Command | None = None


def load_config() -> dict[str, Any]:
    """Load configuration from XDG_CONFIG_HOME/sevdesk-cli/config.json."""
    xdg_config_home = os.environ.get(
        "XDG_CONFIG_HOME",
        str(Path.home() / ".config"),
    )
    config_dir = Path(xdg_config_home) / "sevdesk-cli"
    config_file = config_dir / "config.json"

    if config_file.exists():
        try:
            with config_file.open() as f:
                return cast("dict[str, Any]", json.load(f))
        except (json.JSONDecodeError, OSError) as e:
            msg = f"Failed to load config file: {e}"
            raise ConfigError(msg) from e
    return {}


def get_token(token: str | None, token_command: str | None) -> str | None:
    """Get token from direct value or by running a command."""
    if token:
        return token

    if token_command:
        try:
            result = subprocess.run(  # noqa: S602
                token_command,
                shell=True,
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            msg = f"Failed to get token from command: {e}"
            raise AuthenticationError(msg) from e

    return None


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser."""
    parser = argparse.ArgumentParser(description="SevDesk CLI")
    parser.add_argument(
        "--url",
        default=os.environ.get("SEVDESK_URL"),
        help="SevDesk API URL (or set SEVDESK_URL env var)",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("SEVDESK_API_TOKEN"),
        help="API token (or set SEVDESK_API_TOKEN env var)",
    )
    parser.add_argument(
        "--token-command",
        help="Command to run to get the API token",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug output",
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Add voucher subcommands
    add_voucher_subparser(subparsers)

    return parser


def parse_args(argv: Sequence[str] | None = None) -> Options:
    """Parse command line arguments and return Options."""
    parser = create_parser()
    args = parser.parse_args(argv)

    # Create Options
    options = Options(
        url=args.url,
        token=args.token,
        token_command=args.token_command,
        debug=args.debug,
    )

    # Handle voucher commands
    if args.command == "vouchers" and hasattr(args, "action"):
        action = args.action
        if action == "list":
            options.command = VouchersListCommand(
                status=getattr(args, "status", None),
                start_date=getattr(args, "start_date", None),
                end_date=getattr(args, "end_date", None),
                limit=getattr(args, "limit", None),
                offset=getattr(args, "offset", None),
            )
        elif action == "get":
            options.command = VouchersGetCommand(
                voucher_id=args.voucher_id,
            )
        elif action == "create":
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

            options.command = VouchersCreateCommand(
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

    return options


def handle_command(api: SevDeskAPI, command: Command) -> None:
    """Handle the execution of a command."""
    match command:
        case VouchersListCommand() as cmd:
            list_vouchers(api, cmd)
        case VouchersGetCommand() as cmd:
            get_voucher(api, cmd)
        case VouchersCreateCommand() as cmd:
            create_voucher(api, cmd)
        case _:
            print("Unknown command")
            sys.exit(1)


def configure_logging(*, debug: bool) -> None:
    """Configure logging based on debug flag."""
    if debug:
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(levelname)s: %(message)s",
        )
    else:
        logging.basicConfig(level=logging.INFO, format="%(message)s")


def get_api_url(options: Options, config: dict[str, Any]) -> str:
    """Get API URL from options or config."""
    url = options.url or config.get("url") or "https://my.sevdesk.de/api/v1/"
    if not url:
        print(
            "Error: SevDesk URL not provided. Use --url, set SEVDESK_URL, "
            "or add to config",
        )
        sys.exit(1)
    return url


def get_api_token(options: Options, config: dict[str, Any]) -> str:
    """Get API token from options or config."""
    try:
        token = get_token(
            options.token,
            options.token_command or config.get("token_command"),
        )
    except AuthenticationError as e:
        print(f"Authentication error: {e}")
        sys.exit(1)

    if not token:
        print(
            "Error: API token not provided. Use --token, set SEVDESK_API_TOKEN, "
            "--token-command, or add to config",
        )
        sys.exit(1)
    return token


def main(argv: Sequence[str] | None = None) -> None:
    """Run the main entry point."""
    options = parse_args(argv)
    configure_logging(debug=options.debug)

    # Debug logging
    logger.debug("Options: %s", options)
    logger.debug("Command: %s", options.command)

    if not options.command:
        # Create parser just for help
        parser = create_parser()
        parser.print_help()
        sys.exit(1)

    # Load config file
    try:
        config = load_config()
    except ConfigError as e:
        print(f"Configuration error: {e}")
        sys.exit(1)

    # Get URL and token
    url = get_api_url(options, config)
    token = get_api_token(options, config)

    try:
        api = SevDeskAPI(token, url)
        handle_command(api, options.command)
    except SevDeskError as e:
        print(f"API Error: {e}")
        sys.exit(1)
    except SevDeskCLIError as e:
        print(f"CLI Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        if options.debug:
            raise
        sys.exit(1)


if __name__ == "__main__":
    main()
