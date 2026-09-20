/**
 * LLM Provider API — workspace-scoped LLM config and global model listing.
 */
import { request } from "./client";

// ── Types ────────────────────────────────────────────────────────────

export interface LLMProviderConfig {
  id: string;
  apiProvider: string;
  openAiBaseUrl?: string;
  openAiApiKey?: string;
  openAiModelId?: string;
  openAiLegacyFormat?: boolean;
  openAiHeaders?: Record<string, string>;
  openAiCustomModelInfo?: Record<string, unknown>;
  diffEnabled?: boolean;
  todoListEnabled?: boolean;
  fuzzyMatchThreshold?: number;
  rateLimitSeconds?: number;
  consecutiveMistakeLimit?: number;
  enableReasoningEffort?: boolean;
  toolChoice?: string;
  temperature?: number;
  timeout?: number;
  maxRetries?: number;
  retryDelay?: number;
}

export interface LLMProviderItem {
  name: string;
  source: "user" | "workspace" | "gateway" | string;
  config: {
    config: LLMProviderConfig;
    source: string;
  };
}

/** 后端 provider 目录条目（/llm-provider-catalog），前端下拉的单一数据源 */
export interface LLMProviderCatalogEntry {
  id: string;
  label: string;
  baseUrl: string;
  modelId: string;
  freeForm: boolean;
  description: string;
}

export interface LLMSessionSettings {
  currentApiConfigName: string | null;
  currentConfig: LLMProviderConfig | null;
  allConfigs: Record<string, LLMProviderConfig>;
  modeApiConfigs: Record<string, string>;
}

export interface LLMProviderCreatePayload {
  name: string;
  apiProvider: string;
  openAiBaseUrl?: string;
  openAiApiKey?: string;
  openAiModelId?: string;
  openAiLegacyFormat?: boolean;
  openAiHeaders?: Record<string, string>;
  openAiCustomModelInfo?: Record<string, unknown>;
  diffEnabled?: boolean;
  todoListEnabled?: boolean;
  fuzzyMatchThreshold?: number;
  rateLimitSeconds?: number;
  consecutiveMistakeLimit?: number;
  enableReasoningEffort?: boolean;
  toolChoice?: string;
  temperature?: number;
  timeout?: number;
  maxRetries?: number;
  retryDelay?: number;
  saveLocation?: "user" | "workspace";
}

// ── API ──────────────────────────────────────────────────────────────

export const llmApi = {
  /** GET /api/workspaces/{id}/llms — list model id/name pairs */
  listModels: (workspaceId: string) =>
    request<{ success: boolean; models: Array<{ llm_id: string; model_id: string }> }>(
      `/api/workspaces/${workspaceId}/llms`,
    ),

  /** GET /api/llms — list all globally available LLMs (not workspace-scoped) */
  listGlobalModels: () =>
    request<{
      availableLLMs: Array<{
        id: string;
        name: string;
        displayName?: string;
        provider?: string;
      }>;
    }>("/api/llms"),

  // ── User-level (no workspace required) ────────────────────────────────

  /** GET /api/users/me/llm-providers — list user-level providers */
  listUserProviders: () =>
    request<{
      success: boolean;
      settings: {
        current_config: string | null;
        user: LLMProviderItem[];
        workspace: LLMProviderItem[];
      };
    }>("/api/users/me/llm-providers"),

  /** POST /api/users/me/llm-providers — create user-level provider */
  createUserProvider: (data: LLMProviderCreatePayload) =>
    request<{
      success: boolean;
      message: string;
      provider: { name: string; id: string; config: LLMProviderConfig; location: string };
    }>("/api/users/me/llm-providers", { method: "POST", body: JSON.stringify(data) }),

  /** PUT /api/users/me/llm-providers/{name} — update user-level provider */
  updateUserProvider: (providerName: string, data: LLMProviderCreatePayload) =>
    request<{
      success: boolean;
      message: string;
      provider: { name: string; id: string; config: LLMProviderConfig };
    }>(`/api/users/me/llm-providers/${encodeURIComponent(providerName)}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  /** DELETE /api/users/me/llm-providers/{name} — delete user-level provider */
  deleteUserProvider: (providerName: string) =>
    request<{ success: boolean; message: string }>(
      `/api/users/me/llm-providers/${encodeURIComponent(providerName)}`,
      { method: "DELETE" },
    ),

  /** POST /api/users/me/llm-providers/test?mode= — test tool-call support (workspace-independent) */
  testUserProvider: (
    data: LLMProviderCreatePayload,
    mode: "stream" | "non-stream" = "non-stream",
  ) =>
    request<{ success: boolean; supported: boolean; message: string; model: string }>(
      `/api/users/me/llm-providers/test?mode=${mode}`,
      { method: "POST", body: JSON.stringify(data) },
    ),

  // ── Workspace-level ───────────────────────────────────────────────────

  /** GET /api/workspaces/{id}/llm-settings-all — all configs with source info */
  listSettingsAll: (workspaceId: string) =>
    request<{
      success: boolean;
      settings: {
        current_config: string | null;
        user: LLMProviderItem[];
        workspace: LLMProviderItem[];
        other?: LLMProviderItem[];
        mode_configs: Record<string, string>;
      };
    }>(`/api/workspaces/${workspaceId}/llm-settings-all`),

  /** GET /api/workspaces/{id}/llm-provider-catalog — provider 目录（后端单一数据源） */
  listProviderCatalog: (workspaceId: string) =>
    request<{ success: boolean; providers: LLMProviderCatalogEntry[] }>(
      `/api/workspaces/${workspaceId}/llm-provider-catalog`,
    ),

  /** GET /api/workspaces/{id}/llm-settings — merged settings */
  getSettings: (workspaceId: string) =>
    request<{ success: boolean; settings: LLMSessionSettings }>(
      `/api/workspaces/${workspaceId}/llm-settings`,
    ),

  /** POST /api/workspaces/{id}/llm-settings — update current config / mode configs */
  updateSettings: (
    workspaceId: string,
    data: { currentApiConfigName?: string | null; modeApiConfigs?: Record<string, string> },
  ) =>
    request<{ success: boolean; message: string }>(`/api/workspaces/${workspaceId}/llm-settings`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  /** POST /api/workspaces/{id}/llm-providers — create provider */
  createProvider: (workspaceId: string, data: LLMProviderCreatePayload) =>
    request<{
      success: boolean;
      message: string;
      provider: { name: string; id: string; config: LLMProviderConfig; location: string };
    }>(`/api/workspaces/${workspaceId}/llm-providers`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  /** PUT /api/workspaces/{id}/llm-providers/{name} — update provider */
  updateProvider: (workspaceId: string, providerName: string, data: LLMProviderCreatePayload) =>
    request<{
      success: boolean;
      message: string;
      provider: { name: string; id: string; config: LLMProviderConfig };
    }>(`/api/workspaces/${workspaceId}/llm-providers/${encodeURIComponent(providerName)}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  /** DELETE /api/workspaces/{id}/llm-providers/{name} — delete provider */
  deleteProvider: (workspaceId: string, providerName: string) =>
    request<{ success: boolean; message: string }>(
      `/api/workspaces/${workspaceId}/llm-providers/${encodeURIComponent(providerName)}`,
      { method: "DELETE" },
    ),

  /** POST /api/workspaces/{id}/llm-providers/test — test tool call support */
  testProvider: (workspaceId: string, data: LLMProviderCreatePayload) =>
    request<{ success: boolean; supported: boolean; message: string; model: string }>(
      `/api/workspaces/${workspaceId}/llm-providers/test`,
      { method: "POST", body: JSON.stringify(data) },
    ),

  /** GET /api/workspaces/{id}/llm-providers/effective — override-or-inherit 合并 user+ws */
  listEffective: (workspaceId: string) =>
    request<{
      success: boolean;
      current: string | null;
      default: Array<{ name: string; config: LLMProviderConfig }>;
      override: Array<{ name: string; config: LLMProviderConfig }>;
      effective: Array<{
        name: string;
        config: LLMProviderConfig;
        source: string;
        user_overridden: boolean;
      }>;
    }>(`/api/workspaces/${workspaceId}/llm-providers/effective`),
};
