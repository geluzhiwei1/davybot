/**
 * 工作区分享 API（方案 project/docs/工作区分享功能方案.md）
 *
 * 两类端点、两类凭证，严格分开：
 * - Viewer（/api/shares/*，免登录公开页）：独立 fetch + X-Share-Token。
 *   绝不复用 client.ts request() —— 它会附加用户 Bearer 且 401 时强制登出跳转，
 *   对匿名访客页是错误行为。
 * - Owner（/api/workspaces/{wid}/share，应用内）：走 request()（用户 Bearer）。
 *
 * share-token 存 sessionStorage（关标签页即失效，防长期驻留）。
 */
import { ApiError, request } from "./client";
import { getApiBaseUrl, STORAGE_KEYS } from "../env";

// ── 类型 ────────────────────────────────────────────────────────────

export interface ShareStats {
  files: number;
  conversations: number;
  tasks: number;
  total_bytes: number;
}

export interface SharedWorkspaceMeta {
  display_name: string;
  description: string;
  created_at: string;
}

export interface ShareVerifyResponse {
  share_token: string;
  expires_at: string;
  workspace: SharedWorkspaceMeta;
  stats: ShareStats;
}

export interface ShareMetaResponse {
  workspace: SharedWorkspaceMeta;
  stats: ShareStats;
}

/** 后端 file-tree 为扁平列表（结构对齐 /api/workspaces/.../files/file-tree） */
export interface SharedFileNode {
  id: string;
  name: string;
  path: string;
  type: "directory" | "file";
  level: number;
  size: number;
  createdAt: string;
  updatedAt: string;
}

export interface SharedConversationSummary {
  id: string;
  title: string;
  messageCount?: number;
  createdAt?: string;
  updatedAt?: string;
  lastUpdated?: string;
  [k: string]: unknown;
}

export interface SharedMessage {
  role?: string;
  content?: unknown;
  blocks?: Array<{ type?: string; text?: string } & Record<string, unknown>>;
  [k: string]: unknown;
}

export interface SharedConversationDetail {
  id: string;
  title: string;
  messages: SharedMessage[];
  messageCount: number;
  pagination?: {
    skip: number;
    limit: number | null;
    returned: number;
    total: number;
    hasMore: boolean;
  };
  createdAt?: string;
  updatedAt?: string;
}

export interface SharedTask {
  task_id: string;
  description: string;
  status: string;
  mode?: string;
  priority?: number | null;
  todos?: Array<{ text?: string; done?: boolean }>;
  created_at?: string;
  updated_at?: string;
}

export interface SharedTaskGraph {
  graph_id: string;
  name: string;
  status: string;
  created_at?: string;
  total_tasks: number;
  tasks: SharedTask[];
}

/** Owner GET 视图（提取码回显 + clone_log 脱敏） */
export interface OwnerShareView {
  share_id: string;
  url: string;
  password: string | null;
  status: "active" | "closed";
  revoked: boolean;
  expired: boolean;
  created_at: string;
  expires_at: string;
  view_count: number;
  clone_count: number;
  clone_log: Array<{ user: string; at: string }>;
}

// ── share-token 存取（sessionStorage） ──────────────────────────────

const tokenKey = (shareId: string) => `share_token_${shareId}`;

export function getStoredShareToken(shareId: string): string | null {
  try {
    return sessionStorage.getItem(tokenKey(shareId));
  } catch {
    return null;
  }
}

export function storeShareToken(shareId: string, token: string): void {
  try {
    sessionStorage.setItem(tokenKey(shareId), token);
  } catch {
    // 隐私模式等存储失败 — 不阻断浏览（仅刷新后需重新验证）
  }
}

export function clearShareToken(shareId: string): void {
  try {
    sessionStorage.removeItem(tokenKey(shareId));
  } catch {
    // ignore
  }
}

// ── Viewer 端点（独立 fetch） ───────────────────────────────────────

/** 提取后端 {"detail": "..."} 错误文案（防爆破提示等需要原样展示） */
async function detailOf(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (body && typeof body.detail === "string") return body.detail;
  } catch {
    // ignore
  }
  return `HTTP ${res.status}`;
}

async function shareFetch<T>(shareId: string, path: string, init?: RequestInit): Promise<T> {
  const token = getStoredShareToken(shareId);
  const headers: Record<string, string> = { ...(init?.headers as Record<string, string>) };
  if (token) headers["X-Share-Token"] = token;
  const res = await fetch(`${getApiBaseUrl()}${path}`, { ...init, headers });
  if (!res.ok) {
    // 401 = token 失效/缺失；404 = 分享关闭/撤销/过期 — 调用方据此回落 Gate/失效页
    throw new ApiError(res.status, res.statusText, await detailOf(res));
  }
  return res.json() as Promise<T>;
}

export const shareViewerApi = {
  /** POST /api/shares/{id}/verify — 提取码换 share-token（429 带 Retry-After 秒数） */
  async verify(shareId: string, password: string): Promise<ShareVerifyResponse> {
    const res = await fetch(`${getApiBaseUrl()}/api/shares/${shareId}/verify`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password }),
    });
    if (res.status === 429) {
      const retryAfter = Number(res.headers.get("Retry-After") || "0");
      throw new ShareLockedError(await detailOf(res), retryAfter);
    }
    if (!res.ok) throw new ApiError(res.status, res.statusText, await detailOf(res));
    return res.json() as Promise<ShareVerifyResponse>;
  },

  meta: (shareId: string) => shareFetch<ShareMetaResponse>(shareId, `/api/shares/${shareId}/meta`),

  fileTree: (shareId: string) =>
    shareFetch<{ success: boolean; fileTree: SharedFileNode[] }>(
      shareId,
      `/api/shares/${shareId}/file-tree`,
    ),

  conversations: (shareId: string) =>
    shareFetch<{ conversations: SharedConversationSummary[]; total: number }>(
      shareId,
      `/api/shares/${shareId}/conversations`,
    ),

  conversation: (shareId: string, conversationId: string) =>
    shareFetch<{ conversation: SharedConversationDetail }>(
      shareId,
      `/api/shares/${shareId}/conversations/${conversationId}`,
    ),

  tasks: (shareId: string) =>
    shareFetch<{ graphs: SharedTaskGraph[] }>(shareId, `/api/shares/${shareId}/tasks`),

  /** 文件内容（blob）— preview=1 走安全 mimetype 白名单内联 */
  async file(shareId: string, path: string, preview = false): Promise<Blob> {
    const token = getStoredShareToken(shareId);
    const res = await fetch(
      `${getApiBaseUrl()}/api/shares/${shareId}/files/download?path=${encodeURIComponent(path)}&preview=${preview ? 1 : 0}`,
      { headers: token ? { "X-Share-Token": token } : {} },
    );
    if (!res.ok) throw new ApiError(res.status, res.statusText, await detailOf(res));
    return res.blob();
  },

  /**
   * POST /api/shares/{id}/clone — 双凭证：share-token + 用户 Bearer。
   * 纯服务端拷贝不经浏览器；大工作区可能分钟级 → 10 分钟超时，不设 30s 默认。
   */
  async clone(shareId: string): Promise<{ workspace_id: string; name: string }> {
    const token = getStoredShareToken(shareId);
    const userJwt = localStorage.getItem(STORAGE_KEYS.authToken);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 600_000);
    try {
      const res = await fetch(`${getApiBaseUrl()}/api/shares/${shareId}/clone`, {
        method: "POST",
        headers: {
          ...(token ? { "X-Share-Token": token } : {}),
          ...(userJwt ? { Authorization: `Bearer ${userJwt}` } : {}),
        },
        signal: controller.signal,
      });
      if (!res.ok) throw new ApiError(res.status, res.statusText, await detailOf(res));
      return res.json() as Promise<{ workspace_id: string; name: string }>;
    } finally {
      clearTimeout(timer);
    }
  },
};

/** 429 防爆破锁定 — Gate 显示倒计时 */
export class ShareLockedError extends Error {
  retryAfterSeconds: number;
  constructor(message: string, retryAfterSeconds: number) {
    super(message);
    this.retryAfterSeconds = retryAfterSeconds;
  }
}

// ── Owner 端点（request() = 用户 Bearer） ───────────────────────────

export type ShareExpiryDays = 1 | 3 | 7;

export const workspaceShareApi = {
  create: (workspaceId: string, expires_in_days: ShareExpiryDays, password?: string) =>
    request<{ share_id: string; url: string; password: string; expires_at: string }>(
      `/api/workspaces/${workspaceId}/share`,
      {
        method: "POST",
        body: JSON.stringify({ expires_in_days, ...(password ? { password } : {}) }),
      },
    ),

  get: (workspaceId: string) => request<OwnerShareView>(`/api/workspaces/${workspaceId}/share`),

  close: (workspaceId: string) =>
    request<{ status: string }>(`/api/workspaces/${workspaceId}/share/close`, { method: "POST" }),

  /** 续期/改期（不换链接不换码；已过期续期即复活） */
  updateExpiry: (workspaceId: string, expires_in_days: ShareExpiryDays) =>
    request<{ expires_at: string; status: string }>(`/api/workspaces/${workspaceId}/share`, {
      method: "PUT",
      body: JSON.stringify({ expires_in_days }),
    }),

  /** 重新开启；已过期须带有效期一步复活 */
  open: (workspaceId: string, expires_in_days?: ShareExpiryDays) =>
    request<{ status: string; expires_at: string }>(`/api/workspaces/${workspaceId}/share/open`, {
      method: "POST",
      body: JSON.stringify(expires_in_days ? { expires_in_days } : {}),
    }),

  revoke: (workspaceId: string) =>
    request<{ revoked: boolean }>(`/api/workspaces/${workspaceId}/share`, { method: "DELETE" }),
};
