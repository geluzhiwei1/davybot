/**
 * B3 — LLM provider config contract (client ↔ live backend).
 *
 * Drives llmApi against the live dawei: global model listing + workspace-scoped
 * override-or-inherit merge (effective / settings / settings-all). Guards the
 * config-leveling contract the frontend's settings panel depends on.
 */
import { describe, it, expect, afterAll } from "vitest";
import { probeLive, primeAuth } from "./helpers/live";
import { llmApi } from "@/lib/api/llm";
import { workspaceApi } from "@/lib/api/workspace";

primeAuth(process.env.INTEGRATION_TOKEN);

const LIVE = await probeLive();

let wsId: string | undefined;
afterAll(async () => {
  if (wsId) {
    try {
      await workspaceApi.delete(wsId);
    } catch {
      /* best effort */
    }
  }
});

describe.skipIf(!LIVE)("B3 · LLM config contract (live)", () => {
  it("listGlobalModels() returns { availableLLMs: [] }", async () => {
    const r = await llmApi.listGlobalModels();
    expect(Array.isArray(r.availableLLMs)).toBe(true);
  });

  it("workspace is provisioned for scoped tests", async () => {
    const created = await workspaceApi.createTemp(
      "it-b3-" + Math.random().toString(36).slice(2, 8),
    );
    wsId = created.workspace.id;
    expect(wsId).toBeTruthy();
  });

  it("listEffective() returns override-or-inherit effective list", async () => {
    const r = await llmApi.listEffective(wsId!);
    expect(r.success).toBe(true);
    expect(Array.isArray(r.effective)).toBe(true);
  });

  it("getSettings() returns merged settings", async () => {
    const r = await llmApi.getSettings(wsId!);
    expect(r.success).toBe(true);
    expect(r.settings).toBeTypeOf("object");
  });

  it("listSettingsAll() returns user/workspace split", async () => {
    const r = await llmApi.listSettingsAll(wsId!);
    expect(r.success).toBe(true);
    expect(r.settings).toBeTypeOf("object");
    expect(r.settings.user).toBeDefined();
    expect(r.settings.workspace).toBeDefined();
  });
});
