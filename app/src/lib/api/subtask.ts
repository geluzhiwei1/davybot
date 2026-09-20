/**
 * Subtask API — 子任务委派 §6.2 UI 协议层 REST 客户端。
 *
 * 后端：dawei/api/workspaces/subtasks.py
 * - GET  /api/workspaces/{ws}/subtasks                       树 bootstrap
 * - GET  /api/workspaces/{ws}/subtasks/{id}/conversation     子代理线程抽屉
 * - GET  /api/workspaces/{ws}/agents/profiles                Agent Profile 列表
 * - POST /api/workspaces/{ws}/subtasks/{id}/steer            中途指令
 * - POST /api/workspaces/{ws}/subtasks/{id}/abort            主动取消（级联）
 * - POST /api/workspaces/{ws}/subtasks/{id}/rerun            原位重跑（P2-D）
 */
import { request } from "./client";
import type {
  SubtaskListResponse,
  SubtaskConversationResponse,
  AgentProfilesResponse,
  SubtaskActionResult,
  SubtaskRerunResponse,
} from "../types/subtask";

export const subtaskApi = {
  /** GET — 树 bootstrap（根任务排除；含 parent_id/depth/agent/conversation_id） */
  list: (workspaceId: string) =>
    request<SubtaskListResponse>(`/api/workspaces/${workspaceId}/subtasks`),

  /** GET — 子任务独立会话完整历史（P2-7；降级时 degraded=true + reason） */
  getConversation: (workspaceId: string, taskNodeId: string) =>
    request<SubtaskConversationResponse>(
      `/api/workspaces/${workspaceId}/subtasks/${taskNodeId}/conversation`,
    ),

  /** GET — Agent Profile 注册表（内置 + workspace/.dawei/agents/*） */
  getAgentProfiles: (workspaceId: string) =>
    request<AgentProfilesResponse>(`/api/workspaces/${workspaceId}/agents/profiles`),

  /** POST — 中途指令（RUNNING 注入会话 / PENDING 追加描述 / COMPLETED 续跑） */
  steer: (workspaceId: string, taskNodeId: string, message: string) =>
    request<SubtaskActionResult>(`/api/workspaces/${workspaceId}/subtasks/${taskNodeId}/steer`, {
      method: "POST",
      body: JSON.stringify({ message }),
    }),

  /** POST — 主动取消（BFS 级联整棵子树 ABORTED，幂等） */
  abort: (workspaceId: string, taskNodeId: string, reason?: string) =>
    request<SubtaskActionResult>(`/api/workspaces/${workspaceId}/subtasks/${taskNodeId}/abort`, {
      method: "POST",
      body: JSON.stringify({ reason: reason ?? null }),
    }),

  /** POST — 原位重跑（P2-D：终态重置 PENDING，旧结果 stash 到 prev_*；可带重跑指令） */
  rerun: (workspaceId: string, taskNodeId: string, reason?: string, message?: string) =>
    request<SubtaskRerunResponse>(`/api/workspaces/${workspaceId}/subtasks/${taskNodeId}/rerun`, {
      method: "POST",
      body: JSON.stringify({ reason: reason ?? null, message: message ?? null }),
    }),
};
