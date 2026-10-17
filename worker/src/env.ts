export interface Env {
  DB: D1Database;
  ASSETS: Fetcher;
  /** e.g. "yourteam.cloudflareaccess.com" (secret) */
  ACCESS_TEAM_DOMAIN: string;
  /** Access application AUD tag (secret) */
  ACCESS_AUD: string;
  /** Client ID of the scanner's Access service token (secret) */
  INGEST_SERVICE_TOKEN_CLIENT_ID: string;
  /** Sessions of board snapshots and cards to keep (Plan §6) */
  RETENTION_SESSIONS: string;
}
