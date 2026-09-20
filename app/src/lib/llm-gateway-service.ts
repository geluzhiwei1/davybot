/**
 * LLM Gateway API — 积分 & 模型代理相关接口
 * 通过 support system 的 LLM Gateway 代理访问
 */
import { SUPPORT_API_URL, STORAGE_KEYS } from "@/lib/env";
import { useAuthStore } from "@/lib/auth-store";
import { handleTokenRefresh } from "@/lib/api/client";

// ========== Types ==========

export interface GatewayModel {
  id: string;
  display_name: string;
  provider: string;
  context_window: number;
  supports_vision: boolean;
  supports_streaming: boolean;
  supports_function_calling: boolean;
  pricing: {
    input_rate: number;
    output_rate: number;
    unit: string;
  };
  tags: string[];
  is_active: boolean;
}

export interface UserPreferences {
  default_model: string | null;
  auto_mode_enabled: boolean;
  auto_mode_strategy: "balanced" | "cost_first" | "quality_first" | "fast_first";
  allowed_models: string[];
  blocked_models: string[];
}

export interface CreditsBalance {
  balance: number;
  frozen: number;
  total_recharged: number;
  total_consumed: number;
}

// ========== Helper ==========

function getAuthToken(): string | null {
  return localStorage.getItem(STORAGE_KEYS.authToken) || null;
}

async function gatewayRequest<T>(
  path: string,
  options: RequestInit = {},
  { silent401 = false }: { silent401?: boolean } = {},
): Promise<T> {
  const base = SUPPORT_API_URL.replace(/\/$/, "");
  // /support/api/../llm-api → /support/llm-api
  const url = `${base}/..${path}`;

  const buildHeaders = () => {
    const h: Record<string, string> = {
      "Content-Type": "application/json",
      ...(options.headers as Record<string, string>),
    };
    const token = getAuthToken();
    if (token) h["Authorization"] = `Bearer ${token}`;
    return h;
  };

  let headers = buildHeaders();
  let res = await fetch(url, { ...options, headers });

  // 401 auto-refresh (same pattern as client.ts request())
  if (res.status === 401 && getAuthToken()) {
    const refreshed = await handleTokenRefresh();
    if (refreshed) {
      headers = buildHeaders();
      res = await fetch(url, { ...options, headers });
    } else if (silent401) {
      // 尽力而为的展示性拉取（如初始化时的模型列表）：刷新失败只抛错，不强制登出
      throw new Error("Gateway unavailable (401)");
    } else {
      // Refresh failed — force logout
      useAuthStore.getState().logout();
      localStorage.removeItem(STORAGE_KEYS.authToken);
      localStorage.removeItem(STORAGE_KEYS.refreshToken);
      window.location.href = (import.meta.env.BASE_URL + "login").replace(/\/+/g, "/");
      throw new Error("Session expired — please log in again");
    }
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Gateway API error: ${res.status}`);
  }

  return res.json();
}

// ========== API Functions ==========

/** 获取可用模型列表（含定价信息）。
 *  后端可能返回 {object, data}（分页格式）、{models: [...]} 或裸数组，
 *  这里对三种形状都兼容，避免因 resp.data 为 undefined 而把官方模型判空。 */
export async function listGatewayModels(): Promise<GatewayModel[]> {
  // silent401：此函数在应用初始化（fetchModels）时被调用，网关不可达/拒绝 token 时
  // 不应强制登出用户，仅静默失败交由调用方降级处理。
  const resp = await gatewayRequest<unknown>("/llm-api/models", {}, { silent401: true });
  if (Array.isArray(resp)) return resp as GatewayModel[];
  if (resp && typeof resp === "object") {
    const r = resp as Record<string, unknown>;
    if (Array.isArray(r.data)) return r.data as GatewayModel[];
    if (Array.isArray(r.models)) return r.models as GatewayModel[];
    if (Array.isArray(r.items)) return r.items as GatewayModel[];
  }
  return [];
}

/** 获取用户模型偏好 */
export async function getPreferences(): Promise<UserPreferences> {
  return gatewayRequest<UserPreferences>("/llm-api/preferences");
}

/** 更新用户模型偏好 */
export async function updatePreferences(data: Partial<UserPreferences>): Promise<void> {
  await gatewayRequest<{ message: string }>("/llm-api/preferences", {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

/** 获取积分余额。
 *  - "user"（默认）：当前用户个人余额（/api/v1/credits/balance）
 *  - "tenant"：会话租户余额（/api/v1/tenant/credits/balance，需 token 带 tid） */
export async function getCreditsBalance(
  scope: "user" | "tenant" = "user",
): Promise<CreditsBalance> {
  const path = scope === "tenant" ? "/api/v1/tenant/credits/balance" : "/api/v1/credits/balance";
  return gatewayRequest<CreditsBalance>(path);
}
