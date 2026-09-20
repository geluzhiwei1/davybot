/**
 * Subtask thread helpers — UI-C 子代理线程抽屉（§6.3）。
 *
 * 职责：
 * - extractConversationMessages：REST 会话载荷（Conversation.to_dict）→ 只读
 *   渲染用归一化消息（content 字符串/分片数组 → text；空文本过滤）
 * - findAgentProfile：Agent Profile 注册表按 agent 名匹配（大小写不敏感）
 */
import type {
  AgentProfileInfo,
  SubtaskActionResult,
  SubtaskRerunResponse,
  SubtaskStatus,
} from "./types/subtask";

/** 抽屉只读渲染消息（宽松形态，不依赖后端消息类细节） */
export interface ThreadMessage {
  role: string;
  text: string;
  timestamp?: string;
}

/** content 分片（{type:"text",text} 等）→ 单条消息文本；无有效文本 → null */
function contentToText(content: unknown): string | null {
  if (typeof content === "string") return content.trim() ? content : null;

  if (Array.isArray(content)) {
    const parts: string[] = [];
    for (const part of content) {
      if (typeof part === "string") {
        parts.push(part);
      } else if (
        part &&
        typeof part === "object" &&
        (part as { type?: unknown }).type === "text" &&
        typeof (part as { text?: unknown }).text === "string"
      ) {
        parts.push((part as { text: string }).text);
      }
      // 非 text 分片（image/audio/file）跳过 — 只读摘要无需富媒体
    }
    const joined = parts.join("\n");
    return joined.trim() ? joined : null;
  }

  return null;
}

/**
 * 会话载荷 → 归一化消息列表。
 * 宽松解析：messages 缺失/非数组 → []；空文本消息过滤；role 原样透传。
 */
export function extractConversationMessages(
  conversation: Record<string, unknown> | null | undefined,
): ThreadMessage[] {
  const messages = conversation?.messages;
  if (!Array.isArray(messages)) return [];

  const out: ThreadMessage[] = [];
  for (const m of messages) {
    if (!m || typeof m !== "object") continue;
    const rec = m as Record<string, unknown>;
    const text = contentToText(rec.content);
    if (text == null) continue;

    const timestamp = typeof rec.timestamp === "string" ? rec.timestamp : undefined;
    const role = typeof rec.role === "string" ? rec.role : "unknown";
    out.push(timestamp ? { role, text, timestamp } : { role, text });
  }
  return out;
}

/** Agent Profile 匹配（agent 名大小写不敏感；任一侧为空 → null） */
export function findAgentProfile(
  profiles: AgentProfileInfo[] | null | undefined,
  agent: string | null | undefined,
): AgentProfileInfo | null {
  if (!agent || !profiles?.length) return null;
  const target = agent.toLowerCase();
  return profiles.find((p) => p.agent?.toLowerCase() === target) ?? null;
}

// ── UI-D steer/abort ────────────────────────────────────────────────

/**
 * 按状态判定可用动作（对齐后端 MessageTaskTool/AbortTaskTool/reset_task_for_rerun 语义）：
 * - pending/running：steer + abort
 * - completed：steer（= 续跑）+ rerun（= 从头重跑）
 * - failed/aborted 终态：仅 rerun（原位重置，不要求会话存活）
 */
export function availableSubtaskActions(status: SubtaskStatus): {
  canSteer: boolean;
  canAbort: boolean;
  canRerun: boolean;
} {
  switch (status) {
    case "pending":
    case "running":
      return { canSteer: true, canAbort: true, canRerun: false };
    case "completed":
      return { canSteer: true, canAbort: false, canRerun: true };
    case "failed":
    case "aborted":
      return { canSteer: false, canAbort: false, canRerun: true };
    default:
      return { canSteer: false, canAbort: false, canRerun: false };
  }
}

/** REST steer/abort 结果 → 用户可读文案（失败透出后端 message） */
export function describeActionResult(action: "steer" | "abort", res: SubtaskActionResult): string {
  if (!res.success) {
    return res.result?.message ?? (action === "steer" ? "指令发送失败" : "中止失败");
  }
  if (action === "abort") return "已中止子任务（子树级联置为已中止）";
  const r = res.result ?? {};
  if (r.status === "resumed") return "指令已注入，子任务已续跑";
  if (r.delivery === "description") return "指令已追加至任务描述（待启动时生效）";
  return "指令已注入子会话（下一轮生效）";
}

/** REST rerun 结果 → 用户可读文案（P2-D：重置 PENDING；steer 非空 = 附带了重跑指令） */
export function describeRerunResult(res: SubtaskRerunResponse): string {
  if (!res.success) return "重跑失败";
  const base = "已重置为待启动（旧结果归档至 prev_*，等待父任务调度重跑）";
  return res.steer ? `${base}；重跑指令已追加至任务描述` : base;
}

// ── UI-E Agent Profile 使用计数 ──────────────────────────────────────

/** 单桶节点的最小形态（测试用 {agent:"..."} 即足够） */
export interface AgentCountableNode {
  agent: string | null | undefined;
}

/**
 * 按 agent 分桶统计子任务使用次数。
 * - 只扫描指定工作区桶（其余桶忽略）
 * - agent 为空/缺失跳过
 */
export function countSubtaskAgents(
  buckets: Record<string, Record<string, AgentCountableNode>>,
  workspaceId: string,
): Record<string, number> {
  const out: Record<string, number> = {};
  const bucket = buckets[workspaceId];
  if (!bucket) return out;
  for (const node of Object.values(bucket)) {
    const a = node?.agent;
    if (!a) continue;
    out[a] = (out[a] ?? 0) + 1;
  }
  return out;
}
