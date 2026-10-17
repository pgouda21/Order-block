// MarketBoard Worker: static UI + /api, behind Cloudflare Access. No route is unauthenticated.
import { AuthError, authenticate, isIngestService, remoteKeySource, type KeySource } from "./auth";
import type { Env } from "./env";
import { error } from "./http";
import { applyRetention, retentionSessions } from "./retention";
import { latestBoard } from "./routes/board";
import { handleIngest } from "./routes/ingest";

const INGEST_PREFIX = "/api/ingest/";

export function createHandler(keys: KeySource): ExportedHandler<Env> {
  return {
    async fetch(request, env) {
      let identity;
      try {
        identity = await authenticate(request, env, keys);
      } catch (err) {
        if (err instanceof AuthError) {
          return error(err.status, err.message);
        }
        throw err;
      }

      const { pathname } = new URL(request.url);
      if (pathname.startsWith(INGEST_PREFIX)) {
        if (!isIngestService(identity, env)) {
          return error(403, "ingest requires the scanner service token");
        }
        return handleIngest(request, env, pathname.slice(INGEST_PREFIX.length));
      }

      // Everything else (API reads and the UI itself) is for signed-in people only.
      if (identity.kind !== "user") {
        return error(403, "user login required");
      }
      if (pathname === "/api/board/latest" && request.method === "GET") {
        return latestBoard(env);
      }
      if (pathname === "/api" || pathname.startsWith("/api/")) {
        return error(404, "not found");
      }
      return env.ASSETS.fetch(request);
    },

    async scheduled(_controller, env, ctx) {
      ctx.waitUntil(applyRetention(env.DB, retentionSessions(env.RETENTION_SESSIONS)));
    },
  };
}

export default createHandler(remoteKeySource);
