// POST /api/ingest/* — scanner → D1. Callers are already verified as the ingest service token.
import { error, json } from "../http";
import type { Env } from "../env";

/** Kinds defined in Plan §7; their handlers land with the phase that produces the data. */
const PLANNED_KINDS = new Set(["board", "alert", "digest", "calibration", "outcome"]);

export async function handleIngest(request: Request, _env: Env, kind: string): Promise<Response> {
  if (request.method !== "POST") {
    return error(405, "method not allowed");
  }
  if (kind === "ping") {
    return json({ ok: true });
  }
  if (PLANNED_KINDS.has(kind)) {
    return error(501, `ingest/${kind} is not implemented yet`);
  }
  return error(404, "not found");
}
