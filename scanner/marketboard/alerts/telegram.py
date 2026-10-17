"""Telegram delivery, locked to the single configured chat (CLAUDE.md rule 7).

The bot only sends. It never reads updates, so messages from other chats are
ignored by construction. Callers cannot choose a recipient. Messages carry
tickers, zones and percentages only.
"""

from __future__ import annotations

import time
from collections.abc import Callable

import httpx

from marketboard.config import RetrySettings
from marketboard.retry import request_with_retry

TELEGRAM_API = "https://api.telegram.org"
MAX_MESSAGE_CHARS = 4096  # Telegram API limit


class TelegramError(RuntimeError):
    """Delivery failed. The message never includes the bot token."""


class TelegramClient:
    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        http: httpx.Client,
        retry: RetrySettings,
        *,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not bot_token or not chat_id:
            raise ValueError("bot token and chat id are required")
        self._url = f"{TELEGRAM_API}/bot{bot_token}/sendMessage"
        self._chat_id = chat_id
        self._http = http
        self._retry = retry
        self._sleep = sleep

    def send(self, text: str) -> None:
        body = {
            "chat_id": self._chat_id,
            "text": text[:MAX_MESSAGE_CHARS],
            "disable_web_page_preview": True,
        }
        try:
            response = request_with_retry(
                lambda: self._http.post(self._url, json=body), self._retry, sleep=self._sleep
            )
        except httpx.TransportError as exc:
            # The request URL embeds the token, so do not chain the original error.
            raise TelegramError(f"transport error: {type(exc).__name__}") from None
        if response.status_code != 200 or not _ok(response):
            raise TelegramError(f"HTTP {response.status_code}: {_description(response)}")


def _ok(response: httpx.Response) -> bool:
    try:
        return bool(response.json().get("ok"))
    except ValueError:
        return False


def _description(response: httpx.Response) -> str:
    try:
        return str(response.json().get("description", "no description"))
    except ValueError:
        return "non-JSON response"
