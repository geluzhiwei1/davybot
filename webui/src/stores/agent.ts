/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * AgentStore - Agent状态管理
 *
 * 职责：
 * - Agent执行状态
 * - Agent模式管理
 * - 思考状态管理
 * - Agent控制方法
 */

import { ref, computed } from 'vue'
import { logger } from '@/utils/logger'

import { defineStore } from 'pinia'

import {
  MessageType
} from '@/types/websocket'
import type {
  AgentStartMessage,
  AgentCompleteMessage,
  AgentModeSwitchMessage,
  AgentThinkingMessage,
  AgentStoppedMessage
} from '@/types/websocket'
import { useMonitoringStore } from './monitoringStore'
import { useParallelTasksStore } from './parallelTasks'
import { useWorkspaceStore as _useWorkspaceStore } from './workspace'
import { useMessageStore } from './messages'
import { ParallelTaskState } from '@/types/parallelTasks'

export const useAgentStore = defineStore('agent', () => {
  // --- Helper function to get current workspaceId ---
  const getCurrentWorkspaceId = () => {
    const workspaceStore = _useWorkspaceStore()
    return workspaceStore.currentWorkspaceId || 'default'
  }

  // --- State (按workspace隔离) ---

  /**
   * 是否正在思考映射（按workspace隔离）
   */
  const workspaceIsThinking = ref<Map<string, boolean>>(new Map())

  /**
   * 当前任务ID映射（按workspace隔离）
   */
  const workspaceCurrentTaskId = ref<Map<string, string | null>>(new Map())

  /**
   * Agent执行状态映射（按workspace隔离）
   */
  const workspaceAgentStatus = ref<Map<string, {
    isActive: boolean
    isPaused: boolean
    agentMode: string
    startTime: number | null
    thinking: string
    currentTask: string
  }>>(new Map())

  // --- Helper functions to get current workspace state ---

  /**
   * 获取当前workspace的isThinking状态
   */
  const getCurrentIsThinking = (): boolean => {
    const workspaceId = getCurrentWorkspaceId()
    if (!workspaceIsThinking.value.has(workspaceId)) {
      workspaceIsThinking.value.set(workspaceId, false)
    }
    return workspaceIsThinking.value.get(workspaceId)!
  }

  /**
   * 获取当前workspace的isThinking状态（响应式）
   */
  const isThinking = computed(() => getCurrentIsThinking())

  /**
   * 获取当前workspace的currentTaskId
   */
  const getCurrentTaskId = (): string | null => {
    const workspaceId = getCurrentWorkspaceId()
    if (!workspaceCurrentTaskId.value.has(workspaceId)) {
      workspaceCurrentTaskId.value.set(workspaceId, null)
    }
    return workspaceCurrentTaskId.value.get(workspaceId)!
  }

  /**
   * 获取当前workspace的currentTaskId（响应式）
   */
  const currentTaskId = computed(() => getCurrentTaskId())

  /**
   * 获取当前workspace的agentStatus
   */
  const getCurrentAgentStatus = (): {
    isActive: boolean
    isPaused: boolean
    agentMode: string
    startTime: number | null
    thinking: string
    currentTask: string
  } => {
    const workspaceId = getCurrentWorkspaceId()
    if (!workspaceAgentStatus.value.has(workspaceId)) {
      workspaceAgentStatus.value.set(workspaceId, {
        isActive: false,
        isPaused: false,
        agentMode: 'ask',
        startTime: null,
        thinking: '',
        currentTask: ''
      })
    }
    return workspaceAgentStatus.value.get(workspaceId)!
  }

  /**
   * 获取当前workspace的agentStatus（响应式）
   */
  const agentStatus = computed(() => getCurrentAgentStatus())

  // --- Getters ---

  /**
   * Agent信息
   */
  const agentInfo = computed(() => ({
    isActive: agentStatus.value.isActive,
    isPaused: agentStatus.value.isPaused,
    mode: agentStatus.value.agentMode,
    currentTask: agentStatus.value.currentTask,
    isThinking: isThinking.value,
  }))

  /**
   * Agent执行时长（毫秒）
   */
  const executionDuration = computed(() => {
    if (!agentStatus.value.startTime) return 0
    return Date.now() - agentStatus.value.startTime
  })

  // --- Actions ---

  /**
   * 开始Agent
   */
  const startAgent = (mode: string): void => {
    const workspaceId = getCurrentWorkspaceId()
    workspaceAgentStatus.value.set(workspaceId, {
      isActive: true,
      isPaused: false,
      agentMode: mode,
      startTime: Date.now(),
      thinking: '',
      currentTask: ''
    })
  }

  /**
   * 停止Agent
   */
  const stopAgent = (): void => {
    const workspaceId = getCurrentWorkspaceId()
    workspaceAgentStatus.value.set(workspaceId, {
      isActive: false,
      isPaused: false,
      agentMode: 'ask',
      startTime: null,
      thinking: '',
      currentTask: ''
    })
    workspaceIsThinking.value.set(workspaceId, false)
  }

  /**
   * 设置Agent模式
   */
  const setAgentMode = (mode: string): void => {
    const workspaceId = getCurrentWorkspaceId()
    const currentStatus = getCurrentAgentStatus()
    workspaceAgentStatus.value.set(workspaceId, {
      ...currentStatus,
      agentMode: mode
    })
  }

  /**
   * 更新Agent状态
   */
  const updateAgentStatus = (updates: Partial<{
    isActive: boolean
    isPaused: boolean
    agentMode: string
    startTime: number | null
    thinking: string
    currentTask: string
  }>): void => {
    const workspaceId = getCurrentWorkspaceId()
    const currentStatus = getCurrentAgentStatus()
    workspaceAgentStatus.value.set(workspaceId, {
      ...currentStatus,
      ...updates
    })
  }

  /**
   * 设置思考状态
   */
  const setThinking = (thinking: boolean): void => {
    const workspaceId = getCurrentWorkspaceId()
    workspaceIsThinking.value.set(workspaceId, thinking)
  }

  /**
   * 设置当前任务
   */
  const setCurrentTask = (task: string): void => {
    const workspaceId = getCurrentWorkspaceId()
    const currentStatus = getCurrentAgentStatus()
    workspaceAgentStatus.value.set(workspaceId, {
      ...currentStatus,
      currentTask: task
    })
  }

  /**
   * 更新思考内容
   */
  const updateThinking = (thinking: string): void => {
    const workspaceId = getCurrentWorkspaceId()
    const currentStatus = getCurrentAgentStatus()
    workspaceAgentStatus.value.set(workspaceId, {
      ...currentStatus,
      thinking: thinking
    })
  }

  // --- 消息处理器 ---

  /**
   * 处理Agent启动消息
   */
  const handleAgentStart = (message: WebSocketMessage) => {
    if (message.type !== MessageType.AGENT_START) return
    const agentStart = message as AgentStartMessage

    console.log('[AGENT] Agent started:', {
      agentMode: agentStart.agent_mode,
      userMessage: agentStart.user_message,
      workspaceId: agentStart.workspace_id,
      taskId: agentStart.task_id
    })

    // 设置当前任务ID
    const workspaceId = getCurrentWorkspaceId()
    workspaceCurrentTaskId.value.set(workspaceId, agentStart.task_id)

    // 在 parallelTasksStore 中创建任务记录
    const parallelTasksStore = useParallelTasksStore()
    parallelTasksStore.addTask(
      agentStart.task_id,
      agentStart.agent_mode,
      agentStart.user_message
    )
    parallelTasksStore.updateTaskState(agentStart.task_id, ParallelTaskState.RUNNING)
    logger.debug('[AGENT] Created task in parallelTasksStore:', agentStart.task_id)
    // 自动选择当前Agent，以便Agents显示
    const monitoringStore = useMonitoringStore()
    monitoringStore.selectAgent(agentStart.task_id)

    // 更新 Agent 状态
    workspaceAgentStatus.value.set(workspaceId, {
      isActive: true,
      isPaused: false,
      agentMode: agentStart.agent_mode,
      startTime: Date.now(),
      thinking: '',
      currentTask: agentStart.user_message
    })

    // 触发自定义事件
    window.dispatchEvent(new CustomEvent('agent-start', {
      detail: agentStart
    }))
  }

  /**
   * 处理Agent思考消息
   */
  const handleAgentThinking = (message: WebSocketMessage) => {
    if (message.type !== MessageType.AGENT_THINKING) return
    const agentThinking = message as AgentThinkingMessage

    console.log('[AGENT] Agent thinking:', {
      content: agentThinking.thinking_content.substring(0, 100) + '...',
      isComplete: agentThinking.is_complete
    })

    // 更新思考内容
    const workspaceId = getCurrentWorkspaceId()
    const currentStatus = getCurrentAgentStatus()
    workspaceAgentStatus.value.set(workspaceId, {
      ...currentStatus,
      thinking: agentThinking.thinking_content
    })

    // 触发自定义事件
    window.dispatchEvent(new CustomEvent('agent-thinking', {
      detail: agentThinking
    }))
  }

  /**
   * 处理Agent完成消息
   * 
   * 注意：此方法不再直接修改 isActive 状态
   * 因为 AGENT_COMPLETE 可能是针对子任务的
   * 控制面板的显示/隐藏由 parallelTasksStore.hasActiveTasks 决定
   */
  const handleAgentComplete = (message: WebSocketMessage) => {
    if (message.type !== MessageType.AGENT_COMPLETE) return
    const agentComplete = message as AgentCompleteMessage

    console.log('[AGENT] 🎉 Agent completed:', {
      resultSummary: agentComplete.result_summary,
      duration: agentComplete.total_duration_ms,
      tasksCompleted: agentComplete.tasks_completed,
      toolsUsed: agentComplete.tools_used,
      taskId: agentComplete.task_id
    })

    // 在 parallelTasksStore 中标记任务为完成
    if (agentComplete.task_id) {
      const parallelTasksStore = useParallelTasksStore()
      parallelTasksStore.updateTaskState(agentComplete.task_id, ParallelTaskState.COMPLETED)
      logger.debug('[AGENT] Marked task as completed in parallelTasksStore:', agentComplete.task_id)
    }

    // 注意：不再直接设置 isActive = false
    // 因为控制面板的显示由 parallelTasksStore.hasActiveTasks 决定
    // 只有当 parallelTasksStore 中没有任何活跃任务时，控制面板才会隐藏

    // 清除当前任务ID和Agent状态
    const workspaceId = getCurrentWorkspaceId()
    const currentTaskId = workspaceCurrentTaskId.value.get(workspaceId)

    // 只有当当前任务ID与完成的任务ID相同时，才清除任务ID和状态
    if (currentTaskId === agentComplete.task_id) {
      workspaceCurrentTaskId.value.set(workspaceId, null)

      // 同时重置 workspaceAgentStatus，避免状态残留
      workspaceAgentStatus.value.set(workspaceId, {
        isActive: false,
        isPaused: false,
        agentMode: 'ask',
        startTime: null,
        thinking: '',
        currentTask: ''
      })
    }

    logger.debug('[AGENT] ✅ Agent任务完成消息已处理，isActive状态由parallelTasksStore控制')

    // 🔥 重要：触发消息列表更新，确保assistant消息显示在UI上
    try {
      const messageStore = useMessageStore()
      messageStore.triggerMessagesUpdate()
      logger.debug('[AGENT] ✅ 触发了消息列表更新')
    } catch (error) {
      logger.error('[AGENT] ❌ 触发消息更新失败:', error)
    }

    // 触发自定义事件
    window.dispatchEvent(new CustomEvent('agent-complete', {
      detail: agentComplete
    }))
  }

  /**
   * 处理Agent模式切换消息
   */
  const handleAgentModeSwitch = (message: WebSocketMessage) => {
    if (message.type !== MessageType.AGENT_MODE_SWITCH) return
    const modeSwitch = message as AgentModeSwitchMessage

    console.log('[AGENT] Agent mode switched:', {
      oldMode: modeSwitch.old_mode,
      newMode: modeSwitch.new_mode,
      reason: modeSwitch.reason
    })

    // 更新 Agent 模式
    const workspaceId = getCurrentWorkspaceId()
    const currentStatus = getCurrentAgentStatus()
    workspaceAgentStatus.value.set(workspaceId, {
      ...currentStatus,
      agentMode: modeSwitch.new_mode
    })

    // 触发自定义事件
    window.dispatchEvent(new CustomEvent('agent-mode-switch', {
      detail: modeSwitch
    }))
  }

  /**
   * 处理Agent停止消息
   */
  const handleAgentStopped = (message: WebSocketMessage) => {
    if (message.type !== MessageType.AGENT_STOP) return
    const stoppedMessage = message as AgentStoppedMessage

    console.log('[AGENT] Agent stopped:', {
      taskId: stoppedMessage.task_id,
      stoppedAt: stoppedMessage.stopped_at,
      partial: stoppedMessage.partial,
      resultSummary: stoppedMessage.result_summary
    })

    // 清除当前任务ID并重置 Agent 状态
    const workspaceId = getCurrentWorkspaceId()
    workspaceCurrentTaskId.value.set(workspaceId, null)
    workspaceAgentStatus.value.set(workspaceId, {
      isActive: false,
      isPaused: false,
      agentMode: 'ask',
      startTime: null,
      thinking: '',
      currentTask: ''
    })

    // 触发自定义事件
    window.dispatchEvent(new CustomEvent('agent-stopped', {
      detail: stoppedMessage
    }))
  }

  // --- 带WebSocket通信的控制方法 ---

  /**
   * 发送停止Agent请求
   */
  const stopAgentAsync = async (
    taskId: string,
    sendFunc: (type: MessageType, payload: unknown) => Promise<void>
  ): Promise<void> => {
    if (!taskId) {
      logger.error('[AGENT] Cannot stop agent: no taskId')
      return
    }

    try {
      const payload = {
        task_id: taskId,
      }

      logger.debug('[AGENT] Sending stop request for task:', taskId)
      await sendFunc(MessageType.AGENT_STOP, payload)

      // 同时更新本地状态
      const workspaceId = getCurrentWorkspaceId()
      workspaceAgentStatus.value.set(workspaceId, {
        isActive: false,
        isPaused: false,
        agentMode: 'ask',
        startTime: null,
        thinking: '',
        currentTask: ''
      })
      workspaceIsThinking.value.set(workspaceId, false)
      workspaceCurrentTaskId.value.set(workspaceId, null)
    } catch (error) {
      logger.error('[AGENT] Failed to stop agent:', error)
    }
  }

  // --- 返回store接口 ---

  return {
    // State
    isThinking,
    currentTaskId,
    agentStatus,

    // Getters
    agentInfo,
    executionDuration,

    // Actions
    startAgent,
    stopAgent,
    setAgentMode,
    updateAgentStatus,
    setThinking,
    setCurrentTask,
    updateThinking,

    // 消息处理器
    handleAgentStart,
    handleAgentThinking,
    handleAgentComplete,
    handleAgentModeSwitch,
    handleAgentStopped,

    // 带WebSocket通信的控制方法
    stopAgentAsync,
  }
})
