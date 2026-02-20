/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * MessageStore - 消息管理
 *
 * 职责：
 * - 消息列表管理
 * - 消息增删改查
 * - 流式消息处理
 * - 思考内容管理
 */

import { ref, computed, triggerRef } from 'vue'
import { logger } from '@/utils/logger'

import { defineStore } from 'pinia'
import { v4 as uuidv4 } from 'uuid'
import type {
  ChatMessage,
  ContentBlock,
  WebSocketMessage,
  TextContentBlock,
  ThinkingContentBlock,
  ToolExecutionContentBlock,
  ErrorContentBlock,
  ToolResultContentBlock
} from '@/types/websocket'
import {
  ContentType,
  MessageRole
} from '@/types/websocket'

import { useWorkspaceStore as _useWorkspaceStore } from './workspace'
import { useConnectionStore as _useConnectionStore } from './connection'

export const useMessageStore = defineStore('messages', () => {
  // --- Helper function to get current workspaceId ---
  const getCurrentWorkspaceId = () => {
    const workspaceStore = _useWorkspaceStore()
    return workspaceStore.currentWorkspaceId || 'default'
  }

  // --- Helper function to get workspaceId by session_id (fallback) ---
  const getWorkspaceIdBySession = (sessionId: string | undefined): string | null => {
    if (!sessionId) return null

    const connectionStore = _useConnectionStore()
    const workspaceId = connectionStore.getWorkspaceIdBySession(sessionId)

    if (workspaceId) {
      logger.debug(`[MessageStore] Resolved workspaceId from session: ${sessionId} → ${workspaceId}`)
      return workspaceId
    }

    return null
  }

  // --- State (按workspace隔离) ---

  /**
   * 消息列表映射（按workspace隔离） - 使用 shallowRef 避免深度响应式造成的性能问题
   */
  const workspaceMessages = ref<Map<string, ChatMessage[]>>(new Map())

  /**
   * 当前思考内容映射（按workspace隔离）
   */
  const workspaceThinking = ref<Map<string, string>>(new Map())

  /**
   * 流式内容累积映射（按workspace隔离）
   */
  const workspaceStreamingContent = ref<Map<string, string>>(new Map())

  /**
   * 流式消息缓冲区映射（按workspace隔离）
   * key: workspaceId, value: Map<messageId, { content, reasoning, lastUpdate }>
   */
  const workspaceStreamBuffers = ref<Map<string, Map<string, {
    content: string
    reasoning: string
    lastUpdate: number
  }>>>(new Map())

  /**
   * 流式消息更新定时器映射（按workspace隔离）
   * key: workspaceId, value: Map<messageId, timer>
   */
  const workspaceStreamUpdateTimers = ref<Map<string, Map<string, number>>>(new Map())

  /**
   * 流式消息更新间隔（毫秒）
   */
  const STREAM_UPDATE_INTERVAL = 100

  /**
   * 工具调用流式缓冲区映射（按workspace隔离）
   * key: workspaceId, value: Map<tool_call_id, { partialArguments, toolName, lastUpdate }>
   */
  const workspaceToolCallStreamBuffers = ref<Map<string, Map<string, {
    partialArguments: string
    toolName: string
    lastUpdate: number
  }>>>(new Map())

  // --- Helper functions to get current workspace state ---

  /**
   * 获取当前workspace的消息列表
   */
  const getCurrentMessages = (): ChatMessage[] => {
    const workspaceId = getCurrentWorkspaceId()
    if (!workspaceMessages.value.has(workspaceId)) {
      workspaceMessages.value.set(workspaceId, [])
    }
    return workspaceMessages.value.get(workspaceId)!
  }

  /**
   * 获取当前workspace的消息列表（响应式）
   */
  const messages = computed(() => getCurrentMessages())

  /**
   * 获取当前workspace的思考内容
   */
  const getCurrentThinking = (): string => {
    const workspaceId = getCurrentWorkspaceId()
    return workspaceThinking.value.get(workspaceId) || ''
  }

  /**
   * 获取当前workspace的思考内容（响应式）
   */
  const currentThinking = computed(() => getCurrentThinking())

  /**
   * 获取当前workspace的流式内容
   */
  const getCurrentStreamingContent = (): string => {
    const workspaceId = getCurrentWorkspaceId()
    return workspaceStreamingContent.value.get(workspaceId) || ''
  }

  /**
   * 获取当前workspace的流式内容（响应式）
   */
  const streamingContent = computed(() => getCurrentStreamingContent())

  /**
   * 获取当前workspace的流式缓冲区
   */
  const getCurrentStreamBuffers = (): Map<string, {
    content: string
    reasoning: string
    lastUpdate: number
  }> => {
    const workspaceId = getCurrentWorkspaceId()
    if (!workspaceStreamBuffers.value.has(workspaceId)) {
      workspaceStreamBuffers.value.set(workspaceId, new Map())
    }
    return workspaceStreamBuffers.value.get(workspaceId)!
  }

  /**
   * 获取当前workspace的流式缓冲区（响应式）
   */
  const streamBuffers = computed(() => getCurrentStreamBuffers())

  /**
   * 获取当前workspace的流式更新定时器
   */
  const getCurrentStreamUpdateTimers = (): Map<string, number> => {
    const workspaceId = getCurrentWorkspaceId()
    if (!workspaceStreamUpdateTimers.value.has(workspaceId)) {
      workspaceStreamUpdateTimers.value.set(workspaceId, new Map())
    }
    return workspaceStreamUpdateTimers.value.get(workspaceId)!
  }

  /**
   * 获取当前workspace的流式更新定时器（响应式）
   */
  const streamUpdateTimers = computed(() => getCurrentStreamUpdateTimers())

  /**
   * 获取当前workspace的工具调用流式缓冲区
   */
  const getCurrentToolCallStreamBuffers = (): Map<string, {
    partialArguments: string
    toolName: string
    lastUpdate: number
  }> => {
    const workspaceId = getCurrentWorkspaceId()
    if (!workspaceToolCallStreamBuffers.value.has(workspaceId)) {
      workspaceToolCallStreamBuffers.value.set(workspaceId, new Map())
    }
    return workspaceToolCallStreamBuffers.value.get(workspaceId)!
  }

  /**
   * 获取当前workspace的工具调用流式缓冲区（响应式）
   */
  const toolCallStreamBuffers = computed(() => getCurrentToolCallStreamBuffers())

  // --- Getters ---

  /**
   * 最后一条消息
   */
  const lastMessage = computed(() => {
    return messages.value[messages.value.length - 1] || null
  })

  /**
   * 消息总数
   */
  const messagesCount = computed(() => messages.value.length)

  /**
   * 按类型分组的消息
   */
  const messagesByType = computed(() => {
    const grouped: Record<string, ChatMessage[]> = {
      user: [],
      assistant: [],
      system: [],
      tool: [],
    }

    for (const message of messages.value) {
      const role = message.role
      if (!grouped[role]) {
        grouped[role] = []
      }
      grouped[role].push(message)
    }

    return grouped
  })

  /**
   * 思考步骤（从消息中提取）
   */
  const thinkingSteps = computed(() => {
    const steps: unknown[] = []
    for (const message of messages.value) {
      for (const block of message.content) {
        if (block.type === ContentType.THINKING) {
          steps.push(...(block as unknown).steps)
        } else if (block.type === ContentType.REASONING) {
          steps.push({
            step_id: message.id,
            thought: (block as unknown).reasoning,
            status: 'completed'
          })
        }
      }
    }
    return steps
  })

  // --- Actions ---

  /**
   * 添加消息 - 使用替换数组确保 shallowRef 响应式更新
   *
   * ⚠️ 物理隔离原则：
   * 1. 必须明确知道消息属于哪个workspace
   * 2. 如果无法确定workspace_id，抛出异常
   * 3. 不允许"当前workspace"模糊fallback，防止数据串台
   */
  const addMessage = (message: ChatMessage, workspaceId?: string): void => {
    // 策略1: 使用传入的workspaceId参数
    let targetWorkspaceId = workspaceId

    // 策略2: 如果没有传入workspaceId，尝试从消息的sessionId查找
    if (!targetWorkspaceId && message.sessionId) {
      targetWorkspaceId = getWorkspaceIdBySession(message.sessionId) || undefined
    }

    // 严格检查：如果仍然无法确定workspace_id，抛出异常
    if (!targetWorkspaceId) {
      const errorDetails = {
        messageId: message.id,
        role: message.role,
        sessionId: message.sessionId,
        timestamp: message.timestamp,
        messageContent: message.content
      }

      logger.error('[MessageStore] ❌ ERROR: Cannot determine workspace_id for message::', errorDetails)
      // 抛出异常而不是静默返回
      throw new Error(
        `[MessageStore] Cannot determine workspace_id for message ${message.id}. ` +
        `Session ID: ${message.sessionId}. ` +
        `Message will NOT be added to prevent workspace data crossover. ` +
        `Please ensure the session→workspace mapping is properly initialized in ConnectionStore.`
      )
    }

    logger.debug(`[MessageStore] Adding message to workspace: ${targetWorkspaceId}`, {
      messageId: message.id,
      role: message.role,
      contentLength: message.content.reduce((sum, c) => sum + (('text' in c) ? c.text?.length || 0 : 0), 0),
      contentTypes: message.content.map(c => c.type),
      currentWorkspaceId: getCurrentWorkspaceId(),
      targetWorkspaceId
    })

    // 确保目标workspace的消息数组存在
    if (!workspaceMessages.value.has(targetWorkspaceId)) {
      workspaceMessages.value.set(targetWorkspaceId, [])
    }
    const currentMessages = workspaceMessages.value.get(targetWorkspaceId)!

    workspaceMessages.value.set(targetWorkspaceId, [...currentMessages, message])
  }

  /**
   * 批量添加消息 - 使用替换数组确保 shallowRef 响应式更新
   */
  const addMessages = (newMessages: ChatMessage[]): void => {
    const workspaceId = getCurrentWorkspaceId()
    const currentMessages = getCurrentMessages()
    workspaceMessages.value.set(workspaceId, [...currentMessages, ...newMessages])
  }

  /**
   * 更新消息 - 使用替换数组确保 shallowRef 响应式更新
   *
   * 关键修复：
   * 1. 如果更新 content 数组，创建全新的数组副本
   * 2. 使用深拷贝确保 Vue 能检测到嵌套对象的变化
   */
  const updateMessage = (messageId: string, updates: Partial<ChatMessage>): void => {
    const workspaceId = getCurrentWorkspaceId()
    const currentMessages = getCurrentMessages()
    const index = currentMessages.findIndex(m => m.id === messageId)

    if (index !== -1) {
      const newMessages = [...currentMessages]
      const existingMessage = newMessages[index]

      // ✅ 关键修复：如果有 content 更新，确保创建全新的 content 数组
      if (updates.content) {
        // 创建全新的消息对象和 content 数组
        newMessages[index] = {
          ...existingMessage,
          ...updates,
          // 强制创建新的 content 数组引用
          content: [...updates.content]
        }
        logger.debug(`[MessageStore] Updated message ${messageId} with new content array`, {
          old_content_length: existingMessage.content?.length || 0,
          new_content_length: updates.content.length,
          content_types: updates.content.map(c => c.type)
        })
      } else {
        // 没有 content 更新，正常合并
        newMessages[index] = { ...existingMessage, ...updates }
        logger.debug(`[MessageStore] Updated message ${messageId} (no content change)`)
      }

      workspaceMessages.value.set(workspaceId, newMessages)
    } else {
      logger.warn(`[MessageStore] ⚠️ Message ${messageId} not found for update`)
    }
  }

  /**
   * 删除消息 - 使用替换数组确保 shallowRef 响应式更新
   */
  const removeMessage = (messageId: string): void => {
    const workspaceId = getCurrentWorkspaceId()
    const currentMessages = getCurrentMessages()
    workspaceMessages.value.set(workspaceId, currentMessages.filter(m => m.id !== messageId))
  }

  /**
   * 清空当前workspace的所有消息
   */
  const clearMessages = (): void => {
    const workspaceId = getCurrentWorkspaceId()
    workspaceMessages.value.set(workspaceId, [])
    workspaceThinking.value.set(workspaceId, '')
    workspaceStreamingContent.value.set(workspaceId, '')

    const currentBuffers = getCurrentStreamBuffers()
    currentBuffers.clear()

    // 清除所有定时器
    const currentTimers = getCurrentStreamUpdateTimers()
    for (const timer of currentTimers.values()) {
      clearTimeout(timer)
    }
    currentTimers.clear()
  }

  /**
   * 根据ID获取消息
   */
  const getMessageById = (messageId: string): ChatMessage | undefined => {
    const currentMessages = getCurrentMessages()
    return currentMessages.find(m => m.id === messageId)
  }

  /**
   * 触发消息列表更新（用于 shallowRef 手动触发响应式）
   */
  const triggerMessagesUpdate = (): void => {
    const workspaceId = getCurrentWorkspaceId()
    triggerRef(workspaceMessages.value.get(workspaceId))
  }

  /**
   * 追加流式内容
   */
  const appendStreamingContent = (content: string): void => {
    const workspaceId = getCurrentWorkspaceId()
    const currentContent = getCurrentStreamingContent()
    workspaceStreamingContent.value.set(workspaceId, currentContent + content)
  }

  /**
   * 清空流式内容
   */
  const clearStreamingContent = (): void => {
    const workspaceId = getCurrentWorkspaceId()
    workspaceStreamingContent.value.set(workspaceId, '')
  }

  /**
   * 设置当前思考内容
   */
  const setThinking = (thinking: string): void => {
    const workspaceId = getCurrentWorkspaceId()
    workspaceThinking.value.set(workspaceId, thinking)
  }

  /**
   * 追加思考内容
   */
  const appendThinking = (thinking: string): void => {
    const workspaceId = getCurrentWorkspaceId()
    const currentThinking = getCurrentThinking()
    workspaceThinking.value.set(workspaceId, currentThinking + thinking)
  }

  /**
   * 初始化流式消息缓冲区
   */
  const initStreamBuffer = (messageId: string): void => {
    const currentBuffers = getCurrentStreamBuffers()
    currentBuffers.set(messageId, {
      content: '',
      reasoning: '',
      lastUpdate: Date.now()
    })
  }

  /**
   * 更新流式消息缓冲区
   */
  const updateStreamBuffer = (messageId: string, type: 'content' | 'reasoning', data: string): void => {
    const currentBuffers = getCurrentStreamBuffers()
    const buffer = currentBuffers.get(messageId)
    if (buffer) {
      if (type === 'content') {
        buffer.content += data
      } else if (type === 'reasoning') {
        buffer.reasoning += data
      }
      buffer.lastUpdate = Date.now()
    }
  }

  /**
   * 获取流式消息缓冲区
   */
  const getStreamBuffer = (messageId: string) => {
    const currentBuffers = getCurrentStreamBuffers()
    return currentBuffers.get(messageId)
  }

  /**
   * 清除流式消息缓冲区
   */
  const clearStreamBuffer = (messageId: string): void => {
    const currentBuffers = getCurrentStreamBuffers()
    currentBuffers.delete(messageId)

    const currentTimers = getCurrentStreamUpdateTimers()
    const timer = currentTimers.get(messageId)
    if (timer) {
      clearTimeout(timer)
      currentTimers.delete(messageId)
    }
  }

  /**
   * 设置流式更新定时器
   */
  const setStreamUpdateTimer = (messageId: string, timer: number): void => {
    const currentTimers = getCurrentStreamUpdateTimers()
    currentTimers.set(messageId, timer)
  }

  /**
   * 创建新的消息对象
   */
  const createMessage = (
    role: 'user' | 'assistant' | 'system' | 'tool',
    content: ContentBlock[],
    metadata?: unknown
  ): ChatMessage => {
    return {
      id: uuidv4(),
      role,
      timestamp: new Date().toISOString(),
      content,
      metadata
    }
  }

  // --- 消息处理辅助方法 ---

  /**
   * 获取或创建流式消息缓冲区
   */
  const getOrCreateStreamBuffer = (taskId: string): { content: string; reasoning: string; lastUpdate: number } => {
    const currentBuffers = getCurrentStreamBuffers()
    if (!currentBuffers.has(taskId)) {
      currentBuffers.set(taskId, {
        content: '',
        reasoning: '',
        lastUpdate: Date.now()
      })
    }
    return currentBuffers.get(taskId)!
  }

  /**
   * 更新流式消息到UI（批量更新）
   */
  const flushStreamBuffer = (taskId: string) => {
    const currentBuffers = getCurrentStreamBuffers()
    const buffer = currentBuffers.get(taskId)
    if (!buffer) return

    const chatMessage = getOrCreateAssistantMessage(taskId)

    // 更新内容块
    if (buffer.content) {
      const textBlock = chatMessage.content.find(
        c => c.type === ContentType.TEXT
      ) as TextContentBlock | undefined

      if (textBlock) {
        textBlock.text = buffer.content
      } else {
        chatMessage.content.push({
          type: ContentType.TEXT,
          text: buffer.content
        } as TextContentBlock)
      }
    }

    // 更新推理块
    if (buffer.reasoning) {
      const thinkingBlock = chatMessage.content.find(
        c => c.type === ContentType.THINKING
      ) as ThinkingContentBlock | undefined

      if (thinkingBlock) {
        if (thinkingBlock.steps.length > 0) {
          thinkingBlock.steps[0].thought = buffer.reasoning
        } else {
          thinkingBlock.steps.push({
            step_id: uuidv4(),
            thought: buffer.reasoning,
            status: 'in_progress'
          })
        }
      } else {
        chatMessage.content.push({
          type: ContentType.THINKING,
          steps: [{
            step_id: uuidv4(),
            thought: buffer.reasoning,
            status: 'in_progress'
          }]
        } as ThinkingContentBlock)
      }
    }

    // 清除定时器
    const currentTimers = getCurrentStreamUpdateTimers()
    const timerId = currentTimers.get(taskId)
    if (timerId) {
      clearTimeout(timerId)
      currentTimers.delete(taskId)
    }
  }

  /**
   * 调度流式消息更新（延迟执行）
   */
  const scheduleStreamUpdate = (taskId: string) => {
    const currentTimers = getCurrentStreamUpdateTimers()

    // 清除现有定时器
    const existingTimer = currentTimers.get(taskId)
    if (existingTimer) {
      clearTimeout(existingTimer)
    }

    // 设置新的定时器
    const timerId = setTimeout(() => {
      flushStreamBuffer(taskId)
    }, STREAM_UPDATE_INTERVAL) as unknown as number

    currentTimers.set(taskId, timerId)
  }

  /**
   * 获取或创建助手消息
   */
  const getOrCreateAssistantMessage = (
    taskId: string,
    workspaceId?: string
  ): ChatMessage => {
    if (!taskId) {
      logger.error('[getOrCreateAssistantMessage] called with empty taskId')
      taskId = uuidv4()
    }

    // 使用传入的workspaceId或当前workspaceId
    const targetWorkspaceId = workspaceId || getCurrentWorkspaceId()

    // 获取目标workspace的消息
    if (!workspaceMessages.value.has(targetWorkspaceId)) {
      workspaceMessages.value.set(targetWorkspaceId, [])
    }
    const currentMessages = workspaceMessages.value.get(targetWorkspaceId)!

    let message = currentMessages.find(m => m.role === MessageRole.ASSISTANT && m.taskId === taskId)
    if (!message) {
      const msgId = uuidv4()
      message = {
        id: msgId,
        role: MessageRole.ASSISTANT,
        timestamp: new Date().toISOString(),
        content: [],
        taskId: taskId,
        messageId: msgId  // ✅ 设置messageId
      }
      workspaceMessages.value.set(targetWorkspaceId, [...currentMessages, message])
    }
    return message
  }

  // === Helper functions for message conversion ===

  /**
   * Map backend role to frontend MessageRole
   */
  const mapMessageRole = (role: string): MessageRole => {
    switch (role) {
      case 'user':
        return MessageRole.USER
      case 'assistant':
        return MessageRole.ASSISTANT
      case 'system':
        return MessageRole.SYSTEM
      case 'tool':
        return MessageRole.TOOL
      default:
        return MessageRole.USER
    }
  }

  /**
   * Parse tool result from JSON or plain text
   */
  const parseToolResult = (content: string | object): unknown => {
    if (typeof content === 'string' && content.trim()) {
      try {
        return JSON.parse(content)
      } catch {
        logger.warn('[parseToolResult] Failed to parse as JSON, treating as text')
        return { result: content }
      }
    } else if (typeof content === 'object') {
      return content
    }
    return null
  }

  /**
   * Process tool calls and add to content blocks
   */
  const processToolCalls = (
    toolCalls: unknown[],
    contentBlocks: ContentBlock[]
  ): void => {
    if (!toolCalls || !Array.isArray(toolCalls) || toolCalls.length === 0) {
      return
    }

    for (const toolCall of toolCalls) {
      const toolCallId = toolCall.tool_call_id || toolCall.id || uuidv4()
      const toolName = toolCall.function?.name || toolCall.name || 'unknown'
      const toolInput = toolCall.function?.arguments || toolCall.arguments || toolCall.input || {}
      const status = toolCall.status || 'completed'
      const output = toolCall.output
      const error = toolCall.error

      // Add TOOL_CALL content block
      contentBlocks.push({
        type: ContentType.TOOL_CALL,
        toolCall: {
          tool_call_id: toolCallId,
          tool_name: toolName,
          tool_input: toolInput,
          status: status,
          output: output,
          error: error
        }
      })

      // Add TOOL_RESULT if output exists
      if (output !== undefined && output !== null) {
        contentBlocks.push({
          type: ContentType.TOOL_RESULT,
          toolName: toolName,
          result: output,
          isError: false
        } as ToolResultContentBlock)
      }

      // Add ERROR block if error exists
      if (error) {
        contentBlocks.push({
          type: ContentType.ERROR,
          message: `工具调用失败: ${error}`,
          details: { toolCall }
        } as ErrorContentBlock)
      }

      // Extract completion text from attempt_completion tool
      if (toolName === 'attempt_completion' && toolInput) {
        const resultText = extractCompletionText(toolInput)
        if (resultText) {
          contentBlocks.push({
            type: ContentType.TEXT,
            text: resultText
          })
        }
      }
    }
  }

  /**
   * Extract completion text from attempt_completion tool input
   */
  const extractCompletionText = (toolInput: string | object): string => {
    let resultText = ''

    if (typeof toolInput === 'string') {
      try {
        const parsed = JSON.parse(toolInput)
        resultText = parsed.result || parsed.message || ''
      } catch {
        resultText = toolInput
      }
    } else if (typeof toolInput === 'object') {
      resultText = toolInput.result || toolInput.message || ''
    }

    return resultText.trim() || ''
  }

  /**
   * Process content field (string or array) and add to content blocks
   */
  const processContent = (
    content: string | object | unknown[],
    contentBlocks: ContentBlock[],
    toolCalls?: unknown[]
  ): void => {
    if (!content) {
      return
    }

    if (typeof content === 'string') {
      processStringContent(content, contentBlocks)
    } else if (Array.isArray(content)) {
      processArrayContent(content, contentBlocks, toolCalls)
    }
  }

  /**
   * Process string content
   */
  const processStringContent = (
    content: string,
    contentBlocks: ContentBlock[]
  ): void => {
    const trimmedContent = content.trim()

    // Try to parse as JSON
    let parsedContent = null
    if (trimmedContent.startsWith('{') || trimmedContent.startsWith('[')) {
      try {
        parsedContent = JSON.parse(trimmedContent)
      } catch {
        // Not valid JSON, keep as is
      }
    }

    // Handle task_completion type
    if (parsedContent && parsedContent.type === 'task_completion') {
      const displayContent = parsedContent.result || parsedContent.message || ''
      if (displayContent.trim()) {
        contentBlocks.push({
          type: ContentType.TEXT,
          text: displayContent
        })
      }
    }
    // Regular text content
    else if (trimmedContent) {
      contentBlocks.push({
        type: ContentType.TEXT,
        text: trimmedContent
      })
    }
  }

  /**
   * Process array content
   */
  const processArrayContent = (
    items: unknown[],
    contentBlocks: ContentBlock[],
    toolCalls?: unknown[]
  ): void => {
    for (const item of items) {
      if (typeof item === 'string') {
        if (item.trim()) {
          contentBlocks.push({
            type: ContentType.TEXT,
            text: item
          })
        }
      } else if (typeof item === 'object') {
        processArrayItem(item, contentBlocks, toolCalls)
      }
    }
  }

  /**
   * Process a single item from array content
   */
  const processArrayItem = (
    item: Record<string, unknown>,
    contentBlocks: ContentBlock[],
    toolCalls?: unknown[]
  ): void => {
    if (item.type === 'text' && item.text) {
      if (item.text.trim()) {
        contentBlocks.push({
          type: ContentType.TEXT,
          text: item.text
        })
      }
    }
    // Handle tool call in array
    else if (item.type === 'tool_call' || item.tool_call_id || item.function) {
      const toolCallId = item.tool_call_id || item.id
      const alreadyAdded = toolCalls?.some((tc: unknown) =>
        (tc.tool_call_id || tc.id) === toolCallId
      )

      if (!alreadyAdded) {
        const toolName = item.name || item.function?.name || 'unknown'
        const toolInput = item.arguments || item.function?.arguments || {}

        contentBlocks.push({
          type: ContentType.TOOL_CALL,
          toolCall: {
            tool_call_id: item.tool_call_id || item.id || uuidv4(),
            tool_name: toolName,
            tool_input: toolInput,
            status: 'completed'
          }
        })

        if (item.output) {
          contentBlocks.push({
            type: ContentType.TOOL_RESULT,
            toolName: toolName,
            result: item.output,
            isError: false
          } as ToolResultContentBlock)
        }
      }
    } else if (item.type === 'tool_result') {
      contentBlocks.push({
        type: ContentType.TOOL_RESULT,
        toolName: item.name || 'unknown',
        result: item.content || item.result || '',
        isError: false
      })
    } else if (item.type === 'error') {
      contentBlocks.push({
        type: ContentType.ERROR,
        message: item.message || 'Unknown error',
        details: item.details
      })
    } else {
      // Fallback: stringify unknown items
      const textStr = JSON.stringify(item)
      if (textStr.trim()) {
        contentBlocks.push({
          type: ContentType.TEXT,
          text: textStr
        })
      }
    }
  }

  /**
   * 将后端消息转换为前端ChatMessage格式
   */
  const convertBackendMessageToChatMessage = (backendMsg: unknown): ChatMessage | null => {
    try {
      logger.debug('[convertBackendMessage] Input message:', backendMsg)
      const role = backendMsg.role || 'user'
      const content = backendMsg.content || ''
      const toolCalls = backendMsg.tool_calls

      const id = backendMsg.id || uuidv4()
      const timestamp = backendMsg.timestamp || new Date().toISOString()
      const messageRole = mapMessageRole(role)

      const contentBlocks: ContentBlock[] = []

      // Handle role='tool' messages
      if (role === 'tool') {
        return createToolMessage(id, messageRole, timestamp, backendMsg, content, contentBlocks)
      }

      // Process tool calls from assistant messages
      processToolCalls(toolCalls, contentBlocks)

      // Process content field
      processContent(content, contentBlocks, toolCalls)

      // Early return for task_completion messages
      if (isTaskCompletion(content)) {
        return {
          id,
          role: messageRole,
          timestamp,
          content: contentBlocks,
          taskId: backendMsg.task_id,
          sessionId: backendMsg.session_id,
          messageId: backendMsg.id  // ✅ 使用后端消息的id作为messageId（用于Markdown/纯文本切换）
        }
      }

      // Add empty text block if no content
      if (contentBlocks.length === 0) {
        contentBlocks.push({
          type: ContentType.TEXT,
          text: ''
        })
      }

      return {
        id,
        role: messageRole,
        timestamp,
        content: contentBlocks,
        taskId: backendMsg.task_id,
        sessionId: backendMsg.session_id,
        messageId: backendMsg.id  // ✅ 使用后端消息的id作为messageId（用于Markdown/纯文本切换）
      }
    } catch (error) {
      logger.error('[convertBackendMessage] Error converting message:', error, backendMsg)
      return null
    }
  }

  /**
   * Create tool message
   */
  const createToolMessage = (
    id: string,
    messageRole: MessageRole,
    timestamp: string,
    backendMsg: unknown,
    content: string | object,
    contentBlocks: ContentBlock[]
  ): ChatMessage => {
    const toolResult = parseToolResult(content)
    const toolName = 'unknown'
    const toolCallId = backendMsg.tool_call_id || backendMsg.id || uuidv4()

    if (toolResult && typeof toolResult === 'object') {
      const resultData = toolResult.result || toolResult.output || content

      contentBlocks.push({
        type: ContentType.TOOL_EXECUTION,
        toolName: toolName,
        toolCallId: toolCallId,
        status: toolResult.success !== false ? 'completed' : 'failed',
        input: {},
        output: resultData,
        error: toolResult.success === false ? (toolResult.error || 'Tool execution failed') : undefined,
        startTime: backendMsg.timestamp,
        endTime: backendMsg.timestamp
      } as ToolExecutionContentBlock)
    }

    // Add default text block if no content
    if (contentBlocks.length === 0) {
      contentBlocks.push({
        type: ContentType.TEXT,
        text: typeof content === 'string' ? content : JSON.stringify(content)
      })
    }

    return {
      id,
      role: messageRole,
      timestamp,
      content: contentBlocks,
      taskId: backendMsg.task_id
    }
  }

  /**
   * Check if content is task_completion type
   */
  const isTaskCompletion = (content: string | object): boolean => {
    if (typeof content !== 'string') return false

    const trimmedContent = content.trim()
    if (!trimmedContent.startsWith('{')) return false

    try {
      const parsed = JSON.parse(trimmedContent)
      return parsed && parsed.type === 'task_completion'
    } catch {
      return false
    }
  }

  /**
   * 创建安全的消息处理器（带错误捕获）
   */
  const createSafeMessageHandler = (
    handlerName: string,
    handler: (message: WebSocketMessage) => void
  ) => {
    return (message: WebSocketMessage) => {
      try {
        handler(message)
      } catch (error) {
        logger.error(`[${handlerName}] Error processing message:`, error)
        logger.error(`[${handlerName}] Message that caused error:`, message)

        // 添加错误消息到当前workspace的聊天记录
        addMessage({
          id: uuidv4(),
          role: MessageRole.SYSTEM,
          timestamp: new Date().toISOString(),
          content: [{
            type: ContentType.ERROR,
            message: `消息处理错误 (${handlerName}): ${error instanceof Error ? error.message : String(error)}`
          }],
        })
      }
    }
  }

  // --- 返回store接口 ---

  return {
    // State
    messages,
    currentThinking,
    streamingContent,
    streamBuffers,
    streamUpdateTimers,
    STREAM_UPDATE_INTERVAL,
    toolCallStreamBuffers,

    // Getters
    lastMessage,
    messagesCount,
    messagesByType,
    thinkingSteps,

    // Actions
    addMessage,
    addMessages,
    updateMessage,
    removeMessage,
    clearMessages,
    getMessageById,
    triggerMessagesUpdate,
    appendStreamingContent,
    clearStreamingContent,
    setThinking,
    appendThinking,
    initStreamBuffer,
    updateStreamBuffer,
    getStreamBuffer,
    clearStreamBuffer,
    setStreamUpdateTimer,
    createMessage,

    // 消息处理辅助方法
    getOrCreateStreamBuffer,
    flushStreamBuffer,
    scheduleStreamUpdate,
    getOrCreateAssistantMessage,
    convertBackendMessageToChatMessage,
    createSafeMessageHandler,
  }
})
