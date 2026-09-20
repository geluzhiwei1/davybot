# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""行业调研（Industry Research）工作区服务 — Deep Research 通用框架的第一个复用流水线。

PRD §10 #4 复用扩展: 本模块不写任何工作区/GATE/执行器逻辑，
只声明 PipelineSpec + 少量业务 hook，即获得与产品调研完全一致的基础设施:
- 工作区生命周期（created → running → GATE 暂停 → completed / failed / paused / needs_manual）
- GATE-0 需求确认 / GATE-1 资料完备性审核（拒绝 → 回退 stage-02 补采）
- dry-run 占位推进 / ResearchExecutor 真实 LLM 执行（复用同一个执行器类）
- REST 面（dawei/api/deep_research.py generic router, /api/deep-research/pipelines/industry/...）
- dao 历史 / 报告分享 / report.html（框架内置）

流水线: 4 phase × 7 stage
    phase-00-prepare        stage-00 范围定义
    phase-01-discovery      stage-01 搜索策略 / stage-02 资料采集 → GATE-1（审核通过才进入分析）
    phase-02-analysis       stage-03 行业全景 / stage-04 价值链
    phase-03-report         stage-05 报告撰写 / stage-06 导出打包

真实执行: industry-research-team mode team 的 SSOT 在 market resources
（normos-market-resources/resources/industry-research-team/agents/industry-research/
modes.yaml，2026-09-16 §8 兜底移除后经 market 安装进入工作区），
POST .../start?dry_run=false 即走 ResearchExecutor 真实 LLM 执行。
"""

from __future__ import annotations

import json
from pathlib import Path

from dawei.workspace.deep_research_framework import (
    DeepResearchServiceBase,
    PipelineSpec,
    ResearchExecutor,
    StageDef,
    register_pipeline,
)

INDUSTRY_STAGES: list[tuple[str, str, str, str]] = [
    ("stage-00-scope-init", "phase-00-prepare", "范围定义", "ind-research-preparer"),
    ("stage-01-search-strategy", "phase-01-discovery", "搜索策略", "ind-source-collector"),
    ("stage-02-source-collect", "phase-01-discovery", "资料采集", "ind-source-collector"),
    ("stage-03-landscape", "phase-02-analysis", "行业全景", "ind-landscape-analyst"),
    ("stage-04-value-chain", "phase-02-analysis", "价值链分析", "ind-landscape-analyst"),
    ("stage-05-report-draft", "phase-03-report", "报告撰写", "ind-report-writer"),
    ("stage-06-export", "phase-03-report", "导出打包", "ind-export-finisher"),
]

SPEC = PipelineSpec(
    slug="industry-research",
    name="行业调研",
    prompt_label="行业调研流水线",
    team="industry-research",
    mode_team="industry-research-team",
    stages=tuple(StageDef(id=sid, phase=phase, title=title, mode=mode) for sid, phase, title, mode in INDUSTRY_STAGES),
    phase_labels={
        "phase-00-prepare": "准备 · prepare",
        "phase-01-discovery": "资料发现 · discovery",
        "phase-02-analysis": "行业分析 · analysis",
        "phase-03-report": "报告交付 · report",
    },
    gate_after_stage={"stage-03-landscape": "GATE-1"},  # stage-00..02 采集完成后审核，通过才进入分析
    gate_rollback_stage={"GATE-1": "stage-02-source-collect"},
    gate_labels={"GATE-0": "需求确认", "GATE-1": "资料完备性审核"},
    stage_artifacts={
        "stage-00-scope-init": ("scope.md", "keywords.json"),
        "stage-01-search-strategy": ("search_plan.yaml", "sources.json"),
        "stage-02-source-collect": ("sources.jsonl", "collect_meta.json"),
        "stage-03-landscape": ("landscape.md", "landscape.json"),
        "stage-04-value-chain": ("value_chain.md", "key_players.json"),
        "stage-05-report-draft": ("report_final.md",),
        "stage-06-export": ("export_log.json",),
    },
    stage_minutes={sid: 5 + i for i, (sid, _, _, _) in enumerate(INDUSTRY_STAGES)},
    required_input_sections=("## Overview", "## Goals", "### 必须", "### 优选", "## 约定"),
    description="行业深度调研：4 phase × 7 stage，资料采集 → 行业全景/价值链 → 行业报告（GATE-0 需求确认 / GATE-1 资料完备性审核）",
)

# 简化模板（无独立 templates.yaml；generic router 的 template 概念对本流水线可选）
BUILTIN_TOPICS: list[dict] = [
    {"slug": "industry-ai-legal", "name": "AI + 法律行业", "description": "法律科技行业全景、价值链与格局"},
    {"slug": "industry-generic", "name": "自定义行业", "description": "任意行业的结构化深度调研"},
]

# mode team（SSOT 见 normos-market-resources/resources/industry-research-team/
# agents/industry-research/modes.yaml，2026-09-16 §8 兜底移除后经 market 安装;
# 2026-09-16 Phase 3 §4.8 重命名,旧 slug discovery/analysis/report/export 入 aliases;
# prepare 不设 —— market gelu review-team 已占 slug prepare）
MODE_TEAM_MODES = ["ind-research-preparer", "ind-source-collector", "ind-landscape-analyst", "ind-report-writer", "ind-export-finisher"]


class IndustryResearchService(DeepResearchServiceBase):
    """行业调研服务 — 仅覆写报告汇总 hook，其余全部复用框架。"""

    def __init__(self, storage_root: Path | None = None):
        super().__init__(SPEC, storage_root)

    @property
    def default_template_slug(self) -> str:
        return "industry-generic"

    def list_templates(self) -> list[dict]:
        return [dict(t, is_builtin=True, category="行业调研") for t in BUILTIN_TOPICS]

    def write_references(self, ws_dir: Path, params: dict) -> None:
        (ws_dir / "references" / "industry-research-mode-team.json").write_text(
            json.dumps(
                {
                    "team": SPEC.team,
                    "mode_team": SPEC.mode_team,
                    "modes": MODE_TEAM_MODES,
                    "source": "normos-market-resources/resources/industry-research-team/agents/industry-research/modes.yaml",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def on_stage_completed(self, ws_dir: Path, meta: dict, stage: dict, stage_dir: Path) -> None:
        # stage-05 报告定稿 → 汇总到 reports/（stage-06 由框架生成 report.html/report 分享）
        if stage["id"] == "stage-05-report-draft":
            report = stage_dir / "report_final.md"
            reports_dir = ws_dir / "reports"
            reports_dir.mkdir(exist_ok=True)
            (reports_dir / "report_final.md").write_text(report.read_text(encoding="utf-8"), encoding="utf-8")


# 模块级单例 + 执行器 + 注册表（generic router / 分享反查可见）
industry_research_service = IndustryResearchService()
industry_research_service.executor = ResearchExecutor(industry_research_service)
register_pipeline("industry", industry_research_service)
