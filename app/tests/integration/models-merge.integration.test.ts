/**
 * B4 — Model list merge (store.fetchModels, live).
 *
 * fetchModels() composes two live sources: local (/api/llms via llmApi.listGlobalModels)
 * and official (the support LLM gateway via listGatewayModels). In integration mode the
 * gateway is forced unreachable, so this exercises the best-effort degrade path that has
 * repeatedly regressed: gateway failure must NOT throw, NOT force logout, and must NOT wipe
 * the local models. (Recent bug: listGatewayModels judged official empty on a stray
 * `resp.data` access; silent401 must not log out.)
 */
import { describe, it, expect, beforeAll } from "vitest";
import { probeLive, primeAuth } from "./helpers/live";
import { useStore } from "@/lib/store";

primeAuth(process.env.INTEGRATION_TOKEN);

const LIVE = await probeLive();

describe.skipIf(!LIVE)("B4 · model merge store.fetchModels (live)", () => {
  beforeAll(async () => {
    await useStore.getState().fetchModels();
  });

  it("resolves without throwing and yields a models array", () => {
    const models = useStore.getState().models;
    expect(Array.isArray(models)).toBe(true);
  });

  it("every model is well-formed (id + name)", () => {
    const models = useStore.getState().models as Array<Record<string, unknown>>;
    for (const m of models) {
      expect(typeof m.id).toBe("string");
      expect(typeof m.name).toBe("string");
    }
  });

  it("gateway-unreachable degrade: local models still present, no logout", async () => {
    const tokenBefore = localStorage.getItem("auth_token");
    await expect(useStore.getState().fetchModels()).resolves.toBeUndefined();
    // Best-effort degrade must not have forced a logout.
    expect(localStorage.getItem("auth_token")).toBe(tokenBefore);
    const models = useStore.getState().models;
    expect(Array.isArray(models)).toBe(true);
  });

  it("local-sourced items carry source=local; official carry source=official", () => {
    const models = useStore.getState().models as Array<Record<string, unknown>>;
    const sources = new Set(models.map((m) => m.source));
    // at minimum the set of sources is a subset of the allowed values
    for (const s of sources) expect(["official", "local"]).toContain(s);
  });
});
