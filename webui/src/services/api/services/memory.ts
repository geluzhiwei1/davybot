/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * Memory API Service
 * DaweiMem - Memory Management API
 */

import { httpClient } from '../http'
import type {
  MemoryEntry,
  MemoryFilters,
  MemoryListResponse,
  MemoryStats,
  TemporalQueryParams,
  AssociativeRetrievalParams,
  MemoryExportFormat,
  ContextPage,
  MemorySearchResult,
  CreateMemoryParams,
  UpdateMemoryParams
} from '@/types/memory'

/**
 * Memory API Service
 * Handles all memory-related API calls
 */
export class MemoryApiService {
  private baseUrl = '/memory'


  /**
   * List all memories with optional filters
   */
  async listMemories(
    workspaceId: string,
    filters?: MemoryFilters
  ): Promise<MemoryListResponse> {
    const params = new URLSearchParams()

    if (filters?.type && filters.type !== 'all') {
      params.append('type', filters.type)
    }
    if (filters?.minConfidence !== undefined) {
      params.append('min_confidence', filters.minConfidence.toString())
    }
    if (filters?.minEnergy !== undefined) {
      params.append('min_energy', filters.minEnergy.toString())
    }
    if (filters?.dateFrom) {
      params.append('date_from', filters.dateFrom)
    }
    if (filters?.dateTo) {
      params.append('date_to', filters.dateTo)
    }
    if (filters?.subject) {
      params.append('subject', filters.subject)
    }
    if (filters?.keyword) {
      params.append('keyword', filters.keyword)
    }
    if (filters?.onlyValid !== undefined) {
      params.append('only_valid', filters.onlyValid.toString())
    }

    const url = params.toString()
      ? `/workspaces/${workspaceId}/memory?${params}`
      : `/workspaces/${workspaceId}/memory`

    return httpClient.get<MemoryListResponse>(url)
  }

  /**
   * Get a single memory by ID
   */
  async getMemory(workspaceId: string, memoryId: string): Promise<MemoryEntry> {
    return httpClient.get<MemoryEntry>(
      `/workspaces/${workspaceId}/memory/${memoryId}`
    )
  }

  /**
   * Create a new memory entry
   */
  async createMemory(
    workspaceId: string,
    params: CreateMemoryParams
  ): Promise<MemoryEntry> {
    return httpClient.post<MemoryEntry>(
      `/workspaces/${workspaceId}/memory`,
      params
    )
  }

  /**
   * Update an existing memory entry
   */
  async updateMemory(
    workspaceId: string,
    memoryId: string,
    updates: UpdateMemoryParams
  ): Promise<MemoryEntry> {
    return httpClient.patch<MemoryEntry>(
      `/workspaces/${workspaceId}/memory/${memoryId}`,
      updates
    )
  }

  /**
   * Delete a memory entry
   */
  async deleteMemory(workspaceId: string, memoryId: string): Promise<void> {
    return httpClient.delete<void>(
      `workspaces/${workspaceId}/memory/${memoryId}`
    )
  }

  /**
   * Delete multiple memories
   */
  async deleteMemories(
    workspaceId: string,
    memoryIds: string[]
  ): Promise<void> {
    return httpClient.post<void>(
      `workspaces/${workspaceId}/memory/bulk-delete`,
      { memory_ids: memoryIds }
    )
  }

  /**
   * Search memories by query
   */
  async searchMemories(
    workspaceId: string,
    query: string,
    filters?: Partial<MemoryFilters>
  ): Promise<MemorySearchResult[]> {
    const params = new URLSearchParams()
    params.append('q', query)

    if (filters?.type && filters.type !== 'all') {
      params.append('type', filters.type)
    }
    if (filters?.minConfidence !== undefined) {
      params.append('min_confidence', filters.minConfidence.toString())
    }

    return httpClient.get<MemorySearchResult[]>(
      `workspaces/${workspaceId}/memory/search?${params}`
    )
  }

  /**
   * Temporal query - get memories valid at a specific time
   */
  async queryTemporal(
    workspaceId: string,
    params: TemporalQueryParams
  ): Promise<MemoryEntry[]> {
    const queryParams = new URLSearchParams()

    if (params.subject) {
      queryParams.append('subject', params.subject)
    }
    if (params.predicate) {
      queryParams.append('predicate', params.predicate)
    }
    if (params.object) {
      queryParams.append('object', params.object)
    }
    if (params.at_time) {
      queryParams.append('at_time', params.at_time)
    }
    if (params.only_valid !== undefined) {
      queryParams.append('only_valid', params.only_valid.toString())
    }

    const url = queryParams.toString()
      ? `workspaces/${workspaceId}/memory/temporal?${queryParams}`
      : `workspaces/${workspaceId}/memory/temporal`

    return httpClient.get<MemoryEntry[]>(url)
  }

  /**
   * Associative retrieval - graph traversal
   */
  async retrieveAssociative(
    workspaceId: string,
    params: AssociativeRetrievalParams
  ): Promise<MemoryEntry[]> {
    return httpClient.post<MemoryEntry[]>(
      `workspaces/${workspaceId}/memory/associative`,
      params
    )
  }

  /**
   * Get memory statistics
   */
  async getStats(workspaceId: string): Promise<MemoryStats> {
    return httpClient.get<MemoryStats>(
      `workspaces/${workspaceId}/memory/stats`
    )
  }

  /**
   * Export memories
   */
  async exportMemories(
    workspaceId: string,
    format: MemoryExportFormat = 'json',
    filters?: MemoryFilters
  ): Promise<Blob> {
    const params = new URLSearchParams()
    params.append('format', format)

    if (filters?.type && filters.type !== 'all') {
      params.append('type', filters.type)
    }
    if (filters?.dateFrom) {
      params.append('date_from', filters.dateFrom)
    }
    if (filters?.dateTo) {
      params.append('date_to', filters.dateTo)
    }

    const response = await fetch(
      `/workspaces/${workspaceId}/memory/export?${params}`,
      {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json'
        }
      }
    )

    if (!response.ok) {
      throw new Error(`Export failed: ${response.statusText}`)
    }

    return response.blob()
  }

  /**
   * Import memories
   */
  async importMemories(
    workspaceId: string,
    file: File,
    format: MemoryExportFormat = 'json'
  ): Promise<{ imported: number; errors: string[] }> {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('format', format)

    return httpClient.post<{ imported: number; errors: string[] }>(
      `workspaces/${workspaceId}/import`,
      formData,
      {
        headers: {
          'Content-Type': 'multipart/form-data'
        }
      }
    )
  }

  /**
   * Get context pages
   */
  async getContextPages(
    workspaceId: string,
    sessionId?: string
  ): Promise<ContextPage[]> {
    const params = sessionId
      ? `?session_id=${sessionId}`
      : ''

    return httpClient.get<ContextPage[]>(
      `workspaces/${workspaceId}/context-pages${params}`
    )
  }

  /**
   * Load a context page into active context
   */
  async loadContextPage(
    workspaceId: string,
    pageId: string,
    query: string,
    topK: number = 3
  ): Promise<string[]> {
    return httpClient.post<string[]>(
      `workspaces/${workspaceId}/context-pages/load`,
      { page_id: pageId, query, top_k: topK }
    )
  }

  /**
   * Get memory evolution history for a subject
   */
  async getEvolutionHistory(
    workspaceId: string,
    subject: string,
    predicate?: string
  ): Promise<MemoryEntry[]> {
    const params = new URLSearchParams()
    params.append('subject', subject)
    if (predicate) {
      params.append('predicate', predicate)
    }

    return httpClient.get<MemoryEntry[]>(
      `workspaces/${workspaceId}/evolution?${params}`
    )
  }

  /**
   * Consolidate memories (trigger manual consolidation)
   */
  async consolidateMemories(
    workspaceId: string,
    subject?: string
  ): Promise<{ strategies_created: number }> {
    return httpClient.post<{ strategies_created: number }>(
      `workspaces/${workspaceId}/consolidate`,
      { subject }
    )
  }

  /**
   * Archive expired memories
   */
  async archiveExpiredMemories(
    workspaceId: string
  ): Promise<{ archived: number }> {
    return httpClient.post<{ archived: number }>(
      `workspaces/${workspaceId}/archive`,
      {}
    )
  }

  /**
   * Boost memory energy (manual boost)
   */
  async boostMemoryEnergy(
    workspaceId: string,
    memoryId: string,
    boost: number = 0.2
  ): Promise<MemoryEntry> {
    return httpClient.post<MemoryEntry>(
      `workspaces/${workspaceId}/memory/${memoryId}/boost`,
      { boost }
    )
  }

  /**
   * Get graph data for visualization
   */
  async getGraphData(
    workspaceId: string,
    filters?: MemoryFilters
  ): Promise<{ nodes: unknown[]; links: unknown[] }> {
    const params = new URLSearchParams()

    if (filters?.type && filters.type !== 'all') {
      params.append('type', filters.type)
    }
    if (filters?.minEnergy !== undefined) {
      params.append('min_energy', filters.minEnergy.toString())
    }

    const url = params.toString()
      ? `workspaces/${workspaceId}/memory/graph?${params}`
      : `workspaces/${workspaceId}/memory/graph`

    return httpClient.get<{ nodes: unknown[]; links: unknown[] }>(url)
  }

  /**
   * Extract memories from conversation files
   */
  async extractMemories(
    workspaceId: string
  ): Promise<{
    success: boolean
    workspace_id: string
    extracted: number
    method: string
    details: string[]
    message: string
  }> {
    return httpClient.post<{
      success: boolean
      workspace_id: string
      extracted: number
      method: string
      details: string[]
      message: string
    }>(`workspaces/${workspaceId}/memory/extract`, {})
  }

  /**
   * Get timeline data
   */
  async getTimelineData(
    workspaceId: string,
    subject?: string,
    startDate?: string,
    endDate?: string
  ): Promise<{ date: string; memories: MemoryEntry[] }[]> {
    const params = new URLSearchParams()
    if (subject) {
      params.append('subject', subject)
    }
    if (startDate) {
      params.append('start_date', startDate)
    }
    if (endDate) {
      params.append('end_date', endDate)
    }

    const url = params.toString()
      ? `workspaces/${workspaceId}/memory/timeline?${params}`
      : `workspaces/${workspaceId}/memory/timeline`

    return httpClient.get<{ date: string; memories: MemoryEntry[] }[]>(url)
  }

  /**
   * Validate memory entry
   */
  async validateMemory(
    workspaceId: string,
    memory: Partial<MemoryEntry>
  ): Promise<{ valid: boolean; errors: string[]; warnings: string[] }> {
    return httpClient.post<{ valid: boolean; errors: string[]; warnings: string[] }>(
      `workspaces/${workspaceId}/validate`,
      memory
    )
  }
}

// Export factory function
export function createMemoryApiService(): MemoryApiService {
  return new MemoryApiService()
}
