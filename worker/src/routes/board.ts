// GET /api/board/latest — most recent board snapshot (Plan §7).
import { error, json } from "../http";
import type { Env } from "../env";

interface SnapshotRow {
  ts: number;
  session: string;
  data_asof: number;
  regime: string;
  payload: string;
}

export async function latestBoard(env: Env): Promise<Response> {
  const row = await env.DB.prepare(
    "SELECT ts, session, data_asof, regime, payload FROM board_snapshot ORDER BY ts DESC LIMIT 1",
  ).first<SnapshotRow>();
  if (!row) {
    return error(404, "no board published yet");
  }
  return json({
    ts: row.ts,
    session: row.session,
    data_asof: row.data_asof,
    regime: row.regime,
    payload: JSON.parse(row.payload) as unknown,
  });
}
