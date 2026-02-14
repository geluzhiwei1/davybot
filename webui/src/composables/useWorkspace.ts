/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * 工作区状态管理 Composable
 *
 * 提供工作区生命周期管理、状态同步和持久化功能
 * 对应后端的 UserWorkspace 重构
 */

import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { apiManager } from '@/services/api'
import type {
  Workspace,
  WorkspaceSettings,
  UserUIContext
} from '@/services/api/types'

export interface WorkspaceState {
  currentWorkspace: Workspace | null
  workspacePath: string | null
  workspaceId: string | null
  conversationId: string | null
  isTempConversation: boolean
  uiContext: UserUIContext
  systemEnvironments: unknown
  isInitialized: boolean
  isLoading: boolean
  error: string | null
}

export function useWorkspace() {
  // 状态
  const state = ref<WorkspaceState>({
    currentWorkspace: null,
    workspacePath: null,
    workspaceId: null,
    conversationId: null,
    isTempConversation: false,
    uiContext: {
      open_files: [],
      active_applications: [],
      user_preferences: {},
      current_file: null,
      current_selected_content: null,
      current_mode: 'ask',
      current_llm_id: null,
      conversation_id: null
    },
    systemEnvironments: null,
    isInitialized: false,
    isLoading: false,
    error: null
  })

  // 计算属性
  const currentWorkspace = computed(() => state.value.currentWorkspace)
  const workspaceId = computed(() => state.value.workspaceId)
  const conversationId = computed(() => state.value.conversationId)
  const isTempConversation = computed(() => state.value.isTempConversation)
  const uiContext = computed(() => state.value.uiContext)
  const isInitialized = computed(() => state.value.isInitialized)
  const isLoading = computed(() => state.value.isLoading)
  const error = computed(() => state.value.error)

  /**
   * 初始化工作区
   */
  const initializeWorkspace = async (workspaceId: string) => {
    if (state.value.isLoading) {
      console.warn('[useWorkspace] Workspace initialization already in progress')
      return
    }

    state.value.isLoading = true
    state.value.error = null

    try {
      // 调用API获取工作区信息
      const response = await apiManager.workspaces.getWorkspace(workspaceId)

      if (!response.success || !response.data) {
        throw new Error(response.message || 'Failed to load workspace')
      }

      const workspace = response.data

      // 更新状态
      state.value.currentWorkspace = workspace
      state.value.workspaceId = workspace.id
      state.value.workspacePath = workspace.path
      state.value.isInitialized = true

      return workspace
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Unknown error'
      state.value.error = errorMessage
      console.error('[useWorkspace] ✗ Initialization failed:', errorMessage)
      throw err
    } finally {
      state.value.isLoading = false
    }
  }

  /**
   * 更新工作区设置
   */
  const updateWorkspaceSettings = async (settings: Partial<WorkspaceSettings>) => {
    if (!state.value.workspaceId) {
      console.warn('[useWorkspace] Cannot update settings: no workspace loaded')
      return
    }

    try {
      const response = await apiManager.workspaces.updateWorkspaceSettings(
        state.value.workspaceId,
        settings
      )

      if (response.success && state.value.currentWorkspace) {
        // 更新本地状态
        state.value.currentWorkspace.settings = {
          ...state.value.currentWorkspace.settings,
          ...settings
        }
      }
    } catch (err) {
      console.error('[useWorkspace] ✗ Failed to update settings:', err)
      throw err
    }
  }

  /**
   * 更新UI上下文
   */
  const updateUIContext = async (updates: Partial<UserUIContext>) => {
    const oldContext = { ...state.value.uiContext }
    state.value.uiContext = {
      ...state.value.uiContext,
      ...updates,
      conversation_id: state.value.conversationId
    }

    // 如果工作区已加载，保存到后端
    if (state.value.workspaceId) {
      try {
        await apiManager.workspaces.updateUIContext(
          state.value.workspaceId,
          state.value.uiContext
        )
      } catch (err) {
        const error = err instanceof Error ? err : new Error(String(err))
        console.error('[useWorkspace] Failed to save UI context:', error)

        // Fast fail: 向用户显示错误通知
        ElMessage.error('保存 UI 设置失败，请检查网络连接')

        // 重新抛出错误，让调用者决定如何处理
        throw error
      }
    }
  }

  /**
   * 设置当前对话
   */
  const setConversation = async (conversationId: string | null, isTemp: boolean = false) => {
    const oldConversationId = state.value.conversationId

    state.value.conversationId = conversationId
    state.value.isTempConversation = isTemp

    // 更新UI上下文中的conversation_id
    if (conversationId) {
      await updateUIContext({ conversation_id: conversationId })
    }
  }

  /**
   * 创建新对话
   */
  const createConversation = async (title?: string) => {
    if (!state.value.workspaceId) {
      throw new Error('Cannot create conversation: no workspace loaded')
    }

    try {
      const response = await apiManager.workspaces.createConversation(
        state.value.workspaceId,
        { title }
      )

      if (response.success && response.data) {
        const newConversation = response.data
        await setConversation(newConversation.id, false)

        return newConversation
      }

      throw new Error(response.message || 'Failed to create conversation')
    } catch (err) {
      console.error('[useWorkspace] ✗ Failed to create conversation:', err)
      throw err
    }
  }

  /**
   * 加载历史对话
   */
  const loadConversation = async (conversationId: string) => {
    if (!state.value.workspaceId) {
      throw new Error('Cannot load conversation: no workspace loaded')
    }

    try {
      const response = await apiManager.workspaces.getConversation(
        state.value.workspaceId,
        conversationId
      )

      if (response.success && response.data) {
        await setConversation(conversationId, false)

        return response.data
      }

      throw new Error(response.message || 'Failed to load conversation')
    } catch (err) {
      console.error('[useWorkspace] ✗ Failed to load conversation:', err)
      throw err
    }
  }

  /**
   * 清理工作区状态
   */
  const cleanup = () => {
    state.value.currentWorkspace = null
    state.value.workspacePath = null
    state.value.workspaceId = null
    state.value.conversationId = null
    state.value.isTempConversation = false
    state.value.isInitialized = false
    state.value.error = null

    // 重置UI上下文但保留基本结构
    state.value.uiContext = {
      open_files: [],
      active_applications: [],
      user_preferences: {},
      current_file: null,
      current_selected_content: null,
      current_mode: 'ask',
      current_llm_id: null,
      conversation_id: null
    }
  }

  /**
   * 重置为临时对话
   */
  const resetToTempConversation = () => {
    state.value.conversationId = null
    state.value.isTempConversation = true

    // 清除UI上下文中的conversation_id
    updateUIContext({ conversation_id: null })
  }

  // 监听工作区变化，自动同步UI上下文
  watch(
    () => state.value.uiContext,
    (newContext) => {
      // 可以在这里添加自动保存逻辑
      // 但要避免频繁调用，建议使用防抖
    },
    { deep: true }
  )

  return {
    // 状态
    state,

    // 计算属性
    currentWorkspace,
    workspaceId,
    conversationId,
    isTempConversation,
    uiContext,
    isInitialized,
    isLoading,
    error,

    // 方法
    initializeWorkspace,
    updateWorkspaceSettings,
    updateUIContext,
    setConversation,
    createConversation,
    loadConversation,
    cleanup,
    resetToTempConversation
  }
}

// 导出类型
export type WorkspaceComposable = ReturnType<typeof useWorkspace>
