/**
 * Sandbox v2 Zustand Store — §14.4
 *
 * 状态切片:
 * - selectedProvider: 用户配置 (persist)
 * - actualProvider: 后端 detect 结果 (非 persist)
 * - capabilities / status / quotaUsage / reconnectDeadline / lastError
 *
 * 订阅模式: 使用 selector 避免大面积 rerender
 */
import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import type {
  ProviderType,
  SandboxCapabilities,
  SandboxStatus,
  QuotaUsage,
  SandboxError,
  ProviderHealth,
} from "../types/sandbox";
import { sandboxProviderApi, sandboxQuotaApi, sandboxSettingsApi } from "../api/sandbox";

interface SandboxStoreState {
  // ─── State ───────────────────────────────────────────────────
  selectedProvider: ProviderType;
  actualProvider: ProviderType | null;
  capabilities: SandboxCapabilities | null;
  providers: ProviderHealth[];
  status: SandboxStatus;
  quotaUsage: QuotaUsage | null;
  reconnectDeadline: number | null; // epoch ms
  lastError: SandboxError | null;
  isInitializing: boolean;

  // ─── Actions ─────────────────────────────────────────────────
  loadInitial: () => Promise<void>;
  setProvider: (p: ProviderType) => Promise<void>;
  refreshQuota: () => Promise<void>;
  setStatus: (s: SandboxStatus) => void;
  setReconnectDeadline: (t: number | null) => void;
  setError: (e: SandboxError | null) => void;
}

export const useSandboxStore = create<SandboxStoreState>()(
  persist(
    (set, _get) => ({
      // ─── Initial State ──────────────────────────────────────
      selectedProvider: "auto",
      actualProvider: null,
      capabilities: null,
      providers: [],
      status: "uninitialized",
      quotaUsage: null,
      reconnectDeadline: null,
      lastError: null,
      isInitializing: false,

      // ─── Actions ────────────────────────────────────────────
      loadInitial: async () => {
        set({ isInitializing: true });
        try {
          const [providersRes, quotaRes, settingsRes] = await Promise.allSettled([
            sandboxProviderApi.listProviders(),
            sandboxQuotaApi.getQuota(),
            sandboxSettingsApi.get(),
          ]);

          if (providersRes.status === "fulfilled") {
            set({ providers: providersRes.value.providers });
            // detect actual provider (first available)
            const firstAvail = providersRes.value.providers.find((p) => p.available);
            if (firstAvail) {
              set({ actualProvider: firstAvail.provider });
            }
          }

          if (quotaRes.status === "fulfilled") {
            set({ quotaUsage: quotaRes.value.quota });
          }

          if (settingsRes.status === "fulfilled" && settingsRes.value.settings?.sandbox_provider) {
            set({
              selectedProvider: settingsRes.value.settings.sandbox_provider as ProviderType,
            });
          }

          // Fetch capabilities for selected/actual provider
          try {
            const capsRes = await sandboxProviderApi.getCapabilities(_get().selectedProvider);
            set({ capabilities: capsRes.capabilities });
          } catch {
            // capabilities 非关键, 失败静默
          }
        } finally {
          set({ isInitializing: false });
        }
      },

      setProvider: async (p: ProviderType) => {
        set({ selectedProvider: p });
        try {
          await sandboxSettingsApi.updateSandbox({ sandbox_provider: p });
          // 刷新 capabilities
          const capsRes = await sandboxProviderApi.getCapabilities(p);
          set({ capabilities: capsRes.capabilities });
        } catch {
          // 保存失败不回滚 UI, 用户可重试
        }
      },

      refreshQuota: async () => {
        try {
          const res = await sandboxQuotaApi.getQuota();
          set({ quotaUsage: res.quota });
        } catch {
          // 静默失败
        }
      },

      setStatus: (s) => set({ status: s }),
      setReconnectDeadline: (t) => set({ reconnectDeadline: t }),
      setError: (e) => set({ lastError: e }),
    }),
    {
      name: "dawei-sandbox",
      storage: createJSONStorage(() => localStorage),
      // 仅持久化用户选择的 Provider
      partialize: (state) => ({ selectedProvider: state.selectedProvider }),
    },
  ),
);

// ─── Selector Hooks (§14.4.3 — 避免大面积 rerender) ──────────────────────

export function useSandboxStatus(): SandboxStatus {
  return useSandboxStore((s) => s.status);
}

export function useSandboxQuota(): QuotaUsage | null {
  return useSandboxStore((s) => s.quotaUsage);
}

/** 返回剩余秒数, 内部 1s 递减 */
export function useReconnectCountdown(): number | null {
  return useSandboxStore((s) =>
    s.reconnectDeadline ? Math.max(0, Math.floor((s.reconnectDeadline - Date.now()) / 1000)) : null,
  );
}
