/**
 * Connection store — manages WebSocket connection state.
 * Zustand store wrapping the WebSocketClient singleton.
 *
 * Decoupled from other stores via event bus. All WS events are emitted
 * as typed events; subscriber stores (chat-store, agent-store, task-store)
 * listen independently without import coupling.
 */

import { create } from "zustand";
import { wsClient } from "./ws-client";
import type { ConnectionState, WsMessage } from "./types";
import { taskGraphApi } from "./api-client";
import { emit } from "./event-bus";
import type { TraceSpan } from "./types/agents";

interface ConnectionStore {
  state: ConnectionState;
  sessionId: string | null;
  connectedAt: number | null;
  reconnectCount: number;

  // Actions
  connect: (workspaceId?: string) => void;
  disconnect: () => void;
  send: (msg: WsMessage) => void;
  sendMessage: (content: string, conversationId?: string) => void;
}

export const useConnectionStore = create<ConnectionStore>((set, get) => {
  // Wire up WebSocket client callbacks
  wsClient.setHandlers({
    onStateChange(state: ConnectionState) {
      const current = get();
      set({
        state,
        connectedAt: state === "connected" ? Date.now() : current.connectedAt,
        reconnectCount: state === "reconnecting" ? current.reconnectCount + 1 : 0,
      });

      // ── Connection lost → notify subscribers ──────────────────
      if (state === "reconnecting" || state === "error") {
        emit("ws:connection_lost", {});
      }

      // ── Reconnect restore: fetch task graph + trace spans ─────
      if (state === "connected") {
        const wsId = wsClient.getWorkspaceId();
        if (wsId) {
          // Re-sync chat history — messages pushed while the socket was down
          // are dropped server-side (no replay); the persisted conversation
          // is the source of truth (chat-store patches the gap).
          emit("ws:resync_history", { wsId });
          // Restore task graph UI state
          taskGraphApi
            .getGraphs(wsId)
            .then((res) => {
              if (res.success && res.graphs.length > 0) {
                const g = res.graphs[0];
                console.log(
                  `[TaskGraph] Reconnected — restored ${g.tasks.length} task node(s) for workspace ${wsId}`,
                );
                emit("ws:graph_restored", { wsId, graph: g });
              }
            })
            .catch((err) => {
              console.error("[TaskGraph] Reconnect restore failed:", err);
              emit("ws:error", {
                wsId,
                error: err instanceof Error ? err.message : "恢复任务图失败",
              });
            });
          // Notify agent-store to restore trace spans
          emit("ws:restore_traces", { wsId });
        }
      }
    },
    onMessage(msg: WsMessage) {
      // Session tracking
      if (msg.type === "ws_connected" && msg.session_id) {
        set({ sessionId: msg.session_id });
      }

      // ── Agent degraded features notification ──────────────────
      if (msg.type === "agent_start" && msg.degraded_features) {
        const wsId = msg.workspace_id;
        if (wsId) {
          emit("ws:degraded_features", {
            wsId,
            features: msg.degraded_features,
          });
        }
      }

      // ── Agent start ──────────────────────────────────────────
      if (msg.type === "agent_start") {
        const wsId = msg.workspace_id;
        const mode = msg.agent_mode;
        const taskId = msg.task_id;
        if (wsId) {
          emit("ws:agent_start", { wsId, mode: mode || "orchestrator", taskId });
        }
      }

      // ── Agent status update (memory ready, etc.) ──────────────
      if (msg.type === "agent_status_update") {
        const wsId = msg.workspace_id || (msg.data?.workspace_id as string);
        if (wsId) {
          if (msg.degraded_features) {
            emit("ws:degraded_features", {
              wsId,
              features: msg.degraded_features,
            });
          }
          if (msg.memory_ready) {
            emit("ws:memory_ready", { wsId });
          }
        }
      }

      // ── Agent span (tracing) ──────────────────────────────────
      if (msg.type === "agent_span") {
        const wsId = msg.workspace_id;
        if (wsId && msg.span_id) {
          const span: TraceSpan = {
            span_id: msg.span_id,
            parent_span_id: msg.parent_span_id,
            span_name: msg.span_name || "unknown",
            phase: msg.phase,
            start_time: msg.start_time || new Date().toISOString(),
            end_time: msg.end_time,
            duration_ms: msg.duration_ms,
            status: (msg.status as TraceSpan["status"]) || "running",
            input_summary: msg.input_summary,
            output_summary: msg.output_summary,
          };
          emit("ws:agent_span", { wsId, span });
        }
      }

      // ── Dispatch all messages to chat store via event bus ─────
      emit("ws:message", msg as unknown as Record<string, unknown>);
    },
  });

  return {
    state: "disconnected",
    sessionId: null,
    connectedAt: null,
    reconnectCount: 0,

    connect(workspaceId?: string) {
      wsClient.connect(workspaceId ?? undefined);
    },

    disconnect() {
      wsClient.disconnect();
      set({ sessionId: null, connectedAt: null });
    },

    send(msg: WsMessage) {
      wsClient.send(msg);
    },

    sendMessage(content: string, conversationId?: string) {
      wsClient.sendMessage(content, conversationId);
    },
  };
});

// ── Tab visibility / network recovery ─────────────────────────────────
// Background tabs get their timers throttled and the WS reaped (server
// timeout 180s; frames for disconnected sessions are dropped, no replay).
// When the user comes back to the tab (or the network returns), make sure
// the socket is up immediately and re-sync chat history from the server
// (source of truth). This fixes "messages stuck at old text after
// switching tabs" — demo.normnomos.com 2026-09-22.
if (typeof document !== "undefined") {
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState !== "visible") return;
    const st = wsClient.state;
    if (st === "reconnecting" || st === "disconnected") {
      // Don't wait out the backoff timer — reconnect now (same workspace).
      // "error" is skipped: after auth rejection (1008) reconnecting would
      // just loop back to the login redirect.
      wsClient.connect();
    } else if (st === "connected") {
      const wsId = wsClient.getWorkspaceId();
      if (wsId) emit("ws:resync_history", { wsId });
    }
  });
}
if (typeof window !== "undefined") {
  window.addEventListener("online", () => {
    if (wsClient.state === "reconnecting" || wsClient.state === "disconnected") {
      wsClient.connect();
    }
  });
}
