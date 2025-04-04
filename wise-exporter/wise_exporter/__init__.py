#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import calendar
import json
import os
import shlex
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, NoReturn

import rsa
from jwcrypto import jwe, jwk

BASE_URL = "https://api.transferwise.com"


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


@dataclass
class WiseResult:
    status_code: int
    data: dict[str, Any] | list[dict[str, Any]]


class WiseClient:
    def __init__(
        self, api_key: str, private_key: bytes, pin: str | None = None
    ) -> None:
        self.api_key = api_key
        self.signer = Signer(private_key)
        self.pin: str | None = pin  # Store pin if provided

    def _http_request(
        self,
        url: str,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        data: dict[str, Any] | None = None,
    ) -> WiseResult:
        if headers is None:
            headers = {}
        body = None
        if data:
            body = json.dumps(data).encode("ascii")
        headers = headers.copy()

        req = urllib.request.Request(
            f"{BASE_URL}/{url}", headers=headers, method=method, data=body
        )
        resp = urllib.request.urlopen(req)
        return WiseResult(status_code=resp.getcode(), data=json.load(resp))

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
            return self._http_request(path, method, headers, data).data
        except urllib.error.HTTPError as e:
            if e.code == 403 and "x-2fa-approval" in e.headers:
                # Extract one-time token from the header
                x_2fa_approval = e.headers["x-2fa-approval"].strip().split(" ")
                one_time_token = x_2fa_approval[0]

                # If challenge type is specified in header, use it (usually for signature)
                explicit_challenge_type = None
                if len(x_2fa_approval) >= 2:
                    explicit_challenge_type = x_2fa_approval[1]

                # Handle the 2FA challenge
                self._handle_2fa_challenge(one_time_token, explicit_challenge_type)

                # Retry the original request
                return self._http_request(path, method, headers, data).data
            if e.code == 403:
                print(f"URL: {e.url}", file=sys.stderr)
                print(f"Headers: {e.headers}", file=sys.stderr)
                die(
                    "This API call needs 2FA. For more information, visit: https://docs.wise.com/api-docs/features/strong-customer-authentication-2fa"
                )
            elif e.code == 404:
                msg = f"Not Found URL: {e.url}"
                raise RuntimeError(msg) from e
            else:
                raise

    def _get_token_status(self, one_time_token: str) -> dict[str, Any]:
        """Get the status of a one-time token."""
        headers = {"One-Time-Token": one_time_token}
        result = self._http_request("v1/one-time-token/status", "GET", headers).data
        assert isinstance(result, dict)
        return result

    def _find_required_challenge(
        self, token_status: dict[str, Any]
    ) -> tuple[str | None, bool]:
        """Find the required challenge from token status."""
        challenges = token_status.get("oneTimeTokenProperties", {}).get(
            "challenges", []
        )

        for challenge in challenges:
            if challenge.get("required") and not challenge.get("passed"):
                return challenge.get("primaryChallenge", {}).get("type"), True

        return None, False

    def _handle_2fa_challenge(
        self, one_time_token: str, explicit_challenge_type: str | None = None
    ) -> None:
        """Handle 2FA challenge based on the token status or explicit type."""
        try:
            # If explicit challenge type is provided (like 'signature'), use it directly
            if (
                explicit_challenge_type
                and explicit_challenge_type.upper() == "SIGNATURE"
            ):
                self._handle_signature_challenge(one_time_token)
                return

            # Otherwise, get token status to determine challenge type
            token_status = self._get_token_status(one_time_token)
            challenge_type, found = self._find_required_challenge(token_status)

            if not found:
                die("No pending challenge found for this request")

            breakpoint()
            if challenge_type == "PIN":
                self._handle_pin_challenge(one_time_token)
            elif challenge_type == "SIGNATURE":
                self._handle_signature_challenge(one_time_token)
            elif challenge_type in ["SMS", "WHATSAPP", "VOICE"]:
                self._handle_otp_challenge(one_time_token, challenge_type.lower())
            else:
                die(f"Unsupported challenge type: {challenge_type}")

        except urllib.error.HTTPError as e:
            print(f"Failed to process authentication challenge: {e.code} - {e.reason}")
            raise

    def _handle_signature_challenge(self, one_time_token: str) -> None:
        """Handle signature verification challenge."""
        # Generate signature using the Signer class
        signature = self.signer.sca_challenge(one_time_token)

        # No need to make an additional request for signature challenge
        # The signature will be included in the header of the retried request
        headers = {"One-Time-Token": one_time_token, "X-Signature": signature}

        # Make a status check to verify the signature worked
        try:
            self._http_request("v1/one-time-token/status", "GET", headers)
        except urllib.error.HTTPError as e:
            die(f"Signature verification failed: {e.code} - {e.reason}")

    def _handle_pin_challenge(self, one_time_token: str) -> None:
        """Handle PIN verification challenge."""
        if not self.pin:
            self.pin = input("Enter your 4-digit PIN: ")

        headers = {"One-Time-Token": one_time_token}

        try:
            self._http_request(
                "v1/one-time-token/pin/verify", "POST", headers, {"pin": self.pin}
            )
            # Successfully verified
        except urllib.error.HTTPError as e:
            print(f"PIN verification failed: {e.code} - {e.reason}")
            self.pin = None
            die("PIN verification failed")

    def _handle_otp_challenge(self, one_time_token: str, challenge_type: str) -> None:
        """Handle OTP-based challenges (SMS, WhatsApp, Voice)."""
        # Trigger the challenge
        headers = {"One-Time-Token": one_time_token}

        try:
            # Trigger the challenge
            trigger_data = self._http_request(
                f"v1/one-time-token/{challenge_type}/trigger", "POST", headers
            ).data

            assert isinstance(trigger_data, dict)

            print(
                f"Challenge sent to {trigger_data.get('obfuscatedPhoneNo', 'your phone')}"
            )

            # Get OTP from user
            otp_code = input(
                f"Enter the one-time code sent to you via {challenge_type.upper()}: "
            )

            # Verify the challenge
            self._http_request(
                f"v1/one-time-token/{challenge_type}/verify",
                "POST",
                headers,
                {"otpCode": otp_code},
            )

        except urllib.error.HTTPError as e:
            print(f"Challenge verification failed: {e.code} - {e.reason}")
            die(f"{challenge_type.upper()} verification failed")

    def get_jose_signing_key(self) -> str:
        headers = {
            "authorization": f"Bearer {self.api_key}",
            "accept": "*/*",
            "user-agent": "curl/8.12.1",  # no joke, the test-api rejects anything ffs
        }
        url = "v1/auth/jose/response/public-keys?algorithm=RSA_OAEP_256&scope=PAYLOAD_ENCRYPTION"
        full_url = f"{BASE_URL}/{url}"
        req = urllib.request.Request(
            full_url,
            headers=headers,
            method="GET",
        )

        try:
            res = urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8")
            print(f"Error response body: {error_body}", file=sys.stderr)
            raise
        return json.loads(res.read())

    def post_user_pin(self, pin: str) -> dict[str, Any]:
        """Post user PIN using a JOSE payload.
        The pin must be a string of exactly 4 digits.
        """
        if not (pin.isdigit() and len(pin) == 4):
            msg = "PIN must be exactly 4 digits"
            raise ValueError(msg)

        # Get the JWE public key from Wise
        key_data = self.get_jose_signing_key()

        jose_cli = Path(__file__).parent.parent / "jose_cli"

        if not jose_cli.exists():
            die(f"jose_cli not found at {jose_cli}")

        plaintext = json.dumps(
            {
                "message": pin,
            }
        )
        print(f"Plaintext: {plaintext}")
        cmd = ["bun", "run", "index.ts", json.dumps(key_data), pin]

        res = subprocess.run(cmd, stdout=subprocess.PIPE, check=True, cwd=str(jose_cli))

        encrypted_pin = res.stdout.decode("utf-8").strip("\n")
        print(f"Encrypted pin: {encrypted_pin}")

        url = "v1/auth/jose/playground/jwe"
        headers = {
            "authorization": f"Bearer {self.api_key}",
            "content-type": "application/jose+json",
            "accept": "application/jose+json",
            "user-agent": "curl/8.12.1",
            "x-tw-jose-method": "jwe",
        }
        full_url = f"{BASE_URL}/{url}"
        req = urllib.request.Request(
            full_url,
            headers=headers,
            method="POST",
            data=encrypted_pin.encode(),
        )

        try:
            res = urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8")
            die(f"Error response body: {error_body}")

        if res.status_code == 409:
            msg = "PIN is already set. Please use the --wise-pin argument to provide your PIN."
            raise RuntimeError(msg)

        if res.status_code != 204:
            die(
                f"Unexpected response status: {res.data} \nstatus-code: {res.status_code}"
            )
        return res.data

    def get_business_profile(self) -> int:
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
        path = (
            f"/v1/profiles/{profile}/balance-statements/{balance.id}/statement.json"
            f"?currency={balance.currency}&intervalStart={start}T00:00:00.000Z"
            f"&intervalEnd={end}T23:59:59.999Z&type=COMPACT"
        )
        r = self.http_request(path)
        assert isinstance(r, dict)
        return r


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
    pin = os.environ.get("WISE_PIN")
    parser.add_argument(
        "--wise-pin",
        default=pin,
        help="Your 4-digit PIN for Wise, required for some 2FA challenges",
    )
    parser.add_argument(
        "--wise-test",
        action="store_true",
        help="Use the test API instead of the production API",
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

    wise_api_token = args.wise_api_token

    if args.wise_test:
        global BASE_URL  # noqa: PLW0603
        BASE_URL = "https://api.sandbox.transferwise.tech"
        wise_api_token = "f17ef8f9-5cbe-4732-b1a1-91aefd08fe91"  # noqa: S105

    client = WiseClient(
        wise_api_token, args.wise_private_key.encode("ascii"), pin=args.wise_pin
    )

    if not args.wise_pin:
        msg = "You must set WISE_PIN environment variable or use --wise-pin argument"
        raise ValueError(msg)

    client.post_user_pin(args.wise_pin)
    client.pin = args.wise_pin

    if not args.wise_profile:
        args.wise_profile = client.get_business_profile()
    balances = client.get_balances(args.wise_profile)
    statement_per_account = []
    for balance in balances:
        statements = client.get_balance_statements(
            args.wise_profile, balance, args.start, args.end
        )
        statement_per_account.append(statements)

    json.dump(statement_per_account, sys.stdout, indent=2)
