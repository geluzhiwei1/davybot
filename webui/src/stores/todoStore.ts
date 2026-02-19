/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * TODO状态管理Store
 * 管理TODO列表的状态、操作和实时更新
 */

import { defineStore } from 'pinia'
import { logger } from '@/utils/logger'

import { ref, computed } from 'vue'
import type {
  TodoItemDetail,
  TodoGroup,
  TodoStatistics,
  TodoFilter,
  TodoSortBy,
  TodoSortOrder,
  TodoViewMode,
  TodoNotification
} from '@/types/todos'
import { TodoStatus } from '@/types/todos'
import { useConnectionStore } from '@/stores/connection'
import { globalRouter } from '@/services/websocket/router'
import { MessageType } from '@/services/websocket/types'

export const useTodoStore = defineStore('todos', () => {
  // ==================== 状态 ====================

  // 所有TODO项（按task_node_id分组）
  const todoGroups = ref<Map<string, TodoGroup>>(new Map())

  // Todo history
  const history = ref<TodoHistoryEntry[]>([])

  // 通知
  const notifications = ref<TodoNotification[]>([])

  // 视图模式
  const viewMode = ref<TodoViewMode>('all')

  // 过滤器
  const filter = ref<TodoFilter>({})

  // 排序
  const sortBy = ref<TodoSortBy>('created_at')
  const sortOrder = ref<TodoSortOrder>('desc')

  // 加载状态
  const loading = ref(false)
  const error = ref<string | null>(null)

  // ==================== 计算属性 ====================

  /**
   * 所有TODO项（扁平化）
   */
  const allTodos = computed(() => {
    const todos: TodoItemDetail[] = []
    for (const group of todoGroups.value.values()) {
      todos.push(...group.todos)
    }
    return todos
  })

  /**
   * TODO统计信息
   */
  const statistics = computed<TodoStatistics>(() => {
    const total = allTodos.value.length
    const completed = allTodos.value.filter(t => t.status === TodoStatus.COMPLETED).length
    const pending = allTodos.value.filter(t => t.status === TodoStatus.PENDING).length
    const inProgress = allTodos.value.filter(t => t.status === TodoStatus.IN_PROGRESS).length

    // 找出最活跃的任务
    const taskCounts = new Map<string, number>()
    for (const group of todoGroups.value.values()) {
      taskCounts.set(group.task_node_id, group.todos.length)
    }

    let mostActiveTask: string | undefined
    let maxCount = 0
    for (const [taskId, count] of taskCounts.entries()) {
      if (count > maxCount) {
        maxCount = count
        mostActiveTask = taskId
      }
    }

    return {
      total_groups: todoGroups.value.size,
      total_todos: total,
      completed_todos: completed,
      pending_todos: pending,
      in_progress_todos: inProgress,
      overall_completion_rate: total > 0 ? Math.round((completed / total) * 100) : 0,
      most_active_task: mostActiveTask
    }
  })

  /**
   * 过滤后的TODO项
   */
  const filteredTodos = computed(() => {
    let todos = [...allTodos.value]

    // 应用状态过滤
    if (filter.value.status) {
      todos = todos.filter(t => t.status === filter.value.status)
    }

    // 应用任务节点过滤
    if (filter.value.task_node_id) {
      todos = todos.filter(t => t.task_node_id === filter.value.task_node_id)
    }

    // 应用优先级过滤
    if (filter.value.priority) {
      todos = todos.filter(t => t.priority === filter.value.priority)
    }

    // 应用搜索查询
    if (filter.value.search_query) {
      const query = filter.value.search_query.toLowerCase()
      todos = todos.filter(t =>
        t.content.toLowerCase().includes(query) ||
        t.task_node_id.toLowerCase().includes(query)
      )
    }

    // 应用排序
    todos.sort((a, b) => {
      let comparison = 0

      switch (sortBy.value) {
        case 'created_at':
          comparison = new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
          break
        case 'updated_at':
          comparison = new Date(a.updated_at).getTime() - new Date(b.updated_at).getTime()
          break
        case 'priority':
          const priorityOrder = { critical: 4, high: 3, medium: 2, low: 1 }
          comparison = priorityOrder[a.priority] - priorityOrder[b.priority]
          break
        case 'status':
          const statusOrder = { pending: 1, in_progress: 2, completed: 3 }
          comparison = statusOrder[a.status] - statusOrder[b.status]
          break
        case 'completion':
          comparison = (a.status === TodoStatus.COMPLETED ? 1 : 0) -
                       (b.status === TodoStatus.COMPLETED ? 1 : 0)
          break
      }

      return sortOrder.value === 'asc' ? comparison : -comparison
    })

    return todos
  })

  /**
   * 视图模式下的TODO项
   */
  const viewTodos = computed(() => {
    switch (viewMode.value) {
      case 'active':
        return filteredTodos.value.filter(t =>
          t.status === TodoStatus.PENDING || t.status === TodoStatus.IN_PROGRESS
        )
      case 'completed':
        return filteredTodos.value.filter(t => t.status === TodoStatus.COMPLETED)
      case 'by_task':
        return filteredTodos.value
      case 'by_priority':
        return filteredTodos.value
      case 'all':
      default:
        return filteredTodos.value
    }
  })

  // ==================== WebSocket消息处理 ====================

  /**
   * 处理TODO创建事件
   */
  function handleTodoCreated(data: unknown): void {
    const todo: TodoItemDetail = {
      id: data.todo_id,
      content: data.content,
      status: TodoStatus.PENDING,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      task_node_id: data.task_node_id,
      priority: data.priority || 'medium'
    }

    // 添加到对应的任务组
    let group = todoGroups.value.get(data.task_node_id)
    if (!group) {
      group = createTodoGroup(data.task_node_id, data.task_description || 'Unknown Task')
      todoGroups.value.set(data.task_node_id, group)
    }

    group.todos.push(todo)
    updateGroupSummary(data.task_node_id)

    // 添加通知
    addNotification({
      type: 'todo_created',
      todo_id: todo.id,
      task_node_id: data.task_node_id,
      message: `新TODO项已创建: ${todo.content}`,
      timestamp: new Date().toISOString()
    })
  }

  /**
   * 处理TODO更新事件
   */
  function handleTodoUpdated(data: unknown): void {
    const group = todoGroups.value.get(data.task_node_id)
    if (!group) return

    const todo = group.todos.find(t => t.id === data.todo_id)
    if (!todo) return

    // 更新TODO项
    if (data.status !== undefined) {
      todo.status = data.status
      if (data.status === TodoStatus.COMPLETED) {
        todo.completed_at = new Date().toISOString()
      }
    }
    if (data.content !== undefined) {
      todo.content = data.content
    }
    if (data.priority !== undefined) {
      todo.priority = data.priority
    }
    todo.updated_at = new Date().toISOString()

    updateGroupSummary(data.task_node_id)

    // 添加通知
    addNotification({
      type: 'todo_updated',
      todo_id: todo.id,
      task_node_id: data.task_node_id,
      message: `TODO项已更新: ${todo.content}`,
      timestamp: new Date().toISOString()
    })
  }

  /**
   * 处理TODO删除事件
   */
  function handleTodoDeleted(data: unknown): void {
    const group = todoGroups.value.get(data.task_node_id)
    if (!group) return

    const index = group.todos.findIndex(t => t.id === data.todo_id)
    if (index === -1) return

    const todo = group.todos[index]
    group.todos.splice(index, 1)
    updateGroupSummary(data.task_node_id)

    // 添加通知
    addNotification({
      type: 'todo_deleted',
      todo_id: data.todo_id,
      task_node_id: data.task_node_id,
      message: `TODO项已删除: ${todo.content}`,
      timestamp: new Date().toISOString()
    })
  }

  /**
   * 处理批量TODO更新
   */
  function handleTodoBatchUpdated(data: unknown): void {
    const group = todoGroups.value.get(data.task_node_id)
    if (!group) return

    // 批量更新状态
    for (const todoId of data.todo_ids) {
      const todo = group.todos.find(t => t.id === todoId)
      if (todo && data.status) {
        todo.status = data.status
        todo.updated_at = new Date().toISOString()
        if (data.status === TodoStatus.COMPLETED) {
          todo.completed_at = new Date().toISOString()
        }
      }
    }

    updateGroupSummary(data.task_node_id)

    // 添加通知
    addNotification({
      type: 'batch_operation_completed',
      task_node_id: data.task_node_id,
      message: `批量操作完成: ${data.todo_ids.length} 个TODO项`,
      timestamp: new Date().toISOString()
    })
  }

  // ==================== 辅助方法 ====================

  /**
   * 创建TODO组
   */
  function createTodoGroup(taskNodeId: string, taskDescription: string): TodoGroup {
    return {
      task_node_id: taskNodeId,
      task_description: taskDescription,
      task_mode: 'unknown',
      todos: [],
      summary: {
        task_node_id: taskNodeId,
        total: 0,
        pending: 0,
        in_progress: 0,
        completed: 0,
        percentage: 0,
        latest_update: new Date().toISOString()
      }
    }
  }

  /**
   * 更新TODO组摘要
   */
  function updateGroupSummary(taskNodeId: string): void {
    const group = todoGroups.value.get(taskNodeId)
    if (!group) return

    const total = group.todos.length
    const pending = group.todos.filter(t => t.status === TodoStatus.PENDING).length
    const completed = group.todos.filter(t => t.status === TodoStatus.COMPLETED).length

    group.summary = {
      task_node_id: taskNodeId,
      total,
      pending,
      in_progress: pending, // Reusing pending for in_progress count
      completed,
      percentage: total > 0 ? Math.round((completed / total) * 100) : 0,
      latest_update: new Date().toISOString()
    }
  }

  /**
   * 添加通知
   */
  function addNotification(notification: TodoNotification): void {
    notifications.value.unshift(notification)
    // 只保留最近100条通知
    if (notifications.value.length > 100) {
      notifications.value = notifications.value.slice(0, 100)
    }
  }

  /**
   * 清空所有TODO
   */
  function clearAllTodos(): void {
    todoGroups.value.clear()
    history.value = []
    notifications.value = []
  }

  /**
   * 移除已完成的TODO
   */
  function removeCompletedTodos(taskNodeId?: string): void {
    if (taskNodeId) {
      const group = todoGroups.value.get(taskNodeId)
      if (group) {
        group.todos = group.todos.filter(t => t.status !== TodoStatus.COMPLETED)
        updateGroupSummary(taskNodeId)
      }
    } else {
      for (const [nodeId, group] of todoGroups.value.entries()) {
        group.todos = group.todos.filter(t => t.status !== TodoStatus.COMPLETED)
        updateGroupSummary(nodeId)
      }
    }
  }

  // ==================== TODO操作 ====================

  /**
   * 更新TODO项
   */
  async function updateTodo(request: TodoUpdateRequest): Promise<boolean> {
    try {
      const connectionStore = useConnectionStore()

      await connectionStore.send({
        type: MessageType.TODO_UPDATE,
        ...request
      })

      return true
    } catch (error: unknown) {
      logger.error('Failed to update TODO:', error)
      error.value = error.message
      return false
    }
  }

  /**
   * 批量操作TODO项
   */
  async function batchOperation(request: TodoBatchOperationRequest): Promise<boolean> {
    try {
      const connectionStore = useConnectionStore()

      await connectionStore.send({
        type: 'TODO_BATCH_OPERATION',
        ...request
      })

      return true
    } catch (error: unknown) {
      logger.error('Failed to perform batch operation:', error)
      error.value = error.message
      return false
    }
  }

  /**
   * 设置视图模式
   */
  function setViewMode(mode: TodoViewMode): void {
    viewMode.value = mode
  }

  /**
   * 设置过滤器
   */
  function setFilter(newFilter: TodoFilter): void {
    filter.value = { ...filter.value, ...newFilter }
  }

  /**
   * 清除过滤器
   */
  function clearFilter(): void {
    filter.value = {}
  }

  /**
   * 设置排序
   */
  function setSort(sortByParam: TodoSortBy, sortOrderParam: TodoSortOrder): void {
    sortBy.value = sortByParam
    sortOrder.value = sortOrderParam
  }

  /**
   * 获取TODO组的所有TODO
   */
  function getTodosByTaskNode(taskNodeId: string): TodoItemDetail[] {
    const group = todoGroups.value.get(taskNodeId)
    return group ? group.todos : []
  }

  /**
   * 更新TODO列表（从WebSocket消息）
   */
  function updateTodos(taskNodeId: string, todos: unknown[]) {
    logger.debug('[TODO Store] Updating todos for task node:', taskNodeId, 'count:', todos.length)
    // 转换后端TODO格式到前端格式
    const todoItems: TodoItemDetail[] = todos.map(todo => ({
      id: todo.id,
      content: todo.content,
      status: todo.status,
      created_at: todo.created_at,
      updated_at: todo.updated_at,
      completed_at: todo.completed_at,
      task_node_id: taskNodeId,
      priority: 'medium' as const, // 默认优先级
      metadata: todo.metadata
    }))

    // 计算统计信息
    const total = todoItems.length
    const completed = todoItems.filter(t => t.status === TodoStatus.COMPLETED).length
    const pending = todoItems.filter(t => t.status === TodoStatus.PENDING).length

    // 创建或更新TODO组
    const todoGroup: TodoGroup = {
      task_node_id: taskNodeId,
      task_description: `Task ${taskNodeId}`, // 可以从消息中获取更详细的描述
      task_mode: 'unknown', // 可以从消息中获取
      todos: todoItems,
      summary: {
        task_node_id: taskNodeId,
        total,
        pending,
        in_progress: pending, // Reusing pending for in_progress count
        completed,
        percentage: total > 0 ? Math.round((completed / total) * 100) : 0,
        latest_update: new Date().toISOString()
      }
    }

    // 更新Map
    todoGroups.value.set(taskNodeId, todoGroup)

    logger.debug('[TODO Store] Todos updated successfully')
  }

  /**
   * 获取TODO组
   */
  function getTodoGroup(taskNodeId: string): TodoGroup | undefined {
    return todoGroups.value.get(taskNodeId)
  }

  return {
    // 状态
    todoGroups,
    history,
    notifications,
    viewMode,
    filter,
    sortBy,
    sortOrder,
    loading,
    error,

    // 计算属性
    allTodos,
    statistics,
    filteredTodos,
    viewTodos,

    // WebSocket消息处理
    handleTodoCreated,
    handleTodoUpdated,
    handleTodoDeleted,
    handleTodoBatchUpdated,

    // 操作
    updateTodo,
    updateTodos,
    batchOperation,
    setViewMode,
    setFilter,
    clearFilter,
    setSort,
    getTodosByTaskNode,
    getTodoGroup,
    clearAllTodos,
    removeCompletedTodos
  }
})

/**
 * 注册WebSocket消息路由
 */
export function registerTodoWebSocketRoutes(): void {
  // Todo created
  globalRouter.on(MessageType.TODO_CREATED, (message) => {
    const store = useTodoStore()
    store.handleTodoCreated(message)
  })

  // Todo updated
  globalRouter.on(MessageType.TODO_UPDATED, (message) => {
    const store = useTodoStore()
    store.handleTodoUpdated(message)
  })

  // TODO删除
  globalRouter.on(MessageType.TODO_DELETED, (message) => {
    const store = useTodoStore()
    store.handleTodoDeleted(message)
  })

  // 批量TODO更新
  globalRouter.on(MessageType.TODO_BATCH_UPDATED, (message) => {
    const store = useTodoStore()
    store.handleTodoBatchUpdated(message)
  })
}
