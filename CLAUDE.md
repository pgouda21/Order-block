# CLAUDE.md — MarketBoard (v1.2)

Private US-market board for swing/position decisions (not day trading): ranks the strongest bullish/bearish stocks (S&P 500 ∪ Nasdaq-100), sector rotation, breadth, and order-block/liquidity zones on 1D/4H/1H. Full spec: `MarketBoard-Plan.md` — read it before any change. Work phase by phase (P0 → P5) and do not start a phase until the previous one's acceptance criteria pass.

## Hard rules (never violate)

1. **Read-only market data.** All Alpaca access goes through `scanner/marketboard/data/alpaca_client.py`. Never import or call order/position-mutating APIs (`submit_order`, `OrderRequest`, `MarketOrderRequest`, `LimitOrderRequest`, `close_position`, `close_all_positions`, `cancel_order*`, `replace_order`). `tests/test_no_trading.py` greps the repo and must stay green.
2. **Paper-account keys only.** `ALPACA_BASE_URL` must be the paper endpoint; startup aborts otherwise.
3. **Always pass `feed=` explicitly.** `sip` (delayed, `end <= now - 16 min` in market hours) is the ONLY source for scoring, volume, baselines and gaps. `iex` is used ONLY for live price / zone-touch triggers. Never compute RVOL, gaps or opens from IEX.
4. **No secrets in the repo.** Secrets come from env (`/etc/marketboard/env` on the VM, `wrangler secret` for the Worker). Provide `.env.example` only.
5. **Never public.** Every Worker route verifies the Cloudflare Access JWT (`Cf-Access-Jwt-Assertion`) against team certs. Ingest routes accept only the service-token identity. No route is unauthenticated.
6. **No personal or financial data** is collected or stored.
7. **Telegram** sends only to `TELEGRAM_CHAT_ID`; ignore all other chats. Messages contain tickers, zones and percentages only.
8. **Determinism + no look-ahead.** Detector/score functions are pure and take an explicit `asof`; they may only read bars with close time <= `asof`. Every signal carries `detected_at` (confirmation time, not candle time). `tests/test_no_lookahead.py` replays truncated series and asserts emitted signals never change. Backtests enter at the first bar open after `detected_at` plus costs.
9. All thresholds/weights live in `settings.yaml` — no magic numbers in code.
10. Time: ET (`America/New_York`) internally, PT in UI. Use the Alpaca calendar for holidays and early closes; never hard-code session times beyond defaults.
11. **Alerts are off until the P5 gate passes** (Plan §12). Only signal types that pass may alert; failing types are shown as "unvalidated". The signal ledger is append-only.
12. **Point-in-time universe** in backtests (`universe_history.csv`); never backtest on today's constituents only.
13. **My List is tickers only** (Plan §15). Never add quantity, cost basis or import fields. Every `/api/mylist` query is scoped to the verified Access JWT email.

## Stack

- **scanner/**: Python 3.12, `alpaca-py`, `pandas`, `numpy`, `apscheduler`, `httpx`, `pydantic-settings`, `pyyaml`; SQLite (stdlib) for cache. Tests: `pytest`. Lint: `ruff`. Types: `mypy --strict` on `detect/` and `score/`.
- **worker/**: TypeScript Cloudflare Worker with static assets, D1, `jose` for JWT verification, cron trigger for retention.
- **web/**: Vite + React + TypeScript, `lightweight-charts`. Mobile-first. Light/dark via `prefers-color-scheme` CSS variables.

## Layout

```
marketboard/
  CLAUDE.md
  MarketBoard-Plan.md
  scanner/
    pyproject.toml
    settings.yaml
    .env.example
    data/universe.csv
    data/universe_history.csv
    marketboard/
      config.py
      main.py                 # scheduler entrypoint
      data/   alpaca_client.py universe.py calendar.py baselines.py poller.py cache.py
      detect/ swings.py structure.py ob.py fvg.py liquidity.py chop.py indicators.py
      score/  scorer.py breadth.py sectors.py regime.py
      validate/ ledger.py forward.py null_baseline.py calibration.py walkforward.py decay.py
      alerts/ rules.py telegram.py
      digest/ premarket.py eod.py
      publish/cf_client.py
      backtest/ replay.py report.py
    tests/
      fixtures/               # synthetic candle CSVs per rule
      test_no_trading.py
      test_no_lookahead.py
      test_self_heal.py
      test_swings.py test_ob.py test_fvg.py test_liquidity.py test_chop.py test_scorer.py
    deploy/
      marketboard.service
      marketboard-nightly.service
      marketboard-nightly.timer
  worker/
    wrangler.toml
    migrations/0001_init.sql
    src/index.ts src/auth.ts src/routes/*.ts
  web/
    package.json vite.config.ts
    src/ App.tsx components/ Board.tsx SymbolSheet.tsx Alerts.tsx Digest.tsx ZoneChart.tsx MyList.tsx
```

## Commands

```bash
# scanner
cd scanner
python3.12 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
ruff check . && mypy marketboard/detect marketboard/score && pytest -q
python -m marketboard.main --once            # single poll cycle, prints board JSON, no publish
python -m marketboard.main --dry-run         # full scheduler, publish disabled
python -m marketboard.backtest.replay --start 2023-01-01 --end 2026-09-30
python -m marketboard.validate.calibration --report out/calibration.html
python -m marketboard.validate.walkforward --train-months 12 --test-months 3

# worker + web
cd worker
npx wrangler d1 create marketboard
npx wrangler d1 migrations apply marketboard --local
npx wrangler dev
cd ../web && npm ci && npm run build          # output consumed by worker static assets
cd ../worker && npx wrangler deploy
npx wrangler secret put ACCESS_TEAM_DOMAIN
npx wrangler secret put ACCESS_AUD
npx wrangler secret put INGEST_SERVICE_TOKEN_CLIENT_ID
```

## Env (`scanner/.env.example`)

```
ALPACA_API_KEY=
ALPACA_SECRET_KEY=
ALPACA_BASE_URL=https://paper-api.alpaca.markets
CF_INGEST_URL=https://<host>/api/ingest
CF_ACCESS_CLIENT_ID=
CF_ACCESS_CLIENT_SECRET=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
MB_DB_PATH=/var/lib/marketboard/cache.db
```

## Deploy (VM)

- Unprivileged user `marketboard`; code in `/opt/marketboard`, state in `/var/lib/marketboard`, env in `/etc/marketboard/env` (0600).
- systemd units include: `User=marketboard`, `EnvironmentFile=/etc/marketboard/env`, `ProtectSystem=strict`, `ReadWritePaths=/var/lib/marketboard`, `NoNewPrivileges=yes`, `PrivateTmp=yes`, `Restart=on-failure`.
- Outbound only. No listening ports.
- Oracle account must be on Pay As You Go (Always Free shapes only) to avoid idle reclamation; budget alert at $1.

## Conventions

- Cadence: SIP bar fetch every 5 min over an overlapping 60-min window with upsert (self-healing). Rolling 20-session baselines.
- Bars are `pandas.DataFrame` indexed by tz-aware ET timestamps with columns `open high low close volume vwap`.
- Zones are `[low, high]` floats rounded to tick (0.01).
- Every scored card carries `reasons: list[str]`; a score component that contributes points must append a reason.
- Publish failures: log, keep last board in SQLite, retry next cycle. Never crash the loop on one bad symbol.
- Respect HTTP 429 with exponential backoff + jitter; chunk multi-symbol requests.
- Commit per logical change; each PR updates tests. Do not edit `MarketBoard-Plan.md` thresholds silently — change `settings.yaml` and note it in the PR.

## Definition of done (per phase)

See `MarketBoard-Plan.md` §13. Report results against those criteria at the end of each phase before moving on.
