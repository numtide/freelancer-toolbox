"""Paperless-ngx API client."""

import json
import logging
import mimetypes
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any, TypeVar, cast

from paperless_cli.models import (
    BulkEditRequest,
    BulkEditResponse,
    Correspondent,
    Document,
    DocumentListResponse,
    DocumentSearchParams,
    DocumentType,
    DocumentUpdateRequest,
    MailAccount,
    MailRule,
    MailRuleCreateRequest,
    MailRuleUpdateRequest,
    Tag,
    TagCreateRequest,
    Task,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


class PaperlessAPIError(Exception):
    """Exception raised for Paperless API errors."""


class PaperlessClient:
    """Client for interacting with Paperless-ngx API."""

    def __init__(self, url: str, token: str) -> None:
        self.url = url.rstrip("/")
        self.token = token

        # Validate base URL
        parsed = urllib.parse.urlparse(self.url)
        assert parsed.scheme in ("http", "https"), f"Invalid URL scheme: {parsed.scheme}"
        assert parsed.netloc, "URL must have a valid netloc"

    def _request(
        self,
        method: str,
        endpoint: str,
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make an API request."""
        url = urllib.parse.urljoin(self.url, endpoint)

        # Validate URL scheme for security
        parsed_url = urllib.parse.urlparse(url)
        assert parsed_url.scheme in ("http", "https"), f"Invalid URL scheme: {parsed_url.scheme}"
        assert parsed_url.netloc, "URL must have a valid netloc"

        if params:
            query_string = urllib.parse.urlencode(params)
            url = f"{url}?{query_string}"

        headers = {
            "Authorization": f"Token {self.token}",
            "Content-Type": "application/json",
        }

        body = None
        if data is not None:
            body = json.dumps(data).encode("utf-8")

        # Log HTTP request
        logger.debug(f"HTTP Request: {method} {url}")
        logger.debug(f"Headers: {headers}")
        if data:
            logger.debug(f"Body: {json.dumps(data, indent=2)}")

        request = urllib.request.Request(url, data=body, headers=headers, method=method)  # noqa: S310

        try:
            with urllib.request.urlopen(request) as response:  # noqa: S310
                response_body = None
                if response.status == 204:  # No content
                    logger.debug(f"HTTP Response: {response.status} No Content")
                    return {}

                response_text = response.read().decode("utf-8")
                response_body = json.loads(response_text)
                logger.debug(f"HTTP Response: {response.status}")
                logger.debug(f"Response body: {json.dumps(response_body, indent=2)}")
                return cast("dict[str, Any]", response_body)
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8")
            logger.debug(f"HTTP Error: {e.code}")
            logger.debug(f"Error body: {error_body}")
            error_msg = f"HTTP {e.code}: {error_body}"
            raise PaperlessAPIError(error_msg) from e

    def get_mail_accounts(self) -> list[MailAccount]:
        """Get all mail accounts."""
        response = self._request("GET", "/api/mail_accounts/")
        return [MailAccount.from_api(account) for account in response["results"]]

    def get_mail_rules(self) -> list[MailRule]:
        """Get all mail rules."""
        response = self._request("GET", "/api/mail_rules/")
        return [MailRule.from_api(rule) for rule in response["results"]]

    def get_mail_rule(self, rule_id: int) -> MailRule:
        """Get a specific mail rule."""
        response = self._request("GET", f"/api/mail_rules/{rule_id}/")
        return MailRule.from_api(response)

    def create_mail_rule(self, create_request: MailRuleCreateRequest) -> MailRule:
        """Create a new mail rule."""
        data = create_request.to_dict()
        response = self._request("POST", "/api/mail_rules/", data=data)
        return MailRule.from_api(response)

    def update_mail_rule(
        self, rule_id: int, update_request: MailRuleUpdateRequest, current_rule: MailRule
    ) -> MailRule:
        """Update an existing mail rule."""
        data = update_request.apply_to_rule(current_rule)
        response = self._request("PUT", f"/api/mail_rules/{rule_id}/", data=data)
        return MailRule.from_api(response)

    def delete_mail_rule(self, rule_id: int) -> None:
        """Delete a mail rule."""
        self._request("DELETE", f"/api/mail_rules/{rule_id}/")

    def get_tags(self) -> list[Tag]:
        """Get all tags."""
        response = self._request("GET", "/api/tags/")
        return [Tag.from_api(tag_data) for tag_data in response["results"]]

    def create_tag(self, tag_request: TagCreateRequest) -> Tag:
        """Create a new tag."""
        data = tag_request.to_dict()
        response = self._request("POST", "/api/tags/", data=data)
        return Tag.from_api(response)

    def delete_tag(self, tag_id: int) -> None:
        """Delete a tag."""
        self._request("DELETE", f"/api/tags/{tag_id}/")

    def get_correspondents(self) -> list[Correspondent]:
        """Get all correspondents."""
        response = self._request("GET", "/api/correspondents/")
        return [Correspondent.from_api(corr) for corr in response["results"]]

    def get_document_types(self) -> list[DocumentType]:
        """Get all document types."""
        response = self._request("GET", "/api/document_types/")
        return [DocumentType.from_api(dt) for dt in response["results"]]

    def search_documents(self, search_params: DocumentSearchParams) -> DocumentListResponse:
        """Search documents."""
        params = search_params.to_params()
        response = self._request("GET", "/api/documents/", params=params)
        documents = [Document.from_api(doc) for doc in response["results"]]
        return DocumentListResponse.from_api(response, documents)

    def get_document(self, document_id: int) -> Document:
        """Get a specific document."""
        response = self._request("GET", f"/api/documents/{document_id}/")
        return Document.from_api(response)

    def get_document_metadata(self, document_id: int) -> dict[str, Any]:
        """Get document metadata."""
        return self._request("GET", f"/api/documents/{document_id}/metadata/")

    def download_document(self, document_id: int, original: bool = False) -> bytes:
        """Download a document."""
        endpoint = f"/api/documents/{document_id}/download/"
        params = {"original": "true"} if original else None
        url = urllib.parse.urljoin(self.url, endpoint)
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"

        headers = {"Authorization": f"Token {self.token}"}
        request = urllib.request.Request(url, headers=headers)  # noqa: S310

        with urllib.request.urlopen(request) as response:  # noqa: S310
            return cast("bytes", response.read())

    def upload_document(
        self, file_path: str, title: str | None = None, tags: list[int] | None = None
    ) -> dict[str, Any]:
        """Upload a document."""
        # Read file
        with Path(file_path).open("rb") as f:
            file_data = f.read()

        # Detect MIME type
        mime_type, _ = mimetypes.guess_type(file_path)
        if not mime_type:
            mime_type = "application/octet-stream"

        # Create multipart form data
        boundary = f"----WebKitFormBoundary{uuid.uuid4().hex[:16]}"
        body_parts = []

        # Add file field
        body_parts.append(f"------{boundary}")
        body_parts.append(
            f'Content-Disposition: form-data; name="document"; filename="{Path(file_path).name}"'
        )
        body_parts.append(f"Content-Type: {mime_type}")
        body_parts.append("")

        # Join text parts and add file data
        text_part = "\r\n".join(body_parts) + "\r\n"
        body = text_part.encode() + file_data + b"\r\n"

        # Add title if provided
        if title:
            body += f"------{boundary}\r\n".encode()
            body += b'Content-Disposition: form-data; name="title"\r\n\r\n'
            body += title.encode() + b"\r\n"

        # Add tags if provided
        if tags:
            for tag_id in tags:
                body += f"------{boundary}\r\n".encode()
                body += b'Content-Disposition: form-data; name="tags"\r\n\r\n'
                body += str(tag_id).encode() + b"\r\n"

        body += f"------{boundary}--\r\n".encode()

        headers = {
            "Authorization": f"Token {self.token}",
            "Content-Type": f"multipart/form-data; boundary=----{boundary}",
        }

        url = urllib.parse.urljoin(self.url, "/api/documents/post_document/")
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")  # noqa: S310

        try:
            with urllib.request.urlopen(request) as response:  # noqa: S310
                response_text = response.read().decode("utf-8")
                if response_text:
                    # The API returns just the task_id as a string
                    task_id = response_text.strip().strip('"')
                    return {"task_id": task_id}
                return {"status": "success"}
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8")
            logger.debug(f"HTTP Error: {e.code}")
            logger.debug(f"Error body: {error_body}")
            error_msg = f"HTTP {e.code}: {error_body}"
            raise PaperlessAPIError(error_msg) from e

    def delete_document(self, document_id: int) -> None:
        """Delete a document."""
        self._request("DELETE", f"/api/documents/{document_id}/")

    def get_task_status(self, task_id: str) -> Task | None:
        """Get task status by task_id."""
        response = self._request("GET", "/api/tasks/", params={"task_id": task_id})
        # The tasks endpoint returns an array, not a paginated response
        tasks = cast("list[dict[str, Any]]", response)
        if not tasks:
            return None

        return Task.from_api(tasks[0])

    def update_document(self, document_id: int, update_request: DocumentUpdateRequest) -> Document:
        """Update a document's metadata including tags."""
        data = update_request.to_dict()
        response = self._request("PATCH", f"/api/documents/{document_id}/", data=data)
        return Document.from_api(response)

    def bulk_edit_documents(self, bulk_request: BulkEditRequest) -> BulkEditResponse:
        """Perform bulk operations on multiple documents."""
        data = bulk_request.to_dict()
        response = self._request("POST", "/api/documents/bulk_edit/", data=data)
        # The API returns {"result": "OK"} on success
        # Return the document IDs that were requested as affected
        if response.get("result") == "OK":
            return BulkEditResponse(affected_documents=bulk_request.documents)
        return BulkEditResponse(affected_documents=response.get("affected_documents", []))
