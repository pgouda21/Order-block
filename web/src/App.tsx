import { useEffect, useState } from "react";

// P0 shell: proves the Access → Worker → D1 path from a phone. The board UI arrives in P3.
type ApiState =
  | { kind: "loading" }
  | { kind: "empty" }
  | { kind: "board"; dataAsof: number }
  | { kind: "error"; status: number | null };

function formatPt(epochSeconds: number): string {
  return new Intl.DateTimeFormat("en-US", {
    timeZone: "America/Los_Angeles",
    dateStyle: "medium",
    timeStyle: "short",
    timeZoneName: "short",
  }).format(new Date(epochSeconds * 1000));
}

export function App() {
  const [api, setApi] = useState<ApiState>({ kind: "loading" });

  useEffect(() => {
    fetch("/api/board/latest", { credentials: "same-origin" })
      .then(async (res) => {
        if (res.status === 404) return setApi({ kind: "empty" });
        if (!res.ok) return setApi({ kind: "error", status: res.status });
        const body = (await res.json()) as { data_asof: number };
        setApi({ kind: "board", dataAsof: body.data_asof });
      })
      .catch(() => setApi({ kind: "error", status: null }));
  }, []);

  return (
    <main>
      <h1>MarketBoard</h1>
      <p className="status" role="status">
        {api.kind === "loading" && "Checking API…"}
        {api.kind === "empty" && "Signed in. API reachable. No board published yet."}
        {api.kind === "board" && `Signed in. Latest board data as of ${formatPt(api.dataAsof)}.`}
        {api.kind === "error" && `API error${api.status ? ` (HTTP ${api.status})` : ""}.`}
      </p>
      <p className="muted">The board, symbol sheet, decision log and My List arrive in P3.</p>
      <footer className="muted">Personal analytics tool. Not investment advice.</footer>
    </main>
  );
}
