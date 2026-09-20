/**
 * Market API client — connects to nn-user-system backend (:8766).
 * Self-contained fetch helper with JWT auth and 401 auto-redirect.
 */

import { redirectToLogin, useAuthStore } from "./auth-store";
import { handleTokenRefresh } from "./api/client";
import { MARKET_API_URL as ENV_MARKET_API_URL, getApiBaseUrl } from "./env";

// ── Config ──────────────────────────────────────────────────────────

const MARKET_API_URL = ENV_MARKET_API_URL;

// ── Fetch helper ────────────────────────────────────────────────────

async function marketRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  // server 自包含等未配置市场的构建: 快速失败, 不发请求 (多模式统一方案 §4
  // 「空 URL 不会被调用」的兜底 — 防通用 .env 的云端地址回落泄漏进构建)
  if (!MARKET_API_URL) {
    throw new Error("Market API not configured (VITE_MARKET_API_URL is empty)");
  }
  const url = `${MARKET_API_URL}${path}`;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };

  const token = localStorage.getItem("auth_token");
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  let res = await fetch(url, { ...options, headers });

  // On 401: try refresh once, then redirect to login
  if (res.status === 401) {
    // 自包含 local 模式无云端 JWT, 401 是常态 — 弹回登录会形成
    // 「密码门→进入→market 401→弹回」死循环, 只抛错让消费方降级
    if (useAuthStore.getState().localMode) {
      throw new Error("Market API 401 (local mode, no cloud JWT)");
    }
    const refreshed = await handleTokenRefresh();
    if (refreshed) {
      const newToken = localStorage.getItem("auth_token");
      if (newToken) {
        headers["Authorization"] = `Bearer ${newToken}`;
      }
      res = await fetch(url, { ...options, headers });
    } else {
      redirectToLogin();
      throw new Error("Session expired");
    }
  }

  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`Market API ${res.status}: ${body || res.statusText}`);
  }

  if (res.status === 204) return undefined as T;

  return res.json();
}

// ── Types ──────────────────────────────────────────────────────────

export interface MarketResource {
  id: string;
  type: string;
  name: string;
  slug?: string;
  description?: string;
  author?: string;
  version: string;
  tags: string[];
  extra_metadata?: Record<string, unknown>;
  visibility: string;
  status: string;
  owner_tenant_id?: string;
  owner_user_id?: string;
  downloads: number;
  rating_avg: number;
  rating_count: number;
  view_count: number;
  created_at: string;
  updated_at: string;
}

export interface ResourceListResponse {
  items: MarketResource[];
  total: number;
  page: number;
  page_size: number;
}

export interface ScanResult {
  scanned: number;
  indexed: number;
  updated: number;
  errors: number;
}

export interface DiscoveryStats {
  total_by_type: Record<string, number>;
  total_in_db: number;
}

export interface TeamMember {
  id: string;
  type: string;
  name: string;
  slug?: string;
  description?: string;
  author?: string;
  version: string;
  tags: string[];
  extra_metadata?: Record<string, unknown>;
  visibility: string;
  status: string;
  downloads: number;
  rating_avg: number;
  rating_count: number;
  view_count: number;
  created_at: string;
  updated_at: string;
}

export interface TeamHierarchyEntry {
  name: string;
  slug?: string;
  description?: string;
  icon?: string;
  team_type?: string;
  category?: string;
  priority?: number;
  enabled?: boolean;
  members?: TeamMember[];
  members_count?: number;
  subteams?: TeamHierarchyEntry[];
  parent_id?: string | null;
  level?: number;
  // Categorized member lists
  mcps?: TeamMember[];
  skills?: TeamMember[];
  knowledges?: TeamMember[];
  agents?: TeamMember[];
  [key: string]: unknown;
}

export interface TeamHierarchyResponse {
  teams: TeamHierarchyEntry[];
}

export interface InstallResult {
  success: boolean;
  path: string;
  message?: string;
}

export interface InstallV2Result {
  success: boolean;
  installed: Record<string, string[]>;
  error?: string;
}

// ── Resource APIs ──────────────────────────────────────────────────

export const marketApi = {
  /** List resources with optional filters */
  listResources: (params: {
    type?: string;
    page?: number;
    page_size?: number;
    search?: string;
    tags?: string;
    sort_by?: string;
    sort_order?: string;
  }) => {
    const query = new URLSearchParams();
    if (params.type) query.set("type", params.type);
    if (params.page) query.set("page", String(params.page));
    if (params.page_size) query.set("page_size", String(params.page_size));
    if (params.search) query.set("search", params.search);
    if (params.tags) query.set("tags", params.tags);
    if (params.sort_by) query.set("sort_by", params.sort_by);
    if (params.sort_order) query.set("sort_order", params.sort_order);
    const qs = query.toString();
    return marketRequest<ResourceListResponse>(`/v1/market/resources${qs ? `?${qs}` : ""}`);
  },

  /** Get a single resource */
  getResource: (resourceId: string) =>
    marketRequest<MarketResource>(`/v1/market/resources/${encodeURIComponent(resourceId)}`),

  /** Download a resource */
  downloadResource: (resourceId: string) =>
    marketRequest<{ download_url: string; resource_id: string }>(
      `/v1/market/resources/${encodeURIComponent(resourceId)}/download`,
    ),

  /** Trigger index-all for all resource types */
  indexAllResources: () =>
    marketRequest<{ results: Record<string, ScanResult> }>("/v1/market/discovery/index-all", {
      method: "POST",
    }),

  /** Get discovery stats */
  getDiscoveryStats: () => marketRequest<DiscoveryStats>("/v1/market/discovery/stats"),

  /** Get team hierarchy — agents grouped by team */
  getTeamHierarchy: () => marketRequest<TeamHierarchyResponse>("/v1/market/agents/teams/hierarchy"),
};

export { MARKET_API_URL };

// ── Bot API (nn-bot sidecar) ────────────────────────────────────────

async function botRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const url = `${getApiBaseUrl()}${path}`;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };

  const token = localStorage.getItem("auth_token");
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(url, { ...options, headers });

  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`Bot API ${res.status}: ${body || res.statusText}`);
  }

  if (res.status === 204) return undefined as T;

  return res.json();
}

export const botApi = {
  /** Install resources via nn-bot resource_installer.py */
  installResources: (params: {
    workspace: string;
    resource_id?: string;
    resource_ids?: string[];
    team_id?: string;
    team_meta?: Record<string, unknown>;
  }) =>
    botRequest<InstallV2Result>("/api/market/install-v2", {
      method: "POST",
      body: JSON.stringify(params),
    }),
};
