/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * Memory System Type Definitions
 * DaweiMem - Frontend Types
 */

/**
 * Memory entry types
 */
export enum MemoryType {
  FACT = 'fact',
  PREFERENCE = 'preference',
  PROCEDURE = 'procedure',
  CONTEXT = 'context',
  STRATEGY = 'strategy',
  EPISODE = 'episode'
}

/**
 * Memory entry - Temporal knowledge graph node
 */
export interface MemoryEntry {
  id: string
  subject: string
  predicate: string
  object: string

  // Temporal attributes
  valid_start: string  // ISO datetime
  valid_end?: string   // ISO datetime or null for currently valid

  // Dynamics
  confidence: number   // 0.0 - 1.0
  energy: number       // 0.0 - 1.0
  access_count: number

  // Classification
  memory_type: MemoryType

  // Search & metadata
  keywords: string[]
  source_event_id?: string
  metadata: Record<string, unknown>

  // Timestamps
  created_at: string
  updated_at: string
}

/**
 * Memory filters for search/list
 */
export interface MemoryFilters {
  type?: MemoryType | 'all'
  minConfidence?: number
  minEnergy?: number
  dateFrom?: string
  dateTo?: string
  subject?: string
  keyword?: string
  onlyValid?: boolean
}

/**
 * Temporal query parameters
 */
export interface TemporalQueryParams {
  subject?: string
  predicate?: string
  object?: string
  at_time?: string  // ISO datetime
  only_valid?: boolean
}

/**
 * Graph node for visualization
 */
export interface GraphNode {
  id: string
  label: string
  type: MemoryType
  energy: number
  x?: number
  y?: number
  radius?: number
}

/**
 * Graph link for visualization
 */
export interface GraphLink {
  source: string
  target: string
  label: string  // predicate
  confidence: number
  id?: string
}

/**
 * Graph data for visualization
 */
export interface GraphData {
  nodes: GraphNode[]
  links: GraphLink[]
}

/**
 * Timeline entry
 */
export interface TimelineEntry {
  date: string
  memories: MemoryEntry[]
}

/**
 * Memory statistics
 */
export interface MemoryStats {
  total: number
  byType: Record<MemoryType, number>
  avgConfidence: number
  avgEnergy: number
  mostAccessed: MemoryEntry[]
  recent: MemoryEntry[]
  lowEnergy: number  // Count of memories with energy < 0.2
}

/**
 * View modes for memory browser
 */
export type ViewMode = 'graph' | 'list' | 'timeline'

/**
 * Memory API response wrapper
 */
export interface MemoryApiResponse<T> {
  success: boolean
  data?: T
  error?: string
  message?: string
}

/**
 * Memory list response
 */
export interface MemoryListResponse {
  items: MemoryEntry[]
  total: number
  page: number
  pageSize: number
}

/**
 * Associative retrieval params
 */
export interface AssociativeRetrievalParams {
  entities: string[]
  hops: number
  minEnergy?: number
}

/**
 * Memory export format
 */
export type MemoryExportFormat = 'json' | 'csv' | 'ndjson'

/**
 * Memory validation result
 */
export interface MemoryValidationResult {
  valid: boolean
  errors: string[]
  warnings: string[]
}

/**
 * Memory comparison result
 */
export interface MemoryComparison {
  old: MemoryEntry
  new: MemoryEntry
  changes: {
    field: string
    oldValue: unknown
    newValue: unknown
  }[]
}

/**
 * Memory context page
 */
export interface ContextPage {
  page_id: string
  session_id: string
  content: string
  summary: string
  tokens: number
  access_count: number
  last_accessed: string
  created_at: string
  source_type: string
  source_ref?: string
}

/**
 * Memory search result with relevance score
 */
export interface MemorySearchResult extends MemoryEntry {
  relevance: number  // 0.0 - 1.0
  highlights: {
    subject?: string
    predicate?: string
    object?: string
  }
}

/**
 * Memory cluster (for grouping related memories)
 */
export interface MemoryCluster {
  id: string
  label: string
  center_subject: string
  memories: MemoryEntry[]
  connections: number  // Number of internal connections
}

/**
 * Memory creation params
 */
export interface CreateMemoryParams {
  subject: string
  predicate: string
  object: string
  memory_type: MemoryType
  confidence?: number
  energy?: number
  keywords?: string[]
  metadata?: Record<string, unknown>
}

/**
 * Memory update params
 */
export interface UpdateMemoryParams {
  predicate?: string
  object?: string
  valid_end?: string
  confidence?: number
  energy?: number
  keywords?: string[]
  metadata?: Record<string, unknown>
}

/**
 * Memory consolidation result
 */
export interface MemoryConsolidation {
  strategy_id: string
  consolidated_from: string[]  // Memory IDs
  summary: string
}

/**
 * Memory graph layout options
 */
export interface GraphLayoutOptions {
  type: 'force' | 'hierarchical' | 'circular'
  nodeSize?: number
  linkWidth?: number
  showLabels?: boolean
  clusterByType?: boolean
  animation?: boolean
}

/**
 * Memory UI state
 */
export interface MemoryUIState {
  viewMode: ViewMode
  selectedId: string | null
  searchQuery: string
  filters: MemoryFilters
  loading: boolean
  error: string | null
  showDetails: boolean
  graphLayout: GraphLayoutOptions
}
