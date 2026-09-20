/**
 * Global market teams cache — fetches team hierarchy from nn-user-system.
 * Used by floating-input, workspace-panel, experts routes, agents drawer, etc.
 */
import { create } from "zustand";
import { marketApi, type TeamHierarchyEntry } from "@/lib/market-api";

interface MarketTeamsState {
  teams: TeamHierarchyEntry[];
  loading: boolean;
  loaded: boolean;
  error: string | null;
  fetchTeams: () => Promise<void>;
}

export const useMarketTeamsStore = create<MarketTeamsState>((set, get) => ({
  teams: [],
  loading: false,
  loaded: false,
  error: null,
  fetchTeams: async () => {
    if (get().loaded || get().loading) return;
    set({ loading: true, error: null });
    try {
      const res = await marketApi.getTeamHierarchy();
      // Response is TeamHierarchyResponse with { teams: TeamHierarchyEntry[] }
      const rawTeams = res.teams ?? [];
      // Teams may be nested with subteams; flatten recursively
      const flat: TeamHierarchyEntry[] = [];
      const walk = (entries: TeamHierarchyEntry[]) => {
        for (const e of entries) {
          flat.push(e);
          if (e.subteams?.length) walk(e.subteams);
        }
      };
      walk(rawTeams);
      set({ teams: flat, loading: false, loaded: true });
    } catch (e) {
      set({ error: String(e), loading: false });
    }
  },
}));
