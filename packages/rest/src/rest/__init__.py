import json
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from http.client import HTTPResponse
from typing import Any, cast

# Public retry knobs (also referenced by tests).
DEFAULT_TIMEOUT = 30.0
MAX_ATTEMPTS = 4
_BACKOFF_BASE = 0.5
_BACKOFF_CAP = 8.0
# Status codes worth retrying: rate limiting and transient server faults.
_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})


def _is_transient(exc: Exception) -> bool:
    """Whether a failed request is worth retrying.

    Connection-level failures (``URLError``, which covers timeouts and DNS
    or socket errors) are transient; HTTP errors are only transient for
    rate-limit / 5xx status codes. A 4xx is a caller error — do not retry.
    """
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code in _RETRY_STATUS
    return isinstance(exc, urllib.error.URLError | TimeoutError)


def _urlopen_retrying(req: urllib.request.Request) -> HTTPResponse:
    """Open *req* with a timeout and bounded exponential backoff + jitter.

    Retries only transient failures; a 4xx and the final attempt's error
    propagate unchanged.
    """
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return cast(
                "HTTPResponse",
                urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT),
            )
        except Exception as exc:
            if attempt == MAX_ATTEMPTS or not _is_transient(exc):
                raise
            # Exponential backoff with full jitter: sleep in [0, base·2^n], capped.
            ceiling = min(_BACKOFF_CAP, _BACKOFF_BASE * (2 ** (attempt - 1)))
            time.sleep(random.uniform(0, ceiling))  # noqa: S311 — jitter, not crypto
    msg = "unreachable"  # pragma: no cover
    raise AssertionError(msg)  # pragma: no cover


def http_request(
    url: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if headers is None:
        headers = {}
    body = None
    if data:
        body = json.dumps(data).encode("ascii")
    headers = headers.copy()
    headers["User-Agent"] = "Numtide invoice generator"
    req = urllib.request.Request(url, headers=headers, method=method, data=body)
    resp = _urlopen_retrying(req)
    return cast("dict[str, Any]", json.load(resp))


@dataclass
class Response:
    status: int
    headers: dict[str, str]
    json: dict[str, Any]


def http_request2(
    url: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    data: dict[str, Any] | None = None,
) -> Response:
    if headers is None:
        headers = {}
    if method == "GET" and data:
        url += "?" + urllib.parse.urlencode(data)
        body = None
    else:
        body = json.dumps(data).encode("ascii") if data else None

    headers = headers.copy()
    headers["User-Agent"] = "Numtide invoice generator"
    req = urllib.request.Request(url, headers=headers, method=method, data=body)
    resp = _urlopen_retrying(req)
    return Response(
        status=resp.status,
        headers=dict(resp.headers),
        json=json.load(resp),
    )
