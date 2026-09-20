/**
 * nn-kb-searcher Legal API — direct client to nn-kb-searcher legal-ext service (:8014).
 * Covers legal document search, RAG Q&A, chat, knowledge graph, analytics,
 * enterprise compliance, expert knowledge, concepts, and knowledge base management.
 *
 * Aligned with OpenAPI spec at /api/v1/legal/openapi.json (97 endpoints).
 */
import { createHttpClient } from "./http-client";
import { UNISEARCHER_API_URL } from "@/lib/env";

// ─── Types ─────────────────────────────────────────────────────────────

export interface LegalDocument {
  id?: string;
  chunk_id?: string;
  document_id?: string;
  content?: string;
  title?: string;
  name?: string;
  doc_type?: DocType;
  sub_type?: string;
  jurisdiction?: string;
  status?: DocumentStatus;
  score?: number;
  fused_score?: number;
  relevance?: number;
  legal_domain?: string | string[];
  promulgation_date?: string;
  effective_date?: string;
  expiry_date?: string;
  issuing_authority?: string;
  authority?: string;
  source_url?: string;
  source?: string;
  kb_id?: string;
  doc_number?: string;
  title_en?: string;
  short_title?: string;
  amendment_chain?: Array<Record<string, unknown>>;
  industry?: string[];
  tags?: Array<Record<string, unknown>>;
  replaced_by?: string;
}

export interface LegalSearchResult {
  results: LegalDocument[];
  total: number;
  query?: string;
  mode?: string;
  intent?: string;
}

/** Paginated document list — matches GET /api/v1/legal/documents response. */
export interface DocumentListResult {
  items: LegalDocument[];
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
}

export interface FacetResult {
  facets: Record<string, Record<string, number>>;
  query?: string;
}

export interface DocumentDetail {
  title: string;
  name?: string;
  doc_type: string;
  id: string;
  document_id?: string;
  jurisdiction?: string;
  status?: string;
  promulgation_date?: string;
  effective_date?: string;
  expiry_date?: string;
  issuing_authority?: string;
  authority?: string;
  legal_domain?: string | string[];
  source_url?: string;
  doc_number?: string;
  title_en?: string;
  short_title?: string;
  amendment_chain?: Array<Record<string, unknown>>;
  industry?: string[];
  tags?: Array<Record<string, unknown>>;
  replaced_by?: string;
  versions?: Array<{ date: string; description: string }>;
  amendments?: Array<{ date: string; description: string }>;
  cited_by?: Array<{ title: string; name?: string; id?: string; document_id?: string }>;
  similar?: Array<{ title: string; name?: string; id?: string; score?: number }>;
}

export interface DocumentChunk {
  id: string;
  content: string;
  chunk_index?: number;
  page_number?: number;
  metadata?: Record<string, unknown>;
}

export interface DocumentVersion {
  version_id: string;
  date: string;
  description?: string;
  status?: string;
}

export interface DocumentDiff {
  from_version: string;
  to_version: string;
  changes: Array<{ type: string; content: string }>;
}

export interface DocumentTimeline {
  events: Array<{ date: string; event: string; description?: string }>;
}

export interface LegalQAResult {
  answer: string;
  response?: string;
  citations: Array<{
    title: string;
    name?: string;
    id: string;
    document_id?: string;
    relevance?: number;
    score?: number;
  }>;
  sources?: Array<{
    title: string;
    name?: string;
    id: string;
    document_id?: string;
    relevance?: number;
    score?: number;
  }>;
}

export interface LegalChatResult {
  answer: string;
  response?: string;
  conversation_id: string;
  question?: string;
  sources: Array<{
    chunk_id?: string;
    document_id?: string;
    citation_number?: number;
    title: string;
    content?: string;
    score?: number;
    source?: string;
    doc_type?: string;
    sub_type?: string;
    status?: string;
    jurisdiction?: string;
    legal_domain?: string[];
    kb_id?: string;
  }>;
  citations: Array<{
    number?: number;
    law_name?: string;
    article_number?: string;
    chunk_id?: string;
    content_snippet?: string;
    verified?: boolean;
  }>;
  follow_ups: string[];
  mentioned_laws: string[];
  elapsed_ms: number;
}

export interface GraphEntity {
  id: string;
  entity_id?: string;
  name: string;
  caption?: string;
  entity_type: string;
  type?: string;
  properties?: Record<string, unknown>;
}

export interface GraphNeighbor {
  entity: GraphEntity;
  relation?: { type: string; properties?: Record<string, unknown> };
}

export interface GraphSearchResponse {
  entities: GraphEntity[];
  data?: GraphEntity[];
}

export interface GraphSubgraph {
  entities: GraphEntity[];
  relations: Array<{
    source: string;
    target: string;
    type: string;
    properties?: Record<string, unknown>;
  }>;
}

export interface GraphPath {
  path: Array<{ entity: GraphEntity; relation?: { type: string } }>;
  length: number;
}

export interface GraphCommunity {
  id: string;
  name?: string;
  entities: string[];
  size: number;
}

export interface GraphInfluential {
  entities: Array<GraphEntity & { influence_score: number }>;
}

export interface GraphStats {
  node_count: number;
  edge_count: number;
  entity_type_counts: Record<string, number>;
  relation_type_counts: Record<string, number>;
}

export interface LegalKnowledgeBase {
  id: string;
  name: string;
  description?: string;
  status?: string;
  config?: Record<string, unknown>;
  document_count?: number;
  stats?: { documents: number };
  legal_domains?: string[];
}

export interface KnowledgeBaseListResult {
  knowledge_bases: LegalKnowledgeBase[];
  data?: LegalKnowledgeBase[];
}

export interface KBDiscoveryResult {
  knowledge_bases: Array<{
    kb_id: string;
    name: string;
    description?: string;
    doc_types: string[];
    jurisdictions: string[];
    document_count: number;
  }>;
}

export interface LegalSystemStats {
  documents?: Record<string, number>;
  entities?: Record<string, number>;
  domains?: Record<string, number>;
  [key: string]: unknown;
}

export interface EnterpriseComplianceProfile {
  name: string;
  violations: Array<{ type: string; date: string; penalty: string; authority: string }>;
  risk_score?: number;
  related_docs?: LegalDocument[];
}

export interface ViolationStats {
  total: number;
  by_type: Record<string, number>;
  by_industry: Record<string, number>;
  by_authority: Record<string, number>;
  trend: Array<{ period: string; count: number }>;
}

export interface ExpertKnowledgeStats {
  total_documents: number;
  by_sub_type: Record<string, number>;
  by_legal_domain: Record<string, number>;
  avg_quality_score: number;
}

export interface Concept {
  id: string;
  name: string;
  description?: string;
  jurisdiction?: string;
  legal_domain?: string[];
  properties?: Record<string, unknown>;
}

export interface ConceptComparison {
  concept_a: Concept;
  concept_b: Concept;
  similarities: string[];
  differences: string[];
  related_docs?: LegalDocument[];
}

export interface TrendPoint {
  period: string;
  count: number;
  doc_types?: Record<string, number>;
}

export interface HeatmapCell {
  jurisdiction: string;
  count: number;
  doc_types?: Record<string, number>;
}

export interface LoginResult {
  access_token: string;
  token_type: string;
}

/** DocType enum matching backend OpenAPI spec. */
export type DocType =
  | "NORMATIVE"
  | "STANDARD"
  | "CASE"
  | "ENTERPRISE"
  | "VIOLATION"
  | "PATENT"
  | "EXPERT_KNOWLEDGE"
  | "AUXILIARY";

/** DocumentStatus enum matching backend OpenAPI spec. */
export type DocumentStatus =
  | "DRAFT"
  | "PROMULGATED"
  | "EFFECTIVE"
  | "AMENDED"
  | "SUPERSEDED"
  | "REPEALED"
  | "EXPIRED"
  | "UNKNOWN";

/** Search mode matching backend API. */
export type SearchMode = "hybrid" | "keyword" | "vector" | "graph" | "field";

/** Advanced search filters matching PRD taxonomy dimensions. */
export interface LegalSearchFilters {
  doc_type?: DocType | string | string[];
  sub_type?: string | string[];
  legal_domain?: string | string[];
  jurisdiction?: string | string[];
  status?: DocumentStatus | string | string[];
  effective_date_gte?: string;
  effective_date_lte?: string;
  authority?: string;
  kb_id?: string;
  /** PRD §3.2 — 发文机关 (30+ authorities) */
  issuing_authority?: string;
  /** PRD §3.2 — 行业分类 (19 industries) */
  industry?: string | string[];
  /** PRD §3.3 — 法院层级 (4 levels) */
  court_level?: string;
}

// ─── Base URL ──────────────────────────────────────────────────────────

const uniSearcherClient = createHttpClient({
  baseURL: UNISEARCHER_API_URL,
  timeout: 30000,
});

// ─── Service ───────────────────────────────────────────────────────────

export class UniSearcherApiService {
  private client = uniSearcherClient;

  // ═══════════════════════════════════════════════════════════════════════
  // Auth
  // ═══════════════════════════════════════════════════════════════════════

  /** Login to legal-ext service. */
  async login(username: string, password: string): Promise<LoginResult> {
    return this.client.post<LoginResult>("/auth/login", { username, password });
  }

  // ═══════════════════════════════════════════════════════════════════════
  // Search (7 modes)
  // ═══════════════════════════════════════════════════════════════════════

  /** Advanced search with mode selection and 7-dimension filters. */
  async searchDocuments(params: {
    query: string;
    mode?: SearchMode;
    filters?: LegalSearchFilters;
    top_k?: number;
    use_graph?: boolean;
    as_of_date?: string;
    jurisdiction_boost?: string;
    bm25_weight?: number;
    vector_weight?: number;
    graph_weight?: number;
  }): Promise<LegalSearchResult> {
    return this.client.post<LegalSearchResult>("/search", {
      top_k: 10,
      mode: params.mode || "hybrid",
      use_graph: true,
      ...params,
      filters: params.filters || {},
    });
  }

  /** Faceted search — get dimension counts for filter panel. */
  async searchFacets(params: {
    query?: string;
    facet_fields?: string[];
    filters?: LegalSearchFilters;
  }): Promise<FacetResult> {
    return this.client.post<FacetResult>("/search/facets", {
      query: params.query || "",
      facet_fields: params.facet_fields || [
        "doc_type",
        "sub_type",
        "legal_domain",
        "jurisdiction",
        "status",
      ],
      filters: params.filters || {},
    });
  }

  /** Get search suggestions (autocomplete). */
  async searchSuggest(query: string, limit?: number): Promise<{ suggestions: string[] }> {
    return this.client.get("/search/suggest", { q: query, limit: limit || 8 });
  }

  // ═══════════════════════════════════════════════════════════════════════
  // RAG Q&A & Chat
  // ═══════════════════════════════════════════════════════════════════════

  /** RAG Q&A: ask a legal question, get AI answer with citations. */
  async askQuestion(params: {
    question: string;
    knowledge_base_id?: string;
    use_graph?: boolean;
  }): Promise<LegalQAResult> {
    const body: Record<string, unknown> = { question: params.question };
    if (params.knowledge_base_id) body.kb_id = params.knowledge_base_id;
    if (params.use_graph !== undefined) body.use_graph = params.use_graph;
    return this.client.post<LegalQAResult>("/ask", body);
  }

  /** Multi-turn legal chat with server-side conversation management. */
  async legalChat(params: {
    question: string;
    conversation_id?: string;
    kb_ids?: string[];
    use_graph?: boolean;
    mode?: string;
    /** Scope retrieval + answer to a single doc_type (e.g. "CASE", "STANDARD"). */
    doc_type?: string;
    /** Scope retrieval + answer to a sub_type (e.g. "CONTRACT_TEMPLATE"). */
    sub_type?: string;
  }): Promise<LegalChatResult> {
    const body: Record<string, unknown> = { question: params.question };
    if (params.conversation_id) body.conversation_id = params.conversation_id;
    if (params.kb_ids?.length) body.kb_ids = params.kb_ids;
    if (params.use_graph !== undefined) body.use_graph = params.use_graph;
    if (params.mode) body.mode = params.mode;
    if (params.doc_type) body.doc_type = params.doc_type;
    if (params.sub_type) body.sub_type = params.sub_type;
    return this.client.post<LegalChatResult>("/chat", body);
  }

  // ═══════════════════════════════════════════════════════════════════════
  // Conversation Management
  // ═══════════════════════════════════════════════════════════════════════

  /** List conversations for the current user (optionally scoped to a doc_type/sub_type). */
  async listConversations(params?: {
    limit?: number;
    offset?: number;
    /** Scope to a doc_type (e.g. "CASE"); omit to list only unscoped conversations. */
    doc_type?: string;
    /** Scope to a sub_type (e.g. "CONTRACT_TEMPLATE"). */
    sub_type?: string;
  }): Promise<{
    conversations: Array<{
      id: string;
      title: string;
      created_at: string;
      updated_at: string;
      message_count: number;
    }>;
  }> {
    return this.client.get("/chat/conversations", params);
  }

  /** Get a single conversation with full message history. */
  async getConversation(convId: string): Promise<{
    id: string;
    title: string;
    messages: Array<{
      role: string;
      content: string;
      timestamp: string;
      sources?: Array<Record<string, unknown>>;
    }>;
    created_at: string;
    updated_at: string;
  }> {
    return this.client.get(`/chat/conversations/${convId}`);
  }

  /** Delete a conversation. */
  async deleteConversation(convId: string): Promise<{ deleted: boolean; id: string }> {
    return this.client.delete(`/chat/conversations/${convId}`);
  }

  // ═══════════════════════════════════════════════════════════════════════
  // Document Operations
  // ═══════════════════════════════════════════════════════════════════════

  /** Get full document metadata, amendment history, and citations. */
  async getDocumentDetail(documentId: string): Promise<DocumentDetail> {
    return this.client.get<DocumentDetail>(`/documents/${documentId}/metadata`);
  }

  /** Get document chunks (parsed segments). */
  async getDocumentChunks(
    documentId: string,
    params?: { skip?: number; limit?: number },
  ): Promise<{ chunks: DocumentChunk[]; total: number }> {
    return this.client.get(`/documents/${documentId}/chunks`, params);
  }

  /** Get similar documents based on vector similarity. */
  async getSimilarDocuments(
    documentId: string,
    params?: { top_k?: number; doc_type?: string },
  ): Promise<{ results: LegalDocument[]; total: number }> {
    return this.client.get(`/documents/${documentId}/similar`, params);
  }

  /** Get documents that cite this document. */
  async getCitedBy(
    documentId: string,
    params?: { top_k?: number },
  ): Promise<{ results: LegalDocument[]; total: number }> {
    return this.client.get(`/documents/${documentId}/cited-by`, params);
  }

  /** Get amendment chain for a document. */
  async getAmendments(
    documentId: string,
  ): Promise<{ amendments: Array<{ date: string; description: string; doc_id?: string }> }> {
    return this.client.get(`/documents/${documentId}/amendments`);
  }

  /** Get version history for a document. */
  async getVersions(documentId: string): Promise<{ versions: DocumentVersion[] }> {
    return this.client.get(`/documents/${documentId}/versions`);
  }

  /** Point-in-time query — get document state at a specific date. */
  async getPointInTime(documentId: string, asOfDate: string): Promise<DocumentDetail> {
    return this.client.get(`/documents/${documentId}/point-in-time`, { as_of_date: asOfDate });
  }

  /** Get diff between two document versions. */
  async getVersionDiff(
    documentId: string,
    params: { from_version: string; to_version: string },
  ): Promise<DocumentDiff> {
    return this.client.get(`/documents/${documentId}/diff`, params);
  }

  /** Get document timeline (key events). */
  async getDocumentTimeline(documentId: string): Promise<DocumentTimeline> {
    return this.client.get(`/documents/${documentId}/timeline`);
  }

  /** Upload a document to the legal knowledge base. */
  async uploadDocument(params: {
    file: File;
    kb_id?: string;
    doc_type?: DocType;
    metadata?: Record<string, unknown>;
  }): Promise<{ document_id: string; status: string }> {
    const formData = new FormData();
    formData.append("file", params.file);
    if (params.kb_id) formData.append("kb_id", params.kb_id);
    if (params.doc_type) formData.append("doc_type", params.doc_type);
    if (params.metadata) formData.append("metadata", JSON.stringify(params.metadata));
    return this.client.upload("/documents/upload", formData);
  }

  /**
   * List documents with taxonomy filters, full-text query, pagination, and sorting.
   * Uses GET /api/v1/legal/documents — returns complete document metadata (titles
   * included), unlike /search which returns sparse chunk objects. This is the
   * correct endpoint for browse/filter use cases (e.g. contract-template library).
   */
  async listDocuments(params?: {
    doc_type?: DocType;
    sub_type?: string;
    legal_domain?: string;
    jurisdiction?: string;
    status?: DocumentStatus | string;
    industry?: string;
    authority?: string;
    /** Full-text query (matches title + content). */
    q?: string;
    effective_date_gte?: string;
    effective_date_lte?: string;
    promulgation_date_gte?: string;
    promulgation_date_lte?: string;
    kb_id?: string;
    page?: number;
    page_size?: number;
    sort_by?: string;
    sort_order?: string;
  }): Promise<DocumentListResult> {
    return this.client.get<DocumentListResult>("/documents", params);
  }

  // ═══════════════════════════════════════════════════════════════════════
  // Knowledge Graph
  // ═══════════════════════════════════════════════════════════════════════

  /** Search legal knowledge graph for entities and relationships. */
  async searchGraph(params: {
    query?: string;
    entity_type?: string;
    limit?: number;
  }): Promise<GraphSearchResponse> {
    return this.client.get<GraphSearchResponse>("/graph/entities", params);
  }

  /** Get a single graph entity by ID. */
  async getEntity(entityId: string): Promise<GraphEntity> {
    return this.client.get<GraphEntity>(`/graph/entities/${entityId}`);
  }

  /** Get neighbors of a graph entity. */
  async getNeighbors(
    entityId: string,
    params?: { relation_type?: string; limit?: number },
  ): Promise<{ neighbors: GraphNeighbor[] }> {
    return this.client.get(`/graph/entities/${entityId}/neighbors`, params);
  }

  /** Extract a subgraph based on entity IDs or criteria. */
  async extractSubgraph(params: {
    entity_ids?: string[];
    entity_types?: string[];
    max_depth?: number;
    limit?: number;
  }): Promise<GraphSubgraph> {
    return this.client.post<GraphSubgraph>("/graph/subgraph", params);
  }

  /** Get most influential entities in the knowledge graph. */
  async getInfluential(params?: { top?: number; entity_type?: string }): Promise<GraphInfluential> {
    return this.client.get("/graph/influential", params);
  }

  /** Get graph communities (clusters). */
  async getCommunities(params?: {
    algorithm?: string;
    entity_type?: string;
  }): Promise<{ communities: GraphCommunity[] }> {
    return this.client.get("/graph/communities", params);
  }

  /** Find shortest path between two entities. */
  async getShortestPath(params: {
    from_id: string;
    to_id: string;
    max_depth?: number;
  }): Promise<{ path: GraphPath | null }> {
    return this.client.get("/graph/path", params);
  }

  /** Get knowledge graph statistics. */
  async getGraphStats(): Promise<GraphStats> {
    return this.client.get<GraphStats>("/graph/stats");
  }

  // ═══════════════════════════════════════════════════════════════════════
  // Analytics
  // ═══════════════════════════════════════════════════════════════════════

  /** Regulatory trend analysis over time. */
  async getRegulatoryTrend(params: {
    start_date?: string;
    end_date?: string;
    doc_type?: DocType;
    granularity?: "month" | "quarter" | "year";
  }): Promise<{ trend: TrendPoint[] }> {
    return this.client.post("/analytics/trend", params);
  }

  /** Document lifecycle statistics. */
  async getLifecycleStats(params: {
    doc_type?: DocType;
    jurisdiction?: string;
  }): Promise<Record<string, unknown>> {
    return this.client.post("/analytics/lifecycle", params);
  }

  /** Jurisdiction heatmap — document density per region. */
  async getJurisdictionHeatmap(params: {
    doc_type?: DocType;
    legal_domain?: string;
  }): Promise<{ heatmap: HeatmapCell[] }> {
    return this.client.post("/analytics/jurisdiction-heatmap", params);
  }

  /** Subtype distribution statistics. */
  async getSubtypeDistribution(params?: { doc_type?: DocType }): Promise<Record<string, number>> {
    return this.client.get("/analytics/subtype-distribution", params);
  }

  /** Top issuing authorities by document count. */
  async getTopAuthorities(params?: {
    doc_type?: DocType;
    top_k?: number;
  }): Promise<Array<{ authority: string; count: number }>> {
    return this.client.get("/analytics/top-authorities", params);
  }

  // ═══════════════════════════════════════════════════════════════════════
  // Enterprise Compliance
  // ═══════════════════════════════════════════════════════════════════════

  /** Get compliance profile for an enterprise. */
  async getEnterpriseCompliance(name: string): Promise<EnterpriseComplianceProfile> {
    return this.client.get(`/enterprises/${encodeURIComponent(name)}/compliance-profile`);
  }

  /** Get enterprise violation statistics. */
  async getViolationStats(params?: {
    industry?: string;
    jurisdiction?: string;
  }): Promise<ViolationStats> {
    return this.client.get("/enterprises/violation-stats", params);
  }

  // ═══════════════════════════════════════════════════════════════════════
  // Expert Knowledge
  // ═══════════════════════════════════════════════════════════════════════

  /** Upload expert knowledge content. */
  async uploadExpertKnowledge(params: {
    title: string;
    content: string;
    sub_type?: string;
    kb_id?: string;
    jurisdiction?: string;
    legal_domain?: string[];
    author?: string;
    author_title?: string;
    organization?: string;
    tags?: string[];
    related_laws?: string[];
    related_cases?: string[];
    access_level?: string;
    summary?: string;
  }): Promise<{ document_id: string; status: string }> {
    return this.client.post("/expert/upload", params);
  }

  /** Get recommended expert knowledge for a query. */
  async recommendExpertKnowledge(params: {
    query: string;
    legal_domain?: string[];
    top_k?: number;
  }): Promise<{ results: LegalDocument[]; total: number }> {
    return this.client.post("/expert/recommend", params);
  }

  /** Get expert knowledge statistics. */
  async getExpertStats(): Promise<ExpertKnowledgeStats> {
    return this.client.get("/expert/stats");
  }

  // ═══════════════════════════════════════════════════════════════════════
  // Concepts
  // ═══════════════════════════════════════════════════════════════════════

  /** Compare two legal concepts (e.g., GDPR vs PIPL). */
  async compareConcepts(params: {
    concept_a: string;
    concept_b: string;
    jurisdiction?: string;
  }): Promise<ConceptComparison> {
    return this.client.post("/concepts/compare", params);
  }

  /** List legal concepts. */
  async listConcepts(params?: {
    legal_domain?: string;
    jurisdiction?: string;
  }): Promise<{ concepts: Concept[] }> {
    return this.client.get("/concepts", params);
  }

  /** Create a new legal concept. */
  async createConcept(params: {
    name: string;
    description?: string;
    jurisdiction?: string;
    legal_domain?: string[];
  }): Promise<Concept> {
    return this.client.post("/concepts", params);
  }

  // ═══════════════════════════════════════════════════════════════════════
  // Knowledge Base Management
  // ═══════════════════════════════════════════════════════════════════════

  /** List available knowledge bases with descriptions and document counts. */
  async listKnowledgeBases(): Promise<KnowledgeBaseListResult> {
    return this.client.get<KnowledgeBaseListResult>("/knowledge-bases");
  }

  /** Discover available knowledge bases with capabilities. */
  async discoverKnowledgeBases(): Promise<KBDiscoveryResult> {
    return this.client.get<KBDiscoveryResult>("/knowledge-bases/discover");
  }

  /** Create a new knowledge base. */
  async createKnowledgeBase(params: {
    name: string;
    description?: string;
  }): Promise<LegalKnowledgeBase> {
    return this.client.post("/knowledge-bases", params);
  }

  /** Get knowledge base details. */
  async getKnowledgeBase(kbId: string): Promise<LegalKnowledgeBase> {
    return this.client.get(`/knowledge-bases/${kbId}`);
  }

  /** Update knowledge base metadata. */
  async updateKnowledgeBase(
    kbId: string,
    params: {
      name?: string;
      description?: string;
      status?: string;
      config?: Record<string, unknown>;
    },
  ): Promise<LegalKnowledgeBase> {
    return this.client.put(`/knowledge-bases/${kbId}`, params);
  }

  /** Delete a knowledge base. */
  async deleteKnowledgeBase(kbId: string): Promise<void> {
    return this.client.delete(`/knowledge-bases/${kbId}`);
  }

  // ═══════════════════════════════════════════════════════════════════════
  // Monitoring
  // ═══════════════════════════════════════════════════════════════════════

  /** Get system statistics: document counts, entity counts, domain coverage. */
  async getSystemStats(): Promise<LegalSystemStats> {
    const resp = await this.client.get<{ data?: LegalSystemStats } | LegalSystemStats>("/stats");
    // Unwrap envelope if present
    if (resp && typeof resp === "object" && "data" in resp) {
      return resp.data as LegalSystemStats;
    }
    return resp as LegalSystemStats;
  }

  /** Health check for the legal-ext service. */
  async healthCheck(): Promise<{ status: string }> {
    return this.client.get<{ status: string }>("/health");
  }

  /** List Celery task artifacts. */
  async listTasks(params?: {
    status?: string;
    task_type?: string;
    page?: number;
    page_size?: number;
  }): Promise<{ tasks: Array<Record<string, unknown>>; total: number }> {
    return this.client.get("/tasks", params);
  }

  /** Get task detail. */
  async getTask(taskId: string): Promise<Record<string, unknown>> {
    return this.client.get(`/tasks/${taskId}`);
  }
}

export const uniSearcherApi = new UniSearcherApiService();
