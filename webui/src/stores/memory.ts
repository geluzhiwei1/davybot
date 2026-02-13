/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * Memory Store (Pinia)
 * DaweiMem - Memory State Management
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type {
  MemoryEntry,
  MemoryFilters,
  MemoryStats,
  ViewMode,
  GraphData,
  TimelineEntry,
  MemorySearchResult,
  CreateMemoryParams,
  UpdateMemoryParams
} from '@/types/memory'
import { MemoryType } from '@/types/memory'

export const useMemoryStore = defineStore('memory', () => {
  // State
  const memories = ref<MemoryEntry[]>([])
  const selectedId = ref<string | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const viewMode = ref<ViewMode>('graph')
  const searchQuery = ref('')
  const filters = ref<MemoryFilters>({
    type: 'all',
    onlyValid: true
  })
  const stats = ref<MemoryStats | null>(null)
  const graphData = ref<GraphData>({ nodes: [], links: [] })
  const timelineData = ref<TimelineEntry[]>([])

  // Getters
  const selectedMemory = computed(() => {
    return memories.value.find(m => m.id === selectedId.value) || null
  })

  const memoriesByType = computed(() => {
    const grouped: Record<MemoryType, MemoryEntry[]> = {
      [MemoryType.FACT]: [],
      [MemoryType.PREFERENCE]: [],
      [MemoryType.PROCEDURE]: [],
      [MemoryType.CONTEXT]: [],
      [MemoryType.STRATEGY]: [],
      [MemoryType.EPISODE]: []
    }

    for (const memory of memories.value) {
      grouped[memory.memory_type].push(memory)
    }

    return grouped
  })

  const filteredMemories = computed(() => {
    let filtered = [...memories.value]

    // Apply type filter
    if (filters.value.type && filters.value.type !== 'all') {
      filtered = filtered.filter(m => m.memory_type === filters.value.type)
    }

    // Apply confidence filter
    if (filters.value.minConfidence !== undefined) {
      filtered = filtered.filter(m => m.confidence >= filters.value.minConfidence!)
    }

    // Apply energy filter
    if (filters.value.minEnergy !== undefined) {
      filtered = filtered.filter(m => m.energy >= filters.value.minEnergy!)
    }

    // Apply date filter
    if (filters.value.dateFrom) {
      const fromDate = new Date(filters.value.dateFrom)
      filtered = filtered.filter(m => new Date(m.valid_start) >= fromDate)
    }

    if (filters.value.dateTo) {
      const toDate = new Date(filters.value.dateTo)
      filtered = filtered.filter(m => new Date(m.valid_start) <= toDate)
    }

    // Apply subject filter
    if (filters.value.subject) {
      filtered = filtered.filter(m =>
        m.subject.toLowerCase().includes(filters.value.subject!.toLowerCase())
      )
    }

    // Apply keyword filter
    if (filters.value.keyword) {
      const keyword = filters.value.keyword.toLowerCase()
      filtered = filtered.filter(m =>
        m.keywords.some(k => k.toLowerCase().includes(keyword)) ||
        m.object.toLowerCase().includes(keyword) ||
        m.predicate.toLowerCase().includes(keyword)
      )
    }

    // Apply validity filter
    if (filters.value.onlyValid) {
      const now = new Date().toISOString()
      filtered = filtered.filter(m =>
        m.valid_end === null || m.valid_end > now
      )
    }

    // Apply search query
    if (searchQuery.value) {
      const query = searchQuery.value.toLowerCase()
      filtered = filtered.filter(m =>
        m.subject.toLowerCase().includes(query) ||
        m.predicate.toLowerCase().includes(query) ||
        m.object.toLowerCase().includes(query) ||
        m.keywords.some(k => k.toLowerCase().includes(query))
      )
    }

    return filtered
  })

  const totalMemories = computed(() => memories.value.length)
  const validMemories = computed(() => {
    const now = new Date().toISOString()
    return memories.value.filter(m => m.valid_end === null || m.valid_end > now)
  })
  const archivedMemories = computed(() => {
    const now = new Date().toISOString()
    return memories.value.filter(m => m.valid_end !== null && m.valid_end <= now)
  })

  // Actions
  async function loadMemories(workspaceId: string) {
    loading.value = true
    error.value = null

    try {
      // Import here to avoid circular dependency
      const { apiManager } = await import('@/services/api')
      const memoryApi = apiManager.getMemoryApi()

      const response = await memoryApi.listMemories(workspaceId, filters.value)
      memories.value = response.items || []
    } catch (e: unknown) {
      error.value = e.message || 'Failed to load memories'
      console.error('Failed to load memories:', e)
    } finally {
      loading.value = false
    }
  }

  async function loadStats(workspaceId: string) {
    try {
      const { apiManager } = await import('@/services/api')
      const memoryApi = apiManager.getMemoryApi()

      stats.value = await memoryApi.getStats(workspaceId)
    } catch (e: unknown) {
      console.error('Failed to load memory stats:', e)
    }
  }

  async function loadGraphData(workspaceId: string) {
    try {
      const { apiManager } = await import('@/services/api')
      const memoryApi = apiManager.getMemoryApi()

      const data = await memoryApi.getGraphData(workspaceId, filters.value)
      graphData.value = data
    } catch (e: unknown) {
      console.error('Failed to load graph data:', e)
    }
  }

  async function loadTimelineData(
    workspaceId: string,
    subject?: string,
    startDate?: string,
    endDate?: string
  ) {
    try {
      const { apiManager } = await import('@/services/api')
      const memoryApi = apiManager.getMemoryApi()

      const data = await memoryApi.getTimelineData(
        workspaceId,
        subject,
        startDate,
        endDate
      )
      timelineData.value = data
    } catch (e: unknown) {
      console.error('Failed to load timeline data:', e)
    }
  }

  async function createMemory(
    workspaceId: string,
    params: CreateMemoryParams
  ): Promise<MemoryEntry | null> {
    loading.value = true
    error.value = null

    try {
      const { apiManager } = await import('@/services/api')
      const memoryApi = apiManager.getMemoryApi()

      const newMemory = await memoryApi.createMemory(workspaceId, params)
      memories.value.push(newMemory)

      // Reload stats
      await loadStats(workspaceId)

      return newMemory
    } catch (e: unknown) {
      error.value = e.message || 'Failed to create memory'
      console.error('Failed to create memory:', e)
      return null
    } finally {
      loading.value = false
    }
  }

  async function updateMemory(
    workspaceId: string,
    memoryId: string,
    updates: UpdateMemoryParams
  ): Promise<boolean> {
    loading.value = true
    error.value = null

    try {
      const { apiManager } = await import('@/services/api')
      const memoryApi = apiManager.getMemoryApi()

      const updated = await memoryApi.updateMemory(workspaceId, memoryId, updates)

      // Update local state
      const index = memories.value.findIndex(m => m.id === memoryId)
      if (index !== -1) {
        memories.value[index] = updated
      }

      // Reload stats
      await loadStats(workspaceId)

      return true
    } catch (e: unknown) {
      error.value = e.message || 'Failed to update memory'
      console.error('Failed to update memory:', e)
      return false
    } finally {
      loading.value = false
    }
  }

  async function deleteMemory(workspaceId: string, memoryId: string): Promise<boolean> {
    // ✅ Fast Fail: 验证必需参数
    if (!workspaceId || workspaceId.trim() === '') {
      throw new Error('[MemoryStore] workspaceId cannot be empty when deleting memory')
    }
    if (!memoryId || memoryId.trim() === '') {
      throw new Error('[MemoryStore] memoryId cannot be empty when deleting memory')
    }

    loading.value = true
    error.value = null

    try {
      const { apiManager } = await import('@/services/api')
      const memoryApi = apiManager.getMemoryApi()

      await memoryApi.deleteMemory(workspaceId, memoryId)

      // Remove from local state
      memories.value = memories.value.filter(m => m.id !== memoryId)

      // Clear selection if deleted
      if (selectedId.value === memoryId) {
        selectedId.value = null
      }

      // Reload stats
      await loadStats(workspaceId)

      return true
    } catch (e: unknown) {
      error.value = e.message || 'Failed to delete memory'
      console.error('Failed to delete memory:', e)
      return false
    } finally {
      loading.value = false
    }
  }

  async function searchMemories(
    workspaceId: string,
    query: string
  ): Promise<MemorySearchResult[]> {
    // ✅ Fast Fail: 验证必需参数
    if (!workspaceId || workspaceId.trim() === '') {
      throw new Error('[MemoryStore] workspaceId cannot be empty when searching memories')
    }
    if (!query || query.trim() === '') {
      throw new Error('[MemoryStore] query cannot be empty when searching memories')
    }

    try {
      const { apiManager } = await import('@/services/api')
      const memoryApi = apiManager.getMemoryApi()

      return await memoryApi.searchMemories(workspaceId, query, filters.value)
    } catch (e: unknown) {
      error.value = e.message || 'Search failed'
      console.error('Search failed:', e)
      return []
    }
  }

  async function exportMemories(
    workspaceId: string,
    format: 'json' | 'csv' | 'ndjson'
  ): Promise<void> {
    // ✅ Fast Fail: 验证必需参数
    if (!workspaceId || workspaceId.trim() === '') {
      throw new Error('[MemoryStore] workspaceId cannot be empty when exporting memories')
    }
    const validFormats = ['json', 'csv', 'ndjson']
    if (!validFormats.includes(format)) {
      throw new Error(`[MemoryStore] Invalid format: ${format}. Valid formats: ${validFormats.join(', ')}`)
    }

    try {
      const { apiManager } = await import('@/services/api')
      const memoryApi = apiManager.getMemoryApi()

      const blob = await memoryApi.exportMemories(workspaceId, format, filters.value)

      // Create download link
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `memory-export-${new Date().toISOString().split('T')[0]}.${format}`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      URL.revokeObjectURL(url)
    } catch (e: unknown) {
      error.value = e.message || 'Export failed'
      console.error('Export failed:', e)
    }
  }

  async function importMemories(
    workspaceId: string,
    file: File,
    format: 'json' | 'csv' | 'ndjson'
  ): Promise<{ imported: number; errors: string[] } | null> {
    // ✅ Fast Fail: 验证必需参数
    if (!workspaceId || workspaceId.trim() === '') {
      throw new Error('[MemoryStore] workspaceId cannot be empty when importing memories')
    }
    if (!file) {
      throw new Error('[MemoryStore] file cannot be empty when importing memories')
    }
    const validFormats = ['json', 'csv', 'ndjson']
    if (!validFormats.includes(format)) {
      throw new Error(`[MemoryStore] Invalid format: ${format}. Valid formats: ${validFormats.join(', ')}`)
    }

    loading.value = true
    error.value = null

    try {
      const { apiManager } = await import('@/services/api')
      const memoryApi = apiManager.getMemoryApi()

      const result = await memoryApi.importMemories(workspaceId, file, format)

      // Reload memories
      await loadMemories(workspaceId)

      return result
    } catch (e: unknown) {
      error.value = e.message || 'Import failed'
      console.error('Import failed:', e)
      return null
    } finally {
      loading.value = false
    }
  }

  function setSelected(id: string | null) {
    selectedId.value = id
  }

  function setViewMode(mode: ViewMode) {
    viewMode.value = mode
  }

  function setFilters(newFilters: Partial<MemoryFilters>) {
    filters.value = { ...filters.value, ...newFilters }
  }

  function setSearchQuery(query: string) {
    searchQuery.value = query
  }

  function clearError() {
    error.value = null
  }

  function clearFilters() {
    filters.value = {
      type: 'all',
      onlyValid: true
    }
    searchQuery.value = ''
  }

  async function extractMemories(
    workspaceId: string
  ): Promise<{ success: boolean; extracted: number; method: string; details: string[]; message: string }> {
    if (!workspaceId || workspaceId.trim() === '') {
      throw new Error('[MemoryStore] workspaceId cannot be empty when extracting memories')
    }

    loading.value = true
    error.value = null

    try {
      const { apiManager } = await import('@/services/api')
      const memoryApi = apiManager.getMemoryApi()

      const result = await memoryApi.extractMemories(workspaceId)

      // Reload memories after extraction
      await loadMemories(workspaceId)
      await loadStats(workspaceId)

      return {
        success: result.success,
        extracted: result.extracted,
        method: result.method,
        details: result.details,
        message: result.message || ''
      }
    } catch (e: unknown) {
      error.value = e.message || 'Extract failed'
      console.error('Extract failed:', e)
      return {
        success: false,
        extracted: 0,
        method: 'error',
        details: [],
        message: e.message || 'Extract failed'
      }
    } finally {
      loading.value = false
    }
  }

  return {
    // State
    memories,
    selectedId,
    loading,
    error,
    viewMode,
    searchQuery,
    filters,
    stats,
    graphData,
    timelineData,

    // Getters
    selectedMemory,
    memoriesByType,
    filteredMemories,
    totalMemories,
    validMemories,
    archivedMemories,

    // Actions
    loadMemories,
    loadStats,
    loadGraphData,
    loadTimelineData,
    createMemory,
    updateMemory,
    deleteMemory,
    searchMemories,
    exportMemories,
    importMemories,
    extractMemories,
    setSelected,
    setViewMode,
    setFilters,
    setSearchQuery,
    clearError,
    clearFilters
  }
})
