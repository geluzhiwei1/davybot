/**
 * Subtask report parser tests — P2 UI：[子任务执行报告] 结构化卡片。
 *
 * 对应后端契约（task_graph_excutor.py `_inject_subtask_summaries`）：
 * ```
 * [子任务执行报告 / Subtask Execution Report]
 * - Subtask {id}: status=…, acceptance=…, cost=Ntokens/Ms, description=…
 *   result: …（可多行）
 * 判定提示: …（任一子任务有验收标准时追加）
 * ```
 */
import { describe, it, expect } from "vitest";
import { isSubtaskReport, parseSubtaskReport, SUBTASK_REPORT_HEADER } from "./subtask-report";

const FULL_REPORT = [
  SUBTASK_REPORT_HEADER,
  "- Subtask task-abc12345: status=completed, acceptance=报告包含全部 7 段, cost=1234tokens/56s, description=撰写合规分析报告",
  "  result: 报告已生成，含目录、结论与附录。",
  "- Subtask task-def67890: status=failed, cost=88tokens/12s, description=检索判例（无验收标准）",
  "  result: (无显式完成结果)",
  "判定提示: 请对照验收标准逐条核验后再进入下一步。",
].join("\n");

describe("isSubtaskReport", () => {
  it("matches report header at start (after leading whitespace)", () => {
    expect(isSubtaskReport(FULL_REPORT)).toBe(true);
    expect(isSubtaskReport(`\n   ${SUBTASK_REPORT_HEADER}\n- ...`)).toBe(true);
  });

  it("rejects ordinary text / empty / nullish", () => {
    expect(isSubtaskReport("普通用户消息")).toBe(false);
    expect(isSubtaskReport("")).toBe(false);
    expect(isSubtaskReport(null)).toBe(false);
    expect(isSubtaskReport(undefined)).toBe(false);
    // 头部不在开头（如引用了报告文本的其他消息）不算报告
    expect(isSubtaskReport(`前面有话说\n${SUBTASK_REPORT_HEADER}`)).toBe(false);
  });
});

describe("parseSubtaskReport", () => {
  it("returns null for non-report content", () => {
    expect(parseSubtaskReport("just chatting")).toBeNull();
  });

  it("parses full report: entries + verdict hint", () => {
    const r = parseSubtaskReport(FULL_REPORT);
    expect(r).not.toBeNull();
    expect(r!.entries).toHaveLength(2);

    const [e1, e2] = r!.entries;
    expect(e1.subtaskId).toBe("task-abc12345");
    expect(e1.status).toBe("completed");
    expect(e1.acceptance).toBe("报告包含全部 7 段");
    expect(e1.cost).toBe("1234tokens/56s");
    expect(e1.description).toBe("撰写合规分析报告");
    expect(e1.result).toBe("报告已生成，含目录、结论与附录。");

    // 无验收标准的条目：acceptance=null，占位结果原样保留
    expect(e2.subtaskId).toBe("task-def67890");
    expect(e2.status).toBe("failed");
    expect(e2.acceptance).toBeNull();
    expect(e2.result).toBe("(无显式完成结果)");

    expect(r!.verdictHint).toBe("判定提示: 请对照验收标准逐条核验后再进入下一步。");
  });

  it("multi-line result accumulates after the `result:` prefix line", () => {
    const content = [
      SUBTASK_REPORT_HEADER,
      "- Subtask s1: status=completed, description=demo",
      "  result: line1",
      "line2 continues",
      "line3",
    ].join("\n");
    const r = parseSubtaskReport(content);
    expect(r!.entries[0].result).toBe("line1\nline2 continues\nline3");
  });

  it("keeps commas inside acceptance/description (lookahead split, not naive comma split)", () => {
    const content = [
      SUBTASK_REPORT_HEADER,
      "- Subtask s2: status=running, acceptance=覆盖 A, B, C 三类, cost=1tokens/1s, description=检索判例, 行政处罚, 并汇总",
      "  result: ok",
    ].join("\n");
    const e = parseSubtaskReport(content)!.entries[0];
    expect(e.acceptance).toBe("覆盖 A, B, C 三类");
    expect(e.cost).toBe("1tokens/1s");
    // description 兜底吞余文（含逗号）
    expect(e.description).toBe("检索判例, 行政处罚, 并汇总");
  });

  it("normalizes backend-only statuses: cancelled→aborted, waiting_for_tool/interactive→running, unknown→null", () => {
    const content = [
      SUBTASK_REPORT_HEADER,
      "- Subtask s3: status=cancelled, description=a",
      "  result: r",
      "- Subtask s4: status=waiting_for_tool, description=b",
      "  result: r",
      "- Subtask s5: status=interactive, description=c",
      "  result: r",
      "- Subtask s6: status=mystery, description=d",
      "  result: r",
    ].join("\n");
    const st = parseSubtaskReport(content)!.entries.map((e) => e.status);
    expect(st).toEqual(["aborted", "running", "running", null]);
  });

  it("report without verdict hint (no acceptance anywhere) → null hint", () => {
    const content = [
      SUBTASK_REPORT_HEADER,
      "- Subtask s7: status=completed, description=x",
      "  result: y",
    ].join("\n");
    const r = parseSubtaskReport(content);
    expect(r!.entries).toHaveLength(1);
    expect(r!.verdictHint).toBeNull();
  });

  it("lines after verdict hint all belong to the hint (multi-line tail)", () => {
    const content = [
      SUBTASK_REPORT_HEADER,
      "- Subtask s8: status=completed, description=x",
      "  result: y",
      "判定提示: 第一行",
      "第二行补充说明",
    ].join("\n");
    const r = parseSubtaskReport(content);
    expect(r!.verdictHint).toBe("判定提示: 第一行\n第二行补充说明");
  });

  it("header-only report → zero entries, null hint (not null report)", () => {
    const r = parseSubtaskReport(SUBTASK_REPORT_HEADER);
    expect(r).not.toBeNull();
    expect(r!.entries).toEqual([]);
    expect(r!.verdictHint).toBeNull();
  });
});
