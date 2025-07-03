from __future__ import annotations

import base64
import logging
from dataclasses import dataclass, field
from time import sleep
from typing import Any
from urllib.parse import urljoin

import requests


@dataclass
class PaginationInfo:
    total_pages: int
    current_page: int
    total_results: int


@dataclass
class Meta:
    pagination_info: PaginationInfo


@dataclass
class QuipuResponse:
    data: list[Any]
    meta: Meta | None = None
    errors: list[dict[str, Any]] | None = field(default_factory=list)
    links: dict[str, str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "data": self.data,
            "meta": self.meta,
            "errors": self.errors,
            "links": self.links,
        }


class QuipuAPI:
    def __init__(self, app_id: str, app_secret: str) -> None:
        self._base_url = "https://getquipu.com/"
        self._app_id = app_id
        self._app_secret = app_secret
        self._token = None
        self._headers = {
            "Accept": "application/vnd.quipu.v1+json",
            "Content-Type": "application/vnd.quipu.v1+json",
        }
        self.log = logging.getLogger(__name__)
        self._get_token()

    def _generate_auth_header(self) -> dict[str, str]:
        credentials = f"{self._app_id}:{self._app_secret}"
        base64_credentials = base64.b64encode(credentials.encode("utf-8")).decode(
            "utf-8"
        )
        return {"Authorization": f"Basic {base64_credentials}"}

    def _get_token(self) -> None:
        """Retrieve and set the authentication token."""
        token_endpoint = urljoin(self._base_url, "oauth/token")
        headers = self._generate_auth_header()
        headers.update(
            {"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"}
        )
        try:
            response = requests.post(
                token_endpoint,
                headers=headers,
                data={"scope": "ecommerce", "grant_type": "client_credentials"},
                timeout=20,
            )
            response.raise_for_status()
            self._token = response.json()["access_token"]
            self._headers["Authorization"] = f"Bearer {self._token}"
        except requests.RequestException:
            self.log.exception("Failed to get token")
            raise

    def _try_refresh_token(self) -> bool:
        """Attempt to refresh the authentication token."""
        try:
            self._get_token()
        except requests.RequestException:
            self.log.warning("Failed to refresh token.")
            return False
        else:
            return True

    def _make_request(
        self,
        method: str,
        endpoint: str,
        data: dict | None = None,
        params: dict | None = None,
        max_retries: int = 3,
    ) -> QuipuResponse:
        """Make a request with retries on 401 Unauthorized error."""
        url = urljoin(self._base_url, endpoint)
        attempts = 0

        while attempts < max_retries:
            response = None
            try:
                response = requests.request(
                    method,
                    url,
                    headers=self._headers,
                    json=data,
                    params=params,
                    timeout=20,
                )
                response.raise_for_status()
                self.log.debug(f"Response from {method} {url}: {response.text}")
                return QuipuResponse(**response.json())
            except requests.HTTPError:
                self.log.exception(f"HTTP error for {method} {url}")
                if (
                    response
                    and response.status_code == 401
                    and attempts < max_retries - 1
                ):
                    if not self._try_refresh_token():
                        raise
                else:
                    raise
            except requests.RequestException:
                self.log.exception(f"Request error for {method} {url}")
                raise

            self.log.warning(
                f"Retrying {method} request to {endpoint}. Attempt {attempts + 1}/{max_retries}."
            )
            sleep(2**attempts)  # Exponential backoff
            attempts += 1

        msg = "Maximum retry attempts reached"
        raise RuntimeError(msg)

    def _get(self, endpoint: str, params: dict | None = None) -> QuipuResponse:
        return self._make_request("GET", endpoint, params=params)

    def _post(self, endpoint: str, data: dict) -> QuipuResponse | None:
        return self._make_request("POST", endpoint, data=data)

    def _patch(self, endpoint: str, data: dict) -> QuipuResponse | None:
        return self._make_request("PATCH", endpoint, data=data)

    def list_invoices(
        self, page: int = 1, include_items: bool = False
    ) -> QuipuResponse:
        endpoint = "invoices"
        params = {"page[number]": page, "include": "items" if include_items else None}
        return self._get(endpoint, params)

    def get_invoice(self, invoice_id: str) -> QuipuResponse:
        endpoint = f"invoices/{invoice_id}"
        return self._get(endpoint)

    def create_invoice(self, invoice_data: dict) -> QuipuResponse | None:
        endpoint = "invoices"
        return self._post(endpoint, invoice_data)

    def update_invoice(
        self, invoice_id: str, update_data: dict
    ) -> QuipuResponse | None:
        endpoint = f"invoices/{invoice_id}"
        return self._patch(endpoint, data=update_data)

    def list_contacts(self, page: int = 1) -> QuipuResponse:
        endpoint = "contacts"
        params = {"page[number]": page}
        return self._get(endpoint, params=params)

    def get_contact(self, contact_id: str) -> QuipuResponse:
        endpoint = f"contacts/{contact_id}"
        return self._get(endpoint)

    def list_accounting_categories(
        self, kind: str | None = None, prefix: str | None = None, page: int = 1
    ) -> QuipuResponse:
        endpoint = "accounting_categories"
        params = {"page[number]": page}
        if kind:
            params["filter[kind]"] = kind
        if prefix:
            params["filter[prefix]"] = prefix
        return self._get(endpoint, params=params)
