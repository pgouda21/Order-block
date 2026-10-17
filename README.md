# MarketBoard

A private US-market board for swing and position decisions, viewed on a private website (no Telegram needed). It ranks the strongest bullish and bearish names in the S&P 500 ∪ Nasdaq-100, and shows sector rotation, breadth and order-block / liquidity zones. It uses read-only market data with Alpaca paper keys, has no broker connection, and costs $0/month.

> Personal analytics tool. Not investment advice.

- **Spec**: [`MarketBoard-Plan.md`](MarketBoard-Plan.md)
- **Rules for contributors and agents**: [`CLAUDE.md`](CLAUDE.md)
- **Infra setup / P0 acceptance**: [`docs/P0-runbook.md`](docs/P0-runbook.md)

## Status

| Phase | State |
|---|---|
| P0 Infra | Code complete; acceptance pending your account setup ([runbook](docs/P0-runbook.md)) |
| P1–P5 | Not started (each waits for the previous phase's acceptance) |

## Layout

```
scanner/   Python 3.12 scanner (Oracle VM): config, read-only Alpaca client, ingest client, optional Telegram, systemd units
worker/    Cloudflare Worker: Access JWT verification on every route, ingest API, D1 schema, retention cron
web/       Vite + React UI served by the Worker as static assets (P0 shell; real UI in P3)
docs/      Runbooks
```

## Develop

```bash
cd scanner && python3.12 -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
ruff check . && mypy && pytest -q

cd web && npm ci && npm run build
cd worker && npm ci && npm run check      # typecheck, tests, wrangler dry-run bundle
```
