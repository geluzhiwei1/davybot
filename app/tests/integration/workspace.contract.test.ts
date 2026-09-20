/**
 * B1 — Workspace contract (client ↔ live backend).
 *
 * Drives the REAL frontend workspaceApi against the live dawei server (no mocking).
 * Verifies the response shapes the client relies on actually match what the backend
 * returns — the most common breakage when either side changes.
 */
import { describe, it, expect, afterAll } from "vitest";
import { probeLive, primeAuth } from "./helpers/live";
import { workspaceApi } from "@/lib/api/workspace";

primeAuth(process.env.INTEGRATION_TOKEN);

const LIVE = await probeLive();

const cleanup: string[] = [];
afterAll(async () => {
  for (const id of cleanup) {
    try {
      await workspaceApi.delete(id);
    } catch {
      /* best effort */
    }
  }
});

describe.skipIf(!LIVE)("B1 · workspace contract (live)", () => {
  it("list() returns { success, workspaces[] }", async () => {
    const r = await workspaceApi.list();
    expect(r.success).toBe(true);
    expect(Array.isArray(r.workspaces)).toBe(true);
  });

  it("createTemp → appears in list() → delete → gone from list()", async () => {
    const created = await workspaceApi.createTemp(
      "it-b1-" + Math.random().toString(36).slice(2, 8),
    );
    expect(created.success).toBe(true);
    expect(created.workspace?.id).toBeTruthy();

    const id = created.workspace.id;
    cleanup.push(id);

    const list = await workspaceApi.list();
    expect(list.workspaces.some((w) => w.id === id)).toBe(true);

    await workspaceApi.delete(id);
    const list2 = await workspaceApi.list();
    expect(list2.workspaces.some((w) => w.id === id)).toBe(false);

    // already deleted — drop from cleanup
    const idx = cleanup.indexOf(id);
    if (idx >= 0) cleanup.splice(idx, 1);
  });

  it("getConfig() returns the leveled config envelope", async () => {
    const created = await workspaceApi.createTemp(
      "it-b1-cfg-" + Math.random().toString(36).slice(2, 8),
    );
    const id = created.workspace.id;
    cleanup.push(id);
    try {
      const cfg = await workspaceApi.getConfig(id);
      expect(cfg.success).toBe(true);
      expect(cfg.config).toBeTypeOf("object");
    } finally {
      await workspaceApi.delete(id);
      const idx = cleanup.indexOf(id);
      if (idx >= 0) cleanup.splice(idx, 1);
    }
  });
});
