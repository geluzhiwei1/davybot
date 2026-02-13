/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * ConnectionStore - WebSocket连接管理（支持多Workspace隔离）
 *
 * 职责：
 * - 为每个workspace管理独立的WebSocket连接
 * - 连接、断开、重连逻辑
 * - 连接错误处理
 * - 防止workspace之间的数据串台
 */

import { ref, computed } from 'vue'
import { logger } from '@/utils/logger'

import { defineStore } from 'pinia'
import { WebSocketClientManager } from '@/services/websocket/manager'
import { ConnectionState } from '@/types/websocket'
import type { WebSocketConfig } from '@/types/websocket'
import { getWsBaseUrl } from '@/utils/platform'
import { useWorkspaceStore as _useWorkspaceStore } from './workspace'

// 导入workspace store
function useWorkspaceStore() {
  return _useWorkspaceStore()
}

// WebSocket配置 - 使用platform.ts中的URL配置
const getWebSocketConfig = (workspaceId: string): WebSocketConfig => ({
  url: getWsBaseUrl(),
  reconnectAttempts: 5,
  reconnectDelay: 3000,
  heartbeatInterval: 10000,
  messageTimeout: 30000,
  metadata: {
    workspaceId,
  }
})

export const useConnectionStore = defineStore('connection', () => {
  // --- State ---

  /**
   * 连接状态映射（按workspace）
   */
  const connectionStates = ref<Map<string, ConnectionState>>(new Map())

  /**
   * 最后连接时间映射（按workspace）
   */
  const lastConnectedTimes = ref<Map<string, string>>(new Map())

  /**
   * 连接错误信息映射（按workspace）
   */
  const errors = ref<Map<string, string | null>>(new Map())

  /**
   * 重连尝试次数映射（按workspace）
   */
  const reconnectAttemptsMap = ref<Map<string, number>>(new Map())

  /**
   * 标记是否已注册消息处理器（按workspace）
   */
  const handlersRegistered = ref<Set<string>>(new Set())

  /**
   * Session ID → Workspace ID 映射
   * 用于消息路由的fallback机制
   */
  const sessionToWorkspaceMap = ref<Map<string, string>>(new Map())

  // --- Getters ---

  /**
   * 获取指定workspace的连接状态
   */
  const getConnectionState = (workspaceId: string): ConnectionState => {
    return connectionStates.value.get(workspaceId) || ConnectionState.DISCONNECTED
  }

  /**
   * 获取当前workspace的连接状态
   */
  const currentConnectionStatus = computed((): ConnectionState => {
    const workspaceStore = useWorkspaceStore()
    const workspaceId = workspaceStore.currentWorkspaceId || 'default'
    return getConnectionState(workspaceId)
  })

  /**
   * 当前workspace是否已连接
   */
  const isConnected = computed(() => currentConnectionStatus.value === ConnectionState.CONNECTED)

  /**
   * 当前workspace是否正在连接
   */
  const isConnecting = computed(() => currentConnectionStatus.value === ConnectionState.CONNECTING)

  /**
   * 当前workspace的连接状态文本
   */
  const statusText = computed(() => {
    switch (currentConnectionStatus.value) {
      case ConnectionState.CONNECTED:
        return '已连接'
      case ConnectionState.CONNECTING:
        return '连接中'
      case ConnectionState.DISCONNECTED:
        return '未连接'
      case ConnectionState.ERROR:
        return '连接错误'
      default:
        return '未知'
    }
  })

  /**
   * 当前workspace的连接状态（别名，向后兼容）
   */
  const connectionStatus = computed(() => currentConnectionStatus.value)

  /**
   * 当前workspace的错误信息
   */
  const currentError = computed((): string | null => {
    const workspaceStore = useWorkspaceStore()
    const workspaceId = workspaceStore.currentWorkspaceId || 'default'
    return errors.value.get(workspaceId) || null
  })

  // --- Actions ---

  /**
   * 获取指定workspace的WebSocket客户端
   */
  const getClient = (workspaceId: string) => {
    const config = getWebSocketConfig(workspaceId)
    return WebSocketClientManager.getInstance(workspaceId, config)
  }

  /**
   * 获取当前workspace的WebSocket客户端
   */
  const getCurrentClient = (): unknown => {
    const workspaceStore = useWorkspaceStore()
    const workspaceId = workspaceStore.currentWorkspaceId || 'default'
    return getClient(workspaceId)
  }

  /**
   * 连接指定workspace的WebSocket
   */
  const connect = async (workspaceId?: string): Promise<void> => {
    const workspaceStore = useWorkspaceStore()
    const targetWorkspaceId = workspaceId || workspaceStore.currentWorkspaceId || 'default'

    try {
      logger.debug('[ConnectionStore] 🎯 Target workspace:', targetWorkspaceId)

      // ✅ 严格验证：workspace_id 必须有效
      if (!targetWorkspaceId || targetWorkspaceId === 'default' || targetWorkspaceId.trim() === '') {
        const error = new Error(`[ConnectionStore] ❌ FATAL: Invalid workspace_id: "${targetWorkspaceId}"`)
        logger.error('[ConnectionStore] Error:', error.message)
        console.error('[ConnectionStore] 🔍 Current workspace state:', {
          targetWorkspaceId,
          currentWorkspaceId: workspaceStore.currentWorkspaceId,
          allWorkspaces: 'N/A'  // 可以添加 workspace list
        })
                throw error  // ← FastFail: 无效的 workspace_id
      }

      // 清除错误和重置状态
      errors.value.set(targetWorkspaceId, null)
      reconnectAttemptsMap.value.set(targetWorkspaceId, 0)

      const wsClient = getClient(targetWorkspaceId)
      logger.debug('[ConnectionStore] ✅ WebSocket client obtained for workspace:', targetWorkspaceId)

      // 监听连接状态变化
      wsClient.on('stateChange', (status: ConnectionState) => {
        logger.debug(`[ConnectionStore] 🔄 State changed to: ${status}`)
        connectionStates.value.set(targetWorkspaceId, status)

        if (status === ConnectionState.CONNECTED) {
          lastConnectedTimes.value.set(targetWorkspaceId, new Date().toISOString())
          logger.debug(`[ConnectionStore] ✅ Connected at: ${lastConnectedTimes.value.get(targetWorkspaceId)}`)

          // ✅ 连接成功后，验证并注册 session_id
          const sessionId = wsClient.getSessionId()
          console.log('[ConnectionStore] 🔍 Client session_id:', {
            session_id: sessionId,
            session_id_length: sessionId?.length,
            session_id_prefix: sessionId?.substring(0, 20)
          })

          if (sessionId) {
            // ⚠️ 注意：这里注册的是前端的临时 session_id
            // 真正的映射会在 handleConnect 中用后端的 session_id 重新注册
            sessionToWorkspaceMap.value.set(sessionId, targetWorkspaceId)
            logger.debug(`[ConnectionStore] ✅ Pre-registered placeholder session→workspace: ${sessionId.substring(0, 8)}... → ${targetWorkspaceId}`)
            logger.debug('[ConnectionStore] 📊 Current mappings:', Object.fromEntries(sessionToWorkspaceMap.value))
          } else {
            const error = new Error('[ConnectionStore] ❌ FATAL: WebSocket client has no session_id after connection')
            logger.error('[ConnectionStore] Session error:', error.message)
            throw error  // ← FastFail: session_id 生成失败
          }
        } else if (status === ConnectionState.ERROR) {
          errors.value.set(targetWorkspaceId, '连接错误')
          logger.error(`[ConnectionStore] ❌ Connection error for workspace: ${targetWorkspaceId}`)
        }
      })

      // 监听错误
      wsClient.on('error', (err: Error) => {
        logger.error(`[ConnectionStore] ❌ Workspace ${targetWorkspaceId} error:`, err)
        errors.value.set(targetWorkspaceId, err.message)
      })

      logger.debug('[ConnectionStore] 🔄 Attempting to connect...')
      await wsClient.connect()

      logger.debug(`[ConnectionStore] ✅ Successfully connected workspace: ${targetWorkspaceId}`)
      
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : '连接失败'
      errors.value.set(targetWorkspaceId, errorMsg)
      connectionStates.value.set(targetWorkspaceId, ConnectionState.ERROR)
      logger.error(`[ConnectionStore] ❌ Failed to connect workspace ${targetWorkspaceId}:`, err)
            throw err
    }
  }

  /**
   * 断开指定workspace的WebSocket连接
   *
   * 注意: 这是一个清理操作，采用"best-effort"策略
   * 即使某些步骤失败，我们也会尝试执行所有清理步骤
   * 因此catch块只记录错误而不重新抛出
   */
  const disconnect = (workspaceId?: string): void => {
    const workspaceStore = useWorkspaceStore()
    const targetWorkspaceId = workspaceId || workspaceStore.currentWorkspaceId || 'default'

    // ✅ Fast Fail: 验证 workspaceId
    if (!targetWorkspaceId || targetWorkspaceId === 'default' || targetWorkspaceId.trim() === '') {
      const error = new Error(`[ConnectionStore] Invalid workspace_id for disconnect: "${targetWorkspaceId}"`)
      logger.error(error.message)
      throw error  // disconnect 应该验证参数
    }

    try {
      logger.debug(`[ConnectionStore] Disconnecting workspace: ${targetWorkspaceId}`)

      // 清除session映射
      const sessionId = getSessionId(targetWorkspaceId)
      if (sessionId) {
        sessionToWorkspaceMap.value.delete(sessionId)
        logger.debug(`[ConnectionStore] Cleared session→workspace mapping for session: ${sessionId}`)
      }

      WebSocketClientManager.disconnect(targetWorkspaceId)
      connectionStates.value.set(targetWorkspaceId, ConnectionState.DISCONNECTED)
      lastConnectedTimes.value.delete(targetWorkspaceId)
      errors.value.delete(targetWorkspaceId)
      reconnectAttemptsMap.value.delete(targetWorkspaceId)
      handlersRegistered.value.delete(targetWorkspaceId)
    } catch (err) {
      // ⚠️ 清理操作使用 best-effort 策略
      // 记录错误但不重新抛出，确保所有清理步骤都执行
      logger.error(`[ConnectionStore] Error during disconnect cleanup for ${targetWorkspaceId}:`, err)
    }
  }

  /**
   * 断开所有workspace的连接
   */
  const disconnectAll = (): void => {
    logger.debug('[ConnectionStore] Disconnecting all workspaces')
    WebSocketClientManager.disconnectAll()
    connectionStates.value.clear()
    lastConnectedTimes.value.clear()
    errors.value.clear()
    reconnectAttemptsMap.value.clear()
    handlersRegistered.value.clear()
    sessionToWorkspaceMap.value.clear()  // 清除所有session映射
  }

  /**
   * 获取指定workspace的SessionId
   */
  const getSessionId = (workspaceId?: string): string => {
    const targetWorkspaceId = workspaceId || useWorkspaceStore().currentWorkspaceId || 'default'
    const client = WebSocketClientManager.getInstance(targetWorkspaceId, getWebSocketConfig(targetWorkspaceId))
    return client.getSessionId()
  }

  /**
   * 根据session_id获取workspace_id（用于消息路由的fallback）
   */
  const getWorkspaceIdBySession = (sessionId: string): string | undefined => {
    return sessionToWorkspaceMap.value.get(sessionId)
  }

  /**
   * 更新session→workspace映射
   */
  const updateSessionMapping = (sessionId: string, workspaceId: string): void => {
    // ✅ Fast Fail: 验证参数
    if (!sessionId || sessionId.trim() === '') {
      throw new Error('[ConnectionStore] sessionId cannot be empty when updating session mapping')
    }
    if (!workspaceId || workspaceId.trim() === '' || workspaceId === 'default') {
      throw new Error(`[ConnectionStore] Invalid workspace_id for session mapping: "${workspaceId}"`)
    }

    sessionToWorkspaceMap.value.set(sessionId, workspaceId)
    logger.debug(`[ConnectionStore] Updated session→workspace mapping: ${sessionId} → ${workspaceId}`)
  }

  /**
   * 页面刷新或关闭时清理所有连接
   */
  const cleanup = (): void => {
    disconnectAll()
  }

  /**
   * 初始化WebSocket连接并设置事件监听器
   * @param handlers 消息处理器映射
   * @param safeMessageHandler 安全消息处理器包装器
   */
  const initializeWithHandlers = (
    handlers: Record<string, (message: unknown) => void>,
    safeMessageHandler: (name: string, handler: (message: unknown) => void) => (message: unknown) => void
  ): void => {
    const workspaceStore = useWorkspaceStore()
    const workspaceId = workspaceStore.currentWorkspaceId || 'default'

    // 检查是否已注册
    if (handlersRegistered.value.has(workspaceId)) {
      logger.debug(`[ConnectionStore] Handlers already registered for workspace: ${workspaceId}`)
      return
    }

    logger.debug(`[ConnectionStore] Initializing handlers for workspace: ${workspaceId}`)

    const wsClient = getClient(workspaceId)

    // 注册所有消息处理器
    Object.entries(handlers).forEach(([messageType, handler]) => {
      const safeHandler = safeMessageHandler(messageType, handler)
      wsClient.onMessage(messageType as unknown, safeHandler)
    })

    // 标记已注册
    handlersRegistered.value.add(workspaceId)

    logger.debug(`[ConnectionStore] Handlers registered for workspace: ${workspaceId}`)
  }

  /**
   * 发送WebSocket消息
   * @param message 要发送的消息
   */
  const send = async (message: unknown): Promise<void> => {
    const workspaceStore = useWorkspaceStore()
    const workspaceId = workspaceStore.currentWorkspaceId || 'default'

    const wsClient = getClient(workspaceId)

    if (wsClient && wsClient.state && wsClient.state.value === 'connected') {
      // Validate that message has a type field
      if (!message.type) {
        logger.error('[ConnectionStore] Message missing type field:', message)
        throw new Error('Message must have a type field')
      }

      // Extract the type and create payload without the type field
      // to avoid double-wrapping and field conflicts
      const { type, ...payload } = message
      await wsClient.send(type, payload)
    } else {
      logger.error(`[ConnectionStore] Cannot send message - workspace ${workspaceId} not connected`)
      throw new Error(`Workspace ${workspaceId} not connected`)
    }
  }

  // --- 返回store接口 ---

  return {
    // State
    connectionStates,
    lastConnectedTimes,
    errors,
    reconnectAttemptsMap,
    handlersRegistered,
    sessionToWorkspaceMap,  // Session→Workspace映射

    // Getters
    currentConnectionStatus,
    connectionStatus,
    isConnected,
    isConnecting,
    statusText,
    currentError,

    // Actions
    getClient,
    getCurrentClient,
    connect,
    disconnect,
    disconnectAll,
    getSessionId,
    getWorkspaceIdBySession,  // 新增：根据session获取workspace
    updateSessionMapping,     // 新增：更新session映射
    cleanup,
    initializeWithHandlers,
    send,
  }
})
