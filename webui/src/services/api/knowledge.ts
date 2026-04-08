/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/** 知识库API服务 */

import axios from 'axios'
import type {
  DocumentInfo,
  SearchRequest,
  SearchResponse,
  RAGQueryResponse,
  Stats,
  KnowledgeSettings,
  KnowledgeBase,
  KnowledgeBaseCreate,
  KnowledgeBaseUpdate,
  KnowledgeBaseListResponse,
  DomainSchema,
  EntitySource,
  DomainOption,
} from '@/types/knowledge'
import { getApiBaseUrl } from '@/utils/platform'

const API_BASE = `${getApiBaseUrl()}/knowledge`

export const knowledgeBasesApi = {
  /**
   * 列出所有知识库
   */
  listBases: async (params?: { workspace_id?: string; status?: string }): Promise<KnowledgeBaseListResponse> => {
    const response = await axios.get(`${API_BASE}/bases`, { params })
    return response.data
  },

  /**
   * 创建知识库
   */
  createBase: async (data: KnowledgeBaseCreate): Promise<KnowledgeBase> => {
    const response = await axios.post(`${API_BASE}/bases`, data)
    return response.data
  },

  /**
   * 获取默认知识库
   */
  getDefaultBase: async (): Promise<KnowledgeBase> => {
    const response = await axios.get(`${API_BASE}/bases/default`)
    return response.data
  },

  /**
   * 获取知识库详情
   */
  getBase: async (baseId: string): Promise<KnowledgeBase> => {
    const response = await axios.get(`${API_BASE}/bases/by-id/${baseId}`)
    return response.data
  },

  /**
   * 更新知识库
   */
  updateBase: async (baseId: string, data: KnowledgeBaseUpdate): Promise<KnowledgeBase> => {
    const response = await axios.put(`${API_BASE}/bases/by-id/${baseId}`, data)
    return response.data
  },

  /**
   * 删除知识库
   */
  deleteBase: async (baseId: string, force?: boolean): Promise<void> => {
    await axios.delete(`${API_BASE}/bases/by-id/${baseId}`, { params: { force } })
  },

  /**
   * 设置默认知识库
   */
  setDefaultBase: async (baseId: string): Promise<KnowledgeBase> => {
    const response = await axios.post(`${API_BASE}/bases/by-id/${baseId}/set-default`)
    return response.data
  },

  /**
   * 获取知识库统计
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  getBaseStats: async (baseId: string): Promise<any> => {
    const response = await axios.get(`${API_BASE}/bases/by-id/${baseId}/stats`)
    return response.data
  },

  /**
   * 获取图谱实体
   */
  getGraphEntities: async (baseId: string, params?: {
    limit?: number
    offset?: number
    entity_type?: string
  }) => {
    const response = await axios.get(`${API_BASE}/bases/by-id/${baseId}/graph/entities`, { params })
    return response.data
  },

  /**
   * 获取图谱关系
   */
  getGraphRelations: async (baseId: string, params?: {
    limit?: number
    offset?: number
    relation_type?: string
  }) => {
    const response = await axios.get(`${API_BASE}/bases/by-id/${baseId}/graph/relations`, { params })
    return response.data
  },

  /**
   * 获取实体来源信息
   */
  getEntitySources: async (baseId: string, entityId: string) => {
    const response = await axios.get(`${API_BASE}/bases/by-id/${baseId}/graph/entities/${entityId}/sources`)
    return response.data
  },

  /**
   * 扫描目录文件
   */
  scanDir: async (baseId: string, dirPath?: string) => {
    const params: Record<string, string> = {}
    if (dirPath) params.dir_path = dirPath
    const response = await axios.get(`${API_BASE}/bases/by-id/${baseId}/scan-dir`, { params })
    return response.data
  },

  /**
   * 磨扫描目录（不需要知识库ID，用于创建前预览）
   */
  scanDirStandalone: async (dirPath: string, recursive: boolean = true) => {
    const params: Record<string, unknown> = { dir_path: dirPath, recursive }
    const response = await axios.get(`${API_BASE}/bases/scan-dir`, { params })
    return response.data
  },

  /**
   * 从目录同步文件到知识库（后台任务，立即返回 task_id）
   */
  syncFromDir: async (baseId: string, params?: { dir_path?: string; force_rebuild?: boolean }): Promise<{ task_id: string; base_id: string; status: string; message: string }> => {
    const response = await axios.post(`${API_BASE}/bases/by-id/${baseId}/sync-from-dir`, null, {
      params,
    })
    return response.data
  },

  /**
   * 获取知识库同步任务状态（通过 base_id）
   */
  getSyncStatus: async (baseId: string): Promise<{
    base_id: string
    status: string
    task_id: string | null
    progress?: number
    current_file?: string
    total_files?: number
    processed_files?: number
    result?: Record<string, unknown>
    error?: string
  }> => {
    const response = await axios.get(`${API_BASE}/bases/by-id/${baseId}/sync-status`)
    return response.data
  },
}

export const knowledgeApi = {
  /**
   * 列出指定知识库的文档
   */
  listDocuments: async (params?: { skip?: number; limit?: number }, baseId?: string) => {
    // 如果提供了baseId，使用该知识库；否则使用默认知识库
    const baseUrl = baseId ? `${API_BASE}/bases/by-id/${baseId}/documents` : `${API_BASE}/bases/by-id/default/documents`
    const response = await axios.get(baseUrl, { params })
    return response.data
  },

  /**
   * 上传文档
   */
  uploadDocument: async (file: File) => {
    const formData = new FormData()
    formData.append('file', file)

    const response = await axios.post(`${API_BASE}/documents/upload`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    })
    return response.data
  },

  /**
   * 获取文档详情
   */
  getDocument: async (documentId: string, baseId?: string) => {
    // 如果提供了baseId，使用该知识库；否则使用默认知识库
    const baseUrl = baseId ? `${API_BASE}/bases/by-id/${baseId}/documents/${documentId}` : `${API_BASE}/bases/by-id/default/documents/${documentId}`
    const response = await axios.get(baseUrl)
    return response.data
  },

  /**
   * 删除文档
   */
  deleteDocument: async (documentId: string, baseId?: string) => {
    // 如果提供了baseId，使用该知识库；否则使用默认知识库
    const baseUrl = baseId ? `${API_BASE}/bases/by-id/${baseId}/documents/${documentId}` : `${API_BASE}/bases/by-id/default/documents/${documentId}`
    const response = await axios.delete(baseUrl)
    return response.data
  },

  /**
   * 重新索引文档
   */
  reindexDocument: async (documentId: string, baseId?: string) => {
    // 如果提供了baseId，使用该知识库；否则使用默认知识库
    const baseUrl = baseId ? `${API_BASE}/bases/by-id/${baseId}/documents/${documentId}/reindex` : `${API_BASE}/bases/by-id/default/documents/${documentId}/reindex`
    const response = await axios.post(baseUrl)
    return response.data
  },

  /**
   * 搜索知识库
   */
  search: async (request: SearchRequest, baseId?: string): Promise<SearchResponse> => {
    // 如果提供了baseId，搜索指定知识库；否则搜索默认知识库
    const baseUrl = baseId ? `${API_BASE}/bases/by-id/${baseId}/search` : `${API_BASE}/bases/by-id/default/search`
    const response = await axios.post(baseUrl, null, {
      params: {
        query: request.query,
        mode: request.mode || 'hybrid',
        top_k: request.top_k || 5
      }
    })
    return response.data
  },

  /**
   * RAG查询
   */
  ragQuery: async (query: string, maxContextLength?: number): Promise<RAGQueryResponse> => {
    const response = await axios.post(`${API_BASE}/rag/query`, null, {
      params: {
        query,
        max_context_length: maxContextLength || 4000
      }
    })
    return response.data
  },

  /**
   * 获取统计数据
   */
  getStats: async (): Promise<Stats> => {
    const response = await axios.get(`${API_BASE}/stats`)
    return response.data
  },

  /**
   * 更新设置
   */
  updateSettings: async (settings: KnowledgeSettings) => {
    const response = await axios.post(`${API_BASE}/settings`, settings)
    return response.data
  },

  /**
   * 获取设置
   */
  getSettings: async (): Promise<KnowledgeSettings> => {
    const response = await axios.get(`${API_BASE}/settings`)
    return response.data
  },

  /**
   * 健康检查
   */
  healthCheck: async () => {
    const response = await axios.get(`${API_BASE}/health`)
    return response.data
  },

  /**
   * List available domains
   */
  listDomains: async (): Promise<DomainOption[]> => {
    const response = await axios.get(`${API_BASE}/domains`)
    const data = response.data
    const raw = Array.isArray(data) ? data : data.domains ?? []
    return raw.map((d: { name: string; display_name?: string; description?: string }) => ({
      value: d.name,
      label: d.display_name ?? d.name,
      description: d.description,
    }))
  },

  /**
   * Get domain schema
   */
  getDomainSchema: async (domain: string): Promise<DomainSchema> => {
    const response = await axios.get(`${API_BASE}/domains/${domain}/schema`)
    return response.data
  },

  /**
   * Get entity sources for a domain
   */
  getEntitySources: async (domain: string): Promise<EntitySource[]> => {
    const response = await axios.get(`${API_BASE}/domains/${domain}/entity-sources`)
    return response.data
  },

  /**
   * List available LLM configs for knowledge extraction
   */
  listLLMConfigs: async (): Promise<{ success: boolean; configs: Array<{ llm_id: string; model_id: string }> }> => {
    const response = await axios.get(`${API_BASE}/bases/llm-configs`)
    return response.data
  }
}
