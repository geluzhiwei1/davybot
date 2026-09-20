/**
 * Knowledge Base API — local KB CRUD, documents, search, graph, sync.
 */
import { request, requestMultipart } from "./client";

// ── Legacy Knowledge Types (used by knowledgeApi) ──────────────────

export interface KnowledgeBase {
  id: string;
  name: string;
  description: string;
  status: string;
  is_default: boolean;
  stats: {
    total_documents: number;
    total_chunks: number;
    total_entities: number;
  };
  settings: {
    domain: string;
  };
}

export interface KnowledgeDomain {
  name: string;
  display_name: string;
}

export const knowledgeApi = {
  listBases: () => request<{ total: number; items: KnowledgeBase[] }>("/api/knowledge/bases"),

  listDomains: () =>
    request<{ domains: KnowledgeDomain[]; total: number }>("/api/knowledge/domains"),

  getDefault: () => request<KnowledgeBase>("/api/knowledge/bases/default"),
};

// ── Extended Knowledge Base Types ──────────────────────────────────

export type KnowledgeBaseStatus = "active" | "archived" | "deleting";

export interface KnowledgeBaseSettings {
  watch_dir: string;
  watch_enabled: boolean;
  watch_recursive: boolean;
  watch_extensions: string[];
  chunk_size: number;
  chunk_overlap: number;
  chunk_strategy: string;
  embedding_model: string;
  embedding_dimension: number;
  default_top_k: number;
  default_mode: string;
  vector_weight: number;
  graph_weight: number;
  fulltext_weight: number;
  extraction_strategy: string;
  extraction_llm_config: string;
  domain?: string;
  domain_config: Record<string, unknown>;
  enable_graph: boolean;
  enable_fulltext: boolean;
  enable_vector: boolean;
  auto_reindex: boolean;
}

export interface KnowledgeBaseStats {
  total_documents: number;
  total_chunks: number;
  total_entities: number;
  total_relations: number;
  indexed_documents: number;
  vectors_pending: number;
  storage_size_bytes: number;
  last_indexed_at: string | null;
  last_updated_at: string;
}

export interface KnowledgeBaseItem {
  id: string;
  name: string;
  description: string;
  status: KnowledgeBaseStatus;
  settings: KnowledgeBaseSettings;
  stats: KnowledgeBaseStats;
  created_at: string;
  updated_at: string;
  created_by: string;
  workspace_id: string | null;
  tags: string[];
  is_default: boolean;
  storage_path: string;
}

export interface KnowledgeBaseListResponse {
  total: number;
  items: KnowledgeBaseItem[];
  default_base_id: string | null;
}

export interface ScanFileInfo {
  name: string;
  path: string;
  size: number;
  extension: string;
  exists_in_kb?: boolean;
}

export interface DocumentInfo {
  id: string;
  file_name: string;
  file_size: number;
  uploaded_at: number;
  file_path: string;
}

export interface GraphEntity {
  id: string;
  type: string;
  name: string;
  description?: string;
  properties: Record<string, unknown>;
  base_id: string;
  created_at: string;
}

export interface GraphRelation {
  id: string;
  from_entity: string;
  to_entity: string;
  relation_type: string;
  properties: Record<string, unknown>;
  weight: number;
  base_id: string;
  created_at: string;
}

export interface EntitySource {
  document_title: string;
  page_number?: number;
  chunk_index?: number;
  content?: string;
}

export interface SearchResult {
  id: string;
  content: string;
  score: number;
  source: "vector" | "graph" | "fulltext" | "hybrid";
  metadata: Record<string, unknown>;
}

export interface SyncTaskResult {
  success: boolean;
  base_id: string;
  message: string;
  stats: {
    total_documents: number;
    total_chunks: number;
    total_entities: number;
    total_relations: number;
  };
  skipped: number;
  errors: string[] | null;
}

export interface SyncTaskStatus {
  task_id: string;
  base_id: string;
  status: "pending" | "running" | "completed" | "failed";
  progress: number;
  current_file: string;
  total_files: number;
  processed_files: number;
  result?: SyncTaskResult;
  error?: string;
  force_rebuild: boolean;
}

export interface DomainInfo {
  domain: string;
  description: string;
  entity_types: Record<
    string,
    {
      description: string;
      properties: Record<string, { type: string; description: string; required: boolean }>;
    }
  >;
  relation_types: Record<
    string,
    {
      description: string;
      from_type: string;
      to_type: string;
      properties?: Record<string, { type: string; description: string; required: boolean }>;
    }
  >;
}

export interface CreateKBRequest {
  name: string;
  description?: string;
  settings?: Partial<KnowledgeBaseSettings>;
  workspace_id?: string;
  tags?: string[];
  is_default?: boolean;
}

// ── Extended Knowledge Bases API ───────────────────────────────────

export const knowledgeBasesApi = {
  // ── Base CRUD ──
  list: (params?: { workspace_id?: string; status?: KnowledgeBaseStatus }) => {
    const qs = new URLSearchParams();
    if (params?.workspace_id) qs.set("workspace_id", params.workspace_id);
    if (params?.status) qs.set("status", params.status);
    const query = qs.toString();
    return request<KnowledgeBaseListResponse>(`/api/knowledge/bases${query ? "?" + query : ""}`);
  },

  create: (data: CreateKBRequest) =>
    request<KnowledgeBaseItem>("/api/knowledge/bases", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  getDefault: () => request<KnowledgeBaseItem>("/api/knowledge/bases/default"),

  getById: (baseId: string) => request<KnowledgeBaseItem>(`/api/knowledge/bases/by-id/${baseId}`),

  update: (
    baseId: string,
    data: Partial<
      KnowledgeBaseSettings & {
        name?: string;
        description?: string;
        tags?: string[];
        status?: KnowledgeBaseStatus;
      }
    >,
  ) =>
    request<KnowledgeBaseItem>(`/api/knowledge/bases/by-id/${baseId}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  delete: (baseId: string, force?: boolean) =>
    request<void>(`/api/knowledge/bases/by-id/${baseId}${force ? "?force=true" : ""}`, {
      method: "DELETE",
    }),

  setDefault: (baseId: string) =>
    request<KnowledgeBaseItem>(`/api/knowledge/bases/by-id/${baseId}/set-default`, {
      method: "POST",
    }),

  getStats: (baseId: string) =>
    request<KnowledgeBaseStats>(`/api/knowledge/bases/by-id/${baseId}/stats`),

  // ── Directory ──
  /** Scan KB watch directory */
  scanDir: (baseId: string, dirPath?: string) =>
    request<{
      files: ScanFileInfo[];
      total: number;
      dir_path: string;
      existing_count: number;
      new_count: number;
    }>(
      `/api/knowledge/bases/by-id/${baseId}/scan-dir${dirPath ? `?dir_path=${encodeURIComponent(dirPath)}` : ""}`,
    ),

  /** Scan arbitrary directory (no KB needed) */
  scanDirGlobal: (dirPath?: string) =>
    request<{
      files: ScanFileInfo[];
      total: number;
      dir_path: string;
      existing_count: number;
      new_count: number;
    }>(`/api/knowledge/bases/scan-dir${dirPath ? `?dir_path=${encodeURIComponent(dirPath)}` : ""}`),

  // ── Document Management ──
  listDocuments: (baseId: string, skip = 0, limit = 10) =>
    request<{ documents: DocumentInfo[]; total: number; skip: number; limit: number }>(
      `/api/knowledge/bases/by-id/${baseId}/documents?skip=${skip}&limit=${limit}`,
    ),

  /** Upload document — uses requestMultipart to bypass Content-Type: application/json */
  uploadDocument: (baseId: string, file: File) =>
    requestMultipart<{
      success: boolean;
      document_id: string;
      chunks_added: number;
      vectors_indexed: boolean;
      message: string;
    }>(`/api/knowledge/bases/by-id/${baseId}/documents/upload`, "file", file),

  getDocument: (baseId: string, docId: string) =>
    request<{
      id: string;
      base_id: string;
      content: string;
      file_name: string;
      chunk_count: number;
      metadata: Record<string, unknown>;
    }>(`/api/knowledge/bases/by-id/${baseId}/documents/${docId}`),

  deleteDocument: (baseId: string, docId: string) =>
    request<void>(`/api/knowledge/bases/by-id/${baseId}/documents/${docId}`, { method: "DELETE" }),

  // ── Directory Sync ──
  syncFromDir: (baseId: string, params?: { dir_path?: string; force_rebuild?: boolean }) => {
    const qs = new URLSearchParams();
    if (params?.dir_path) qs.set("dir_path", params.dir_path);
    if (params?.force_rebuild) qs.set("force_rebuild", "true");
    return request<{ task_id: string; base_id: string; status: string; message: string }>(
      `/api/knowledge/bases/by-id/${baseId}/sync-from-dir?${qs}`,
      { method: "POST" },
    );
  },

  getSyncStatus: (baseId: string) =>
    request<SyncTaskStatus>(`/api/knowledge/bases/by-id/${baseId}/sync-status`),

  cancelSync: (baseId: string) =>
    request<SyncTaskStatus>(`/api/knowledge/bases/by-id/${baseId}/sync-cancel`, { method: "POST" }),

  autoSync: (baseId: string) =>
    request<{ success: boolean; base_id: string; message: string }>(
      `/api/knowledge/bases/by-id/${baseId}/auto-sync`,
      { method: "POST" },
    ),

  // ── Reindex ──
  /** Full reindex — may take >30s, uses timeoutMs: 120_000 */
  reindexAll: (baseId: string) =>
    request<{
      success: boolean;
      base_id: string;
      message: string;
      stats: Partial<KnowledgeBaseStats>;
      errors?: string[];
    }>(`/api/knowledge/bases/by-id/${baseId}/reindex`, { method: "POST", timeoutMs: 120_000 }),

  /** Single-doc reindex (backend TODO — falls back to full reindex). Uses timeoutMs. */
  reindexDocument: (baseId: string, docId: string) =>
    request<{ success: boolean }>(
      `/api/knowledge/bases/by-id/${baseId}/documents/${docId}/reindex`,
      { method: "POST", timeoutMs: 120_000 },
    ),

  // ── Search ──
  search: (baseId: string, query: string, mode = "hybrid", topK = 5) =>
    request<{
      success: boolean;
      query: string;
      mode: string;
      top_k: number;
      results: SearchResult[];
      total_count: number;
      vector_count: number;
      graph_count: number;
      fulltext_count: number;
      latency_ms: number;
    }>(
      `/api/knowledge/bases/by-id/${baseId}/search?query=${encodeURIComponent(query)}&mode=${mode}&top_k=${topK}`,
      { method: "POST" },
    ),

  // ── Graph ──
  getGraphEntities: (
    baseId: string,
    params?: { limit?: number; offset?: number; entity_type?: string },
  ) => {
    const qs = new URLSearchParams();
    if (params?.limit) qs.set("limit", String(params.limit));
    if (params?.offset) qs.set("offset", String(params.offset));
    if (params?.entity_type) qs.set("entity_type", params.entity_type);
    return request<{ success: boolean; entities: GraphEntity[]; total: number }>(
      `/api/knowledge/bases/by-id/${baseId}/graph/entities?${qs}`,
    );
  },

  getGraphRelations: (
    baseId: string,
    params?: { limit?: number; offset?: number; relation_type?: string },
  ) => {
    const qs = new URLSearchParams();
    if (params?.limit) qs.set("limit", String(params.limit));
    if (params?.offset) qs.set("offset", String(params.offset));
    if (params?.relation_type) qs.set("relation_type", params.relation_type);
    return request<{ success: boolean; relations: GraphRelation[]; total: number }>(
      `/api/knowledge/bases/by-id/${baseId}/graph/relations?${qs}`,
    );
  },

  getEntitySources: (baseId: string, entityId: string) =>
    request<{
      entity: GraphEntity;
      sources: EntitySource[];
      source_documents: string[];
      source_pages: number[];
    }>(`/api/knowledge/bases/by-id/${baseId}/graph/entities/${entityId}/sources`),

  // ── LLM Configs ──
  listLLMConfigs: () =>
    request<{ success: boolean; configs: { llm_id: string; model_id: string }[] }>(
      "/api/knowledge/bases/llm-configs",
    ),

  // ── Domains ──
  listDomains: () => request<{ domains: DomainInfo[]; total: number }>("/api/knowledge/domains"),
};
