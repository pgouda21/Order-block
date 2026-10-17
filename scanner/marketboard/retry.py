"""HTTP retry with exponential backoff and full jitter (CLAUDE.md conventions)."""

from __future__ import annotations

import random
import time
from collections.abc import Callable

import httpx

from marketboard.config import RetrySettings

RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


def backoff_delay(attempt: int, retry: RetrySettings, rng: random.Random) -> float:
    """Full-jitter delay for a zero-based attempt: uniform(0, min(cap, base * 2**attempt))."""
    ceiling = min(retry.max_delay_s, retry.base_delay_s * 2**attempt)
    return rng.uniform(0, ceiling)


def retry_after_s(response: httpx.Response, retry: RetrySettings) -> float | None:
    """Honour a numeric Retry-After header, capped at max_delay_s."""
    value = response.headers.get("retry-after")
    if value is None:
        return None
    try:
        seconds = float(value)
    except ValueError:
        return None  # HTTP-date form: fall back to backoff
    return min(max(seconds, 0.0), retry.max_delay_s)


def request_with_retry(
    send: Callable[[], httpx.Response],
    retry: RetrySettings,
    *,
    sleep: Callable[[float], None] = time.sleep,
    rng: random.Random | None = None,
) -> httpx.Response:
    """Call `send` until it returns a non-retryable response or attempts run out.

    Returns the last response even if it is still retryable; re-raises the last
    transport error if every attempt failed to connect.
    """
    rng = rng or random.Random()
    for attempt in range(retry.max_attempts):
        is_last = attempt == retry.max_attempts - 1
        try:
            response = send()
        except httpx.TransportError:
            if is_last:
                raise
            sleep(backoff_delay(attempt, retry, rng))
            continue
        if response.status_code not in RETRYABLE_STATUS or is_last:
            return response
        delay = retry_after_s(response, retry)
        sleep(delay if delay is not None else backoff_delay(attempt, retry, rng))
    raise AssertionError("unreachable: max_attempts >= 1")
