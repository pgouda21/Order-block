"""Read-only Alpaca access: the ONLY module allowed to import `alpaca` (CLAUDE.md rule 1).

The SDK trading client is held privately and only read endpoints are exposed.
Never add a method that places, replaces, cancels or closes anything;
`tests/test_no_trading.py` greps the repo and fails the build if one appears.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from alpaca.trading.client import TradingClient
from alpaca.trading.models import Clock

from marketboard.config import require_paper_endpoint


@dataclass(frozen=True)
class MarketClock:
    timestamp: datetime
    is_open: bool
    next_open: datetime
    next_close: datetime


class ReadOnlyAlpaca:
    """Read-only facade over alpaca-py, pinned to the paper endpoint (rule 2)."""

    def __init__(self, api_key: str, secret_key: str, base_url: str, tz: ZoneInfo) -> None:
        require_paper_endpoint(base_url)  # abort before any client exists
        self._tz = tz
        self.__trading = TradingClient(api_key, secret_key, paper=True)

    def clock(self) -> MarketClock:
        raw = self.__trading.get_clock()
        if not isinstance(raw, Clock):
            raise TypeError("unexpected raw clock payload")
        return MarketClock(
            timestamp=raw.timestamp.astimezone(self._tz),
            is_open=raw.is_open,
            next_open=raw.next_open.astimezone(self._tz),
            next_close=raw.next_close.astimezone(self._tz),
        )
