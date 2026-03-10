/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * 现代化WebSocket客户端
 *
 * 特性：
 * - 完全类型安全的消息通信
 * - 自动重连机制（指数退避）
 * - 心跳检测
 * - 消息队列（离线时缓存）
 * - 事件订阅系统
 * - 性能监控
 */

import { ref, computed, onUnmounted } from 'vue'

import { ElMessage } from 'element-plus'
import { logger } from '@/utils/logger'
import type {
  MessagePayloadMap,
  WebSocketConfig,
  MessageHandler,
  Unsubscribe,
  WebSocketEvent,
  WebSocketEventMap,
} from './types'

import { MessageRouter, globalRouter } from './router'

export * from './types'
export { MessageBuilder } from './builder'
export { MessageRouter, globalRouter } from './router'

/**
 * WebSocket客户端类
 */
export class WebSocketClient {
  private ws: WebSocket | null = null
  private config: Required<WebSocketConfig & { metadata?: { workspaceId?: string; [key: string]: unknown } }>
  private router = new MessageRouter()

  // 状态
  private _state = ref<ConnectionState>('disconnected')
  private _sessionId = ref<string>(this.generateSessionId())
  private _reconnectCount = ref(0)
  private _lastError = ref<Error | null>(null)

  // Workspace标识
  private readonly workspaceId: string

  // 定时器
  private heartbeatTimer: number | null = null
  private reconnectTimer: number | null = null
  private connectionTimeoutTimer: number | null = null

  // 消息队列（离线时缓存）
  private messageQueue: WebSocketMessage[] = []
  private maxQueueSize = 100

  // 事件监听器
  private eventListeners = new Map<WebSocketEvent, Set<() => unknown>>()

  // 性能监控
  private metrics = {
    messagesSent: 0,
    messagesReceived: 0,
    bytesSent: 0,
    bytesReceived: 0,
    connectionTime: 0,
    lastHeartbeatTime: 0,
  }

  // ==================== 单例支持 ====================
  private static instance: WebSocketClient | null = null

  /**
   * 获取单例实例
   */
  static getInstance(config?: WebSocketConfig): WebSocketClient {
    if (!WebSocketClient.instance) {
      if (!config) {
        throw new Error('WebSocket configuration is required for first initialization')
      }
      WebSocketClient.instance = new WebSocketClient(config)
    }
    return WebSocketClient.instance
  }

  /**
   * 重置单例（用于测试或重新配置）
   */
  static resetInstance(): void {
    if (WebSocketClient.instance) {
      WebSocketClient.instance.disconnect()
      WebSocketClient.instance = null
    }
  }

  constructor(config: WebSocketConfig & { metadata?: { workspaceId?: string; [key: string]: unknown } }) {
    this.config = {
      url: config.url,
      reconnectAttempts: config.reconnectAttempts ?? 5,
      reconnectDelay: config.reconnectDelay ?? 3000,
      heartbeatInterval: config.heartbeatInterval ?? 30000,
      messageTimeout: config.messageTimeout ?? 30000,
      connectionTimeout: config.connectionTimeout ?? 10000,
      metadata: config.metadata || {}
    }

    // 提取workspaceId
    this.workspaceId = config.metadata?.workspaceId || 'default'

    logger.debug(`[WebSocketClient] Initialized for workspace: ${this.workspaceId}`)

    // 从sessionStorage恢复sessionId（按workspace隔离）
    this.restoreSessionId()
  }

  // ==================== 公共API ====================

  /**
   * 连接WebSocket
   */
  async connect(): Promise<void> {
    if (this._state.value === 'connected' || this._state.value === 'connecting') {
      logger.debug('[WebSocketClient] Already connected or connecting, skipping duplicate connect call')
      return
    }

    logger.debug('[WebSocketClient] Starting connection to:', this.config.url)
    this._state.value = 'connecting'
    this.emit('connect')

    try {
      await this.createConnection()
      await this.waitForConnection()
      this._state.value = 'connected'
      this._reconnectCount.value = 0
      this.startHeartbeat()
      this.flushMessageQueue()
      this.emit('stateChange', this._state.value)
      logger.success('WebSocket connected successfully')
    } catch (error) {
      this._state.value = 'error'
      this._lastError.value = error as Error
      this.handleConnectionError(error as Error)
      this.emit('stateChange', this._state.value)
      throw error
    }
  }

  /**
   * 断开连接
   */
  disconnect(): void {
    this.stopHeartbeat()
    this.clearTimers()

    if (this.ws) {
      this.ws.close(1000, 'Manual disconnect')
      this.ws = null
    }

    this._state.value = 'disconnected'
    this.emit('disconnect', { code: 1000, reason: 'Manual disconnect' })
    this.emit('stateChange', this._state.value)
    logger.info('WebSocket disconnected')
  }

  /**
   * 发送消息（类型安全）
   */
  async send<T extends MessageType>(
    type: T,
    payload: MessagePayloadMap[T]
  ): Promise<void> {
    // 创建符合后端期望的消息结构，不使用 payload 包装
    const message: unknown = {
      id: this.generateId(),
      type,
      timestamp: new Date().toISOString(),
      session_id: this._sessionId.value,
      ...payload  // 将 payload 字段展开到消息顶层
    }

    await this.sendMessage(message)
  }

  /**
   * 订阅消息
   */
  onMessage<T extends MessageType>(type: T, handler: MessageHandler<T>): Unsubscribe {
    return this.router.on(type, handler)
  }

  /**
   * 订阅所有消息
   */
  onAny(handler: (message: WebSocketMessage) => void): Unsubscribe {
    return this.router.onAny(handler)
  }

  /**
   * 发送用户消息
   */
  async sendUserMessage(
    content: string,
    metadata?: unknown,
    userUIContext?: unknown,
    knowledgeBaseIds?: string[]
  ): Promise<void> {
    // Create user message with knowledge base IDs
    const message: Record<string, unknown> = {
       id: this.generateId(),
       timestamp: new Date().toISOString(),
       type: 'user_message',
       session_id: this._sessionId.value,
       content,
       metadata,
       user_ui_context: userUIContext
    };

    // Add knowledge base IDs if provided
    if (knowledgeBaseIds && knowledgeBaseIds.length > 0) {
      message.knowledge_base_ids = knowledgeBaseIds;
    }

    // Send message directly
    await this.sendMessage(message);
  }

  /**
   * 发送心跳
   */
  async sendHeartbeat(): Promise<void> {
    // 创建符合后端 HeartbeatMessage 结构的消息
    const message = {
       id: this.generateId(),
       timestamp: new Date().toISOString(),
       type: 'ws_heartbeat',
       session_id: this._sessionId.value,
       message: 'ping'
    };
    
    // 直接发送消息对象，不使用 payload 包装
    await this.sendMessage(message);
  }

  /**
   * 订阅事件
   */
  on<E extends WebSocketEvent>(
    event: E,
    handler: (payload: WebSocketEventMap[E]) => void
  ): Unsubscribe {
    if (!this.eventListeners.has(event)) {
      this.eventListeners.set(event, new Set())
    }

    this.eventListeners.get(event)!.add(handler)

    return () => {
      const listeners = this.eventListeners.get(event)
      if (listeners) {
        listeners.delete(handler)
        if (listeners.size === 0) {
          this.eventListeners.delete(event)
        }
      }
    }
  }

  // ==================== 状态查询 ====================

  get state() {
    return computed(() => this._state.value)
  }

  get sessionId() {
    return computed(() => this._sessionId.value)
  }

  /**
   * 获取会话ID值
   */
  getSessionId(): string {
    return this._sessionId.value
  }

  /**
   * 设置会话ID（用于同步后端生成的值）
   *
   * @param sessionId - 后端生成的 session_id
   */
  setSessionId(sessionId: string): void {
    const oldSessionId = this._sessionId.value

    logger.debug('[WebSocketClient] 🔧 setSessionId called:', {
      old_session_id: oldSessionId,
      new_session_id: sessionId,
      workspace_id: this.workspaceId,
      needs_update: oldSessionId !== sessionId
    })

    if (oldSessionId === sessionId) {
      logger.debug('[WebSocketClient] ℹ️ SessionId unchanged, skipping update')
      return
    }

    // ✅ 更新 session_id
    this._sessionId.value = sessionId

    // ✅ 持久化到 sessionStorage
    this.saveSessionId()
  }

  /**
   * 保存会话ID到sessionStorage（公共方法）
   */
  saveSessionIdToStorage(): void {
    this.saveSessionId()
  }

  get reconnectCount() {
    return computed(() => this._reconnectCount.value)
  }

  get lastError() {
    return computed(() => this._lastError.value)
  }

  get isConnected() {
    return computed(() => this._state.value === 'connected')
  }

  get isConnecting() {
    return computed(() => this._state.value === 'connecting')
  }

  getMetrics() {
    return this.metrics
  }

  // ==================== 私有方法 ====================

  /**
   * 创建WebSocket连接
   */
  private async createConnection(): Promise<void> {
    return new Promise((resolve, reject) => {
      try {
        this.ws = new WebSocket(this.config.url)
        this.setupEventHandlers()

        // 连接超时
        this.connectionTimeoutTimer = window.setTimeout(() => {
          if (this.ws?.readyState === WebSocket.CONNECTING) {
            this.ws.close()
            reject(new Error('Connection timeout'))
          }
        }, this.config.connectionTimeout)

        resolve()
      } catch {
        reject(error)
      }
    })
  }

  /**
   * 等待连接建立
   */
  private waitForConnection(): Promise<void> {
    return new Promise((resolve, reject) => {
      if (!this.ws) return reject(new Error('WebSocket not initialized'))

      const onOpen = () => {
        this.ws?.removeEventListener('open', onOpen)
        this.ws?.removeEventListener('error', onError)
        resolve()
      }

      const onError = () => {
        this.ws?.removeEventListener('open', onOpen)
        this.ws?.removeEventListener('error', onError)
        reject(new Error('Connection failed'))
      }

      this.ws.addEventListener('open', onOpen)
      this.ws.addEventListener('error', onError)
    })
  }

  /**
   * 设置WebSocket事件处理器
   */
  private setupEventHandlers(): void {
    if (!this.ws) return

    this.ws.onopen = () => {
      this.clearConnectionTimeout()
      logger.debug('[WebSocket] Connection opened')
    }

    this.ws.onmessage = (event) => {
      this.handleMessage(event.data)
    }

    this.ws.onclose = (event) => {
      this.clearConnectionTimeout()
      this.handleDisconnect(event.code, event.reason, event.wasClean)
    }

    this.ws.onerror = (error) => {
      this.clearConnectionTimeout()
      logger.error('[WebSocket] Error:', error)
    }
  }

  /**
   * 处理接收到的消息
   */
  private async handleMessage(data: string): Promise<void> {
    try {
      const message = JSON.parse(data) as WebSocketMessage

      // 更新性能指标
      this.metrics.messagesReceived++
      this.metrics.bytesReceived += data.length

      // 路由消息到本地处理器
      await this.router.dispatch(message)

      // 同步路由到全局路由器（用于 parallelTasks 等全局处理器）
      try {
        await globalRouter.dispatch(message)
      } catch {
        logger.error('Error in global router handler', error, { messageType: message.type })

        // Report to error monitoring
        const errorMonitoring = (await import('@/utils/errorMonitoring')).errorMonitoring
        errorMonitoring.recordError(error as Error, {
          component: 'globalRouter',
          messageType: message.type
        })

        // Fast fail: ALL message processing failures should be surfaced
        // Create typed error for better handling
        const dispatchError = new Error(`Failed to dispatch ${message.type} message`)
        dispatchError.name = 'WebSocketDispatchError'
        ;(dispatchError as unknown).cause = error
        ;(dispatchError as unknown).messageType = message.type

        // Notify user for visible failures
        if (message.type === 'error' || message.type === 'stream_complete') {
          ElMessage.error('处理关键消息时发生错误')
        }

        throw dispatchError  // Always re-throw for fast fail
      }

      // 触发消息事件
      this.emit('message', message)
    } catch {
      logger.error('Failed to handle message', error, { messageType: message?.type })
      throw error  // Re-throw for upper layer handling
    }
  }

  /**
   * 发送消息（内部方法）
   */
  private async sendMessage(message: WebSocketMessage): Promise<void> {
    if (this._state.value !== 'connected') {
      // 离线时加入队列
      this.queueMessage(message)
      return
    }

    try {
      const data = JSON.stringify(message)
      this.ws!.send(data)

      // 更新性能指标
      this.metrics.messagesSent++
      this.metrics.bytesSent += data.length

      // 调试日志：追踪每条消息（忽略心跳消息以减少日志噪音）
      if (message.type !== 'ws_heartbeat') {
        logger.debug('[WebSocket] Sent:', message.type, message.id)
      }
    } catch {
      logger.error('[WebSocket] Failed to send message:', error)
      throw error
    }
  }

  /**
   * 将消息加入队列
   */
  private queueMessage(message: WebSocketMessage): void {
    if (this.messageQueue.length >= this.maxQueueSize) {
      // 队列满时，移除最旧的消息
      this.messageQueue.shift()
    }

    this.messageQueue.push(message)
    // 调试日志：追踪每条消息（忽略心跳消息以减少日志噪音）
    if (message.type !== 'ws_heartbeat') {
      logger.debug('[WebSocket] Queued message:', message.type)
    }
  }

  /**
   * 发送队列中的所有消息
   */
  private flushMessageQueue(): void {
    if (this.messageQueue.length === 0) return

    logger.debug(`[WebSocket] Flushing ${this.messageQueue.length} queued messages`)

    const messages = [...this.messageQueue]
    this.messageQueue = []

    messages.forEach(message => {
      this.sendMessage(message).catch(error => {
        logger.error('[WebSocket] Failed to send queued message:', error)
      })
    })
  }

  /**
   * 处理连接错误
   */
  private handleConnectionError(error: Error): void {
    logger.error('[WebSocket] Connection error:', error)
    this.emit('error', error)

    // 尝试重连，并向用户明确通知重连状态
    if (this._reconnectCount.value < this.config.reconnectAttempts) {
      this.scheduleReconnect()

      // 明确通知用户正在重连
      ElMessage.warning({
        message: `连接失败，正在尝试重连 (${this._reconnectCount.value}/${this.config.reconnectAttempts})...`,
        duration: 3000,
        showClose: true
      })
    } else {
      // Fast fail: 达到最大重试次数后明确失败
      logger.error('[WebSocket] Max reconnection attempts reached')
      ElMessage.error({
        message: '连接失败，请检查网络设置或刷新页面',
        duration: 5000,
        showClose: true
      })
      this.emit('fatalError', error)
    }
  }

  /**
   * 处理断开连接
   */
  private handleDisconnect(code: number, reason: string, wasClean: boolean): void {
    logger.debug('[WebSocket] Disconnected:', { code, reason, wasClean })

    this._state.value = 'disconnected'
    this.stopHeartbeat()
    this.emit('disconnect', { code, reason })
    this.emit('stateChange', this._state.value)

    // 如果非正常断开，尝试重连并向用户通知
    if (!wasClean || code !== 1000) {
      if (this._reconnectCount.value < this.config.reconnectAttempts) {
        this.scheduleReconnect()

        // 通知用户正在重连
        ElMessage.warning({
          message: `连接断开，正在尝试重连 (${this._reconnectCount.value}/${this.config.reconnectAttempts})...`,
          duration: 3000,
          showClose: true
        })
      } else {
        // 达到最大重试次数
        ElMessage.error({
          message: '连接断开，无法自动重连，请刷新页面',
          duration: 5000,
          showClose: true
        })
      }
    }
  }

  /**
   * 安排重连（指数退避）
   */
  private scheduleReconnect(): void {
    this._state.value = 'reconnecting'
    this._reconnectCount.value++
    this.emit('stateChange', this._state.value)

    const delay = Math.min(
      this.config.reconnectDelay * Math.pow(2, this._reconnectCount.value - 1),
      30000
    )

    logger.debug(`[WebSocket] Reconnecting in ${delay}ms (attempt ${this._reconnectCount.value})`)

    this.reconnectTimer = window.setTimeout(() => {
      this.connect().catch(error => {
        logger.error('[WebSocket] Reconnection failed:', error)
      })
    }, delay)
  }

  /**
   * 开始心跳
   */
  private startHeartbeat(): void {
    this.heartbeatTimer = window.setInterval(() => {
      if (this._state.value === 'connected') {
        this.sendHeartbeat()
      }
    }, this.config.heartbeatInterval)
  }

  /**
   * 停止心跳
   */
  private stopHeartbeat(): void {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer)
      this.heartbeatTimer = null
    }
  }

  /**
   * 清除定时器
   */
  private clearTimers(): void {
    if (this.heartbeatTimer) clearInterval(this.heartbeatTimer)
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer)
    if (this.connectionTimeoutTimer) clearTimeout(this.connectionTimeoutTimer)

    this.heartbeatTimer = null
    this.reconnectTimer = null
    this.connectionTimeoutTimer = null
  }

  /**
   * 清除连接超时
   */
  private clearConnectionTimeout(): void {
    if (this.connectionTimeoutTimer) {
      clearTimeout(this.connectionTimeoutTimer)
      this.connectionTimeoutTimer = null
    }
  }

  /**
   * 触发事件
   */
  private emit<E extends WebSocketEvent>(
    event: E,
    payload?: WebSocketEventMap[E]
  ): void {
    const listeners = this.eventListeners.get(event)
    if (listeners) {
      listeners.forEach(handler => {
        try {
          handler(payload as unknown)
        } catch {
          logger.error(`[WebSocket] Error in ${event} handler:`, error)
        }
      })
    }
  }

  /**
   * 生成消息ID
   */
  private generateId(): string {
    return `msg_${Date.now()}_${Math.random().toString(36).substring(2, 11)}`
  }

  /**
   * 生成会话ID
   */
  private generateSessionId(): string {
    return `session_${Date.now()}_${Math.random().toString(36).substring(2, 11)}`
  }

  /**
   * 保存会话ID到sessionStorage
   */
  private saveSessionId(): void {
    try {
      const key = `ws_session_id_${this.workspaceId}`
      sessionStorage.setItem(key, this._sessionId.value)
      logger.debug(`[WebSocketClient] Saved sessionId for workspace ${this.workspaceId}: ${this._sessionId.value}`)
    } catch {
      logger.warn('[WebSocketClient] Failed to save session ID:', error)
    }
  }

  /**
   * 从sessionStorage恢复会话ID（按workspace隔离）
   */
  private restoreSessionId(): void {
    try {
      const key = `ws_session_id_${this.workspaceId}`
      const saved = sessionStorage.getItem(key)
      if (saved) {
        this._sessionId.value = saved
        logger.debug(`[WebSocketClient] Restored sessionId for workspace ${this.workspaceId}: ${saved}`)
      }
    } catch {
      // Fast fail（针对隐私模式等严重问题）
      if (error instanceof Error && error.name === 'SecurityError') {
        logger.error('[WebSocketClient] ❌ Cannot access sessionStorage (privacy mode?)')
        logger.warn('[WebSocketClient] Session restoration unavailable, will generate new session_id')
        // 显示一次性提示
        ElMessage.warning({
          message: '会话恢复功能不可用（隐私模式），可能影响使用体验',
          duration: 3000,
          showClose: true
        })
      } else {
        logger.warn('[WebSocketClient] Failed to restore session ID:', error)
      }
      // 不抛出错误，允许继续连接（使用新生成的 session_id）
    }
  }
}

/**
 * 创建WebSocket客户端composable
 */
export function useWebSocket(config: WebSocketConfig) {
  const client = new WebSocketClient(config)

  // 组件卸载时自动断开
  onUnmounted(() => {
    client.disconnect()
  })

  return client
}

/**
 * 导出单例客户端（可选）
 */
let defaultClient: WebSocketClient | null = null

export const initWebSocket = (config: WebSocketConfig) => {
  if (!defaultClient) {
    defaultClient = new WebSocketClient(config)
  }
  return defaultClient
}

export const getWebSocket = () => {
  if (!defaultClient) {
    throw new Error('WebSocket client not initialized. Call initWebSocket first.')
  }
  return defaultClient
}

// ==================== 兼容 api/index.ts 的便捷函数 ====================

/**
 * 获取 WebSocket 单例客户端（兼容 api/websocket.ts）
 * @param config 可选配置，仅在首次调用时需要
 */
export const getWebSocketClient = (config?: WebSocketConfig): WebSocketClient => {
  return WebSocketClient.getInstance(config)
}

/**
 * 创建 WebSocket 客户端（兼容 api/websocket.ts）
 */
export const createWebSocketClient = (config?: WebSocketConfig): WebSocketClient => {
  return WebSocketClient.getInstance(config)
}

/**
 * 初始化 WebSocket 客户端（兼容 api/websocket.ts）
 */
export const initWebSocketClient = (config: WebSocketConfig): WebSocketClient => {
  return WebSocketClient.getInstance(config)
}

