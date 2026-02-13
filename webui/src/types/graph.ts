/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

// Graph types for TaskGraph functionality

export enum TodoStatus {
  PENDING = 'pending',
  IN_PROGRESS = 'in_progress',
  COMPLETED = 'completed'
}

export interface TodoItem {
  id: string
  content: string
  status: TodoStatus
  created_at?: string
  updated_at?: string
}

export interface TaskGraph {
  graphId: string
  taskId: string
  data?: unknown
  nodes?: Record<string, unknown>
  updateType?: string
}

// Additional types needed by other modules
export type TaskStatus = 'pending' | 'in_progress' | 'completed' | 'failed' | 'cancelled'
export type TaskPriority = 'low' | 'medium' | 'high' | 'critical'

export interface TaskNode {
  id: string
  type: string
  name: string
  status: TaskStatus
  priority: TaskPriority
  dependencies?: string[]
}

export interface TaskContext {
  taskId: string
  workspaceId: string
  metadata?: Record<string, unknown>
}

export interface TaskInfo {
  id: string
  title: string
  description?: string
  status: TaskStatus
  priority: TaskPriority
  context: TaskContext
}
