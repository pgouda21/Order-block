import { describe, expect, it } from "vitest";
import { AuthError, accessIssuer, authenticate } from "../src/auth";
import { AUD, ISSUER, SERVICE_ID, makeEnv, makeKeys, request } from "./helpers";

async function authError(promise: Promise<unknown>): Promise<AuthError> {
  try {
    await promise;
  } catch (err) {
    expect(err).toBeInstanceOf(AuthError);
    return err as AuthError;
  }
  throw new Error("expected authentication to fail");
}

describe("accessIssuer", () => {
  it.each(["myteam.cloudflareaccess.com", "https://myteam.cloudflareaccess.com/", " myteam.cloudflareaccess.com "])(
    "normalises %j",
    (domain) => expect(accessIssuer(domain)).toBe(ISSUER),
  );
});

describe("authenticate", () => {
  it("accepts a user login and lower-cases the email", async () => {
    const keys = await makeKeys();
    const token = await keys.sign({ email: "Owner@Example.com", sub: "u1" });
    await expect(authenticate(request("/", token), makeEnv(), keys.source)).resolves.toEqual({
      kind: "user",
      email: "owner@example.com",
    });
    expect(keys.issuersSeen).toEqual([ISSUER]);
  });

  it("accepts a service token by common_name", async () => {
    const keys = await makeKeys();
    const token = await keys.sign({ common_name: SERVICE_ID, sub: "" });
    await expect(authenticate(request("/", token), makeEnv(), keys.source)).resolves.toEqual({
      kind: "service",
      clientId: SERVICE_ID,
    });
  });

  it("rejects a missing token with 401", async () => {
    const keys = await makeKeys();
    const err = await authError(authenticate(request("/"), makeEnv(), keys.source));
    expect(err.status).toBe(401);
  });

  it.each([
    ["wrong audience", { audience: "other-aud" }],
    ["wrong issuer", { issuer: "https://evil.cloudflareaccess.com" }],
    ["expired", { expiresIn: "-1m" }],
  ])("rejects %s with 401", async (_label, opts) => {
    const keys = await makeKeys();
    const token = await keys.sign({ email: "owner@example.com" }, opts);
    const err = await authError(authenticate(request("/", token), makeEnv(), keys.source));
    expect(err.status).toBe(401);
  });

  it("rejects a token signed by another key", async () => {
    const trusted = await makeKeys();
    const attacker = await makeKeys();
    const token = await attacker.sign({ email: "owner@example.com" });
    const err = await authError(authenticate(request("/", token), makeEnv(), trusted.source));
    expect(err.status).toBe(401);
  });

  it("rejects an unsigned (alg none) token", async () => {
    const keys = await makeKeys();
    const encode = (o: object) => Buffer.from(JSON.stringify(o)).toString("base64url");
    const now = Math.floor(Date.now() / 1000);
    const token = `${encode({ alg: "none" })}.${encode({ email: "owner@example.com", iss: ISSUER, aud: AUD, exp: now + 60 })}.`;
    const err = await authError(authenticate(request("/", token), makeEnv(), keys.source));
    expect(err.status).toBe(401);
  });

  it("rejects a valid token with no identity claim with 403", async () => {
    const keys = await makeKeys();
    const token = await keys.sign({ sub: "x" });
    const err = await authError(authenticate(request("/", token), makeEnv(), keys.source));
    expect(err.status).toBe(403);
  });

  it.each(["ACCESS_TEAM_DOMAIN", "ACCESS_AUD", "INGEST_SERVICE_TOKEN_CLIENT_ID"] as const)(
    "fails closed with 500 when %s is unset",
    async (key) => {
      const keys = await makeKeys();
      const token = await keys.sign({ email: "owner@example.com" });
      const err = await authError(authenticate(request("/", token), makeEnv({ [key]: "" }), keys.source));
      expect(err.status).toBe(500);
    },
  );
});
