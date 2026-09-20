/**
 * Conversation API — conversations, history, task context.
 */
import { request, type ApiResponse } from "./client";
import type { WorkspaceResources } from "./workspace";

// ── Conversation API ────────────────────────────────────────────────

export const conversationApi = {
  list: (workspaceId: string) =>
    request<{
      success: boolean;
      conversations: Array<{ id: string; title: string; created_at: string }>;
    }>(`/api/workspaces/${workspaceId}/conversations`),

  create: (workspaceId: string, title?: string) =>
    request<{ success: boolean; id: string; conversation_id?: string; title: string }>(
      `/api/workspaces/${workspaceId}/conversations`,
      {
        method: "POST",
        body: JSON.stringify({ title }),
      },
    ),

  /** POST /api/workspaces/{wsId}/conversations/{id} — rename conversation (workspace-scoped) */
  rename: (workspaceId: string, conversationId: string, title: string) =>
    request<ApiResponse>(`/api/workspaces/${workspaceId}/conversations/${conversationId}`, {
      method: "POST",
      body: JSON.stringify({ title }),
    }),

  /** DELETE /api/workspaces/{wsId}/conversations/{id} — delete conversation (workspace-scoped) */
  deleteScoped: (workspaceId: string, conversationId: string) =>
    request<ApiResponse>(`/api/workspaces/${workspaceId}/conversations/${conversationId}`, {
      method: "DELETE",
    }),
};

// ── Conversation History API ───────────────────────────────────────

export const historyApi = {
  getMessages: (workspaceId: string, conversationId: string) =>
    request<{
      success: boolean;
      // Backend nests messages under `conversation`; top-level `messages` kept as a
      // legacy/fallback shape. chat-store reads both (conversation.messages ?? messages).
      conversation?: {
        id?: string;
        title?: string;
        messages?: Array<{
          role: string;
          content: string;
          agent_id?: string;
          agent_name?: string;
          timestamp?: string;
        }>;
      };
      messages?: Array<{
        role: string;
        content: string;
        agent_id?: string;
        agent_name?: string;
        timestamp?: string;
      }>;
      message?: string;
    }>(`/api/workspaces/${workspaceId}/conversations/${conversationId}`),
};

// ── Task Context API ──────────────────────────────────────────────

export interface TaskContextData {
  id: string;
  title: string;
  status: string;
  mode: string;
  model: string;
  summary: string;
  key_decisions: string[];
  files: Array<{ path: string; type: string; description?: string; added_at?: string }>;
  variables: Record<string, string>;
}

export interface TaskGraphRef {
  graph_id: string;
  total_nodes: number;
  completed_nodes: number;
  status: "idle" | "running" | "completed" | "failed";
  nodes: Array<{ id: string; name: string; status: string }>;
}

export interface TaskContextResponse {
  success: boolean;
  task: TaskContextData;
  task_graph: TaskGraphRef | null;
  resources: WorkspaceResources;
}

export const taskContextApi = {
  /** GET /api/workspaces/{ws_id}/task-context/{conv_id} — aggregated task context */
  get: (workspaceId: string, conversationId: string) =>
    request<TaskContextResponse>(`/api/workspaces/${workspaceId}/task-context/${conversationId}`),

  /** PATCH /api/workspaces/{ws_id}/task-context/{conv_id} — update context fields */
  update: (
    workspaceId: string,
    conversationId: string,
    data: {
      summary?: string;
      key_decisions?: string[];
      files?: Array<{ path: string; type: string; description?: string }>;
      variables?: Record<string, string>;
    },
  ) =>
    request<{ success: boolean; metadata: Record<string, unknown> }>(
      `/api/workspaces/${workspaceId}/task-context/${conversationId}`,
      {
        method: "PATCH",
        body: JSON.stringify(data),
      },
    ),

  /** POST .../summarize — trigger LLM summarization */
  summarize: (workspaceId: string, conversationId: string) =>
    request<{ success: boolean; summary: string; key_decisions: string[] }>(
      `/api/workspaces/${workspaceId}/task-context/${conversationId}/summarize`,
      { method: "POST" },
    ),

  /** POST .../files — add file association */
  addFile: (
    workspaceId: string,
    conversationId: string,
    file: { path: string; type?: string; description?: string },
  ) =>
    request<{ success: boolean; file: Record<string, unknown>; total_files: number }>(
      `/api/workspaces/${workspaceId}/task-context/${conversationId}/files`,
      { method: "POST", body: JSON.stringify(file) },
    ),

  /** DELETE .../files — remove file association */
  removeFile: (workspaceId: string, conversationId: string, path: string) =>
    request<{ success: boolean; removed: string; total_files: number }>(
      `/api/workspaces/${workspaceId}/task-context/${conversationId}/files?path=${encodeURIComponent(path)}`,
      { method: "DELETE" },
    ),
};

// ── Skill API ───────────────────────────────────────────────────────

export const skillApi = {
  list: () =>
    request<
      ApiResponse<
        Array<{
          id: string;
          name: string;
          description: string;
          category: string;
          installed: boolean;
        }>
      >
    >("/api/skills"),

  install: (id: string) => request<ApiResponse>(`/api/skills/${id}/install`, { method: "POST" }),

  uninstall: (id: string) =>
    request<ApiResponse>(`/api/skills/${id}/uninstall`, { method: "POST" }),
};
