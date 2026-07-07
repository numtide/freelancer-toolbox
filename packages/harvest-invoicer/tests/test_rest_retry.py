"""Retry/backoff behavior of the shared rest.http_request helper.

Lives in the harvest-invoicer suite (rather than the untested harvest
package) so `nix flake check` exercises it — the FX/Harvest fetch path
depends on this resilience.
"""

from __future__ import annotations

import io
import urllib.error
from typing import TYPE_CHECKING

import pytest
import rest

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(autouse=True)
def captured_sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Capture backoff sleeps instead of waiting; keep jitter deterministic."""
    slept: list[float] = []
    monkeypatch.setattr(rest.time, "sleep", slept.append)
    # random.uniform(0, ceiling) -> the ceiling, so we can assert the schedule.
    monkeypatch.setattr(rest.random, "uniform", lambda _lo, hi: hi)
    return slept


def _fake_body(payload: bytes = b'{"ok": true}') -> io.BytesIO:
    return io.BytesIO(payload)


def _install_urlopen(monkeypatch: pytest.MonkeyPatch, outcomes: list[object]) -> list:
    """Make urlopen yield each outcome in turn (raise if it's an Exception)."""
    calls: list = []
    it: Iterator[object] = iter(outcomes)

    def fake_urlopen(req: object, timeout: float | None = None) -> object:
        calls.append((req, timeout))
        result = next(it)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(rest.urllib.request, "urlopen", fake_urlopen)
    return calls


def test_retries_transient_then_succeeds(
    monkeypatch: pytest.MonkeyPatch, captured_sleeps: list[float]
) -> None:
    calls = _install_urlopen(
        monkeypatch,
        [
            urllib.error.URLError("connection reset"),
            urllib.error.URLError("connection reset"),
            _fake_body(b'{"rate": 1}'),
        ],
    )
    result = rest.http_request("https://example.test/x")
    assert result == {"rate": 1}
    assert len(calls) == 3  # two failures + one success
    assert captured_sleeps == [0.5, 1.0]  # exponential base 0.5, factor 2


def test_timeout_is_passed_to_urlopen(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _install_urlopen(monkeypatch, [_fake_body()])
    rest.http_request("https://example.test/x")
    assert calls[0][1] == rest.DEFAULT_TIMEOUT


def test_client_error_is_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    err = urllib.error.HTTPError("u", 400, "Bad Request", {}, None)  # type: ignore[arg-type]
    calls = _install_urlopen(monkeypatch, [err])
    with pytest.raises(urllib.error.HTTPError):
        rest.http_request("https://example.test/x")
    assert len(calls) == 1  # no retry on a 4xx


def test_server_error_is_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    err = urllib.error.HTTPError("u", 503, "Unavailable", {}, None)  # type: ignore[arg-type]
    calls = _install_urlopen(monkeypatch, [err, _fake_body(b'{"v": 2}')])
    assert rest.http_request("https://example.test/x") == {"v": 2}
    assert len(calls) == 2


def test_gives_up_after_max_attempts(
    monkeypatch: pytest.MonkeyPatch, captured_sleeps: list[float]
) -> None:
    err = urllib.error.URLError("down")
    calls = _install_urlopen(monkeypatch, [err] * rest.MAX_ATTEMPTS)
    with pytest.raises(urllib.error.URLError):
        rest.http_request("https://example.test/x")
    assert len(calls) == rest.MAX_ATTEMPTS
    assert len(captured_sleeps) == rest.MAX_ATTEMPTS - 1  # no sleep after last try
