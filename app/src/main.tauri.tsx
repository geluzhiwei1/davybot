// Tauri desktop app entry point — mounts TanStack Router SPA into the DOM.
import React from "react";
import ReactDOM from "react-dom/client";
import { RouterProvider } from "@tanstack/react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { getRouter } from "./router";
import { setSidecarBase } from "./lib/env";
import { IS_DESKTOP } from "./lib/platform";
import { SidecarOverlay } from "./components/sidecar-overlay";
import "./styles.css";

/**
 * Resolve the sidecar's runtime port (Tauri only) before first paint so every
 * HTTP/WS request targets the correct dynamically-picked localhost port. The
 * Rust host picks the port in setup() and exposes it via get_sidecar_port; this
 * runs before React mounts, so no consumer reads a stale base URL. Web build
 * (cloud / same-origin API) is a no-op.
 */
async function resolveSidecarBase(): Promise<void> {
  if (!IS_DESKTOP) return;
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    const port = await invoke<number | null>("get_sidecar_port");
    if (typeof port === "number" && port > 0) setSidecarBase(port);
  } catch (e) {
    console.warn("[sidecar] failed to resolve sidecar port", e);
  }
}

const router = getRouter();

// React Query client with sensible defaults
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000, // 30s before data is considered stale
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

const rootElement = document.getElementById("root")!;

// 全局兜底：OS 拖文件到页面非 drop 区时，浏览器默认会打开/替换当前页面。
// 各 drop 区（如工作区文件面板）自行处理并 preventDefault；这里只拦下
// 未被处理的默认行为，拖放不会再导致页面跳转。
window.addEventListener("dragover", (e) => e.preventDefault());
window.addEventListener("drop", (e) => e.preventDefault());

async function bootstrap(): Promise<void> {
  await resolveSidecarBase();
  ReactDOM.createRoot(rootElement).render(
    <React.StrictMode>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
        {/* SidecarOverlay renders null in web builds and once the sidecar is ready. */}
        <SidecarOverlay />
      </QueryClientProvider>
    </React.StrictMode>,
  );
}

bootstrap();

// Web PWA:注册离线壳 Service Worker(仅生产构建;桌面 Tauri 不走 SW)。
// 作用域 /app-ui/,策略见 public/sw.js;注册失败静默(不影响主流程)。
if (!IS_DESKTOP && import.meta.env.PROD && "serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker
      .register(`${import.meta.env.BASE_URL}sw.js`)
      .catch((e) => console.warn("[pwa] service worker registration failed", e));
  });
}
