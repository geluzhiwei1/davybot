/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * 并行任务类型定义
 * 用于并行AgentAgents
 */

// 不再需要导入 TaskStatus，因为我们使用自己的 ParallelTaskState 枚举

/**
 * 并行任务状态枚举
 * 包含状态值和排序优先级（越小越靠前）
 */
export enum ParallelTaskState {
  PENDING = 'pending',
  RUNNING = 'running',
  PAUSED = 'paused',
  COMPLETED = 'completed',
  FAILED = 'failed',
  CANCELLED = 'cancelled',
  SKIPPED = 'skipped'
}

/**
 * 获取状态优先级（用于排序）
 * 优先级：RUNNING > PENDING > COMPLETED > FAILED > PAUSED > CANCELLED > SKIPPED
 */
export function getStatePriority(state: ParallelTaskState): number {
  const priorityMap: Record<ParallelTaskState, number> = {
    [ParallelTaskState.RUNNING]: 0,
    [ParallelTaskState.PENDING]: 1,
    [ParallelTaskState.COMPLETED]: 2,
    [ParallelTaskState.FAILED]: 3,
    [ParallelTaskState.PAUSED]: 4,
    [ParallelTaskState.CANCELLED]: 5,
    [ParallelTaskState.SKIPPED]: 6
  }
  return priorityMap[state] ?? 999
}

/**
 * TODO项信息
 */
export interface ParallelTodoItem {
  id: string
  content: string
  status: ParallelTaskState
  result?: string
  error?: string
  createdAt: Date
  updatedAt: Date
}

/**
 * 任务进度信息
 */
export interface ParallelTaskProgress {
  current: number
  total: number
  percentage: number
  message?: string
}

/**
 * 任务性能指标
 */
export interface ParallelTaskMetrics {
  startTime?: Date
  endTime?: Date
  duration?: number // 秒
  tokenUsage?: {
    prompt: number
    completion: number
    total: number
  }
  toolCalls: number
  llmCalls: number
}

/**
 * 并行任务完整信息
 */
export interface ParallelTaskInfo {
  // 基础信息
  taskId: string
  taskNodeId?: string  // 后端字段名: task_node_id
  nodeType: string     // 后端字段名: node_type
  description: string

  // 状态
  state: ParallelTaskState
  progress: ParallelTaskProgress

  // TODO列表
  todos: ParallelTodoItem[]

  // 性能指标
  metrics: ParallelTaskMetrics

  // 实时输出
  outputs: string[]

  // 错误信息
  error?: string

  // 时间戳
  createdAt: Date
  updatedAt: Date
}

/**
 * 并行任务统计信息
 */
export interface ParallelTasksStats {
  total: number
  active: number
  completed: number
  failed: number
  pending: number
}

/**
 * 并行任务控制操作
 */
export enum ParallelTaskControl {
  PAUSE = 'pause',
  RESUME = 'resume',
  STOP = 'stop',
  RETRY = 'retry'
}

/**
 * 控制操作结果
 */
export interface ControlResult {
  success: boolean
  taskId: string
  action: ParallelTaskControl
  message?: string
  error?: string
}
