/**
 * Hook to connect the app to the backend on mount.
 * Waits for auth initialization before fetching data.
 */

import { useEffect, useRef } from "react";
import { toast } from "sonner";
import { useConnectionStore } from "./connection-store";
import { healthApi } from "./api-client";
import { useStore } from "./store";
import { useAuthStore } from "./auth-store";
import { useWorkspaceStore } from "./workspace-store";

export function useBackendConnection() {
  // Use specific selectors to avoid subscribing to the entire store.
  // Zustand 5's useSyncExternalStore returns the full state on any change
  // when no selector is provided — this caused infinite loops in React 19.
  const state = useConnectionStore((s) => s.state);
  const connect = useConnectionStore((s) => s.connect);
  const disconnect = useConnectionStore((s) => s.disconnect);
  const authInitialized = useAuthStore((s) => s.initialized);
  const authenticated = useAuthStore((s) => s.authenticated);
  const currentWorkspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);
  const dataFetched = useRef(false);
  const offlineToasted = useRef(false);

  // 工作区切换 → WS 重连并携带新 workspace_id(连接绑定工作区后才能收到
  // 该工作区的过滤广播,如 task_node_* / subtask_lifecycle;ws-client 检测
  // 到 id 变化会自动断开重连)。初始连接用 workspaces[0],此处跟随用户选择。
  useEffect(() => {
    if (currentWorkspaceId) connect(currentWorkspaceId);
  }, [currentWorkspaceId, connect]);

  useEffect(() => {
    // Wait until auth validation completes AND user is authenticated
    if (!authInitialized || !authenticated) return;
    if (dataFetched.current) return;
    dataFetched.current = true;

    // Try to connect and fetch initial data.
    // Retry health check until sidecar is ready (Tauri sidecar takes a few seconds to start).
    const autoConnect = async () => {
      const MAX_RETRIES = 30; // up to ~90s
      const RETRY_INTERVAL = 3000; // 3s between retries

      let healthy = false;
      for (let i = 0; i < MAX_RETRIES; i++) {
        try {
          const controller = new AbortController();
          const timer = setTimeout(() => controller.abort(), 10000);
          await healthApi.check({ signal: controller.signal });
          clearTimeout(timer);
          healthy = true;
          break;
        } catch {
          if (i === 0) {
            console.log("[Backend] Waiting for sidecar to become ready...");
          }
          await new Promise((r) => setTimeout(r, RETRY_INTERVAL));
        }
      }

      if (!healthy) {
        console.log("[Backend] Server not available, running in offline mode");
        if (!offlineToasted.current) {
          offlineToasted.current = true;
          toast.error("无法连接到后端服务", {
            description:
              "Agent 服务 (端口 8431) 未运行，工作区和对话数据无法加载。请启动后端服务后刷新页面。",
            duration: 15000,
          });
        }
        return;
      }

      try {
        // Fetch real data from backend first to get workspace list
        await useStore.getState().fetchInitialData();

        // Connect with the first workspace ID so the WS client includes it in messages
        const workspaces = useStore.getState().workspaces;
        const firstWorkspaceId = workspaces.length > 0 ? workspaces[0].id : undefined;
        connect(firstWorkspaceId);
      } catch {
        console.log("[Backend] Failed to fetch initial data, running in offline mode");
        if (!offlineToasted.current) {
          offlineToasted.current = true;
          toast.error("无法加载初始数据", {
            description: "后端服务已连接，但加载数据失败。请刷新页面重试。",
            duration: 15000,
          });
        }
      }
    };

    autoConnect();
  }, [authInitialized, authenticated, connect]);

  useEffect(() => {
    return () => {
      disconnect();
    };
  }, [disconnect]);

  return { connectionState: state };
}
