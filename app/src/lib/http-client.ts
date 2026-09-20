/**
 * Fetch-based HTTP client with auth and error interceptors.
 * Migrated from legalbot/webui/src/services/api/http.ts (axios → fetch).
 */
import type { ApiError, HttpConfig } from "@/lib/types/api";
import { STORAGE_KEYS, getApiBaseUrl } from "@/lib/env";

class NetworkError extends Error {
  constructor(
    message: string,
    public context?: { url?: string; method?: string },
  ) {
    super(message);
    this.name = "NetworkError";
  }
}

export { NetworkError };

/**
 * Per-call request options. `timeoutMs` overrides the client's default
 * `config.timeout` for a single request — use for slow endpoints (e.g. the
 * non-streaming QA RAG call) that legitimately exceed the default 15s cap.
 */
export interface RequestOptions {
  timeoutMs?: number;
}

export class HttpClient {
  private config: HttpConfig;

  constructor(config: HttpConfig) {
    this.config = config;
  }

  // ─── Public Methods ──────────────────────────────────────────────────

  async get<T>(url: string, params?: unknown): Promise<T> {
    const fullUrl = this.buildUrl(url, params);
    return this.request<T>("GET", fullUrl);
  }

  async post<T>(url: string, data?: unknown, opts?: RequestOptions): Promise<T> {
    return this.request<T>("POST", this.buildUrl(url), data, opts);
  }

  async put<T>(url: string, data?: unknown): Promise<T> {
    return this.request<T>("PUT", this.buildUrl(url), data);
  }

  async patch<T>(url: string, data?: unknown): Promise<T> {
    return this.request<T>("PATCH", this.buildUrl(url), data);
  }

  async delete<T>(url: string, params?: unknown): Promise<T> {
    const fullUrl = this.buildUrl(url, params);
    return this.request<T>("DELETE", fullUrl);
  }

  async upload<T>(url: string, formData: FormData): Promise<T> {
    const fullUrl = this.buildUrl(url);
    const token = this.getAuthToken();

    const response = await fetch(fullUrl, {
      method: "POST",
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: formData,
    });

    return this.processResponse<T>(response);
  }

  async download(url: string, params?: unknown): Promise<Blob> {
    const fullUrl = this.buildUrl(url, params);
    const token = this.getAuthToken();

    const response = await fetch(fullUrl, {
      method: "GET",
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    });

    if (!response.ok) {
      throw this.handleError(response);
    }

    return response.blob();
  }

  /**
   * POST that returns an async iterator of Server-Sent Events (SSE).
   *
   * Each yielded value is `{ event, id, data }` where `data` is already
   * JSON-parsed if the wire payload was a JSON object/array, otherwise it's
   * the raw string. Used by long-running endpoints that stream progress
   * (e.g. `/api/v1/qa/ask/stream` for RAG Q&A).
   *
   * The caller controls cancellation via `signal` (AbortController).
   * No request timeout — SSE streams are long-lived by design.
   */
  async *postSSE(
    url: string,
    data?: unknown,
    signal?: AbortSignal,
  ): AsyncGenerator<{ event: string; id?: string; data: unknown }, void, void> {
    const fullUrl = this.buildUrl(url);
    const token = this.getAuthToken();

    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      ...this.config.headers,
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    };

    const response = await fetch(fullUrl, {
      method: "POST",
      headers,
      body: data !== undefined ? JSON.stringify(data) : undefined,
      signal,
    });

    if (!response.ok) {
      throw await this.handleError(response);
    }
    if (!response.body) {
      throw new NetworkError("SSE response has no body", { url, method: "POST" });
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // SSE frames are separated by a blank line. Dispatch each complete
        // frame as soon as it arrives so the caller sees incremental progress.
        let sepIdx: number;
        while ((sepIdx = buffer.indexOf("\n\n")) !== -1) {
          const frame = buffer.slice(0, sepIdx);
          buffer = buffer.slice(sepIdx + 2);
          const parsed = parseSseFrame(frame);
          if (parsed) yield parsed;
        }
      }
      // Flush any trailing frame
      if (buffer.trim()) {
        const parsed = parseSseFrame(buffer);
        if (parsed) yield parsed;
      }
    } finally {
      reader.releaseLock();
    }
  }

  // ─── Config Management ───────────────────────────────────────────────

  updateConfig(newConfig: Partial<HttpConfig>): void {
    this.config = { ...this.config, ...newConfig };
  }

  setAuthToken(token: string): void {
    localStorage.setItem("auth_token", token);
  }

  clearAuthToken(): void {
    localStorage.removeItem(STORAGE_KEYS.authToken);
  }

  // ─── Internals ───────────────────────────────────────────────────────

  private buildUrl(path: string, params?: unknown): string {
    // Resolve the sidecar base lazily at request time so a dynamically-picked
    // Tauri port (injected after module load) is honored. An explicit
    // config.baseURL (non-sidecar clients) still wins.
    const base = (this.config.baseURL || getApiBaseUrl()).replace(/\/$/, "");
    const cleanPath = path.startsWith("/") ? path : `/${path}`;
    let url = `${base}${cleanPath}`;

    if (params && typeof params === "object") {
      const searchParams = new URLSearchParams();
      const entries = Object.entries(params as Record<string, unknown>);
      for (const [key, value] of entries) {
        if (value !== undefined && value !== null) {
          searchParams.set(key, String(value));
        }
      }
      const qs = searchParams.toString();
      if (qs) url += `?${qs}`;
    }

    return url;
  }

  private async request<T>(
    method: string,
    url: string,
    data?: unknown,
    opts?: RequestOptions,
  ): Promise<T> {
    // GETs are idempotent — retry transient connection failures (backend
    // restart blips, momentary proxy/worker stalls) with short backoff
    // instead of surfacing "Network request failed" to the user. Timeouts
    // and non-GET methods are never retried.
    const maxAttempts = method === "GET" ? 3 : 1;

    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
      const token = this.getAuthToken();
      const controller = new AbortController();
      const timeout = opts?.timeoutMs ?? this.config.timeout ?? 10000;
      const timer = setTimeout(() => controller.abort(), timeout);

      try {
        const headers: Record<string, string> = {
          "Content-Type": "application/json",
          ...this.config.headers,
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        };

        const response = await fetch(url, {
          method,
          headers,
          body: data !== undefined ? JSON.stringify(data) : undefined,
          signal: controller.signal,
        });

        return await this.processResponse<T>(response);
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          const apiError: ApiError = {
            code: 0,
            message: "Request timed out",
            timestamp: new Date().toISOString(),
            type: "TIMEOUT_ERROR",
          };
          throw apiError;
        }

        if (error instanceof TypeError) {
          // fetch network error — retry while attempts remain
          if (attempt < maxAttempts) {
            await new Promise((resolve) => setTimeout(resolve, 300 * attempt));
            continue;
          }
          throw new NetworkError("Network request failed: Unable to connect to server", {
            url,
            method,
          });
        }

        throw error;
      } finally {
        clearTimeout(timer);
      }
    }

    // Unreachable: the loop always returns or throws.
    throw new NetworkError("Network request failed: Unable to connect to server", { url, method });
  }

  private async processResponse<T>(response: Response): Promise<T> {
    if (!response.ok) {
      throw await this.handleError(response);
    }

    // For non-JSON responses (e.g. blob)
    const contentType = response.headers.get("content-type") || "";
    if (!contentType.includes("application/json")) {
      return response as unknown as T;
    }

    const json = await response.json();

    // Standard ApiResponse envelope
    if (json && typeof json.success === "boolean") {
      if (json.success) {
        return json as T;
      }

      // Business logic failure
      const error: ApiError = {
        code: json.code || 400,
        message: json.message || "API request failed",
        details: json,
        timestamp: new Date().toISOString(),
        type: "API_BUSINESS_ERROR",
      };
      throw error;
    }

    // Non-standard response — return as-is
    return json as T;
  }

  private async handleError(response: Response): Promise<ApiError> {
    let message: string;
    let details: unknown;

    try {
      const body = await response.json();
      message = body?.message || body?.detail || body?.error || response.statusText;
      details = body;
    } catch {
      message = response.statusText;
      details = undefined;
    }

    return {
      code: response.status,
      message,
      details,
      timestamp: new Date().toISOString(),
      type: this.getErrorType(response.status),
    };
  }

  private getErrorType(status: number): string {
    if (status >= 400 && status < 500) {
      switch (status) {
        case 400:
          return "BAD_REQUEST";
        case 401:
          return "UNAUTHORIZED";
        case 403:
          return "FORBIDDEN";
        case 404:
          return "NOT_FOUND";
        case 422:
          return "VALIDATION_ERROR";
        default:
          return "CLIENT_ERROR";
      }
    }
    if (status >= 500) return "SERVER_ERROR";
    return "UNKNOWN_ERROR";
  }

  private getAuthToken(): string | null {
    return localStorage.getItem(STORAGE_KEYS.authToken) || null;
  }
}

// ─── Default instance ──────────────────────────────────────────────────────

export const createHttpClient = (config?: Partial<HttpConfig>): HttpClient => {
  const defaultConfig: HttpConfig = {
    timeout: 10000,
    headers: { "Content-Type": "application/json" },
  };
  return new HttpClient({ ...defaultConfig, ...config });
};

export const httpClient = createHttpClient();

// ─── SSE helpers ────────────────────────────────────────────────────────

/** Parse one SSE frame (a block of "key: value" lines) into a typed event. */
function parseSseFrame(frame: string): { event: string; id?: string; data: unknown } | null {
  let event = "message";
  let id: string | undefined;
  const dataLines: string[] = [];

  for (const rawLine of frame.split(/\r?\n/)) {
    if (!rawLine || rawLine.startsWith(":")) continue; // blank/comment
    const colon = rawLine.indexOf(":");
    const field = colon === -1 ? rawLine : rawLine.slice(0, colon);
    // Per spec, a single leading space after the colon is stripped.
    let value = colon === -1 ? "" : rawLine.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);

    if (field === "event") event = value;
    else if (field === "id") id = value;
    else if (field === "data") dataLines.push(value);
  }

  if (dataLines.length === 0 && event === "message") return null;

  const dataStr = dataLines.join("\n");
  let data: unknown = dataStr;
  // Try JSON parse for convenience — fall back to raw string.
  if (dataStr) {
    const trimmed = dataStr.trim();
    if (
      (trimmed.startsWith("{") && trimmed.endsWith("}")) ||
      (trimmed.startsWith("[") && trimmed.endsWith("]"))
    ) {
      try {
        data = JSON.parse(trimmed);
      } catch {
        /* keep raw string */
      }
    }
  }
  return { event, id, data };
}
