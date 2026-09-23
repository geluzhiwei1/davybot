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

/** todo 步级摘要（C25 subtask_progress 的 todos 快照） */
export interface SubtaskTodos {
  total: number;
  completed: number;
  /** 当前进行中的 todo 文案（≤40 字，可缺省） */
  current?: string;
}

/** WS subtask_progress 载荷（C25/§3.8 todo 步级进度，纯 UI 态）
 *  后端 SubtaskProgressMessage to_websocket_format = model_dump(exclude_none) */
export interface SubtaskProgressPayload {
  type: "subtask_progress";
  session_id?: string;
  /** 父任务 id（后端填充，仅作展示参考） */
  task_id?: string;
  subtask_id: string;
  parent_id?: string;
  batch_id?: string;
  item_identity?: string;
  todos: SubtaskTodos;
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
  /** 批量派发组 ID（new_task_batch 展开；单发 new_task = null） */
  batch_id?: string | null;
  /** 批量条目身份（C16 batch 分组展示用） */
  item_identity?: string | null;
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
  /** 批量派发组 ID（C16 batch 分组展示；null = 单发/未知） */
  batchId: string | null;
  /** 批量条目身份（批次内条目名；null = 未知） */
  itemIdentity: string | null;
  /** todo 步级摘要（C25 subtask_progress 维护；null = 未上报） */
  todos: SubtaskTodos | null;
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
