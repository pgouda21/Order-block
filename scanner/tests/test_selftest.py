from __future__ import annotations

from datetime import UTC, datetime

import pytest

from marketboard import main as main_module
from marketboard.data.alpaca_client import MarketClock
from marketboard.selftest import format_results, run_checks

NOW = datetime(2026, 10, 16, 17, 0, tzinfo=UTC)


class FakeAlpaca:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    def clock(self) -> MarketClock:
        if self.error:
            raise self.error
        return MarketClock(NOW, True, NOW, NOW)


class FakeIngest:
    def __init__(self, body: dict[str, object]) -> None:
        self.body = body
        self.calls: list[tuple[str, dict[str, object]]] = []

    def post(self, kind: str, payload: dict[str, object]) -> dict[str, object]:
        self.calls.append((kind, payload))
        return self.body


class FakeTelegram:
    def __init__(self) -> None:
        self.sent: list[str] = []

    def send(self, text: str) -> None:
        self.sent.append(text)


def test_all_checks_pass() -> None:
    ingest, telegram = FakeIngest({"ok": True}), FakeTelegram()
    results = run_checks(alpaca=FakeAlpaca(), ingest=ingest, telegram=telegram, now=NOW)
    assert [r.name for r in results] == ["config", "alpaca", "ingest", "telegram"]
    assert [r.status for r in results] == ["pass"] * 4
    assert ingest.calls == [("ping", {"sent_at": int(NOW.timestamp())})]
    assert telegram.sent == ["MarketBoard self-test OK 2026-10-16 10:00 PDT"]


def test_telegram_off_is_skipped_not_failed() -> None:
    results = run_checks(
        alpaca=FakeAlpaca(), ingest=FakeIngest({"ok": True}), telegram=None, now=NOW
    )
    by_name = {r.name: r for r in results}
    assert by_name["telegram"].status == "skip"
    assert all(r.ok for r in results)
    assert "SKIP  telegram" in format_results(results)


def test_failures_reported_and_secrets_redacted() -> None:
    results = run_checks(
        alpaca=FakeAlpaca(RuntimeError("bad key PKSECRET")),
        ingest=FakeIngest({"ok": False}),
        telegram=None,
        now=NOW,
        secrets_to_redact=["PKSECRET", ""],
    )
    by_name = {r.name: r for r in results}
    assert not by_name["alpaca"].ok
    assert "PKSECRET" not in by_name["alpaca"].detail
    assert "***" in by_name["alpaca"].detail
    assert not by_name["ingest"].ok
    assert by_name["telegram"].status == "skip"
    assert "FAIL" in format_results(results)


def test_main_aborts_on_live_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALPACA_API_KEY", "k")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "s")
    monkeypatch.setenv("ALPACA_BASE_URL", "https://api.alpaca.markets")
    assert main_module.main(["--selftest"]) == 1


def test_main_without_flag_refuses_until_p1(paper_env: None) -> None:
    assert main_module.main([]) == 2
