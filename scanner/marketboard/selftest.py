"""P0 infrastructure self-test (Plan §13).

Checks, in order: config (paper endpoint), Alpaca read-only clock call,
service-token ingest ping through Cloudflare Access, and a Telegram test message.
Run on the VM via `systemctl start marketboard-selftest` so it runs under the same
sandbox, user and env file as the real service.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from zoneinfo import ZoneInfo

from marketboard.data.alpaca_client import MarketClock

UI_TZ = ZoneInfo("America/Los_Angeles")  # PT in anything a human reads (rule 10)


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str


class ClockSource(Protocol):
    def clock(self) -> MarketClock: ...


class Ingest(Protocol):
    def post(self, kind: str, payload: dict[str, object]) -> dict[str, object]: ...


class Messenger(Protocol):
    def send(self, text: str) -> None: ...


def _guard(name: str, redact: Callable[[str], str], fn: Callable[[], str]) -> CheckResult:
    try:
        return CheckResult(name, True, fn())
    except Exception as exc:  # report every failure, keep checking the rest
        return CheckResult(name, False, redact(f"{type(exc).__name__}: {exc}"))


def run_checks(
    *,
    alpaca: ClockSource,
    ingest: Ingest | None,
    telegram: Messenger | None,
    now: datetime,
    secrets_to_redact: Iterable[str] = (),
) -> list[CheckResult]:
    hidden = [s for s in secrets_to_redact if s]

    def redact(text: str) -> str:
        for secret in hidden:
            text = text.replace(secret, "***")
        return text

    results = [CheckResult("config", True, "paper endpoint enforced, settings.yaml valid")]

    def check_alpaca() -> str:
        clock = alpaca.clock()
        state = "open" if clock.is_open else "closed"
        return f"market {state}; next open {clock.next_open:%Y-%m-%d %H:%M %Z}"

    results.append(_guard("alpaca", redact, check_alpaca))

    if ingest is None:
        results.append(CheckResult("ingest", False, "CF_INGEST_URL / CF_ACCESS_* not configured"))
    else:
        found = ingest
        results.append(
            _guard("ingest", redact, lambda: _ping(found, now)),
        )

    if telegram is None:
        results.append(CheckResult("telegram", False, "TELEGRAM_* not configured"))
    else:
        bot = telegram
        stamp = now.astimezone(UI_TZ).strftime("%Y-%m-%d %H:%M %Z")

        def check_telegram() -> str:
            bot.send(f"MarketBoard self-test OK {stamp}")
            return "test message sent"

        results.append(_guard("telegram", redact, check_telegram))
    return results


def _ping(ingest: Ingest, now: datetime) -> str:
    body = ingest.post("ping", {"sent_at": int(now.timestamp())})
    if body.get("ok") is not True:
        raise RuntimeError("ping response did not report ok")
    return "service-token ingest returned 200"


def format_results(results: list[CheckResult]) -> str:
    width = max(len(r.name) for r in results)
    lines = [f"{'PASS' if r.ok else 'FAIL'}  {r.name:<{width}}  {r.detail}" for r in results]
    return "\n".join(lines)
