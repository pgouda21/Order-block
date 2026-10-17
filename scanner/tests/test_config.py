from __future__ import annotations

from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from marketboard.config import (
    ConfigError,
    load_secrets,
    load_settings,
    require_paper_endpoint,
)
from marketboard.data.alpaca_client import ReadOnlyAlpaca

LIVE_URLS = [
    "https://api.alpaca.markets",
    "https://api.alpaca.markets/v2",
    "http://paper-api.alpaca.markets",
    "https://paper-api.alpaca.markets.evil.example",
    "",
]


@pytest.mark.parametrize(
    "url",
    [
        "https://paper-api.alpaca.markets",
        "https://paper-api.alpaca.markets/",
        "https://paper-api.alpaca.markets/v2",
        " https://paper-api.alpaca.markets ",
    ],
)
def test_paper_endpoint_accepted(url: str) -> None:
    assert require_paper_endpoint(url) == "https://paper-api.alpaca.markets"


@pytest.mark.parametrize("url", LIVE_URLS)
def test_non_paper_endpoint_rejected(url: str) -> None:
    with pytest.raises(ConfigError):
        require_paper_endpoint(url)


@pytest.mark.parametrize("url", LIVE_URLS)
def test_startup_aborts_on_live_endpoint(monkeypatch: pytest.MonkeyPatch, url: str) -> None:
    monkeypatch.setenv("ALPACA_API_KEY", "k")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "s")
    monkeypatch.setenv("ALPACA_BASE_URL", url)
    with pytest.raises(ConfigError):
        load_secrets()


def test_wrapper_refuses_live_endpoint() -> None:
    with pytest.raises(ConfigError):
        ReadOnlyAlpaca("k", "s", "https://api.alpaca.markets", ZoneInfo("America/New_York"))


def test_missing_keys_abort_without_echoing_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "super-secret-value")
    with pytest.raises(ConfigError) as info:
        load_secrets()
    assert "alpaca_api_key" in str(info.value)
    assert "super-secret-value" not in str(info.value)


def test_blank_optional_secrets_mean_not_configured(
    monkeypatch: pytest.MonkeyPatch, paper_env: None
) -> None:
    for key in ("CF_INGEST_URL", "CF_ACCESS_CLIENT_ID", "CF_ACCESS_CLIENT_SECRET"):
        monkeypatch.setenv(key, "")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "  ")
    secrets = load_secrets()
    assert not secrets.ingest_configured
    assert not secrets.telegram_configured


def test_full_secrets(monkeypatch: pytest.MonkeyPatch, paper_env: None) -> None:
    monkeypatch.setenv("CF_INGEST_URL", "https://board.example.com/api/ingest/")
    monkeypatch.setenv("CF_ACCESS_CLIENT_ID", "id.access")
    monkeypatch.setenv("CF_ACCESS_CLIENT_SECRET", "secret")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    secrets = load_secrets()
    assert secrets.cf_ingest_url == "https://board.example.com/api/ingest"
    assert secrets.ingest_configured
    assert secrets.telegram_configured


def test_ingest_url_must_be_https(monkeypatch: pytest.MonkeyPatch, paper_env: None) -> None:
    monkeypatch.setenv("CF_INGEST_URL", "http://board.example.com/api/ingest")
    with pytest.raises(ConfigError):
        load_secrets()


def test_repo_settings_load() -> None:
    settings = load_settings()
    assert settings.timezone == "America/New_York"
    assert settings.http.retry.max_attempts >= 1


def test_settings_reject_unknown_keys(tmp_path: Path) -> None:
    path = tmp_path / "settings.yaml"
    path.write_text(
        "timezone: America/New_York\n"
        "http: {timeout_s: 5, retry: {max_attempts: 1, base_delay_s: 1, max_delay_s: 2}}\n"
        "typo_section: {}\n"
    )
    with pytest.raises(ConfigError):
        load_settings(path)


def test_settings_path_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "settings.yaml"
    path.write_text(
        "timezone: America/New_York\n"
        "http: {timeout_s: 5, retry: {max_attempts: 2, base_delay_s: 1, max_delay_s: 2}}\n"
    )
    monkeypatch.setenv("MB_SETTINGS_PATH", str(path))
    assert load_settings().http.retry.max_attempts == 2
