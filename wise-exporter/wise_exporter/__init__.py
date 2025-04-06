#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import calendar
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from typing import Any, NoReturn

import rsa

BASE_URL = " https://api.transferwise.com"


class Signer:
    def __init__(self, private_key: bytes) -> None:
        self.private_key = rsa.PrivateKey.load_pkcs1(private_key, "PEM")

    def sca_challenge(self, one_time_token: str) -> str:
        # Use the private key to sign the one-time-token that was returned
        # in the x-2fa-approval header of the HTTP 403.
        signed_token = rsa.sign(
            one_time_token.encode("ascii"), self.private_key, "SHA-256"
        )

        # Encode the signed message as friendly base64 format for HTTP
        # headers.
        return base64.b64encode(signed_token).decode("ascii")


class Balance:
    def __init__(self, balance_id: int, currency: str) -> None:
        self.id = balance_id
        self.currency = currency


class WiseClient:
    def __init__(self, api_key: str, private_key: bytes) -> None:
        self.api_key = api_key
        self.signer = Signer(private_key)

    def _http_request(
        self,
        url: str,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        if headers is None:
            headers = {}
        body = None
        if data:
            body = json.dumps(data).encode("ascii")
        headers = headers.copy()
        req = urllib.request.Request(url, headers=headers, method=method, data=body)
        resp = urllib.request.urlopen(req)
        return json.load(resp)

    def http_request(
        self,
        path: str,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        if headers is None:
            headers = {}
        headers["Authorization"] = f"Bearer {self.api_key}"
        headers["Content-Type"] = "application/json"
        headers["User-Agent"] = "Numtide wise importer"
        try:
            return self._http_request(f"{BASE_URL}/{path}", method, headers, data)
        except urllib.error.HTTPError as e:
            if e.code == 403 and "x-2fa-approval" in e.headers:
                one_time_token = e.headers["x-2fa-approval"]
                headers["x-2fa-approval"] = one_time_token
                headers["X-Signature"] = self.signer.sca_challenge(one_time_token)
                return self._http_request(f"{BASE_URL}/{path}", method, headers, data)
            raise

    def get_buisness_profile(self) -> int:
        r = self.http_request("/v2/profiles")
        assert isinstance(r, list)
        profiles = [p["id"] for p in r if p["type"] == "BUSINESS"]
        if len(profiles) == 0:
            die(
                f"No business profiles found, however found the following personal profiles: {' '.join(p['id'] for p in r)}."
            )
        if len(profiles) > 1:
            die(
                f"Found multiple business profiles: {' '.join(p['id'] for p in r)}.\nSelect one by setting the WISE_PROFILE environment variable."
            )
        return profiles[0]

    def get_balances(self, profile: int) -> list[Balance]:
        r = self.http_request(f"/v4/profiles/{profile}/balances?types=STANDARD")
        assert isinstance(r, list)
        return [Balance(a["id"], a["currency"]) for a in r]

    def get_balance_statements(
        self, profile: int, balance: Balance, start: str, end: str
    ) -> dict[str, Any]:
        path = f"/v1/profiles/{profile}/balance-statements/{balance.id}/statement.json?currency={balance.currency}&intervalStart={start}T00:00:00.000Z&intervalEnd={end}T23:59:59.999Z&type=COMPACT"
        r = self.http_request(path)
        assert isinstance(r, dict)
        return r

    # GET


def die(msg: str) -> NoReturn:
    print(msg, file=sys.stderr)
    sys.exit(1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    api_token = os.environ.get("WISE_API_TOKEN")
    parser.add_argument(
        "--wise-api-token",
        default=api_token,
        required=api_token is None,
        help="Get one from https://wise.com/settings/",
    )
    private_key = os.environ.get("WISE_PRIVATE_KEY")
    parser.add_argument(
        "--wise-private-key",
        default=private_key,
        help="Upload one to https://wise.com/settings/",
    )
    raw_profile_id = os.environ.get("WISE_PROFILE")
    profile_id = None
    if raw_profile_id is not None:
        try:
            profile_id = int(raw_profile_id)
        except ValueError:
            die("WISE_PROFILE must be an integer")
    parser.add_argument(
        "--wise-profile",
        type=int,
        default=profile_id,
        help="Profile ID to use",
    )
    parser.add_argument(
        "--start",
        type=int,
        help="Start date i.e. 20220101",
    )
    parser.add_argument(
        "--end",
        type=int,
        help="End date i.e. 20220101",
    )
    parser.add_argument(
        "--month",
        type=int,
        choices=range(1, 13),
        help="Month to generate report for (conflicts with `--start` and `--end`)",
    )
    parser.add_argument(
        "--year",
        type=int,
        help="Year to generate report for (conflicts with `--start` and `--end`)",
    )
    args = parser.parse_args()
    if not args.wise_private_key:
        msg = """
--wise-private-key is not set

You can generate a key pair using the following commands:

```
$ openssl genrsa -out private.pem 2049 && ssh-keygen -p -m PEM -f private.pem -N "" && openssl rsa -pubout -in private.pem -out public.pem
```

Upload this key: ./public.pem

The public keys management page can be accessed via the "Manage public keys" button under the API tokens section of your Wise a
ccount settings.
"""
        die(msg)
    today = datetime.today()
    if args.month and (args.start or args.end):
        print("--month flag conflicts with --start and --end", file=sys.stderr)
        sys.exit(1)
    if args.month:
        year = today.year
        if args.year:
            year = args.year
        _, last_day = calendar.monthrange(year, args.month)
        args.start = date(year, args.month, 1).strftime("%Y-%m-%d")
        args.end = date(year, args.month, last_day).strftime("%Y-%m-%d")
    elif (args.start and not args.end) or (args.end and not args.start):
        print("both --start and --end flag must be passed", file=sys.stderr)
        sys.exit(1)
    elif not args.start and not args.end:
        # Show the previous month by default
        start_of_month = today.replace(day=1)
        end_of_previous_month = start_of_month - timedelta(days=1)
        args.start = end_of_previous_month.strftime("%Y-%m-01")
        args.end = end_of_previous_month.strftime("%Y-%m-%d")
    return args


def main() -> None:
    args = parse_args()

    client = WiseClient(args.wise_api_token, args.wise_private_key.encode("ascii"))
    if not args.wise_profile:
        args.wise_profile = client.get_buisness_profile()
    balances = client.get_balances(args.wise_profile)
    statement_per_account = []
    for balance in balances:
        statements = client.get_balance_statements(
            args.wise_profile, balance, args.start, args.end
        )
        statement_per_account.append(statements)

    json.dump(statement_per_account, sys.stdout, indent=2)
