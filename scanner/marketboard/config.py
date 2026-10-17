"""Configuration: secrets from the environment, tunables from settings.yaml.

Secrets come only from the environment (`/etc/marketboard/env` on the VM, CLAUDE.md rule 4).
Everything else, including every threshold, lives in `settings.yaml` (rule 9).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Safety invariant, not a tunable: it deliberately lives in code so that editing
# settings.yaml or the env file can never point the scanner at a live account.
PAPER_BASE_URL = "https://paper-api.alpaca.markets"

DEFAULT_SETTINGS_PATH = Path(__file__).resolve().parents[1] / "settings.yaml"


class ConfigError(RuntimeError):
    """Configuration is missing or unsafe. Startup must abort."""


def require_paper_endpoint(base_url: str) -> str:
    """Return the normalised paper URL, or raise ConfigError for anything else (rule 2)."""
    normalised = base_url.strip().rstrip("/").removesuffix("/v2")
    if normalised != PAPER_BASE_URL:
        raise ConfigError(
            f"ALPACA_BASE_URL must be the paper endpoint {PAPER_BASE_URL}; refusing to start"
        )
    return normalised


class Secrets(BaseSettings):
    """Values read from the environment. Field names map to upper-case env vars."""

    model_config = SettingsConfigDict(extra="ignore", frozen=True)

    alpaca_api_key: SecretStr = Field(min_length=1)
    alpaca_secret_key: SecretStr = Field(min_length=1)
    alpaca_base_url: str
    # Optional until the job that needs them runs; the self-test reports them as missing.
    cf_ingest_url: str | None = None
    cf_access_client_id: SecretStr | None = None
    cf_access_client_secret: SecretStr | None = None
    telegram_bot_token: SecretStr | None = None
    telegram_chat_id: str | None = None
    mb_db_path: Path = Path("/var/lib/marketboard/cache.db")

    @field_validator("alpaca_base_url")
    @classmethod
    def _paper_only(cls, value: str) -> str:
        return require_paper_endpoint(value)

    @field_validator("cf_ingest_url")
    @classmethod
    def _https_only(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        parts = urlsplit(value)
        if parts.scheme != "https" or not parts.netloc:
            raise ValueError("CF_INGEST_URL must be an https:// URL")
        return value.rstrip("/")

    @field_validator("telegram_chat_id")
    @classmethod
    def _blank_is_none(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        return value.strip()

    @property
    def ingest_configured(self) -> bool:
        return bool(
            self.cf_ingest_url and self.cf_access_client_id and self.cf_access_client_secret
        )

    @property
    def telegram_configured(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)


class RetrySettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_attempts: int = Field(ge=1)
    base_delay_s: float = Field(gt=0)
    max_delay_s: float = Field(gt=0)


class HttpSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    timeout_s: float = Field(gt=0)
    retry: RetrySettings


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    timezone: str
    http: HttpSettings

    @field_validator("timezone")
    @classmethod
    def _known_zone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"unknown timezone {value!r}") from exc
        return value

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


def load_settings(path: Path | None = None) -> Settings:
    """Load settings.yaml (override the location with MB_SETTINGS_PATH)."""
    if path is None:
        path = Path(os.environ.get("MB_SETTINGS_PATH", DEFAULT_SETTINGS_PATH))
    try:
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
        return Settings.model_validate(raw)
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        raise ConfigError(f"invalid settings file {path}: {exc}") from exc


def load_secrets() -> Secrets:
    """Read secrets from the environment, aborting on a missing key or a non-paper endpoint."""
    try:
        return Secrets()  # type: ignore[call-arg]  # populated from the environment
    except ValidationError as exc:
        # Report field names only; never echo values, which may be secrets.
        fields = ", ".join(".".join(str(p) for p in err["loc"]) or "?" for err in exc.errors())
        reasons = "; ".join(err["msg"] for err in exc.errors())
        raise ConfigError(f"invalid environment ({fields}): {reasons}") from None
