"""Tax rule management commands for SevDesk."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sevdesk_api.object_resolver import ObjectType

from sevdesk_cli.errors import SevDeskCLIError

if TYPE_CHECKING:
    import argparse

    from sevdesk_api import SevDeskAPI


@dataclass
class TaxRulesListCommand:
    """Tax rules list command."""


def add_tax_rule_subparser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Add tax rule subcommands to the parser."""
    tax_rule_parser = subparsers.add_parser("tax-rules", help="Manage tax rules")
    tax_rule_subparsers = tax_rule_parser.add_subparsers(
        dest="action",
        help="Tax rule actions",
    )

    # List tax rules
    tax_rule_subparsers.add_parser("list", help="List all tax rules")


def list_tax_rules(api: SevDeskAPI, cmd: TaxRulesListCommand) -> None:  # noqa: ARG001
    """List all available tax rules."""
    try:
        # Get all tax rules using the object resolver
        resolver = api.object_resolver
        tax_rules = resolver._fetch_objects(ObjectType.TAX_RULE, "id")  # noqa: SLF001
    except Exception as e:
        msg = f"Failed to fetch tax rules: {e}"
        raise SevDeskCLIError(msg) from e

    if not tax_rules:
        print("No tax rules found.")
        return

    # Display tax rules
    print("Available Tax Rules:")
    print("-" * 100)
    print(f"{'ID':<4} {'Code':<40} {'Name'}")
    print("-" * 100)

    for _rule_id, rule in sorted(tax_rules.items(), key=lambda x: int(x[0])):
        print(
            f"{rule['id']:<4} {rule.get('code', 'N/A'):<40} {rule['name']}",
        )

    print("-" * 100)
    print("\nUsage hints:")
    print(
        "- For expense vouchers: Use 'VORST_ABZUGSF_AUFW' (ID 9) for "
        "deductible expenses",
    )
    print("- For revenue vouchers: Use 'USTPFL_UMS_EINN' (ID 1) for taxable revenue")
    print(
        "- For EU transactions: Use 'INNERGEM_LIEF' (ID 3) for supplies, "
        "'INNERGEM_ERWERB' (ID 8) for acquisitions",
    )


def parse_tax_rule_command(args: argparse.Namespace) -> TaxRulesListCommand | None:
    """Parse tax rule command from argparse namespace."""
    if not hasattr(args, "action"):
        return None

    match args.action:
        case "list":
            return TaxRulesListCommand()
        case _:
            return None
