/**
 * Plugin store — migrated from legalbot/webui/src/stores/plugins.ts
 * Zustand store for managing plugin state.
 */
import { create } from "zustand";
import type { PluginInfo, PluginSettings } from "./types/plugins";

interface PluginStatistics {
  total: number;
  enabled: number;
  activated: number;
  byType: Record<string, number>;
}

interface PluginStoreState {
  plugins: PluginInfo[];
  currentPlugin: PluginInfo | null;
  currentPluginSettings: PluginSettings | null;
  statistics: PluginStatistics | null;
  loading: boolean;
  error: string | null;

  // Computed-like getters
  getEnabledPlugins: () => PluginInfo[];
  getActivatedPlugins: () => PluginInfo[];
  getPluginsByType: () => Record<string, PluginInfo[]>;

  // Actions
  setPlugins: (plugins: PluginInfo[]) => void;
  setCurrentPlugin: (plugin: PluginInfo | null) => void;
  setCurrentPluginSettings: (settings: PluginSettings | null) => void;
  updatePluginInList: (pluginId: string, updates: Partial<PluginInfo>) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  clearCurrentPlugin: () => void;
  clearError: () => void;
}

export const usePluginStore = create<PluginStoreState>((set, get) => ({
  plugins: [],
  currentPlugin: null,
  currentPluginSettings: null,
  statistics: null,
  loading: false,
  error: null,

  getEnabledPlugins: () => get().plugins.filter((p) => p.enabled),
  getActivatedPlugins: () => get().plugins.filter((p) => p.activated),
  getPluginsByType: () => {
    const grouped: Record<string, PluginInfo[]> = {};
    for (const plugin of get().plugins) {
      if (!grouped[plugin.type]) grouped[plugin.type] = [];
      grouped[plugin.type].push(plugin);
    }
    return grouped;
  },

  setPlugins: (plugins) => {
    const enabled = plugins.filter((p) => p.enabled).length;
    const activated = plugins.filter((p) => p.activated).length;
    const byType: Record<string, number> = {};
    for (const p of plugins) {
      byType[p.type] = (byType[p.type] || 0) + 1;
    }
    set({
      plugins,
      statistics: { total: plugins.length, enabled, activated, byType },
    });
  },

  setCurrentPlugin: (plugin) => set({ currentPlugin: plugin }),
  setCurrentPluginSettings: (settings) => set({ currentPluginSettings: settings }),

  updatePluginInList: (pluginId, updates) => {
    set((s) => ({
      plugins: s.plugins.map((p) => (p.id === pluginId ? { ...p, ...updates } : p)),
    }));
  },

  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error }),
  clearCurrentPlugin: () => set({ currentPlugin: null, currentPluginSettings: null }),
  clearError: () => set({ error: null }),
}));
