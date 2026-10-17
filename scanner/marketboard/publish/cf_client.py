"""Publish to the Cloudflare Worker ingest API through Access with a service token.

Cloudflare Access checks the CF-Access-Client-Id / CF-Access-Client-Secret headers
and forwards a signed JWT to the Worker, which also checks that the token's
identity is the scanner's service token (CLAUDE.md rule 5).
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from typing import Any

import httpx

from marketboard.config import RetrySettings
from marketboard.retry import request_with_retry

INGEST_KINDS = frozenset({"board", "alert", "digest", "calibration", "outcome", "ping"})


class IngestError(RuntimeError):
    """Ingest failed. The message never includes credentials."""


class IngestClient:
    def __init__(
        self,
        base_url: str,
        client_id: str,
        client_secret: str,
        http: httpx.Client,
        retry: RetrySettings,
        *,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not client_id or not client_secret:
            raise ValueError("service token client id and secret are required")
        self._base = base_url.rstrip("/")
        self._headers = {
            "CF-Access-Client-Id": client_id,
            "CF-Access-Client-Secret": client_secret,
        }
        self._http = http
        self._retry = retry
        self._sleep = sleep

    def post(self, kind: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        if kind not in INGEST_KINDS:
            raise ValueError(f"unknown ingest kind {kind!r}")
        url = f"{self._base}/{kind}"
        try:
            response = request_with_retry(
                lambda: self._http.post(url, json=dict(payload), headers=self._headers),
                self._retry,
                sleep=self._sleep,
            )
        except httpx.TransportError as exc:
            raise IngestError(f"{kind}: transport error: {type(exc).__name__}") from None
        if response.status_code != 200:
            raise IngestError(f"{kind}: HTTP {response.status_code}{_hint(response.status_code)}")
        try:
            body = response.json()
        except ValueError:
            raise IngestError(f"{kind}: response is not JSON") from None
        if not isinstance(body, dict):
            raise IngestError(f"{kind}: unexpected response shape")
        return body


def _hint(status: int) -> str:
    if status in (301, 302, 303, 307, 308):
        return " (Access redirected to login: the service token was not accepted)"
    if status == 401:
        return " (Worker rejected the Access JWT)"
    if status == 403:
        return " (Access or the Worker denied this identity: check the Service Auth policy)"
    return ""
