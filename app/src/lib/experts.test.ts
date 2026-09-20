/**
 * 用例：专家下拉按入口专家所属 agent 过滤（核心用户路径）。
 *
 * 背景：安装器把各 agent 的 customModes 拍平进 mode_settings.json，
 * agent 归属只保留在 GET /api/workspaces/{id}/resources 的 agent_modes
 * 字段里（源自 .dawei/agents/<slug>/modes.yaml）。
 * 用户从「原创论文」入口进入任务页时，下拉应只显示 paper-team 的专家，
 * 而不是整个工作区的全部 mode（63 个）。
 */
import { describe, expect, it } from "vitest";
import type { WorkspaceMode } from "@/lib/store";
import { modesToExperts, scopeModesByExpert } from "@/lib/experts";

const mode = (slug: string, name = slug): WorkspaceMode => ({
  slug,
  name,
  description: "",
  source: "workspace",
});

// 模拟 gelu-research 全量安装后的工作区：基座 + 三条流水线团队的 modes
const WORKSPACE_MODES: WorkspaceMode[] = [
  mode("orchestrator", "🧿 Orchestrator"),
  mode("pdca", "🔄 PDCA"),
  mode("paper-orchestrator", "🧪 论文主编"),
  mode("paper-methods", "🧪 方法设计"),
  mode("review-orchestrator", "🔬 综述主编"),
  mode("review-surveyor", "🔬 文献普查"),
  mode("lens-orchestrator", "👓 格律透镜"),
  mode("analysis", "Analysis"),
];

const AGENT_MODES: Record<string, string[]> = {
  "paper-team": ["paper-orchestrator", "paper-methods"],
  "review-team": ["review-orchestrator", "review-surveyor"],
  "lens-team": ["lens-orchestrator"],
};

describe("modesToExperts name/icon 去重", () => {
  it("name 中的 emoji 前缀被剥离，icon 单独持有，避免下拉里图标重复显示", () => {
    const experts = modesToExperts([
      mode("quality-steward", "✅ Quality Steward"),
      mode("review-writer", "✍️ Review Writer"),
      mode("methods", "🧪 方法设计"),
    ]);
    expect(experts.map((e) => e.name)).toEqual(["Quality Steward", "Review Writer", "方法设计"]);
    expect(experts.map((e) => e.icon)).toEqual(["✅", "✍️", "🧪"]);
  });

  it("无 emoji 前缀的 name 原样保留", () => {
    const experts = modesToExperts([mode("analysis", "Analysis")]);
    expect(experts[0].name).toBe("Analysis");
    expect(experts[0].icon).toBe("");
  });
});

describe("scopeModesByExpert", () => {
  it("原创论文入口（paper-orchestrator）→ 只返回 paper-team 的 modes", () => {
    const scoped = scopeModesByExpert(WORKSPACE_MODES, AGENT_MODES, "paper-orchestrator");
    expect(scoped.map((m) => m.slug)).toEqual(["paper-orchestrator", "paper-methods"]);
  });

  it("综述入口（review-orchestrator）→ 只返回 review-team 的 modes", () => {
    const scoped = scopeModesByExpert(WORKSPACE_MODES, AGENT_MODES, "review-orchestrator");
    expect(scoped.map((m) => m.slug)).toEqual(["review-orchestrator", "review-surveyor"]);
  });

  it("无 agent_modes（未装团队 / 旧引擎）→ 回退全量", () => {
    const scoped = scopeModesByExpert(WORKSPACE_MODES, undefined, "paper-orchestrator");
    expect(scoped).toBe(WORKSPACE_MODES);
  });

  it("未选专家（expertId 空）→ 回退全量", () => {
    expect(scopeModesByExpert(WORKSPACE_MODES, AGENT_MODES, undefined)).toBe(WORKSPACE_MODES);
    expect(scopeModesByExpert(WORKSPACE_MODES, AGENT_MODES, null)).toBe(WORKSPACE_MODES);
    expect(scopeModesByExpert(WORKSPACE_MODES, AGENT_MODES, "")).toBe(WORKSPACE_MODES);
  });

  it("基座专家（不属于任何 agent，如 analysis）→ 回退全量", () => {
    const scoped = scopeModesByExpert(WORKSPACE_MODES, AGENT_MODES, "analysis");
    expect(scoped).toBe(WORKSPACE_MODES);
  });

  it("agent 声明了 mode 但工作区缺失（过滤后为空）→ 回退全量，不出空下拉", () => {
    const partial: Record<string, string[]> = { "paper-team": ["paper-orchestrator"] };
    const scoped = scopeModesByExpert(
      [mode("analysis"), mode("pdca")],
      partial,
      "paper-orchestrator",
    );
    expect(scoped.length).toBe(2);
  });

  it("空映射（{}）等价于无归属 → 回退全量", () => {
    expect(scopeModesByExpert(WORKSPACE_MODES, {}, "paper-orchestrator")).toBe(WORKSPACE_MODES);
  });

  it("与 modesToExperts 组合：框架 mode 仍被排除", () => {
    const experts = modesToExperts(
      scopeModesByExpert(WORKSPACE_MODES, AGENT_MODES, "paper-orchestrator"),
    );
    // paper-team 无框架 mode，两个专家都保留
    expect(experts.map((e) => e.id).sort()).toEqual(["paper-methods", "paper-orchestrator"]);
  });
});
