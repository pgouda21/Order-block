-- MarketBoard D1 schema (Plan §6).
-- All timestamps (ts, data_asof, added, card_ts) are Unix epoch seconds, UTC.
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
