import { describe, expect, it } from "vitest";
import { createHandler } from "../src/index";
import { SERVICE_ID, makeEnv, makeKeys, request } from "./helpers";

async function setup() {
  const keys = await makeKeys();
  const handler = createHandler(keys.source);
  const env = makeEnv();
  const ctx = { waitUntil: () => undefined, passThroughOnException: () => undefined } as unknown as ExecutionContext;
  const fetch = (req: Request) => handler.fetch!(req as Request<unknown, IncomingRequestCfProperties>, env, ctx);
  return {
    env,
    fetch,
    user: await keys.sign({ email: "owner@example.com" }),
    service: await keys.sign({ common_name: SERVICE_ID }),
    otherService: await keys.sign({ common_name: "someone-else.access" }),
  };
}

describe("every route requires Access", () => {
  it.each(["/", "/index.html", "/assets/app.js", "/api/board/latest", "/api/ingest/ping", "/api/nope"])(
    "%s without a token is 401 and never reaches assets",
    async (path) => {
      const { fetch, env } = await setup();
      const res = await fetch(request(path, undefined, { method: path.includes("ingest") ? "POST" : "GET" }));
      expect(res.status).toBe(401);
      expect(env.assetRequests).toHaveLength(0);
    },
  );
});

describe("ingest", () => {
  it("ping returns 200 for the scanner service token", async () => {
    const { fetch, service } = await setup();
    const res = await fetch(request("/api/ingest/ping", service, { method: "POST", body: "{}" }));
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ ok: true });
  });

  it("rejects user logins", async () => {
    const { fetch, user } = await setup();
    const res = await fetch(request("/api/ingest/ping", user, { method: "POST" }));
    expect(res.status).toBe(403);
  });

  it("rejects other service tokens", async () => {
    const { fetch, otherService } = await setup();
    const res = await fetch(request("/api/ingest/ping", otherService, { method: "POST" }));
    expect(res.status).toBe(403);
  });

  it("requires POST", async () => {
    const { fetch, service } = await setup();
    expect((await fetch(request("/api/ingest/ping", service))).status).toBe(405);
  });

  it("planned kinds are 501 until their phase, unknown kinds 404", async () => {
    const { fetch, service } = await setup();
    const post = (kind: string) => fetch(request(`/api/ingest/${kind}`, service, { method: "POST", body: "{}" }));
    expect((await post("board")).status).toBe(501);
    expect((await post("ping/extra")).status).toBe(404);
    expect((await post("orders")).status).toBe(404);
  });
});

describe("user routes", () => {
  it("serves the UI to signed-in users", async () => {
    const { fetch, user, env } = await setup();
    const res = await fetch(request("/", user));
    expect(res.status).toBe(200);
    expect(env.assetRequests).toHaveLength(1);
  });

  it("service tokens cannot read user routes or the UI", async () => {
    const { fetch, service, env } = await setup();
    expect((await fetch(request("/", service))).status).toBe(403);
    expect((await fetch(request("/api/board/latest", service))).status).toBe(403);
    expect(env.assetRequests).toHaveLength(0);
  });

  it("board/latest is 404 before the first publish", async () => {
    const { fetch, user } = await setup();
    const res = await fetch(request("/api/board/latest", user));
    expect(res.status).toBe(404);
    expect(res.headers.get("cache-control")).toBe("no-store");
  });

  it("board/latest returns the newest snapshot", async () => {
    const { fetch, user, env } = await setup();
    const insert = env.d1.db.prepare(
      "INSERT INTO board_snapshot (ts, session, data_asof, regime, payload) VALUES (?, ?, ?, ?, ?)",
    );
    insert.run(1000, "2026-10-15", 900, "bull_lowvol", JSON.stringify({ n: 1 }));
    insert.run(2000, "2026-10-16", 1900, "bull_lowvol", JSON.stringify({ n: 2 }));
    const res = await fetch(request("/api/board/latest", user));
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({
      ts: 2000,
      session: "2026-10-16",
      data_asof: 1900,
      regime: "bull_lowvol",
      payload: { n: 2 },
    });
  });

  it("unknown API paths are 404, not the SPA shell", async () => {
    const { fetch, user, env } = await setup();
    expect((await fetch(request("/api/mylist", user))).status).toBe(404);
    expect(env.assetRequests).toHaveLength(0);
  });
});
