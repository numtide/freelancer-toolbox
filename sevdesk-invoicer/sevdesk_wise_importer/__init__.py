#!/usr/bin/env python3

# This script is currently only used by Jörg, in case someone else is also interested in using it,
# we can make it more flexible.

import argparse
import csv
import datetime
import json
import os
import sys
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn

from sevdesk_api import SevDeskAPI, SevDeskError


def die(msg: str) -> NoReturn:
    print(msg, file=sys.stderr)
    sys.exit(1)


@dataclass
class NeutralTransactionCurrencies:
    source_currency: str
    target_currency: str


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
        "--import-state-file",
        default="import-state.json",
        type=Path,
        help="Used to memorize already imported transactions",
    )
    parser.add_argument(
        "--add-account",
        metavar=("account_number", "currency"),
        nargs=2,
        action="append",
        default=[],
        help='Add a currency to the bank account number mapping (IBAN or account number) i.e. --add-account "BE00 0000 0000 0000" EUR',
    )
    parser.add_argument(
        "--import-neutral",
        metavar=("source_currency", "target_currency"),
        nargs=2,
        action="append",
        default=[],
        help="Import neutral transactions that match source currency and target currency.",
    )
    parser.add_argument(
        "--ignore-currency",
        action="append",
        default=[],
        help="Ignore any transaction involving this currency.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not actually import anything, just print what would be done",
    )
    parser.add_argument(
        "csv_file",
        help="CSV file containing wise bank statements (as opposed to stdin)",
    )
    return parser.parse_args()


class Accounts:
    def __init__(self, api: SevDeskAPI) -> None:
        self.api = api
        self.accounts: dict[str, str] = {}
        self.cache: dict[str, int] = {}

    def add_account(self, account_id: str, currency: str) -> None:
        if currency in self.accounts:
            die(f"Duplicate currency {currency}")
        self.accounts[currency] = account_id

    def get_or_create_account(self, currency: str) -> int:
        account_id = self.accounts.get(currency)
        if account_id is None:
            die(f"Missing account id for currency {currency}")
        if currency in self.cache:
            return self.cache[currency]
        name = f"Wise ({currency}, {account_id})"
        try:
            res = self.api.check_accounts.get_check_accounts()
            if res and "objects" in res:
                for obj in res["objects"]:
                    # We only want to return accounts that are not registers (German KASSE)
                    if (
                        obj.get("name") == name
                        and obj.get("type") != "register"
                    ):
                        return obj["id"]
        except SevDeskError as e:
            die(f"Failed to get check accounts: {e}")
        die(
            f"missing account '{name}', please create the respective account on sevdesk by uploading a dummy CSV"
        )


# These had to be introduced when switching from the wise API to the CSV export
ALIASES = {
    "CARD_TRANSACTION": "CARD",
    "DIRECT_DEBIT_TRANSACTION": "DIRECT_DEBIT",
}


def import_record(
    api: SevDeskAPI,
    accounts: Accounts,
    record: dict[str, Any],
    import_state: set[str],
    ignore_currencies: set[str],
    neutral_currencies: list[NeutralTransactionCurrencies],
    dry_run: bool = False,
) -> None:
    status = record["Status"]
    if status == "REFUNDED":
        print(f"Skipping refunded transaction {record['ID']}")
        return
    elif status == "CANCELLED":
        print(f"Skipping cancelled transaction {record['ID']}")
        return
    elif status == "COMPLETED":
        pass
    else:
        die(f"Unknown status '{status}'")
    direction = record["Direction"]
    if direction == "IN":
        currency = record["Target currency"]
        payee_payer_name = record["Source name"]
        amount = float(record["Target amount (after fees)"])
    elif direction == "OUT":
        currency = record["Source currency"]
        payee_payer_name = record["Target name"]
        source_fee_str = record["Source fee amount"]
        source_fee = float(source_fee_str) if source_fee_str else 0.0
        amount = -float(record["Source amount (after fees)"]) - source_fee
    elif direction == "NEUTRAL":
        currencies = NeutralTransactionCurrencies(
            record["Source currency"], record["Target currency"]
        )
        currency = currencies.target_currency
        exchange_rate = record["Exchange rate"]
        if currencies not in neutral_currencies:
            print(
                f"Skipping neutral transaction with currencies {currencies.source_currency} -> {currencies.target_currency}"
            )
            return
        payee_payer_name = record["Source name"]
        amount = float(record["Target amount (after fees)"])
    else:
        die(f"Unknown direction {direction} for {record['ID']}")

    # Wise exports a list of transaction involving all accounts
    if currency in ignore_currencies and direction in {"IN", "OUT"}:
        print(
            f"Skipping {direction} transaction {record['ID']} with ignored currency {currency}"
        )
        return

    reference = record["Reference"]

    account_number = accounts.get_or_create_account(currency)
    record_id = record["ID"]
    if "CARD_TRANSACTION" in record_id and reference == "" and direction == "OUT":
        target_currency = record["Target currency"]
        target_amount = record["Target amount (after fees)"]
        reference = f"Card transaction of {target_amount} ({target_currency})"
    for original_name, replacement in ALIASES.items():
        record_id = record_id.replace(original_name, replacement)

    if reference == "" and direction == "NEUTRAL":
        reference = f"Currency exchange from {currencies.source_currency} to {currencies.target_currency} at exchange rate {exchange_rate}"

    transaction_id = f"{currency}-{account_number}-{record_id}"

    if transaction_id in import_state:
        print(f"Skipping already imported transaction {transaction_id}")
        return

    import_state.add(transaction_id)
    # What timezone is this?
    created_on = datetime.datetime.strptime(record["Created on"], "%Y-%m-%d %H:%M:%S")
    finished_on = datetime.datetime.strptime(record["Finished on"], "%Y-%m-%d %H:%M:%S")
    if created_on > finished_on:
        print(
            f"WARNING: Transaction {transaction_id} has created_on > finished_on, skipping",
            file=sys.stderr,
        )
    if dry_run:
        print(
            f"id={record_id} currency={currency} entry_date={record['Created on']}, value_date={record['Finished on']}, amount={amount}, payee_payer_name={payee_payer_name}, paymt_purpose={reference}"
        )
    else:
        try:
            api.transactions.create_transaction(
                check_account_id=account_number,
                value_date=finished_on,
                amount=amount,
                status=100,  # Created status
                payee_payer_name=payee_payer_name,
                entry_date=created_on,
                paymt_purpose=reference,
            )
        except SevDeskError as e:
            die(f"Failed to create transaction: {e}")


def main() -> None:
    args = parse_args()
    ignore_currencies = set(args.ignore_currency)
    neutral_currencies = [
        NeutralTransactionCurrencies(source_currency, target_currency)
        for source_currency, target_currency in args.import_neutral
    ]
    if len(args.add_account) == 0:
        die("No accounts specifed, use --add-account")
    with ExitStack() as exit_stack:
        if args.csv_file:
            csv_file = exit_stack.enter_context(Path(args.csv_file).open(newline=""))
            records = csv.DictReader(csv_file)
        else:
            records = csv.DictReader(sys.stdin)
        api = SevDeskAPI(api_token=args.sevdesk_api_token)
        accounts = Accounts(api=api)

        for account_number, currency in args.add_account:
            accounts.add_account(account_number, currency)
        if args.import_state_file.exists():
            imported_transactions = set(json.loads(args.import_state_file.read_text()))
        else:
            imported_transactions = set()

        for record in records:
            import_record(
                api,
                accounts,
                record,
                imported_transactions,
                ignore_currencies,
                neutral_currencies,
                dry_run=args.dry_run,
            )
            if not args.dry_run:
                args.import_state_file.write_text(
                    json.dumps(sorted(imported_transactions), indent=2)
                )


if __name__ == "__main__":
    main()
