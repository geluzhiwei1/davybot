/**
 * Trace + Task Graph API — workspace-scoped execution traces and task graphs.
 */
import { request } from "./client";

// ── Task Graph API ────────────────────────────────────────────────

export interface TaskGraphNode {
  task_id: string;
  description: string;
  mode: string;
  status: string;
  priority: string;
  parent_id: string | null;
  child_ids: string[];
  created_at: string | null;
  updated_at: string | null;
}

export interface TaskGraphData {
  graph_id: string;
  name: string;
  description: string;
  root_task_id: string | null;
  total_tasks: number;
  status: string;
  created_at: string | null;
  updated_at: string | null;
  tasks: TaskGraphNode[];
}

export const taskGraphApi = {
  /** GET /api/workspaces/{id}/graphs — returns the workspace task graph with all nodes */
  getGraphs: (workspaceId: string) =>
    request<{ success: boolean; graphs: TaskGraphData[]; total: number }>(
      `/api/workspaces/${workspaceId}/graphs`,
    ),
};

// ── Trace API ────────────────────────────────────────────────────

export interface TraceSpanItem {
  trace_id: string;
  span_id: string;
  parent_span_id: string | null;
  span_name: string;
  phase: string | null;
  status: string;
  start_time: string;
  end_time: string | null;
  duration_ms: number | null;
  input_summary: string | null;
  output_summary: string | null;
  metadata: Record<string, unknown>;
}

export interface TraceSummary {
  trace_id: string;
  conversation_id: string | null;
  task_id: string | null;
  workspace_id: string | null;
  span_count: number;
  total_duration_ms: number;
  error_count: number;
  created_at: string | null;
  spans: TraceSpanItem[];
}

export const traceApi = {
  /** GET /api/workspaces/{id}/traces — query persisted agent execution traces */
  getTraces: (
    workspaceId: string,
    params?: { conversation_id?: string; task_id?: string; limit?: number },
  ) => {
    const sp = new URLSearchParams();
    if (params?.conversation_id) sp.set("conversation_id", params.conversation_id);
    if (params?.task_id) sp.set("task_id", params.task_id);
    if (params?.limit) sp.set("limit", String(params.limit));
    const qs = sp.toString();
    return request<{
      success: boolean;
      data: { traces: TraceSummary[]; total: number; limit: number; offset: number };
    }>(`/api/workspaces/${workspaceId}/traces${qs ? `?${qs}` : ""}`);
  },
};
