/**
 * Infrastructure API — MCP servers, ACP agents, channels, security.
 */
import { request, type ApiResponse } from "./client";

// ── MCP Server API ──────────────────────────────────────────────────

export const mcpApi = {
  listServers: () =>
    request<
      ApiResponse<
        Array<{ id: string; name: string; transport: string; enabled: boolean; status: string }>
      >
    >("/api/mcp/servers"),

  addServer: (data: { name: string; transport: string; command?: string; url?: string }) =>
    request<ApiResponse<{ id: string }>>("/api/mcp/servers", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  updateServer: (id: string, data: { enabled?: boolean; command?: string; url?: string }) =>
    request<ApiResponse>(`/api/mcp/servers/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  deleteServer: (id: string) =>
    request<ApiResponse>(`/api/mcp/servers/${id}`, { method: "DELETE" }),

  getTools: (serverId: string) =>
    request<ApiResponse<Array<{ name: string; description: string }>>>(
      `/api/mcp/servers/${serverId}/tools`,
    ),
};

// ── User-Level MCP Server API ─────────────────────────────────────

export const userMcpApi = {
  listServers: () =>
    request<{ success: boolean; servers: WsMcpServerConfig[] }>("/api/users/me/mcp-servers"),

  addServer: (data: WsMcpServerConfig) =>
    request<{ success: boolean; message: string }>("/api/users/me/mcp-servers", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  updateServer: (serverName: string, data: Partial<WsMcpServerConfig>) =>
    request<{ success: boolean; message: string }>(
      `/api/users/me/mcp-servers/${encodeURIComponent(serverName)}`,
      { method: "PUT", body: JSON.stringify(data) },
    ),

  deleteServer: (serverName: string) =>
    request<{ success: boolean; message: string }>(
      `/api/users/me/mcp-servers/${encodeURIComponent(serverName)}`,
      { method: "DELETE" },
    ),

  testServer: (serverName: string) =>
    request<{ success: boolean; message: string }>(
      `/api/users/me/mcp-servers/${encodeURIComponent(serverName)}/test`,
      { method: "POST" },
    ),
};

// ── Local MCP Host API (light-app Tauri shell relay) ────────────────
// 仅壳内可达:demo 页面同源 fetch 经 inject.js shim → light_bridge 环回
// 端点 /api/mcp-host/*。command/env 只落本机,云端仅见服务器名。

export interface LocalMcpServer {
  name: string;
  command: string;
  args?: string[];
  env?: Record<string, string>;
  cwd?: string;
  timeout?: number;
  disabled?: boolean;
}

export interface LocalMcpHostStatus {
  running: boolean;
  api_base: string;
  registered: string;
  servers_enabled: number;
  enabled: string[];
  last_claim: string | null;
  last_error: string;
}

export interface LocalMcpTestResult {
  ok: boolean;
  server_info?: { name?: string; version?: string };
  protocol_version?: string;
  tools?: string[];
  error?: string | Record<string, unknown> | null;
}

export const localMcpApi = {
  listServers: () =>
    request<{ servers: LocalMcpServer[]; config_path: string; running_children: number }>(
      "/api/mcp-host/servers",
    ),

  /** upsert 全量覆盖(POST;created 区分新建/更新)。 */
  upsertServer: (data: LocalMcpServer) =>
    request<{ ok: boolean; created: boolean; name: string }>("/api/mcp-host/servers", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  deleteServer: (name: string) =>
    request<{ ok: boolean; name: string }>(`/api/mcp-host/servers/${encodeURIComponent(name)}`, {
      method: "DELETE",
    }),

  /** 连通性测试:initialize → tools/list(壳侧临时子进程,上限 30s/步)。 */
  testServer: (name: string) =>
    request<LocalMcpTestResult>(`/api/mcp-host/servers/${encodeURIComponent(name)}/test`, {
      method: "POST",
      timeoutMs: 70_000,
    }),

  status: () => request<LocalMcpHostStatus>("/api/mcp-host/status"),
};

// ── Workspace MCP Server API ────────────────────────────────────────

export interface WsMcpServerConfig {
  name: string;
  command?: string;
  args?: string[];
  cwd?: string;
  env?: Record<string, string>;
  transport?: "stdio" | "sse" | "http";
  url?: string;
  headers?: Record<string, string>;
  always_allow?: string[];
  timeout?: number;
  disabled?: boolean;
}

export const wsMcpApi = {
  listServers: (workspaceId: string) =>
    request<{ success: boolean; servers: WsMcpServerConfig[] }>(
      `/api/workspaces/${workspaceId}/mcp-servers`,
    ),

  addServer: (workspaceId: string, data: WsMcpServerConfig) =>
    request<{ success: boolean; message: string }>(`/api/workspaces/${workspaceId}/mcp-servers`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  updateServer: (workspaceId: string, serverName: string, data: Partial<WsMcpServerConfig>) =>
    request<{ success: boolean; message: string }>(
      `/api/workspaces/${workspaceId}/mcp-servers/${encodeURIComponent(serverName)}`,
      { method: "PUT", body: JSON.stringify(data) },
    ),

  deleteServer: (workspaceId: string, serverName: string) =>
    request<{ success: boolean; message: string }>(
      `/api/workspaces/${workspaceId}/mcp-servers/${encodeURIComponent(serverName)}`,
      { method: "DELETE" },
    ),

  testServer: (workspaceId: string, serverName: string) =>
    request<{ success: boolean; message: string }>(
      `/api/workspaces/${workspaceId}/mcp-servers/${encodeURIComponent(serverName)}/test`,
      { method: "POST" },
    ),

  /** GET /api/workspaces/{id}/mcp-servers/effective — override-or-inherit 合并 user+ws */
  listEffective: (workspaceId: string) =>
    request<{
      success: boolean;
      default: WsMcpServerConfig[];
      override: WsMcpServerConfig[];
      effective: Array<WsMcpServerConfig & { source: string; user_overridden: boolean }>;
    }>(`/api/workspaces/${workspaceId}/mcp-servers/effective`),

  /** GET /api/workspaces/{id}/mcp-servers/status — 主动探活（逐个连接，返回 status/tools/error） */
  listStatus: (workspaceId: string) =>
    request<{
      success: boolean;
      servers: Array<{
        name: string;
        status: string;
        tools_count: number;
        resources_count: number;
        error: string | null;
      }>;
    }>(`/api/workspaces/${workspaceId}/mcp-servers/status`),
};

// ── Workspace ACP Agent API ────────────────────────────────────────

export interface AcpAgentInfo {
  name: string;
  command: string;
  description?: string;
  disabled: boolean;
  path?: string;
}

export const acpAgentApi = {
  list: (workspaceId: string) =>
    request<{ success: boolean; agents: AcpAgentInfo[] }>(
      `/api/workspaces/${workspaceId}/acp-agents`,
    ),

  listAvailable: (workspaceId: string) =>
    request<{ success: boolean; agents: AcpAgentInfo[] }>(
      `/api/workspaces/${workspaceId}/acp-agents/available`,
    ),

  scan: (workspaceId: string) =>
    request<{ success: boolean; agents: AcpAgentInfo[]; message: string }>(
      `/api/workspaces/${workspaceId}/acp-agents/scan`,
      { method: "POST" },
    ),

  add: (workspaceId: string, data: { command: string; name?: string; description?: string }) =>
    request<{ success: boolean; message: string; agent: AcpAgentInfo }>(
      `/api/workspaces/${workspaceId}/acp-agents`,
      { method: "POST", body: JSON.stringify(data) },
    ),

  remove: (workspaceId: string, command: string) =>
    request<{ success: boolean; message: string }>(
      `/api/workspaces/${workspaceId}/acp-agents/${encodeURIComponent(command)}`,
      { method: "DELETE" },
    ),

  toggle: (workspaceId: string, command: string, disabled: boolean) =>
    request<{ success: boolean; message: string }>(
      `/api/workspaces/${workspaceId}/acp-agents/${encodeURIComponent(command)}/toggle`,
      { method: "PUT", body: JSON.stringify({ disabled }) },
    ),
};

// ── Workspace Channel API ──────────────────────────────────────────

export interface ChannelInfo {
  channel_type: string;
  registered: boolean;
  enabled: boolean;
  running: boolean;
  description?: string;
  capabilities?: Record<string, unknown>;
  config_fields?: Array<{
    name: string;
    type: string;
    required: boolean;
    default?: unknown;
    description?: string;
  }>;
}

export const channelApi = {
  list: (workspaceId: string) =>
    request<{ success: boolean; channels: ChannelInfo[] }>(
      `/api/workspaces/${workspaceId}/channels`,
    ),

  health: (workspaceId: string) =>
    request<{ success: boolean; channels: Record<string, { running: boolean; error?: string }> }>(
      `/api/workspaces/${workspaceId}/channels/health`,
    ),

  get: (workspaceId: string, channelType: string) =>
    request<{ success: boolean; channel: ChannelInfo }>(
      `/api/workspaces/${workspaceId}/channels/${channelType}`,
    ),

  updateConfig: (
    workspaceId: string,
    channelType: string,
    data: { enabled?: boolean; config?: Record<string, unknown> },
  ) =>
    request<{ success: boolean; message: string }>(
      `/api/workspaces/${workspaceId}/channels/${channelType}/config`,
      { method: "PUT", body: JSON.stringify(data) },
    ),

  enable: (workspaceId: string, channelType: string) =>
    request<{ success: boolean; message: string }>(
      `/api/workspaces/${workspaceId}/channels/${channelType}/enable`,
      { method: "POST" },
    ),

  disable: (workspaceId: string, channelType: string) =>
    request<{ success: boolean; message: string }>(
      `/api/workspaces/${workspaceId}/channels/${channelType}/disable`,
      { method: "POST" },
    ),
};

// ── Workspace Security API ─────────────────────────────────────────

export const securityApi = {
  get: (workspaceId: string) =>
    request<{ success: boolean; settings: Record<string, unknown> | null; message?: string }>(
      `/api/workspaces/${workspaceId}/security`,
    ),

  update: (workspaceId: string, settings: Record<string, unknown>) =>
    request<{ success: boolean; settings: Record<string, unknown>; message: string }>(
      `/api/workspaces/${workspaceId}/security`,
      { method: "PUT", body: JSON.stringify(settings) },
    ),

  reset: (workspaceId: string) =>
    request<{ success: boolean; message: string }>(
      `/api/workspaces/${workspaceId}/security/reset`,
      { method: "POST" },
    ),
};

// ── User-level Security API ─────────────────────────────────────────
// 用户级安全策略（所有工作区的默认值）。override-or-inherit：工作区可自由覆盖。

export const usersSecurityApi = {
  get: () =>
    request<{ success: boolean; settings: Record<string, unknown> | null; message?: string }>(
      `/api/me/security`,
    ),

  update: (settings: Record<string, unknown>) =>
    request<{ success: boolean; settings: Record<string, unknown>; message: string }>(
      `/api/me/security`,
      { method: "PUT", body: JSON.stringify(settings) },
    ),

  reset: () =>
    request<{ success: boolean; message: string }>(`/api/me/security/reset`, {
      method: "POST",
    }),
};
