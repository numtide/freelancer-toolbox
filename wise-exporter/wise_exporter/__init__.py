#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import calendar
import contextlib
import json
import os
import shlex
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
import uuid  # <-- Import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone  # <-- Import timezone
from pathlib import Path
from typing import Any, NoReturn

# Use 'rsa' library for signing (compatibility with existing 2FA logic)
import rsa as rsa_signer_lib

# Use cryptography for key generation and DER export
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa as crypto_rsa

# --- Global Variables ---
BASE_URL = "https://api.transferwise.com"


# --- Helper Function for Key Generation ---
def generate_and_save_rsa_key_pair(
    private_pem_path: Path, public_pem_path: Path, key_size: int = 2048
) -> tuple[crypto_rsa.RSAPrivateKey, crypto_rsa.RSAPublicKey]:
    """Generates an RSA key pair using cryptography and saves them in PEM format."""
    print(f"Generating {key_size}-bit RSA key pair...")
    private_key = crypto_rsa.generate_private_key(
        public_exponent=65537,
        key_size=key_size,
    )
    public_key = private_key.public_key()

    # Serialize and save private key (PKCS8 format, PEM encoding)
    pem_private = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),  # IMPORTANT: Add password protection for production use
    )
    private_pem_path.parent.mkdir(
        parents=True, exist_ok=True
    )  # Ensure directory exists
    with open(private_pem_path, "wb") as f:
        f.write(pem_private)
    print(f"Private key (PKCS8 PEM) saved securely to: {private_pem_path}")
    print("!!! KEEP THIS PRIVATE KEY FILE SAFE AND SECRET !!!")

    # Serialize and save public key in PEM (SubjectPublicKeyInfo format) - for reference
    pem_public = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    public_pem_path.parent.mkdir(parents=True, exist_ok=True)  # Ensure directory exists
    with open(public_pem_path, "wb") as f:
        f.write(pem_public)
    print(f"Public key (PEM format for reference) saved to: {public_pem_path}")

    return private_key, public_key


# --- Signer Class (using the 'rsa' library for compatibility with existing code) ---
class Signer:
    """Handles signing of 2FA challenges using a PKCS1 private key."""

    def __init__(self, private_key_pkcs1_bytes: bytes) -> None:
        try:
            # The 'rsa' library typically expects PKCS1 format
            self.private_key = rsa_signer_lib.PrivateKey.load_pkcs1(
                private_key_pkcs1_bytes, "PEM"
            )
        except Exception as e:
            print(
                f"Error loading private key for signing (PKCS1 PEM format expected): {e}",
                file=sys.stderr,
            )
            print(
                "Ensure the provided --wise-private-key-path points to a valid PKCS1 PEM file.",
                file=sys.stderr,
            )
            msg = "Invalid private key format for signing."
            raise ValueError(msg) from e

    def sca_challenge(self, one_time_token: str) -> str:
        """Signs the one-time token for 2FA."""
        signed_token = rsa_signer_lib.sign(
            one_time_token.encode("ascii"), self.private_key, "SHA-256"
        )
        # Encode the signed message as friendly base64 format for HTTP headers.
        return base64.b64encode(signed_token).decode("ascii")


# --- Balance and WiseResult Classes (WiseResult Modified) ---
class Balance:
    """Represents a Wise balance account."""

    def __init__(self, balance_id: int, currency: str) -> None:
        self.id = balance_id
        self.currency = currency


@dataclass
class WiseResult:
    """Holds the result of an HTTP request."""

    status_code: int
    data: dict[str, Any] | list[dict[str, Any]] | None = None  # Parsed JSON data
    raw_data: bytes | None = None  # Raw response body
    headers: dict[str, str] | None = None  # Response headers


# --- WiseClient Class (Modified) ---
class WiseClient:
    """Client for interacting with the Wise API, handling auth, 2FA, JWE, etc."""

    def __init__(
        self,
        api_key: str,
        signing_private_key_bytes: bytes | None,  # For 2FA signing (PKCS1 PEM)
        client_private_key_path: str
        | Path
        | None,  # For response decryption (PKCS8 PEM)
        pin: str | None = None,
    ) -> None:
        self.api_key = api_key
        # Initialize signer only if signing key bytes are provided
        self.signer = (
            Signer(signing_private_key_bytes) if signing_private_key_bytes else None
        )
        self.pin: str | None = pin
        # Store and validate client private key path for decryption
        self.client_private_key_path: Path | None = (
            Path(client_private_key_path) if client_private_key_path else None
        )
        if self.client_private_key_path and not self.client_private_key_path.is_file():
            # This is only a warning at init time; becomes an error if decryption is attempted
            print(
                f"Warning: Client private key file for decryption specified but not found: {self.client_private_key_path}",
                file=sys.stderr,
            )

    def _http_request(
        self,
        url: str,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        data: bytes | dict[str, Any] | None = None,  # Accept dict or bytes
        is_json_data: bool = True,  # Flag to indicate if dict data should be JSON encoded
        content_type: str | None = "application/json",  # Default Content-Type for JSON
        expect_raw_response: bool = False,  # Flag to expect raw bytes response (e.g., JWE)
    ) -> WiseResult:
        """Internal helper to perform HTTP requests and parse responses."""
        if headers is None:
            headers = {}

        # Prepare body (handle dict or bytes)
        body: bytes | None = None
        request_headers = headers.copy()  # Work on a copy

        if data is not None:
            if is_json_data and isinstance(data, dict):
                body = json.dumps(data).encode("utf-8")  # Use utf-8 generally
                if "Content-Type" not in request_headers:
                    request_headers["Content-Type"] = content_type or "application/json"
            elif isinstance(data, bytes):
                body = data  # Use raw bytes directly
                if "Content-Type" not in request_headers and content_type:
                    # Set Content-Type if provided and not already set for raw bytes
                    request_headers["Content-Type"] = content_type
            else:  # Fallback for other types
                body = str(data).encode("utf-8")
                if "Content-Type" not in request_headers:
                    request_headers["Content-Type"] = content_type or "text/plain"

        req = urllib.request.Request(
            f"{BASE_URL}/{url}", headers=request_headers, method=method, data=body
        )
        try:
            # Added unverified context option based on original code
            context = ssl._create_unverified_context()
            resp = urllib.request.urlopen(req, context=context)
            status_code = resp.getcode()
            response_headers = dict(resp.info())  # Get response headers as dict
            response_body_bytes = resp.read()

            # Handle response based on expect_raw_response flag
            parsed_json_data = None
            if not expect_raw_response and status_code != 204 and response_body_bytes:
                # Try decoding as JSON only if raw is not expected and there's content
                try:
                    content_type_header = response_headers.get(
                        "content-type", ""
                    ).lower()
                    if "application/json" in content_type_header:
                        parsed_json_data = json.loads(response_body_bytes)
                    else:
                        # Log if non-JSON received when JSON might have been expected
                        print(
                            f"Warning: Received non-JSON response (Content-Type: {content_type_header}, Status: {status_code})",
                            file=sys.stderr,
                        )
                except json.JSONDecodeError:
                    # Log if JSON parsing fails
                    print(
                        f"Warning: Could not decode response as JSON (Status: {status_code}).",
                        file=sys.stderr,
                    )
                    # Keep raw_data populated

            # Return WiseResult containing status, headers, raw bytes, and parsed JSON (if applicable)
            return WiseResult(
                status_code=status_code,
                data=parsed_json_data,  # Will be None if expect_raw_response or parsing failed
                raw_data=response_body_bytes,  # Always populate raw bytes
                headers=response_headers,
            )

        except urllib.error.HTTPError:
            # Re-raise the HTTPError to be handled by the calling function (http_request)
            raise
        except Exception as e:
            # Catch other potential errors during request/response handling
            print(
                f"Unexpected error during HTTP request processing: {e}", file=sys.stderr
            )
            msg = f"HTTP request failed unexpectedly: {e}"
            raise RuntimeError(msg) from e

    def http_request(
        self,
        path: str,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        data: dict[str, Any] | bytes | None = None,  # Allow bytes for JWE
        is_json_data: bool = True,  # Default to assuming dict data is JSON
        content_type: str | None = "application/json",  # Default content type for JSON
        expect_raw_response: bool = False,  # Flag to bypass JSON parsing
    ) -> dict[str, Any] | list[dict[str, Any]] | bytes:  # Can now return bytes
        """Performs an HTTP request, handling auth, 2FA retries, and response parsing."""
        if headers is None:
            headers = {}
        request_headers = headers.copy()  # Work on copy
        request_headers["Authorization"] = f"Bearer {self.api_key}"
        request_headers["User-Agent"] = (
            "Numtide wise importer"  # Keep original user agent
        )

        try:
            result = self._http_request(
                path,
                method,
                request_headers,
                data,
                is_json_data,
                content_type,
                expect_raw_response,
            )

            # Return data based on expectations and availability
            if expect_raw_response:
                # If raw response was requested, return it (even if empty)
                return result.raw_data if result.raw_data is not None else b""
            if result.data is not None:
                # If JSON was expected and parsed successfully, return it
                return result.data
            if result.status_code == 204:
                # Represent No Content (204) as an empty dictionary
                return {}
            # If raw wasn't expected, but JSON parsing failed or was empty, return raw data as fallback
            print(
                f"Warning: Returning raw response data due to lack of parsed JSON (Status: {result.status_code}).",
                file=sys.stderr,
            )
            return result.raw_data if result.raw_data is not None else b""

        except urllib.error.HTTPError as e:
            breakpoint()
            # --- 2FA Handling ---
            if e.code == 403 and "x-2fa-approval" in e.headers:
                if not self.signer:
                    die(
                        "Received 2FA challenge, but no signing private key provided (--wise-private-key-path)."
                    )

                x_2fa_approval = e.headers["x-2fa-approval"].strip().split(" ")
                one_time_token = x_2fa_approval[0]
                explicit_challenge_type = (
                    x_2fa_approval[1] if len(x_2fa_approval) >= 2 else None
                )

                # Prepare headers for the retry attempt
                retry_headers = request_headers.copy()
                # Handle_2fa_challenge might add 'X-Signature' and 'One-Time-Token' to retry_headers
                self._handle_2fa_challenge(
                    one_time_token, explicit_challenge_type, retry_headers
                )

                print("Retrying request after handling 2FA challenge...")
                # Retry the request with potentially modified headers
                retry_result = self._http_request(
                    path,
                    method,
                    retry_headers,
                    data,
                    is_json_data,
                    content_type,
                    expect_raw_response,
                )

                # Handle retry result similarly to original result
                if expect_raw_response:
                    return (
                        retry_result.raw_data
                        if retry_result.raw_data is not None
                        else b""
                    )
                if retry_result.data is not None:
                    return retry_result.data
                if retry_result.status_code == 204:
                    return {}
                print(
                    f"Warning: Returning raw response data from retry (Status: {retry_result.status_code}).",
                    file=sys.stderr,
                )
                return (
                    retry_result.raw_data if retry_result.raw_data is not None else b""
                )
            # --- Handle other HTTP errors ---
            error_body = f"Could not read error body (Status: {e.code})."
            error_content_type = e.headers.get("content-type", "unknown")
            try:
                error_body_bytes = e.read()
                # Try decoding, fallback to hex representation if needed
                try:
                    error_body = error_body_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    error_body = error_body_bytes.hex()
            except Exception as read_err:
                error_body = f"Could not read error body (Status: {e.code}). Read Error: {read_err}"

            print(f"HTTP Error {e.code}: {e.reason}", file=sys.stderr)
            print(f"Error Content-Type: {error_content_type}", file=sys.stderr)
            print(f"Error Response Body:\n{error_body}", file=sys.stderr)

            if e.code == 400:
                die("HTTP 400 Bad Request. Check request parameters and payload.")
            elif e.code == 401:
                die("HTTP 401 Unauthorized. Check API token validity.")
            elif e.code == 403:
                die(
                    "HTTP 403 Forbidden. Check permissions or potential 2FA requirements not handled by signature/PIN/OTP."
                )
            elif e.code == 404:
                msg = f"Not Found URL: {e.url}"
                raise RuntimeError(msg) from e
            elif e.code == 409:
                # Conflict: Let caller handle specific 409 meanings (like PIN already set)
                print("HTTP 409 Conflict detected.")
                raise  # Re-raise for specific handling
            elif e.code == 429:
                die("HTTP 429 Too Many Requests. Rate limit exceeded.")
            elif e.code >= 500:
                die(f"HTTP {e.code} Server Error. Please try again later.")
            else:
                # Re-raise other unexpected HTTP errors after printing
                raise

    # --- 2FA Handling Methods (Modified slightly to update retry_headers) ---
    def _get_token_status(self, one_time_token: str) -> dict[str, Any]:
        """Gets the status of a one-time token."""
        print(f"Getting status for One-Time-Token: {one_time_token[:8]}...")
        headers = {
            "Authorization": f"Bearer {self.api_key}",  # Auth usually needed
            "One-Time-Token": one_time_token,
        }
        # Use _http_request directly to get WiseResult including potential errors
        result = self._http_request(
            "v1/one-time-token/status", "GET", headers, expect_raw_response=False
        )
        if result.status_code >= 400 or result.data is None:
            raw_info = (
                result.raw_data.decode("utf-8", errors="ignore")
                if result.raw_data
                else "N/A"
            )
            die(
                f"Failed to get token status (HTTP {result.status_code}). Response: {raw_info}"
            )
        assert isinstance(result.data, dict)
        print(f"Token status received: {result.data}")
        return result.data

    def _find_required_challenge(
        self, token_status: dict[str, Any]
    ) -> tuple[str | None, bool]:
        """Finds the required challenge type from token status."""
        challenges = token_status.get("oneTimeTokenProperties", {}).get(
            "challenges", []
        )
        for challenge in challenges:
            if challenge.get("required") and not challenge.get("passed"):
                # Prefer primary challenge type, fall back to main challenge type
                primary_challenge = challenge.get("primaryChallenge", {})
                challenge_type = primary_challenge.get("type") or challenge.get("type")
                print(f"Found required challenge: {challenge_type}")
                return challenge_type, True
        print("No pending required challenge found in token status.")
        return None, False

    def _handle_2fa_challenge(
        self,
        one_time_token: str,
        explicit_challenge_type: str | None,
        retry_headers: dict[str, str],
    ) -> None:
        """Handles 2FA challenge by determining type and calling appropriate handler. Updates retry_headers if needed."""
        try:
            challenge_type_to_handle = explicit_challenge_type
            if challenge_type_to_handle:
                challenge_type_to_handle = challenge_type_to_handle.upper()  # Normalize
                print(
                    f"Handling explicit 2FA challenge type from header: {challenge_type_to_handle}"
                )
            else:
                token_status = self._get_token_status(one_time_token)
                challenge_type_from_status, found = self._find_required_challenge(
                    token_status
                )
                if not found:
                    # Check if maybe it *was* passed already, log status
                    print(f"Token status details: {token_status}", file=sys.stderr)
                    die("No pending required challenge found for this request.")
                challenge_type_to_handle = challenge_type_from_status

            if not challenge_type_to_handle:
                die("Could not determine required 2FA challenge type.")

            print(f"Processing 2FA challenge: {challenge_type_to_handle}")

            # Call specific handlers
            if challenge_type_to_handle == "PIN":
                self._handle_pin_challenge(one_time_token)
                # PIN challenge is verified separately, no header needed for retry
            elif challenge_type_to_handle == "SIGNATURE":
                self._handle_signature_challenge(one_time_token, retry_headers)
                # Signature is added to retry_headers
            elif challenge_type_to_handle in ["SMS", "WHATSAPP", "VOICE"]:
                self._handle_otp_challenge(
                    one_time_token, challenge_type_to_handle.lower()
                )
                # OTP challenge is verified separately, no header needed for retry
            else:
                die(
                    f"Unsupported challenge type encountered: {challenge_type_to_handle}"
                )

        except urllib.error.HTTPError as e:
            # Catch errors during the challenge verification itself
            error_body = "Could not read error body."
            with contextlib.suppress(Exception):
                error_body = e.read().decode("utf-8", errors="ignore")
            print(
                f"Failed to process authentication challenge: {e.code} - {e.reason}\n{error_body}",
                file=sys.stderr,
            )
            raise  # Re-raise to indicate overall request failure

    def _handle_signature_challenge(
        self, one_time_token: str, retry_headers: dict[str, str]
    ) -> None:
        """Handles signature challenge by signing the token and adding headers for retry."""
        if not self.signer:
            die(
                "Signature challenge received, but no signing private key provided (--wise-private-key-path)."
            )
        print("Handling SIGNATURE challenge...")
        # Generate signature using the Signer class
        signature = self.signer.sca_challenge(one_time_token)
        # Add One-Time-Token and X-Signature to the headers for the *retry* attempt
        retry_headers["One-Time-Token"] = one_time_token
        retry_headers["X-Signature"] = signature
        print(
            "Signature generated and added to retry headers ('One-Time-Token', 'X-Signature')."
        )
        # Optional: Could make a status check here to *verify* the signature worked before retry, but adds complexity.

    def _handle_pin_challenge(self, one_time_token: str) -> None:
        """Handles PIN challenge by prompting user and verifying via API."""
        print("Handling PIN challenge...")
        if not self.pin:
            self.pin = input("Enter your 4-digit PIN: ").strip()
            if not (self.pin.isdigit() and len(self.pin) == 4):
                die("Invalid PIN format. Must be 4 digits.")

        headers = {
            "Authorization": f"Bearer {self.api_key}",  # Need auth for this endpoint
            "One-Time-Token": one_time_token,
            "Content-Type": "application/json",
        }
        try:
            print(f"Verifying PIN (token: {one_time_token[:8]}...)")
            # Use _http_request to check status code directly
            result = self._http_request(
                "v1/one-time-token/pin/verify",
                "POST",
                headers,
                data={"pin": self.pin},  # Send as JSON data
                is_json_data=True,
                expect_raw_response=False,  # Expect JSON response (or error)
            )
            if result.status_code >= 400:
                # If _http_request didn't raise, check status here
                error_info = result.data or result.raw_data.decode(
                    "utf-8", errors="ignore"
                )
                die(
                    f"PIN verification failed (HTTP {result.status_code}): {error_info}"
                )

            print("PIN verified successfully.")
            # No need to modify retry headers, the token status is updated server-side
        except urllib.error.HTTPError as e:
            # This handles cases where _http_request re-raises
            error_body = "Could not read error body."
            with contextlib.suppress(Exception):
                error_body = e.read().decode("utf-8", errors="ignore")
            print(
                f"PIN verification API call failed: {e.code} - {e.reason}\n{error_body}",
                file=sys.stderr,
            )
            self.pin = None  # Clear potentially wrong PIN
            die("PIN verification failed")
        except Exception as e:
            print(
                f"An unexpected error occurred during PIN verification: {e}",
                file=sys.stderr,
            )
            die("PIN verification failed")

    def _handle_otp_challenge(self, one_time_token: str, challenge_type: str) -> None:
        """Handles OTP challenges (SMS, WhatsApp, Voice) by triggering, prompting, and verifying."""
        print(f"Handling {challenge_type.upper()} challenge...")
        headers = {
            "Authorization": f"Bearer {self.api_key}",  # Need auth
            "One-Time-Token": one_time_token,
            "Content-Type": "application/json",  # Usually needed even for POST trigger
        }
        try:
            # 1. Trigger the challenge
            print(
                f"Triggering {challenge_type.upper()} challenge (token: {one_time_token[:8]}...)..."
            )
            trigger_result = self._http_request(
                f"v1/one-time-token/{challenge_type}/trigger",
                "POST",
                headers,
                is_json_data=False,  # Trigger might not need body
                expect_raw_response=False,  # Expect JSON response
            )
            if trigger_result.status_code >= 400 or trigger_result.data is None:
                error_info = trigger_result.data or (
                    trigger_result.raw_data.decode("utf-8", errors="ignore")
                    if trigger_result.raw_data
                    else "N/A"
                )
                die(
                    f"Failed to trigger {challenge_type.upper()} challenge (HTTP {trigger_result.status_code}): {error_info}"
                )

            trigger_data = trigger_result.data
            assert isinstance(trigger_data, dict)
            print(
                f"Challenge sent to {trigger_data.get('obfuscatedPhoneNo', 'your configured device')}"
            )

            # 2. Get OTP from user
            otp_code = input(
                f"Enter the one-time code sent via {challenge_type.upper()}: "
            ).strip()
            if not otp_code.isdigit():
                die("Invalid OTP code format. Should contain only digits.")

            # 3. Verify the challenge
            print(
                f"Verifying {challenge_type.upper()} code (token: {one_time_token[:8]}...)..."
            )
            verify_result = self._http_request(
                f"v1/one-time-token/{challenge_type}/verify",
                "POST",
                headers,  # Use same headers (token needed)
                data={"otpCode": otp_code},
                is_json_data=True,
                expect_raw_response=False,  # Expect JSON response or error
            )
            if verify_result.status_code >= 400:
                error_info = verify_result.data or (
                    verify_result.raw_data.decode("utf-8", errors="ignore")
                    if verify_result.raw_data
                    else "N/A"
                )
                die(
                    f"{challenge_type.upper()} verification failed (HTTP {verify_result.status_code}): {error_info}"
                )

            print(f"{challenge_type.upper()} verified successfully.")
            # No need to modify retry headers, token status updated server-side

        except urllib.error.HTTPError as e:
            # Handles cases where _http_request re-raises (e.g., from trigger/verify)
            error_body = "Could not read error body."
            with contextlib.suppress(Exception):
                error_body = e.read().decode("utf-8", errors="ignore")
            print(
                f"{challenge_type.upper()} challenge API call failed: {e.code} - {e.reason}\n{error_body}",
                file=sys.stderr,
            )
            die(f"{challenge_type.upper()} verification failed")
        except Exception as e:
            print(
                f"An unexpected error occurred during {challenge_type.upper()} challenge: {e}",
                file=sys.stderr,
            )
            die(f"{challenge_type.upper()} verification failed")

    # --- NEW Method: Upload Client Public Key ---
    def upload_client_public_key(
        self, public_key: crypto_rsa.RSAPublicKey, validity_years: int = 1
    ) -> dict[str, Any] | None:
        """Uploads the client's public key (for response encryption) to Wise."""
        print("\nPreparing to upload client public key for response encryption...")

        # 1. Convert public key to DER format
        try:
            der_public = public_key.public_bytes(
                encoding=serialization.Encoding.DER,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        except Exception as e:
            print(f"Error converting public key to DER format: {e}", file=sys.stderr)
            return None

        # 2. Base64 encode the DER key
        base64_der_public = base64.b64encode(der_public).decode("utf-8")
        print("Public key successfully converted to DER and Base64 encoded.")

        # 3. Prepare payload data
        key_id = str(uuid.uuid4())
        now_utc = datetime.now(UTC)
        valid_from = now_utc.strftime("%Y-%m-%d %H:%M:%S")
        valid_till = (now_utc + timedelta(days=int(365.25 * validity_years))).strftime(
            "%Y-%m-%d %H:%M:%S"
        )  # Adjust for leap year avg

        payload = {
            "keyId": key_id,
            "validFrom": valid_from,
            "validTill": valid_till,
            "scope": "PAYLOAD_ENCRYPTION",  # Crucial scope for response encryption
            "publicKeyMaterial": {
                "algorithm": "RSA_OAEP_256",  # Algorithm server will use *with this key*
                "keyMaterial": base64_der_public,
            },
        }
        print(
            f"Uploading key with ID: {key_id} (Valid: {valid_from} to {valid_till} UTC)"
        )
        # Avoid printing full key to log
        print(
            f"Payload (keyMaterial truncated): { {**payload, 'publicKeyMaterial': {**payload['publicKeyMaterial'], 'keyMaterial': base64_der_public[:30] + '...'}} }"
        )

        # 4. Make the API request using http_request for consistency
        upload_path = "/v1/auth/jose/request/public-keys"
        try:
            # Expect a JSON response on success (201 Created)
            response_data = self.http_request(
                path=upload_path,
                method="POST",
                data=payload,  # http_request handles JSON encoding
                is_json_data=True,
                content_type="application/json",  # Explicitly set
                expect_raw_response=False,  # We want the parsed JSON response
            )
            # Check type, as http_request might return bytes on non-JSON success? Unlikely for POST 201.
            if not isinstance(response_data, dict):
                print(
                    f"Warning: Expected JSON dictionary response for key upload, but got {type(response_data)}.",
                    file=sys.stderr,
                )
                print(f"Raw response: {response_data}", file=sys.stderr)
                die("Key upload response format was unexpected.")

            print("\nKey Upload Successful!")
            print(f"API Response:\n{json.dumps(response_data, indent=2)}")
            return response_data
        except urllib.error.HTTPError:
            # http_request already prints details for non-2FA errors
            print("\nKey Upload Failed (HTTP Error).", file=sys.stderr)
            return None  # Indicate failure
        except Exception as e:
            # Catch other errors during http_request or response processing
            print(
                f"\nAn unexpected error occurred during key upload: {e}",
                file=sys.stderr,
            )
            return None

    # --- Existing Methods (Modified get_jose_signing_key, post_user_pin) ---
    def get_jose_signing_key(self) -> dict[str, Any]:  # Renamed for clarity
        """Gets the Wise *server* public key details required for *request* encryption."""
        print(
            "Fetching Wise server public key for request encryption (RSA_OAEP_256)..."
        )
        path = "v1/auth/jose/response/public-keys?algorithm=RSA_OAEP_256&scope=PAYLOAD_ENCRYPTION"
        try:
            # Use http_request which handles auth, base URL, and expects JSON list
            key_info_list = self.http_request(
                path=path,
                method="GET",
                content_type="*/*",  # Mimic curl accept if needed, though usually ignored for GET
                expect_raw_response=False,  # Expect JSON list
            )

            if not isinstance(key_info_list, list) or not key_info_list:
                die(
                    f"Expected a non-empty list of keys from {path}, but got: {key_info_list}"
                )

            # Assuming we take the first key matching the criteria
            # A production system might filter by keyId or check validity period more carefully
            server_key_data = key_info_list[0]
            print(f"Received server key data: {server_key_data}")

            # Basic validation of received key data structure
            if (
                not isinstance(server_key_data, dict)
                or "keyMaterial" not in server_key_data
                or not isinstance(server_key_data["keyMaterial"], dict)
                or server_key_data["keyMaterial"].get("algorithm") != "RSA_OAEP_256"
                or not server_key_data["keyMaterial"].get("keyMaterial")
                or server_key_data.get("scope") != "PAYLOAD_ENCRYPTION"
            ):
                die(
                    f"Server key data received has unexpected format or values: {server_key_data}"
                )

            return server_key_data  # Return the first valid key dictionary

        except Exception as e:
            # Catch errors from http_request or validation
            print(
                f"Failed to fetch or validate Wise server public key: {e}",
                file=sys.stderr,
            )
            raise  # Re-raise to stop execution if key cannot be obtained

    def post_user_pin(self, pin: str, bun_script_path: Path) -> dict[str, Any] | None:
        """Sets/updates PIN via JWE: Encrypts request, sends, receives JWE response, decrypts response."""
        if not (pin.isdigit() and len(pin) == 4):
            msg = "PIN must be exactly 4 digits"
            raise ValueError(msg)

        # --- Encryption Step ---
        print("\n--- Encrypting PIN Request ---")
        # 1. Get server's public key
        server_key_data = self.get_jose_signing_key()
        # 2. Prepare plaintext (using playground format)
        plaintext_payload = json.dumps({"message": pin})
        print(f"Plaintext for JWE encryption: {plaintext_payload}")

        # 3. Call Bun script to ENCRYPT
        bun_executable = "bun"
        script_file = "encrypt.ts"  # Assuming this name in the target dir
        encrypt_cmd = [
            bun_executable,
            "run",
            script_file,
            "encrypt",  # Encrypt command
            json.dumps(server_key_data),  # Server key JSON
            plaintext_payload,  # Plaintext
        ]
        print(
            f"Running encryption command: {' '.join(shlex.quote(c) for c in encrypt_cmd)}"
        )
        try:
            if not bun_script_path.is_dir():
                die(f"Bun script path '{bun_script_path}' is not a directory.")

            result = subprocess.run(
                encrypt_cmd,
                capture_output=True,
                check=True,
                text=True,
                cwd=str(bun_script_path),
            )
            # Extract JWE string from the last line of stdout, ignoring logs on stderr/earlier stdout
            jwe_request_string = (
                result.stdout.strip().splitlines()[-1].strip() if result.stdout else ""
            )

            if not jwe_request_string:
                print(f"Bun script stdout:\n{result.stdout}", file=sys.stderr)
                print(f"Bun script stderr:\n{result.stderr}", file=sys.stderr)
                die("Failed to extract JWE request string from bun script output.")
            print(f"Successfully encrypted PIN request: {jwe_request_string[:30]}...")

        except FileNotFoundError:
            die(f"Error: '{bun_executable}' command not found. Is Bun installed?")
        except subprocess.CalledProcessError as e:
            print(
                f"Error running bun encryption script (Exit Code: {e.returncode}):",
                file=sys.stderr,
            )
            print(
                f"Command: {' '.join(shlex.quote(c) for c in e.cmd)}", file=sys.stderr
            )
            print(f"Stdout:\n{e.stdout}", file=sys.stderr)
            print(f"Stderr:\n{e.stderr}", file=sys.stderr)
            die("JWE encryption failed.")
        except Exception as e:
            die(f"An unexpected error occurred during JWE encryption: {e}")

        # --- API Call Step ---
        print("\n--- Sending Encrypted PIN to API ---")
        # target_path = "/v1/user/pin" # Use if testing against actual endpoint
        target_path = "/v1/auth/jose/playground/jwe"  # Using playground
        print(f"Target endpoint: {target_path}")
        headers = {
            "Accept": "application/jose+json",  # IMPORTANT: Request encrypted JWE response
            "X-Tw-Jose-Method": "jwe",
            # Content-Type will be set automatically for bytes data
        }
        jwe_response_string = ""  # Initialize
        try:
            # Expecting raw bytes back (the JWE response string)
            response_body = self.http_request(
                path=target_path,
                method="POST",
                headers=headers,
                data=jwe_request_string.encode("utf-8"),  # Send JWE request as bytes
                is_json_data=False,  # Data is not dict->JSON
                content_type="application/jose+json",  # Set specific content type
                expect_raw_response=True,  # <-- Tell http_request to return raw bytes
            )

            # Check if we got bytes back as expected
            if not isinstance(response_body, bytes):
                # This might happen for 204 No Content (actual endpoint) or unexpected JSON errors
                if (
                    target_path == "/v1/user/pin" and not response_body
                ):  # Check if empty (like 204)
                    print(
                        "Received success status (likely 204 No Content) from /v1/user/pin."
                    )
                    return {}  # Indicate success without needing decryption
                # Got something other than bytes when bytes were expected
                print(
                    f"Warning: Expected raw JWE response bytes but received type: {type(response_body)}",
                    file=sys.stderr,
                )
                try:
                    # Try to print if it decodes as text (e.g., error message)
                    print(
                        f"Response Data (non-JWE):\n{response_body.decode('utf-8', errors='ignore')}",
                        file=sys.stderr,
                    )
                except AttributeError:
                    # If it's not bytes (e.g., dict from http_request fallback), print it
                    print(f"Response Data (non-JWE):\n{response_body}", file=sys.stderr)
                die("Received unexpected non-JWE response when JWE was expected.")

            # Decode the raw JWE response string
            jwe_response_string = response_body.decode("utf-8").strip()
            if not jwe_response_string:
                die("Received empty response body when JWE response was expected.")
            print(f"Received JWE response: {jwe_response_string[:30]}...")

        except urllib.error.HTTPError as e:
            # http_request already prints details, handle specific logical cases
            if e.code == 409 and target_path == "/v1/user/pin":
                print("PIN has already been created (HTTP 409).", file=sys.stderr)
                # Indicate PIN already exists, not an error in *this* operation attempt
                return None
            # For other errors, http_request will print details and likely raise/die
            # If it didn't die, ensure we exit here
            die(
                f"PIN submission failed during API call (HTTP {e.code}). See logs above for details."
            )
        except Exception as e:
            # Catch errors from http_request response handling
            die(f"An unexpected error occurred during PIN submission API call: {e}")

        # --- Decryption Step ---
        print("\n--- Decrypting API Response ---")
        if not self.client_private_key_path:
            die(
                "Client private key path (--client-private-key-path) is required to decrypt the JWE response."
            )
        if not self.client_private_key_path.is_file():
            die(
                f"Client private key file for decryption not found at: {self.client_private_key_path}"
            )

        # 4. Call Bun script to DECRYPT
        decrypt_cmd = [
            bun_executable,
            "run",
            script_file,
            "decrypt",  # Decrypt command
            jwe_response_string,  # The JWE received from API
            str(self.client_private_key_path),  # Path to client's PKCS8 private key
        ]
        print(
            f"Running decryption command: {' '.join(shlex.quote(c) for c in decrypt_cmd)}"
        )
        try:
            result = subprocess.run(
                decrypt_cmd,
                capture_output=True,
                check=True,
                text=True,
                cwd=str(bun_script_path),
            )
            # Extract decrypted plaintext (expecting it on the last line of stdout)
            decrypted_json_string = (
                result.stdout.strip().splitlines()[-1].strip() if result.stdout else ""
            )

            if not decrypted_json_string:
                print(f"Bun script stdout:\n{result.stdout}", file=sys.stderr)
                print(f"Bun script stderr:\n{result.stderr}", file=sys.stderr)
                die("Failed to extract decrypted plaintext from bun script output.")
            print("Successfully decrypted response.")

            # 5. Parse the decrypted JSON
            decrypted_data = json.loads(decrypted_json_string)
            print(f"Decrypted Response Data:\n{json.dumps(decrypted_data, indent=2)}")
            return decrypted_data

        except FileNotFoundError:
            die(f"Error: '{bun_executable}' command not found.")
        except subprocess.CalledProcessError as e:
            print(
                f"Error running bun decryption script (Exit Code: {e.returncode}):",
                file=sys.stderr,
            )
            print(
                f"Command: {' '.join(shlex.quote(c) for c in e.cmd)}", file=sys.stderr
            )
            print(f"Stdout:\n{e.stdout}", file=sys.stderr)
            print(f"Stderr:\n{e.stderr}", file=sys.stderr)
            die("JWE decryption failed.")
        except json.JSONDecodeError as e:
            print(f"Failed to parse decrypted text as JSON: {e}", file=sys.stderr)
            print(f"Raw decrypted text:\n{decrypted_json_string}", file=sys.stderr)
            die("Decrypted response was not valid JSON.")
        except Exception as e:
            die(f"An unexpected error occurred during JWE decryption: {e}")

    # --- Other existing methods (Unchanged logic, check profile/balance/statements) ---
    def get_business_profile(self) -> int:
        """Finds the business profile ID, falling back to personal if necessary."""
        print("Fetching user profiles...")
        r = self.http_request("/v2/profiles")  # Expects JSON list
        if not isinstance(r, list):
            die(f"Expected a list of profiles, but got: {type(r)}")

        business_profiles = [p["id"] for p in r if p.get("type") == "BUSINESS"]
        personal_profiles = [p["id"] for p in r if p.get("type") == "PERSONAL"]

        if len(business_profiles) == 1:
            print(f"Using business profile ID: {business_profiles[0]}")
            return business_profiles[0]
        if len(business_profiles) > 1:
            profile_ids_str = ", ".join(map(str, business_profiles))
            die(
                f"Found multiple business profiles: {profile_ids_str}.\nSelect one by setting the WISE_PROFILE environment variable."
            )
            return None
        if len(personal_profiles) >= 1:
            # No business profiles, use the first personal profile found
            print(
                f"No business profile found. Using first personal profile ID: {personal_profiles[0]}",
                file=sys.stderr,
            )
            return personal_profiles[0]
        die("No business or personal profiles found for this API token.")
        return None

    def get_balances(self, profile_id: int) -> list[Balance]:
        """Gets the standard balances for a given profile ID."""
        print(f"Fetching balances for profile ID: {profile_id}...")
        r = self.http_request(
            f"/v4/profiles/{profile_id}/balances?types=STANDARD"
        )  # Expects JSON list
        if not isinstance(r, list):
            die(f"Expected a list of balances, but got: {type(r)}")
        balances = [
            Balance(a["id"], a["currency"]) for a in r if "id" in a and "currency" in a
        ]
        if not balances:
            print(
                f"Warning: No standard balances found for profile {profile_id}.",
                file=sys.stderr,
            )
        return balances

    def get_balance_statements(
        self, profile_id: int, balance: Balance, start_date: str, end_date: str
    ) -> dict[str, Any]:
        """Gets the statement for a specific balance and date range."""
        print(
            f"Fetching statement for {balance.currency} (ID: {balance.id}) from {start_date} to {end_date}..."
        )
        # Ensure dates are in ISO format with time and Z for UTC
        start_iso = f"{start_date}T00:00:00.000Z"
        end_iso = f"{end_date}T23:59:59.999Z"
        path = (
            f"/v1/profiles/{profile_id}/balance-statements/{balance.id}/statement.json"
            f"?currency={balance.currency}&intervalStart={start_iso}"
            f"&intervalEnd={end_iso}&type=COMPACT"
        )
        r = self.http_request(path)  # Expects JSON dict
        if not isinstance(r, dict):
            die(f"Expected a dictionary for the statement response, but got: {type(r)}")
        print(f"Successfully fetched statement for {balance.currency}.")
        return r


# --- Utility and Argument Parsing (Modified) ---
def die(msg: str) -> NoReturn:
    """Prints an error message to stderr and exits with status 1."""
    print(f"Error: {msg}", file=sys.stderr)
    sys.exit(1)


def parse_args() -> argparse.Namespace:
    """Parses command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Wise API client for fetching statements, managing keys, and setting PIN.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,  # Show defaults
    )

    # API Credentials
    api_token = os.environ.get("WISE_API_TOKEN")
    parser.add_argument(
        "--wise-api-token",
        default=api_token,
        required=api_token is None,
        help="Wise API token. (Env: WISE_API_TOKEN)",
    )
    # Key for *Signing* 2FA challenges (expects PKCS1 PEM format)
    signing_key_path_env = os.environ.get("WISE_PRIVATE_KEY_PATH")
    parser.add_argument(
        "--wise-private-key-path",  # Renamed for clarity (signing key)
        default=signing_key_path_env,
        help="Path to your *signing* private key PEM file (PKCS1 format) for 2FA signature challenges. "
        "Generate with: openssl genrsa -out signing_private_pkcs1.pem 2048 (Env: WISE_PRIVATE_KEY_PATH)",
    )
    # Key for *Decrypting* API responses (expects PKCS8 PEM format)
    client_decrypt_key_path_env = os.environ.get("WISE_CLIENT_PRIVATE_KEY_PATH", ".")
    parser.add_argument(
        "--client-private-key-path",
        default=client_decrypt_key_path_env,
        help="Path to your *client* private key PEM file (PKCS8 format, generated by --generate-and-upload-key) "
        "needed for decrypting encrypted API responses. (Env: WISE_CLIENT_PRIVATE_KEY_PATH)",
    )

    # Profile and PIN
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
        help="Profile ID to use. If omitted, attempts to find business or personal profile. (Env: WISE_PROFILE)",
    )
    pin = os.environ.get("WISE_PIN")
    parser.add_argument(
        "--wise-pin",
        default=pin,
        help="Your 4-digit PIN for Wise, used for --set-pin or potential 2FA PIN challenges. (Env: WISE_PIN)",
    )

    # Environment Selection
    parser.add_argument(
        "--wise-test",
        action="store_true",
        help="Use the Wise Sandbox API (api.sandbox.transferwise.tech).",
    )

    # Actions Group (Mutually Exclusive)
    action_group = parser.add_mutually_exclusive_group()
    action_group.add_argument(
        "--generate-and-upload-key",
        action="store_true",
        help="Generate a new client RSA key pair (for response decryption), save it, and upload public key to Wise.",
    )
    action_group.add_argument(
        "--set-pin",
        action="store_true",
        help="Encrypt and submit the PIN provided via --wise-pin using JWE request/response.",
    )


    # JWE Script Location
    default_bun_dir = Path(__file__).parent / "bun-jwe-encrypt"  # Assumes subdir
    parser.add_argument(
        "--bun-script-dir",
        default=str(default_bun_dir),
        help="Path to the directory containing the 'encrypt.ts' Bun script.",
    )

    # Statement Fetching Options
    statement_group = parser.add_argument_group("Statement Fetching Options")
    statement_group.add_argument(
        "--start",
        help="Start date for statements in YYYY-MM-DD format.",
    )
    statement_group.add_argument(
        "--end",
        help="End date for statements in YYYY-MM-DD format.",
    )
    statement_group.add_argument(
        "--month",
        type=int,
        choices=range(1, 13),
        help="Month (1-12) to generate report for (conflicts with --start/--end).",
    )
    statement_group.add_argument(
        "--year",
        type=int,
        help="Year for --month (defaults to current year).",
    )

    args = parser.parse_args()

    # --- Validate Arguments ---

    # Ensure keys exist if needed for the action
    is_fetching_statements = not (args.generate_and_upload_key or args.set_pin)

    if args.set_pin and not args.client_private_key_path:
        die(
            "--client-private-key-path is required when using --set-pin to decrypt the API response."
        )

    # Signing key is only strictly needed if fetching statements (might trigger 2FA)
    if is_fetching_statements and not args.wise_private_key_path:
        print(
            "Warning: --wise-private-key-path (for signing) is not set. "
            "Fetching statements might fail if a 2FA signature challenge occurs.",
            file=sys.stderr,
        )

    # --- Process Dates ---
    today = date.today()  # Use date object
    date_format = "%Y-%m-%d"

    if args.month:
        if args.start or args.end:
            die("--month flag conflicts with --start and --end")
        year = args.year if args.year else today.year
        try:
            # Calculate first and last day of the specified month/year
            first_day = date(year, args.month, 1)
            _, last_day_of_month = calendar.monthrange(year, args.month)
            last_day = date(year, args.month, last_day_of_month)
            args.start = first_day.strftime(date_format)
            args.end = last_day.strftime(date_format)
        except ValueError:
            die(f"Invalid year/month combination: {year}-{args.month}")
    elif args.start or args.end:
        # If one is provided, the other must be too
        if not (args.start and args.end):
            die(
                "Both --start and --end flags must be passed together (using YYYY-MM-DD format)."
            )
        # Validate formats
        try:
            datetime.strptime(args.start, date_format)
        except ValueError:
            die(f"Invalid start date format: '{args.start}'. Use YYYY-MM-DD.")
        try:
            datetime.strptime(args.end, date_format)
        except ValueError:
            die(f"Invalid end date format: '{args.end}'. Use YYYY-MM-DD.")
    elif is_fetching_statements:
        # Default to previous month only if fetching statements
        print("Defaulting statements to the previous full month.")
        first_day_current_month = today.replace(day=1)
        last_day_previous_month = first_day_current_month - timedelta(days=1)
        first_day_previous_month = last_day_previous_month.replace(day=1)
        args.start = first_day_previous_month.strftime(date_format)
        args.end = last_day_previous_month.strftime(date_format)

    return args


# --- Main Execution Logic ---
def main() -> None:
    """Main function to orchestrate actions based on arguments."""
    args = parse_args()

    # Set Base URL for Sandbox if requested
    global BASE_URL
    if args.wise_test:
        print("--- Using Wise Sandbox Environment (api.sandbox.transferwise.tech) ---")
        BASE_URL = "https://api.sandbox.transferwise.tech"
        # Note: Sandbox might require specific test tokens/keys
        args.wise_api_token = "f17ef8f9-5cbe-4732-b1a1-91aefd08fe91"  # noqa: S105

    # Read signing private key (PKCS1) if path is provided
    signing_private_key_bytes = None
    if args.wise_private_key_path:
        try:
            signing_key_path = Path(args.wise_private_key_path)
            if not signing_key_path.is_file():
                # Only error if path explicitly provided but invalid. Env var handled by warning.
                if args.wise_private_key_path != os.environ.get(
                    "WISE_PRIVATE_KEY_PATH"
                ):
                    die(f"Signing private key file not found: {signing_key_path}")
            else:
                signing_private_key_bytes = signing_key_path.read_bytes()
                print(f"Loaded signing private key (PKCS1) from: {signing_key_path}")
        except Exception as e:
            die(
                f"Failed to read signing private key from {args.wise_private_key_path}: {e}"
            )

    # Initialize WiseClient (can handle None for keys if not needed for action)
    try:
        client = WiseClient(
            args.wise_api_token,
            signing_private_key_bytes,
            args.client_private_key_path,  # Path to client's decryption key (PKCS8)
            pin=args.wise_pin,
        )
    except Exception as e:
        # Catch potential errors during Signer init if key format is bad
        die(f"Failed to initialize Wise client: {e}")

    # --- Action: Generate and Upload Key ---
    if args.generate_and_upload_key:
        print("\n--- Action: Generate and Upload Client Encryption Key ---")

        key_path = Path(args.client_private_key_path)
        priv_path = key_path
        pub_path = key_path.with_name(f"{key_path.stem}_pub.pem")  # e.g., client_wise_crypto_key_pub.pem

        def load_public_key(public_key_path: Path) -> crypto_rsa.RSAPublicKey:
            try:
                public_key_bytes = public_key_path.read_bytes()
                public_key_obj = serialization.load_pem_public_key(public_key_bytes)
                return public_key_obj
            except Exception as e:
                raise RuntimeError(f"Failed to load public key from {public_key_path}: {e}")

        if not priv_path.exists() or not pub_path.exists():
            print(f"Generating new RSA key pair at {priv_path} and {pub_path}")
            # Generate the RSA key pair (PKCS8 private, PEM public)
            _, public_key = generate_and_save_rsa_key_pair(priv_path, pub_path)
        else:
            print(f"Loading existing RSA public key from {pub_path}")
            try:
                public_key = load_public_key(pub_path)
            except Exception as e:
                die(f"Failed to load existing public key: {e}")

        try:
            # Upload the public key (DER/Base64)
            upload_result = client.upload_client_public_key(public_key)
            if upload_result:
                print("\nSuccessfully generated, saved, and uploaded client public key.")
                print(f"Client Private Key (PKCS8): '{priv_path}' - Keep this file safe!")
                print("Use this private key with --client-private-key-path for decrypting responses.")
            else:
                die("Failed to upload the generated public key.")
        except Exception as e:
            die(f"An error occurred during key generation/upload: {e}")
        try:
            # Upload the public key (DER/Base64)
            upload_result = client.upload_client_public_key(public_key)
            if upload_result:
                print(
                    "\nSuccessfully generated, saved, and uploaded client public key."
                )
                print(f"Client Private Key (PKCS8): '{priv_path}' - Keep Safe!")
                print(
                    "Use this private key path with --client-private-key-path for decrypting responses."
                )
            else:
                die("Failed to upload the generated public key.")
        except Exception as e:
            die(f"An error occurred during key generation/upload: {e}")

    # --- Action: Set PIN ---
    elif args.set_pin:
        print("\n--- Action: Set/Update Wise PIN via JWE ---")
        if not args.wise_pin:
            die(
                "PIN must be provided via --wise-pin or WISE_PIN env var to use --set-pin."
            )
        # Decryption key is required for this action
        if not client.client_private_key_path:
            die("--client-private-key-path is required when using --set-pin.")

        try:
            bun_script_dir = Path(args.bun_script_dir)
            # post_user_pin handles encrypt, send, receive, decrypt
            result_data = client.post_user_pin(args.wise_pin, bun_script_dir)

            if (
                result_data is not None
            ):  # Success (could be {} for 204 or decrypted data)
                print("\nPIN setting process completed successfully.")
                # result_data contains decrypted response if available
            else:
                # Indicates PIN likely already existed (409 handled in post_user_pin)
                print(
                    "\nPIN setting process indicates PIN already existed or encountered an issue."
                )
                sys.exit(1)  # Exit with error for non-success

        except ValueError as e:
            die(str(e))  # Invalid PIN format
        except Exception as e:
            die(f"An error occurred during PIN setting process: {e}")

    # --- Default Action: Fetch Statements ---
    else:
        print("\n--- Action: Fetch Statements ---")
        if not args.start or not args.end:
            die(
                "Start and end dates (--start YYYY-MM-DD --end YYYY-MM-DD, or --month) are required for fetching statements."
            )
        print(f"Fetching statements from {args.start} to {args.end}")

        # Determine profile ID if not provided
        profile_id_to_use = args.wise_profile
        if not profile_id_to_use:
            print("Detecting profile ID...")
            profile_id_to_use = client.get_business_profile()
            print(f"Using detected profile ID: {profile_id_to_use}")

        # Get balances for the profile
        balances = client.get_balances(profile_id_to_use)
        if not balances:
            die(f"No standard balances found for profile ID {profile_id_to_use}.")

        print(f"Found balances: {', '.join(b.currency for b in balances)}")
        all_statements = []
        fetch_errors = 0
        for balance in balances:
            try:
                statement_data = client.get_balance_statements(
                    profile_id_to_use, balance, args.start, args.end
                )
                all_statements.append(statement_data)
            except Exception as e:
                # Log error for specific balance but continue with others
                print(
                    f"\n--- Failed to fetch statement for {balance.currency} (ID: {balance.id}) ---",
                    file=sys.stderr,
                )
                print(f"Error details: {e}", file=sys.stderr)
                print("--- Continuing with next balance ---", file=sys.stderr)
                fetch_errors += 1

        if not all_statements:
            die("Failed to fetch statements for any balances.")

        # Output combined statements as JSON array
        print("\n--- Combined Statements JSON Output ---")
        json.dump(all_statements, sys.stdout, indent=2)
        print("\n--- End of Statements ---")

        if fetch_errors > 0:
            print(
                f"\nWarning: Failed to fetch statements for {fetch_errors} balance(s). See logs above.",
                file=sys.stderr,
            )
            sys.exit(1)  # Exit with error if any statement failed


# --- Entry Point ---
if __name__ == "__main__":
    main()
