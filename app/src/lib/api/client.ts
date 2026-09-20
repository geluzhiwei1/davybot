/**
 * Core HTTP client — extracted from api-client.ts for domain module reuse.
 * Provides request<T>(), requestMultipart<T>(), ApiError, and 401 auto-refresh.
 */
import type { ApiResponse } from "../types";
import { useAuthStore } from "../auth-store";
import { getApiBaseUrl, STORAGE_KEYS } from "../env";
import { toast } from "sonner";

// ── 401 refresh lock ────────────────────────────────────────────────
// The actual mutex lives in auth-store.ts refreshAccessToken() so that
// ALL callers (not just this module) share a single in-flight promise.
// This thin wrapper exists for ergonomic / import reasons.
const MAX_REFRESH_ATTEMPTS = 2;
let refreshAttempts = 0;

export async function handleTokenRefresh(): Promise<boolean> {
  return useAuthStore.getState().refreshAccessToken();
}

// ── ApiError ────────────────────────────────────────────────────────

/** Extract a readable error message from unknown catch values. */
export function errorMsg(e: unknown): string {
  if (e instanceof Error) return e.message;
  if (typeof e === "string") return e;
  try {
    return JSON.stringify(e);
  } catch {
    return String(e);
  }
}

/**
 * Show an error toast with a "复制" (Copy) action button.
 * Users can click the button to copy error details for investigation.
 */
export function toastError(title: string, e: unknown, opts?: { duration?: number }) {
  const msg = errorMsg(e);
  toast.error(title, {
    description: msg || undefined,
    duration: opts?.duration ?? 8000,
    action: msg
      ? {
          label: "复制",
          onClick: () => navigator.clipboard.writeText(`${title}: ${msg}`),
        }
      : undefined,
  });
}

export class ApiError extends Error {
  status: number;
  statusText: string;
  body: string;

  constructor(status: number, statusText: string, body: string) {
    super(`API Error ${status}: ${statusText}`);
    this.status = status;
    this.statusText = statusText;
    this.body = body;
  }
}

/**
 * Extract a human-readable reason from an API failure, parsing FastAPI's
 * {"detail": "..."} (or {"message": "..."}) JSON body and falling back to
 * the HTTP status text. Surfaces the backend's real failure reason on
 * surfaces like the LLM provider test, instead of a generic message.
 * Handles request timeouts (AbortError) explicitly.
 */
export function apiErrorDetail(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.body) {
      try {
        const parsed = JSON.parse(e.body);
        if (parsed && typeof parsed.detail === "string") return parsed.detail;
        if (parsed && typeof parsed.message === "string") return parsed.message;
      } catch {
        if (e.body.trim()) return e.body.trim();
      }
    }
    return `HTTP ${e.status} ${e.statusText}`.trim();
  }
  if (e instanceof Error) {
    if (e.name === "AbortError") return "请求超时或网络中断";
    return e.message;
  }
  return errorMsg(e);
}

// ── Generic fetch helper ────────────────────────────────────────────

export async function request<T>(
  path: string,
  options: RequestInit & { timeoutMs?: number } = {},
  baseUrl = getApiBaseUrl(),
): Promise<T> {
  const url = `${baseUrl}${path}`;
  const { timeoutMs = 30_000, ...fetchInit } = options;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(fetchInit.headers as Record<string, string>),
  };

  // Attach JWT if available; server 自包含模式下退化为访问密码 (DAWEI_SERVER_PASSWORD)
  const token =
    localStorage.getItem(STORAGE_KEYS.authToken) ??
    (useAuthStore.getState().localMode ? localStorage.getItem(STORAGE_KEYS.serverPassword) : null);
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  // Set request timeout (default 30s, overridable via timeoutMs)
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  const fetchOptions: RequestInit = {
    ...fetchInit,
    headers,
    signal: controller.signal,
  };

  let res: Response;
  try {
    res = await fetch(url, fetchOptions);
  } finally {
    clearTimeout(timeoutId);
  }

  // Auto-refresh on 401 (with retry guard to prevent infinite loops)
  if (res.status === 401 && token) {
    // Guard: if the request itself was already a retry after refresh, force logout
    if (refreshAttempts >= MAX_REFRESH_ATTEMPTS) {
      console.warn("[API] Auth refresh failed after retry — forcing logout");
      refreshAttempts = 0;
      useAuthStore.getState().logout();
      localStorage.removeItem(STORAGE_KEYS.authToken);
      localStorage.removeItem(STORAGE_KEYS.refreshToken);
      window.location.href = (import.meta.env.BASE_URL + "login").replace(/\/+/g, "/");
      throw new ApiError(401, "Unauthorized", "Session expired — please log in again");
    }

    refreshAttempts++;
    const refreshed = await handleTokenRefresh();
    if (refreshed) {
      // Retry with new token
      const newToken = localStorage.getItem(STORAGE_KEYS.authToken);
      if (newToken) {
        headers["Authorization"] = `Bearer ${newToken}`;
      }
      const retryController = new AbortController();
      const retryTimeoutId = setTimeout(() => retryController.abort(), timeoutMs);
      try {
        res = await fetch(url, { ...fetchInit, headers, signal: retryController.signal });
      } finally {
        clearTimeout(retryTimeoutId);
      }
      refreshAttempts = 0; // Reset on successful retry
    } else {
      // Refresh failed — force logout and redirect
      refreshAttempts = 0;
      useAuthStore.getState().logout();
      localStorage.removeItem(STORAGE_KEYS.authToken);
      localStorage.removeItem(STORAGE_KEYS.refreshToken);
      window.location.href = (import.meta.env.BASE_URL + "login").replace(/\/+/g, "/");
      throw new ApiError(401, "Unauthorized", "Session expired");
    }
  }

  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new ApiError(res.status, res.statusText, body);
  }

  // Reset refresh attempts on any successful request
  refreshAttempts = 0;

  // Handle 204 No Content
  if (res.status === 204) return undefined as T;

  return res.json();
}

// ── Multipart upload helper ─────────────────────────────────────────

/**
 * Upload file using multipart/form-data — bypasses request()'s
 * hardcoded Content-Type: application/json.  Supports 401 auto-refresh
 * using the same handleTokenRefresh() as request().
 */
export async function requestMultipart<T>(
  path: string,
  fieldName: string,
  file: File,
  baseUrl = getApiBaseUrl(),
): Promise<T> {
  const formData = new FormData();
  formData.append(fieldName, file);

  const url = `${baseUrl}${path}`;

  const buildHeaders = () => {
    const h: Record<string, string> = {};
    const token =
      localStorage.getItem(STORAGE_KEYS.authToken) ??
      (useAuthStore.getState().localMode
        ? localStorage.getItem(STORAGE_KEYS.serverPassword)
        : null);
    if (token) h["Authorization"] = `Bearer ${token}`;
    return h;
  };
  // DO NOT set Content-Type — let browser auto-generate multipart boundary

  let headers = buildHeaders();
  let res = await fetch(url, { method: "POST", headers, body: formData });

  // 401 auto-refresh (same pattern as request(); single bounded retry —
  // B8: refresh 失败不再静默吞掉,与 request() 一致强制登出并跳转登录页)
  if (res.status === 401 && localStorage.getItem(STORAGE_KEYS.authToken)) {
    const refreshed = await handleTokenRefresh();
    if (refreshed) {
      headers = buildHeaders();
      res = await fetch(url, { method: "POST", headers, body: formData });
    } else {
      useAuthStore.getState().logout();
      localStorage.removeItem(STORAGE_KEYS.authToken);
      localStorage.removeItem(STORAGE_KEYS.refreshToken);
      window.location.href = (import.meta.env.BASE_URL + "login").replace(/\/+/g, "/");
      throw new ApiError(401, "Unauthorized", "Session expired");
    }
  }

  if (!res.ok) {
    // B8:修正 ApiError 参序 —— (status, statusText, body),与 request() 对齐
    throw new ApiError(res.status, res.statusText, await res.text());
  }
  return res.json();
}

// Re-export types used by domain modules
export type { ApiResponse };
