// Cloudflare Access JWT verification (CLAUDE.md rule 5). Every request, including static
// assets, is verified here against the team's signing keys. Fails closed.
import { createRemoteJWKSet, jwtVerify, type JWTVerifyGetKey } from "jose";
import type { Env } from "./env";

export type Identity =
  | { kind: "user"; email: string }
  | { kind: "service"; clientId: string };

/** Resolves the signing keys for an Access issuer. Injected so tests can use local keys. */
export type KeySource = (issuer: string) => JWTVerifyGetKey;

export class AuthError extends Error {
  constructor(
    readonly status: 401 | 403 | 500,
    message: string,
  ) {
    super(message);
  }
}

const remoteKeySets = new Map<string, JWTVerifyGetKey>();

/** Access publishes its rotating signing keys at <team>/cdn-cgi/access/certs. */
export const remoteKeySource: KeySource = (issuer) => {
  let keys = remoteKeySets.get(issuer);
  if (!keys) {
    keys = createRemoteJWKSet(new URL(`${issuer}/cdn-cgi/access/certs`));
    remoteKeySets.set(issuer, keys);
  }
  return keys;
};

export function accessIssuer(teamDomain: string): string {
  const host = teamDomain
    .trim()
    .replace(/^https?:\/\//, "")
    .replace(/\/+$/, "");
  return `https://${host}`;
}

export async function authenticate(
  request: Request,
  env: Env,
  keys: KeySource,
): Promise<Identity> {
  if (!env.ACCESS_TEAM_DOMAIN?.trim() || !env.ACCESS_AUD?.trim() || !env.INGEST_SERVICE_TOKEN_CLIENT_ID?.trim()) {
    throw new AuthError(500, "access verification is not configured");
  }
  const token = request.headers.get("Cf-Access-Jwt-Assertion");
  if (!token) {
    throw new AuthError(401, "missing access token");
  }
  const issuer = accessIssuer(env.ACCESS_TEAM_DOMAIN);
  let payload;
  try {
    ({ payload } = await jwtVerify(token, keys(issuer), {
      issuer,
      audience: env.ACCESS_AUD.trim(),
      algorithms: ["RS256"],
    }));
  } catch {
    throw new AuthError(401, "invalid access token");
  }
  // User logins carry an email; service tokens carry the token's client ID as common_name.
  if (typeof payload.email === "string" && payload.email !== "") {
    return { kind: "user", email: payload.email.toLowerCase() };
  }
  if (typeof payload.common_name === "string" && payload.common_name !== "") {
    return { kind: "service", clientId: payload.common_name };
  }
  throw new AuthError(403, "unrecognised access identity");
}

export function isIngestService(identity: Identity, env: Env): boolean {
  return identity.kind === "service" && identity.clientId === env.INGEST_SERVICE_TOKEN_CLIENT_ID.trim();
}
