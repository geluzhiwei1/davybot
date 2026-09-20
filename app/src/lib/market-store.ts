/**
 * Market store — migrated from legalbot/webui/src/stores/market.ts
 * Zustand store for marketplace resources (skills, agents, plugins).
 * Fetches real data from backend API; no demo/mock data.
 */
import { create } from "zustand";
import { toast } from "sonner";
import { getApiBaseUrl } from "./env";

export type ResourceType = "skill" | "agent" | "plugin";

export interface MarketSearchResult {
  name: string;
  description: string;
  type: ResourceType;
  version?: string;
  author?: string;
  category?: string;
  tags?: string[];
  downloads?: number;
  rating?: number;
  icon?: string;
}

export interface InstalledResource {
  name: string;
  type: ResourceType;
  version?: string;
  enabled?: boolean;
  installedAt?: string;
  path?: string;
}

interface MarketState {
  searchResults: Record<ResourceType, MarketSearchResult[]>;
  installedResources: Record<ResourceType, InstalledResource[]>;
  currentQuery: Record<ResourceType, string>;
  loading: Record<ResourceType, boolean>;
  installing: Record<string, boolean>;
  error: Record<ResourceType, string | null>;
  featuredResources: Record<ResourceType, MarketSearchResult[]>;

  // Actions
  searchResources: (type: ResourceType, query: string, limit?: number) => void;
  installResource: (type: ResourceType, name: string, force?: boolean) => Promise<void>;
  uninstallResource: (type: ResourceType, name: string) => Promise<void>;
  loadFeaturedResources: (type: ResourceType) => void;
  loadInstalledResources: (type: ResourceType) => void;
  loadAllInstalledResources: () => void;
  clearError: (type: ResourceType) => void;
}

const emptyRecord: Record<ResourceType, MarketSearchResult[]> = {
  skill: [],
  agent: [],
  plugin: [],
};

const emptyInstalled: Record<ResourceType, InstalledResource[]> = {
  skill: [],
  agent: [],
  plugin: [],
};

export const useMarketStore = create<MarketState>((set, get) => ({
  searchResults: { ...emptyRecord },
  installedResources: { ...emptyInstalled },
  currentQuery: { skill: "", agent: "", plugin: "" },
  loading: { skill: false, agent: false, plugin: false },
  installing: {},
  error: { skill: null, agent: null, plugin: null },
  featuredResources: { ...emptyRecord },

  searchResources: async (type, query, _limit = 20) => {
    set((s) => ({
      loading: { ...s.loading, [type]: true },
      currentQuery: { ...s.currentQuery, [type]: query },
      error: { ...s.error, [type]: null },
    }));

    try {
      // Use skills/search for skill type, otherwise fallback
      if (type === "skill") {
        const res = await fetch(
          `${getApiBaseUrl()}/api/skills/search/${encodeURIComponent(query || "*")}`,
        );
        if (res.ok) {
          const data = await res.json();
          const results: MarketSearchResult[] = (data.skills ?? data.data ?? []).map(
            (s: Record<string, unknown>) => ({
              name: (s.name as string) || "",
              description: (s.description as string) || "",
              type: "skill" as ResourceType,
              version: s.version as string | undefined,
              author: s.author as string | undefined,
              category: s.category as string | undefined,
              tags: s.tags as string[] | undefined,
            }),
          );
          set((s) => ({
            searchResults: { ...s.searchResults, [type]: results },
            loading: { ...s.loading, [type]: false },
          }));
          return;
        }
      }
      // Fallback: show featured
      const featured = get().featuredResources[type];
      const results = query
        ? featured.filter(
            (r) =>
              r.name.toLowerCase().includes(query.toLowerCase()) ||
              r.description.toLowerCase().includes(query.toLowerCase()) ||
              r.tags?.some((t) => t.includes(query)),
          )
        : featured;
      set((s) => ({
        searchResults: { ...s.searchResults, [type]: results },
        loading: { ...s.loading, [type]: false },
      }));
    } catch {
      set((s) => ({
        loading: { ...s.loading, [type]: false },
        error: { ...s.error, [type]: "Failed to search resources" },
      }));
    }
  },

  installResource: async (type, name, _force = false) => {
    set((s) => ({ installing: { ...s.installing, [name]: true } }));
    try {
      const res = await fetch(`${getApiBaseUrl()}/api/skills/install`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, type }),
      });
      if (!res.ok) throw new Error("Install failed");
      set((s) => ({
        installedResources: {
          ...s.installedResources,
          [type]: [
            ...s.installedResources[type],
            { name, type, enabled: true, installedAt: new Date().toISOString() },
          ],
        },
        installing: { ...s.installing, [name]: false },
      }));
    } catch {
      set((s) => ({ installing: { ...s.installing, [name]: false } }));
      toast.error(`安装 ${name} 失败`);
    }
  },

  uninstallResource: async (type, name) => {
    set((s) => ({ installing: { ...s.installing, [name]: true } }));
    try {
      const res = await fetch(`${getApiBaseUrl()}/api/skills/uninstall`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, type }),
      });
      if (!res.ok) throw new Error("Uninstall failed");
      set((s) => ({
        installedResources: {
          ...s.installedResources,
          [type]: s.installedResources[type].filter((r) => r.name !== name),
        },
        installing: { ...s.installing, [name]: false },
      }));
    } catch {
      set((s) => ({ installing: { ...s.installing, [name]: false } }));
      toast.error(`卸载 ${name} 失败`);
    }
  },

  loadFeaturedResources: async (type) => {
    if (type !== "skill") {
      // Only skill featured resources are fetched from backend
      return;
    }
    try {
      const res = await fetch(`${getApiBaseUrl()}/api/skills/list`);
      if (res.ok) {
        const data = await res.json();
        const results: MarketSearchResult[] = (data.skills ?? data.data ?? []).map(
          (s: Record<string, unknown>) => ({
            name: (s.name as string) || "",
            description: (s.description as string) || "",
            type: "skill" as ResourceType,
            version: s.version as string | undefined,
            author: s.author as string | undefined,
            category: s.category as string | undefined,
            tags: s.tags as string[] | undefined,
          }),
        );
        set((s) => ({
          featuredResources: { ...s.featuredResources, [type]: results },
          searchResults: { ...s.searchResults, [type]: results },
        }));
      }
    } catch {
      // Backend not available — leave featured empty
      console.log("[MarketStore] Failed to load featured resources for", type);
    }
  },

  loadInstalledResources: (_type) => {
    // Installed resources are fetched from backend when available
    // Currently no dedicated installed endpoint; skip
  },

  loadAllInstalledResources: () => {
    // No dedicated installed endpoint yet
  },

  clearError: (type) => {
    set((s) => ({ error: { ...s.error, [type]: null } }));
  },
}));
