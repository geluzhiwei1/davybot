/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * 并行任务状态管理Store
 * 管理所有并行执行的task node状态
 */

import { defineStore } from 'pinia'
import { logger } from '@/utils/logger'

import { ref, computed, reactive } from 'vue'
import { ParallelTaskState, getStatePriority } from '@/types/parallelTasks'
import type { ParallelTaskInfo, ParallelTasksStats, ParallelTodoItem, ParallelTaskProgress } from '@/types/parallelTasks'

export const useParallelTasksStore = defineStore('parallelTasks', () => {
  // 状态：并行任务Map
  const tasks = ref<Map<string, ParallelTaskInfo>>(new Map())

  // 配置：最大并行任务数
  const maxParallel = ref(2)

  // ==================== 计算属性 ====================

  /**
   * 获取统计信息
   */
  const stats = computed<ParallelTasksStats>(() => {
    const allTasks = Array.from(tasks.value.values())

    return {
      total: allTasks.length,
      active: allTasks.filter(t => t.state === ParallelTaskState.RUNNING).length,
      completed: allTasks.filter(t => t.state === ParallelTaskState.COMPLETED).length,
      failed: allTasks.filter(t => t.state === ParallelTaskState.FAILED).length,
      pending: allTasks.filter(t => t.state === ParallelTaskState.PENDING).length
    }
  })

  /**
   * 是否有活跃任务
   */
  const hasActiveTasks = computed(() => stats.value.active > 0)

  /**
   * 活跃任务列表（按创建时间排序）
   */
  const activeTasks = computed(() => {
    return Array.from(tasks.value.values())
      .filter(t => t.state === ParallelTaskState.RUNNING || t.state === ParallelTaskState.PENDING)
      .sort((a, b) => a.createdAt.getTime() - b.createdAt.getTime())
  })

  /**
   * 已完成任务列表
   */
  const completedTasks = computed(() => {
    return Array.from(tasks.value.values())
      .filter(t => t.state === ParallelTaskState.COMPLETED)
      .sort((a, b) => b.updatedAt.getTime() - a.updatedAt.getTime())
  })

  /**
   * 失败任务列表
   */
  const failedTasks = computed(() => {
    return Array.from(tasks.value.values())
      .filter(t => t.state === ParallelTaskState.FAILED)
      .sort((a, b) => b.updatedAt.getTime() - a.updatedAt.getTime())
  })

  /**
   * 所有任务列表（按状态和创建时间排序）
   */
  const allTasks = computed(() => {
    return Array.from(tasks.value.values()).sort((a, b) => {
      // ✅ 使用统一的优先级函数（KISS 原则）
      const priorityA = getStatePriority(a.state)
      const priorityB = getStatePriority(b.state)

      if (priorityA !== priorityB) {
        return priorityA - priorityB
      }

      return a.createdAt.getTime() - b.createdAt.getTime()
    })
  })

  // ==================== Actions ====================

  /**
   * 添加新任务或更新已存在的任务
   */
  function addTask(taskId: string, nodeType: string, description: string, taskNodeId?: string): void {
    // ✅ Fast Fail: 验证必需参数
    if (!taskId || taskId.trim() === '') {
      throw new Error('[ParallelTasks] taskId cannot be empty')
    }
    if (!nodeType || nodeType.trim() === '') {
      throw new Error('[ParallelTasks] nodeType cannot be empty')
    }
    if (!description || description.trim() === '') {
      throw new Error('[ParallelTasks] description cannot be empty')
    }

    const now = new Date()
    const existingTask = tasks.value.get(taskId)

    if (existingTask) {
      // 任务已存在，更新其信息
      logger.debug(`[ParallelTasks] Updating existing task: ${taskId}`)

      // 只更新非运行状态的字段，避免覆盖正在执行的任务状态
      if (existingTask.state === ParallelTaskState.PENDING) {
        existingTask.nodeType = nodeType
        existingTask.description = description
        existingTask.taskNodeId = taskNodeId
      }

      existingTask.updatedAt = now

      // 如果任务已经完成但再次收到启动消息，重置为PENDING
      if (existingTask.state === ParallelTaskState.COMPLETED ||
          existingTask.state === ParallelTaskState.FAILED ||
          existingTask.state === ParallelTaskState.CANCELLED) {
        logger.debug(`[ParallelTasks] Resetting task state from ${existingTask.state} to PENDING: ${taskId}`)
        existingTask.state = ParallelTaskState.PENDING
        existingTask.progress = {
          current: 0,
          total: 100,
          percentage: 0
        }
        // 保留输出和历史，但可以清空TODO
        existingTask.todos = []
      }

      return
    }

    // 创建新任务
    const newTask: ParallelTaskInfo = {
      taskId,
      taskNodeId,
      nodeType,
      description,
      state: ParallelTaskState.PENDING,
      progress: {
        current: 0,
        total: 100,
        percentage: 0
      },
      todos: [],
      metrics: {
        toolCalls: 0,
        llmCalls: 0
      },
      outputs: [],
      createdAt: now,
      updatedAt: now
    }

    tasks.value.set(taskId, reactive(newTask))

    logger.debug(`[ParallelTasks] Added new task: ${taskId} (${nodeType})`)
  }

  /**
   * 更新任务状态
   */
  function updateTaskState(taskId: string, state: ParallelTaskState): void {
    // ✅ Fast Fail: 验证参数
    if (!taskId || taskId.trim() === '') {
      throw new Error('[ParallelTasks] taskId cannot be empty when updating state')
    }

    const task = tasks.value.get(taskId)
    if (!task) {
      throw new Error(`[ParallelTasks] Task ${taskId} not found`)
    }

    task.state = state
    task.updatedAt = new Date()

    // 如果任务开始，记录开始时间
    if (state === ParallelTaskState.RUNNING && !task.metrics.startTime) {
      task.metrics.startTime = new Date()
    }

    // 如果任务完成或失败，记录结束时间和持续时间
    if ((state === ParallelTaskState.COMPLETED || state === ParallelTaskState.FAILED) && !task.metrics.endTime) {
      task.metrics.endTime = new Date()
      if (task.metrics.startTime) {
        task.metrics.duration = (task.metrics.endTime.getTime() - task.metrics.startTime.getTime()) / 1000
      }
    }

    logger.debug(`[ParallelTasks] Task ${taskId} state: ${state}`)
  }

  /**
   * 更新任务进度
   */
  function updateTaskProgress(taskId: string, progress: Partial<ParallelTaskProgress>): void {
    // ✅ Fast Fail: 验证参数
    if (!taskId || taskId.trim() === '') {
      throw new Error('[ParallelTasks] taskId cannot be empty when updating progress')
    }

    const task = tasks.value.get(taskId)
    if (!task) {
      throw new Error(`[ParallelTasks] Task ${taskId} not found`)
    }

    if (progress.current !== undefined) {
      task.progress.current = progress.current
    }
    if (progress.total !== undefined) {
      task.progress.total = progress.total
    }
    if (progress.message !== undefined) {
      task.progress.message = progress.message
    }

    // 计算百分比
    task.progress.percentage = task.progress.total > 0
      ? (task.progress.current / task.progress.total) * 100
      : 0

    task.updatedAt = new Date()
  }

  /**
   * 更新TODO列表
   */
  function updateTaskTodos(taskId: string, todos: ParallelTodoItem[]): void {
    // ✅ Fast Fail: 验证参数
    if (!taskId || taskId.trim() === '') {
      throw new Error('[ParallelTasks] taskId cannot be empty when updating todos')
    }
    if (!Array.isArray(todos)) {
      throw new Error('[ParallelTasks] todos must be an array')
    }

    const task = tasks.value.get(taskId)
    if (!task) {
      throw new Error(`[ParallelTasks] Task ${taskId} not found`)
    }

    task.todos = reactive(todos)
    task.updatedAt = new Date()

    // 更新进度基于TODO完成情况
    const completedCount = todos.filter(t => t.status === ParallelTaskState.COMPLETED).length
    updateTaskProgress(taskId, {
      current: completedCount,
      total: todos.length
    })
  }

  /**
   * 添加任务输出
   */
  function appendTaskOutput(taskId: string, output: string): void {
    // ✅ Fast Fail: 验证参数
    if (!taskId || taskId.trim() === '') {
      throw new Error('[ParallelTasks] taskId cannot be empty when appending output')
    }
    if (output === undefined || output === null) {
      throw new Error('[ParallelTasks] output cannot be null or undefined')
    }

    const task = tasks.value.get(taskId)
    if (!task) {
      throw new Error(`[ParallelTasks] Task ${taskId} not found`)
    }

    task.outputs.push(output)

    // 限制输出长度（保留最后1000行）
    if (task.outputs.length > 1000) {
      task.outputs = task.outputs.slice(-1000)
    }

    task.updatedAt = new Date()
  }

  /**
   * 更新任务错误
   */
  function setTaskError(taskId: string, error: string): void {
    // ✅ Fast Fail: 验证参数
    if (!taskId || taskId.trim() === '') {
      throw new Error('[ParallelTasks] taskId cannot be empty when setting error')
    }
    if (!error || error.trim() === '') {
      throw new Error('[ParallelTasks] error message cannot be empty')
    }

    const task = tasks.value.get(taskId)
    if (!task) {
      throw new Error(`[ParallelTasks] Task ${taskId} not found`)
    }

    task.error = error
    task.state = ParallelTaskState.FAILED
    task.updatedAt = new Date()

    logger.error(`[ParallelTasks] Task ${taskId} error: ${error}`)
  }

  /**
   * 移除任务
   */
  function removeTask(taskId: string): void {
    tasks.value.delete(taskId)
    logger.debug(`[ParallelTasks] Removed task: ${taskId}`)
  }

  /**
   * 清空所有任务
   */
  function clearAllTasks(): void {
    tasks.value.clear()
    logger.debug('[ParallelTasks] Cleared all tasks')
  }

  /**
   * 获取任务信息
   */
  function getTask(taskId: string): ParallelTaskInfo | undefined {
    return tasks.value.get(taskId)
  }

  /**
   * 设置最大并行任务数
   */
  function setMaxParallel(max: number): void {
    maxParallel.value = max
    logger.debug(`[ParallelTasks] Max parallel tasks set to: ${max}`)
  }

  // ==================== WebSocket消息处理 ====================

  /**
   * 处理任务节点开始消息
   */
  function handleTaskNodeStart(data: unknown): void {
    const { task_id, node_type, description, task_node_id } = data

    // ✅ Fast Fail: 验证必需字段
    if (!task_id) {
      const error = new Error('[ParallelTasks] task_node_start message missing required field: task_id')
      logger.error('[ParallelTasks] Invalid message data:', { data })
      throw error
    }

    if (!node_type) {
      const error = new Error('[ParallelTasks] task_node_start message missing required field: node_type')
      logger.error('[ParallelTasks] Invalid message data:', {
        task_id,
        task_node_id,
        data_keys: Object.keys(data),
        full_data: data
      })
      throw error
    }

    if (!description) {
      const error = new Error('[ParallelTasks] task_node_start message missing required field: description')
      logger.error('[ParallelTasks] Invalid message data:', { task_id, node_type, data })
      throw error
    }

    addTask(task_id, node_type, description, task_node_id)
    updateTaskState(task_id, ParallelTaskState.RUNNING)
  }

  /**
   * 处理任务节点进度消息
   */
  function handleTaskNodeProgress(data: unknown): void {
    const { task_id, progress, message } = data

    if (!task_id) {
      const error = new Error('[ParallelTasks] task_node_progress message missing required field: task_id')
      logger.error('[ParallelTasks] Invalid message data:', { data })
      throw error
    }

    if (progress === undefined || progress === null) {
      const error = new Error('[ParallelTasks] task_node_progress message missing required field: progress')
      logger.error('[ParallelTasks] Invalid message data:', { task_id, data })
      throw error
    }

    updateTaskProgress(task_id, { current: progress, message: message || '' })
  }

  /**
   * 处理任务节点完成消息
   */
  function handleTaskNodeComplete(data: unknown): void {
    const { task_id, result } = data

    if (!task_id) {
      const error = new Error('[ParallelTasks] task_node_complete message missing required field: task_id')
      logger.error('[ParallelTasks] Invalid message data:', { data })
      throw error
    }

    updateTaskState(task_id, ParallelTaskState.COMPLETED)
    if (result) {
      appendTaskOutput(task_id, result)
    }
  }

  /**
   * 处理单个TODO项更新消息
   */
  function handleTodoUpdate(data: unknown): void {
    const { task_node_id, todos } = data

    if (!task_node_id) {
      const error = new Error('[ParallelTasks] todo_update message missing required field: task_node_id')
      logger.error('[ParallelTasks] Invalid message data:', { data })
      throw error
    }

    if (!todos || !Array.isArray(todos)) {
      const error = new Error('[ParallelTasks] todo_update message has invalid field: todos (must be array)')
      logger.error('[ParallelTasks] Invalid message data:', { task_node_id, todos, data })
      throw error
    }

    updateTaskTodos(task_node_id, todos)
  }

  /**
   * 处理TODO列表更新消息（批量）
   */
  function handleTodoBatchUpdate(data: unknown): void {
    const { task_id, todos } = data

    if (!task_id) {
      const error = new Error('[ParallelTasks] todo_batch_update message missing required field: task_id')
      logger.error('[ParallelTasks] Invalid message data:', { data })
      throw error
    }

    if (!todos || !Array.isArray(todos)) {
      const error = new Error('[ParallelTasks] todo_batch_update message has invalid field: todos (must be array)')
      logger.error('[ParallelTasks] Invalid message data:', { task_id, todos, data })
      throw error
    }

    updateTaskTodos(task_id, todos)
  }

  /**
   * 移除所有已完成的任务
   */
  function removeCompletedTasks(): void {
    const toRemove: string[] = []
    for (const [taskId, task] of tasks.value.entries()) {
      if (task.state === ParallelTaskState.COMPLETED) {
        toRemove.push(taskId)
      }
    }
    toRemove.forEach(taskId => removeTask(taskId))
    logger.debug(`[ParallelTasks] Removed ${toRemove.length} completed tasks`)
  }

  /**
   * 处理流式内容消息
   */
  function handleStreamContent(data: unknown): void {
    logger.debug('[ParallelTasks] handleStreamContent called:', data)
    const { task_node_id, content, task_id } = data

    // 🔧 修复：优先使用 task_id，如果没有则使用 task_node_id
    const targetTaskId = task_id || task_node_id

    // ✅ Fast Fail: 验证必需字段
    if (!targetTaskId || targetTaskId.trim() === '') {
      throw new Error('[ParallelTasks] No valid task_id or task_node_id in stream_content message')
    }
    if (content === undefined || content === null) {
      throw new Error('[ParallelTasks] content cannot be null for stream_content')
    }

    logger.debug('[ParallelTasks] Adding stream content to task:', targetTaskId, content?.substring(0, 50))
    appendTaskOutput(targetTaskId, content)
  }

  return {
    // 状态
    tasks,
    maxParallel,

    // 计算属性
    stats,
    hasActiveTasks,
    activeTasks,
    completedTasks,
    failedTasks,
    allTasks,

    // Actions
    addTask,
    updateTaskState,
    updateTaskProgress,
    updateTaskTodos,
    appendTaskOutput,
    setTaskError,
    removeTask,
    clearAllTasks,
    getTask,
    setMaxParallel,

    // WebSocket消息处理
    handleTaskNodeStart,
    handleTaskNodeProgress,
    handleTaskNodeComplete,
    handleTodoUpdate,
    handleTodoBatchUpdate,
    handleStreamContent,
    removeCompletedTasks
  }
})
