import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


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
    resp = urllib.request.urlopen(req)
    return json.load(resp)


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
    resp = urllib.request.urlopen(req)
    return Response(
        status=resp.status,
        headers=dict(resp.headers),
        json=json.load(resp),
    )
