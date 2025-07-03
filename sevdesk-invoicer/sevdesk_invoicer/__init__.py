#!/usr/bin/env python3

# This script is currently only used by Jörg, in case someone else is also interested in using it,
# we can make it more flexible.
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from fractions import Fraction
from pathlib import Path
from typing import Any

from sevdesk_api import (
    Contact,
    Invoice,
    InvoicePosition,
    InvoiceStatus,
    SevDeskAPI,
    TaxRule,
    UnityTypes,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    api_token = os.environ.get("SEVDESK_API_TOKEN")
    parser.add_argument(
        "--sevdesk-api-token",
        default=api_token,
        required=api_token is None,
        help="Get one from https://my.sevdesk.de/#/admin/userManagement",
    )
    parser.add_argument(
        "--customer",
        required=False,
        type=str,
        help="Ignore customer from json and assume this one instead",
    )
    parser.add_argument(
        "--payment-method",
        required=False,
        type=int,
        help="Payment method id to use for invoice. You can find the id by saving an existing method and see what the id is in the url in your network tab inspector.",
    )
    parser.add_argument(
        "--days-until-payment",
        required=False,
        type=int,
        default=30,
        help="Days until payment is due",
    )
    parser.add_argument(
        "json_file", help="JSON file containing reports (as opposed to stdin)"
    )
    return parser.parse_args()


def get_contact_by_name(api: SevDeskAPI, name: str) -> Contact:
    contacts = api.contacts.search_by_name(name)
    if len(contacts) == 0:
        msg = f"Could not find customer with name {name}. Please create it first in contacts."
        raise ValueError(msg)
    if len(contacts) > 1:
        ids = " ".join(c.customer_number or "N/A" for c in contacts)
        msg = f"Found multiple customers with name: {ids}"
        raise ValueError(msg)
    return contacts[0]


def are_floats_similar(a: float, b: float, error_rate: float) -> bool:
    """Compare two floats to see if they are 'similar enough' within the specified error rate."""
    curr_err = abs(a - b)
    return curr_err <= error_rate


def line_item(task: dict[str, Any], has_agency: bool) -> InvoicePosition:
    price = float(
        round(
            (Fraction(task["target_cost"]) / Fraction(task["rounded_hours"])),
            2,
        )
    )
    if are_floats_similar(task["target_hourly_rate"], price, 0.02):
        price = task["target_hourly_rate"]
    else:
        msg = f"Price {price} is not similar to target hourly rate {task['target_hourly_rate']}"
        raise RuntimeError(msg)

    original_price = float(
        round(
            (Fraction(task["source_cost"]) / Fraction(task["rounded_hours"])),
            2,
        )
    )
    if are_floats_similar(task["source_hourly_rate"], original_price, 0.02):
        original_price = task["source_hourly_rate"]
    else:
        msg = f"Original price {original_price} is not similar to source hourly rate {task['source_hourly_rate']}"
        raise RuntimeError(msg)

    text = ""
    if task["source_currency"] != task["target_currency"]:
        text = f"{task['source_currency']} {original_price} x {float(task['exchange_rate'])} = {task['target_currency']} {price}"
    name = f"{task['client']} - {task['task']}" if has_agency else task["task"]
    return InvoicePosition(
        name=name,
        unity=UnityTypes.HOUR,
        tax_rate=0,
        text=text,
        quantity=task["rounded_hours"],
        price=price,
    )


def create_invoice(
    api_token: str,
    customer_name: str | None,
    payment_method: str | None,
    tasks: list[dict[str, Any]],
    days_until_payment: int = 30,
) -> None:
    api = SevDeskAPI(api_token)

    # Get the current user for contact person
    user_resp = api.client.get("SevUser")
    if not user_resp.get("objects"):
        msg = "Could not fetch current user"
        raise ValueError(msg)
    current_user = user_resp["objects"][0]

    start = datetime.strptime(str(tasks[0]["start_date"]), "%Y%m%d")
    end = datetime.strptime(str(tasks[0]["end_date"]), "%Y%m%d")
    currency = tasks[0]["target_currency"]
    agency = tasks[0]["agency"]
    # agency == "-" is legacy
    has_agency = agency not in {"-", "none"}
    if customer_name:
        billing_target = customer_name
    elif has_agency:
        billing_target = agency
    else:
        billing_target = tasks[0]["client"]
    items = [line_item(task, has_agency) for task in tasks]

    customer = get_contact_by_name(api, billing_target)

    head_text = f"""Terms of payment: Payment within {days_until_payment} days from receipt of invoice without deductions."""
    time = start.strftime("%Y-%m")

    # Create invoice object
    invoice = Invoice(
        status=InvoiceStatus.DRAFT,
        header=f"Bill for {time}",
        head_text=head_text,
        contact=customer,
        reference=None,
        tax_rule=TaxRule.NOT_TAXABLE_IN_COUNTRY,  # Using tax rule instead of tax type
        delivery_date=start,
        delivery_date_until=end,
        currency=currency,
        invoice_date=datetime.now(),
        time_to_pay=days_until_payment,
        contact_person={"id": current_user["id"], "objectName": "SevUser"},
    )

    # Create the invoice with positions
    created_invoice = api.invoices.create_invoice(invoice, items)
    print(
        f"Invoice created successfully: https://my.sevdesk.de/fi/detail/type/RE/id/{created_invoice.id}"
    )


def main() -> None:
    args = parse_args()
    if args.json_file:
        tasks = json.loads(Path(args.json_file).read_text())
    else:
        tasks = json.load(sys.stdin)
    create_invoice(
        args.sevdesk_api_token,
        args.customer,
        args.payment_method,
        tasks,
        args.days_until_payment,
    )


if __name__ == "__main__":
    main()
