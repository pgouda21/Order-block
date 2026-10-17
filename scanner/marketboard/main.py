"""Scanner entrypoint.

P0 provides only `--selftest`. The scheduler (`--once`, `--dry-run`, the default
loop) arrives in P1 once the P0 acceptance checks pass (CLAUDE.md).
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime

import httpx

from marketboard.alerts.telegram import TelegramClient
from marketboard.config import ConfigError, Secrets, Settings, load_secrets, load_settings
from marketboard.data.alpaca_client import ReadOnlyAlpaca
from marketboard.publish.cf_client import IngestClient
from marketboard.selftest import format_results, run_checks

log = logging.getLogger("marketboard")


def selftest(secrets: Secrets, settings: Settings, http: httpx.Client) -> int:
    alpaca = ReadOnlyAlpaca(
        secrets.alpaca_api_key.get_secret_value(),
        secrets.alpaca_secret_key.get_secret_value(),
        secrets.alpaca_base_url,
        settings.tz,
    )
    ingest = None
    if secrets.ingest_configured:
        assert secrets.cf_ingest_url and secrets.cf_access_client_id
        assert secrets.cf_access_client_secret
        ingest = IngestClient(
            secrets.cf_ingest_url,
            secrets.cf_access_client_id.get_secret_value(),
            secrets.cf_access_client_secret.get_secret_value(),
            http,
            settings.http.retry,
        )
    telegram = None
    if secrets.telegram_configured:
        assert secrets.telegram_bot_token and secrets.telegram_chat_id
        telegram = TelegramClient(
            secrets.telegram_bot_token.get_secret_value(),
            secrets.telegram_chat_id,
            http,
            settings.http.retry,
        )
    hidden = [
        s.get_secret_value()
        for s in (
            secrets.alpaca_api_key,
            secrets.alpaca_secret_key,
            secrets.cf_access_client_secret,
            secrets.telegram_bot_token,
        )
        if s is not None
    ]
    results = run_checks(
        alpaca=alpaca,
        ingest=ingest,
        telegram=telegram,
        now=datetime.now(UTC),
        secrets_to_redact=hidden,
    )
    print(format_results(results))
    return 0 if all(r.ok for r in results) else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="marketboard")
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="P0 check: paper config, Alpaca clock, ingest ping (Telegram only if configured)",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    # httpx logs full request URLs at INFO, and the Telegram URL embeds the bot token.
    logging.getLogger("httpx").setLevel(logging.WARNING)

    try:
        settings = load_settings()
        secrets = load_secrets()
    except ConfigError as exc:
        log.critical("startup aborted: %s", exc)
        return 1

    if not args.selftest:
        log.error("the scheduler arrives in P1; only --selftest is available in P0")
        return 2

    with httpx.Client(timeout=settings.http.timeout_s) as http:
        return selftest(secrets, settings, http)


if __name__ == "__main__":
    sys.exit(main())
