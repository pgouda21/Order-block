# MarketBoard — Build Plan (v1.2)

Private US-market board for **swing / position decisions** (hours to weeks, not day trading). Ranks the strongest bullish and bearish stocks across the market, shows sector rotation and breadth, and draws order-block / liquidity zones. No holdings, no broker connection, $0/month.

> Personal analytics tool. Not investment advice. Signals measure price/volume pressure, not buyer/seller identity. Smart Money Concepts are a popular framework, not a proven one — this system's job is to find out whether they work, and to say so when they don't.

## Changelog v1.1 → v1.2
- New: **My List** tab, a personal screener over a ticker list (stocks and ETFs). Tickers only: no quantities, cost basis or imports (§15).

## Changelog v1 → v1.1
- Use case changed from intraday to swing/position. Primary timeframes are now 1H / 4H / 1D; 15m is supporting only.
- **Delayed SIP (consolidated, ~15–20 min) is now the primary data** for all scoring, because it has correct full-market volume. IEX real-time is used only for live price and zone-touch triggers.
- Scan cadence changed from 60 s to 5 min. The latency requirement was rewritten honestly (§3.4).
- Fixed: Oracle idle-reclaim risk (account converted to PAYG, §11). Pricing corrected: the full-market paid plan is $99/mo, not $9.
- Fixed: repainting and look-ahead. Every signal carries `detected_at`, and the backtest acts only after it (§4.1).
- Fixed: survivorship bias (point-in-time universe, §3.2), IEX-based gaps (§9), bar-gap holes (self-healing bar fetch, §3.1), and rolling baselines.
- New: validation and learning layer (§12). **P5 validation is a hard gate before alerts go live.**

---

## 1. Requirements

**Functional**
- Board refreshed every 5 min during regular hours, with a daily close snapshot.
- Market pulse (SPY / QQQ / IWM trend, breadth) and sector flow (11 SPDR ETFs ranked by relative strength).
- Top 20 bullish and top 20 bearish, ranked by a swing strength score with reasons and zones (OB, FVG, support, resistance, liquidity).
- Outliers panel from the Alpaca screener, filtered for liquidity.
- Telegram alerts (after P5 gate), a pre-market digest at 06:00 PT and an EOD recap at 13:15 PT.
- Validation harness, calibration report and decision log.

**Non-functional**
- $0 base cost. Private (owner plus allowlist via Cloudflare Access).
- Freshness: live price within ~15 s of the poll; scores reflect data ≤ 20 min old (§3.4).

**Constraints**
- Personal Oracle and Cloudflare accounts only; nothing on company hardware or tenants.
- Only secret: an Alpaca **paper-account** key.

---

## 2. Architecture

```
Oracle Cloud A1 VM (account on PAYG; Always Free shapes still $0)
  marketboard.service  (Python 3.12, APScheduler, tz=America/New_York)
    data/      SIP bars (delayed, primary)  · IEX latest trades (live price)
               screener · clock/calendar · point-in-time universe
    detect/    swings → BOS → OB → FVG → liquidity/sweeps   (all stamped detected_at)
    score/     swing score + reasons · breadth · sector RS · regime tag
    validate/  signal ledger → forward returns → calibration / walk-forward / null baseline
    alerts/    rules + dedupe (persisted) → Telegram   [disabled until P5 gate passes]
    digest/    premarket · EOD
    publish/   HTTPS → Cloudflare ingest (Access service token)
    SQLite:    bar cache, baselines, signal ledger, alert dedupe
        │ outbound only
        ▼
Cloudflare: Access → Worker (static UI + /api) → D1
```

---

## 3. Data

### 3.1 Sources and cadence (Alpaca Basic, paper keys)

| Use | Call | Feed | Cadence |
|---|---|---|---|
| Scoring bars (5m, aggregated to 15m / 1H / 4H) | Multi-symbol bars, `end = now − 16 min`, last 60 min window, upsert | `sip` | every 5 min |
| Daily bars | Multi-symbol daily bars | `sip` | 16:20 ET + 09:00 ET (prior close) |
| Live price / zone-touch trigger | Multi-symbol latest trades | `iex` | every 5 min (alerts) |
| Baselines (ATR, RVOL curves) | 5m bars, **rolling 20 sessions** | `sip` | nightly 20:00 ET |
| Discovery | Screener most-actives / movers | — | every 15 min |
| Session state | Clock, calendar | — | startup + hourly |

The bar fetch always re-pulls an overlapping window and upserts, so a missed cycle self-heals. Budget: about 520 symbols in chunked multi-symbol calls uses roughly 10–20 requests per cycle, well under the 200/min limit. Back off on 429 with jitter.

### 3.2 Universe (point-in-time)
- `universe_history.csv`: `symbol, sector_etf, added, removed` for S&P 500 ∪ Nasdaq-100.
- Live board uses current members. **The backtest uses the members as of each historical date**, so removed names stay in and survivorship bias is avoided. If history is incomplete, the report must state the bias.
- Outliers outside the universe require price ≥ $5 and 20-day average dollar volume ≥ $20M.

### 3.3 IEX caveats
- IEX is about 4% of volume and its share has been growing, so IEX volume is never used for scoring.
- Opening and closing auctions and pre/post-market are thin or absent on IEX. Never derive gaps or the open from IEX; use the SIP daily bar.

### 3.4 Freshness budget

| Item | Freshness |
|---|---|
| Live price on board | ≤ 5 min poll + ~15 s pipeline |
| Scores / zones / volume | SIP delay 15–16 min + up to 5 min cycle ≈ **15–21 min** |
| Structure confirmation (pivot N bars right) | 15m: +30 min · 1H: +3 h · 1D: +3 sessions (by design, non-repainting) |

Every card shows `data_asof` and each signal's `detected_at`.

---

## 4. Detection rules (deterministic, non-repainting)

Thresholds live in `settings.yaml`. ATR = ATR(14) on the bar's own timeframe. Timeframes: **1D (primary), 4H, 1H**, with 15m used only for entry context.

| Concept | Rule |
|---|---|
| Swing high / low | Fractal pivot, N bars each side (15m/1H: N=2; 4H/1D: N=3). Confirmed only after N right-side bars close; `detected_at` = close of the Nth bar. |
| Displacement | Body ≥ 1.5×ATR, or 3-bar net move ≥ 2.0×ATR. |
| BOS | Close beyond the last confirmed opposite swing point. |
| Bullish OB | Last down-close candle before the displacement leg that produced the BOS. Zone `[low, high]` (wick) or `[open, low]` (body). `detected_at` = BOS bar close. Bearish mirrors. |
| OB state | fresh → tested → invalidated (close beyond far edge). |
| FVG | `low[i] > high[i-2]`, size ≥ 0.25×ATR; `detected_at` = bar i close. |
| Liquidity pools | ≥ 2 confirmed swings within 0.10×ATR; PDH/PDL; prior week high/low. |
| Sweep | Wick beyond a pool by ≤ 0.5×ATR, close back inside within 2 bars. |
| Chop | Efficiency ratio(10) < 0.30 or ADX(14) < 18 on **1H**. Penalty, not zeroing; threshold set by P5. |

### 4.1 Look-ahead rules
- Detector functions receive only bars with close time ≤ `asof`. A test feeds truncated series and asserts that outputs never change for any `asof` once emitted.
- The backtest enters only at the first bar **after** `detected_at`, at that bar's open plus a slippage assumption.

---

## 5. Swing strength score (0–100, signed)

| Component | Pts | Definition (SIP data) |
|---|---|---|
| Multi-day RVOL | 20 | 5-day avg volume / 50-day avg, capped at 2.5 |
| Trend alignment | 20 | Price vs 20/50-day MA, and 1D structure direction |
| Normalized move | 15 | 5-day return / daily ATR%, capped |
| 1D or 4H BOS in direction | 15 | Within the last 10 bars |
| Fresh OB in direction | 10 | Untested, within 1×ATR(1D) |
| FVG in direction | 5 | Unfilled, within 1×ATR(1D) |
| Sector alignment | 10 | Sector ETF RS rank top/bottom 3 over 5 and 20 days |
| Relative strength vs SPY | 5 | 20-day excess return percentile |
| Sweep against direction | −10 | Recent sweep on the trend side |
| Chop | −15 | Per §4 |

Weights are a **starting hypothesis**. P5 decides the final weights, and any component with no out-of-sample value is removed.

**Regime tag** on every snapshot: SPY above/below 50-day MA × VIX proxy (VIXY or SPY 20-day realized vol) high/low = 4 regimes.

---

## 6. Storage (D1)

```sql
CREATE TABLE board_snapshot (ts INTEGER PRIMARY KEY, session TEXT NOT NULL,
  data_asof INTEGER NOT NULL, regime TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE cards (ts INTEGER NOT NULL, symbol TEXT NOT NULL, side TEXT NOT NULL,
  rank INTEGER NOT NULL, score REAL NOT NULL, reasons TEXT NOT NULL, zones TEXT NOT NULL,
  bars TEXT, PRIMARY KEY (ts, symbol));
CREATE INDEX idx_cards_symbol_ts ON cards(symbol, ts);
CREATE TABLE alerts (id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER NOT NULL,
  symbol TEXT, kind TEXT NOT NULL, detail TEXT NOT NULL);
CREATE TABLE digests (date TEXT NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL,
  PRIMARY KEY (date, kind));
CREATE TABLE decisions (id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER NOT NULL,
  symbol TEXT NOT NULL, action TEXT NOT NULL,       -- would_buy | would_sell | skip | watch
  thesis TEXT, card_ts INTEGER, outcome TEXT);       -- outcome filled by scanner job
CREATE TABLE my_list (owner TEXT NOT NULL,      -- Access-authenticated email
  symbol TEXT NOT NULL, added INTEGER NOT NULL, PRIMARY KEY (owner, symbol));
CREATE TABLE calibration (run_date TEXT NOT NULL, horizon TEXT NOT NULL,
  regime TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY (run_date, horizon, regime));
```

Volume: about 78 snapshots × 46 rows per session ≈ 3.6k rows/day. Retention: snapshots and cards 60 sessions; the signal ledger stays on the VM indefinitely.

---

## 7. Worker API

| Method | Path | Auth |
|---|---|---|
| POST | `/api/ingest/{board,alert,digest,calibration,outcome}` | Access service token |
| POST | `/api/ingest/ping` (P0 connectivity check, no writes) | Access service token |
| GET | `/api/board/latest`, `/api/symbol/:sym`, `/api/alerts`, `/api/digest/:date/:kind`, `/api/calibration/latest` | Access user JWT |
| GET / POST / DELETE | `/api/mylist`, `/api/mylist/:sym` | Access user JWT (scoped to the JWT email) |
| POST | `/api/decisions` | Access user JWT |
| GET | `/api/decisions` | Access user JWT |

The Worker verifies `Cf-Access-Jwt-Assertion` on every request; ingest routes also require the service-token identity.

---

## 8. UI (mobile-first)

1. **Board**: Pulse with regime tag → Sector RS → Bull / Bear top 20 → Outliers. Header shows `data_asof`; a stale badge appears at > 25 min.
2. **Symbol sheet**: 1D / 4H / 1H chart with zones, score breakdown, reasons, each signal's `detected_at`, and the **historical hit rate for this signal type in the current regime** (from §12).
3. **Decision log**: one tap for would-buy / would-sell / skip / watch plus a one-line thesis; outcomes appear automatically at 5 and 20 days.
4. **Calibration**: score-decile chart, signal scorecards, last walk-forward result.
5. **My List** (§15).
6. **Alerts** and **Digests**.

---

## 9. Alerts & digests

Alerts are **disabled until the P5 gate passes**, and only signal types that pass are enabled.
- `zone_touch`: live IEX price enters a fresh 1D/4H OB of a top-20 name.
- `top5_entry`: a name enters bull/bear top 5 (once per day).
- `sweep_reclaim`: a 1D/4H liquidity sweep and reclaim on a top-20 name.
- `sector_flip`: sector ETF moves from top-3 to bottom-3 RS (or the reverse) on the 5-day window.

Dedupe is persisted in SQLite (survives restarts): symbol + kind once per day; cap 10/day.

**Pre-market digest (06:00 PT)**: prior close from SIP daily, IEX pre-market moves **labelled indicative**, fresh 1D OBs within 3% of price, sector 5-day ranks, regime.
**EOD recap (13:15 PT)**: final ranks, sector rotation, new 1D structures, decision-log outcomes due.

---

## 10. Schedule (ET, calendar-aware)

| Time | Job |
|---|---|
| 09:00 | Pre-market digest |
| 09:45–16:15 every 5 min | SIP bars (delayed) → detect → score → publish; IEX price → zone touches |
| Every 15 min | Screener refresh |
| 16:20 | EOD recap, daily bars, signal-ledger forward-return update, decision outcomes |
| 20:00 | Rolling baselines |
| Sat 08:00 | Weekly calibration + walk-forward report (§12) |

---

## 11. Security & hosting

- Oracle account converted to **Pay As You Go** to avoid idle reclamation of the A1 VM. Use Always Free shapes only, and set a $1 budget alert.
- Secrets in `/etc/marketboard/env` (0600, `marketboard` user): Alpaca paper key, Telegram token, Access service token.
- No trading path: read-only Alpaca wrapper; CI grep test for order or position calls; startup aborts unless the paper endpoint is configured.
- VM: key-only SSH from owner IP, no other inbound; systemd hardening; automatic security updates.
- Cloudflare Access for owner plus allowlist; Worker verifies the JWT itself. No personal or financial data stored.

---

## 12. Validation & learning layer

The goal is the rigor quant firms apply, scaled to one person.

1. **Signal ledger**: every signal (`symbol, type, timeframe, direction, detected_at, zone, score, regime`) is written once and never edited.
2. **Forward returns**: +1, +5 and +20 trading days measured from the next bar's open after `detected_at`, net of a 5 bp round-trip cost and 5 bp slippage; plus MAE/MFE (worst and best excursion).
3. **Null baseline**: for each signal, 20 random entries in the same universe, same direction, same calendar week. A signal type must beat its null to count.
4. **Score calibration**: forward return by score decile, per regime. Pass condition: top decile beats bottom decile and beats the null, out of sample.
5. **Walk-forward**: tune on a rolling 12-month window, test on the next 3 months, roll quarterly. Report degradation from in-sample to out-of-sample.
6. **Overfitting guard**: hold out the most recent 3 months untouched until the end; at most 3 tuning iterations; report how many parameter sets were tried.
7. **Decay monitor**: weekly rolling 60-day out-of-sample hit rate per signal type; a type is auto-disabled from alerts if it drops below its null for 4 consecutive weeks.
8. **Decision log**: your would-buy / would-sell calls are scored like signals, showing whether your judgment adds value on top of the board.

**P5 gate (blocks alerts)**: at least 3 years of SIP history replayed; at least 200 signals per enabled type; top-decile minus bottom-decile 20-day return > 0 with bootstrap 90% CI excluding 0; beats the null out of sample. Types that fail stay visible on the board, marked "unvalidated", and never alert.

---

## 13. Phases & acceptance

| Phase | Done when |
|---|---|
| P0 Infra | Access blocks unauthenticated requests; service-token ingest returns 200; Telegram test message arrives; Oracle PAYG plus budget alert in place |
| P1 Data | One week of runs: ≥ 99% of 5-min cycles complete; self-heal verified by killing the service mid-session |
| P2 Detect + score | Fixture tests for every rule; look-ahead invariance test passes |
| P3 UI | Board, symbol sheet, decision log and My List usable on phone; stale badge works |
| P4 Digests | Both digests on time for 5 sessions (alerts still off) |
| P5 Validate | §12 report generated; gate evaluated per signal type; passing types enabled for alerts |

---

## 14. Trade-offs & revisit

| Decision | Trade-off | Revisit when |
|---|---|---|
| Delayed SIP for scoring | 15–20 min lag, irrelevant for swing horizon | Never for swing; $99/mo plan only if intraday becomes the goal |
| 5-min cadence | Less load, fully adequate for 1H/1D | — |
| Rule-based score | Transparent, low overfitting risk | Gate passes and more history accumulates → simple regularized regression on the same features |
| No fundamentals / alt data | Pure technical | Add earnings dates (avoid holding through earnings) as the first extra feature |

---

## 15. My List (personal screener)

**Scope**: a list of tickers (US stocks and ETFs, max 50 per user) shown as the same cards as the main board. No quantities, cost basis, CSV import or portfolio math.

**Behaviour**
- Add a ticker: the Worker inserts into `my_list`; the scanner pulls the union of all `my_list` symbols every cycle (`GET /api/ingest/mylist-symbols`, service token) and validates each as an active Alpaca asset. Invalid symbols are flagged in the UI, not dropped silently.
- My List symbols join the scan universe, so they are scored every cycle even if they are not S&P 500 / Nasdaq-100 members. The liquidity floor does not apply to them.
- Cards show price, day and 5-day %, score, overall rank (or "unranked"), zones, reasons and `detected_at`, sorted by score (toggle: alphabetical).
- **ETFs** (Alpaca asset attribute, or `etf` flag in `settings.yaml`): the sector-alignment component is replaced by relative strength vs SPY over 5/20 days. All other components are unchanged.
- Alerts for My List names follow the same P5 gate. Only validated signal types alert, deduped as in §9.

**Privacy**
- Every My List query is scoped to the email in the verified Access JWT, never a client-supplied value. Other allowlist users cannot see your list.
- Tickers only; nothing else personal is stored.

**Acceptance**: add and remove on phone; a new ticker is scored within 2 cycles; an invalid ticker is flagged; a second allowlist account sees an empty list.
