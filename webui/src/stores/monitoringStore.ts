/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * 三级AgentsStore
 * 管理 Agent → Task Graph → TODO List 的层级状态
 */

import { defineStore } from 'pinia'
import { logger } from '@/utils/logger'

import { ref, computed } from 'vue'
import type { ParallelTaskInfo } from '@/types/parallelTasks'
import type { TodoItemDetail } from '@/types/todos'

/**
 * Agents层级
 */
export enum MonitoringLevel {
  AGENTS_OVERVIEW = 'agents_overview',  // Level 1: 所有Agent概览
  TASK_GRAPH = 'task_graph',            // Level 2: 选中Agent的任务图
  TASK_NODE_TODOS = 'task_node_todos'   // Level 3: 选中任务节点的TODO列表
}

/**
 * Agents视图状态
 */
interface MonitoringViewState {
  currentLevel: MonitoringLevel
  selectedAgentId: string | null
  selectedTaskNodeId: string | null
}

export const useMonitoringStore = defineStore('monitoring', () => {
  // ==================== 状态 ====================

  // 当前视图层级和选择状态
  const viewState = ref<MonitoringViewState>({
    currentLevel: MonitoringLevel.AGENTS_OVERVIEW,
    selectedAgentId: null,
    selectedTaskNodeId: null
  })

  // 所有并行任务（从 parallelTasksStore 同步）
  const allAgents = ref<ParallelTaskInfo[]>([])

  // 当前选中Agent的任务节点列表
  const currentAgentTaskNodes = ref<Map<string, unknown>>(new Map())

  // 当前选中任务节点的TODO列表
  const currentNodeTodos = ref<TodoItemDetail[]>([])

  // 加载状态
  const loading = ref(false)
  const error = ref<string | null>(null)

  // ==================== 计算属性 ====================

  /**
   * 当前选中的Agent
   */
  const selectedAgent = computed(() => {
    if (!viewState.value.selectedAgentId) return null
    return allAgents.value.find(agent => agent.taskId === viewState.value.selectedAgentId)
  })

  /**
   * 当前选中的任务节点
   */
  const selectedTaskNode = computed(() => {
    if (!viewState.value.selectedTaskNodeId) return null
    return currentAgentTaskNodes.value.get(viewState.value.selectedTaskNodeId)
  })

  /**
   * Agent统计信息
   */
  const agentsStatistics = computed(() => {
    const total = allAgents.value.length
    const running = allAgents.value.filter(a => a.state === 'running').length
    const completed = allAgents.value.filter(a => a.state === 'completed').length
    const failed = allAgents.value.filter(a => a.state === 'failed').length

    return { total, running, completed, failed }
  })

  /**
   * 当前Agent的TODO统计
   */
  const currentAgentTodoStats = computed(() => {
    let total = 0
    let completed = 0
    let pending = 0
    let inProgress = 0

    for (const node of currentAgentTaskNodes.value.values()) {
      if (node.todos) {
        total += node.todos.length
        completed += node.todos.filter((t: TodoItemDetail) => t.status === 'completed').length
        pending += node.todos.filter((t: TodoItemDetail) => t.status === 'pending').length
        inProgress += node.todos.filter((t: TodoItemDetail) => t.status === 'in_progress').length
      }
    }

    return { total, completed, pending, inProgress }
  })

  /**
   * 面包屑导航文本
   */
  const breadcrumbText = computed(() => {
    const parts: string[] = ['所有 Agents']

    if (viewState.value.selectedAgentId) {
      const agent = selectedAgent.value
      parts.push(agent?.taskName || viewState.value.selectedAgentId.slice(0, 8))
    }

    if (viewState.value.selectedTaskNodeId) {
      const node = selectedTaskNode.value
      parts.push(node?.description || viewState.value.selectedTaskNodeId.slice(0, 8))
    }

    return parts.join(' → ')
  })

  // ==================== Actions ====================

  /**
   * 设置当前视图层级
   */
  function setCurrentLevel(level: MonitoringLevel): void {
    viewState.value.currentLevel = level

    // 根据层级自动清理下级选择
    if (level === MonitoringLevel.AGENTS_OVERVIEW) {
      viewState.value.selectedAgentId = null
      viewState.value.selectedTaskNodeId = null
      currentAgentTaskNodes.value.clear()
      currentNodeTodos.value = []
    } else if (level === MonitoringLevel.TASK_GRAPH) {
      viewState.value.selectedTaskNodeId = null
      currentNodeTodos.value = []
    }
  }

  /**
   * 选择Agent（进入Level 2）
   */
  function selectAgent(agentId: string): void {
    viewState.value.selectedAgentId = agentId
    viewState.value.currentLevel = MonitoringLevel.TASK_GRAPH
    logger.debug('[MonitoringStore] Agent selected:', agentId)
  }

  /**
   * 选择任务节点（进入Level 3）
   */
  function selectTaskNode(taskNodeId: string): void {
    viewState.value.selectedTaskNodeId = taskNodeId
    viewState.value.currentLevel = MonitoringLevel.TASK_NODE_TODOS
    logger.debug('[MonitoringStore] Task node selected:', taskNodeId)
  }

  /**
   * 返回上一级
   */
  function goBack(): void {
    if (viewState.value.currentLevel === MonitoringLevel.TASK_NODE_TODOS) {
      // 从Level 3返回到Level 2
      viewState.value.selectedTaskNodeId = null
      viewState.value.currentLevel = MonitoringLevel.TASK_GRAPH
      currentNodeTodos.value = []
    } else if (viewState.value.currentLevel === MonitoringLevel.TASK_GRAPH) {
      // 从Level 2返回到Level 1
      viewState.value.selectedAgentId = null
      viewState.value.currentLevel = MonitoringLevel.AGENTS_OVERVIEW
      currentAgentTaskNodes.value.clear()
    }
  }

  /**
   * 更新所有Agent列表
   */
  function updateAgents(agents: ParallelTaskInfo[]): void {
    allAgents.value = agents
    logger.debug('[MonitoringStore] Agents updated:', agents.length)
  }

  /**
   * 更新当前Agent的任务节点
   */
  function updateAgentTaskNodes(taskNodes: Map<string, unknown>): void {
    currentAgentTaskNodes.value = taskNodes
    logger.debug('[MonitoringStore] Task nodes updated:', taskNodes.size)
  }

  /**
   * 更新当前节点的TODO列表
   */
  function updateNodeTodos(todos: TodoItemDetail[]): void {
    currentNodeTodos.value = todos
    logger.debug('[MonitoringStore] Node TODOs updated:', todos.length)
  }

  /**
   * 重置视图状态
   */
  function reset(): void {
    viewState.value = {
      currentLevel: MonitoringLevel.AGENTS_OVERVIEW,
      selectedAgentId: null,
      selectedTaskNodeId: null
    }
    currentAgentTaskNodes.value.clear()
    currentNodeTodos.value = []
    error.value = null
    logger.debug('[MonitoringStore] View reset')
  }

  /**
   * 清空所有数据
   */
  function clear(): void {
    reset()
    allAgents.value = []
  }

  return {
    // 状态
    viewState,
    allAgents,
    currentAgentTaskNodes,
    currentNodeTodos,
    loading,
    error,

    // 计算属性
    selectedAgent,
    selectedTaskNode,
    agentsStatistics,
    currentAgentTodoStats,
    breadcrumbText,

    // Actions
    setCurrentLevel,
    selectAgent,
    selectTaskNode,
    goBack,
    updateAgents,
    updateAgentTaskNodes,
    updateNodeTodos,
    reset,
    clear
  }
})
