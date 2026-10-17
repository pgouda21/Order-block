import { SignJWT, createLocalJWKSet, exportJWK, generateKeyPair, type JWTPayload } from "jose";
import type { KeySource } from "../src/auth";
import type { Env } from "../src/env";
import { FakeD1 } from "./d1";

export const TEAM = "myteam.cloudflareaccess.com";
export const ISSUER = `https://${TEAM}`;
export const AUD = "aud-tag-123";
export const SERVICE_ID = "scanner-token.access";

export interface Keys {
  sign(claims: JWTPayload, opts?: { issuer?: string; audience?: string; expiresIn?: string }): Promise<string>;
  source: KeySource;
  issuersSeen: string[];
}

export async function makeKeys(): Promise<Keys> {
  const { publicKey, privateKey } = await generateKeyPair("RS256");
  const jwk = { ...(await exportJWK(publicKey)), kid: "k1", alg: "RS256" };
  const local = createLocalJWKSet({ keys: [jwk] });
  const issuersSeen: string[] = [];
  return {
    issuersSeen,
    source: (issuer) => {
      issuersSeen.push(issuer);
      return local;
    },
    sign: (claims, opts = {}) =>
      new SignJWT(claims)
        .setProtectedHeader({ alg: "RS256", kid: "k1" })
        .setIssuedAt()
        .setIssuer(opts.issuer ?? ISSUER)
        .setAudience(opts.audience ?? AUD)
        .setExpirationTime(opts.expiresIn ?? "5m")
        .sign(privateKey),
  };
}

export function makeEnv(overrides: Partial<Env> = {}): Env & { assetRequests: Request[]; d1: FakeD1 } {
  const assetRequests: Request[] = [];
  const d1 = new FakeD1();
  return {
    DB: d1.asD1(),
    ASSETS: {
      fetch: async (input: RequestInfo | URL) => {
        assetRequests.push(input as Request);
        return new Response("<!doctype html>", { headers: { "content-type": "text/html" } });
      },
    } as unknown as Fetcher,
    ACCESS_TEAM_DOMAIN: TEAM,
    ACCESS_AUD: AUD,
    INGEST_SERVICE_TOKEN_CLIENT_ID: SERVICE_ID,
    RETENTION_SESSIONS: "60",
    assetRequests,
    d1,
    ...overrides,
  };
}

export function request(path: string, token?: string, init: RequestInit = {}): Request {
  const headers = new Headers(init.headers);
  if (token) {
    headers.set("Cf-Access-Jwt-Assertion", token);
  }
  return new Request(`https://board.example.com${path}`, { ...init, headers });
}
