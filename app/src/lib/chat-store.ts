/**
 * Chat store — manages conversations, messages, and stream handling.
 * Replaces the mock-reply system with real WebSocket communication.
 * Ported from legacy Vue 3 webui (legalbot/webui/src/stores/chat.ts) → React 19 + Zustand.
 */

import { create } from "zustand";
import type {
  ChatMessage,
  WsMessage,
  StreamBuffer,
  AgentStatus,
  ContentBlock,
  ToolCallContentBlock,
  ToolResultContentBlock,
  ToolExecutionContentBlock,
  SimpleTextContentBlock,
  GovernanceMeta,
  SubtaskCardContentBlock,
} from "./types";
import { wsClient } from "./ws-client";
import { historyApi } from "./api-client";
import { useTaskStore } from "./task-store";
import { on } from "./event-bus";
import { useAgentStore } from "./agent-store";
import { useMonitoringStore } from "./monitoring-store";
import { extractSubtaskBatchCard, extractSubtaskCard } from "./subtask-card";
import { STORAGE_KEYS } from "./env";
// 循环依赖：store.ts ↔ chat-store.ts。仅在本模块的 action 函数内部调用
// useStore.getState()（运行时两边的 Zustand store 都已创建完成），不在顶层使用。
import { useStore } from "./store";

/** Generate a short unique ID for UI-only message keys. NOT used for conversation IDs.
 *  Uses crypto.randomUUID() when available (secure context), falls back to a
 *  Math.random based UUID v4 for HTTP origins where randomUUID is unavailable. */
const uid = (): string => {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID().slice(0, 8);
  }
  // Fallback for non-secure contexts (HTTP) where crypto.randomUUID is not available
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx"
    .replace(/[xy]/g, (c) => {
      const r = (Math.random() * 16) | 0;
      return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
    })
    .slice(0, 8);
};

// ── Types ───────────────────────────────────────────────────────────

/** Chat display mode — controls which content blocks are visible. */
export type DisplayMode = "minimal" | "default" | "detailed";

/** Pending follow-up question from the agent (ask_followup_question, human-in-the-loop). */
export interface FollowupState {
  question: string;
  suggestions: string[];
  toolCallId: string;
  taskId: string;
}

interface ConversationState {
  id: string;
  title: string;
  messages: ChatMessage[];
  model?: string;
  expertId?: string;
  mode?: "single" | "team";
  isStreaming: boolean;
  agentStatus: AgentStatus;
  streamBuffer: StreamBuffer | null;
  /** Active follow-up question awaiting user input (null/undefined when none). */
  followup?: FollowupState | null;
}

interface ChatStore {
  // State
  conversations: Map<string, ConversationState>;
  /** Display mode: minimal (text only), default (thinking + tool summary), detailed (all blocks) */
  displayMode: DisplayMode;
  /** Compact mode — reduced spacing/padding in chat messages */
  compactMode: boolean;
  /** Font size for message text content (12–20px) */
  fontSize: number;
  /** Conversations that failed to load history (convId -> error message) */
  historyLoadErrors: Record<string, string>;
  // Computed-like getters
  getConversation: (id: string) => ConversationState | undefined;
  getMessages: (conversationId: string) => ChatMessage[];
  /** Retry loading history for a failed conversation */
  retryLoadHistory: (conversationId: string, workspaceId: string) => Promise<void>;

  // Actions
  deleteConversation: (id: string) => void;
  /** Send a message to a specific conversation. conversationId is required.
   *  When `opts` is provided (task context), the full payload is sent so the
   *  backend routes to the right workspace and selects the right LLM/experts.
   *  Without `opts`, falls back to the bare payload (content + conversation_id). */
  sendMessage: (
    content: string,
    conversationId: string,
    opts?: {
      workspaceId?: string | null;
      model?: string;
      expertId?: string;
      mode?: "single" | "team";
      /** 社媒编辑会话上下文(A-M1):随 data 透传,引擎工具经 ContextVar 读取 */
      socialContext?: { content_id: string; tenant_id: string };
      /** 显式模型来源(gateway|local…):社媒轨模型目录与全局 models store 不同源,优先于查表 */
      modelSource?: string;
    },
  ) => void;
  setConversationModel: (id: string, model: string) => void;
  setConversationMode: (id: string, mode: "single" | "team") => void;
  clearMessages: (id: string) => void;
  /** Set the streaming flag for a specific conversation. */
  setStreaming: (id: string, streaming: boolean) => void;
  /**
   * 🔧 修复：收口残留流式状态。终态事件（agent_complete/agent_stopped/最终
   * stream_complete）缺失时（如后端异常结束、断线、子任务报错），会话 isStreaming
   * 与已落盘消息的 status:"streaming"/"pending" 会永久残留（消息转圈不停、输入区
   * 一直显示停止按钮）。flush 缓冲为部分输出，并把该会话所有未完结消息标记为
   * complete。用户点击停止与收到 agent_stopped 时调用。
   */
  finalizeStaleStreams: (conversationId: string) => void;
  loadHistory: (
    conversationId: string,
    workspaceId: string,
    opts?: { force?: boolean },
  ) => Promise<void>;
  /** Ensure a conversation entry exists for the given ID (no-op if already present). */
  ensureConversation: (
    id: string,
    opts?: { title?: string; model?: string; expertId?: string; mode?: "single" | "team" },
  ) => void;
  /** Switch display mode (minimal/default/detailed). */
  setDisplayMode: (mode: DisplayMode) => void;
  /** Toggle compact mode (reduced spacing). */
  setCompactMode: (mode: boolean) => void;
  /** Set font size for chat messages (12–20px). */
  setFontSize: (size: number) => void;
  /** Interrupt all active streams — flush buffers as "interrupted" messages. Called on WS disconnect. */
  interruptAllStreams: () => void;
  /** Reply to the active follow-up question in a conversation (sends followup_response). */
  respondFollowup: (conversationId: string, response: string) => void;
  /** Cancel the active follow-up question in a conversation (sends followup_cancel). */
  cancelFollowup: (conversationId: string) => void;

  // Internal
  _handleWsMessage: (msg: WsMessage) => void;
  _startStreamBuffer: (messageId: string, conversationId: string) => void;
  _flushStreamBuffer: (conversationId: string) => void;
}

// ── Stream flush interval ───────────────────────────────────────────

const FLUSH_INTERVAL = 100; // ms
const STREAM_IDLE_TIMEOUT = 120_000; // 2 min — auto-cleanup stale streams to prevent timer leaks

// ── Store ───────────────────────────────────────────────────────────

export const useChatStore = create<ChatStore>((set, get) => {
  // Per-conversation flush timers — each conversation gets its own timer
  const flushTimers = new Map<string, ReturnType<typeof setInterval>>();

  return {
    conversations: new Map(),
    displayMode: (() => {
      try {
        const stored = localStorage.getItem("normnomos-display-mode");
        if (stored === "minimal" || stored === "default" || stored === "detailed") return stored;
      } catch {
        /* no-op */
      }
      return "default" as DisplayMode;
    })(),
    compactMode: (() => {
      try {
        return localStorage.getItem(STORAGE_KEYS.compactMode) === "true";
      } catch {
        return false;
      }
    })(),
    fontSize: (() => {
      try {
        const v = parseInt(localStorage.getItem(STORAGE_KEYS.fontSize) ?? "", 10);
        return v >= 12 && v <= 20 ? v : 14;
      } catch {
        return 14;
      }
    })(),
    historyLoadErrors: {} as Record<string, string>,

    // ── Getters ─────────────────────────────────────────────────

    getConversation(id: string) {
      return get().conversations.get(id);
    },

    getMessages(conversationId: string) {
      return get().conversations.get(conversationId)?.messages ?? [];
    },

    // ── Actions ─────────────────────────────────────────────────

    deleteConversation(id) {
      // Clean up per-conversation flush timer
      const timer = flushTimers.get(id);
      if (timer) {
        clearInterval(timer);
        flushTimers.delete(id);
      }
      set((s) => {
        const next = new Map(s.conversations);
        next.delete(id);
        return { conversations: next };
      });
    },

    sendMessage(content, conversationId, opts) {
      if (!conversationId) {
        console.warn("[ChatStore] sendMessage called without conversationId — ignoring");
        return;
      }
      const convId = conversationId;

      const conv = get().conversations.get(convId);
      if (!conv) return;

      // Add user message locally
      const userMsg: ChatMessage = {
        id: uid(),
        role: "user",
        content,
        status: "complete",
        ts: Date.now(),
      };

      // Auto-title from first message
      const title = conv.messages.length === 0 ? content.slice(0, 24) : conv.title;

      set((s) => {
        const next = new Map(s.conversations);
        const c = next.get(convId);
        if (!c) return {};
        next.set(convId, {
          ...c,
          title,
          messages: [...c.messages, userMsg],
        });
        return { conversations: next };
      });

      // Send via WebSocket.
      // When task context (opts) is available, send the FULL payload so the
      // backend uses the correct workspace + LLM + experts — matching the
      // manual-input path (floating-input). Otherwise (no opts) the bare
      // wsClient.sendMessage falls back to the WS client's default workspace,
      // which is wrong for any workspace other than workspaces[0].
      if (opts && (opts.workspaceId || opts.model)) {
        let authToken: string | undefined;
        try {
          authToken = localStorage.getItem("auth_token") || undefined;
        } catch {
          authToken = undefined;
        }
        // 查出用户所选模型的来源与 provider 配置名，明确告诉后端走本地 provider 还是官方网关，
        // 后端据此路由，不靠 model id 猜测。
        const modelObj = opts.model
          ? useStore.getState().models.find((m) => m.id === opts.model)
          : undefined;
        wsClient.send({
          type: "user_message",
          content,
          conversation_id: convId,
          workspace_id: opts.workspaceId ?? undefined,
          data: {
            mode: opts.mode,
            model: opts.model,
            expert_id: opts.expertId,
            auth_token: authToken,
            ...(opts.socialContext ? { social_context: opts.socialContext } : {}),
          },
          user_ui_context: {
            current_experts: opts.expertId ? [opts.expertId] : [],
            current_mode: opts.expertId || "orchestrator",
            current_llm_id: opts.model,
            current_llm_source: opts.modelSource ?? modelObj?.source,
            current_config_name: modelObj?.configName,
          },
        });
      } else {
        wsClient.sendMessage(content, convId);
      }

      // 与手工发送路径（floating-input.handleSend 调 setStreaming(true)）对齐：
      // 自动开场白发送后立即将会话标记为"生成中"，使发送按钮（FloatingInput 据
      // isStreaming 显示忙碌/停止态）无论人工还是自动发送都正确进入忙碌态。
      get().setStreaming(convId, true);
    },

    setConversationModel(id, model) {
      set((s) => {
        const next = new Map(s.conversations);
        const c = next.get(id);
        if (!c) return {};
        next.set(id, { ...c, model });
        return { conversations: next };
      });
    },

    setConversationMode(id, mode) {
      set((s) => {
        const next = new Map(s.conversations);
        const c = next.get(id);
        if (!c) return {};
        next.set(id, { ...c, mode });
        return { conversations: next };
      });
    },

    clearMessages(id) {
      set((s) => {
        const next = new Map(s.conversations);
        const c = next.get(id);
        if (!c) return {};
        next.set(id, { ...c, messages: [] });
        return { conversations: next };
      });
    },

    setStreaming(id, streaming) {
      set((s) => {
        const next = new Map(s.conversations);
        const c = next.get(id);
        if (!c) return {};
        next.set(id, { ...c, isStreaming: streaming });
        return { conversations: next };
      });
    },

    finalizeStaleStreams(conversationId) {
      // 1) 先把缓冲中的部分输出落盘（与 agent_stopped 原路径一致）
      get()._flushStreamBuffer(conversationId);
      // 2) 清理 per-conversation flush 定时器
      const timer = flushTimers.get(conversationId);
      if (timer) {
        clearInterval(timer);
        flushTimers.delete(conversationId);
      }
      // 3) 会话级 isStreaming 置 false + 消息级 streaming/pending 收口为 complete
      set((s) => {
        const c = s.conversations.get(conversationId);
        if (!c) return {};
        const next = new Map(s.conversations);
        const messages = c.messages.map((m) =>
          m.status === "streaming" || m.status === "pending"
            ? { ...m, status: "complete" as const }
            : m,
        );
        next.set(conversationId, {
          ...c,
          messages,
          isStreaming: false,
          streamBuffer: null,
          agentStatus: { mode: "idle" },
        });
        return { conversations: next };
      });
    },

    ensureConversation(id, opts) {
      const existing = get().conversations.get(id);
      if (existing) return;
      const conv: ConversationState = {
        id,
        title: opts?.title ?? "新对话",
        messages: [],
        model: opts?.model,
        expertId: opts?.expertId,
        mode: opts?.mode,
        isStreaming: false,
        agentStatus: { mode: "idle" },
        streamBuffer: null,
        followup: null,
      };
      set((s) => {
        const next = new Map(s.conversations);
        next.set(id, conv);
        return { conversations: next };
      });
    },

    respondFollowup(conversationId, response) {
      const conv = get().conversations.get(conversationId);
      const followup = conv?.followup;
      if (!followup) return;
      // 发送回复（task_id/tool_call_id/response 在顶层，匹配后端 FollowupResponseMessage）
      wsClient.sendFollowupResponse(followup.taskId, followup.toolCallId, response);
      // 清空追问状态、恢复 agent 状态
      set((s) => {
        const next = new Map(s.conversations);
        const c = next.get(conversationId);
        if (!c) return {};
        next.set(conversationId, { ...c, followup: null, agentStatus: { mode: "idle" } });
        return { conversations: next };
      });
    },

    cancelFollowup(conversationId) {
      const conv = get().conversations.get(conversationId);
      const followup = conv?.followup;
      if (!followup) return;
      // 通知后端取消（task_id/tool_call_id/reason 在顶层，匹配后端 FollowupCancelMessage）
      wsClient.sendFollowupCancel(followup.taskId, followup.toolCallId, "user_cancelled");
      set((s) => {
        const next = new Map(s.conversations);
        const c = next.get(conversationId);
        if (!c) return {};
        next.set(conversationId, { ...c, followup: null, agentStatus: { mode: "idle" } });
        return { conversations: next };
      });
    },

    setDisplayMode(mode) {
      set({ displayMode: mode });
      try {
        localStorage.setItem("normnomos-display-mode", mode);
      } catch {
        /* no-op */
      }
    },

    setCompactMode(mode) {
      set({ compactMode: mode });
      try {
        localStorage.setItem(STORAGE_KEYS.compactMode, String(mode));
      } catch {
        /* no-op */
      }
    },

    setFontSize(size) {
      const clamped = Math.min(20, Math.max(12, size));
      set({ fontSize: clamped });
      try {
        localStorage.setItem(STORAGE_KEYS.fontSize, String(clamped));
      } catch {
        /* no-op */
      }
    },

    interruptAllStreams() {
      set((s) => {
        const next = new Map(s.conversations);
        let changed = false;
        for (const [id, conv] of next) {
          if (conv.streamBuffer || conv.isStreaming) {
            changed = true;
            // Flush the buffer content as a message with "interrupted" status
            const buf = conv.streamBuffer;
            const interruptedMsg: ChatMessage = buf
              ? {
                  id: buf.messageId,
                  role: "assistant",
                  content: buf.content || "",
                  reasoning: buf.reasoning || undefined,
                  blocks: buf.content
                    ? [
                        { type: "text" as const, text: buf.content },
                        {
                          type: "simple_text" as const,
                          text: "（连接中断，回复不完整）",
                          kind: "interrupted",
                        },
                      ]
                    : undefined,
                  status: "error",
                  ts: Date.now(),
                }
              : {
                  id: uid(),
                  role: "assistant",
                  content: "",
                  blocks: [
                    {
                      type: "error" as const,
                      message: "连接中断",
                      details: "生成过程中连接断开，请重新连接后重试。",
                    },
                  ],
                  status: "error",
                  ts: Date.now(),
                };

            next.set(id, {
              ...conv,
              isStreaming: false,
              streamBuffer: null,
              agentStatus: { mode: "error" },
              messages: [...conv.messages, interruptedMsg],
            });
          }
        }
        // Cross-store sync: clear all agent-store state on connection loss
        if (changed) {
          const agentStore = useAgentStore.getState();
          for (const taskId of Object.keys(agentStore._taskToWorkspace)) {
            agentStore.stopAgentByTaskId(taskId);
          }
          // Clean up all active flush timers
          for (const [_convId, timer] of flushTimers) {
            clearInterval(timer);
          }
          flushTimers.clear();
        }
        return changed ? { conversations: next } : {};
      });
    },

    async loadHistory(conversationId, workspaceId, opts) {
      const existing = get().conversations.get(conversationId);
      if (opts?.force) {
        // Re-sync path (WS reconnect / tab became visible again): pull server
        // truth and patch messages missed while the socket was down. Server
        // drops WS frames for disconnected sessions (no replay), but the
        // conversation JSON on disk has everything.
        // Skip while streaming — live events are arriving, don't clobber.
        if (existing?.isStreaming) return;
      } else {
        // Skip if already loaded
        if (existing && existing.messages.length > 0) return;
      }

      try {
        const res = await historyApi.getMessages(workspaceId, conversationId);
        // API returns { conversation: { messages: [...] } } or { messages: [...] }
        const convData = (res as Record<string, unknown>).conversation as
          Record<string, unknown> | undefined;
        const rawMsgs = (convData?.messages ??
          (res as Record<string, unknown>).messages ??
          []) as Array<{
          role: string;
          content: string;
          agent_id?: string;
          agent_name?: string;
          timestamp?: string;
          tool_calls?: unknown[];
        }>;
        // Filter out tool messages — only show user and assistant
        const filtered = rawMsgs.filter((m) => m.role === "user" || m.role === "assistant");
        if (filtered.length === 0) return;

        const messages: ChatMessage[] = filtered.map((m, i) => {
          // History messages are persisted LLM message dicts (role/content/tool_calls/timestamp).
          // The real-time WS path produces rich blocks (text/tool_call/tool_result/...), but
          // history JSON only carries flat fields. Reconstruct blocks here so the message bubble
          // matches what the user saw live:
          //   1. attempt_completion: keep the existing extraction (text → content).
          //   2. Other tool_calls: render as completed tool_call blocks (collapsible in default
          //      mode, expanded in detailed mode) — fixes the "multiple empty 智能体 bubbles"
          //      bug where intermediate rounds have content="" + only tool_calls.
          //   3. If non-empty content remains after tool_calls handling, wrap as a text block
          //      so message.tsx renders it via its "other" branch (markdown).
          //   4. If nothing usable was produced (silent round / broken attempt_completion),
          //      blocks stays empty and message.tsx's existing fallthrough returns null —
          //      matching the legacy behavior for this edge case.
          let content = m.content ?? "";
          const blocks: ContentBlock[] = [];
          const toolCalls = m.tool_calls as
            Array<{ id?: string; function?: { name?: string; arguments?: string } }> | undefined;

          if (toolCalls && toolCalls.length > 0) {
            let attemptCompletionText: string | null = null;
            const otherCalls: Array<{ id?: string; name: string; arguments: string }> = [];

            for (const tc of toolCalls) {
              const name = tc.function?.name;
              if (!name) continue;
              if (name === "attempt_completion") {
                try {
                  const args = tc.function?.arguments ? JSON.parse(tc.function.arguments) : {};
                  if (args.result) attemptCompletionText = String(args.result);
                } catch {
                  // ignore parse errors — fall through and leave content as-is
                }
              } else {
                otherCalls.push({
                  id: tc.id,
                  name,
                  arguments: tc.function?.arguments ?? "",
                });
              }
            }

            // 1) attempt_completion → keep original behavior (merge into content)
            if (attemptCompletionText !== null) {
              content = content ? `${content}\n\n${attemptCompletionText}` : attemptCompletionText;
            }

            // 2) Other tool_calls → simple_text blocks (always visible across display modes).
            //    NOTE: We deliberately use simple_text instead of tool_call blocks. In the
            //    default display mode, message.tsx's filterBlocksByMode strips tool_call from
            //    the "other" bucket (see filterBlocksByMode line 253-254), so a message with
            //    ONLY tool_call blocks renders nothing — leaving an "avatar + 智能体 label"
            //    with no content (the symptom the user reported). simple_text is rendered
            //    in minimal/default/detailed, so it always shows up.
            //
            //    Args preview: stringify the parsed arguments (one line) so users can see
            //    which file/range/etc was touched at a glance. Keeps history compact vs.
            //    a full pretty JSON dump.
            for (const tc of otherCalls) {
              let argPreview = "";
              if (tc.arguments) {
                try {
                  const parsed = JSON.parse(tc.arguments);
                  if (parsed && typeof parsed === "object") {
                    // Extract the most common "identifier" fields for readability.
                    const id =
                      (parsed as Record<string, unknown>).file_path ??
                      (parsed as Record<string, unknown>).path ??
                      (parsed as Record<string, unknown>).query;
                    argPreview = id ? ` ${String(id)}` : "";
                  } else {
                    argPreview = ` ${String(parsed)}`;
                  }
                } catch {
                  argPreview = "";
                }
              }
              blocks.push({
                type: "simple_text",
                text: `${tc.name}${argPreview}`,
                kind: "history-tool-marker",
              });
            }
          }

          // 3) Wrap remaining content as a text block if no text block was already added.
          //    Avoid duplicate text blocks when attempt_completion merged into content.
          if (content && !blocks.some((b) => b.type === "text")) {
            blocks.push({ type: "text", text: content });
          }

          return {
            id: `hist-${conversationId}-${i}`,
            role: (m.role === "user" ? "user" : "assistant") as ChatMessage["role"],
            content, // kept for legacy fallback / backward compatibility
            blocks: blocks.length > 0 ? blocks : undefined,
            status: "complete" as const,
            ts: m.timestamp ? new Date(m.timestamp).getTime() : Date.now(),
          };
        });

        // Force-resync guard: only overwrite local messages when the server is
        // strictly ahead (messages were missed while disconnected). Equal count
        // → in sync, skip (avoids flicker on every tab-switch resync); fewer →
        // local has messages the server hasn't persisted yet (e.g. just sent),
        // skip so we don't drop them.
        if (opts?.force && existing) {
          const localCount = existing.messages.filter((m) => m.status !== "error").length;
          if (filtered.length <= localCount) return;
        }

        set((s) => {
          const next = new Map(s.conversations);
          let conv = next.get(conversationId);
          if (!conv) {
            // Create conversation entry with backend ID
            conv = {
              id: conversationId,
              title: "",
              messages,
              isStreaming: false,
              agentStatus: { mode: "idle" },
              streamBuffer: null,
            };
          } else {
            conv = { ...conv, messages };
          }
          next.set(conversationId, conv);
          return {
            conversations: next,
          };
        });
      } catch (e) {
        const errMsg = e instanceof Error ? e.message : String(e);
        if (opts?.force) {
          // Background re-sync — stay silent (no error banner) unless we have
          // nothing locally; the next resync/user action will retry.
          console.debug("[ChatStore] force resync failed:", errMsg);
          return;
        }
        console.error("[ChatStore] loadHistory failed:", e);
        set((s) => ({
          historyLoadErrors: { ...s.historyLoadErrors, [conversationId]: errMsg },
        }));
      }
    },

    async retryLoadHistory(conversationId, workspaceId) {
      // Clear error state before retry
      set((s) => {
        const next = { ...s.historyLoadErrors };
        delete next[conversationId];
        return { historyLoadErrors: next };
      });
      await get().loadHistory(conversationId, workspaceId);
    },

    // ── WebSocket message handler ───────────────────────────────

    _handleWsMessage(msg: WsMessage) {
      // Route strictly by conversation_id.
      // Messages without conversation_id are broadcast-type (task_node_*, etc.)
      // and are handled via window.dispatchEvent directly.
      const convId = msg.conversation_id;
      if (!convId) {
        // 🔧 安全网：终态事件缺 conversation_id 时不能直接丢弃。
        // 后端 user_workspace.current_conversation 是共享可变状态，任务执行期间
        // 可能被切换/清空为 None（生产事故 2026-09-17：AGENT_COMPLETE 缺 convId
        // 被丢弃，isStreaming 永不复位，停止按钮卡运行态）。终态意味着执行结束，
        // 回退收口本 tab 内所有仍在流式的会话（正常带 convId 的路径不受影响）。
        if (msg.type === "agent_complete" || msg.type === "agent_stopped") {
          for (const conv of get().conversations.values()) {
            if (conv.isStreaming || conv.streamBuffer) {
              get().finalizeStaleStreams(conv.id);
            }
          }
          if (msg.task_id) {
            useAgentStore.getState().stopAgentByTaskId(msg.task_id);
          }
        }
        return;
      }

      const handlers: Partial<Record<WsMessage["type"], () => void>> = {
        // ── Conversation info ──────────────────────────────────
        // Backend confirms the conversation. task.id = conversation_id
        // (both are backend UUIDs). Just ensure the conversation entry exists.
        conversation_info() {
          const backendConvId = msg.conversation_id;
          if (!backendConvId) return;

          set((s) => {
            const next = new Map(s.conversations);
            // If conversation already exists (created by ensureConversation), keep it
            if (next.has(backendConvId)) return {};
            // Otherwise create a minimal entry so subsequent messages have a home
            next.set(backendConvId, {
              id: backendConvId,
              title: "对话",
              messages: [],
              isStreaming: false,
              agentStatus: { mode: "idle" },
              streamBuffer: null,
            });
            return { conversations: next };
          });
        },

        // ── Assistant message (complete) ──────────────────────
        assistant_message() {
          const blocks =
            (msg.data?.blocks as ContentBlock[] | undefined) ??
            (msg.content ? [{ type: "text" as const, text: msg.content }] : []);

          const msgId = msg.message_id ?? uid();
          const assistantMsg: ChatMessage = {
            id: msgId,
            role: "assistant",
            content: msg.content ?? "",
            blocks: blocks.length > 0 ? blocks : undefined,
            agentId: msg.data?.agent_id as string | undefined,
            agentName: msg.data?.agent_name as string | undefined,
            messageId: msg.message_id,
            status: "complete",
            ts: Date.now(),
          };

          set((s) => {
            const next = new Map(s.conversations);
            const c = next.get(convId);
            if (!c) return {};
            const messages = [...c.messages];
            // Deduplicate: if a message with this ID already exists (e.g. from
            // _flushStreamBuffer during streaming), replace it instead of appending.
            const existingIdx = messages.findIndex((m) => m.id === msgId);
            if (existingIdx >= 0) {
              messages[existingIdx] = assistantMsg;
            } else {
              messages.push(assistantMsg);
            }
            next.set(convId, {
              ...c,
              isStreaming: false,
              streamBuffer: null,
              messages,
            });
            return { conversations: next };
          });
        },

        // ── Stream: content chunk ──────────────────────────────
        stream_content() {
          // 用户已停止（isStreaming=false）时丢弃迟到的流式分片，
          // 防止停止后内容继续增长/复活 streamBuffer。
          if (!get().conversations.get(convId)?.isStreaming) return;
          get()._startStreamBuffer(msg.message_id ?? uid(), convId);
          set((s) => {
            const next = new Map(s.conversations);
            const c = next.get(convId);
            if (!c) return {};
            const buf = c.streamBuffer;
            if (!buf) return {};
            next.set(convId, {
              ...c,
              streamBuffer: {
                ...buf,
                content: buf.content + (msg.content ?? ""),
                lastUpdate: Date.now(),
              },
            });
            return { conversations: next };
          });
        },

        // ── Stream: reasoning chunk ────────────────────────────
        stream_reasoning() {
          // 用户已停止（isStreaming=false）时丢弃迟到的推理分片，与 stream_content
          // 同守卫。此前无守卫：停止后到达的 stream_reasoning 会经 _startStreamBuffer
          // 把 isStreaming 复活为 true（生产事故 2026-09-18 08:28：stop 后后端收尾
          // LLM 流持续 8s 推 reasoning，忙碌态复活并靠 flush 的
          // isStreaming:!!streamActive 维持到 120s idle 超时，停止按钮反复出现）。
          if (!get().conversations.get(convId)?.isStreaming) return;
          get()._startStreamBuffer(msg.message_id ?? uid(), convId);
          set((s) => {
            const next = new Map(s.conversations);
            const c = next.get(convId);
            if (!c) return {};
            const buf = c.streamBuffer;
            if (!buf) return {};
            next.set(convId, {
              ...c,
              streamBuffer: {
                ...buf,
                reasoning: buf.reasoning + (msg.content ?? ""),
                lastUpdate: Date.now(),
              },
            });
            return { conversations: next };
          });
        },

        // ── Stream: complete ───────────────────────────────────
        stream_complete() {
          // Distinguish between intermediate rounds (agent loop with tool calls)
          // and the final round (finish_reason=stop). Intermediate rounds should
          // flush the current buffer into a message but NOT stop the agent.
          const finishReason = (msg as unknown as Record<string, unknown>).finish_reason as
            string | undefined;
          const rawToolCalls = (msg as unknown as Record<string, unknown>).tool_calls;
          const isIntermediate =
            finishReason === "tool_calls" ||
            (Array.isArray(rawToolCalls) && rawToolCalls.length > 0);

          // For reasoning-only models (GLM-4.7, DeepSeek Reasoner, etc.)
          // all streaming content arrives via stream_reasoning with empty
          // content deltas. stream_complete provides the merged final content
          // from CompleteMessage — update buffer so it's rendered to the user.
          if (msg.content && msg.content.trim()) {
            set((s) => {
              const next = new Map(s.conversations);
              const c = next.get(convId);
              if (!c) return {};
              const buf = c.streamBuffer;
              next.set(convId, {
                ...c,
                streamBuffer: buf ? { ...buf, content: msg.content! } : null,
              });
              return { conversations: next };
            });
          }

          get()._flushStreamBuffer(convId);

          if (isIntermediate) {
            // Intermediate round (tool_calls): flush buffer but keep agent running.
            // Clear buffer so next round gets a fresh bubble; keep timer & isStreaming.
            set((s) => {
              const next = new Map(s.conversations);
              const c = next.get(convId);
              if (!c) return {};
              next.set(convId, {
                ...c,
                streamBuffer: null,
                // Keep isStreaming=true and agentStatus as-is — agent is still working
              });
              return { conversations: next };
            });
          } else {
            // Final round (finish_reason=stop): full cleanup.
            // Clean up per-conversation flush timer
            const timer = flushTimers.get(convId);
            if (timer) {
              clearInterval(timer);
              flushTimers.delete(convId);
            }
            // Mark streaming complete
            set((s) => {
              const next = new Map(s.conversations);
              const c = next.get(convId);
              if (!c) return {};
              next.set(convId, {
                ...c,
                isStreaming: false,
                streamBuffer: null,
                agentStatus: { mode: "idle" },
              });
              return { conversations: next };
            });
            // 终态：与磁盘对账（见 scheduleHistoryReconcile 注释）
            scheduleHistoryReconcile(convId, msg.workspace_id);
            // Cross-store sync: stream ended → stop in agent-store
            if (msg.task_id) {
              useAgentStore.getState().stopAgentByTaskId(msg.task_id);
            }
          }
        },

        // ── Stream: tool call ──────────────────────────────────
        stream_tool_call() {
          // Backend (StreamToolCallMessage / protocol.py) sends fields flat at
          // the top level — NOT nested under msg.data. Read from msg directly.
          const toolCallId = msg.tool_call_id ?? uid();
          const toolName = msg.tool_name ?? "unknown";
          const toolInput = msg.tool_input;

          // Add both a tool_call block (for detailed mode) AND a tool_execution block (for default mode)
          // This ensures the tool is visible immediately during streaming in all display modes.
          set((s) => {
            const next = new Map(s.conversations);
            const c = next.get(convId);
            if (!c) return {};
            const msgs = [...c.messages];
            const lastIdx = msgs.length - 1;
            if (lastIdx < 0 || msgs[lastIdx].role !== "assistant") return {};

            const callBlock: ToolCallContentBlock = {
              type: "tool_call",
              toolCall: {
                tool_call_id: toolCallId,
                tool_name: toolName,
                tool_input: toolInput,
                status: "in_progress",
              },
            };

            const execBlock: ToolExecutionContentBlock = {
              type: "tool_execution",
              toolCallId: toolCallId,
              toolName,
              status: "executing",
              startTime: new Date().toISOString(),
            };

            const existing = msgs[lastIdx].blocks ?? [];
            // Avoid duplicate tool_execution blocks for the same tool
            const hasExecBlock = existing.some(
              (b) => b.type === "tool_execution" && b.toolName === toolName,
            );
            const newBlocks = hasExecBlock
              ? [...existing, callBlock]
              : [...existing, callBlock, execBlock];

            msgs[lastIdx] = {
              ...msgs[lastIdx],
              blocks: newBlocks,
            };
            next.set(convId, { ...c, messages: msgs });
            return { conversations: next };
          });
        },

        // ── Tool call start ────────────────────────────────────
        tool_call_start() {
          // Backend (ToolCallStartMessage) sends fields flat at the top level.
          const toolCallId = msg.tool_call_id ?? uid();
          const toolName = msg.tool_name ?? "unknown";

          const block: ToolCallContentBlock = {
            type: "tool_call",
            toolCall: {
              tool_call_id: toolCallId,
              tool_name: toolName,
              tool_input: msg.tool_input,
              status: "started",
            },
          };

          // Upsert into latest assistant message
          set((s) => {
            const next = new Map(s.conversations);
            const c = next.get(convId);
            if (!c) return {};
            const msgs = [...c.messages];
            const lastIdx = msgs.length - 1;
            if (lastIdx < 0) return {};

            // Find existing block with same tool_call_id
            const blocks = [...(msgs[lastIdx].blocks ?? [])];
            const existIdx = blocks.findIndex(
              (b) => b.type === "tool_call" && b.toolCall.tool_call_id === toolCallId,
            );
            if (existIdx >= 0) {
              blocks[existIdx] = block;
            } else {
              blocks.push(block);
            }
            msgs[lastIdx] = { ...msgs[lastIdx], blocks };
            next.set(convId, { ...c, messages: msgs });
            return { conversations: next };
          });

          // Cross-store sync: increment tool call count in monitoring store
          if (msg.task_id) {
            useMonitoringStore.getState().incrementToolCall(msg.task_id);
          }
        },

        // ── Tool call progress ─────────────────────────────────
        tool_call_progress() {
          // Backend (ToolCallProgressMessage) sends flat top-level fields.
          const raw = msg as unknown as Record<string, unknown>;
          const toolCallId = (raw.tool_call_id as string) ?? msg.tool_call_id ?? "";

          set((s) => {
            const next = new Map(s.conversations);
            const c = next.get(convId);
            if (!c) return {};
            const msgs = [...c.messages];
            const lastIdx = msgs.length - 1;
            if (lastIdx < 0) return {};

            const blocks = [...(msgs[lastIdx].blocks ?? [])];
            const blockIdx = blocks.findIndex(
              (b) => b.type === "tool_call" && b.toolCall.tool_call_id === toolCallId,
            );
            if (blockIdx < 0) return {};

            const existing = blocks[blockIdx] as ToolCallContentBlock;
            blocks[blockIdx] = {
              ...existing,
              toolCall: {
                ...existing.toolCall,
                status: "in_progress",
                progress_percentage: raw.progress_percentage as number | undefined,
                current_step: raw.current_step as string | undefined,
                current_step_index: raw.current_step_index as number | undefined,
                total_steps: raw.total_steps as number | undefined,
              },
            };
            msgs[lastIdx] = { ...msgs[lastIdx], blocks };
            next.set(convId, { ...c, messages: msgs });
            return { conversations: next };
          });
        },

        // ── Tool call result ───────────────────────────────────
        tool_call_result() {
          // Backend (ToolCallResultMessage) sends flat top-level fields.
          const raw = msg as unknown as Record<string, unknown>;
          const toolCallId = (raw.tool_call_id as string) ?? msg.tool_call_id ?? "";
          const result = raw.result;
          const isError = !!raw.is_error;
          const errorMsg = raw.error_message as string | undefined;
          const executionTime = raw.execution_time as number | undefined;
          const governance = raw.governance as GovernanceMeta | undefined;

          set((s) => {
            const next = new Map(s.conversations);
            const c = next.get(convId);
            if (!c) return {};
            const msgs = [...c.messages];
            const lastIdx = msgs.length - 1;
            if (lastIdx < 0) return {};

            const blocks = [...(msgs[lastIdx].blocks ?? [])];
            const blockIdx = blocks.findIndex(
              (b) => b.type === "tool_call" && b.toolCall.tool_call_id === toolCallId,
            );
            if (blockIdx >= 0) {
              const existing = blocks[blockIdx] as ToolCallContentBlock;
              blocks[blockIdx] = {
                ...existing,
                toolCall: {
                  ...existing.toolCall,
                  status: isError ? "failed" : "completed",
                  output: result,
                  error: errorMsg,
                  execution_time: executionTime,
                },
              };
            }

            // Also add a tool_result block
            const resultBlock: ToolResultContentBlock = {
              type: "tool_result",
              toolName: msg.tool_name ?? "unknown",
              result: result,
              isError: isError,
              executionTime: executionTime,
              errorMessage: errorMsg,
              governance: governance,
            };
            blocks.push(resultBlock);

            // attempt_completion: extract the result text and add as a visible
            // simple_text block so the user sees the final response in default mode.
            // (tool_result blocks are hidden in default display mode.)
            const toolName = msg.tool_name ?? "";

            // UI-B (§6.3): new_task/run_task → 子任务卡片块
            // （initialStatus 为结果快照；实时状态由渲染端联动 subtask-store）
            const subtaskCard = extractSubtaskCard(toolName, result);
            if (subtaskCard) {
              // run_task 结果不带 message → 从同 id 的 tool_call 块 tool_input 补齐
              const callBlock = blocks.find(
                (b) => b.type === "tool_call" && b.toolCall.tool_call_id === toolCallId,
              ) as ToolCallContentBlock | undefined;
              const inputMessage = (
                callBlock?.toolCall.tool_input as Record<string, unknown> | undefined
              )?.message;
              const cardBlock: SubtaskCardContentBlock = {
                type: "subtask_card",
                ...subtaskCard,
                message:
                  subtaskCard.message ?? (typeof inputMessage === "string" ? inputMessage : null),
                executionTime,
              };
              blocks.push(cardBlock);
            }

            // C21/§3.8.1：new_task_batch → 批量进度卡块（纯 UI 组件态；
            // 全部创建失败不进卡——错误明细由 tool_result 块承载）
            const batchCard = extractSubtaskBatchCard(toolName, result);
            if (batchCard) {
              blocks.push({ type: "subtask_batch_card", ...batchCard });
            }
            if (toolName === "attempt_completion" && !isError) {
              let resultText = "";
              if (typeof result === "string") {
                try {
                  const parsed = JSON.parse(result);
                  resultText = parsed.result ?? parsed.content ?? result;
                } catch {
                  resultText = result;
                }
              } else if (result && typeof result === "object") {
                resultText =
                  ((result as Record<string, unknown>).result as string) ??
                  ((result as Record<string, unknown>).content as string) ??
                  JSON.stringify(result, null, 2);
              }
              if (resultText) {
                blocks.push({
                  type: "simple_text",
                  text: resultText,
                  kind: "attempt_completion",
                } as SimpleTextContentBlock);
              }
            }

            msgs[lastIdx] = { ...msgs[lastIdx], blocks };
            next.set(convId, { ...c, messages: msgs });
            return { conversations: next };
          });
        },

        // ── System message ─────────────────────────────────────
        system_message() {
          const sysMsg: ChatMessage = {
            id: uid(),
            role: "system",
            content: msg.content ?? "",
            status: "complete",
            ts: Date.now(),
          };
          set((s) => {
            const next = new Map(s.conversations);
            const c = next.get(convId);
            if (!c) return {};
            next.set(convId, { ...c, messages: [...c.messages, sysMsg] });
            return { conversations: next };
          });
        },

        // ── Agent thinking ─────────────────────────────────────
        agent_thinking() {
          set((s) => {
            const next = new Map(s.conversations);
            const c = next.get(convId);
            if (!c) return {};
            next.set(convId, {
              ...c,
              agentStatus: { mode: "thinking", thinking: msg.content },
            });
            return { conversations: next };
          });
          // Cross-store sync: also update agent-store thinking state
          if (msg.task_id) {
            useAgentStore.getState().syncThinking(msg.task_id, msg.content ?? "");
          }
        },

        // ── Agent complete ─────────────────────────────────────
        agent_complete() {
          set((s) => {
            const next = new Map(s.conversations);
            const c = next.get(convId);
            if (!c) return {};
            next.set(convId, {
              ...c,
              isStreaming: false,
              agentStatus: { mode: "idle" },
            });
            return { conversations: next };
          });
          // 终态：与磁盘对账（见 scheduleHistoryReconcile 注释）
          scheduleHistoryReconcile(convId, msg.workspace_id);
          // Cross-store sync: agent completed → stop in agent-store
          if (msg.task_id) {
            useAgentStore.getState().stopAgentByTaskId(msg.task_id);
          }
        },

        // ── Agent stopped (user-initiated cancel confirmed by backend) ──
        // 与 stream_complete / agent_complete 同级的收尾分支：
        // flush 已缓冲的部分输出，清理 streaming/timer/agent-store，
        // 并把已落盘消息的 streaming/pending 状态收口为 complete（🔧 修复：
        // 此前已落盘消息的转圈在终态事件路径外永不复位）。
        agent_stopped() {
          get().finalizeStaleStreams(convId);
          // 终态：与磁盘对账（见 scheduleHistoryReconcile 注释）
          scheduleHistoryReconcile(convId, msg.workspace_id);
          // 跨 store 同步：停止 agent-store 里的执行态
          if (msg.task_id) {
            useAgentStore.getState().stopAgentByTaskId(msg.task_id);
          }
        },

        // ── Error ──────────────────────────────────────────────
        error() {
          console.log(
            "[ChatStore] error() handler called. convId:",
            convId,
            "msg:",
            JSON.stringify(msg).slice(0, 200),
          );
          // Clean up per-conversation flush timer
          const timer = flushTimers.get(convId);
          if (timer) {
            clearInterval(timer);
            flushTimers.delete(convId);
          }
          // Backend ErrorMessage serializes as {message: "...", details: {...}}
          // Frontend WsMessage uses {content: "...", data: {...}} — handle both
          const errText =
            ((msg as unknown as Record<string, unknown>).message as string) ??
            msg.content ??
            "未知错误";
          const errDetails =
            ((msg as unknown as Record<string, unknown>).details as Record<string, unknown>) ??
            msg.data;
          const errMsg: ChatMessage = {
            id: uid(),
            role: "assistant",
            content: "",
            blocks: [{ type: "error", message: errText, details: errDetails }],
            status: "error",
            ts: Date.now(),
          };
          set((s) => {
            const next = new Map(s.conversations);
            let c = next.get(convId);
            // If conversation doesn't exist yet (e.g. error arrived before conversation_info),
            // create it so the error is visible to the user.
            if (!c) {
              c = {
                id: convId,
                title: "对话",
                messages: [],
                model: "unknown",
                mode: "single" as const,
                isStreaming: false,
                agentStatus: { mode: "error" },
                streamBuffer: null,
              };
            }
            next.set(convId, {
              ...c,
              isStreaming: false,
              streamBuffer: null,
              agentStatus: { mode: "error" },
              messages: [...c.messages, errMsg],
            });
            return { conversations: next };
          });
          // 终态：与磁盘对账（见 scheduleHistoryReconcile 注释；子任务报错
          // 路由到父会话的 error 也会走到这里 —— 正是 2026-09-24 事故的自愈点）
          scheduleHistoryReconcile(convId, msg.workspace_id);
          // Cross-store sync: error occurred → stop in agent-store
          if (msg.task_id) {
            useAgentStore.getState().stopAgentByTaskId(msg.task_id);
          }
        },

        // ── TaskNode: start ──────────────────────────────────
        task_node_start() {
          const d = msg.data;
          if (!d) return;
          const workspaceId = msg.workspace_id ?? "";
          if (!workspaceId) return;
          const nodeId = (d.task_node_id as string) ?? "";
          const taskStore = useTaskStore.getState();
          taskStore.startTask(workspaceId, (d.task_id as string) ?? "");
          taskStore.updateNodeProgress(workspaceId, nodeId);
          // Dispatch for workspace-panel to react
          window.dispatchEvent(new CustomEvent("task:node_update", { detail: msg }));
        },

        // ── TaskNode: progress ───────────────────────────────
        task_node_progress() {
          const workspaceId = msg.workspace_id ?? "";
          if (!workspaceId) return;
          window.dispatchEvent(new CustomEvent("task:node_update", { detail: msg }));
        },

        // ── TaskNode: complete ───────────────────────────────
        task_node_complete() {
          const d = msg.data;
          if (!d) return;
          const workspaceId = msg.workspace_id ?? "";
          if (!workspaceId) return;
          const nodeId = (d.task_node_id as string) ?? "";
          const taskStore = useTaskStore.getState();
          taskStore.completeNode(workspaceId, nodeId);
          window.dispatchEvent(new CustomEvent("task:node_update", { detail: msg }));
        },

        // ── Follow-up question ─────────────────────────────────
        // ── Follow-up question (ask_followup_question, human-in-the-loop) ──
        // 后端 FollowupQuestionMessage 把 task_id/tool_call_id/question/suggestions 放在顶层。
        // 暂存到 conversation.followup，由 FollowupQuestionDialog 展示并收集用户回复。
        followup_question() {
          const taskId = msg.task_id ?? "";
          const toolCallId = msg.tool_call_id ?? "";
          const question = msg.question ?? msg.content ?? "";
          const suggestions = msg.suggestions ?? [];
          set((s) => {
            const next = new Map(s.conversations);
            const c = next.get(convId);
            if (!c) return {};
            next.set(convId, {
              ...c,
              agentStatus: { mode: "waiting_input" },
              followup: { question, suggestions, toolCallId, taskId },
            });
            return { conversations: next };
          });
        },
      };

      const handler = handlers[msg.type];
      if (handler) {
        handler();
      } else {
        if (msg.type === "error") {
          console.warn("[ChatStore] 'error' handler NOT matched. convId:", convId, "msg:", msg);
        }
      }
    },

    // ── Stream buffer management ────────────────────────────────

    _startStreamBuffer(messageId: string, conversationId: string) {
      set((s) => {
        const next = new Map(s.conversations);
        const c0 = next.get(conversationId);
        if (!c0) return {};
        // If buffer already exists with the SAME message id, no-op.
        // If a NEW message_id arrives (next agent-loop round), flush the
        // existing buffer into a message first, then start a fresh buffer
        // — otherwise all rounds get merged into one bubble.
        let c = c0;
        if (c.streamBuffer) {
          if (c.streamBuffer.messageId === messageId) return {}; // same round
          // Different round: flush old buffer into a message before replacing.
          const oldBuf = c.streamBuffer;
          const oldDisplay = oldBuf.content || oldBuf.reasoning;
          if (oldDisplay) {
            const msgs = [...c.messages];
            const oldIdx = msgs.findIndex((m) => m.id === oldBuf.messageId);
            const oldBlocks: ContentBlock[] = [];
            if (oldBuf.reasoning) {
              oldBlocks.push({ type: "reasoning", reasoning: oldBuf.reasoning });
            }
            if (oldBuf.content) {
              oldBlocks.push({ type: "text", text: oldBuf.content });
            }
            // Preserve non-stream blocks from prior updates. Keep
            // simple_text blocks too — tool_call_result may have pushed a
            // kind="attempt_completion" final report that must survive the
            // round-boundary flush (mirrors the fix in flushStreamBuffer).
            const priorBlocks =
              oldIdx >= 0
                ? (msgs[oldIdx]?.blocks ?? []).filter(
                    (b) => !["text", "reasoning", "thinking"].includes(b.type),
                  )
                : [];
            const flushedMsg: ChatMessage = {
              id: oldBuf.messageId,
              role: "assistant",
              content: oldDisplay,
              reasoning: oldBuf.reasoning || undefined,
              blocks:
                [...oldBlocks, ...priorBlocks].length > 0
                  ? [...oldBlocks, ...priorBlocks]
                  : undefined,
              status: "complete",
              ts: Date.now(),
            };
            if (oldIdx >= 0) {
              msgs[oldIdx] = flushedMsg;
            } else {
              msgs.push(flushedMsg);
            }
            c = { ...c, messages: msgs };
          }
        }

        next.set(conversationId, {
          ...c,
          isStreaming: true,
          streamBuffer: {
            messageId,
            content: "",
            reasoning: "",
            toolCalls: [],
            lastUpdate: Date.now(),
          },
        });

        // Start per-conversation flush timer
        if (!flushTimers.has(conversationId)) {
          const timer = setInterval(() => {
            get()._flushStreamBuffer(conversationId);
          }, FLUSH_INTERVAL);
          flushTimers.set(conversationId, timer);
        }

        return { conversations: next };
      });
    },

    _flushStreamBuffer(conversationId: string) {
      set((s) => {
        const next = new Map(s.conversations);
        const c = next.get(conversationId);
        if (!c) {
          // Clean up orphaned timer for deleted conversation
          const timer = flushTimers.get(conversationId);
          if (timer) {
            clearInterval(timer);
            flushTimers.delete(conversationId);
          }
          return {};
        }

        const buf = c.streamBuffer;
        if (!buf) {
          // Buffer already cleared — clean up timer
          const timer = flushTimers.get(conversationId);
          if (timer) {
            clearInterval(timer);
            flushTimers.delete(conversationId);
          }
          return {};
        }

        // Auto-cleanup stale streams: if no data received for STREAM_IDLE_TIMEOUT,
        // treat as interrupted and clean up to prevent timer leaks
        const idleTime = Date.now() - buf.lastUpdate;
        if (idleTime > STREAM_IDLE_TIMEOUT) {
          console.warn(
            `[ChatStore] Stream buffer for ${conversationId} timed out after ${idleTime}ms idle — auto-cleaning`,
          );
          const timer = flushTimers.get(conversationId);
          if (timer) {
            clearInterval(timer);
            flushTimers.delete(conversationId);
          }
          const timeoutContent = buf.content || buf.reasoning || "";
          const timeoutMsg: ChatMessage = {
            id: buf.messageId,
            role: "assistant",
            content: timeoutContent,
            reasoning: buf.reasoning || undefined,
            blocks: timeoutContent ? [{ type: "text" as const, text: timeoutContent }] : undefined,
            status: "error",
            ts: Date.now(),
          };
          const messages = [...c.messages];
          const existingIdx = messages.findIndex((m) => m.id === buf.messageId);
          if (existingIdx >= 0) {
            messages[existingIdx] = timeoutMsg;
          } else if (timeoutContent) {
            messages.push(timeoutMsg);
          }
          next.set(conversationId, {
            ...c,
            isStreaming: false,
            streamBuffer: null,
            agentStatus: { mode: "idle" },
            messages,
          });
          return { conversations: next };
        }

        // Find existing streaming message or create new one
        const existingIdx = c.messages.findIndex((m) => m.id === buf.messageId);

        // For reasoning-only models, content may be empty while reasoning
        // has the full response text. Use reasoning as content fallback so
        // the message renders correctly even without the stream_complete update.
        const displayContent = buf.content || buf.reasoning;

        // Build content blocks so that reasoning text stays visible above the
        // bubble when content starts arriving (fixes "thinking text disappears").
        // --- Preserve non-stream blocks (tool_call, tool_execution, tool_result,
        //     error, etc.) that were added to the message by other WS handlers
        //     (stream_tool_call, tool_call_start, tool_call_result).  Otherwise
        //     every flush cycle overwrites them. ---
        const existingMsg = existingIdx >= 0 ? c.messages[existingIdx] : undefined;
        // Preserve blocks added by non-stream WS handlers (tool_call, tool_execution,
        // tool_result, error). Also preserve simple_text blocks emitted by
        // tool_call_result (e.g. kind="attempt_completion") so that the final
        // completion report survives stream-buffer flushes. Strip only the
        // stream-derived text/reasoning/thinking so the buffered content can
        // take their place on the message.
        const preservedBlocks =
          existingMsg?.blocks?.filter((b) => !["text", "reasoning", "thinking"].includes(b.type)) ??
          [];

        const msgBlocks: ContentBlock[] = [];
        if (buf.reasoning) {
          msgBlocks.push({ type: "reasoning", reasoning: buf.reasoning });
        }
        // Only add a text block if we have real content (not just reasoning fallback).
        // When content is empty and reasoning provides the display text, the ChatMessage
        // component will use its legacy fallback rendering.
        if (buf.content) {
          msgBlocks.push({ type: "text", text: buf.content });
        }

        // Prepend preserved blocks (tool_call, tool_execution, etc.) so they
        // appear before the streaming text in detailed view.
        const allBlocks = [...msgBlocks, ...preservedBlocks];

        const streamMsg: ChatMessage = {
          id: buf.messageId,
          role: "assistant",
          content: displayContent,
          reasoning: buf.reasoning || undefined,
          blocks: allBlocks.length > 0 ? allBlocks : undefined,
          status: displayContent ? "streaming" : "pending",
          ts: Date.now(),
        };

        const messages = [...c.messages];
        if (existingIdx >= 0) {
          messages[existingIdx] = streamMsg;
        } else {
          messages.push(streamMsg);
        }

        // Only clear buffer if stream has truly ended (no content AND no reasoning).
        // Reasoning-only streams are still active — keep the buffer & timer.
        const streamActive = buf.content || buf.reasoning;
        next.set(conversationId, {
          ...c,
          messages,
          streamBuffer: streamActive ? buf : null,
          isStreaming: !!streamActive,
        });

        return { conversations: next };
      });
    },
  };
});

// ── Terminal-event history reconcile ────────────────────────────────
// 生产事故 2026-09-24（任务 64d83937 页面空白）：任务页打开时的历史 GET 早于
// 后端首次落盘（返回空），随后 WS 会话在服务端已断（帧被丢弃），流式事件
// 全部丢失——此后再无任何路径回拉历史，页面永久空白直到手动刷新。终态事件
// （完成/停止/出错）是天然的补拉时机：后端此时已把完整消息写入会话 JSON，
// 延迟 2s（留出最终落盘时间）强制回拉一次即可与磁盘对账。
// loadHistory 的 force 守卫保证仅在服务端消息严格多于本地时才覆盖。
const reconcileTimers = new Map<string, ReturnType<typeof setTimeout>>();
function scheduleHistoryReconcile(conversationId: string, wsId?: string) {
  if (reconcileTimers.has(conversationId)) return;
  const timer = setTimeout(() => {
    reconcileTimers.delete(conversationId);
    const workspaceId = wsId ?? wsClient.getWorkspaceId();
    if (!workspaceId) return;
    const { conversations, loadHistory } = useChatStore.getState();
    const conv = conversations.get(conversationId);
    // 会话不存在或仍在流式（live 事件在途）时不补拉
    if (!conv || conv.isStreaming) return;
    void loadHistory(conversationId, workspaceId, { force: true });
  }, 2000);
  reconcileTimers.set(conversationId, timer);
}

// ── Event bus subscriptions (decoupled from connection-store) ───────

on("ws:message", (detail) => {
  const msg = detail as unknown as WsMessage;
  useChatStore.getState()._handleWsMessage(msg);
});

on("ws:connection_lost", () => {
  useChatStore.getState().interruptAllStreams();
});

// Re-sync missed chat messages after a WS reconnect or when the tab becomes
// visible again. The server drops WS frames for disconnected sessions (no
// replay queue), but every message is persisted in the conversation JSON —
// so re-pull history and let loadHistory's force path patch the gap.
// Triggered by connection-store (reconnect / visibilitychange).
on("ws:resync_history", (detail) => {
  const { wsId } = (detail ?? {}) as { wsId?: string };
  if (!wsId) return;
  const { conversations, loadHistory } = useChatStore.getState();
  for (const [convId, conv] of conversations) {
    // 🔧 2026-09-24 事故：此前只回拉本地已有消息的会话——当历史 GET 早于后端
    // 落盘返回空、或流式事件随断线丢失时，本地 messages 恒为 0，重连/回前台
    // 也永远不会补拉，任务页永久空白。空会话同样强制回拉（磁盘为准；
    // loadHistory 的 force 守卫保证只在服务端严格领先时才覆盖本地）。
    if (!conv.isStreaming) {
      void loadHistory(convId, wsId, { force: true });
    }
  }
});
