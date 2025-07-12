"""SevDesk API Client."""

from __future__ import annotations

import json
from http.client import HTTPSConnection
from typing import Any, cast
from urllib.parse import urlencode, urlparse

# HTTP status codes
HTTP_BAD_REQUEST = 400

# Constants
RESPONSE_SIZE_LIMIT = 1000


class SevDeskError(Exception):
    """Base exception for SevDesk API errors."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response_body: str | None = None,
    ) -> None:
        """Initialize SevDeskError.

        Args:
            message: Error message
            status_code: HTTP status code
            response_body: Response body from API

        """
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class SevDeskClient:
    """Client for interacting with the SevDesk API."""

    def __init__(
        self,
        api_token: str,
        base_url: str = "https://my.sevdesk.de/api/v1/",
    ) -> None:
        """Initialize the SevDesk client.

        Args:
            api_token: The API token for authentication
            base_url: The base URL for the API

        """
        self.api_token = api_token
        self.base_url = base_url.rstrip("/") + "/"

        # Parse base URL
        parsed = urlparse(self.base_url)
        self.host = parsed.hostname
        self.port = parsed.port or (443 if parsed.scheme == "https" else 80)
        self.is_https = parsed.scheme == "https"
        self.base_path = parsed.path.rstrip("/")

        # Default headers
        self.headers = {
            "Authorization": api_token,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "sevdesk-python-client/1.0",
        }

    def get_connection(self) -> HTTPSConnection:
        """Get an HTTPS connection."""
        if self.host is None:
            msg = "Host is not set"
            raise ValueError(msg)
        return HTTPSConnection(self.host, self.port)

    def _format_error_message(
        self,
        response_body: str,
        response_status: int,
        method: str,
        path: str,
    ) -> str:
        """Format error message from API response.

        Args:
            response_body: Response body
            response_status: HTTP status code
            method: HTTP method
            path: Request path

        Returns:
            Formatted error message

        """
        error_msg = f"API request failed with status {response_status}"
        if not response_body:
            return error_msg

        try:
            error_data = json.loads(response_body)
            error_detail = error_data.get("error", {}).get("message", error_msg)
            error_msg = f"API request failed: {error_detail}"

            # Include more context if available
            if "error" in error_data and isinstance(error_data["error"], dict):
                if "code" in error_data["error"]:
                    error_msg += f" (code: {error_data['error']['code']})"
                if "details" in error_data["error"]:
                    error_msg += f"\nDetails: {error_data['error']['details']}"

            # Always include the full response for debugging
            error_msg += f"\nHTTP {response_status} {method} {path}"
            if len(response_body) < RESPONSE_SIZE_LIMIT:
                error_msg += f"\nFull response: {response_body}"
        except json.JSONDecodeError:
            error_msg = (
                f"API request failed: {response_body}\n"
                f"HTTP {response_status} {method} {path}"
            )
        return error_msg

    def _request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make a request to the SevDesk API.

        Args:
            method: HTTP method
            endpoint: API endpoint
            params: Query parameters
            json_data: JSON data for request body
            data: Form data for request body

        Returns:
            Response data as dict

        Raises:
            SevDeskError: If the request fails

        """
        # Build URL path
        path = f"{self.base_path}/{endpoint.lstrip('/')}"

        # Add query parameters
        if params:
            query_string = urlencode(params, doseq=True)
            path = f"{path}?{query_string}"

        # Prepare body
        body = None
        headers = self.headers.copy()

        if json_data is not None:
            body = json.dumps(json_data).encode("utf-8")
            headers["Content-Type"] = "application/json"
        elif data is not None:
            body = urlencode(data).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"

        # Make request
        conn = self.get_connection()
        try:
            conn.request(method, path, body=body, headers=headers)
            response = conn.getresponse()
            response_body = response.read().decode("utf-8")

            # Check status
            if response.status >= HTTP_BAD_REQUEST:
                error_msg = self._format_error_message(
                    response_body,
                    response.status,
                    method,
                    path,
                )
                raise SevDeskError(error_msg, response.status, response_body)

            # Parse response
            if response_body:
                result = json.loads(response_body)
                return cast("dict[str, Any]", result)
            return {}

        finally:
            conn.close()

    def get(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make a GET request."""
        return self._request("GET", endpoint, params=params)

    def post(
        self,
        endpoint: str,
        json_data: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make a POST request."""
        return self._request(
            "POST",
            endpoint,
            params=params,
            json_data=json_data,
            data=data,
        )

    def put(
        self,
        endpoint: str,
        json_data: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make a PUT request."""
        return self._request(
            "PUT",
            endpoint,
            params=params,
            json_data=json_data,
            data=data,
        )

    def delete(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make a DELETE request."""
        return self._request("DELETE", endpoint, params=params)
