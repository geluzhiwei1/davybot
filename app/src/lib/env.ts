/**
 * Environment configuration — single source of truth for all service URLs.
 *
 * F1: 业务服务 URL(sanctions/kb-searcher)与账号体系一样是可选集成 ——
 * 未配置(空串) = 功能关闭,不 crash;消费端按 404/能力位降级。
 * 引擎同源 API/WS 留空 = 相对路径(同源)或运行时推导。
 */

// ── Auth / localStorage storage keys ──────────────────────────────────
export const STORAGE_KEYS = {
  authToken: "auth_token",
  refreshToken: "refresh_token",
  /**server 自包含模式的访问密码 (DAWEI_SERVER_PASSWORD; 仅 server 模式写入)*/
  serverPassword: "normnomos-server-password",
  language: "legent-language",
  displayMode: "normnomos-display-mode",
  lastModel: "normnomos-last-model",
  lastMode: "normnomos-last-mode",
  lastExpert: "normnomos-last-expert",
  compactMode: "normnomos-compact-mode",
  fontSize: "normnomos-font-size",
} as const;

// ── Optional env variables ────────────────────────────────────────────
// F1: 全部可选 —— 空 = 集成关闭(页面随 F2 core-only 隐藏;调用 404 降级)。
// SUPPORT / MARKET / NORFLOW / SANCTIONS / KB_SEARCHER 同策略。

// ── Derive WS URL from current page origin ────────────────────────────
// WebSocket requires an absolute URL (ws:// or wss://).  When
// VITE_WS_BASE_URL is left empty (server-embedded mode), we derive it
// from `window.location` so it always matches the current host/port.

function deriveWsUrl(): string {
  if (typeof window === "undefined") return "ws://localhost:8431";
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}`;
}

// ── Validate at module load ───────────────────────────────────────────
// (F1: 无必填变量 —— 全部可选,空 = 集成关闭)

// ── Exported constants ─────────────────────────────────────────────────

// VITE_API_BASE_URL: empty string = relative paths (same-origin API).
// Tauri mode sets this to "http://localhost:8431".
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "";

// VITE_WS_BASE_URL: empty string = derive from window.location at runtime.
// Tauri mode sets this to "ws://localhost:8431".
export const WS_BASE_URL = import.meta.env.VITE_WS_BASE_URL || deriveWsUrl();

// ── Tauri sidecar runtime override ───────────────────────────────────
// In the desktop app the bundled dawei sidecar listens on a *dynamically
// picked* localhost port (chosen by the Rust host, see
// src-tauri/src/main.rs). main.tauri.tsx resolves it via the
// `get_sidecar_port` command before first paint and injects it here.
// Web builds never call setSidecarBase(), so these stay null and the
// build-time VITE_* values above are used (cloud / same-origin).
let runtimeApiBase: string | null = null;
let runtimeWsBase: string | null = null;

/** Inject the sidecar's runtime localhost port (Tauri desktop only). */
export function setSidecarBase(port: number): void {
  runtimeApiBase = `http://localhost:${port}`;
  runtimeWsBase = `ws://localhost:${port}`;
}

/** Clear the sidecar override (falls back to build-time VITE_* values). */
export function clearSidecarBase(): void {
  runtimeApiBase = null;
  runtimeWsBase = null;
}

/** Resolve the current dawei HTTP base URL (sidecar port if set, else VITE value). */
export function getApiBaseUrl(): string {
  return runtimeApiBase ?? API_BASE_URL;
}

/** Resolve the current dawei WebSocket base URL (sidecar port if set, else VITE/derived). */
export function getWsBaseUrl(): string {
  return runtimeWsBase ?? WS_BASE_URL;
}
// F1: 业务服务可选 —— 空 = 关闭(未配置时相关页面已随 F2 core-only 隐藏)
export const SANCTIONS_API_URL = import.meta.env.VITE_SANCTIONS_API_URL || "";
export const UNISEARCHER_API_URL = import.meta.env.VITE_KB_SEARCHER_API_URL || "";
// 账号体系/市场/norflow — server 自包含模式留空 (F1 同策略:空=集成关闭)
export const SUPPORT_API_URL = import.meta.env.VITE_SUPPORT_API_URL || "";
export const MARKET_API_URL = import.meta.env.VITE_MARKET_API_URL || "";
export const NORFLOW_API_URL = import.meta.env.VITE_NORFLOW_API_URL || "";

// ── Optional config ───────────────────────────────────────────────────

/** User center web base URL — path appended in code */
export const USER_CENTER_BASE_URL = import.meta.env.VITE_USER_CENTER_BASE_URL || "";

// ── Server 自包含构建开关 ─────────────────────────────────────────────
// build:server = `vite build --mode server` → 云端依赖 UI 在构建期降级
// (资源市场入口 / 切换身份 / 我的账号 等;SaaS 形态不受影响)。
export const SERVER_BUILD = import.meta.env.MODE === "server";

// ── Optional numeric config ───────────────────────────────────────────

// VITE_WS_RECONNECT_DELAY: base backoff in ms (doubles up to 30s cap).
// VITE_WS_MAX_RECONNECT_ATTEMPTS: 0 = infinite reconnection (recommended —
//   auto-recovers from transient outages instead of dying after N failures).
export const WS_RECONNECT_DELAY = Number(import.meta.env.VITE_WS_RECONNECT_DELAY ?? 2000);
export const WS_MAX_RECONNECT_ATTEMPTS = Number(
  import.meta.env.VITE_WS_MAX_RECONNECT_ATTEMPTS ?? 0,
);
