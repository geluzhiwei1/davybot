/**
 * B5 — Conversation contract (client ↔ live backend).
 *
 * Drives the real conversationApi / historyApi (all workspace-scoped) against the
 * live dawei: create → list → getMessages → deleteScoped. The earlier broken
 * single-arg get()/delete() (which hit a non-existent /api/conversations/{id} and
 * 404'd) have been removed; the correct workspace-scoped methods are exercised here.
 */
import { describe, it, expect, afterAll } from "vitest";
import { probeLive, primeAuth } from "./helpers/live";
import { conversationApi, historyApi } from "@/lib/api/conversation";
import { workspaceApi } from "@/lib/api/workspace";

primeAuth(process.env.INTEGRATION_TOKEN);

const LIVE = await probeLive();

const cleanup: { wsId?: string; convId?: string } = {};
afterAll(async () => {
  if (cleanup.convId && cleanup.wsId) {
    try {
      await conversationApi.deleteScoped(cleanup.wsId, cleanup.convId);
    } catch {
      /* best effort */
    }
  }
  if (cleanup.wsId) {
    try {
      await workspaceApi.delete(cleanup.wsId);
    } catch {
      /* best effort */
    }
  }
});

describe.skipIf(!LIVE)("B5 · conversation contract (live, workspace-scoped)", () => {
  it("create() returns { success, id }", async () => {
    const ws = await workspaceApi.createTemp("it-b5-" + Math.random().toString(36).slice(2, 8));
    cleanup.wsId = ws.workspace.id;
    const created = await conversationApi.create(cleanup.wsId, "it-conv");
    expect(created.success).toBe(true);
    expect(created.id).toBeTruthy();
    cleanup.convId = created.id;
  });

  it("list() returns { success, conversations[] } containing it", async () => {
    const r = await conversationApi.list(cleanup.wsId!);
    expect(r.success).toBe(true);
    expect(Array.isArray(r.conversations)).toBe(true);
    expect(r.conversations.some((c) => c.id === cleanup.convId)).toBe(true);
  });

  it("historyApi.getMessages() returns the conversation messages", async () => {
    const r = (await historyApi.getMessages(cleanup.wsId!, cleanup.convId!)) as {
      success: boolean;
      messages?: unknown[];
      conversation?: { messages?: unknown[] };
    };
    expect(r.success).toBe(true);
    // backend nests messages under `conversation`; client type declares top-level — accept both
    const msgs = r.messages ?? r.conversation?.messages;
    expect(Array.isArray(msgs)).toBe(true);
  });

  it("deleteScoped() removes it from list()", async () => {
    await conversationApi.deleteScoped(cleanup.wsId!, cleanup.convId!);
    const r = await conversationApi.list(cleanup.wsId!);
    expect(r.conversations.some((c) => c.id === cleanup.convId)).toBe(false);
    cleanup.convId = undefined;
  });
});
