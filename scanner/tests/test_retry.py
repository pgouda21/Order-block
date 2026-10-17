from __future__ import annotations

import random
from collections.abc import Callable

import httpx
import pytest

from marketboard.config import RetrySettings
from marketboard.retry import backoff_delay, request_with_retry

REQ = httpx.Request("POST", "https://example.test/x")


def _responses(
    *items: int | Exception,
) -> tuple[list[float], Callable[[], httpx.Response]]:
    sleeps: list[float] = []
    queue = list(items)

    def send() -> httpx.Response:
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return httpx.Response(item, request=REQ)

    return sleeps, send


def test_backoff_is_capped_and_jittered(retry: RetrySettings) -> None:
    rng = random.Random(7)
    for attempt in range(10):
        delay = backoff_delay(attempt, retry, rng)
        assert 0 <= delay <= min(retry.max_delay_s, retry.base_delay_s * 2**attempt)


def test_success_returns_immediately(retry: RetrySettings) -> None:
    sleeps, send = _responses(200)
    response = request_with_retry(send, retry, sleep=sleeps.append)
    assert response.status_code == 200
    assert sleeps == []


def test_retries_429_then_succeeds(retry: RetrySettings) -> None:
    sleeps, send = _responses(429, 503, 200)
    response = request_with_retry(send, retry, sleep=sleeps.append)
    assert response.status_code == 200
    assert len(sleeps) == 2


def test_honours_retry_after_capped(retry: RetrySettings) -> None:
    sleeps: list[float] = []
    calls = iter(
        [
            httpx.Response(429, headers={"Retry-After": "999"}, request=REQ),
            httpx.Response(200, request=REQ),
        ]
    )
    request_with_retry(lambda: next(calls), retry, sleep=sleeps.append)
    assert sleeps == [retry.max_delay_s]


def test_gives_up_and_returns_last_response(retry: RetrySettings) -> None:
    sleeps, send = _responses(503, 503, 503)
    response = request_with_retry(send, retry, sleep=sleeps.append)
    assert response.status_code == 503
    assert len(sleeps) == retry.max_attempts - 1


def test_does_not_retry_client_errors(retry: RetrySettings) -> None:
    sleeps, send = _responses(403)
    assert request_with_retry(send, retry, sleep=sleeps.append).status_code == 403
    assert sleeps == []


def test_transport_errors_retried_then_raised(retry: RetrySettings) -> None:
    err = httpx.ConnectError("boom")
    sleeps, send = _responses(err, err, err)
    with pytest.raises(httpx.ConnectError):
        request_with_retry(send, retry, sleep=sleeps.append)
    assert len(sleeps) == retry.max_attempts - 1
