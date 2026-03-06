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
} from '@/types/knowledge'
import { getApiBaseUrl } from '@/utils/platform'

const API_BASE = `${getApiBaseUrl()}/api/knowledge`

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
    const response = await axios.get(`${API_BASE}/bases/${baseId}`)
    return response.data
  },

  /**
   * 更新知识库
   */
  updateBase: async (baseId: string, data: KnowledgeBaseUpdate): Promise<KnowledgeBase> => {
    const response = await axios.put(`${API_BASE}/bases/${baseId}`, data)
    return response.data
  },

  /**
   * 删除知识库
   */
  deleteBase: async (baseId: string, force?: boolean): Promise<void> => {
    await axios.delete(`${API_BASE}/bases/${baseId}`, { params: { force } })
  },

  /**
   * 设置默认知识库
   */
  setDefaultBase: async (baseId: string): Promise<KnowledgeBase> => {
    const response = await axios.post(`${API_BASE}/bases/${baseId}/set-default`)
    return response.data
  },

  /**
   * 获取知识库统计
   */
  getBaseStats: async (baseId: string): Promise<any> => {
    const response = await axios.get(`${API_BASE}/bases/${baseId}/stats`)
    return response.data
  },
}

export const knowledgeApi = {
  /**
   * 列出指定知识库的文档
   */
  listDocuments: async (params?: { skip?: number; limit?: number }, baseId?: string) => {
    // 如果提供了baseId，使用该知识库；否则使用默认知识库
    const baseUrl = baseId ? `${API_BASE}/bases/${baseId}/documents` : `${API_BASE}/bases/default/documents`
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
    const baseUrl = baseId ? `${API_BASE}/bases/${baseId}/documents/${documentId}` : `${API_BASE}/bases/default/documents/${documentId}`
    const response = await axios.get(baseUrl)
    return response.data
  },

  /**
   * 删除文档
   */
  deleteDocument: async (documentId: string, baseId?: string) => {
    // 如果提供了baseId，使用该知识库；否则使用默认知识库
    const baseUrl = baseId ? `${API_BASE}/bases/${baseId}/documents/${documentId}` : `${API_BASE}/bases/default/documents/${documentId}`
    const response = await axios.delete(baseUrl)
    return response.data
  },

  /**
   * 重新索引文档
   */
  reindexDocument: async (documentId: string, baseId?: string) => {
    // 如果提供了baseId，使用该知识库；否则使用默认知识库
    const baseUrl = baseId ? `${API_BASE}/bases/${baseId}/documents/${documentId}/reindex` : `${API_BASE}/bases/default/documents/${documentId}/reindex`
    const response = await axios.post(baseUrl)
    return response.data
  },

  /**
   * 搜索知识库
   */
  search: async (request: SearchRequest, baseId?: string): Promise<SearchResponse> => {
    // 如果提供了baseId，搜索指定知识库；否则搜索默认知识库
    const baseUrl = baseId ? `${API_BASE}/bases/${baseId}/search` : `${API_BASE}/bases/default/search`
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
  }
}
