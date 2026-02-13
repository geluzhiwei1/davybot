/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

// 检查点相关类型定义

import type { TaskNode } from "./graph"

// 检查点数据结构
export interface CheckpointData {
  checkpoint_id: string
  task_graph_id: string
  timestamp: string
  nodes: Record<string, TaskNode>
  root_node_id: string | null
  states: Record<string, string>
  contexts: Record<string, unknown>
}

// 检查点信息
export interface Checkpoint {
  id: string
  task_graph_id: string
  timestamp: string
  checkpoint_size: number
  node_count: number
  description?: string
}

// 检查点列表项
export interface CheckpointListItem {
  checkpoint_id: string
  task_graph_id: string
  created_at: string
  size: number
  node_count: number
  notes?: string
}

// 创建检查点请求
export interface CreateCheckpointRequest {
  task_graph_id: string
  description?: string
}

// 创建检查点响应
export interface CreateCheckpointResponse {
  checkpoint_id: string
  checkpoint_path: string
  checkpoint_size: number
  task_id: string
  created_at: string
}

// 恢复检查点请求
export interface RestoreCheckpointRequest {
  checkpoint_id: string
  task_graph_id: string
}

// 恢复检查点响应
export interface RestoreCheckpointResponse {
  success: boolean
  checkpoint_id: string
  restored_tasks: number
  restore_time: number
}

// 检查点列表响应
export interface CheckpointListResponse {
  checkpoints: CheckpointListItem[]
  total: number
  page: number
  limit: number
}

// 检查点统计信息
export interface CheckpointStatistics {
  total_checkpoints: number
  total_size: number
  latest_checkpoint: string | null
  oldest_checkpoint: string | null
}
