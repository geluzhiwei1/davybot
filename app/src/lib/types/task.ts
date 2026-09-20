/**
 * Task type definitions — migrated from legalbot/webui/src/types/task.ts
 */

import type { TaskStatus, TaskPriority, TodoItem, TaskContext } from "./graph";

export interface TaskSummary {
  task_id: string;
  instance_id: string;
  initial_mode: string;
  final_mode: string;
  mode_transitions: number;
  skill_calls: number;
  mcp_requests: number;
  subtasks_created: number;
  tool_usage: Record<string, number>;
  token_usage: {
    input: number;
    output: number;
    total: number;
  };
}

export interface TaskStatusUpdate {
  task_id: string;
  old_status: TaskStatus;
  new_status: TaskStatus;
  reason: string;
  timestamp: string;
}

export interface BatchTaskOperationRequest {
  task_ids: string[];
  operation: "cancel" | "pause" | "resume" | "retry";
  reason?: string;
}

export interface BatchTaskOperationResponse {
  success_count: number;
  failed_count: number;
  results: Array<{
    task_id: string;
    success: boolean;
    error?: string;
  }>;
}

export interface TaskSearchParams {
  query?: string;
  status?: TaskStatus;
  mode?: string;
  priority?: TaskPriority;
  parent_id?: string;
  created_after?: string;
  created_before?: string;
  page?: number;
  limit?: number;
  sort_by?: "created_at" | "updated_at" | "priority";
  sort_order?: "asc" | "desc";
}

export interface TaskSearchResult {
  tasks: import("./graph").TaskInfo[];
  total: number;
  page: number;
  limit: number;
  total_pages: number;
}

export interface TaskListItem {
  task_id: string;
  description: string;
  mode: string;
  status: TaskStatus;
  priority: TaskPriority;
  parent_id: string | null;
  child_count: number;
  created_at: string;
  updated_at: string;
  progress: number;
}

export interface TaskProgress {
  task_id: string;
  total_steps: number;
  completed_steps: number;
  percentage: number;
  current_step?: string;
  eta?: number;
}

export interface TaskDetail extends TaskListItem {
  context: TaskContext;
  todos: TodoItem[];
  metadata: Record<string, unknown>;
  state_history: TaskStatusUpdate[];
}

export interface TaskCreateResponse {
  task_id: string;
  parent_id: string | null;
  created_at: string;
}

export interface TaskDeleteResponse {
  success: boolean;
  deleted_task_id: string;
  cascade_deleted: string[];
}

export interface TaskEvent {
  type: "created" | "updated" | "completed" | "failed" | "cancelled";
  task_id: string;
  data: unknown;
  timestamp: string;
}
