/**
 * 自动更新 Zustand Store — 桌面应用更新状态管理
 *
 * 对应 Rust 端通过 tauri-plugin-updater 发出的 update-available 事件。
 * skippedVersions 持久化到 localStorage，其余为会话状态。
 */
import { create } from "zustand";
import { persist } from "zustand/middleware";

// ===================================================================
// State Type
// ===================================================================

export interface UpdateState {
  // Data
  /** 是否有可用更新 */
  checkUpdateAvailable: boolean;
  /** 新版本号，如 "0.2.0" */
  updateVersion: string | null;
  /** Release notes (Markdown) */
  updateNotes: string | null;
  /** 当前运行版本 */
  rawCurrentVersion: string | null;
  /** Update priority: "security" | "feature" | "patch" */
  updatePriority: string | null;
  /** If true, user cannot skip this update */
  updateForced: boolean;

  // Download state
  checking: boolean;
  downloading: boolean;
  downloadProgress: number; // 0–100
  installReady: boolean;
  error: string | null;

  // Skipped versions (persisted)
  skippedVersions: string[];

  // UI state
  dialogOpen: boolean;
  /** "checking" | "available" | "downloading" | "ready" | "error" | null */
  status: "checking" | "available" | "downloading" | "ready" | "error" | null;

  // Actions
  setUpdateInfo: (info: {
    version: string;
    notes?: string;
    currentVersion: string;
    priority?: string;
    forced?: boolean;
  }) => void;
  setChecking: (v: boolean) => void;
  setDownloading: (v: boolean) => void;
  setDownloadProgress: (pct: number) => void;
  setInstallReady: (v: boolean) => void;
  setError: (err: string | null) => void;
  setDialogOpen: (v: boolean) => void;
  setStatus: (s: UpdateState["status"]) => void;
  skipVersion: (version: string) => void;
  reset: () => void;
}

// ===================================================================
// Initial state factory
// ===================================================================

const initialState = {
  checkUpdateAvailable: false,
  updateVersion: null,
  updateNotes: null,
  rawCurrentVersion: null,
  updatePriority: null,
  updateForced: false,
  checking: false,
  downloading: false,
  downloadProgress: 0,
  installReady: false,
  error: null,
  dialogOpen: false,
  status: null as UpdateState["status"],
};

// ===================================================================
// Store
// ===================================================================

export const useUpdateStore = create<UpdateState>()(
  persist(
    (set) => ({
      ...initialState,
      skippedVersions: [],

      setUpdateInfo: (info) =>
        set({
          checkUpdateAvailable: true,
          updateVersion: info.version,
          updateNotes: info.notes ?? null,
          rawCurrentVersion: info.currentVersion,
          updatePriority: info.priority ?? null,
          updateForced: info.forced ?? false,
          status: "available",
        }),

      setChecking: (v) => set({ checking: v }),
      setDownloading: (v) => set({ downloading: v, status: v ? "downloading" : null }),
      setDownloadProgress: (pct) => set({ downloadProgress: pct }),
      setInstallReady: (v) => set({ installReady: v, status: v ? "ready" : null }),
      setError: (err) => set({ error: err, status: err ? "error" : null }),
      setDialogOpen: (v) => set({ dialogOpen: v }),
      setStatus: (s) => set({ status: s }),

      skipVersion: (version) =>
        set((state) => ({
          skippedVersions: [...state.skippedVersions, version],
          dialogOpen: false,
        })),

      reset: () => set({ ...initialState }),
    }),
    {
      name: "normnomos-update",
      partialize: (state) => ({
        skippedVersions: state.skippedVersions,
      }),
    },
  ),
);
