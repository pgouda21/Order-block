import { describe, expect, it } from "vitest";
import { applyRetention, retentionSessions } from "../src/retention";
import { FakeD1 } from "./d1";

const DAY = 86_400;
const BASE = Date.UTC(2026, 0, 5) / 1000; // a Monday, 00:00 UTC

function seed(d1: FakeD1, days: number, perDay = 3) {
  const snap = d1.db.prepare(
    "INSERT INTO board_snapshot (ts, session, data_asof, regime, payload) VALUES (?, 'x', ?, 'r', '{}')",
  );
  const card = d1.db.prepare(
    "INSERT INTO cards (ts, symbol, side, rank, score, reasons, zones) VALUES (?, 'AAPL', 'bull', 1, 50, '[]', '[]')",
  );
  for (let d = 0; d < days; d++) {
    for (let i = 0; i < perDay; i++) {
      // 14:00, 17:00, 20:00 UTC — inside the US regular session
      const ts = BASE + d * DAY + (14 + i * 3) * 3600;
      snap.run(ts, ts - 960);
      card.run(ts);
    }
  }
}

const count = (d1: FakeD1, table: string) =>
  Number((d1.db.prepare(`SELECT COUNT(*) AS n FROM ${table}`).get() as { n: number }).n);

describe("retention", () => {
  it("keeps exactly the most recent N sessions", async () => {
    const d1 = new FakeD1();
    seed(d1, 65);
    const cutoff = await applyRetention(d1.asD1(), 60);
    expect(cutoff).toBe(BASE + 5 * DAY);
    expect(count(d1, "board_snapshot")).toBe(60 * 3);
    expect(count(d1, "cards")).toBe(60 * 3);
  });

  it("is a no-op with fewer sessions than the window", async () => {
    const d1 = new FakeD1();
    seed(d1, 10);
    await applyRetention(d1.asD1(), 60);
    expect(count(d1, "board_snapshot")).toBe(30);
  });

  it("is a no-op on an empty database", async () => {
    await expect(applyRetention(new FakeD1().asD1(), 60)).resolves.toBeNull();
  });

  it.each(["0", "-1", "abc", "1.5", undefined])("rejects RETENTION_SESSIONS=%j", (raw) => {
    expect(() => retentionSessions(raw)).toThrow();
  });
});
