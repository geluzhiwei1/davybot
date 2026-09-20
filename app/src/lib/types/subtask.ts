/**
 * Subtask delegation types — §6.2/§6.3 子任务委派前端契约。
 *
 * 对齐后端：
 * - WS `subtask_lifecycle`（dawei/websocket/protocol.py SubtaskLifecycleMessage，
 *   to_websocket_format = model_dump(exclude_none) → 缺省字段不出现在载荷中）
 * - REST `dawei/api/workspaces/subtasks.py`（bootstrap / conversation / profiles / steer / abort / rerun）
 */

/** 子任务状态（后端 TaskStatus 小写值） */
export type SubtaskStatus = "pending" | "running" | "completed" | "failed" | "aborted";

/** WS 生命周期事件名 */
export type SubtaskLifecycleEventName =
  "created" | "started" | "completed" | "failed" | "aborted" | "steered";

/** WS subtask_lifecycle 载荷（字段均可缺省，除 subtask_id/event） */
export interface SubtaskLifecyclePayload {
  type: "subtask_lifecycle";
  session_id?: string;
  /** 根任务 id（后端填充 parent id，仅作展示参考） */
  task_id?: string;
  subtask_id: string;
  event: SubtaskLifecycleEventName;
  status?: SubtaskStatus | string;
  parent_id?: string;
  conversation_id?: string;
  agent?: string;
  depth?: number;
  metadata?: Record<string, unknown>;
}

/** REST GET /api/workspaces/{ws}/subtasks 列表项（树 bootstrap） */
export interface SubtaskInfo {
  task_id: string;
  parent_id: string | null;
  status: string | null;
  mode: string | null;
  agent: string | null;
  model: string | null;
  depth: number | null;
  conversation_id: string | null;
  description: string;
  child_ids: string[];
}

/** store 内部子任务节点（WS 事件 + REST bootstrap 归一化后的形态） */
export interface SubtaskNode {
  task_id: string;
  parent_id: string | null;
  status: SubtaskStatus;
  agent: string | null;
  model: string | null;
  mode: string | null;
  depth: number | null;
  conversation_id: string | null;
  description: string;
  /** 最近一次生命周期事件 */
  lastEvent: SubtaskLifecycleEventName | null;
  /** steer 指令历史（metadata.message） */
  steerMessages: string[];
  createdAt: number;
  updatedAt: number;
}

/** 树面板节点（selectSubtaskTree 产物） */
export interface SubtaskTreeNode extends SubtaskNode {
  children: SubtaskTreeNode[];
}

// ── REST 响应类型 ────────────────────────────────────────────────────

export interface SubtaskListResponse {
  success: boolean;
  subtasks: SubtaskInfo[];
  total: number;
}

/** 子任务会话消息（Conversation.to_dict().messages 项的宽松形态） */
export interface SubtaskConversationMessage {
  role?: string;
  content?: unknown;
  [key: string]: unknown;
}

export interface SubtaskConversationResponse {
  success: boolean;
  task_node_id: string;
  conversation_id?: string;
  degraded: boolean;
  reason?: "shared_conversation" | "conversation_not_found" | string;
  message?: string;
  conversation: Record<string, unknown> | null;
}

/** Agent Profile（P3-0 注册表：to_metadata() + description + builtin） */
export interface AgentProfileInfo {
  agent: string;
  description: string;
  builtin: boolean;
  sandbox_mode?: string;
  model?: string | null;
  [key: string]: unknown;
}

export interface AgentProfilesResponse {
  success: boolean;
  profiles: AgentProfileInfo[];
  total: number;
}

/** steer/abort 通用响应（result = 工具 JSON 结果） */
export interface SubtaskActionResult {
  success: boolean;
  source: string;
  result: {
    status: string;
    task_node_id?: string;
    delivery?: string;
    message?: string;
    [key: string]: unknown;
  };
}

/** POST rerun 响应（P2-D：终态原位重置 PENDING，旧结果 stash 到 prev_*；
 *  steer = 可选重跑指令经 MessageTaskTool PENDING 路径的注入结果，null = 未带指令） */
export interface SubtaskRerunResponse {
  success: boolean;
  task_node_id: string;
  status: string;
  steer: SubtaskActionResult["result"] | null;
}
