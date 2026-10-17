"""CLAUDE.md rule 7: Telegram sends only to TELEGRAM_CHAT_ID and never leaks the token."""

from __future__ import annotations

import json

import httpx
import pytest

from marketboard.alerts.telegram import MAX_MESSAGE_CHARS, TelegramClient, TelegramError
from marketboard.config import RetrySettings

TOKEN = "123456:SECRET-TOKEN"


def _client(handler: httpx.MockTransport, retry: RetrySettings) -> TelegramClient:
    http = httpx.Client(transport=handler)
    return TelegramClient(TOKEN, "4242", http, retry, sleep=lambda _: None)


def test_sends_only_to_configured_chat(retry: RetrySettings) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"ok": True})

    _client(httpx.MockTransport(handler), retry).send("AAPL 1D OB 187.20-189.05 +2.1%")
    assert len(seen) == 1
    body = json.loads(seen[0].content)
    assert body["chat_id"] == "4242"
    assert "parse_mode" not in body
    assert seen[0].url.path == f"/bot{TOKEN}/sendMessage"


def test_send_has_no_recipient_parameter() -> None:
    import inspect

    assert list(inspect.signature(TelegramClient.send).parameters) == ["self", "text"]


def test_long_messages_truncated(retry: RetrySettings) -> None:
    sizes: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sizes.append(len(json.loads(request.content)["text"]))
        return httpx.Response(200, json={"ok": True})

    _client(httpx.MockTransport(handler), retry).send("x" * (MAX_MESSAGE_CHARS + 50))
    assert sizes == [MAX_MESSAGE_CHARS]


def test_api_error_raises_without_token(retry: RetrySettings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"ok": False, "description": "Bad Request: chat not found"})

    with pytest.raises(TelegramError) as info:
        _client(httpx.MockTransport(handler), retry).send("hi")
    assert "chat not found" in str(info.value)
    assert TOKEN not in str(info.value)


def test_transport_error_does_not_leak_token(retry: RetrySettings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"cannot reach {request.url}", request=request)

    with pytest.raises(TelegramError) as info:
        _client(httpx.MockTransport(handler), retry).send("hi")
    assert TOKEN not in str(info.value)
    assert info.value.__cause__ is None
    assert info.value.__suppress_context__


def test_ok_false_is_failure(retry: RetrySettings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": False, "description": "nope"})

    with pytest.raises(TelegramError):
        _client(httpx.MockTransport(handler), retry).send("hi")
