import argparse
import json
from decimal import Decimal
from pathlib import Path


class Error(Exception):
    pass


def convert_to_decimal(value: str) -> Decimal:
    if "," not in value:
        msg = "Value should be in the format 10.1234,56"
        raise ValueError(msg)
    return Decimal(value.replace(".", "").replace(",", "."))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--harvest-folder",
        help="Folder containing all harvest json files",
        type=str,
        required=True,
    )
    parser.add_argument(
        "--wise-folder",
        help="Folder containing all wise transactions files",
        type=str,
        required=True,
    )
    parser.add_argument(
        "--tax-office-name",
        help="Name of the tax office as it appears in Wise",
        type=str,
        required=True,
    )
    parser.add_argument(
        "--calculated-tax", type=str, help="Use https://www.bmf-steuerrechner.de/"
    )
    parser.add_argument(
        "--estimated-expenses",
        type=str,
        help="Go to sevdesk and get the sum of all expenses",
    )
    parser.add_argument(
        "--description",
        type=str,
        help="Description used by Wise to filter transactions",
    )
    args = parser.parse_args()

    revenue = Decimal(0)
    for file in Path(args.harvest_folder).glob("*.json"):
        text = Path(file).read_text()
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            msg = f"Failed to parse {file}"
            raise Error(msg) from e
        for entry in data:
            revenue += Decimal(entry["target_cost"])

    # get sum of all payed taxes
    payed_taxes = Decimal(0)
    for file in Path(args.wise_folder).glob("*.json"):
        text = Path(file).read_text()
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            msg = f"Failed to parse {file}"
            raise Error(msg) from e
        if "transactions" not in data[0]:
            continue
        for entry in data[0]["transactions"]:
            if (
                entry["details"]["type"] == "DIRECT_DEBIT"
                and args.tax_office_name in entry["details"]["description"]
            ):
                payed_taxes += -Decimal(entry["amount"]["value"])

    estimated_expenses = args.estimated_expenses
    if not estimated_expenses:
        estimated_expenses = input(
            "Go to https://sevdesk.de/ and get the sum of all expenses: "
        )
    estimated_expenses = convert_to_decimal(estimated_expenses)

    calculated_tax = args.calculated_tax
    if not args.calculated_tax:
        print(f"Taxable net income: {revenue - estimated_expenses}")
        calculated_tax = input(
            "Use https://www.bmf-steuerrechner.de/ to calculate remaining taxes, based on your taxable net income: "
        )
    calculated_tax = convert_to_decimal(calculated_tax)

    print()
    print(f"Revenue:            | {revenue:.2f}")
    print(f"Expenses:           | {estimated_expenses:.2f}")
    print(f"Net income:         | {revenue - estimated_expenses:.2f}")
    print(f"Payed taxes:        | {payed_taxes:.2f}")
    print(f"Calculated taxes:   | {calculated_tax:.2f}")
    print("--------------------|----------")
    print(f"Taxes left to pay:  | {Decimal(calculated_tax) - payed_taxes:.2f}")


if __name__ == "__main__":
    main()
