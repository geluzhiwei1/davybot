/**
 * Checkpoint type definitions — migrated from legalbot/webui/src/types/checkpoint.ts
 */

import type { TaskNode } from "./graph";

export interface CheckpointData {
  checkpoint_id: string;
  task_graph_id: string;
  timestamp: string;
  nodes: Record<string, TaskNode>;
  root_node_id: string | null;
  states: Record<string, string>;
  contexts: Record<string, unknown>;
}

export interface Checkpoint {
  id: string;
  task_graph_id: string;
  timestamp: string;
  checkpoint_size: number;
  node_count: number;
  description?: string;
}

export interface CheckpointListItem {
  checkpoint_id: string;
  task_graph_id: string;
  created_at: string;
  size: number;
  node_count: number;
  notes?: string;
}

export interface CreateCheckpointRequest {
  task_graph_id: string;
  description?: string;
}

export interface CreateCheckpointResponse {
  checkpoint_id: string;
  checkpoint_path: string;
  checkpoint_size: number;
  task_id: string;
  created_at: string;
}

export interface RestoreCheckpointRequest {
  checkpoint_id: string;
  task_graph_id: string;
}

export interface RestoreCheckpointResponse {
  success: boolean;
  checkpoint_id: string;
  restored_tasks: number;
  restore_time: number;
}

export interface CheckpointListResponse {
  items: CheckpointListItem[];
  total: number;
  page: number;
  limit: number;
  pages: number;
}

export interface CheckpointStatistics {
  total_checkpoints: number;
  total_size: number;
  latest_checkpoint: string | null;
  oldest_checkpoint: string | null;
}
