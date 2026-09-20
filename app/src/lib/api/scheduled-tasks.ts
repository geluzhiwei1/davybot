/**
 * Scheduled Tasks API — workspace-scoped and global scheduled tasks.
 */
import { request } from "./client";

// ── Types ────────────────────────────────────────────────────────────

export type ScheduleType = "delay" | "at_time" | "recurring" | "cron";
export type TriggerStatus =
  "pending" | "paused" | "triggered" | "completed" | "failed" | "cancelled";

export interface ExecutionData {
  message: string;
  llm?: string;
  mode?: string;
}

export interface ScheduledTask {
  task_id: string;
  workspace_id: string;
  description: string;
  schedule_type: ScheduleType;
  trigger_time: string;
  repeat_interval?: number;
  max_repeats?: number;
  cron_expression?: string;
  execution_type: "message";
  execution_data: ExecutionData;
  status: TriggerStatus;
  created_at: string;
  updated_at?: string;
  paused_at?: string;
  resumed_at?: string;
  triggered_at?: string;
  repeat_count: number;
  last_error?: string;
  tags?: string[];
  metadata?: Record<string, unknown>;
  // 工作空间关联信息（全局 API 返回）
  workspace_name?: string;
  workspace_display_name?: string;
  is_temp_workspace?: boolean;
  last_execution_conversation_id?: string;
}

export interface ScheduledTaskExecution {
  conversation_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  repeat_count: number;
  triggered_at: string;
}

export interface ScheduledTasksListResponse {
  success: boolean;
  tasks: ScheduledTask[];
  total: number;
  scheduler_active: boolean;
}

export interface ScheduledTaskExecutionsResponse {
  success: boolean;
  task_id: string;
  executions: ScheduledTaskExecution[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface CreateScheduledTaskRequest {
  description: string;
  schedule_type: ScheduleType;
  trigger_time: string;
  repeat_interval?: number;
  max_repeats?: number;
  cron_expression?: string;
  execution_type: "message";
  execution_data: ExecutionData;
  tags?: string[];
  metadata?: Record<string, unknown>;
}

export interface CreateScheduledTaskGlobalRequest extends CreateScheduledTaskRequest {
  workspace_id?: string | null; // null = 自动创建临时工作空间
}

export interface GlobalScheduledTasksResponse {
  success: boolean;
  tasks: ScheduledTask[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

// ── API ──────────────────────────────────────────────────────────────

export const scheduledTasksApi = {
  list: (workspaceId: string) =>
    request<ScheduledTasksListResponse>(`/api/workspaces/${workspaceId}/scheduled-tasks`),

  create: (workspaceId: string, body: CreateScheduledTaskRequest) =>
    request<{ success: boolean; task: ScheduledTask; message: string }>(
      `/api/workspaces/${workspaceId}/scheduled-tasks`,
      { method: "POST", body: JSON.stringify(body) },
    ),

  get: (workspaceId: string, taskId: string) =>
    request<{ success: boolean; task: ScheduledTask }>(
      `/api/workspaces/${workspaceId}/scheduled-tasks/${taskId}`,
    ),

  update: (workspaceId: string, taskId: string, updates: Partial<ScheduledTask>) =>
    request<{ success: boolean; task: ScheduledTask; message: string }>(
      `/api/workspaces/${workspaceId}/scheduled-tasks/${taskId}`,
      { method: "PUT", body: JSON.stringify(updates) },
    ),

  delete: (workspaceId: string, taskId: string) =>
    request<{ success: boolean; message: string }>(
      `/api/workspaces/${workspaceId}/scheduled-tasks/${taskId}`,
      { method: "DELETE" },
    ),

  pause: (workspaceId: string, taskId: string) =>
    request<{ success: boolean; message: string }>(
      `/api/workspaces/${workspaceId}/scheduled-tasks/${taskId}/pause`,
      { method: "POST" },
    ),

  resume: (workspaceId: string, taskId: string) =>
    request<{ success: boolean; message: string }>(
      `/api/workspaces/${workspaceId}/scheduled-tasks/${taskId}/resume`,
      { method: "POST" },
    ),

  trigger: (workspaceId: string, taskId: string) =>
    request<{ success: boolean; message: string }>(
      `/api/workspaces/${workspaceId}/scheduled-tasks/${taskId}/trigger`,
      { method: "POST" },
    ),

  getExecutions: (workspaceId: string, taskId: string, page = 1, pageSize = 20) =>
    request<ScheduledTaskExecutionsResponse>(
      `/api/workspaces/${workspaceId}/scheduled-tasks/${taskId}/executions?page=${page}&page_size=${pageSize}`,
    ),

  // ── Global API (cross-workspace) ──

  listGlobal: (params?: { status?: string; page?: number; page_size?: number }) => {
    const sp = new URLSearchParams();
    if (params?.status) sp.set("status", params.status);
    if (params?.page) sp.set("page", String(params.page));
    if (params?.page_size) sp.set("page_size", String(params.page_size));
    const qs = sp.toString();
    return request<GlobalScheduledTasksResponse>(`/api/scheduled-tasks${qs ? `?${qs}` : ""}`);
  },

  createGlobal: (body: CreateScheduledTaskGlobalRequest) =>
    request<{ success: boolean; task: ScheduledTask; message: string }>("/api/scheduled-tasks", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  getGlobal: (taskId: string) =>
    request<{ success: boolean; task: ScheduledTask }>(`/api/scheduled-tasks/${taskId}`),
};
