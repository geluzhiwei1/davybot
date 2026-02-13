/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * TODO系统类型定义
 * 定义了TODO列表、TODO项和TODO操作相关的类型
 */

// 导出TodoStatus
export { TodoStatus } from './graph'

/**
 * TODO项的详细状态信息
 */
export interface TodoItemDetail {
  id: string
  content: string
  status: TodoStatus
  created_at: string
  updated_at: string
  completed_at?: string
  // 关联的任务节点ID
  task_node_id?: string
  // 优先级
  priority: 'low' | 'medium' | 'high' | 'critical'
  // TODO项的子任务（如果有）
  subtasks?: TodoItemDetail[]
  // 元数据
  metadata?: Record<string, unknown>
}

/**
 * TODO列表摘要
 */
export interface TodoListSummary {
  task_node_id: string
  total: number
  pending: number
  in_progress: number
  completed: number
  percentage: number
  latest_update: string
}

/**
 * TODO组（按任务节点分组）
 */
export interface TodoGroup {
  task_node_id: string
  task_description: string
  task_mode: string
  todos: TodoItemDetail[]
  summary: TodoListSummary
}

/**
 * TODO更新请求
 */
export interface TodoUpdateRequest {
  todo_id: string
  task_node_id: string
  status?: TodoStatus
  content?: string
  priority?: TodoItemDetail['priority']
}

/**
 * TODO创建请求
 */
export interface TodoCreateRequest {
  task_node_id: string
  content: string
  priority?: TodoItemDetail['priority']
}

/**
 * TODO批量操作请求
 */
export interface TodoBatchOperationRequest {
  task_node_id: string
  todo_ids: string[]
  operation: 'complete' | 'uncomplete' | 'delete' | 'update_priority'
  new_priority?: TodoItemDetail['priority']
}

/**
 * TODO统计信息
 */
export interface TodoStatistics {
  total_groups: number
  total_todos: number
  completed_todos: number
  pending_todos: number
  in_progress_todos: number
  overall_completion_rate: number
  most_active_task?: string
}

/**
 * TODO历史记录
 */
export interface TodoHistoryEntry {
  id: string
  todo_id: string
  from_status: TodoStatus
  to_status: TodoStatus
  timestamp: string
  trigger: 'user' | 'system' | 'agent'
  reason?: string
}

/**
 * TODO过滤器
 */
export interface TodoFilter {
  status?: TodoStatus
  task_node_id?: string
  priority?: TodoItemDetail['priority']
  search_query?: string
  date_from?: string
  date_to?: string
}

/**
 * 排序选项
 */
export type TodoSortBy =
  | 'created_at'
  | 'updated_at'
  | 'priority'
  | 'status'
  | 'completion'

export type TodoSortOrder = 'asc' | 'desc'

/**
 * TODO视图模式
 */
export type TodoViewMode = 'all' | 'active' | 'completed' | 'by_task' | 'by_priority'

/**
 * TODO通知类型
 */
export type TodoNotificationType =
  | 'todo_created'
  | 'todo_updated'
  | 'todo_completed'
  | 'todo_deleted'
  | 'batch_operation_completed'

/**
 * TODO通知事件
 */
export interface TodoNotification {
  type: TodoNotificationType
  todo_id?: string
  task_node_id?: string
  message: string
  timestamp: string
  metadata?: Record<string, unknown>
}
