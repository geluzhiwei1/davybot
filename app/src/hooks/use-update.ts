/**
 * useUpdate — 桌面应用自动更新逻辑 Hook
 *
 * 封装 Tauri updater 插件的前端交互：
 *  - 监听 Rust 端发出的 update-available 事件
 *  - 提供手动检查更新（调用 Tauri check_update 命令）
 *  - 4 小时定时轮询
 *
 * 非 Tauri 环境下静默返回，不做任何操作。
 */
import { useEffect, useCallback, useRef } from "react";
import { useUpdateStore } from "@/lib/stores/update-store";
import { IS_DESKTOP } from "@/lib/platform";

// 4 小时轮询间隔（毫秒）
const POLL_INTERVAL_MS = 4 * 60 * 60 * 1000;

export function useUpdate() {
  const store = useUpdateStore();
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const initializedRef = useRef(false);

  // ── 监听 Rust 端发出的 update-available / update-ready 事件 ──
  useEffect(() => {
    if (!IS_DESKTOP) return;

    let unlistenAvailable: (() => void) | undefined;
    let unlistenReady: (() => void) | undefined;

    const setupListeners = async () => {
      try {
        const { listen } = await import("@tauri-apps/api/event");

        // Event: update-available (feature/major — user confirm)
        unlistenAvailable = await listen<{
          available: boolean;
          version: string | null;
          notes: string | null;
          current_version: string;
          priority: string | null;
          forced: boolean;
        }>("update-available", (event) => {
          if (!event.payload.available || !event.payload.version) return;

          // 检查是否已被用户跳过（forced 更新不可跳过）
          if (!event.payload.forced && store.skippedVersions.includes(event.payload.version)) {
            console.log("[updater] version", event.payload.version, "was skipped, ignoring");
            return;
          }

          store.setUpdateInfo({
            version: event.payload.version,
            notes: event.payload.notes ?? undefined,
            currentVersion: event.payload.current_version,
            priority: event.payload.priority ?? undefined,
            forced: event.payload.forced,
          });
          store.setDialogOpen(true);
        });

        // Event: update-ready (patch — already installed, just need restart)
        unlistenReady = await listen<{
          available: boolean;
          version: string | null;
          notes: string | null;
          current_version: string;
          priority: string | null;
          forced: boolean;
        }>("update-ready", (event) => {
          if (!event.payload.version) return;
          store.setUpdateInfo({
            version: event.payload.version,
            notes: event.payload.notes ?? undefined,
            currentVersion: event.payload.current_version,
            priority: event.payload.priority ?? "patch",
            forced: true,
          });
          store.setInstallReady(true);
          store.setDialogOpen(true);
        });
      } catch {
        // Tauri API not available — silently skip
      }
    };

    setupListeners();

    return () => {
      unlistenAvailable?.();
      unlistenReady?.();
    };
  }, [store.skippedVersions]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── 手动检查更新 ────────────────────────────────────────
  const checkForUpdates = useCallback(async () => {
    if (!IS_DESKTOP) return;

    store.setChecking(true);
    store.setStatus("checking");
    store.setError(null);

    try {
      const { invoke } = await import("@tauri-apps/api/core");
      const result = await invoke<{
        available: boolean;
        version: string | null;
        notes: string | null;
        current_version: string;
        priority: string | null;
        forced: boolean;
      }>("check_update");

      if (result.available && result.version) {
        if (!result.forced && store.skippedVersions.includes(result.version)) {
          store.setChecking(false);
          store.setStatus(null);
          return;
        }
        store.setUpdateInfo({
          version: result.version,
          notes: result.notes ?? undefined,
          currentVersion: result.current_version,
          priority: result.priority ?? undefined,
          forced: result.forced,
        });
        store.setDialogOpen(true);
      }

      store.setChecking(false);
      if (!result.available) {
        store.setStatus(null);
      }
    } catch (err) {
      store.setChecking(false);
      store.setError(err instanceof Error ? err.message : String(err));
    }
  }, [store]);

  // ── 4 小时定时轮询 ──────────────────────────────────────
  useEffect(() => {
    if (!IS_DESKTOP) return;
    if (initializedRef.current) return;
    initializedRef.current = true;

    // 启动 30 秒后首次轮询（与 Rust 端的自动检查错开）
    const timeout = setTimeout(() => {
      checkForUpdates();
      pollTimerRef.current = setInterval(checkForUpdates, POLL_INTERVAL_MS);
    }, 60_000);

    return () => {
      clearTimeout(timeout);
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
  }, [checkForUpdates]);

  // ── 下载并安装更新 ──────────────────────────────────────
  const downloadAndInstall = useCallback(async () => {
    if (!IS_DESKTOP) return;

    store.setDownloading(true);
    store.setDownloadProgress(0);
    store.setError(null);

    try {
      const { invoke } = await import("@tauri-apps/api/core");
      // Tauri v2 updater: download + install happens on Rust side via command
      await invoke("download_and_install_update");
      // Note: app.restart() is called inside the Rust command after install,
      // so we may not reach this line.
      store.setInstallReady(true);
    } catch (err) {
      store.setDownloading(false);
      store.setError(err instanceof Error ? err.message : String(err));
    }
  }, [store]);

  // ── 跳过此版本 ──────────────────────────────────────────
  const skipVersion = useCallback(() => {
    if (store.updateVersion) {
      store.skipVersion(store.updateVersion);
    }
  }, [store]);

  // ── 稍后提醒 ────────────────────────────────────────────
  const remindLater = useCallback(() => {
    store.setDialogOpen(false);
  }, [store]);

  return {
    // State
    updateAvailable: store.checkUpdateAvailable,
    updateVersion: store.updateVersion,
    updateNotes: store.updateNotes,
    currentVersion: store.rawCurrentVersion,
    priority: store.updatePriority,
    forced: store.updateForced,
    checking: store.checking,
    downloading: store.downloading,
    downloadProgress: store.downloadProgress,
    installReady: store.installReady,
    error: store.error,
    dialogOpen: store.dialogOpen,
    status: store.status,

    // Actions
    checkForUpdates,
    downloadAndInstall,
    skipVersion,
    remindLater,
    dismissError: () => store.setError(null),
    setDialogOpen: store.setDialogOpen,
  };
}
