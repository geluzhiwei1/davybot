/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * ChatStore - 主聊天Store (组合式架构)
 *
 * 职责：
 * - 组合5个专门stores
 * - 提供向后兼容的API
 * - 协调各store之间的交互
 */

import { watch, computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { v4 as uuidv4 } from 'uuid'
import { ElMessage } from 'element-plus'
import type { ChatMessage, WebSocketMessage } from '@/types/websocket'
import { MessageType, ContentType, MessageRole } from '@/types/websocket'
import { errorMonitoring } from '@/utils/errorMonitoring'
import { logger } from '@/utils/logger'
import { resolveWorkspaceId } from '@/utils/workspaceResolver'
import { createWorkspaceMap } from '@/utils/workspaceState'

// 导入专门stores
import { useConnectionStore } from './connection'
import { useMessageStore } from './messages'
import { useAgentStore } from './agent'
import { useTaskStore } from './task'
import { useWorkspaceStore } from './workspace'
import { useParallelTasksStore } from './parallelTasks'
import { useTodoStore } from './todoStore'

// 导入map类型以支持fallback机制


export const useChatStore = defineStore('chat', () => {
  // --- 组合专门stores ---

  const connectionStore = useConnectionStore()
  const messageStore = useMessageStore()
  const agentStore = useAgentStore()
  const taskStore = useTaskStore()
  const workspaceStore = useWorkspaceStore()
  const parallelTasksStore = useParallelTasksStore()
  const todoStore = useTodoStore()

  // --- Local State (按workspace隔离) ---

  /**
   * UI 上下文状态类型定义
   */
  interface UIContextState {
    openFiles: string[]
    currentFile: string | null
    currentMode: string | null
    currentLlmId: string | null
    userPreferences: Record<string, unknown>
  }

  /**
   * LLM API 交互状态类型定义
   */
  interface LlmApiState {
    isActive: boolean
    provider: string
    model: string
    requestType: string
    startTime: number | null
    responseContent: string
  }

  // ✅ 使用通用 workspace 状态工具（遵循 DRY 原则）
  const [, getUIContext] = createWorkspaceMap<UIContextState>(() => ({
    openFiles: [],
    currentFile: null,
    currentMode: 'build',
    currentLlmId: null,
    userPreferences: {}
  }))

  const [, getLlmApiStatus] = createWorkspaceMap<LlmApiState>(() => ({
    isActive: false,
    provider: '',
    model: '',
    requestType: '',
    startTime: null,
    responseContent: ''
  }))

  /**
   * 获取当前workspace的UI上下文状态
   */
  const getCurrentUIContext = () => {
    const workspaceId = workspaceStore.currentWorkspaceId || 'default'
    return getUIContext(workspaceId)
  }

  /**
   * 获取当前workspace的LLM API状态
   */
  const getCurrentLlmApiStatus = () => {
    const workspaceId = workspaceStore.currentWorkspaceId || 'default'
    return getLlmApiStatus(workspaceId)
  }

  /**
   * UI上下文状态（计算属性，自动使用当前workspace）
   */
  const uiContext = computed(() => getCurrentUIContext())

  /**
   * LLM API交互状态（计算属性，自动使用当前workspace）
   */
  const llmApiStatus = computed(() => getCurrentLlmApiStatus())

  // --- Computed (代理到专门stores) ---

  const connectionStatus = computed(() => connectionStore.connectionStatus)
  const isConnected = computed(() => connectionStore.isConnected)
  const messages = computed(() => messageStore.messages)
  const isThinking = computed(() => agentStore.isThinking)
  const currentTaskId = computed(() => agentStore.currentTaskId)
  const currentWorkspaceId = computed(() => workspaceStore.currentWorkspaceId)
  const currentConversationId = computed(() => workspaceStore.currentConversationId)
  const isTempConversation = computed(() => workspaceStore.isTempConversation)
  const currentThinking = computed(() => messageStore.currentThinking)
  const sessionId = computed(() => connectionStore.getSessionId())
  const workspaceId = computed(() => workspaceStore.currentWorkspaceId)
  const thinkingSteps = computed(() => messageStore.thinkingSteps)
  const agentStatus = computed(() => agentStore.agentStatus)

  // --- Actions ---

  // --- Private State ---

  /**
   * 标记是否已初始化连接
   */
  let isConnectionInitialized = false

  /**
   * 记录正在处理的消息ID（防止重复处理）
   */
  const processingMessages = new Set<string>()

  /**
   * 初始化WebSocket连接并设置事件监听器
   */
  const initializeConnection = () => {
    // 防止重复初始化
    if (isConnectionInitialized) {
      return
    }
    isConnectionInitialized = true

    // 创建消息处理器映射
    const handlers: Record<MessageType, (message: WebSocketMessage) => void> = {
      // 基础消息
      [MessageType.USER_MESSAGE]: handleUserMessage,
      [MessageType.ASSISTANT_MESSAGE]: handleAssistantMessage,
      [MessageType.SYSTEM_MESSAGE]: handleSystemMessage,
      [MessageType.CONNECT]: handleConnect,
      [MessageType.CONVERSATION_INFO]: handleConversationInfo,

      // 任务节点管理
      [MessageType.TASK_NODE_START]: taskStore.handleTaskNodeStart,
      [MessageType.TASK_NODE_PROGRESS]: handleTaskNodeProgressForChat,
      [MessageType.TASK_NODE_COMPLETE]: taskStore.handleTaskNodeComplete,
      [MessageType.TASK_STATUS_UPDATE]: taskStore.handleTaskStatusUpdate,
      [MessageType.TASK_GRAPH_UPDATE]: taskStore.handleTaskGraphUpdate,
      [MessageType.TODO_UPDATE]: handleTodoUpdate,

      // 流式消息
      [MessageType.STREAM_REASONING]: handleStreamReasoning,
      [MessageType.STREAM_CONTENT]: handleStreamContent,
      [MessageType.STREAM_TOOL_CALL]: handleStreamToolCall,
      [MessageType.STREAM_COMPLETE]: handleStreamComplete,

      // 工具调用
      [MessageType.TOOL_CALL_START]: handleToolCallStart,
      [MessageType.TOOL_CALL_PROGRESS]: handleToolCallProgress,
      [MessageType.TOOL_CALL_RESULT]: handleToolCallResult,

      // 追问问题
      [MessageType.FOLLOWUP_QUESTION]: handleFollowupQuestion,

      // LLM API
      [MessageType.LLM_API_REQUEST]: handleLLMApiRequest,
      [MessageType.LLM_API_RESPONSE]: handleLLMApiResponse,
      [MessageType.LLM_API_COMPLETE]: handleLLMApiComplete,
      [MessageType.LLM_API_ERROR]: handleLLMApiError,

      // Agent状态
      [MessageType.AGENT_START]: agentStore.handleAgentStart,
      [MessageType.AGENT_MODE_SWITCH]: agentStore.handleAgentModeSwitch,
      [MessageType.AGENT_THINKING]: agentStore.handleAgentThinking,
      [MessageType.AGENT_COMPLETE]: agentStore.handleAgentComplete,
      [MessageType.AGENT_PAUSE]: agentStore.handleAgentPaused,
      [MessageType.AGENT_RESUME]: agentStore.handleAgentResumed,
      [MessageType.AGENT_STOP]: agentStore.handleAgentStopped,

      // A2UI
      [MessageType.A2UI_SERVER_EVENT]: handleA2UIServerEvent,
      [MessageType.A2UI_USER_ACTION]: handleA2UIUserAction,

      // 错误
      [MessageType.ERROR]: handleError,
    }

    // 使用connection store初始化
    connectionStore.initializeWithHandlers(handlers, safeMessageHandler)
  }

  /**
   * 发送用户消息
   */
  const sendMessage = (text: string, knowledgeBaseIds?: string[]) => {
    if (!isConnected.value) {
      logger.error('WebSocket is not connected.')
      return
    }

    const userMessage: ChatMessage = {
      id: uuidv4(),
      role: MessageRole.USER,
      timestamp: new Date().toISOString(),
      content: [{ type: ContentType.TEXT, text }],
    }
    messageStore.addMessage(userMessage, workspaceStore.currentWorkspaceId)

    agentStore.setThinking(true)
    messageStore.setThinking('')
    messageStore.clearStreamingContent()

    // 构建metadata
    const metadata: Record<string, unknown> = {}
    if (currentWorkspaceId.value) {
      metadata.workspaceId = currentWorkspaceId.value
    }
    if (currentConversationId.value) {
      metadata.conversationId = currentConversationId.value
    }

    // 构建用户UI上下文
    const userUIContext: Record<string, unknown> = {}
    if (uiContext.value.openFiles.length > 0) {
      userUIContext.open_files = uiContext.value.openFiles
    }
    if (uiContext.value.currentFile) {
      userUIContext.current_file = uiContext.value.currentFile
    }
    if (uiContext.value.currentMode) {
      userUIContext.current_mode = uiContext.value.currentMode
    }
    if (uiContext.value.currentLlmId) {
      userUIContext.current_llm_id = uiContext.value.currentLlmId
    }
    if (Object.keys(uiContext.value.userPreferences).length > 0) {
      userUIContext.user_preferences = uiContext.value.userPreferences
    }

    // 【调试】记录即将发送给 WebSocket 的 knowledgeBaseIds
    console.log('[CHAT_STORE.sendMessage] Sending to WebSocket with knowledgeBaseIds:', knowledgeBaseIds);

    // 发送消息（使用当前workspace的客户端）
    const workspaceId = workspaceStore.currentWorkspaceId || 'default'
    connectionStore.getClient(workspaceId).sendUserMessage(
      text,
      metadata,
      userUIContext,
      knowledgeBaseIds
    ).catch(err => {
      logger.error('Failed to send message:', err)
      messageStore.addMessage({
        id: uuidv4(),
        role: MessageRole.SYSTEM,
        timestamp: new Date().toISOString(),
        content: [{ type: ContentType.ERROR, message: '消息发送失败' }],
      })
      agentStore.setThinking(false)
    })
  }

  /**
   * 发送任意类型的WebSocket消息
   */
  const sendWebSocketMessage = async (message: unknown) => {
    if (!isConnected.value) {
      logger.error('WebSocket is not connected.')
      throw new Error('WebSocket is not connected')
    }

    try {
      await connectionStore.send(message)
    } catch (error) {
      logger.error('[CHAT_STORE] Failed to send WebSocket message:', error)
      throw error
    }
  }

  /**
   * 设置当前工作区ID
   */
  const setWorkspaceId = (workspaceId: string) => {
    workspaceStore.setWorkspace(workspaceId)
  }

  /**
   * 更新UI上下文
   */
  const updateUIContext = (updates: Partial<{
    openFiles: string[];
    currentFile: string | null;
    currentMode: string | null;
    currentLlmId: string | null;
    userPreferences: Record<string, unknown>;
  }>) => {
    const currentContext = getCurrentUIContext()

    if (updates.openFiles !== undefined) {
      currentContext.openFiles = updates.openFiles
    }
    if (updates.currentFile !== undefined) {
      currentContext.currentFile = updates.currentFile
    }
    if (updates.currentMode !== undefined) {
      currentContext.currentMode = updates.currentMode
    }
    if (updates.currentLlmId !== undefined) {
      currentContext.currentLlmId = updates.currentLlmId
    }
    if (updates.userPreferences !== undefined) {
      currentContext.userPreferences = { ...currentContext.userPreferences, ...updates.userPreferences }
    }

    logger.debug('[CHAT_STORE] UI Context updated:', currentContext)
  }

  /**
   * 清空聊天记录
   */
  const clearChat = () => {
    messageStore.clearMessages()
    taskStore.clearTaskGraph()
    workspaceStore.clearCurrentConversation()
    messageStore.setThinking('')
    messageStore.clearStreamingContent()
  }

  /**
   * 设置临时会话
   */
  const setTempConversation = (conversationId: string) => {
    workspaceStore.setConversation(conversationId)
    // isTempConversation会在setConversation中设置为false，所以这里不需要额外设置
  }

  /**
   * 加载历史会话
   */
  const loadConversation = async (conversationId: string) => {
    try {
      // 标记正在加载，避免 watch 重复触发
      isLoadingConversation = true

      // 使用workspace store加载会话
      const loadedMessages = await workspaceStore.loadConversation(
        conversationId,
        messageStore.convertBackendMessageToChatMessage
      )

      // 清空当前消息
      messageStore.clearMessages()

      // 添加加载的消息
      messageStore.addMessages(loadedMessages)

      logger.debug(`[CHAT_STORE] Successfully loaded ${loadedMessages.length} messages`)
    } catch (error) {
      logger.error('[CHAT_STORE] Error loading conversation:', error)
      messageStore.addMessage({
        id: uuidv4(),
        role: MessageRole.SYSTEM,
        timestamp: new Date().toISOString(),
        content: [{
          type: ContentType.ERROR,
          message: `加载会话失败: ${error instanceof Error ? error.message : String(error)}`
        }],
      }, workspaceStore.currentWorkspaceId)  // 添加 workspaceId
    } finally {
      // 恢复加载标志
      setTimeout(() => {
        isLoadingConversation = false
      }, 100)
    }
  }

  /**
   * Agent控制方法
   */

  /**
   * 创建适配器函数,将 (type, payload) 转换为完整消息对象
   * 用于 agentStore 的 *Async 方法,它们期望的 sendFunc 签名是 (type, payload) => Promise<void>
   */
  const createSendAdapter = () => {
    return async (type: MessageType, payload: unknown): Promise<void> => {
      const message = {
        type,
        ...payload
      }
      await connectionStore.send(message)
    }
  }

  const stopAgent = async (taskId: string) => {
    await agentStore.stopAgentAsync(taskId, createSendAdapter())
  }

  // --- Private Message Handlers ---

  /**
   * 创建安全的消息处理器
   */
  const safeMessageHandler = (
    handlerName: string,
    handler: (message: WebSocketMessage) => void
  ) => {
    return (message: WebSocketMessage) => {
      try {
        handler(message)
      } catch (error) {
        logger.error(`[${handlerName}] Error processing message:`, error)
        logger.error(`[${handlerName}] Message that caused error:`, message)

        // 从原始消息中提取 session_id
        const sessionId = (message as unknown).session_id

        messageStore.addMessage({
          id: uuidv4(),
          role: MessageRole.SYSTEM,
          timestamp: new Date().toISOString(),
          sessionId: sessionId,  // 添加 session_id
          content: [{
            type: ContentType.ERROR,
            message: `消息处理错误 (${handlerName}): ${error instanceof Error ? error.message : String(error)}`
          }],
        })
      }
    }
  }

  const handleUserMessage = (message: WebSocketMessage) => {
    if (message.type !== MessageType.USER_MESSAGE) return
    logger.debug('User message received:', message)
  }

  const handleAssistantMessage = (message: WebSocketMessage) => {
    if (message.type !== MessageType.ASSISTANT_MESSAGE) return
    const assistantMessage = message as unknown
    if (!assistantMessage.task_id) return

    agentStore.setThinking(false)
    const chatMessage = messageStore.getOrCreateAssistantMessage(assistantMessage.task_id)

    const textBlock = chatMessage.content.find(
      c => c.type === ContentType.TEXT
    )

    if (textBlock) {
      (textBlock as unknown).text += assistantMessage.content
    } else {
      chatMessage.content.push({
        type: ContentType.TEXT,
        text: assistantMessage.content,
      })
    }

    // 触发响应式更新（shallowRef需要手动触发）
    messageStore.triggerMessagesUpdate()
  }

  const handleSystemMessage = (message: WebSocketMessage) => {
    if (message.type !== MessageType.SYSTEM_MESSAGE) return
    const systemMessage = message as unknown

    messageStore.addMessage({
      id: systemMessage.id,
      role: MessageRole.SYSTEM,
      timestamp: systemMessage.timestamp,
      sessionId: systemMessage.session_id,  // 添加 session_id
      content: [{ type: ContentType.TEXT, text: systemMessage.content }],
    })
  }

  const handleConnect = (message: WebSocketMessage) => {

    if (message.type !== MessageType.CONNECT) {
      return
    }

    const connectMessage = message as unknown

    // ✅ 严格验证：CONNECT 消息必须包含 session_id
    const backendSessionId = connectMessage.session_id
    if (!backendSessionId) {
      const error = new Error('[handleConnect] ❌ FATAL: CONNECT message missing session_id')
      logger.error('[ConnectionStore] Error:', error.message)
      logger.error('[handleConnect] 🔍 Full message for diagnosis:', connectMessage)
      throw error  // ← FastFail: 立即失败
    }

    const workspaceId = workspaceStore.currentWorkspaceId
    if (!workspaceId) {
      const error = new Error('[handleConnect] ❌ FATAL: No current workspace_id in workspaceStore')
      logger.error('[ConnectionStore] Error:', error.message)
      throw error  // ← FastFail: 立即失败
    }

    // ✅ 同步客户端的 session_id（关键步骤）
    try {
      const wsClient = connectionStore.getClient(workspaceId)

      if (!wsClient) {
        const error = new Error(`[handleConnect] ❌ FATAL: No WebSocket client found for workspace: ${workspaceId}`)
        logger.error('[ConnectionStore] Error:', error.message)
        throw error  // ← FastFail: 立即失败
      }

      const frontendSessionId = wsClient._sessionId?.value

      // ✅ 更新客户端的 session_id 为后端生成的值
      if (wsClient.setSessionId) {
        wsClient.setSessionId(backendSessionId)
        logger.debug('[handleConnect] ✅ Called wsClient.setSessionId()')
      } else {
        // Fallback: 如果没有公共方法，直接设置（不推荐，但保证兼容性）
        logger.warn('[handleConnect] ⚠️ wsClient.setSessionId not available, setting directly')
        wsClient._sessionId.value = backendSessionId
      }

      // ✅ 持久化到 sessionStorage（通过 wsClient 的方法）
      if (wsClient.saveSessionIdToStorage) {
        try {
          wsClient.saveSessionIdToStorage()
          logger.debug('[handleConnect] 💾 Saved session_id to sessionStorage via wsClient')
        } catch (storageError) {
          logger.warn('[handleConnect] ⚠️ Failed to save session_id to sessionStorage:', storageError)
          // 不抛出错误，sessionStorage 失败不应阻止连接
        }
      }

      // ✅ 清理旧的映射（如果存在且不同）
      if (frontendSessionId && frontendSessionId !== backendSessionId) {
        const deleted = connectionStore.sessionToWorkspaceMap.delete(frontendSessionId)
        if (deleted) {
          logger.debug('[handleConnect] 🧹 Cleaned up old session_id mapping:', frontendSessionId)
        } else {
          logger.debug('[handleConnect] ℹ️ Old session_id not in map (may have been cleaned::', frontendSessionId)
        }
      }

      // ✅ 注册新的映射
      connectionStore.sessionToWorkspaceMap.set(backendSessionId, workspaceId)

    } catch (syncError) {
      const error = new Error(`[handleConnect] ❌ FATAL: Failed to sync session_id: ${syncError.message}`)
      logger.error('[ConnectionStore] Error:', error.message, syncError)
      throw error  // ← FastFail: session_id 同步失败，立即终止
    }

  }

  const handleStreamReasoning = (message: WebSocketMessage) => {
    if (message.type !== MessageType.STREAM_REASONING) return
    const reasoningMessage = message as unknown

    if (!reasoningMessage.task_id) {
      logger.error('StreamReasoning message missing task_id:', reasoningMessage)
      return
    }

    const taskId = reasoningMessage.task_id
    const messageId = reasoningMessage.message_id
    const content = reasoningMessage.content || ''

    // 【DEBUG】记录接收到的流式推理内容
    if (content) {
      logger.warn('[STREAM_REASONING] 接收到内容:', content.substring(0, 50))
    }

    if (!messageId) {
      logger.warn('[CHAT_STORE] Stream reasoning missing message_id, using fallback')
      // 由于streamBuffers是私有的，我们需要通过messageStore的方法访问
      // 这里简化处理，直接使用messageStore的公开方法
      messageStore.updateStreamBuffer(taskId, 'reasoning', content)
      return
    }

    const reasoningBubbleId = `${messageId}_reasoning`

    let chatMessage = messageStore.getMessageById(reasoningBubbleId)

    if (!chatMessage) {
      chatMessage = {
        id: reasoningBubbleId,
        role: MessageRole.ASSISTANT,
        timestamp: new Date().toISOString(),
        content: [],
        taskId: taskId,
        sessionId: reasoningMessage.session_id,
        messageId: messageId,  // 保存原始的LLM message_id
      }
      messageStore.addMessage(chatMessage)
      logger.debug(`[CHAT_STORE] Created reasoning bubble: ${reasoningBubbleId}, messageId=${messageId}`)
    }

    const reasoningBlock = chatMessage.content.find(
      c => c.type === ContentType.REASONING
    )

    if (reasoningBlock) {
      // 创建新的reasoning block对象以确保响应式更新
      const newReasoning = reasoningBlock.reasoning + content
      // 【DEBUG】记录拼接后的内容
      if (content.length > 0 && content.length < 20) {
        logger.warn('[STREAM_REASONING] 拼接内容。当前长度:', newReasoning.length, '新增:', content)
      }
      const newContent = chatMessage.content.map(block =>
        block === reasoningBlock
          ? { ...block, reasoning: newReasoning }
          : block
      )
      messageStore.updateMessage(reasoningBubbleId, { content: newContent })
    } else {
      // 只有当内容非空时才创建推理块
      const trimmedContent = content.trim()
      if (trimmedContent) {
        // 【DEBUG】记录首次创建推理块
        logger.warn('[STREAM_REASONING] 首次创建推理块，内容:', content.substring(0, 50))
        const newContent = [...chatMessage.content, {
          type: ContentType.REASONING,
          reasoning: content
        }]
        messageStore.updateMessage(reasoningBubbleId, { content: newContent })
      }
    }

    // 触发响应式更新（shallowRef需要手动触发）
    messageStore.triggerMessagesUpdate()
  }

  // ✅ 修复：删除内容分析函数，使用后端提供的message_id

  // === Helper functions for stream content handling ===

  /**
   * Validate stream content message
   */
  const validateStreamContentMessage = (message: WebSocketMessage): void => {
    if (message.type !== MessageType.STREAM_CONTENT) {
      const error = new Error(`Expected STREAM_CONTENT, got ${message.type}`)
      logger.error('Invalid message type', error, { receivedType: message.type })
      throw error
    }
  }

  /**
   * Extract stream content message information
   */
  const extractStreamContentInfo = (message: WebSocketMessage): {
    taskId: string
    sessionId: string
    content: string
    messageId?: string
  } => {
    const contentMessage = message as unknown

    // 🔍 Debug: 打印完整的WebSocket消息
    logger.debug('[extractStreamContentInfo] Raw WebSocket message:', {
      type: message.type,
      keys: Object.keys(message),
      task_id: contentMessage.task_id,
      message_id: contentMessage.message_id,
      content_length: contentMessage.content?.length,
      fullMessage: JSON.stringify(message, null, 2)
    })

    // Strict validation: task_id must exist
    if (!contentMessage.task_id) {
      const error = new Error('StreamContent message missing task_id')
      logger.error('Missing task_id', error, { message: contentMessage })
      throw error
    }

    // Strict validation: session_id must exist
    if (!message.session_id) {
      const error = new Error('Message missing session_id')
      logger.error('Missing session_id', error, { taskId: contentMessage.task_id })
      throw error
    }

    const result = {
      taskId: contentMessage.task_id,
      sessionId: message.session_id,
      content: contentMessage.content || '',
      messageId: contentMessage.message_id
    }

    logger.debug('[extractStreamContentInfo] Extracted:', {
      taskId: result.taskId,
      messageId: result.messageId,
      hasMessageId: !!result.messageId
    })

    return result
  }

  /**
   * Get or create stream message
   */
  const getOrCreateStreamMessage = (
    messageBubbleId: string,
    taskId: string,
    sessionId: string,
    workspaceId: string,
    llmMessageId?: string  // ✅ 新增：LLM message_id参数
  ): ChatMessage => {
    let chatMessage = messageStore.getMessageById(messageBubbleId)

    if (!chatMessage) {
      // Create new message
      chatMessage = {
        id: messageBubbleId,
        role: MessageRole.ASSISTANT,
        timestamp: new Date().toISOString(),
        content: [],
        taskId: taskId,
        sessionId: sessionId,
        workspaceId: workspaceId,
        messageId: llmMessageId || messageBubbleId  // ✅ 优先使用LLM message_id，否则fallback到bubble ID
      }

      logger.debug('Creating new message', {
        messageBubbleId,
        taskId,
        workspaceId,
        llmMessageId,  // ✅ 记录LLM message_id
        finalMessageId: llmMessageId || messageBubbleId  // ✅ 记录最终设置的messageId
      })

      try {
        messageStore.addMessage(chatMessage, workspaceId)
        logger.debug('New message created', { messageBubbleId, workspaceId })
      } catch (error) {
        const errorMsg = `Failed to add message: ${error instanceof Error ? error.message : String(error)}`
        logger.error(errorMsg, error instanceof Error ? error : new Error(String(error)), { messageBubbleId, workspaceId })
        throw new Error(errorMsg)
      }

      // Re-fetch latest message reference
      chatMessage = messageStore.getMessageById(messageBubbleId)
    }

    if (!chatMessage) {
      logger.error('Message disappeared after add/get', { messageBubbleId })
      throw new Error('Message disappeared')
    }

    return chatMessage
  }

  /**
   * Update stream message content
   */
  const updateStreamMessageContent = (
    messageBubbleId: string,
    chatMessage: ChatMessage,
    content: string
  ): void => {
    const textBlock = chatMessage.content.find(c => c.type === ContentType.TEXT)

    if (textBlock && 'text' in textBlock) {
      // Append to existing text block
      const newText = textBlock.text + content

      // Create new content array to ensure reactivity
      const newContent = chatMessage.content.map(block => {
        if (block === textBlock || (block.type === ContentType.TEXT && 'text' in block)) {
          return {
            type: ContentType.TEXT,
            text: newText
          }
        }
        return block
      })

      messageStore.updateMessage(messageBubbleId, { content: newContent })
      logger.debug('Text block updated:', {
        messageBubbleId,
        oldLength: textBlock.text.length,
        newLength: newText.length,
        addedLength: content.length
      })
    } else {
      // Create new text block
      const newContent = [...chatMessage.content, {
        type: ContentType.TEXT,
        text: content
      }]

      messageStore.updateMessage(messageBubbleId, { content: newContent })
      logger.debug('New text block created:', {
        messageBubbleId,
        contentLength: content.length
      })
    }
  }

  /**
   * Handle stream content message
   */
  const handleStreamContent = (message: WebSocketMessage) => {
    logger.debug('Stream content message received:', {
      type: message.type,
      messageId: message.id,
      sessionId: message.session_id
    })

    // Validate message type
    validateStreamContentMessage(message)

    // Extract message information
    const { taskId, sessionId, content, messageId } = extractStreamContentInfo(message)

    // Add to processing set
    processingMessages.add(message.id)

    logger.debug('Processing stream content:', {
      taskId,
      messageId,  // ✅ LLM message_id from WebSocket
      wsMessageId: message.id,  // WebSocket protocol message id
      contentLength: content?.length,
      hasMessageId: !!messageId  // ✅ Debug: 是否有LLM message_id
    })

    // Resolve workspace
    const workspaceId = resolveWorkspaceId(
      { session_id: sessionId },
      false // No fallback - fast fail
    )

    logger.debug('Workspace resolved:', {
      sessionId,
      workspaceId,
      taskId
    })

    // Use try-finally to ensure cleanup
    try {
      // Determine message bubble ID
      const messageBubbleId = messageId || `msg_${taskId}`

      // Get or create message
      const chatMessage = getOrCreateStreamMessage(
        messageBubbleId,
        taskId,
        sessionId,
        workspaceId,
        messageId  // ✅ 传递LLM message_id
      )

      logger.debug('Found existing message:', {
        messageBubbleId,
        llmMessageId: messageId,  // ✅ LLM message_id
        chatMessageId: chatMessage.messageId,  // ✅ ChatMessage.messageId当前值
        contentLength: chatMessage.content.length,
        idMatch: chatMessage.messageId === messageId  // ✅ Debug: ID是否匹配
      })

      // Update message content
      updateStreamMessageContent(messageBubbleId, chatMessage, content)

      // Trigger reactive update
      messageStore.triggerMessagesUpdate()

      logger.debug('Stream content processing complete', { messageBubbleId })
    } finally {
      // Cleanup processing mark
      processingMessages.delete(message.id)
      logger.debug('Processing mark removed', { messageId: message.id })
    }
  }

  const handleStreamToolCall = (message: WebSocketMessage) => {
    logger.debug('[handleStreamToolCall] Received message:', message)
    if (message.type !== MessageType.STREAM_TOOL_CALL) {
      logger.warn('[handleStreamToolCall] Message type mismatch:', message.type)
      return
    }

    const toolCallMessage = message as unknown

    if (!toolCallMessage.task_id) {
      logger.error('[handleStreamToolCall] Message missing task_id:', toolCallMessage)
      return
    }

    const chatMessage = messageStore.getOrCreateAssistantMessage(toolCallMessage.task_id)

    const rawToolCall = toolCallMessage.tool_call
    let toolCallId: string
    let toolName: string
    let argumentsChunk: string | null = null

    if (rawToolCall) {
      toolCallId = rawToolCall.tool_call_id || uuidv4()

      if (rawToolCall.type === 'function' && rawToolCall.function) {
        toolName = rawToolCall.function.name || 'unknown'
        argumentsChunk = rawToolCall.function.arguments || null
      } else {
        toolName = rawToolCall.tool_name || 'unknown'
        argumentsChunk = rawToolCall.tool_input || null
      }
    } else {
      logger.error('StreamToolCall message missing tool_call:', toolCallMessage)
      return
    }

    logger.debug('[handleStreamToolCall] toolCallId:', toolCallId)
    logger.debug('[handleStreamToolCall] toolName:', toolName)
    logger.debug('[handleStreamToolCall] argumentsChunk:', argumentsChunk)
    // 处理工具执行的实时输出
    if (rawToolCall.output !== undefined && rawToolCall.output !== null) {
      logger.debug('[handleStreamToolCall] Found tool output:', rawToolCall.output)
      let toolExecutionBlock = chatMessage.content.find(
        c => c.type === ContentType.TOOL_EXECUTION && (c as unknown).toolCallId === toolCallId
      )

      if (!toolExecutionBlock) {
        toolExecutionBlock = {
          type: ContentType.TOOL_EXECUTION,
          toolCallId: toolCallId,
          toolName: toolName,
          toolInput: rawToolCall.tool_input,
          status: rawToolCall.status || 'executing',
          startTime: new Date().toISOString(),
          streamOutput: []
        }
        chatMessage.content.push(toolExecutionBlock)
        logger.debug('[handleStreamToolCall] Created new ToolExecutionContentBlock')
      }

      if (!toolExecutionBlock.streamOutput) {
        toolExecutionBlock.streamOutput = []
      }

      if (typeof rawToolCall.output === 'string') {
        toolExecutionBlock.streamOutput.push(rawToolCall.output)
      } else if (typeof rawToolCall.output === 'object') {
        toolExecutionBlock.streamOutput.push(JSON.stringify(rawToolCall.output))
      }

      if (rawToolCall.status) {
        toolExecutionBlock.status = rawToolCall.status
      }

      logger.debug('[handleStreamToolCall] Stream output added, total lines:', toolExecutionBlock.streamOutput.length)
      // 触发响应式更新（shallowRef需要手动触发）
      messageStore.triggerMessagesUpdate()
    }

    // 积累arguments
    if (argumentsChunk !== null) {
      // 获取或创建工具调用流式缓冲区
      let streamBuffer = messageStore.toolCallStreamBuffers.get(toolCallId)

      if (!streamBuffer) {
        streamBuffer = {
          partialArguments: '',
          toolName: toolName,
          lastUpdate: Date.now()
        }
        messageStore.toolCallStreamBuffers.set(toolCallId, streamBuffer)
        logger.debug('[handleStreamToolCall] Created new stream buffer for tool_call_id:', toolCallId)
      }

      // 追加 arguments 数据块
      streamBuffer.partialArguments += argumentsChunk
      streamBuffer.lastUpdate = Date.now()

      logger.debug('[handleStreamToolCall] Accumulated arguments length:', streamBuffer.partialArguments.length)
    }

    // 查找或创建工具调用内容块
    const toolCallBlock = chatMessage.content.find(
      c => c.type === ContentType.TOOL_CALL && (c as unknown).toolCall.tool_call_id === toolCallId
    )

    // 获取当前积累的 arguments
    const streamBuffer = messageStore.toolCallStreamBuffers.get(toolCallId)
    const currentArguments = streamBuffer?.partialArguments || '{}'

    // 尝试解析为 JSON 对象
    let toolInput: unknown
    try {
      toolInput = JSON.parse(currentArguments)
    } catch {
      toolInput = currentArguments
    }

    logger.debug('[handleStreamToolCall] toolCallBlock found:', !!toolCallBlock)
    if (toolCallBlock) {
      // 更新现有工具调用块的状态和内容
      logger.debug('[handleStreamToolCall] Updating existing tool call block')
        (toolCallBlock as unknown).toolCall = {
        tool_call_id: toolCallId,
        tool_name: toolName,
        tool_input: toolInput,
        status: 'in_progress'
      }
    } else {
      // 创建新的工具调用块
      logger.debug('[handleStreamToolCall] Creating new tool call block')
      const newBlock = {
        type: ContentType.TOOL_CALL,
        toolCall: {
          tool_call_id: toolCallId,
          tool_name: toolName,
          tool_input: toolInput,
          status: 'started'
        }
      }
      chatMessage.content.push(newBlock)
      logger.debug('[handleStreamToolCall] New block added:', newBlock)
    }

    // 触发响应式更新（shallowRef需要手动触发）
    messageStore.triggerMessagesUpdate()

  }

  const handleStreamComplete = async (message: WebSocketMessage) => {
    logger.debug('isThinking.value BEFORE:', isThinking.value)
    logger.debug('收到 stream_complete 消息:', message)
    if (message.type !== MessageType.STREAM_COMPLETE) return
    const completeMessage = message as unknown
    agentStore.setThinking(false)

    logger.debug('isThinking.value AFTER:', isThinking.value)
    const taskId = completeMessage.task_id

    // ⭐ 清理工具调用流式缓冲区
    if (completeMessage.tool_calls && completeMessage.tool_calls.length > 0) {
      logger.debug('[handleStreamComplete] Cleaning up tool call stream buffers')
      for (const toolCall of completeMessage.tool_calls) {
        const toolCallId = toolCall.tool_call_id
        if (toolCallId && messageStore.toolCallStreamBuffers.has(toolCallId)) {
          logger.debug('[handleStreamComplete] Removing stream buffer for tool_call_id:', toolCallId)
          messageStore.toolCallStreamBuffers.delete(toolCallId)
        }
      }
    }

    // 🔥 处理 conversation_id 更新(来自 STREAM_COMPLETE)
    // 注意: 主要的 conversation_id 更新来自 CONVERSATION_INFO 消息
    // 这里只是作为双重保障
    if (completeMessage.conversation_id && currentConversationId.value !== completeMessage.conversation_id) {
      logger.debug(`[CHAT_STORE] STREAM_COMPLETE: 更新 conversation_id: ${currentConversationId.value} -> ${completeMessage.conversation_id}`)

      const workspaceStore = useWorkspaceStore()
      workspaceStore.setConversation(completeMessage.conversation_id)

      // 重新加载会话列表
      if (workspaceId.value) {
        await workspaceStore.loadConversations(workspaceId.value)
      }
    }

    // 刷新缓冲区
    messageStore.flushStreamBuffer(taskId)

    // 清除缓冲区和定时器
    messageStore.clearStreamBuffer(taskId)

    // 🔥 优先使用 LLM API 响应消息（如果存在），否则创建新消息
    const llmApiMessageId = `${taskId}-response`
    let chatMessage = messageStore.getMessageById(llmApiMessageId)

    if (!chatMessage) {
      chatMessage = messageStore.getOrCreateAssistantMessage(taskId)
    }

    // 处理推理内容
    if (completeMessage.reasoning_content) {
      logger.debug('处理 reasoning_content:', completeMessage.reasoning_content)

      // 【调查】记录原始内容的前100个字符
      const preview = completeMessage.reasoning_content.substring(0, 100)
      logger.warn('[DEBUG] reasoning_content 原始内容预览:', preview)

      const reasoningBlock = chatMessage.content.find(
        c => c.type === ContentType.REASONING
      )

      if (!reasoningBlock) {
        chatMessage.content.push({
          type: ContentType.REASONING,
          reasoning: completeMessage.reasoning_content
        })
      }
    }

    // 处理回复内容
    if (completeMessage.content) {
      logger.debug('处理 content:', completeMessage.content)
      const textBlock = chatMessage.content.find(
        c => c.type === ContentType.TEXT
      )

      if (!textBlock) {
        // 如果 LLM API 响应消息已经存在且有内容，跳过（避免重复）
        if (chatMessage.id === llmApiMessageId) {
          const existingText = chatMessage.content.find(c => c.type === ContentType.TEXT)
          if (existingText && 'text' in existingText && existingText.text) {
            logger.debug('[handleStreamComplete] LLM API 响应消息已有内容，跳过重复添加')
          } else {
            chatMessage.content.push({
              type: ContentType.TEXT,
              text: completeMessage.content
            })
          }
        } else {
          chatMessage.content.push({
            type: ContentType.TEXT,
            text: completeMessage.content
          })
        }
      }
    }

    // 处理工具调用结果
    if (completeMessage.tool_calls && completeMessage.tool_calls.length > 0) {
      logger.debug('处理 tool_calls:', completeMessage.tool_calls)

      // ✅ 创建新的 content 数组用于存储更新
      const newContent = [...chatMessage.content]

      for (const toolCall of completeMessage.tool_calls) {
        const toolCallBlockIndex = newContent.findIndex(
          c => c.type === ContentType.TOOL_CALL && (c as unknown).toolCall.tool_call_id === toolCall.tool_call_id
        )

        if (toolCallBlockIndex !== -1) {
          // ✅ 更新现有的 toolCall block
          const toolCallBlock = newContent[toolCallBlockIndex] as unknown
          toolCallBlock.toolCall = {
            ...toolCallBlock.toolCall,
            status: toolCall.status,
            output: toolCall.output,
            error: toolCall.error
          }
          newContent[toolCallBlockIndex] = toolCallBlock

          if (toolCall.output) {
            newContent.push({
              type: ContentType.TOOL_RESULT,
              toolName: toolCall.tool_name,
              result: toolCall.output,
              isError: false
            })
          }

          if (toolCall.error) {
            newContent.push({
              type: ContentType.ERROR,
              message: `工具调用失败: ${toolCall.error}`,
              details: { toolCall }
            })
          }
        }
      }

      // ✅ 更新消息内容以触发响应式更新
      messageStore.updateMessage(chatMessage.id, { content: newContent })
      logger.debug('[handleStreamComplete] Updated message with tool call results:', chatMessage.id)
    }

    logger.debug('✅ stream_complete 处理完成')
  }

  const handleToolCallStart = (message: WebSocketMessage) => {
    if (message.type !== MessageType.TOOL_CALL_START) return
    const toolMessage = message as unknown

    const chatMessage = messageStore.getOrCreateAssistantMessage(toolMessage.task_id)

    const toolExecutionBlock = {
      type: ContentType.TOOL_EXECUTION,
      toolCallId: toolMessage.tool_call_id || uuidv4(),
      toolName: toolMessage.tool_name,
      toolInput: toolMessage.tool_input,
      status: toolMessage.status || 'started',
      startTime: new Date().toISOString()
    }

    // ✅ 创建新的 content 数组以触发响应式更新
    const newContent = [...chatMessage.content, toolExecutionBlock]
    messageStore.updateMessage(chatMessage.id, { content: newContent })
    logger.debug('[handleToolCallStart] Tool call started and added to message:', chatMessage.id)
  }

  const handleToolCallProgress = (message: WebSocketMessage) => {
    if (message.type !== MessageType.TOOL_CALL_PROGRESS) return
    const progressMessage = message as unknown

    let found = false
    for (const msg of messageStore.messages) {
      if (msg.role === MessageRole.ASSISTANT) {
        for (const content of msg.content) {
          if (content.type === ContentType.TOOL_EXECUTION &&
            (content as unknown).toolCallId === progressMessage.tool_call_id) {
            found = true

            const toolExecution = content as unknown

            // ✅ 创建新的 toolExecution 对象
            const updatedToolExecution = {
              ...toolExecution,
              status: progressMessage.status || toolExecution.status,
              progressPercentage: progressMessage.progress_percentage,
              currentStep: progressMessage.current_step,
              totalSteps: progressMessage.total_steps,
              currentStepIndex: progressMessage.current_step_index,
              estimatedRemainingTime: progressMessage.estimated_remaining_time,
              progressHistory: [
                ...(toolExecution.progressHistory || []),
                {
                  timestamp: new Date().toISOString(),
                  message: progressMessage.message,
                  progress_percentage: progressMessage.progress_percentage,
                  step: progressMessage.current_step
                }
              ],
              streamOutput: progressMessage.stream_output
                ? [...(toolExecution.streamOutput || []), progressMessage.stream_output]
                : toolExecution.streamOutput
            }

            // ✅ 创建新的 content 数组以触发响应式更新
            const newContent = msg.content.map(block =>
              block === content ? updatedToolExecution : block
            )
            messageStore.updateMessage(msg.id, { content: newContent })
            logger.debug('[handleToolCallProgress] Tool progress updated:', msg.id)
          }
        }
      }
    }

    // ✅ 如果没有找到匹配的块，创建一个新的 TOOL_EXECUTION 块
    if (!found) {
      const toolCallId = progressMessage.tool_call_id
      const toolName = progressMessage.tool_name || 'unknown'

      // 查找最新的 assistant 消息或创建新的
      const assistantMessages = messageStore.messages.filter(m => m.role === MessageRole.ASSISTANT)
      const lastAssistantMsg = assistantMessages[assistantMessages.length - 1]

      if (lastAssistantMsg) {
        const newToolExecutionBlock = {
          type: ContentType.TOOL_EXECUTION,
          toolCallId: toolCallId,
          toolName: toolName,
          toolInput: {},
          status: 'in_progress',
          startTime: new Date().toISOString(),
          progressPercentage: progressMessage.progress_percentage,
          currentStep: progressMessage.current_step,
          totalSteps: progressMessage.total_steps,
          progressHistory: [
            {
              timestamp: new Date().toISOString(),
              message: progressMessage.message,
              progress_percentage: progressMessage.progress_percentage,
              step: progressMessage.current_step
            }
          ]
        }

        const newContent = [...lastAssistantMsg.content, newToolExecutionBlock]
        messageStore.updateMessage(lastAssistantMsg.id, { content: newContent })
        logger.debug('[handleToolCallProgress] Created new TOOL_EXECUTION block:', toolCallId)
      }
    }
  }

  const handleToolCallResult = (message: WebSocketMessage) => {
    if (message.type !== MessageType.TOOL_CALL_RESULT) return
    const resultMessage = message as unknown

    let found = false
    for (const msg of messageStore.messages) {
      if (msg.role === MessageRole.ASSISTANT) {
        for (const content of msg.content) {
          if (content.type === ContentType.TOOL_EXECUTION &&
            (content as unknown).toolCallId === resultMessage.tool_call_id) {
            found = true

            const toolExecution = content as unknown

            // ✅ 创建新的 toolExecution 对象
            const updatedToolExecution = {
              ...toolExecution,
              status: resultMessage.is_error ? 'failed' : 'completed',
              result: resultMessage.result,
              isError: resultMessage.is_error,
              errorCode: resultMessage.error_code,
              errorMessage: resultMessage.error_message,
              endTime: new Date().toISOString(),
              executionTime: resultMessage.execution_time,
              performanceMetrics: resultMessage.performance_metrics || toolExecution.performanceMetrics
            }

            // ✅ 创建新的 content 数组以触发响应式更新
            const newContent = msg.content.map(block =>
              block === content ? updatedToolExecution : block
            )
            messageStore.updateMessage(msg.id, { content: newContent })
            logger.debug('[handleToolCallResult] Tool result updated:', msg.id)
          }
        }
      }
    }

    // ✅ 如果没有找到匹配的块，创建一个新的 TOOL_EXECUTION 块
    if (!found) {
      const toolCallId = resultMessage.tool_call_id
      const toolName = resultMessage.tool_name || 'unknown'
      const isError = resultMessage.is_error

      // 查找最新的 assistant 消息
      const assistantMessages = messageStore.messages.filter(m => m.role === MessageRole.ASSISTANT)
      const lastAssistantMsg = assistantMessages[assistantMessages.length - 1]

      if (lastAssistantMsg) {
        const newToolExecutionBlock = {
          type: ContentType.TOOL_EXECUTION,
          toolCallId: toolCallId,
          toolName: toolName,
          toolInput: {},
          status: isError ? 'failed' : 'completed',
          result: resultMessage.result,
          isError: isError,
          errorCode: resultMessage.error_code,
          errorMessage: resultMessage.error_message,
          startTime: new Date().toISOString(),
          endTime: new Date().toISOString(),
          executionTime: resultMessage.execution_time
        }

        const newContent = [...lastAssistantMsg.content, newToolExecutionBlock]
        messageStore.updateMessage(lastAssistantMsg.id, { content: newContent })
        logger.debug('[handleToolCallResult] Created new TOOL_EXECUTION block:', toolCallId)
      } else {
        console.warn('[handleToolCallResult] No assistant message found to attach tool result')
      }
    }
  }

  const handleFollowupQuestion = (message: WebSocketMessage) => {
    logger.debug('收到追问问题消息:', message)
    window.dispatchEvent(new CustomEvent('followup-question', {
      detail: message
    }))
  }

  const handleLLMApiRequest = (message: WebSocketMessage) => {
    if (message.type !== MessageType.LLM_API_REQUEST) return
    const apiRequest = message as unknown

    const currentStatus = getCurrentLlmApiStatus()
    currentStatus.isActive = true
    currentStatus.provider = apiRequest.provider
    currentStatus.model = apiRequest.model
    currentStatus.requestType = apiRequest.request_type || 'chat'
    currentStatus.startTime = Date.now()
    currentStatus.responseContent = ''

    // LLM API消息不再显示在消息区域，只通过status bar显示
    // const systemMessage: ChatMessage = {
    //   id: uuidv4(),
    //   role: MessageRole.SYSTEM,
    //   timestamp: new Date().toISOString(),
    //   content: [{
    //     type: ContentType.SIMPLE_TEXT,
    //     text: `LLM API: ${apiRequest.provider} - ${apiRequest.model}`
    //   }]
    // }
    // messageStore.addMessage(systemMessage)

    window.dispatchEvent(new CustomEvent('llm-api-request', {
      detail: apiRequest
    }))
  }

  const handleLLMApiResponse = (message: WebSocketMessage) => {
    if (message.type !== MessageType.LLM_API_RESPONSE) return
    const apiResponse = message as unknown

    if (apiResponse.content) {
      const currentStatus = getCurrentLlmApiStatus()
      currentStatus.responseContent += apiResponse.content

      // 🔥 如果是 content 类型，需要添加到聊天消息中（实现打字机效果）
      if (apiResponse.response_type === 'content' && apiResponse.task_id) {
        const taskId = apiResponse.task_id
        const messageId = `${taskId}-response` // 为 LLM API 响应创建唯一的消息 ID
        const content = apiResponse.content

        // ✅ Use workspace resolver utility
        const workspaceId = resolveWorkspaceId(
          apiResponse,
          true // Allow fallback to current workspace for LLM API responses
        )

        let chatMessage = messageStore.getMessageById(messageId)

        if (!chatMessage) {
          chatMessage = {
            id: messageId,
            role: MessageRole.ASSISTANT,
            timestamp: new Date().toISOString(),
            content: [],
            taskId: taskId,
            sessionId: apiResponse.session_id,
          }

          try {
            messageStore.addMessage(chatMessage, workspaceId)
            logger.debug(`[handleLLMApiResponse] ✅ Created new message for streaming: messageId=${messageId}`)
          } catch (error) {
            logger.error('[handleLLMApiResponse] ❌ Failed to add message:', error)
          }
        }

        // 追加内容到消息（实现打字机效果）
        const textBlock = chatMessage.content.find(c => c.type === ContentType.TEXT)

        if (textBlock && 'text' in textBlock) {
          const newText = textBlock.text + content
          const newContent = chatMessage.content.map(block =>
            block === textBlock
              ? { ...block, text: newText }
              : block
          )
          messageStore.updateMessage(messageId, { content: newContent })
        } else {
          const newContent = [...chatMessage.content, {
            type: ContentType.TEXT,
            text: content
          }]
          messageStore.updateMessage(messageId, { content: newContent })
        }
      }
    }

    window.dispatchEvent(new CustomEvent('llm-api-response', {
      detail: apiResponse
    }))
  }

  const handleLLMApiComplete = (message: WebSocketMessage) => {
    if (message.type !== MessageType.LLM_API_COMPLETE) return
    const apiComplete = message as unknown

    const currentStatus = getCurrentLlmApiStatus()
    currentStatus.isActive = false
    currentStatus.provider = ''
    currentStatus.model = ''
    currentStatus.requestType = ''
    currentStatus.startTime = null
    currentStatus.responseContent = ''

    // LLM API完成消息不再显示在消息区域，只通过status bar显示
    // const systemMessage: ChatMessage = {
    //   id: uuidv4(),
    //   role: MessageRole.SYSTEM,
    //   timestamp: new Date().toISOString(),
    //   content: [{
    //     type: ContentType.SIMPLE_TEXT,
    //     text: `LLM API 完成: ${duration}`
    //   }]
    // }
    // messageStore.addMessage(systemMessage)

    window.dispatchEvent(new CustomEvent('llm-api-complete', {
      detail: apiComplete
    }))
  }

  const handleLLMApiError = (message: WebSocketMessage) => {
    if (message.type !== MessageType.LLM_API_ERROR) return
    const apiError = message as unknown

    console.error('[LLM API] Request failed:', {
      provider: apiError.provider,
      model: apiError.model,
      errorCode: apiError.error_code,
      errorMessage: apiError.error_message,
      isRetryable: apiError.is_retryable
    })

    const currentStatus = getCurrentLlmApiStatus()
    currentStatus.isActive = false
    currentStatus.provider = ''
    currentStatus.model = ''
    currentStatus.requestType = ''
    currentStatus.startTime = null
    currentStatus.responseContent = ''

    // LLM API错误消息不再显示在消息区域，只通过status bar显示
    // const systemMessage: ChatMessage = {
    //   id: uuidv4(),
    //   role: MessageRole.SYSTEM,
    //   timestamp: new Date().toISOString(),
    //   content: [{
    //     type: ContentType.SIMPLE_TEXT,
    //     text: `LLM API 错误: ${apiError.error_code || 'unknown'} - ${apiError.error_message || 'unknown error'}`
    //   }]
    // }
    // messageStore.addMessage(systemMessage)

    window.dispatchEvent(new CustomEvent('llm-api-error', {
      detail: apiError
    }))
  }

  const handleTodoUpdate = (message: WebSocketMessage) => {
    if (message.type !== MessageType.TODO_UPDATE) return
    const todoMessage = message as unknown

    // 更新todoStore
    if (todoMessage.todos && Array.isArray(todoMessage.todos)) {
      todoStore.updateTodos(todoMessage.task_node_id, todoMessage.todos)
    }

    // 同步到parallelTasks store
    parallelTasksStore.handleTodoUpdate({
      task_id: todoMessage.task_node_id,
      todos: todoMessage.todos
    })
  }

  /**
   * 处理任务节点进度消息 - 显示在聊天对话框中
   */
  const handleTaskNodeProgressForChat = (message: WebSocketMessage) => {
    if (message.type !== MessageType.TASK_NODE_PROGRESS) return
    const progressMessage = message as unknown

  }

  /**
   * 处理会话信息消息 - 更新conversation_id
   */
  const handleConversationInfo = (message: WebSocketMessage) => {
    if (message.type !== MessageType.CONVERSATION_INFO) return
    const convInfoMessage = message as ConversationInfoMessage

    // 立即更新 currentConversationId
    const workspaceStore = useWorkspaceStore()
    if (workspaceStore.currentConversationId !== convInfoMessage.conversation_id) {
      workspaceStore.setConversation(convInfoMessage.conversation_id)
    }
  }

  const handleError = (message: WebSocketMessage) => {
    const startTime = performance.now()
    const usedLayer = 0

    if (message.type !== MessageType.ERROR) return
    const errorMessage = message as unknown
    agentStore.setThinking(false)

    // ✅ 恢复错误消息在聊天区域的显示
    const errorContent: unknown = {
      type: ContentType.ERROR,
      message: errorMessage.message || '未知错误',
      details: errorMessage.details
    }

    // 如果有错误代码，添加到details中
    if (errorMessage.code) {
      if (!errorContent.details) {
        errorContent.details = {}
      }
      if (typeof errorContent.details === 'object') {
        errorContent.details.code = errorMessage.code
      }
    }

    const errorMsg: ChatMessage = {
      id: errorMessage.id || uuidv4(),
      role: MessageRole.SYSTEM,
      timestamp: errorMessage.timestamp || new Date().toISOString(),
      taskId: errorMessage.task_id,
      sessionId: errorMessage.session_id,  // Use sessionId (camelCase) not session_id
      content: [errorContent],
    }

    // ✅ Use workspace resolver utility (eliminates 35+ lines of duplicate code)
    const workspaceId = resolveWorkspaceId(
      errorMessage,
      false // No fallback - fast fail if cannot resolve
    )

    logger.debug('Workspace resolved for error message:', {
      sessionId: errorMessage.session_id,
      workspaceId
    })

    // 尝试添加消息，捕获任何异常
    try {
      logger.debug('[ERROR] Adding error message with workspaceId:', workspaceId)
      messageStore.addMessage(errorMsg, workspaceId)

      // ✅ 确保UI更新 - 触发响应式更新
      messageStore.triggerMessagesUpdate()

      // 记录性能指标（不使用fallback）
      const duration = performance.now() - startTime
      errorMonitoring.recordErrorHandling(usedLayer, duration, false)
    } catch (error) {
      // 如果添加消息失败，记录错误并快速失败
      logger.error('[ERROR] Failed to add error message to workspace:', error)
      console.error('[ERROR] Error details:', {
        errorMessage,
        attemptedWorkspaceId: workspaceId,
        sessionId: errorMessage.session_id,
        error: error instanceof Error ? error.message : String(error)
      })

      // 记录失败
      errorMonitoring.recordAddMessageFailure()

      // Fast fail: 不使用 fallback 机制，直接抛出错误
      const fatalError = new Error(
        `[handleError] ❌ FATAL: Failed to add error message to workspace\n` +
        `  Workspace ID: ${workspaceId}\n` +
        `  Error: ${error instanceof Error ? error.message : String(error)}\n` +
        `  Original Error: ${errorMessage.message}`
      )

      // 显示用户友好错误
      ElMessage.error('显示错误消息失败，请刷新页面')

      throw fatalError  // ✅ Fast fail: 立即失败
    }
  }

  // --- 监听会话变化自动加载消息 ---

  // 用于标记是否正在手动加载（避免重复）
  let isLoadingConversation = false

  // 监听 currentConversationId 变化，自动加载会话消息
  watch(currentConversationId, async (newConversationId, oldConversationId) => {
    // 如果正在手动加载，跳过
    if (isLoadingConversation) return

    // 如果新值与旧值相同，跳过
    if (newConversationId === oldConversationId) return

    // 如果为空或为临时会话，跳过
    if (!newConversationId || isTempConversation.value) return

    logger.debug(`[CHAT_STORE] Auto-loading conversation on ID change: ${oldConversationId} -> ${newConversationId}`)

    try {
      isLoadingConversation = true
      await loadConversation(newConversationId)
    } catch (error) {
      logger.error('[CHAT_STORE] Error auto-loading conversation:', error)
    } finally {
      isLoadingConversation = false
    }
  })

  // --- A2UI Message Handlers ---

  /**
   * Handle A2UI server event messages
   */
  const handleA2UIServerEvent = (message: WebSocketMessage) => {
    if (message.type !== MessageType.A2UI_SERVER_EVENT) return

    const a2uiMessage = message as unknown
    logger.debug('[A2UI] Received server event:', a2uiMessage)

    // Process A2UI messages through the processor
    try {
      // Import A2UI processor dynamically
      import('@/a2ui/processor').then(({ a2uiProcessor }) => {
        a2uiProcessor.processMessages(a2uiMessage.messages || [])

        // Get all surfaces from the processor
        const surfaces = a2uiProcessor.getSurfaces()

        // Update or create chat messages for each surface
        surfaces.forEach((surface, surfaceId) => {
          const messageId = `a2ui_${surfaceId}`

          // Check if message already exists
          const existingMessage = messageStore.getMessageById(messageId)

          if (!existingMessage) {
            // Create new message for this surface
            const newMessage: ChatMessage = {
              id: messageId,
              role: MessageRole.ASSISTANT,
              timestamp: new Date().toISOString(),
              content: [
                {
                  type: ContentType.A2UI_SURFACE,
                  surfaceId: surfaceId,
                  surfaceType: 'custom',
                  components: Array.from(surface.components.values()),
                  dataModel: Object.fromEntries(surface.dataModel),
                  metadata: {
                    title: a2uiMessage.metadata?.title,
                    description: a2uiMessage.metadata?.description,
                    interactive: true,
                  },
                }
              ],
              sessionId: a2uiMessage.session_id || sessionId.value,
            }

            messageStore.addMessage(newMessage, workspaceStore.currentWorkspaceId || 'default')
          } else {
            // Update existing message
            const a2uiBlock = existingMessage.content.find(
              block => block.type === ContentType.A2UI_SURFACE
            ) as unknown

            if (a2uiBlock) {
              a2uiBlock.components = Array.from(surface.components.values())
              a2uiBlock.dataModel = Object.fromEntries(surface.dataModel)
              messageStore.updateMessage(messageId, { content: existingMessage.content })
            }
          }
        })
      })
    } catch (error) {
      logger.error('[A2UI] Error processing server event:', error)
    }
  }

  /**
   * Handle A2UI user action messages (optional - for backend responses)
   */
  const handleA2UIUserAction = (message: WebSocketMessage) => {
    if (message.type !== MessageType.A2UI_USER_ACTION) return

    const actionMessage = message as unknown
    logger.debug('[A2UI] Received user action response:', actionMessage)

    // Backend can send responses to user actions here
    // For now, just log it
  }

  // --- 返回store接口 ---

  // 知识库选择状态 (本地状态,不持久化)
  const selectedKnowledgeBaseIds = ref<string[]>([])

  return {
    // State (代理到专门stores)
    messages,
    connectionStatus,
    isConnected,
    isThinking,
    currentTaskId,
    sessionId,
    workspaceId,
    currentThinking,
    thinkingSteps,
    uiContext,
    llmApiStatus,
    agentStatus,
    selectedKnowledgeBaseIds,

    // Actions
    initializeConnection,
    sendMessage,
    sendWebSocketMessage,
    updateUIContext,
    clearChat,
    setTempConversation,
    setWorkspaceId,
    loadConversation,
    stopAgent,
  }
})
