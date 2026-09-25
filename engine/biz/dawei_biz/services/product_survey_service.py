# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""产品调研（Product Survey）工作区服务。

设计文档: project/docs/PRD-gelu-diaoyan/prd-产品调研.md

职责（PRD §10 #4 后）:
- 继承 Deep Research 通用框架（deep_research_framework.DeepResearchServiceBase），
  工作区生命周期 / GATE 状态机 / retry / duplicate / 审计 / 产物 / 分享 / dao 历史
  全部复用框架实现；本模块只保留产品调研业务差异（hook）:
    - 模板数据加载（dawei/data/templates/product-survey/templates.yaml）
    - dao.md 渲染与四段校验（§2.4）
    - 维度覆盖 / GATE-1 预览（解析 stage-02 candidates.jsonl，§4.2）
    - reports 汇总（report_final.md / report.pdf）与指标口径
- 流水线: 6 phase × 11 stage，GATE-0 需求确认 → GATE-1 维度审核
    dry_run=True  → 同步占位推进（可演示/可测试）
    dry_run=False → 真实执行（ResearchExecutor，通用执行器）
"""

from __future__ import annotations

import json
import logging
import random
import re
from pathlib import Path
from typing import Any, Optional

import yaml

from dawei_biz.services.deep_research_framework import (
    DeepResearchError,
    DeepResearchServiceBase,
    PipelineSpec,
    StageDef,
    _now_iso,  # noqa: F401  向后兼容 re-export（executor 旧引用）
    register_pipeline,
)

logger = logging.getLogger(__name__)

# 业务错误（框架 DeepResearchError 的别名，router/test 既有引用保持不变）
ProductSurveyError = DeepResearchError

# ============================================================
# 流水线常量（6 phase × 11 stage，与 .roomodes / product-survey 产物一致）
# ============================================================

# (stage_id, phase, 中文标题, 负责 mode)
PIPELINE_STAGES: list[tuple[str, str, str, str]] = [
    ("stage-00-scope-init", "phase-00-prepare", "范围定义", "survey-preparer"),
    ("stage-01-search-strategy", "phase-01-product-discovery", "搜索策略", "survey-product-collector"),
    ("stage-02-product-collect", "phase-01-product-discovery", "候选采集", "survey-product-collector"),
    ("stage-03-product-screen", "phase-02-product-analysis", "产品筛选", "survey-product-analyst"),
    ("stage-04-deep-dive", "phase-02-product-analysis", "深度分析", "survey-product-analyst"),
    ("stage-05-market-landscape", "phase-03-synthesis", "市场格局", "survey-trend-synthesizer"),
    ("stage-06-trend-insight", "phase-03-synthesis", "趋势洞察", "survey-trend-synthesizer"),
    ("stage-07-structural-outline", "phase-04-report-writing", "结构大纲", "survey-report-writer"),
    ("stage-08-section-draft", "phase-04-report-writing", "章节撰写", "survey-report-writer"),
    ("stage-09-integration-polish", "phase-04-report-writing", "整合润色", "survey-report-writer"),
    ("stage-10-export", "phase-05-export", "导出打包", "survey-export-finisher"),
]

PHASE_LABELS = {
    "phase-00-prepare": "准备 · prepare",
    "phase-01-product-discovery": "产品发现 · product-discovery",
    "phase-02-product-analysis": "产品分析 · product-analysis",
    "phase-03-synthesis": "综合洞察 · synthesis",
    "phase-04-report-writing": "报告写作 · report-writing",
    "phase-05-export": "导出交付 · export",
}

STAGE_IDS = [s[0] for s in PIPELINE_STAGES]

# stage-03 完成后进入 GATE-1（维度审核）；拒绝 → 回退 stage-02 补采
GATE_AFTER_STAGE = {"stage-03-product-screen": "GATE-1"}
GATE_ROLLBACK_STAGE = {"GATE-1": "stage-02-product-collect"}

GATE_LABELS = {"GATE-0": "需求确认", "GATE-1": "维度审核"}

MAX_GATE_ROUNDS = 3
GATE_TIMEOUT_HOURS = 24

DAO_REQUIRED_SECTIONS = ["## Overview", "## Goals", "### 必须", "### 优选", "## 约定"]

MODE_TEAM_MODES = [
    "survey-preparer", "survey-product-collector", "survey-product-analyst", "survey-trend-synthesizer", "survey-report-writer", "survey-export-finisher", "survey-product-searcher",
]

# 每阶段占位产物（dry-run 落盘，真实执行由 Agent 按契约产出）
STAGE_ARTIFACTS: dict[str, list[str]] = {
    "stage-00-scope-init": ["scope.md", "keywords.json", "targets.json"],
    "stage-01-search-strategy": ["search_plan.yaml", "sources.json", "product_schema.json"],
    "stage-02-product-collect": ["candidates.jsonl", "collect_meta.json"],
    "stage-03-product-screen": ["shortlist.jsonl", "screen_meta.json"],
    "stage-04-deep-dive": ["cards/P_D1_001.md", "cards/P_D1_002.md", "feature_matrix.json", "competitive_map.json"],
    "stage-05-market-landscape": ["landscape.md", "landscape.json", "market_data.json"],
    "stage-06-trend-insight": ["trends.md", "evolution_roadmap.md", "insights.json"],
    "stage-07-structural-outline": ["outline.md"],
    "stage-08-section-draft": ["report_draft.md"],
    "stage-09-integration-polish": ["report_final.md"],
    "stage-10-export": ["export_log.json"],
}

STAGE_MINUTES = {sid: 4 + i for i, sid in enumerate(STAGE_IDS)}  # 4..14 分钟

CANDIDATES_PATH = "output/phase-01-product-discovery/stage-02-product-collect/candidates.jsonl"

# ---- 框架 spec 声明（模块常量为唯一事实来源）----
SPEC = PipelineSpec(
    slug="product-survey",
    name="产品调研",
    prompt_label="产品调研流水线",
    team="product-survey",
    mode_team="product-survey-team",
    stages=tuple(StageDef(id=sid, phase=phase, title=title, mode=mode) for sid, phase, title, mode in PIPELINE_STAGES),
    phase_labels=PHASE_LABELS,
    gate_after_stage=GATE_AFTER_STAGE,
    gate_rollback_stage=GATE_ROLLBACK_STAGE,
    gate_labels=GATE_LABELS,
    stage_artifacts={sid: tuple(rels) for sid, rels in STAGE_ARTIFACTS.items()},
    stage_minutes=STAGE_MINUTES,
    max_gate_rounds=MAX_GATE_ROUNDS,
    gate_timeout_hours=GATE_TIMEOUT_HOURS,
    required_input_sections=tuple(DAO_REQUIRED_SECTIONS),
    description="AI 产品全景调研：6 phase × 11 stage，候选采集 → 深度分析 → 全景报告（GATE-0 需求确认 / GATE-1 维度审核）",
)


class ProductSurveyService(DeepResearchServiceBase):
    """产品调研工作区服务（框架 + 业务 hook；无状态 HTTP 调用，元数据落盘 workspace.json）。"""

    def __init__(self, templates_path: Optional[Path] = None, storage_root: Optional[Path] = None):
        super().__init__(SPEC, storage_root)
        self._templates_path = templates_path or (
            Path(__file__).parent.parent / "templates" / "product-survey" / "templates.yaml"
        )
        self._templates: Optional[list[dict[str, Any]]] = None

    # --------------------------------------------------------
    # 模板
    # --------------------------------------------------------

    def _load_templates(self) -> list[dict[str, Any]]:
        if self._templates is None:
            with open(self._templates_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            templates = data.get("templates", [])
            for t in templates:
                t.setdefault("default_dao_path", f"examples/{t.get('slug', '')}/dao.md")
                t.setdefault("thumbnail", None)
                t.setdefault("updated_at", "2026-08-31T00:00:00+00:00")
            self._templates = templates
        return self._templates

    def list_templates(self) -> list[dict[str, Any]]:
        """模板市场卡片数据（§6.3 契约字段）。"""
        result = []
        for t in self._load_templates():
            result.append(
                {
                    "slug": t["slug"],
                    "name": t["name"],
                    "category": t["category"],
                    "icon": t.get("icon"),
                    "description": t.get("description", "").strip(),
                    "estimated_products": t["estimated_products"],
                    "estimated_dimensions": t["estimated_dimensions"],
                    "estimated_minutes": t["estimated_minutes"],
                    "tags": t.get("tags", []),
                    "thumbnail": t.get("thumbnail"),
                    "default_dao_path": t.get("default_dao_path"),
                    "is_builtin": t.get("is_builtin", True),
                    "updated_at": t.get("updated_at"),
                }
            )
        return result

    def get_template(self, slug: str) -> dict[str, Any]:
        for t in self._load_templates():
            if t["slug"] == slug:
                return t
        raise ProductSurveyError(f"Template not found: {slug}", status_code=404)

    @property
    def default_template_slug(self) -> str:
        return "ai-short-video"

    # --------------------------------------------------------
    # dao.md 生成（GATE-0 前端预览 / 落盘）
    # --------------------------------------------------------

    def render_dao_md(
        self,
        template_slug: str,
        topic: str,
        background: str = "",
        audience: str = "",
        dimensions: Optional[list[dict[str, Any]]] = None,
        success_criteria: Optional[dict[str, Any]] = None,
        user_input: str = "",
    ) -> str:
        """按 §2.4 dao.md 模板结构渲染（Overview/Goals/成功标准/约定 四段完整）。"""
        tpl = self.get_template(template_slug)
        dims = dimensions or [
            {"key": d["key"], "name": d["name"], "description": d["description"]} for d in tpl["dimensions"]
        ]
        sc = success_criteria or {}
        min_per_dim = sc.get("min_products_per_dimension", 10)
        total_min = sc.get("min_total_products", max(tpl["estimated_products"], min_per_dim * len(dims)))
        ratio = sc.get("china_overseas_ratio", "1:2")
        pricing = int(sc.get("pricing_completeness", 0.7) * 100)

        dim_lines = "\n".join(
            f"{i}. **{d['key']}: {d['name']}** — {d.get('description', '')}" for i, d in enumerate(dims, 1)
        )
        goals = tpl.get("goals_hints", [])
        goal_lines = "\n".join(f"- {g}" for g in goals) if goals else "- 建立全维度产品索引"

        return f"""# dao.md

## Overview

对全球范围内 **AI（大模型、智能体、深度学习）在{topic}领域的产品应用**做系统性调研。
聚焦**商业产品**——已上市或公测中的 AI 驱动工具、平台与 SaaS 服务，覆盖海内外市场。

{f"调研背景：{background}" if background else ""}
{f"目标读者：{audience}" if audience else ""}
{f"用户原始输入：{user_input}" if user_input else ""}

调研围绕 {len(dims)} 个维度展开（每个维度用一句话 + 子项列表描述）：
{dim_lines}

## Goals

- 建立 {len(dims)} 个维度下的产品索引（含公司、产品名、核心功能、定价、目标市场）
- 按维度梳理产品功能矩阵与差异化定位
- 识别各维度的市场格局（头部产品、新兴玩家、中国 vs 海外）
- 提炼关键技术趋势与商业模式洞察
- 产出面向行业决策者的{topic}全景报告

### 调研重点

{goal_lines}

## 成功标准

达成如下要求后才能结束。

### 必须

如下要求，必须完全实现，100% 符合。

- 每个维度收录 ≥{min_per_dim} 个产品，总计 ≥{total_min} 个产品
- 每个产品包含：公司、产品名、网址、核心功能描述、定价层级、目标客户群、AI 技术栈
- 覆盖中国与海外市场（比例不低于 {ratio}）
- 产品信息来源可追溯（官网、行业报告、权威评测）

### 优选

如下要求，要尽量符合。

- 包含市场规模数据（各细分赛道的市场规模与增速）
- 包含融资/估值信息（头部公司融资状态）
- 绘制竞品对比矩阵（功能覆盖、定价、技术路线）
- 识别各维度的"空白地带"（未被满足的需求或产品缺口）

## 约定

- 产品信息优先来源：官网 > 行业报告 > 权威评测 > 社区讨论
- 所有产品信息需标注来源 URL
- 定价信息标注采集日期（价格变动快）
- 中国产品标注中英文双语名称
- 不收录纯概念/未发布产品，需有可访问的官网或 App
- AI 技术栈标注尽可能具体（如 "GPT-4" 而非仅 "LLM"）
- 种子产品索引在 `phase-00-prepare/seed.md`
"""

    def validate_dao_md(self, content: str) -> dict[str, Any]:
        """GATE-0 校验摘要：四段结构完整且非空。"""
        return self.validate_input_doc(content)

    # --------------------------------------------------------
    # 框架 hook 实现
    # --------------------------------------------------------

    async def create_workspace(
        self,
        template_slug: str,
        topic: str,
        mode: str = "direct",
        background: str = "",
        audience: str = "",
        user_input: str = "",
        scope: Optional[dict[str, Any]] = None,
        dimensions: Optional[list[dict[str, Any]]] = None,
        success_criteria: Optional[dict[str, Any]] = None,
        dao_md: Optional[str] = None,
        user_id: str = "anonymous",
        tenant_id: str = "default",
        skip_gate0: bool = False,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        """创建工作区：模板解析 + 维度选择后转调框架通用脚手架。"""
        tpl = self.get_template(template_slug)
        if mode not in ("direct", "wizard"):
            raise ProductSurveyError(f"Invalid mode: {mode}")
        if not topic or not topic.strip():
            raise ProductSurveyError("topic is required")

        selected_dims = dimensions or [
            {"key": d["key"], "name": d["name"], "description": d["description"]} for d in tpl["dimensions"]
        ]
        params = {
            "template_slug": template_slug,
            "template_name": tpl["name"],
            "topic": topic,
            "mode": mode,
            "background": background,
            "audience": audience,
            "user_input": user_input,
            "scope": scope or tpl.get("default_scope", {}),
            "dimensions": selected_dims,
            "success_criteria": success_criteria or {},
            "input_doc": dao_md,
        }
        return await self._create_workspace_internal(
            params, user_id=user_id, tenant_id=tenant_id, skip_gate0=skip_gate0, dry_run=dry_run
        )

    def render_input_doc(self, params: dict[str, Any]) -> str:
        return self.render_dao_md(
            params["template_slug"],
            params["topic"],
            params.get("background", ""),
            params.get("audience", ""),
            params.get("dimensions"),
            params.get("success_criteria"),
            params.get("user_input", ""),
        )

    def build_task_params(self, params: dict[str, Any]) -> dict[str, Any]:
        return {
            "template_slug": params.get("template_slug"),
            "topic": params.get("topic"),
            "mode": params.get("mode"),
            "background": params.get("background", ""),
            "audience": params.get("audience", ""),
            "user_input": params.get("user_input", ""),
            "scope": params.get("scope") or {},
            "dimensions": params.get("dimensions"),
            "success_criteria": params.get("success_criteria") or {},
        }

    def write_references(self, ws_dir: Path, params: dict[str, Any]) -> None:
        (ws_dir / "references" / "product-survey-mode-team.json").write_text(
            json.dumps(
                {
                    "team": SPEC.team,
                    "mode_team": SPEC.mode_team,
                    "modes": MODE_TEAM_MODES,
                    "source": "normos-market-resources/resources/product-survey-team/agents/product-survey/modes.yaml",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def render_agent_instructions(self, params: dict[str, Any]) -> str:
        topic = params.get("topic", "")
        dims = params.get("dimensions") or []
        dim_lines = "\n".join(f"- {d['key']}: {d['name']} — {d.get('description', '')}" for d in dims)
        return f"""# {topic} — Agent 工作指令

你已加入产品调研工作区（mode team: product-survey-team），按 6 phase × 11 stage 流水线执行。

## 输入

1. `input/dao.md` — 调研需求文档（GATE-0 确认后的唯一权威输入）
2. `input/task_parameters.json` — 用户提交的向导参数

## 维度（{len(dims)} 个）

{dim_lines}

## 流水线

- phase-00 prepare → stage-00 范围定义
- phase-01 product-discovery → stage-01 搜索策略 / stage-02 候选采集（Web Search，不使用检索类 MCP）
- phase-02 product-analysis → stage-03 产品筛选（GATE-1）/ stage-04 深度分析
- phase-03 synthesis → stage-05 市场格局 / stage-06 趋势洞察
- phase-04 report-writing → stage-07 大纲 / stage-08 起草 / stage-09 润色
- phase-05 export → stage-10 导出（Pandoc + XeLaTeX）

## 约定

- 数据源优先级：官网 > 行业报告 > 权威评测 > 社区讨论
- 所有产品信息标注来源 URL；定价标注采集日期；缺失字段留空不编造
- 产物写入 `output/phase-XX/stage-YY/`，最终交付物写入 `reports/`
"""

    def initial_metrics(self, params: dict[str, Any]) -> dict[str, Any]:
        return {
            "products_collected": 0,
            "products_deep_carded": 0,
            "dimensions_covered": len(params.get("dimensions") or []),
            "pricing_completeness": 0.0,
            "china_overseas_ratio": None,
            "total_tokens": 0,
            "total_minutes": 0,
        }

    def stub_artifact(self, meta: dict[str, Any], stage: dict[str, Any], rel: str) -> str:
        if rel.startswith("cards/"):
            stem = Path(rel).stem
            return f"# Product Card: {meta.get('topic', '')} sample ({stem})\n\n1. **card_id**: {stem}\n2. **product_name**: 待真实执行填充\n"
        return super().stub_artifact(meta, stage, rel)

    def on_stage_completed(self, ws_dir: Path, meta: dict[str, Any], stage: dict[str, Any], stage_dir: Path) -> None:
        """产品调研指标口径 + reports 汇总（PRD §6.7 metrics）。"""
        metrics = meta["metrics"]
        if stage["id"] == "stage-02-product-collect":
            coverage = self._dimension_coverage(meta)
            metrics["products_collected"] = sum(coverage.values())
        if stage["id"] == "stage-03-product-screen":
            coverage = self._dimension_coverage(meta)
            counts = list(coverage.values())
            metrics["products_deep_carded"] = max(0, sum(counts) - 4)
            metrics["dimensions_covered"] = len(counts)
            scan = self._scan_candidates(meta)
            metrics["pricing_completeness"] = scan["pricing_pct"] if scan["total"] else 0.76
            china = scan["china"] or max(1, round(sum(counts) / 3))
            metrics["china_overseas_ratio"] = f"{china}:{(scan['overseas'] or (sum(counts) - china))}"
        if stage["id"] == "stage-09-integration-polish":
            report = stage_dir / "report_final.md"
            reports_dir = ws_dir / "reports"
            reports_dir.mkdir(exist_ok=True)
            (reports_dir / "report_final.md").write_text(report.read_text(encoding="utf-8"), encoding="utf-8")
        if stage["id"] == "stage-10-export":
            pdf = stage_dir / "report.pdf"
            reports_dir = ws_dir / "reports"
            reports_dir.mkdir(exist_ok=True)
            if pdf.is_file():  # 真实执行：export mode 已生成
                (reports_dir / "report.pdf").write_bytes(pdf.read_bytes())
            else:  # dry-run 占位 / Pandoc 不可用时保留占位（PRD: 导出失败不阻塞）
                (reports_dir / "report.pdf").write_bytes(b"%PDF-1.4\n% placeholder report\n")

    def enrich_detail(self, ws_dir: Path, meta: dict[str, Any]) -> None:
        # GATE-1 预览数据（维度覆盖）——供前端弹窗展示
        gate1 = self._gate(meta, "GATE-1")
        if gate1["status"] == "pending" or gate1.get("round", 0) > 0:
            meta["gate1_preview"] = self._gate1_preview(ws_dir, meta)

    def regenerate_input_doc(self, ws_dir: Path, meta: dict[str, Any], gate: dict[str, Any], note: str) -> None:
        """GATE-0 拒绝 → 重新生成 dao.md（补充说明附加到背景；历史版本已由框架归档）。"""
        params = self._read_task_params(ws_dir)
        regenerated = self.render_dao_md(
            params.get("template_slug", meta.get("slug")),
            params.get("topic", meta.get("topic")),
            background=params.get("background", ""),
            audience=params.get("audience", ""),
            dimensions=params.get("dimensions"),
            success_criteria=params.get("success_criteria"),
            user_input=params.get("user_input", ""),
        )
        if note:
            regenerated += f"\n\n<!-- 用户补充说明（第 {gate['round']} 轮）：{note} -->\n"
        (ws_dir / SPEC.input_doc_path).write_text(regenerated, encoding="utf-8")

    def duplicate_extras(self, src_ws: Path, dst_ws: Path) -> None:
        # scope.md 等范围产物一并复制（PRD §6.5: 复制 dao.md + scope.md）
        for rel in ("output/phase-00-prepare/stage-00-scope-init/scope.md",):
            src_f = src_ws / rel
            if src_f.exists():
                dst_f = dst_ws / rel
                dst_f.parent.mkdir(parents=True, exist_ok=True)
                dst_f.write_text(src_f.read_text(encoding="utf-8"), encoding="utf-8")

    # --------------------------------------------------------
    # 维度覆盖 / GATE-1 预览（解析真实 candidates.jsonl）
    # --------------------------------------------------------

    def _dimension_coverage(self, meta: dict[str, Any]) -> dict[str, int]:
        """GATE-1 维度覆盖统计。

        真实执行：解析 stage-02 candidates.jsonl 按维度计数；
        dry-run / 文件缺失：确定性占位数据（14 递减，下限 7）。
        """
        dims = self._task_dimensions(meta)
        scan = self._scan_candidates(meta)
        if scan["total"] > 0:
            by_name, by_key = scan["by_name"], scan["by_key"]
            coverage = {}
            for d in dims:
                coverage[d["name"]] = by_name.get(d["name"], 0) + by_key.get(d["key"], 0)
            return coverage
        return {d["name"]: max(7, 14 - i) for i, d in enumerate(dims)}

    def _scan_candidates(self, meta: dict[str, Any]) -> dict[str, Any]:
        """扫描 stage-02 candidates.jsonl → 维度/地域/定价统计（§4.2 20 字段 schema）。

        解析失败或文件缺失 → total=0（调用方回退占位数据）。
        """
        empty = {"total": 0, "by_name": {}, "by_key": {}, "china": 0, "overseas": 0, "pricing_pct": 0.0}
        ws_dir = self.storage_root / meta["workspace_id"]
        path = ws_dir / CANDIDATES_PATH
        if not path.is_file():
            return empty
        total = china = overseas = priced = 0
        by_name: dict[str, int] = {}
        by_key: dict[str, int] = {}
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                dim = str(rec.get("dimension") or "").strip()
                if not dim:
                    continue  # §4.2 契约必含 dimension；缺失视为占位数据（回退确定性统计）
                total += 1
                by_name[dim] = by_name.get(dim, 0) + 1
                if re.fullmatch(r"D\d+", dim):
                    by_key[dim] = by_key.get(dim, 0) + 1
                market = str(rec.get("market") or rec.get("region") or "").lower()
                if any(k in market for k in ("china", "中国", "cn", "domestic")):
                    china += 1
                else:
                    overseas += 1
                if str(rec.get("pricing_model") or rec.get("pricing_detail") or "").strip():
                    priced += 1
        except OSError:
            return empty
        return {
            "total": total,
            "by_name": by_name,
            "by_key": by_key,
            "china": china,
            "overseas": overseas,
            "pricing_pct": round(priced / total, 2) if total else 0.0,
        }

    def _task_dimensions(self, meta: dict[str, Any]) -> list[dict[str, Any]]:
        ws_dir = self.storage_root / meta["workspace_id"]
        p = ws_dir / "input" / "task_parameters.json"
        if p.exists():
            try:
                params = json.loads(p.read_text(encoding="utf-8"))
                if params.get("dimensions"):
                    return params["dimensions"]
            except (json.JSONDecodeError, OSError):
                pass
        return [{"key": f"D{i+1}", "name": f"维度{i+1}", "description": ""} for i in range(8)]

    def _gate1_preview(self, ws_dir: Path, meta: dict[str, Any]) -> dict[str, Any]:
        coverage = self._dimension_coverage(meta)
        items = [
            {"dimension": name, "count": count, "ok": count >= 10} for name, count in coverage.items()
        ]
        total = sum(coverage.values())
        scan = self._scan_candidates(meta)
        if scan["total"] > 0:
            china, overseas, pricing = scan["china"], scan["overseas"], scan["pricing_pct"]
        else:
            china = max(1, round(total / 3))
            overseas = total - china
            pricing = 0.76
        return {
            "products_collected": total,
            "dimensions": items,
            "region": {"china": china, "overseas": overseas},
            "pricing_completeness": pricing,
            "rollback_stage": GATE_ROLLBACK_STAGE["GATE-1"],
        }

    # --------------------------------------------------------
    # dao 历史（#5 diff 视图数据源，框架实现的便捷别名）
    # --------------------------------------------------------

    def get_dao_history(self, workspace_id: str) -> dict[str, Any]:
        return self.get_input_doc_history(workspace_id)


# 模块级单例（router 使用；测试可自行实例化注入 tmp 路径）
product_survey_service = ProductSurveyService()

# 真实执行器 + 流水线注册（此处导入避免循环依赖；executor 通过实例引用本服务）
from dawei_biz.services.deep_research_framework import ResearchExecutor  # noqa: E402

product_survey_service.executor = ResearchExecutor(product_survey_service)
register_pipeline("product", product_survey_service)
