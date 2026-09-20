// @vitest-environment node
/**
 * B6 — Chat streaming over the REAL WebSocket (end-to-end).
 *
 * Connects the real frontend WebSocketClient to the live dawei, sends a user
 * message, and asserts the STREAM_* event sequence the chat-store depends on:
 * content/reasoning deltas → stream_complete, no stream_error.
 *
 * Requires (a) the backend running and (b) a working model backend (DAWEI_TEST_LLM=1).
 * Runs in the node environment (jsdom has no real WebSocket); workspace creation
 * uses raw fetch since node has no localStorage for the request() helper.
 */
import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { probeLive, LLM_ENABLED, INTEGRATION_TARGET } from "./helpers/live";
import { WebSocketClient } from "@/lib/ws-client";

const LIVE = await probeLive();
const RUN = LIVE && LLM_ENABLED;

const TARGET = INTEGRATION_TARGET;
let wsId: string | undefined;
let client: WebSocketClient | undefined;

beforeAll(async () => {
  if (!RUN) return;
  // Create a workspace via raw fetch (node env has no localStorage for request()).
  const r = await fetch(`${TARGET}/api/workspaces/create-temp`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ display_name: "it-b6-" + Math.random().toString(36).slice(2, 8) }),
  });
  const body = await r.json();
  wsId = body?.workspace?.id ?? body?.id;
  if (!wsId) throw new Error(`workspace create failed: ${r.status}`);
});

afterAll(async () => {
  try {
    client?.disconnect();
  } catch {
    /* noop */
  }
  if (wsId) {
    try {
      await fetch(`${TARGET}/api/workspaces/${wsId}`, { method: "DELETE" });
    } catch {
      /* best effort */
    }
  }
});

async function waitFor<T>(fn: () => T | undefined, timeoutMs: number): Promise<T | undefined> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const v = fn();
    if (v !== undefined && v !== null) return v;
    await new Promise((res) => setTimeout(res, 100));
  }
  return undefined;
}

describe.skipIf(!RUN)("B6 · chat streaming over real WebSocket (live, LLM)", () => {
  it("streams an assistant reply and ends with stream_complete", async () => {
    const messages: Array<{ type: string; content?: string }> = [];
    client = new WebSocketClient();
    client.addMessageListener((m) => messages.push(m as { type: string; content?: string }));

    client.connect(wsId);
    const connected = await waitFor(
      () => (client!.state === "connected" ? true : undefined),
      10_000,
    );
    expect(connected, "WS did not reach connected state").toBe(true);

    client.sendMessage("请只回复两个字：你好");

    const done = await waitFor(() => {
      const hasComplete = messages.some((m) => m.type === "stream_complete");
      const hasError = messages.some((m) => m.type === "stream_error");
      return hasComplete || hasError ? true : undefined;
    }, 120_000);
    expect(done, "neither stream_complete nor stream_error arrived in time").toBe(true);

    const types = messages.map((m) => m.type);
    expect(types).not.toContain("stream_error");

    const hasText = messages.some(
      (m) =>
        ["stream_content", "stream_reasoning", "assistant_message"].includes(m.type) &&
        typeof m.content === "string" &&
        m.content.length > 0,
    );
    expect(hasText, `no streamed assistant text; types=${types.join(",")}`).toBe(true);
    expect(types).toContain("stream_complete");
  });
});
