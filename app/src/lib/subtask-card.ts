/**
 * Subtask card helpers — UI-B 子任务卡片（§6.3）。
 *
 * 职责：
 * - extractSubtaskCard：从 new_task/run_task 工具结果（JSON 字符串或对象）提取
 *   卡片字段（后端第五批结果增强：subtask_id/agent/conversation_id）
 * - findSubtaskNode：跨工作区桶按 subtask_id 查找实时节点（卡片与 UI-A 树
 *   共享 subtask-store 状态；卡片渲染端不持有工作区上下文，跨桶扫描即可——
 *   subtask_id 为 UUID，天然唯一）
 */
import type { SubtaskNode, SubtaskStatus } from "./types/subtask";

/** 工具结果 status → 子任务状态（结果无 running；created 即待执行） */
const RESULT_STATUS_MAP: Record<string, SubtaskStatus> = {
  created: "pending",
  pending: "pending",
  running: "running",
  completed: "completed",
  failed: "failed",
  aborted: "aborted",
};

/** 子任务卡片信息（chat-store 提取产物，进 SubtaskCardContentBlock） */
export interface SubtaskCardInfo {
  subtaskId: string;
  toolName: "new_task" | "run_task";
  agent: string | null;
  conversationId: string | null;
  mode: string | null;
  /** 任务描述（run_task 结果不带 message，由 tool_input 补齐） */
  message: string | null;
  /** 结果携带的初始状态；error/未知 → null（渲染端回落） */
  initialStatus: SubtaskStatus | null;
  isError: boolean;
}

function parseResultObject(result: unknown): Record<string, unknown> | null {
  if (typeof result === "string") {
    try {
      const parsed: unknown = JSON.parse(result);
      return parsed && typeof parsed === "object" ? (parsed as Record<string, unknown>) : null;
    } catch {
      return null;
    }
  }
  if (result && typeof result === "object") {
    return result as Record<string, unknown>;
  }
  return null;
}

/** 工具结果/卡片快照 status 字符串 → SubtaskStatus（未知/空值回落 fallback） */
export function toSubtaskStatus(
  value: string | null | undefined,
  fallback: SubtaskStatus,
): SubtaskStatus {
  if (typeof value === "string") {
    return RESULT_STATUS_MAP[value.toLowerCase()] ?? fallback;
  }
  return fallback;
}

/**
 * 从工具结果提取子任务卡片信息。
 * 仅认 new_task/run_task；无有效 subtask_id → null（new_task 失败即此形态）。
 */
export function extractSubtaskCard(toolName: string, result: unknown): SubtaskCardInfo | null {
  if (toolName !== "new_task" && toolName !== "run_task") return null;

  const obj = parseResultObject(result);
  if (!obj) return null;

  const subtaskId = obj.subtask_id;
  if (typeof subtaskId !== "string" || !subtaskId) return null;

  const rawStatus = typeof obj.status === "string" ? obj.status.toLowerCase() : "";
  const isError = rawStatus === "error";
  const initialStatus = RESULT_STATUS_MAP[rawStatus] ?? null;

  const conversationId = typeof obj.conversation_id === "string" ? obj.conversation_id : null;
  const agent = typeof obj.agent === "string" ? obj.agent : null;
  const mode = typeof obj.mode === "string" ? obj.mode : null;
  const message = typeof obj.message === "string" ? obj.message : null;

  return {
    subtaskId,
    toolName,
    agent,
    conversationId,
    mode,
    message,
    initialStatus,
    isError,
  };
}

/** 跨工作区桶按 subtask_id 查找实时节点（UUID 全局唯一） */
export function findSubtaskNode(
  buckets: Record<string, Record<string, SubtaskNode>>,
  subtaskId: string,
): SubtaskNode | undefined {
  for (const bucket of Object.values(buckets)) {
    const hit = bucket?.[subtaskId];
    if (hit) return hit;
  }
  return undefined;
}

/** 跨工作区桶定位归属工作区 id（卡片点击打开线程抽屉用；未命中 → null） */
export function findSubtaskWorkspace(
  buckets: Record<string, Record<string, SubtaskNode>>,
  subtaskId: string,
): string | null {
  for (const [workspaceId, bucket] of Object.entries(buckets)) {
    if (bucket?.[subtaskId]) return workspaceId;
  }
  return null;
}
