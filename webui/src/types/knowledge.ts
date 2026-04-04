/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/** 知识库相关类型定义 */

/** 文档类型 */
export type DocumentType = 'markdown' | 'image' | 'audio' | 'video'

/** 检索模式 */
export type RetrievalMode = 'vector' | 'graph' | 'fulltext' | 'hybrid'

/** 分块策略 */
export type ChunkingStrategy = 'fixed_size' | 'recursive' | 'semantic' | 'markdown' | 'code'

/** 知识抽取策略 */
export type ExtractionStrategy = 'rule_based' | 'llm' | 'ner_model' | 'auto'

/** 知识库状态 */
export type KnowledgeBaseStatus = 'active' | 'archived' | 'deleting'

/** 知识库设置 */
export interface KnowledgeBaseSettings {
  // File directory watching
  watch_dir: string
  watch_enabled: boolean
  watch_recursive: boolean
  watch_extensions: string[]

  chunk_size: number
  chunk_overlap: number
  chunk_strategy: ChunkingStrategy
  embedding_model: 'qwen3-embedding' | 'minilm' | 'bge-m3' | 'bge-large-zh' | 'jina-v4' | 'text-embedding-3-large'
  embedding_dimension: number
  default_top_k: number
  default_mode: RetrievalMode
  vector_weight: number
  graph_weight: number
  fulltext_weight: number
  extraction_strategy: ExtractionStrategy
  enable_graph: boolean
  enable_fulltext: boolean
  auto_reindex: boolean

  // Domain knowledge graph
  domain?: string
}

/** 知识库统计 */
export interface KnowledgeBaseStats {
  total_documents: number
  total_chunks: number
  total_entities: number
  total_relations: number
  indexed_documents: number
  storage_size_bytes: number
  last_indexed_at: string | null
  last_updated_at: string
}

/** 知识库 */
export interface KnowledgeBase {
  id: string
  name: string
  description: string
  status: KnowledgeBaseStatus
  settings: KnowledgeBaseSettings
  stats: KnowledgeBaseStats
  created_at: string
  updated_at: string
  created_by: string
  workspace_id: string | null
  tags: string[]
  is_default: boolean
  storage_path: string
}

/** 创建知识库请求 */
export interface KnowledgeBaseCreate {
  name: string
  description?: string
  settings?: Partial<KnowledgeBaseSettings>
  workspace_id?: string
  tags?: string[]
  is_default?: boolean
}

/** 更新知识库请求 */
export interface KnowledgeBaseUpdate {
  name?: string
  description?: string
  settings?: KnowledgeBaseSettings
  tags?: string[]
  status?: KnowledgeBaseStatus
}

/** 知识库列表响应 */
export interface KnowledgeBaseListResponse {
  total: number
  items: KnowledgeBase[]
  default_base_id: string | null
}

/** 文档信息 */
export interface DocumentInfo {
  id: string
  file_path: string
  file_name: string
  file_size: number
  file_type: DocumentType
  sha256: string
  created_at: string
  updated_at: string
  indexed_at: string | null
  author?: string
  title?: string
  tags?: string[]
  language?: string
  page_count?: number
  chunk_count: number
  metadata?: Record<string, any>
  description?: string
}

/** 文档块 */
export interface DocumentChunk {
  id: string
  document_id: string
  chunk_index: number
  content: string
  metadata: Record<string, any>
}

/** 搜索结果 */
export interface SearchResult {
  id: string
  content: string
  score: number
  source: 'vector' | 'graph' | 'fulltext' | 'hybrid'
  metadata: Record<string, any>
}

/** 搜索请求 */
export interface SearchRequest {
  query: string
  mode?: RetrievalMode
  top_k?: number
  filters?: Record<string, any>
  min_score?: number
  vector_weight?: number
  graph_weight?: number
  fulltext_weight?: number
}

/** 搜索响应 */
export interface SearchResponse {
  success: boolean
  query: string
  mode: RetrievalMode
  results: SearchResult[]
  total_count: number
  vector_count: number
  graph_count: number
  fulltext_count: number
  latency_ms: number
}

/** RAG查询响应 */
export interface RAGQueryResponse {
  success: boolean
  query: string
  prompt: string
  context: string
  sources: Array<{
    id: string
    score: number
    source_type: string
    file_name?: string
    file_path?: string
    title?: string
    author?: string
    chunk_index?: number
  }>
  citations: string[]
  metadata: {
    total_results: number
    vector_count: number
    graph_count: number
    fulltext_count: number
    latency_ms: number
  }
}

/** 统计信息 */
export interface Stats {
  totalDocuments: number
  totalChunks: number
  totalEntities: number
  avgRelevance: number
}

/** 知识库设置 */
export interface KnowledgeSettings {
  chunkSize: number
  chunkOverlap: number
  embeddingModel: 'minilm' | 'bge-m3' | 'jina-v4'
  chunkStrategy: ChunkingStrategy
}

/** 图谱实体 */
export interface GraphEntity {
  id: string
  type: string
  name: string
  properties: Record<string, any>
}

/** 图谱关系 */
export interface GraphRelation {
  id: string
  from_entity: string
  to_entity: string
  relation_type: string
  properties: Record<string, any>
}

/** Domain schema - defines entity types and relations for a domain */
export interface DomainSchema {
  domain: string
  description: string
   
  entity_types: Record<string, {
    description: string
    properties: Record<string, {
      type: string
      description: string
      required: boolean
    }>
  }>
   
  relation_types: Record<string, {
    description: string
    from_type: string
    to_type: string
     
    properties?: Record<string, {
      type: string
      description: string
      required: boolean
    }>
  }>
}

/** Entity source - where entities can be extracted from */
export interface EntitySource {
  source_type: 'text' | 'table' | 'image' | 'audio' | 'video' | 'code' | 'structured'
  description: string
  extraction_method: string
  confidence: number
  example_count?: number
}

/** Domain option for dropdown/selection */
export interface DomainOption {
  value: string
  label: string
  description?: string
}
