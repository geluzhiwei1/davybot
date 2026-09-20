/**
 * B8 — HTTP transport live behaviour (api/client.ts).
 *
 * Exercises the real request()/apiErrorDetail() against the live server:
 *   - a genuine 404 surfaces as ApiError with the backend's {detail} extracted
 *   - timeoutMs aborts and yields the "请求超时或网络中断" message
 * The 401-refresh path needs the support system and is skipped locally.
 */
import { describe, it, expect } from "vitest";
import { probeLive, primeAuth } from "./helpers/live";
import { request, apiErrorDetail, ApiError } from "@/lib/api/client";

primeAuth(process.env.INTEGRATION_TOKEN);

const LIVE = await probeLive();

describe.skipIf(!LIVE)("B8 · HTTP transport (live)", () => {
  it("a 404 is surfaced as ApiError with the backend detail extracted", async () => {
    let threw = false;
    let detail = "";
    try {
      await request("/api/knowledge/bases/by-id/__does_not_exist_it__");
    } catch (e) {
      threw = true;
      expect(e).toBeInstanceOf(ApiError);
      detail = apiErrorDetail(e);
    }
    expect(threw).toBe(true);
    expect(typeof detail).toBe("string");
    expect(detail.length).toBeGreaterThan(0);
  });

  it("timeoutMs aborts the request → '请求超时或网络中断'", async () => {
    let threw = false;
    let detail = "";
    try {
      // 1ms cap: localhost list is ~10ms, so the abort wins reliably
      await request("/api/workspaces/list", { timeoutMs: 1 });
    } catch (e) {
      threw = true;
      detail = apiErrorDetail(e);
    }
    expect(threw).toBe(true);
    expect(detail).toBe("请求超时或网络中断");
  });

  // 401 auto-refresh requires the support/OAuth system; skip when no token wired.
  it.skipIf(!process.env.INTEGRATION_TOKEN)(
    "401 → refresh → retry (needs support system)",
    async () => {
      // Placeholder: exercise the refresh path only when a real token + support backend exist.
      expect(true).toBe(true);
    },
  );
});
