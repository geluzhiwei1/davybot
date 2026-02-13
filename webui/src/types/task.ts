/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

// 任务相关类型定义

import type { TaskStatus, TaskPriority, TodoItem, TaskContext } from "./graph"

// 任务摘要
export interface TaskSummary {
  task_id: string
  instance_id: string
  initial_mode: string
  final_mode: string
  mode_transitions: number
  skill_calls: number
  mcp_requests: number
  subtasks_created: number
  tool_usage: Record<string, number>
  token_usage: {
    input: number
    output: number
    total: number
  }
}

// 任务状态更新
export interface TaskStatusUpdate {
  task_id: string
  old_status: TaskStatus
  new_status: TaskStatus
  reason: string
  timestamp: string
}

// 批量任务操作请求
export interface BatchTaskOperationRequest {
  task_ids: string[]
  operation: "cancel" | "pause" | "resume" | "retry"
  reason?: string
}

// 批量任务操作响应
export interface BatchTaskOperationResponse {
  success_count: number
  failed_count: number
  results: Array<{
    task_id: string
    success: boolean
    error?: string
  }>
}

// 任务搜索参数
export interface TaskSearchParams {
  query?: string
  status?: TaskStatus
  mode?: string
  priority?: TaskPriority
  parent_id?: string
  created_after?: string
  created_before?: string
  page?: number
  limit?: number
  sort_by?: "created_at" | "updated_at" | "priority"
  sort_order?: "asc" | "desc"
}

// 任务搜索结果
export interface TaskSearchResult {
  tasks: TaskInfo[]
  total: number
  page: number
  limit: number
  total_pages: number
}

// 任务列表项（简化版）
export interface TaskListItem {
  task_id: string
  description: string
  mode: string
  status: TaskStatus
  priority: TaskPriority
  parent_id: string | null
  child_count: number
  created_at: string
  updated_at: string
  progress: number
}

// 任务进度信息
export interface TaskProgress {
  task_id: string
  total_steps: number
  completed_steps: number
  percentage: number
  current_step?: string
  eta?: number
}

// 任务详情
export interface TaskDetail extends TaskListItem {
  context: TaskContext
  todos: TodoItem[]
  metadata: Record<string, unknown>
  state_history: TaskStatusUpdate[]
}

// 任务创建响应
export interface TaskCreateResponse {
  task_id: string
  parent_id: string | null
  created_at: string
}

// 任务删除响应
export interface TaskDeleteResponse {
  success: boolean
  deleted_task_id: string
  cascade_deleted: string[]
}

// 任务事件
export interface TaskEvent {
  type: "created" | "updated" | "completed" | "failed" | "cancelled"
  task_id: string
  data: unknown
  timestamp: string
}
