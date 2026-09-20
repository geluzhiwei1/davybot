/**
 * Platform abstraction — single source of truth for desktop/web/mobile branching.
 *
 * `__APP_TARGET__` is injected at build time by Vite `define`:
 *   - vite.config.ts       → "web"
 *   - vite.config.tauri.ts → "desktop" (default) / "mobile" (--mode mobile,
 *     Tauri Android/iOS builds — cloud mode, no local sidecar)
 *
 * Prefer `IS_DESKTOP` / `IS_MOBILE` / `IS_WEB` for build-time branching (dead
 * branches get tree-shaken). Use `isTauri()` only when you need a runtime check
 * (e.g. code that runs in both builds but must detect the Tauri webview at
 * runtime).
 */

/** True if building for the Tauri desktop app. Tree-shaken in web/mobile builds. */
export const IS_DESKTOP: boolean = __APP_TARGET__ === "desktop";

/** True if building for the Tauri mobile app (Android/iOS, cloud mode). */
export const IS_MOBILE: boolean = __APP_TARGET__ === "mobile";

/** True if building for the web/SaaS app. Tree-shaken in desktop builds. */
export const IS_WEB: boolean = !IS_DESKTOP && !IS_MOBILE;

/**
 * Runtime check for the Tauri environment. Prefer `IS_DESKTOP` for static
 * branching. This is useful when a single code path must behave differently
 * depending on whether `window.__TAURI__` exists at runtime.
 */
export function isTauri(): boolean {
  return typeof window !== "undefined" && "__TAURI__" in window;
}
