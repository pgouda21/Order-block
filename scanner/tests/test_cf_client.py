from __future__ import annotations

import json

import httpx
import pytest

from marketboard.config import RetrySettings
from marketboard.publish.cf_client import IngestClient, IngestError

BASE = "https://board.example.com/api/ingest/"


def _client(handler: httpx.MockTransport, retry: RetrySettings) -> IngestClient:
    http = httpx.Client(transport=handler)
    return IngestClient(BASE, "client.access", "client-secret", http, retry, sleep=lambda _: None)


def test_posts_with_service_token_headers(retry: RetrySettings) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"ok": True})

    body = _client(httpx.MockTransport(handler), retry).post("ping", {"sent_at": 1})
    assert body == {"ok": True}
    request = seen[0]
    assert str(request.url) == "https://board.example.com/api/ingest/ping"
    assert request.headers["CF-Access-Client-Id"] == "client.access"
    assert request.headers["CF-Access-Client-Secret"] == "client-secret"
    assert json.loads(request.content) == {"sent_at": 1}


def test_unknown_kind_rejected(retry: RetrySettings) -> None:
    client = _client(httpx.MockTransport(lambda r: httpx.Response(200, json={})), retry)
    with pytest.raises(ValueError):
        client.post("orders", {})


def test_retries_then_succeeds(retry: RetrySettings) -> None:
    statuses = iter([429, 502, 200])

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(next(statuses), json={"ok": True})

    assert _client(httpx.MockTransport(handler), retry).post("ping", {}) == {"ok": True}


@pytest.mark.parametrize(
    ("status", "hint"),
    [(302, "service token was not accepted"), (401, "JWT"), (403, "Service Auth")],
)
def test_auth_failures_explained_without_secret(
    retry: RetrySettings, status: int, hint: str
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, headers={"location": "https://login.example"})

    with pytest.raises(IngestError) as info:
        _client(httpx.MockTransport(handler), retry).post("ping", {})
    assert hint in str(info.value)
    assert "client-secret" not in str(info.value)


def test_persistent_5xx_raises(retry: RetrySettings) -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(503)

    with pytest.raises(IngestError):
        _client(httpx.MockTransport(handler), retry).post("ping", {})
    assert len(calls) == retry.max_attempts
