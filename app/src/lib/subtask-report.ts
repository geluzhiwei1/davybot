/**
 * Subtask execution report parser — [子任务执行报告] 结构化卡片（P2 UI）。
 *
 * 后端 `_inject_subtask_summaries`（task_graph_excutor.py）把每批子任务结果
 * 以 UserMessage 纯文本回注父对话，头部为 SUBTASK_REPORT_HEADER。此前前端
 * 将其渲染为右侧用户裸文本气泡（whitespace-pre-wrap 原文）；本模块把该文本
 * 解析为结构化条目，message.tsx 据此渲染结构化卡片而非裸文本。
 *
 * 报告格式（后端唯一事实源，解析尽力而为、失败回落原文渲染）：
 * ```
 * [子任务执行报告 / Subtask Execution Report]
 * - Subtask {id}: status=completed, acceptance=…, cost=1234tokens/56s, description=…
 *   result: …
 * 判定提示: …（有验收标准时后端追加）
 * ```
 */
import type { SubtaskStatus } from "./types/subtask";

export const SUBTASK_REPORT_HEADER = "[子任务执行报告 / Subtask Execution Report]";

/** 单个子任务报告条目 */
export interface SubtaskReportEntry {
  subtaskId: string;
  status: SubtaskStatus | null;
  /** 验收标准（P1b ⑧；无则 null） */
  acceptance: string | null;
  /** 成本/耗时（"1234tokens/56s" 形态原样展示；无则 null） */
  cost: string | null;
  description: string;
  result: string;
}

/** 解析产物；verdictHint = 末尾"判定提示"行（无验收标准时 null） */
export interface SubtaskReport {
  entries: SubtaskReportEntry[];
  verdictHint: string | null;
}

/** 是否为子任务执行报告消息（message.tsx 用户分支据此切换卡片渲染） */
export function isSubtaskReport(content: string | null | undefined): boolean {
  return typeof content === "string" && content.trimStart().startsWith(SUBTASK_REPORT_HEADER);
}

/** 后端 TaskStatus 值 → SubtaskStatus（cancelled→aborted；waiting_for_tool/interactive→running；未知→null） */
const STATUS_MAP: Record<string, SubtaskStatus> = {
  pending: "pending",
  running: "running",
  completed: "completed",
  failed: "failed",
  aborted: "aborted",
};

function normalizeStatus(raw: string): SubtaskStatus | null {
  const v = raw.trim().toLowerCase();
  if (v === "cancelled") return "aborted";
  if (v === "waiting_for_tool" || v === "interactive") return "running";
  return STATUS_MAP[v] ?? null;
}

const ENTRY_RE = /^- Subtask (\S+?):\s*(.*)$/;

/** 解析 `- Subtask {id}: …` 行的 bits（status/acceptance/cost 逗号分隔，description 兜底吞余文） */
function parseEntryLine(rest: string): Omit<SubtaskReportEntry, "result"> {
  // 顺序固定（后端 _bits）：status, [acceptance], [cost], description。
  // acceptance/description 可含逗号 → 用 ", key=" 定界而非 split(",")。
  const segs = rest.split(/,\s(?=acceptance=|cost=|description=)/);
  let status: SubtaskStatus | null = null;
  let acceptance: string | null = null;
  let cost: string | null = null;
  let description = "";
  for (const seg of segs) {
    if (seg.startsWith("status=")) {
      status = normalizeStatus(seg.slice("status=".length));
    } else if (seg.startsWith("acceptance=")) {
      acceptance = seg.slice("acceptance=".length);
    } else if (seg.startsWith("cost=")) {
      cost = seg.slice("cost=".length);
    } else if (seg.startsWith("description=")) {
      description = seg.slice("description=".length);
    }
  }
  return { subtaskId: "", status, acceptance, cost, description };
}

/**
 * 解析报告文本为结构化条目。
 * 非报告文本 → null（调用方回落默认渲染）。
 */
export function parseSubtaskReport(content: string): SubtaskReport | null {
  if (!isSubtaskReport(content)) return null;

  const lines = content.split("\n");
  const entries: SubtaskReportEntry[] = [];
  let verdictHint: string | null = null;
  let current: SubtaskReportEntry | null = null;
  let resultStarted = false;

  for (const line of lines) {
    if (verdictHint !== null) {
      verdictHint += `\n${line}`;
      continue;
    }
    if (line.startsWith("判定提示")) {
      verdictHint = line;
      current = null;
      continue;
    }
    const m = ENTRY_RE.exec(line);
    if (m) {
      const parsed = parseEntryLine(m[2]);
      current = { ...parsed, subtaskId: m[1], result: "" };
      resultStarted = false;
      entries.push(current);
      continue;
    }
    if (current) {
      // result 段：首行剥 "  result: " 前缀，后续行（截断的多行结果）原样追加
      let text = line;
      if (!resultStarted) {
        const rm = /^\s*result:\s?/.exec(line);
        if (rm) text = line.slice(rm[0].length);
        resultStarted = true;
      }
      current.result = current.result ? `${current.result}\n${text}` : text;
    }
    // 头部行（SUBTASK_REPORT_HEADER）与空行：忽略
  }

  return { entries, verdictHint };
}
