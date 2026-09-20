/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** nn-bot backend API base URL (REQUIRED) */
  readonly VITE_API_BASE_URL: string;
  /** WebSocket base URL (REQUIRED) */
  readonly VITE_WS_BASE_URL: string;
  /** Sanctions knowledge base API URL (REQUIRED) */
  readonly VITE_SANCTIONS_API_URL: string;
  /** nn-kb-searcher API URL (REQUIRED) */
  readonly VITE_KB_SEARCHER_API_URL: string;
  /** User system / support API URL (REQUIRED) */
  readonly VITE_SUPPORT_API_URL: string;
  /** Market API URL (REQUIRED) */
  readonly VITE_MARKET_API_URL: string;
  /** Market Flow 市场智能控制面 API URL (optional, default http://localhost:8054) */
  readonly VITE_MARKET_FLOW_API_URL?: string;
  /** gelu-research-flow 科研控制面 API URL (optional, default http://localhost:8056) */
  readonly VITE_RESEARCH_API_URL?: string;
  /** NormFlow law firm management API URL (REQUIRED) */
  readonly VITE_NORFLOW_API_URL: string;
  /** User center web base URL — opened in external browser (optional) */
  readonly VITE_USER_CENTER_BASE_URL?: string;
  /** WS reconnect delay (ms), default 2000 (optional) */
  readonly VITE_WS_RECONNECT_DELAY?: string;
  /** WS max reconnect attempts, 0 = infinite (default), >0 = finite cap (optional) */
  readonly VITE_WS_MAX_RECONNECT_ATTEMPTS?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

/** Build-time target injected by Vite `define` in vite.config.ts / vite.config.tauri.ts */
declare const __APP_TARGET__: "web" | "desktop" | "mobile";
