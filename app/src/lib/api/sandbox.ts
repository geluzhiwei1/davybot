/**
 * Sandbox v2 REST API 客户端 — §14.7
 *
 * 复用 @/lib/api/client 的 request() (自动注入 JWT, 自动 401 刷新)
 */
import { request } from "./client";
import type {
  ProviderHealth,
  SandboxCapabilities,
  ProviderType,
  QuotaUsage,
  NetworkPolicy,
  SandboxSessionInfo,
  TestConnectionResult,
  SandboxUserSettings,
} from "../types/sandbox";

// ─── Provider ──────────────────────────────────────────────────────────────

export const sandboxProviderApi = {
  /** GET /api/system/sandbox/providers — 可用 Provider 列表 + 健康状态 */
  listProviders: () =>
    request<{ success: boolean; providers: ProviderHealth[] }>("/api/system/sandbox/providers"),

  /** GET /api/system/sandbox/capabilities?provider= — Provider 能力描述 */
  getCapabilities: (provider?: ProviderType) =>
    request<{ success: boolean; capabilities: SandboxCapabilities }>(
      `/api/system/sandbox/capabilities${provider ? `?provider=${provider}` : ""}`,
    ),

  /** GET /api/system/deployment-mode — 部署模式检测 */
  getDeploymentMode: () => request<{ mode: "local" | "saas" }>("/api/system/deployment-mode"),
};

// ─── Session ───────────────────────────────────────────────────────────────

export const sandboxSessionApi = {
  /** GET /api/sandbox/session/{workspace_id} — 当前会话沙箱状态 */
  getSession: (workspaceId: string) =>
    request<{ success: boolean; session: SandboxSessionInfo }>(
      `/api/sandbox/session/${workspaceId}`,
    ),
};

// ─── Quota ─────────────────────────────────────────────────────────────────

export const sandboxQuotaApi = {
  /** GET /api/sandbox/quota — 当前用户配额使用 */
  getQuota: () => request<{ success: boolean; quota: QuotaUsage }>("/api/sandbox/quota"),
};

// ─── Network Policy ────────────────────────────────────────────────────────

export const sandboxPolicyApi = {
  /** GET /api/sandbox/network-policy — 当前生效网络策略 (只读) */
  getPolicy: () =>
    request<{ success: boolean; policy: NetworkPolicy }>("/api/sandbox/network-policy"),
};

// ─── Test Connection ───────────────────────────────────────────────────────

export const sandboxTestApi = {
  /** POST /api/sandbox/test-connection — 测试 Provider 连接 */
  testConnection: (provider: ProviderType) =>
    request<{ success: boolean; result: TestConnectionResult }>("/api/sandbox/test-connection", {
      method: "POST",
      body: JSON.stringify({ provider }),
    }),
};

// ─── User Security Settings (sandbox v2 字段) ──────────────────────────────

export const sandboxSettingsApi = {
  /** GET /api/me/security — 读取 (含 sandbox v2 字段) */
  get: () =>
    request<{
      success: boolean;
      settings: Record<string, unknown> & Partial<SandboxUserSettings>;
    }>("/api/me/security"),

  /** PUT /api/me/security — 更新 (仅传 sandbox 字段) */
  updateSandbox: (settings: Partial<SandboxUserSettings>) =>
    request<{ success: boolean; settings: Record<string, unknown>; message: string }>(
      "/api/me/security",
      { method: "PUT", body: JSON.stringify(settings) },
    ),
};
