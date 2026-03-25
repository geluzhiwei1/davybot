/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * WorkspaceStore - Workspace和Conversation管理
 *
 * 职责：
 * - Workspace管理
 * - Conversation管理
 * - 会话状态管理
 */

import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import { v4 as uuidv4 } from 'uuid'
import { apiManager } from '@/services/api'
import { logger } from '@/utils/logger'
import { ElMessage } from 'element-plus'
import type { Workspace, Conversation } from '@/services/api/types'
import { useMessageStore } from './messages'

export const useWorkspaceStore = defineStore('workspace', () => {
  // --- State ---

  /**
   * 当前Workspace ID
   */
  const currentWorkspaceId = ref<string | null>(null)

  /**
   * 当前Conversation ID
   */
  const currentConversationId = ref<string | null>(null)

  /**
   * Workspace列表
   */
  const workspaceList = ref<Workspace[]>([])

  /**
   * Conversation列表
   */
  const conversationList = ref<Conversation[]>([])

  /**
   * 消息分页状态
   */
  const messagePagination = ref({
    hasMore: false,
    total: 0,
    loaded: 0
  })

  /**
   * 正在加载更多消息
   */
  const isLoadingMore = ref<boolean>(false)

  // --- Getters ---

  /**
   * 当前Workspace
   */
  const currentWorkspace = computed(() => {
    if (!currentWorkspaceId.value) return null
    return workspaceList.value.find(w => w.id === currentWorkspaceId.value) || null
  })

  /**
   * 当前Conversation
   */
  const currentConversation = computed(() => {
    if (!currentConversationId.value) return null
    return conversationList.value.find(c => c.id === currentConversationId.value) || null
  })

  // --- Actions ---

  /**
   * 设置Workspace
   */
  const setWorkspace = async (workspaceId: string): Promise<void> => {
    currentWorkspaceId.value = workspaceId
    // 注意：conversations 由 SidePanel 组件自己管理加载,这里不需要重复加载
  }

  /**
   * 设置Conversation (支持多会话切换,不影响Agent运行)
   */
  const setConversation = (conversationId: string): void => {
    const oldConversationId = currentConversationId.value

    // 更新当前会话ID
    currentConversationId.value = conversationId

    // 清除该会话的后台通知 (用户正在查看)
    if (oldConversationId && oldConversationId !== conversationId) {
      const messageStore = useMessageStore()
      messageStore.clearBackgroundNotification(conversationId)

      logger.debug(`[WorkspaceStore] Switched conversation: ${oldConversationId} -> ${conversationId}`)
    }
  }

  /**
   * 创建Workspace
   */
  const createWorkspace = async (name: string): Promise<unknown> => {
    try {
      const workspace = await apiManager.getWorkspacesApi().createWorkspace({ name, path: name })
      workspaceList.value.push(workspace)
      await setWorkspace(workspace.id)
      return workspace
    } catch (error) {
      logger.error('Failed to create workspace', error)
      ElMessage.error('创建工作区失败')
      throw error // Fast fail - re-throw for caller to handle
    }
  }

  /**
   * 从用户消息生成会话标题
   */
  const generateConversationTitle = (userMessage: string): string => {
    // 移除首尾空白
    const trimmed = userMessage.trim()

    // 如果消息很短（≤20字符），直接使用
    if (trimmed.length <= 20) {
      return trimmed
    }

    // 提取前30个字符作为标题
    const title = trimmed.substring(0, 30)

    // 如果在第30个字符之前有句子结束符（。！？.!?），在那里截断
    const sentenceEnd = title.search(/[。！？.!?\n]/)
    if (sentenceEnd !== -1 && sentenceEnd > 5) {
      return title.substring(0, sentenceEnd)
    }

    // 否则添加省略号
    return title + '...'
  }

  /**
   * 更新会话标题
   */
  const updateConversationTitle = async (conversationId: string, title: string): Promise<void> => {
    try {
      if (!currentWorkspaceId.value) {
        throw new Error('No workspace selected')
      }

      // 使用后端API更新会话（POST /workspaces/{workspaceId}/conversations/{conversationId}）
      await apiManager.getWorkspacesApi().updateConversation(
        currentWorkspaceId.value,
        conversationId,
        { title }
      )

      // 重新加载会话列表以确保同步
      await loadConversations(currentWorkspaceId.value)
    } catch (error) {
      logger.error('[WORKSPACE_STORE] Failed to update conversation title:', error)
      throw error
    }
  }

  /**
   * 创建Conversation
   */
  const createConversation = async (title: string): Promise<unknown> => {
    try {
      if (!currentWorkspaceId.value) {
        throw new Error('No workspace selected')
      }

      // ✅ 使用 workspaces API 创建会话
      // 后端期望一个会话数组，每个会话需要包含完整的结构
      const now = new Date().toISOString()
      const conversationId = uuidv4()
      const conversationData = [{
        id: conversationId,
        title: title,
        created_at: now,
        updated_at: now,
        messages: [],
        message_count: 0,
        task_type: 'user',
        metadata: {}
      }]

      const response = await apiManager.getWorkspacesApi().createConversation(
        currentWorkspaceId.value,
        conversationData
      )

      // 后端返回的是保存结果，需要从数据中提取会话信息
      const newConversation = {
        id: conversationId,
        title: title,
        createdAt: now,
        updatedAt: now,
        lastUpdated: now
      }

      conversationList.value.push(newConversation)
      await setConversation(newConversation.id)
      return newConversation
    } catch (error) {
      logger.error('Failed to create conversation', error)
      ElMessage.error('创建会话失败')
      throw error // Fast fail - re-throw for caller to handle
    }
  }

  /**
   * 加载Workspace列表
   */
  const loadWorkspaces = async (): Promise<void> => {
    try {
      const workspaces = await apiManager.getWorkspacesApi().getWorkspaces()
      workspaceList.value = workspaces
    } catch (error) {
      logger.error('Failed to load workspaces', error)
      ElMessage.error('加载工作区失败，请刷新页面重试')
      throw error // Fast fail - re-throw to prevent silent failure
    }
  }

  /**
   * 加载Conversation列表
   */
  const loadConversations = async (workspaceId: string): Promise<void> => {
    try {
      // 使用和 SidePanel 相同的 API 方法，避免路径错误
      const response = await apiManager.getWorkspacesApi().getConversations(workspaceId) as unknown
      // Backend returns {items: [...]}
      conversationList.value = response.items || []

      // 如果有会话列表且当前没有选中会话，自动选择最近的一次对话
      if (conversationList.value.length > 0 && !currentConversationId.value) {
        const sortedConversations = [...conversationList.value].sort((a, b) => {
          const dateA = new Date(a.updated_at || a.created_at || 0)
          const dateB = new Date(b.updated_at || b.created_at || 0)
          return dateB.getTime() - dateA.getTime()
        })
        const latestConversation = sortedConversations[0]
        logger.debug(`Auto-selecting latest conversation: ${latestConversation.title || latestConversation.name}`)
        currentConversationId.value = latestConversation.id
      }
    } catch (error) {
      logger.error('Failed to load conversations', error)
      ElMessage.error('加载会话列表失败，请刷新重试')
      throw error // Fast fail - re-throw to prevent silent failure
    }
  }

  /**
   * 清空当前会话
   */
  const clearCurrentConversation = (): void => {
    currentConversationId.value = null
  }

  /**
   * 加载历史会话消息（支持渐进式分页加载）
   * @param conversationId 会话ID
   * @param convertBackendMessage 消息转换函数 (从message store传入)
   * @param options 加载选项
   * @returns 转换后的消息数组
   */
  const loadConversation = async (
    conversationId: string,
    convertBackendMessage: (backendMsg: unknown) => unknown,
    options?: {
      skip?: number
      limit?: number
      append?: boolean
    }
  ): Promise<unknown[]> => {
    const INITIAL_MESSAGE_LIMIT = 50
    const skip = options?.skip ?? 0
    const limit = options?.limit ?? INITIAL_MESSAGE_LIMIT

    logger.debug(`[WORKSPACE_STORE] loadConversation called with ID: ${conversationId}`)
    logger.debug(`[WORKSPACE_STORE] Pagination: skip=${skip}, limit=${limit}`)
    logger.debug(`[WORKSPACE_STORE] currentWorkspaceId: ${currentWorkspaceId.value}`)

    // Check if this is a temporary conversation
    if (conversationId && conversationId.startsWith('temp_')) {
      logger.debug('[WORKSPACE_STORE] Temporary conversation detected, skipping API load')
      return []
    }

    if (!currentWorkspaceId.value) {
      logger.error('[WORKSPACE_STORE] No workspace ID set')
      throw new Error('未设置工作区ID，无法加载会话')
    }

    try {
      logger.debug('[WORKSPACE_STORE] Calling API getConversationById with pagination...')
      const response = await apiManager.getWorkspacesApi().getConversationById(
        currentWorkspaceId.value,
        conversationId,
        {
          skip,
          limit,
          include_metadata: skip === 0,
          order: 'desc'  // 默认加载最新消息
        }
      )
      logger.debug('[WORKSPACE_STORE] API response:', response)
      if (!response.success || !response.conversation) {
        logger.error('[WORKSPACE_STORE] Failed to load conversation:', response.message)
        throw new Error(`加载会话失败: ${response.message || '未知错误'}`)
      }

      const conversation = response.conversation
      logger.debug('[WORKSPACE_STORE] Conversation data:', conversation)
      // 首次加载时设置当前会话ID
      if (skip === 0) {
        currentConversationId.value = conversationId
        logger.debug(`[WORKSPACE_STORE] Set currentConversationId to: ${conversationId}`)
      }

      // 更新分页状态
      if (conversation.pagination) {
        messagePagination.value = {
          hasMore: conversation.pagination.hasMore,
          total: conversation.pagination.total,
          loaded: conversation.pagination.skip + conversation.pagination.returned
        }
        logger.debug('[WORKSPACE_STORE] Updated pagination:', messagePagination.value)
      }

      // 转换消息
      const loadedMessages: unknown[] = []
      for (const msg of conversation.messages || []) {
        const chatMessage = convertBackendMessage(msg)
        if (chatMessage) {
          loadedMessages.push(chatMessage)
        }
      }

      logger.debug(`[WORKSPACE_STORE] Converted ${loadedMessages.length} messages`)

      // 首次加载时触发元数据相关事件
      if (skip === 0 && conversation.metadata) {
        // 如果会话metadata中包含graph_id，触发加载任务图
        if (conversation.metadata.graph_id) {
          const event = new CustomEvent('load-task-graph', {
            detail: { graphId: conversation.metadata.graph_id }
          })
          window.dispatchEvent(event)
          logger.debug(`[WORKSPACE_STORE] Dispatched load-task-graph event for graph ${conversation.metadata.graph_id}`)
        }
      }

      return loadedMessages
    } catch (error) {
      logger.error('[WORKSPACE_STORE] Error loading conversation:', error)
      throw new Error(`加载会话失败: ${error instanceof Error ? error.message : String(error)}`)
    }
  }

  /**
   * 加载更多消息（渐进式加载）
   *
   * @param conversationId Conversation ID
   * @param convertBackendMessage 消息转换函数
   * @returns 新加载的消息数组
   */
  const loadMoreMessages = async (
    conversationId: string,
    convertBackendMessage: (backendMsg: unknown) => unknown
  ): Promise<unknown[]> => {
    if (isLoadingMore.value) {
      logger.warn('[WORKSPACE_STORE] Already loading more messages, ignoring request')
      return []
    }

    if (!messagePagination.value.hasMore) {
      logger.debug('[WORKSPACE_STORE] No more messages to load')
      return []
    }

    isLoadingMore.value = true
    logger.debug(`[WORKSPACE_STORE] Loading more messages... Loaded: ${messagePagination.value.loaded}, Total: ${messagePagination.value.total}`)

    try {
      const newMessages = await loadConversation(
        conversationId,
        convertBackendMessage,
        {
          skip: messagePagination.value.loaded,
          limit: 50,
          append: true
        }
      )

      logger.debug(`[WORKSPACE_STORE] Loaded ${newMessages.length} more messages`)
      return newMessages
    } finally {
      isLoadingMore.value = false
    }
  }

  // --- 返回store接口 ---

  return {
    // State
    currentWorkspaceId,
    currentConversationId,
    workspaceList,
    conversationList,
    messagePagination,
    isLoadingMore,

    // Getters
    currentWorkspace,
    currentConversation,

    // Actions
    setWorkspace,
    setConversation,
    createWorkspace,
    createConversation,
    generateConversationTitle,
    updateConversationTitle,
    loadWorkspaces,
    loadConversations,
    clearCurrentConversation,
    loadConversation,
    loadMoreMessages,
  }
})
