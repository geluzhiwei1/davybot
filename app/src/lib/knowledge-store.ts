/**
 * Knowledge Bases Zustand Store — manages backend knowledge_bases API state.
 */
import { toastError } from "./api/client.js";
import { toast } from "sonner";
import { create } from "zustand";
import {
  knowledgeBasesApi,
  type KnowledgeBaseItem,
  type KnowledgeBaseStats,
  type DocumentInfo,
  type SearchResult,
  type GraphEntity,
  type GraphRelation,
  type EntitySource,
  type SyncTaskStatus,
  type CreateKBRequest,
} from "@/lib/api-client";

interface KnowledgeState {
  /** KB list */
  bases: KnowledgeBaseItem[];
  basesLoading: boolean;
  error: string | null;

  /** Selected KB */
  selectedBaseId: string | null;
  selectedBase: KnowledgeBaseItem | null;

  /** Documents */
  documents: DocumentInfo[];
  documentsTotal: number;
  documentsLoading: boolean;
  documentsPage: number;

  /** Stats */
  stats: KnowledgeBaseStats | null;
  statsLoading: boolean;

  /** Search */
  searchResults: SearchResult[];
  searchLoading: boolean;
  searchStats: {
    vector_count: number;
    graph_count: number;
    fulltext_count: number;
    latency_ms: number;
  } | null;

  /** Graph */
  entities: GraphEntity[];
  relations: GraphRelation[];
  graphLoading: boolean;

  /** Entity provenance — sources for the selected graph entity */
  entitySources: EntitySource[] | null;
  entitySourcesLoading: boolean;

  /** Sync */
  syncTask: SyncTaskStatus | null;
  _pollInterval: ReturnType<typeof setInterval> | null;

  /** Workspace context (passed to MemoryBrowser via useWorkspaceStore) */
  selectedWorkspaceId: string | null;

  // ── Actions ──

  fetchBases: (workspaceId?: string) => Promise<void>;
  createBase: (data: CreateKBRequest) => Promise<KnowledgeBaseItem>;
  updateBase: (id: string, data: Record<string, unknown>) => Promise<void>;
  deleteBase: (id: string, force?: boolean) => Promise<void>;
  setDefaultBase: (id: string) => Promise<void>;
  selectBase: (id: string | null) => void;

  fetchDocuments: (baseId: string, skip?: number, limit?: number) => Promise<void>;
  fetchStats: (baseId: string) => Promise<void>;

  uploadDocument: (
    baseId: string,
    file: File,
  ) => Promise<{
    success: boolean;
    vectors_indexed: boolean;
    chunks_added: number;
    message: string;
  }>;
  deleteDocument: (baseId: string, docId: string) => Promise<void>;

  search: (baseId: string, query: string, mode?: string, topK?: number) => Promise<void>;
  clearSearch: () => void;

  fetchGraphData: (baseId: string) => Promise<void>;
  fetchEntitySources: (baseId: string, entityId: string) => Promise<void>;

  startSync: (baseId: string, dirPath?: string, forceRebuild?: boolean) => Promise<string>;
  pollSyncStatus: (baseId: string) => void;
  stopPollingSync: () => void;
  cancelSync: (baseId: string) => Promise<void>;

  reindexAll: (baseId: string) => Promise<void>;
  reindexDocument: (baseId: string, docId: string) => Promise<void>;

  setSelectedWorkspace: (id: string | null) => void;
  clearError: () => void;
}

export const useKnowledgeStore = create<KnowledgeState>((set, get) => ({
  bases: [],
  basesLoading: false,
  error: null,

  selectedBaseId: null,
  selectedBase: null,

  documents: [],
  documentsTotal: 0,
  documentsLoading: false,
  documentsPage: 0,

  stats: null,
  statsLoading: false,

  searchResults: [],
  searchLoading: false,
  searchStats: null,

  entities: [],
  relations: [],
  graphLoading: false,

  entitySources: null,
  entitySourcesLoading: false,

  syncTask: null,
  _pollInterval: null,

  selectedWorkspaceId: null,

  // ── Fetch bases ──
  fetchBases: async (workspaceId) => {
    set({ basesLoading: true, error: null });
    try {
      const res = await knowledgeBasesApi.list({ workspace_id: workspaceId });
      set({ bases: res.items, basesLoading: false });
      // Auto-select first base if none selected
      const { selectedBaseId } = get();
      if (!selectedBaseId && res.items.length > 0) {
        set({ selectedBaseId: res.items[0].id, selectedBase: res.items[0] });
      } else if (selectedBaseId) {
        // Refresh selected base data
        const selected = res.items.find((b) => b.id === selectedBaseId);
        if (selected) set({ selectedBase: selected });
      }
    } catch (e: unknown) {
      set({ error: e instanceof Error ? e.message : "加载知识库列表失败", basesLoading: false });
    }
  },

  // ── Create ──
  createBase: async (data) => {
    const base = await knowledgeBasesApi.create(data);
    await get().fetchBases(get().selectedWorkspaceId ?? undefined);
    return base;
  },

  // ── Update ──
  updateBase: async (id, data) => {
    await knowledgeBasesApi.update(id, data);
    await get().fetchBases(get().selectedWorkspaceId ?? undefined);
  },

  // ── Delete ──
  deleteBase: async (id, force) => {
    await knowledgeBasesApi.delete(id, force);
    set((s) => ({
      selectedBaseId: s.selectedBaseId === id ? null : s.selectedBaseId,
      selectedBase: s.selectedBaseId === id ? null : s.selectedBase,
      stats: s.selectedBaseId === id ? null : s.stats,
    }));
    await get().fetchBases(get().selectedWorkspaceId ?? undefined);
  },

  // ── Set default ──
  setDefaultBase: async (id) => {
    await knowledgeBasesApi.setDefault(id);
    await get().fetchBases(get().selectedWorkspaceId ?? undefined);
  },

  // ── Select base ──
  selectBase: (id) => {
    const base = id ? (get().bases.find((b) => b.id === id) ?? null) : null;
    set({
      selectedBaseId: id,
      selectedBase: base,
      documents: [],
      documentsTotal: 0,
      stats: null,
      searchResults: [],
      searchStats: null,
      entities: [],
      relations: [],
      entitySources: null,
      syncTask: null,
    });
    // Fetch stats when selecting
    if (id) {
      get().fetchStats(id);
    }
  },

  // ── Documents ──
  fetchDocuments: async (baseId, skip = 0, limit = 10) => {
    set({ documentsLoading: true });
    try {
      const res = await knowledgeBasesApi.listDocuments(baseId, skip, limit);
      set({
        documents: res.documents,
        documentsTotal: res.total,
        documentsPage: skip,
        documentsLoading: false,
      });
    } catch (e) {
      set({ documentsLoading: false });
      toastError("加载文档列表失败", e);
    }
  },

  // ── Stats ──
  fetchStats: async (baseId) => {
    set({ statsLoading: true });
    try {
      const stats = await knowledgeBasesApi.getStats(baseId);
      set({ stats, statsLoading: false });
    } catch (e) {
      set({ statsLoading: false });
      toastError("加载统计信息失败", e);
    }
  },

  // ── Upload document ──
  uploadDocument: async (baseId, file) => {
    const res = await knowledgeBasesApi.uploadDocument(baseId, file);
    await get().fetchDocuments(baseId);
    await get().fetchStats(baseId);
    await get().fetchBases(get().selectedWorkspaceId ?? undefined);
    return res;
  },

  // ── Delete document ──
  deleteDocument: async (baseId, docId) => {
    await knowledgeBasesApi.deleteDocument(baseId, docId);
    await get().fetchDocuments(baseId);
    await get().fetchStats(baseId);
  },

  // ── Search ──
  search: async (baseId, query, mode = "hybrid", topK = 5) => {
    set({ searchLoading: true });
    try {
      const res = await knowledgeBasesApi.search(baseId, query, mode, topK);
      set({
        searchResults: res.results,
        searchStats: {
          vector_count: res.vector_count,
          graph_count: res.graph_count,
          fulltext_count: res.fulltext_count,
          latency_ms: res.latency_ms,
        },
        searchLoading: false,
      });
    } catch (e) {
      set({ searchLoading: false });
      toastError("搜索失败", e);
    }
  },

  clearSearch: () => {
    set({ searchResults: [], searchStats: null });
  },

  // ── Graph ──
  fetchGraphData: async (baseId) => {
    set({ graphLoading: true });
    try {
      const [entitiesRes, relationsRes] = await Promise.all([
        knowledgeBasesApi.getGraphEntities(baseId, { limit: 500 }),
        knowledgeBasesApi.getGraphRelations(baseId, { limit: 1000 }),
      ]);
      set({
        entities: entitiesRes.entities,
        relations: relationsRes.relations,
        graphLoading: false,
      });
    } catch (e) {
      set({ graphLoading: false });
      toastError("加载知识图谱失败", e);
    }
  },

  fetchEntitySources: async (baseId, entityId) => {
    set({ entitySourcesLoading: true });
    try {
      const res = await knowledgeBasesApi.getEntitySources(baseId, entityId);
      set({ entitySources: res.sources, entitySourcesLoading: false });
    } catch {
      set({ entitySources: [], entitySourcesLoading: false });
    }
  },

  // ── Sync ──
  startSync: async (baseId, dirPath, forceRebuild) => {
    const res = await knowledgeBasesApi.syncFromDir(baseId, {
      dir_path: dirPath,
      force_rebuild: forceRebuild,
    });
    return res.task_id;
  },

  pollSyncStatus: (baseId) => {
    get().stopPollingSync();
    const id = setInterval(async () => {
      try {
        const status = await knowledgeBasesApi.getSyncStatus(baseId);
        set({ syncTask: status });
        if (status.status === "completed" || status.status === "failed") {
          get().stopPollingSync();
          // Refresh docs and stats after sync completes
          await get().fetchDocuments(baseId);
          await get().fetchStats(baseId);
          await get().fetchBases(get().selectedWorkspaceId ?? undefined);

          // Surface errors to the user
          const errors = status.result?.errors;
          if (status.status === "failed") {
            const detail = status.error || (errors && errors.length > 0 ? errors[0] : "未知错误");
            toast.error("同步失败", {
              description: detail,
              duration: 10000,
              action:
                errors && errors.length > 1
                  ? {
                      label: "复制详情",
                      onClick: () => navigator.clipboard.writeText(errors.join("\n")),
                    }
                  : undefined,
            });
          } else if (errors && errors.length > 0) {
            toast.warning(`同步完成，但 ${errors.length} 个文件失败`, {
              description: errors[0],
              duration: 10000,
              action:
                errors.length > 1
                  ? {
                      label: "复制详情",
                      onClick: () => navigator.clipboard.writeText(errors.join("\n")),
                    }
                  : undefined,
            });
          } else {
            toast.success("同步完成");
          }
        }
      } catch {
        // Silently ignore polling errors
      }
    }, 2000);
    set({ _pollInterval: id });
  },

  stopPollingSync: () => {
    const { _pollInterval } = get();
    if (_pollInterval) {
      clearInterval(_pollInterval);
      set({ _pollInterval: null });
    }
  },

  cancelSync: async (baseId) => {
    await knowledgeBasesApi.cancelSync(baseId);
    get().stopPollingSync();
    set({ syncTask: null });
  },

  // ── Reindex ──
  reindexAll: async (baseId) => {
    await knowledgeBasesApi.reindexAll(baseId);
    await get().fetchStats(baseId);
    await get().fetchBases(get().selectedWorkspaceId ?? undefined);
  },

  reindexDocument: async (baseId, docId) => {
    try {
      await knowledgeBasesApi.reindexDocument(baseId, docId);
      await get().fetchDocuments(baseId);
      await get().fetchStats(baseId);
      await get().fetchBases(get().selectedWorkspaceId ?? undefined);
    } catch (e) {
      toastError("重新索引失败", e);
    }
  },

  // ── Workspace ──
  setSelectedWorkspace: (id) => {
    set({ selectedWorkspaceId: id });
  },

  clearError: () => set({ error: null }),
}));
