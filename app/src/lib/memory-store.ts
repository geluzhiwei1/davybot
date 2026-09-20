/**
 * Memory Zustand store.
 */
import { create } from "zustand";
import type {
  MemoryEntry,
  MemoryFilters,
  MemoryStats,
  GraphData,
  TimelineEntry,
} from "@/lib/types/memory";
import { MemoryType } from "@/lib/types/memory";

interface MemoryState {
  memories: MemoryEntry[];
  selectedId: string | null;
  loading: boolean;
  error: string | null;
  viewMode: "graph" | "list" | "timeline";
  searchQuery: string;
  filters: MemoryFilters;
  stats: MemoryStats | null;
  graphData: GraphData;
  timelineData: TimelineEntry[];
  showForm: boolean;
  editingMemory: MemoryEntry | null;
  scope: "user" | "workspace";
}

interface MemoryActions {
  setMemories: (memories: MemoryEntry[]) => void;
  addMemory: (memory: MemoryEntry) => void;
  updateMemory: (id: string, updates: Partial<MemoryEntry>) => void;
  removeMemory: (id: string) => void;
  setSelectedId: (id: string | null) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  setViewMode: (mode: "graph" | "list" | "timeline") => void;
  setSearchQuery: (query: string) => void;
  setFilters: (filters: Partial<MemoryFilters>) => void;
  resetFilters: () => void;
  setStats: (stats: MemoryStats | null) => void;
  setGraphData: (data: GraphData) => void;
  setTimelineData: (data: TimelineEntry[]) => void;
  setShowForm: (show: boolean) => void;
  setEditingMemory: (memory: MemoryEntry | null) => void;
  setScope: (scope: "user" | "workspace") => void;
  getFilteredMemories: () => MemoryEntry[];
  getMemoriesByType: () => Partial<Record<MemoryType, MemoryEntry[]>>;
  getSelectedMemory: () => MemoryEntry | undefined;
}

const defaultFilters: MemoryFilters = {
  type: "all",
  minConfidence: 0,
  minEnergy: 0,
  onlyValid: false,
};

export const useMemoryStore = create<MemoryState & MemoryActions>((set, get) => ({
  memories: [],
  selectedId: null,
  loading: false,
  error: null,
  viewMode: "list",
  searchQuery: "",
  filters: { ...defaultFilters },
  stats: null,
  graphData: { nodes: [], links: [] },
  timelineData: [],
  showForm: false,
  editingMemory: null,
  scope: "workspace",

  setMemories: (memories) => set({ memories }),
  addMemory: (memory) => set((s) => ({ memories: [...s.memories, memory] })),
  updateMemory: (id, updates) =>
    set((s) => ({
      memories: s.memories.map((m) => (m.id === id ? { ...m, ...updates } : m)),
    })),
  removeMemory: (id) => set((s) => ({ memories: s.memories.filter((m) => m.id !== id) })),
  setSelectedId: (id) => set({ selectedId: id }),
  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error }),
  setViewMode: (viewMode) => set({ viewMode }),
  setSearchQuery: (searchQuery) => set({ searchQuery }),
  setFilters: (filters) => set((s) => ({ filters: { ...s.filters, ...filters } })),
  resetFilters: () => set({ filters: { ...defaultFilters } }),
  setStats: (stats) => set({ stats }),
  setGraphData: (graphData) => set({ graphData }),
  setTimelineData: (timelineData) => set({ timelineData }),
  setShowForm: (showForm) => set({ showForm }),
  setEditingMemory: (editingMemory) => set({ editingMemory }),
  setScope: (scope) => set({ scope }),

  getFilteredMemories: () => {
    const { memories, searchQuery, filters } = get();
    let result = [...memories];

    if (filters.type && filters.type !== "all") {
      result = result.filter((m) => m.memoryType === filters.type);
    }
    if (filters.minConfidence) {
      result = result.filter((m) => m.confidence >= (filters.minConfidence ?? 0));
    }
    if (filters.minEnergy) {
      result = result.filter((m) => m.energy >= (filters.minEnergy ?? 0));
    }
    if (filters.onlyValid) {
      const now = new Date().toISOString();
      result = result.filter((m) => !m.validEnd || m.validEnd > now);
    }
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      result = result.filter(
        (m) =>
          m.subject.toLowerCase().includes(q) ||
          m.predicate.toLowerCase().includes(q) ||
          m.object.toLowerCase().includes(q) ||
          m.keywords.some((k) => k.toLowerCase().includes(q)),
      );
    }
    return result;
  },

  getMemoriesByType: () => {
    const memories = get().memories;
    const grouped: Partial<Record<MemoryType, MemoryEntry[]>> = {};
    for (const m of memories) {
      if (!grouped[m.memoryType]) grouped[m.memoryType] = [];
      grouped[m.memoryType]!.push(m);
    }
    return grouped;
  },

  getSelectedMemory: () => {
    const { memories, selectedId } = get();
    return memories.find((m) => m.id === selectedId);
  },
}));
