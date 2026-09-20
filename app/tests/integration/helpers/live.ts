/**
 * Live-backend helpers for Part B integration tests.
 *
 * Every test file resolves `LIVE` via top-level await, then gates its suite with
 * `describe.skipIf(!LIVE)` — so `pnpm test:integration` is green even when the
 * backend isn't running (it just reports skips), and runs for real when it is.
 */
export const INTEGRATION_TARGET = process.env.INTEGRATION_TARGET || "http://localhost:8010";

const PROBE_PATHS = ["/api/workspaces/list", "/api/system/info", "/api/knowledge/bases"];

/** True if the dawei backend answers any read-only probe with < 500. */
export async function probeLive(target: string = INTEGRATION_TARGET): Promise<boolean> {
  for (const path of PROBE_PATHS) {
    try {
      const ctrl = new AbortController();
      const timer = setTimeout(() => ctrl.abort(), 3000);
      const res = await fetch(`${target}${path}`, { signal: ctrl.signal });
      clearTimeout(timer);
      if (res.status < 500) return true;
    } catch {
      // try next probe
    }
  }
  return false;
}

/** Set the auth token the frontend's request() reads from localStorage (optional). */
export function primeAuth(token?: string): void {
  if (token) localStorage.setItem("auth_token", token);
  else localStorage.removeItem("auth_token");
}

/** Whether LLM/embedding-dependent tests should run. */
export const LLM_ENABLED = process.env.DAWEI_TEST_LLM === "1";
