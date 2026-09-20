/**
 * WebSocket client for real-time communication with the legalbot backend.
 * Ported from legacy Vue 3 webui (legalbot/webui/src/stores/connection.ts) → React 19 + Zustand.
 */

import type { WsMessage, ConnectionState } from "./types";
import { WS_RECONNECT_DELAY, WS_MAX_RECONNECT_ATTEMPTS, getWsBaseUrl, STORAGE_KEYS } from "./env";

const RECONNECT_DELAY = WS_RECONNECT_DELAY;
const MAX_RECONNECT_ATTEMPTS = WS_MAX_RECONNECT_ATTEMPTS;
const MAX_PENDING_QUEUE = 50; // max messages to queue while offline
const HEARTBEAT_INTERVAL = 30_000; // 30 seconds

export type WsMessageHandler = (msg: WsMessage) => void;
export type WsStateHandler = (state: ConnectionState) => void;

/**
 * WebSocket client with auto-reconnect, heartbeat, and session management.
 */
export class WebSocketClient {
  private ws: WebSocket | null = null;
  private url: string | null;
  private sessionId: string | null = null;
  private workspaceId: string | null = null;
  private reconnectAttempts = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  private _intendedDisconnect = false; // true = disconnect was intentional vs network error
  private pendingQueue: WsMessage[] = []; // offline message queue

  // Callbacks
  private onMessage: WsMessageHandler | null = null;
  private onStateChange: WsStateHandler | null = null;
  // Additional message listeners (P2.2): components can subscribe without
  // replacing the primary chat-store onMessage handler.
  private messageListeners: WsMessageHandler[] = [];

  state: ConnectionState = "disconnected";

  // Optional explicit base; falls back to getWsBaseUrl() at connect time so a
  // dynamically-picked Tauri sidecar port (resolved after this singleton is
  // constructed) is honored.
  constructor(baseUrl?: string) {
    this.url = baseUrl ?? null;
  }

  // ── Public API ──────────────────────────────────────────────────

  connect(workspaceId?: string, sessionId?: string): void {
    const workspaceChanged = workspaceId !== undefined && workspaceId !== this.workspaceId;

    // If already connected to the same workspace, skip
    if (this.ws?.readyState === WebSocket.OPEN && !workspaceChanged) {
      return;
    }

    // If workspace changed while connected, disconnect so we reconnect with new params
    if (this.ws?.readyState === WebSocket.OPEN && workspaceChanged) {
      console.log(`[WS] Workspace switch detected (→ ${workspaceId}), reconnecting...`);
      this._intendedDisconnect = true;
      if (this.ws) {
        try {
          this.ws.close(1000, "workspace switch");
        } catch {
          /* ignore */
        }
        this.ws = null;
      }
    }

    this.workspaceId = workspaceId ?? null;
    this.sessionId = sessionId ?? null;
    this._intendedDisconnect = false;
    this.doConnect();
  }

  disconnect(): void {
    this._intendedDisconnect = true;
    this.cleanup();
    // Clear pending queue on explicit disconnect
    if (this.pendingQueue.length > 0) {
      console.log(`[WS] Discarding ${this.pendingQueue.length} queued message(s) on disconnect`);
      this.pendingQueue = [];
    }

    if (this.ws) {
      try {
        this.ws.close(1000, "client disconnect");
      } catch {
        // ignore
      }
      this.ws = null;
    }
    this.setState("disconnected");
  }

  send(msg: WsMessage): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      // Queue message for later delivery when connection restores
      if (this.pendingQueue.length < MAX_PENDING_QUEUE && msg.type !== "ws_heartbeat") {
        this.pendingQueue.push(msg);
        console.debug(
          `[WS] Queued message (type=${msg.type}, queue=${this.pendingQueue.length}/${MAX_PENDING_QUEUE})`,
        );
      } else if (this.pendingQueue.length >= MAX_PENDING_QUEUE) {
        console.warn("[WS] Queue full — dropping oldest message");
        this.pendingQueue.shift();
        this.pendingQueue.push(msg);
      }
      return;
    }

    this._doSend(msg);
  }

  /** Actually send a raw message over the WebSocket */
  private _doSend(msg: WsMessage): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;

    const payload = {
      ...msg,
      session_id: msg.session_id ?? this.sessionId ?? undefined,
      workspace_id: msg.workspace_id ?? this.workspaceId ?? undefined,
      timestamp: msg.timestamp ?? Date.now(),
    };

    this.ws.send(JSON.stringify(payload));
  }

  /** Drain the pending message queue onto the open connection */
  private drainQueue(): void {
    if (this.pendingQueue.length === 0) return;

    const count = this.pendingQueue.length;
    console.log(`[WS] Draining ${count} queued message(s)...`);

    // Drain in order, oldest first
    const messages = [...this.pendingQueue];
    this.pendingQueue = [];

    for (const msg of messages) {
      this._doSend(msg);
    }

    if (this.onStateChange) {
      console.log(`[WS] Drain complete — sent ${count} message(s)`);
    }
  }

  sendMessage(content: string, conversationId?: string): void {
    this.send({
      type: "user_message",
      content,
      conversation_id: conversationId ?? undefined,
      data: {
        // let backend use its default mode/model from workspace config
      },
    });
  }

  sendFollowupResponse(taskId: string, toolCallId: string, response: string): void {
    // 后端 FollowupResponseMessage 要求 task_id / tool_call_id / response 在顶层
    this.send({
      type: "followup_response",
      task_id: taskId,
      tool_call_id: toolCallId,
      response,
    });
  }

  sendFollowupCancel(
    taskId: string,
    toolCallId: string,
    reason: "user_cancelled" | "timeout" | "skipped" = "user_cancelled",
  ): void {
    // 后端 FollowupCancelMessage 要求 task_id / tool_call_id / reason 在顶层
    this.send({
      type: "followup_cancel",
      task_id: taskId,
      tool_call_id: toolCallId,
      reason,
    });
  }

  /** P2.2: reply to a tool_approval_request (approve / deny). */
  sendToolApprovalResponse(requestId: string, approved: boolean): void {
    this.send({
      type: "tool_approval_response",
      request_id: requestId,
      approved,
    });
  }

  setHandlers(handlers: { onMessage?: WsMessageHandler; onStateChange?: WsStateHandler }): void {
    this.onMessage = handlers.onMessage ?? null;
    this.onStateChange = handlers.onStateChange ?? null;
  }

  /** P2.2: subscribe an extra message listener (e.g. ApprovalPrompt). */
  addMessageListener(fn: WsMessageHandler): void {
    if (!this.messageListeners.includes(fn)) this.messageListeners.push(fn);
  }

  removeMessageListener(fn: WsMessageHandler): void {
    this.messageListeners = this.messageListeners.filter((f) => f !== fn);
  }

  // ── Connection lifecycle ────────────────────────────────────────

  private doConnect(): void {
    this.cleanup();
    this.setState("connecting");

    const params = new URLSearchParams();
    // JWT 优先; server 自包含模式退化为访问密码 (该 key 仅 server 模式流程写入)
    const authToken =
      typeof localStorage !== "undefined"
        ? (localStorage.getItem(STORAGE_KEYS.authToken) ??
          localStorage.getItem(STORAGE_KEYS.serverPassword))
        : null;
    if (authToken) params.set("token", authToken);
    if (this.workspaceId) params.set("workspace_id", this.workspaceId);
    if (this.sessionId) params.set("session_id", this.sessionId);

    // Resolve the base fresh on each connect — the sidecar port may be set
    // after this singleton was constructed.
    const base = this.url ?? getWsBaseUrl();
    const wsUrl = `${base}/ws${params.toString() ? `?${params}` : ""}`;

    try {
      this.ws = new WebSocket(wsUrl);
    } catch (err) {
      console.error("[WS] Failed to create WebSocket:", err);
      this.setState("error");
      this.scheduleReconnect();
      return;
    }

    this.ws.onopen = () => {
      console.log("[WS] Connected");
      this.reconnectAttempts = 0;
      this.setState("connected");
      this.startHeartbeat();
      // Drain any messages queued while offline
      this.drainQueue();
    };

    this.ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data) as WsMessage;
        this.handleMessage(msg);
      } catch (err) {
        console.warn("[WS] Failed to parse message:", err);
      }
    };

    this.ws.onclose = (event) => {
      console.log(`[WS] Closed (code=${event.code}, reason=${event.reason})`);
      this.stopHeartbeat();

      // 鉴权被拒:后端对缺失/无效 token 以 1008 关闭
      // (agent/dawei/api/websocket.py::_authenticate_ws)。用同一 token 重试
      // 毫无意义 — 停止重连循环,派发事件由应用壳收口(提示 + 跳登录)。
      if (event.code === 1008) {
        console.error("[WS] Auth rejected (code 1008) — stopping reconnects");
        this._intendedDisconnect = true; // prevent scheduleReconnect
        this.setState("error");
        if (typeof window !== "undefined") {
          window.dispatchEvent(new CustomEvent("ws:auth-error"));
        }
        return;
      }

      if (!this._intendedDisconnect) {
        this.setState("reconnecting");
        this.scheduleReconnect();
      } else {
        this.setState("disconnected");
      }
    };

    this.ws.onerror = (event) => {
      console.error("[WS] Error:", event);
      this.setState("error");
    };
  }

  private handleMessage(msg: WsMessage): void {
    // Track session_id from server
    if (msg.type === "ws_connected" && msg.session_id) {
      this.sessionId = msg.session_id;
    }

    // Forward to primary handler + any extra listeners (P2.2 etc.)
    this.onMessage?.(msg);
    for (const fn of this.messageListeners) {
      try {
        fn(msg);
      } catch (err) {
        console.warn("[WS] message listener error:", err);
      }
    }
  }

  // ── Reconnection ────────────────────────────────────────────────

  private scheduleReconnect(): void {
    // MAX_RECONNECT_ATTEMPTS <= 0 means infinite reconnection (matches the
    // webui app convention). Otherwise honor the finite cap.
    const hasCap = MAX_RECONNECT_ATTEMPTS > 0;

    if (this._intendedDisconnect || (hasCap && this.reconnectAttempts >= MAX_RECONNECT_ATTEMPTS)) {
      if (hasCap && this.reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
        console.error("[WS] Max reconnect attempts reached");
        this.setState("error");
      }
      return;
    }

    const delay = Math.min(RECONNECT_DELAY * Math.pow(1.5, this.reconnectAttempts), 30_000);
    this.reconnectAttempts++;

    const attemptLabel = hasCap
      ? `attempt ${this.reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS}`
      : `attempt ${this.reconnectAttempts}`;
    console.log(`[WS] Reconnecting in ${Math.round(delay)}ms (${attemptLabel})`);

    this.reconnectTimer = setTimeout(() => {
      if (!this._intendedDisconnect) {
        this.doConnect();
      }
    }, delay);
  }

  // ── Heartbeat ───────────────────────────────────────────────────

  private startHeartbeat(): void {
    this.stopHeartbeat();
    this.heartbeatTimer = setInterval(() => {
      this.send({ type: "ws_heartbeat" });
    }, HEARTBEAT_INTERVAL);
  }

  private stopHeartbeat(): void {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  /** Get current workspace id (used for reconnect restore). */
  getWorkspaceId(): string | null {
    return this.workspaceId;
  }

  // ── Utilities ───────────────────────────────────────────────────

  private setState(state: ConnectionState): void {
    this.state = state;
    this.onStateChange?.(state);
  }

  private cleanup(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.stopHeartbeat();
  }

  // ── Static helper ───────────────────────────────────────────────

  static getWsUrl(): string {
    return getWsBaseUrl();
  }
}

/** Singleton WebSocket client instance. */
export const wsClient = new WebSocketClient();
