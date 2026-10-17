// Daily cron: keep board snapshots and cards for the most recent N sessions (Plan §6).
// A session is a distinct UTC date of `ts`; the whole US regular session falls on one UTC date.

export function retentionSessions(raw: string | undefined): number {
  const value = Number(raw);
  if (!Number.isInteger(value) || value < 1) {
    throw new Error(`RETENTION_SESSIONS must be a positive integer, got ${JSON.stringify(raw)}`);
  }
  return value;
}

export async function applyRetention(db: D1Database, sessions: number): Promise<number | null> {
  const row = await db
    .prepare(
      `SELECT MIN(day) AS cutoff FROM (
         SELECT DISTINCT date(ts, 'unixepoch') AS day FROM board_snapshot ORDER BY day DESC LIMIT ?
       )`,
    )
    .bind(sessions)
    .first<{ cutoff: string | null }>();
  if (!row?.cutoff) {
    return null;
  }
  const cutoffTs = Date.parse(`${row.cutoff}T00:00:00Z`) / 1000;
  await db.batch([
    db.prepare("DELETE FROM board_snapshot WHERE ts < ?").bind(cutoffTs),
    db.prepare("DELETE FROM cards WHERE ts < ?").bind(cutoffTs),
  ]);
  return cutoffTs;
}
