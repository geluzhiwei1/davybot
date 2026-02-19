/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * TaskStore - 任务和任务图管理
 *
 * 职责：
 * - 当前任务管理
 * - 任务图数据管理
 * - 任务节点进度
 */

import { ref, computed } from 'vue'
import { logger } from '@/utils/logger'

import { defineStore } from 'pinia'
import type { WebSocketMessage } from '@/types/websocket'
import { MessageType } from '@/types/websocket'
import type {
  TaskStatusUpdateMessage,
  TaskGraphUpdateMessage,
  TaskNodeStartMessage,
  TaskNodeProgressMessage,
  TaskNodeCompleteMessage
} from '@/types/websocket'
import { useParallelTasksStore } from './parallelTasks'
import { useWorkspaceStore as _useWorkspaceStore } from './workspace'

export const useTaskStore = defineStore('task', () => {
  // --- Helper function to get current workspaceId ---
  const getCurrentWorkspaceId = () => {
    const workspaceStore = _useWorkspaceStore()
    return workspaceStore.currentWorkspaceId || 'default'
  }

  // 获取parallelTasks store实例
  const parallelTasksStore = useParallelTasksStore()

  // --- State (按workspace隔离) ---

  /**
   * 当前任务ID映射（按workspace隔离）
   */
  const workspaceCurrentTaskId = ref<Map<string, string | null>>(new Map())

  /**
   * 任务图数据映射（按workspace隔离）
   */
  const workspaceTaskGraphData = ref<Map<string, unknown>>(new Map())

  /**
   * 任务图统计映射（按workspace隔离）
   */
  const workspaceTaskGraphStats = ref<Map<string, unknown>>(new Map())

  /**
   * 活跃的节点映射（按workspace隔离）
   */
  const workspaceActiveNodes = ref<Map<string, string[]>>(new Map())

  /**
   * 已完成的节点映射（按workspace隔离）
   */
  const workspaceCompletedNodes = ref<Map<string, string[]>>(new Map())

  // --- Helper functions to get current workspace state ---

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
   * 获取当前workspace的taskGraphData
   */
  const getTaskGraphData = (): unknown => {
    const workspaceId = getCurrentWorkspaceId()
    return workspaceTaskGraphData.value.get(workspaceId)
  }

  /**
   * 获取当前workspace的taskGraphData（响应式）
   */
  const taskGraphData = computed(() => getTaskGraphData())

  /**
   * 获取当前workspace的taskGraphStats
   */
  const getTaskGraphStats = (): unknown => {
    const workspaceId = getCurrentWorkspaceId()
    return workspaceTaskGraphStats.value.get(workspaceId)
  }

  /**
   * 获取当前workspace的taskGraphStats（响应式）
   */
  const taskGraphStats = computed(() => getTaskGraphStats())

  /**
   * 获取当前workspace的activeNodes
   */
  const getActiveNodes = (): string[] => {
    const workspaceId = getCurrentWorkspaceId()
    if (!workspaceActiveNodes.value.has(workspaceId)) {
      workspaceActiveNodes.value.set(workspaceId, [])
    }
    return workspaceActiveNodes.value.get(workspaceId)!
  }

  /**
   * 获取当前workspace的activeNodes（响应式）
   */
  const activeNodes = computed(() => getActiveNodes())

  /**
   * 获取当前workspace的completedNodes
   */
  const getCompletedNodes = (): string[] => {
    const workspaceId = getCurrentWorkspaceId()
    if (!workspaceCompletedNodes.value.has(workspaceId)) {
      workspaceCompletedNodes.value.set(workspaceId, [])
    }
    return workspaceCompletedNodes.value.get(workspaceId)!
  }

  /**
   * 获取当前workspace的completedNodes（响应式）
   */
  const completedNodes = computed(() => getCompletedNodes())

  // --- Getters ---

  /**
   * 是否有活跃任务
   */
  const hasActiveTask = computed(() => !!getCurrentTaskId())

  /**
   * 任务进度百分比
   */
  const taskProgress = computed(() => {
    const stats = getTaskGraphStats()
    if (!stats) return 0
    const total = stats.total_tasks || 0
    const completed = stats.status_counts?.completed || 0
    return total > 0 ? (completed / total) * 100 : 0
  })

  // --- Actions ---

  /**
   * 开始任务
   */
  const startTask = (taskId: string): void => {
    const workspaceId = getCurrentWorkspaceId()
    workspaceCurrentTaskId.value.set(workspaceId, taskId)
  }

  /**
   * 完成任务
   */
  const completeTask = (): void => {
    const workspaceId = getCurrentWorkspaceId()
    workspaceCurrentTaskId.value.set(workspaceId, null)
  }

  /**
   * 更新任务状态
   */
  const updateTaskStatus = (taskId: string, status: string): void => {
    // 触发状态更新事件
    logger.debug(`Task ${taskId} status updated to ${status}`)
  }

  /**
   * 更新任务节点进度
   */
  const updateNodeProgress = (nodeId: string): void => {
    const workspaceId = getCurrentWorkspaceId()
    const currentActive = getActiveNodes()
    if (!currentActive.includes(nodeId)) {
      workspaceActiveNodes.value.set(workspaceId, [...currentActive, nodeId])
    }
  }

  /**
   * 完成任务节点
   */
  const completeNode = (nodeId: string): void => {
    const workspaceId = getCurrentWorkspaceId()
    const currentActive = getActiveNodes()
    const currentCompleted = getCompletedNodes()

    const index = currentActive.indexOf(nodeId)
    if (index !== -1) {
      workspaceActiveNodes.value.set(workspaceId, currentActive.filter((_, i) => i !== index))
    }
    if (!currentCompleted.includes(nodeId)) {
      workspaceCompletedNodes.value.set(workspaceId, [...currentCompleted, nodeId])
    }
  }

  /**
   * 更新任务图
   */
  const updateTaskGraph = (update: unknown): void => {
    const workspaceId = getCurrentWorkspaceId()
    if (update.statistics) {
      workspaceTaskGraphStats.value.set(workspaceId, update.statistics)
    }
    if (update.task_info) {
      // 更新任务信息
      logger.debug('Task info updated:', update.task_info)
    }
  }

  /**
   * 设置任务图数据
   */
  const setTaskGraphData = (data: unknown): void => {
    const workspaceId = getCurrentWorkspaceId()
    workspaceTaskGraphData.value.set(workspaceId, data)
  }

  /**
   * 清空当前workspace的任务图数据
   */
  const clearTaskGraph = (): void => {
    const workspaceId = getCurrentWorkspaceId()
    workspaceCurrentTaskId.value.set(workspaceId, null)
    workspaceTaskGraphData.value.set(workspaceId, null)
    workspaceTaskGraphStats.value.set(workspaceId, null)
    workspaceActiveNodes.value.set(workspaceId, [])
    workspaceCompletedNodes.value.set(workspaceId, [])
  }

  // --- 消息处理器 ---

  /**
   * 处理任务状态更新消息
   */
  const handleTaskStatusUpdate = (message: WebSocketMessage) => {
    if (message.type !== MessageType.TASK_STATUS_UPDATE) return
    const statusUpdateMessage = message as TaskStatusUpdateMessage

    logger.debug('Task status update:', statusUpdateMessage)
    // 更新当前任务ID
    if (statusUpdateMessage.task_id) {
      const workspaceId = getCurrentWorkspaceId()
      workspaceCurrentTaskId.value.set(workspaceId, statusUpdateMessage.task_id)
    }

    // 触发自定义事件，通知组件更新任务状态
    const event = new CustomEvent('task-status-update', {
      detail: {
        taskId: statusUpdateMessage.task_id,
        graphId: statusUpdateMessage.graph_id,
        oldStatus: statusUpdateMessage.old_status,
        newStatus: statusUpdateMessage.new_status,
        timestamp: statusUpdateMessage.timestamp
      }
    })
    window.dispatchEvent(event)
  }

  /**
   * 处理任务图更新消息
   */
  const handleTaskGraphUpdate = (message: WebSocketMessage) => {
    if (message.type !== MessageType.TASK_GRAPH_UPDATE) return
    const graphUpdateMessage = message as TaskGraphUpdateMessage

    logger.debug('Task graph update:', graphUpdateMessage)
    // 更新任务图统计
    if (graphUpdateMessage.data?.statistics) {
      const workspaceId = getCurrentWorkspaceId()
      workspaceTaskGraphStats.value.set(workspaceId, graphUpdateMessage.data.statistics)
    }

    // 触发自定义事件，通知组件更新任务图
    const event = new CustomEvent('task-graph-update', {
      detail: {
        graphId: graphUpdateMessage.graph_id,
        updateType: graphUpdateMessage.update_type,
        data: graphUpdateMessage.data,
        timestamp: graphUpdateMessage.timestamp
      }
    })
    window.dispatchEvent(event)
  }

  /**
   * 处理任务节点开始消息
   */
  const handleTaskNodeStart = (message: WebSocketMessage) => {
    if (message.type !== MessageType.TASK_NODE_START) return
    const nodeStart = message as TaskNodeStartMessage

    // 添加到活跃节点
    const workspaceId = getCurrentWorkspaceId()
    const currentActive = getActiveNodes()
    if (!currentActive.includes(nodeStart.task_node_id)) {
      workspaceActiveNodes.value.set(workspaceId, [...currentActive, nodeStart.task_node_id])
    }

    // 同步到parallelTasks store
    parallelTasksStore.handleTaskNodeStart({
      task_id: nodeStart.task_node_id,
      task_node_id: nodeStart.task_node_id,
      node_type: nodeStart.node_type || 'unknown',
      description: nodeStart.description || ''
    })

    // 触发自定义事件供监控界面使用
    window.dispatchEvent(new CustomEvent('task-node-start', {
      detail: nodeStart
    }))
  }

  /**
   * 处理任务节点进度消息
   */
  const handleTaskNodeProgress = (message: WebSocketMessage) => {
    if (message.type !== MessageType.TASK_NODE_PROGRESS) return
    const nodeProgress = message as TaskNodeProgressMessage

    // 确保节点在活跃列表中
    const workspaceId = getCurrentWorkspaceId()
    const currentActive = getActiveNodes()
    if (!currentActive.includes(nodeProgress.task_node_id)) {
      workspaceActiveNodes.value.set(workspaceId, [...currentActive, nodeProgress.task_node_id])
    }

    // 同步到parallelTasks store
    parallelTasksStore.handleTaskNodeProgress({
      task_id: nodeProgress.task_node_id,
      progress: nodeProgress.progress,
      message: nodeProgress.message
    })

    // 触发自定义事件供监控界面使用
    window.dispatchEvent(new CustomEvent('task-node-progress', {
      detail: nodeProgress
    }))
  }

  /**
   * 处理任务节点完成消息
   */
  const handleTaskNodeComplete = (message: WebSocketMessage) => {
    if (message.type !== MessageType.TASK_NODE_COMPLETE) return
    const nodeComplete = message as TaskNodeCompleteMessage

    // 从活跃节点移除并添加到已完成节点
    const workspaceId = getCurrentWorkspaceId()
    const currentActive = getActiveNodes()
    const currentCompleted = getCompletedNodes()

    const index = currentActive.indexOf(nodeComplete.task_node_id)
    if (index !== -1) {
      workspaceActiveNodes.value.set(workspaceId, currentActive.filter((_, i) => i !== index))
    }
    if (!currentCompleted.includes(nodeComplete.task_node_id)) {
      workspaceCompletedNodes.value.set(workspaceId, [...currentCompleted, nodeComplete.task_node_id])
    }

    // 同步到parallelTasks store
    parallelTasksStore.handleTaskNodeComplete({
      task_id: nodeComplete.task_node_id,
      result: nodeComplete.result
    })

    // 触发自定义事件供监控界面使用
    window.dispatchEvent(new CustomEvent('task-node-complete', {
      detail: nodeComplete
    }))

    // ✅ 自动刷新：触发文件树和已打开文件的内容刷新
    logger.debug('[TaskStore] Task node completed, triggering auto-refresh for workspace files')
    window.dispatchEvent(new CustomEvent('task-node-complete-refresh', {
      detail: {
        workspaceId: workspaceId,
        taskNodeId: nodeComplete.task_node_id
      }
    }))
  }

  // --- 返回store接口 ---

  return {
    // State
    currentTaskId,
    taskGraphData,
    taskGraphStats,
    activeNodes,
    completedNodes,

    // Getters
    hasActiveTask,
    taskProgress,

    // Actions
    startTask,
    completeTask,
    updateTaskStatus,
    updateNodeProgress,
    completeNode,
    updateTaskGraph,
    setTaskGraphData,
    clearTaskGraph,

    // 消息处理器
    handleTaskStatusUpdate,
    handleTaskGraphUpdate,
    handleTaskNodeStart,
    handleTaskNodeProgress,
    handleTaskNodeComplete,
  }
})
