# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Gelu Research Flow（科研审稿控制面）业务工具 — gelu-research-team 编队用。

设计文档：project/docs/PRD-gelu-yanjiu/gelu-research-flow-design.md §4.2。
认证：复用 AuthenticatedServiceClient，每请求从 local_context 注入当前用户 JWT
（多租户隔离，JWT 不进入 LLM 上下文）——与 market/normflow 组同款机制；
编队在用户会话内运行，回流调用自动携带该 JWT（设计风险 #3）。
可见性（mode-工具解耦后，原 RESTRICTED_GROUPS 组准入已删除）：无组级白名单——
本组工具经 gelu-research-team 编队安装进工作区后，任何模式均可经 search_tools
发现并调用（编队模式见 websocket/research_fleet.py RESEARCH_TEAM_MODES）。

P3 工具（§8）：journal_lookup / journal_rubric / paper_search / paper_get /
paper_import / review_run_create / review_submit（★ 结构化回流）。
P4 工具（§8）：journal_suggest（选刊推荐，控制面 heuristic-v1 代理）/
submission_check（投稿格式自检，逐项命中刊物 requirement）。
编队状态广播：websocket/research_fleet.py（research_agent_status）；
服务账号/无会话通道：dawei/research/bridge.py（设计 §4.1）。

工具纪律（§4.2）：结果瘦身——列表 ≤20 条、摘录 ≤160 字；run/paper/journal id
返回完整值（下游工具调用需要精确 id，不截断）。维度 weight/threshold 由控制面
rubric 快照应用（服务端计算 passed/加权，编队不自行加权）。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from dawei.core.decorators import safe_tool_operation
from dawei.tools.custom_base_tool import CustomBaseTool
from dawei.tools.custom_tools._service_client import (
    ServiceAuthError,
    ServiceUnavailableError,
    research_client,
)
from dawei.tools.custom_tools.async_utils import run_async

# inner-layer governance: 列表渲染上限（对齐 market/normflow 组）
_MAX_RENDER = 20
# 摘要截断长度（正文/答案摘录等长文本）
_EXCERPT = 160

_VERDICT_ZH = {
    "accept": "接收",
    "minor_revision": "小修",
    "major_revision": "大修",
    "reject": "拒稿",
}


async def _call_research(method: str, path: str, *, json_data: dict = None, params: dict = None, timeout: float = 20.0) -> dict:
    """Call gelu-research-flow API with the current user's JWT injected.

    Returns parsed JSON body, or {"error": ...} / {"_error": ...} on failure
    (mirrors market_tools._call_market contract).
    """
    try:
        if method.upper() == "GET":
            return await research_client.get(path, params=params, timeout=timeout)
        return await research_client.post(path, json_body=json_data, params=params, timeout=timeout)
    except ServiceAuthError as e:
        return {"error": "AUTH", "detail": str(e)}
    except ServiceUnavailableError as e:
        return {"error": "UNAVAILABLE", "detail": str(e)}
    except Exception as e:
        return {"error": f"research call failed: {e}"}


def _err(result: Any) -> str | None:
    """Extract error message from a _call_research result, if any."""
    if isinstance(result, dict) and result.get("error"):
        detail = result.get("detail") or ""
        return f"Error: {result['error']}" + (f" — {str(detail)[:300]}" if detail else "")
    if isinstance(result, dict) and result.get("_error"):
        detail = result.get("detail") or ""
        return f"Error: {result['_error']}" + (f" — {str(detail)[:300]}" if detail else "")
    return None


# ============================================================================
# 刊物域：档案 / rubric
# ============================================================================


class ResearchJournalLookupInput(BaseModel):
    query: str = Field(description="刊物名称 / ISSN / 缩写（如 'Nature Medicine' 或 '0028-0836'）")


class ResearchJournalLookupTool(CustomBaseTool):
    def __init__(self):
        super().__init__()
        self.name = "research_journal_lookup"
        self.description = "刊物档案查询：按名称/ISSN 检索刊物，返回最新指标（影响因子/分区/审稿周期）、投稿要求摘要与生效 rubric 概览。投稿选刊、按刊物标准评审前必用；返回的 journal_id 用于 research_journal_rubric / research_review_run_create。"
        self.args_schema = ResearchJournalLookupInput

    @safe_tool_operation("research_journal_lookup", fallback_value="Error: 刊物查询失败")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run(**kwargs))

    async def _async_run(self, query: str) -> str:
        result = await _call_research("GET", "/api/v1/journals", params={"q": query, "limit": 5})
        if e := _err(result):
            return e
        items = result.get("items") or []
        if not items:
            return f"## 刊物检索「{query}」\n\n未找到（控制面无该刊档案；可在 /research/journals 页面导入）。"
        top = items[0]
        jid = str(top.get("id", ""))
        lines = [f"## 刊物档案：{top.get('name', '?')}（最佳匹配，共 {len(items)} 条候选）\n"]
        detail = await _call_research("GET", f"/api/v1/journals/{jid}")
        if e := _err(detail):
            lines.append(f"- journal_id：{jid}（详情拉取失败：{e}）")
        else:
            lines.append(f"- journal_id：{jid}（完整 id，后续调用使用）")
            for k, label in (("issn", "ISSN"), ("publisher", "出版商"), ("kind", "类型"), ("discipline", "学科")):
                if detail.get(k):
                    lines.append(f"- {label}：{detail[k]}")
            metrics = detail.get("metrics") or []
            if metrics:
                m = metrics[0]
                parts = [
                    f"IF {m['impact_factor']}" if m.get("impact_factor") else "",
                    f"JCR {m['jcr_quartile']}" if m.get("jcr_quartile") else "",
                    f"CAS {m['cas_quartile']}" if m.get("cas_quartile") else "",
                    f"审稿周期 {m['review_cycle_days']} 天" if m.get("review_cycle_days") else "",
                ]
                lines.append(f"- 最新指标（{m.get('year', '?')}，{m.get('source', '?')}）：" + " · ".join(p for p in parts if p))
            reqs = detail.get("requirements") or []
            if reqs:
                req_txt = " | ".join(f"{r.get('article_type')} {r.get('word_limit') or '?'} 词" + ("（已验证）" if r.get("verified_at") else "") for r in reqs[:4])
                lines.append(f"- 投稿要求：{req_txt}")
            dims = (detail.get("rubric") or {}).get("dimensions") or []
            if dims:
                lines.append(f"- 生效 rubric：{len(dims)} 维（research_journal_rubric 查看权重/阈值）")
        if len(items) > 1:
            others = "、".join(f"{i.get('name', '?')}（{str(i.get('id', ''))[:8]}）" for i in items[1:4])
            lines.append(f"\n其他候选：{others}")
        return "\n".join(lines)


class ResearchJournalRubricInput(BaseModel):
    journal_id: str = Field(description="刊物 id（research_journal_lookup 返回的完整 journal_id）")


class ResearchJournalRubricTool(CustomBaseTool):
    def __init__(self):
        super().__init__()
        self.name = "research_journal_rubric"
        self.description = "获取刊物生效评审 rubric（维度 weight/threshold，全局默认 ⊕ 刊物覆盖），以 {journal_profile} 块注入提示词。peer-review / quality-gate 模式评审打分前必用；未指定刊物时控制面回退全局默认（等价现状）。"
        self.args_schema = ResearchJournalRubricInput

    @safe_tool_operation("research_journal_rubric", fallback_value="Error: rubric 获取失败")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run(**kwargs))

    async def _async_run(self, journal_id: str) -> str:
        result = await _call_research("GET", f"/api/v1/journals/{journal_id}/rubric")
        if e := _err(result):
            return e
        dims = result.get("dimensions") or []
        if not dims:
            return "## 刊物 rubric\n\n该刊未配置维度且全局默认为空（请联系管理员 seed 全局维度）。"
        lines = ["{journal_profile}", f"journal_id: {journal_id}", "dimensions:"]
        for d in dims:
            origin = "刊物覆盖" if d.get("origin") == "override" else "全局默认"
            lines.append(f"- {d['dimension_key']}（{d.get('display_name') or d['dimension_key']}）：weight={float(d.get('weight', 1.0)):.2f}，threshold={float(d.get('threshold', 7.5)):.2f} [{origin}]")
        lines.append("")
        lines.append("评审纪律：每维打 1-10 分；threshold 为该维通过线；weight 由控制面快照加权（编队勿自行加权）；dimension_scores 仅可使用上面列出的 dimension_key。")
        return "\n".join(lines)


# ============================================================================
# 文献域：检索 / 详情 / 导入
# ============================================================================


class ResearchPaperSearchInput(BaseModel):
    q: str = Field(description="检索词（标题/关键词）")
    fulltext: bool = Field(False, description="true=对首条结果做 kb2 全文向量检索（需已摄取）")
    limit: int = Field(10, ge=1, le=20, description="返回条数上限")


class ResearchPaperSearchTool(CustomBaseTool):
    def __init__(self):
        super().__init__()
        self.name = "research_paper_search"
        self.description = "检索库内文献元数据（标题/年份/出处/doi）；可选对首条结果做全文向量检索返回命中片段。回答「有哪些相关文献」、需要 paper_id 上下文时使用；库外文献先 research_paper_import。"
        self.args_schema = ResearchPaperSearchInput

    @safe_tool_operation("research_paper_search", fallback_value="Error: 文献检索失败")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run(**kwargs))

    async def _async_run(self, q: str, fulltext: bool = False, limit: int = 10) -> str:
        result = await _call_research("GET", "/api/v1/papers", params={"q": q, "limit": limit})
        if e := _err(result):
            return e
        items = result.get("items") or []
        total = result.get("total", len(items))
        if not items:
            return f"## 文献检索「{q}」\n\n库内无匹配（可用 research_paper_import 按 DOI/arXiv 导入）。"
        lines = [f"## 文献检索「{q}」（命中 {total}，显示 {min(len(items), _MAX_RENDER)}）\n"]
        for i, p in enumerate(items[:_MAX_RENDER], 1):
            meta = " · ".join(x for x in (str(p.get("year") or ""), p.get("venue") or "") if x)
            line = f"{i}. {str(p.get('title', ''))[:_EXCERPT]}"
            if meta:
                line += f"（{meta}）"
            line += f" — paper_id：{p.get('id', '')}"
            if p.get("doi"):
                line += f" doi:{p['doi']}"
            lines.append(line)
        if fulltext:
            top = items[0]
            ft = await _call_research("GET", f"/api/v1/papers/{top['id']}/fulltext", params={"query": q, "top_k": 5})
            lines.append(f"\n**全文命中（首条：{str(top.get('title', ''))[:60]}）**")
            if e := _err(ft):
                lines.append(f"- 不可用：{e}")
            else:
                for c in (ft.get("chunks") or [])[:5]:
                    score = c.get("score")
                    score_txt = f"{score:.2f}" if isinstance(score, (int, float)) else "?"
                    lines.append(f"- [{score_txt}] {str(c.get('text', ''))[:_EXCERPT]}…")
        return "\n".join(lines)


class ResearchPaperGetInput(BaseModel):
    paper_id: str = Field(description="文献 id（research_paper_search 返回的完整 paper_id）")
    query: str = Field("", description="可选：按主题/章节关键词做全文向量检索（空=仅元数据+摘要）")


class ResearchPaperGetTool(CustomBaseTool):
    def __init__(self):
        super().__init__()
        self.name = "research_paper_get"
        self.description = "查看文献完整元数据（作者/出处/摘要/引用数/摄取状态）；可选带 query 做 kb2 全文向量检索取指定主题片段。深读某篇文献、核查摄取状态时使用。"
        self.args_schema = ResearchPaperGetInput

    @safe_tool_operation("research_paper_get", fallback_value="Error: 文献详情获取失败")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run(**kwargs))

    async def _async_run(self, paper_id: str, query: str = "") -> str:
        result = await _call_research("GET", f"/api/v1/papers/{paper_id}")
        if e := _err(result):
            return e
        lines = ["## 文献详情\n"]
        lines.append(f"- 标题：{result.get('title', '?')}（paper_id：{paper_id}）")
        authors = [a.get("name", "") for a in (result.get("authors_json") or []) if isinstance(a, dict)]
        if authors:
            lines.append(f"- 作者：{'、'.join(authors[:8])}{'…' if len(authors) > 8 else ''}")
        meta = " · ".join(x for x in (str(result.get("year") or ""), result.get("venue") or "") if x)
        if meta:
            lines.append(f"- 出处：{meta}")
        for k, label in (("doi", "DOI"), ("arxiv_id", "arXiv"), ("citation_count", "被引")):
            if result.get(k) is not None:
                lines.append(f"- {label}：{result[k]}")
        lines.append(f"- 摄取：{result.get('ingest_status', '?')}" + (f"（{result.get('ingest_error', '')[:80]}）" if result.get("ingest_error") else ""))
        if result.get("abstract"):
            lines.append(f"\n**摘要**：{str(result['abstract'])[:300]}…")
        if query:
            ft = await _call_research("GET", f"/api/v1/papers/{paper_id}/fulltext", params={"query": query, "top_k": 5})
            lines.append(f"\n**全文命中（query：{query}）**")
            if e := _err(ft):
                lines.append(f"- 不可用：{e}")
            else:
                for c in (ft.get("chunks") or [])[:5]:
                    score = c.get("score")
                    score_txt = f"{score:.2f}" if isinstance(score, (int, float)) else "?"
                    lines.append(f"- [{score_txt}] {str(c.get('text', ''))[:_EXCERPT]}…")
        return "\n".join(lines)


class ResearchPaperImportInput(BaseModel):
    doi: str = Field("", description="DOI（10.xxxx/…）")
    arxiv_id: str = Field("", description="arXiv id（如 2401.12345）")
    pmid: str = Field("", description="PubMed PMID")
    collection_id: str = Field("", description="可选：导入即入文集")


class ResearchPaperImportTool(CustomBaseTool):
    def __init__(self):
        super().__init__()
        self.name = "research_paper_import"
        self.description = "按 DOI/arXiv/PMID 导入文献：控制面抓元数据建档并异步摄取全文（kb2）。评审/综述需要某篇库外文献时使用；摄取为后台任务，稍后用 research_paper_get 查全文。"
        self.args_schema = ResearchPaperImportInput

    @safe_tool_operation("research_paper_import", fallback_value="Error: 文献导入失败")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run(**kwargs))

    async def _async_run(self, doi: str = "", arxiv_id: str = "", pmid: str = "", collection_id: str = "") -> str:
        body = {k: v for k, v in {"doi": doi, "arxiv_id": arxiv_id, "pmid": pmid}.items() if v}
        if not body:
            return "Error: 需要至少一个标识（doi / arxiv_id / pmid）"
        if collection_id:
            body["collection_id"] = collection_id
        result = await _call_research("POST", "/api/v1/papers/import", json_data=body)
        if e := _err(result):
            return e
        status = str(result.get("ingest_status", "?"))
        lines = [
            "## 文献导入",
            f"- paper_id：{result.get('id', '')}（完整 id）",
            f"- 标题：{result.get('title', '?')}",
            f"- 摄取状态：{status}",
        ]
        if status == "queued":
            lines.append("- 提示：全文摄取为后台任务，稍后用 research_paper_get（带 query）检索全文。")
        elif status == "failed":
            lines.append(f"- 失败原因：{str(result.get('ingest_error', ''))[:160]}（可稍后重试）")
        return "\n".join(lines)


# ============================================================================
# 评审域：发起 run / ★ 结构化回流
# ============================================================================


class ResearchReviewRunCreateInput(BaseModel):
    journal_id: str = Field(description="目标刊物（决定 rubric 快照；research_journal_lookup 获取）")
    paper_id: str = Field("", description="库内文献 id（与 manuscript_kb_doc_id 二选一）")
    manuscript_kb_doc_id: str = Field("", description="稿件 kb 文档 id（库外稿件路径，此时 title 必填）")
    title: str = Field("", description="稿件标题（manuscript 路径必填；paper 路径自动取文献标题）")
    mode: str = Field(
        "peer_review",
        pattern="^(peer_review|presubmission|quick_critique)$",
        description="评审模式：peer_review=3 审稿人+质量门；presubmission=投稿前自查；quick_critique=轻量批判",
    )
    reviewer_keys: list[str] = Field(
        default_factory=list,
        description="审稿人 key（methodologist/domain_expert/statistician；空=模式默认组合）",
    )


class ResearchReviewRunCreateTool(CustomBaseTool):
    def __init__(self):
        super().__init__()
        self.name = "research_review_run_create"
        self.description = "发起评审 run：控制面展开刊物 rubric 快照（防漂移），run 进入 dispatched 状态等待审稿产出。返回 run_id 与快照维度清单——后续 research_review_submit 回流必须只用列出的 dimension_key。"
        self.args_schema = ResearchReviewRunCreateInput

    @safe_tool_operation("research_review_run_create", fallback_value="Error: 评审 run 创建失败")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run(**kwargs))

    async def _async_run(
        self,
        journal_id: str,
        paper_id: str = "",
        manuscript_kb_doc_id: str = "",
        title: str = "",
        mode: str = "peer_review",
        reviewer_keys: list | None = None,
    ) -> str:
        body: dict[str, Any] = {"journal_id": journal_id, "mode": mode}
        if paper_id:
            body["paper_id"] = paper_id
        if manuscript_kb_doc_id:
            body["manuscript_kb_doc_id"] = manuscript_kb_doc_id
        if title:
            body["title"] = title
        if reviewer_keys:
            body["reviewer_keys"] = reviewer_keys
        result = await _call_research("POST", "/api/v1/review-runs", json_data=body)
        if e := _err(result):
            return e
        snap = result.get("rubric_snapshot_json") or []
        dim_keys = [d.get("dimension_key", "?") for d in snap]
        lines = [
            "## 评审 run 已创建",
            f"- run_id：{result.get('id', '')}（完整 id，用于 research_review_submit 回流）",
            f"- 状态：{result.get('status', '?')}（{result.get('mode', '?')}）",
            f"- 审稿人：{'、'.join(result.get('reviewer_keys') or [])}",
            f"- rubric 快照（{len(snap)} 维）：{', '.join(dim_keys)}",
            "",
            "评审约定：dimension_scores 只能使用上面列出的 dimension_key；每维 1-10 分；verdict ∈ accept / minor_revision / major_revision / reject；weight/threshold 由控制面应用。",
        ]
        return "\n".join(lines)


class ResearchReviewSubmitInput(BaseModel):
    run_id: str = Field(description="评审 run id（research_review_run_create 返回的完整 run_id）")
    outputs: list[dict] = Field(
        default_factory=list,
        description=("审稿人产出列表，每项 {reviewer_key, overall_score(1-10), verdict(accept|minor_revision|major_revision|reject), dimension_scores: [{dimension_key, score(1-10), rationale}], strengths: [{point}], issues: [{id, point, severity}], persona: {}, model_meta: {}}"),
    )
    gate: dict = Field(default_factory=dict, description="可选，质量门聚合 {gate_key: 'G1', threshold, result: {...}}（建门待人审 decide）")
    complete: dict = Field(
        default_factory=dict,
        description="可选，收尾 {status: 'done'|'failed', dimension_scores: [汇总分， reviewer_key 留空], summary: {}, error}",
    )


class ResearchReviewSubmitTool(CustomBaseTool):
    def __init__(self):
        super().__init__()
        self.name = "research_review_submit"
        self.description = "★ 评审产出结构化回流：把审稿人意见/维度分（→ reviewer-outputs）、质量门聚合（→ gate）、汇总收尾（→ complete）写回控制面 run，运行详情页实时可见。outputs / gate / complete 至少给一项，按 outputs → gate → complete 顺序提交，遇错即停（FAST FAIL，修正后可重试，维度重报幂等覆盖）。"
        self.args_schema = ResearchReviewSubmitInput

    @safe_tool_operation("research_review_submit", fallback_value="Error: 评审回流失败")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run(**kwargs))

    async def _async_run(self, run_id: str, outputs: list | None = None, gate: dict | None = None, complete: dict | None = None) -> str:
        outputs, gate, complete = outputs or [], gate or {}, complete or {}
        if not (outputs or gate or complete):
            return "Error: outputs / gate / complete 至少提供一项"
        base = f"/api/v1/internal/review-runs/{run_id}"
        lines = [f"## 评审回流（run {run_id}）\n"]
        for out in outputs:
            r = await _call_research("POST", f"{base}/reviewer-outputs", json_data=out)
            if e := _err(r):
                return "\n".join(lines + [f"- reviewer {out.get('reviewer_key', '?')}：❌ {e}（已停止，修正后重试）"])
            verdict = str(r.get("verdict", "?"))
            lines.append(f"- reviewer {r.get('reviewer_key', '?')}：✅ overall {r.get('overall_score')} / {verdict}（{_VERDICT_ZH.get(verdict, verdict)}）")
        if gate:
            r = await _call_research("POST", f"{base}/gate", json_data=gate)
            if e := _err(r):
                return "\n".join(lines + [f"- gate {gate.get('gate_key', '?')}：❌ {e}（已停止）"])
            lines.append(f"- gate {r.get('gate_key', '?')}：✅ 已建门（threshold {r.get('threshold')}，待人审 decide）")
        if complete:
            r = await _call_research("POST", f"{base}/complete", json_data=complete)
            if e := _err(r):
                return "\n".join(lines + [f"- complete：❌ {e}（已停止）"])
            lines.append(f"- complete：✅ run → {r.get('status', '?')}")
        return "\n".join(lines)


# ============================================================================
# 投稿域（P4）：选刊推荐 / 格式自检
# ============================================================================


class ResearchJournalSuggestInput(BaseModel):
    abstract: str = Field("", description="稿件摘要（选刊主要依据）")
    keywords: list[str] = Field(default_factory=list, description="关键词列表")
    paper_id: str = Field("", description="库内文献 id（自动取其摘要+关键词，与显式输入互补）")
    discipline: str = Field("", description="可选：学科（如 'law' / 'computer science'，精确匹配加分）")
    article_type: str = Field("original", description="稿件类型：original|review|letter|case_report")
    top_n: int = Field(5, ge=3, le=6, description="返回推荐数（3-6）")


class ResearchJournalSuggestTool(CustomBaseTool):
    def __init__(self):
        super().__init__()
        self.name = "research_journal_suggest"
        self.description = "选刊推荐（控制面 heuristic-v1 确定性打分，可解释）：按摘要/关键词推荐 3-6 本目标刊物，每条含得分、理由（指标类理由带数据来源与年份）与该稿型的结构化投稿要求。回答「投哪本刊」、投稿选刊时使用；返回的 journal_id 用于 research_submission_check / 投稿台账。"
        self.args_schema = ResearchJournalSuggestInput

    @safe_tool_operation("research_journal_suggest", fallback_value="Error: 选刊推荐失败")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run(**kwargs))

    async def _async_run(
        self,
        abstract: str = "",
        keywords: list | None = None,
        paper_id: str = "",
        discipline: str = "",
        article_type: str = "original",
        top_n: int = 5,
    ) -> str:
        body: dict[str, Any] = {"article_type": article_type, "top_n": top_n}
        if abstract:
            body["abstract"] = abstract
        if keywords:
            body["keywords"] = keywords
        if paper_id:
            body["paper_id"] = paper_id
        if discipline:
            body["discipline"] = discipline
        result = await _call_research("POST", "/api/v1/journals/suggest", json_data=body)
        if e := _err(result):
            return e
        items = result.get("items") or []
        if not items:
            return "## 选刊推荐\n\n无匹配刊物（控制面期刊库无相关档案或输入信息不足；可先在 /research/journals 导入，或提供更具体的摘要/关键词）。"
        lines = [f"## 选刊推荐（{result.get('method', '?')}，{len(items)} 本，得分降序）\n"]
        for i, it in enumerate(items[:_MAX_RENDER], 1):
            j = it.get("journal") or {}
            lines.append(f"{i}. **{j.get('name', '?')}** — score {it.get('score', 0)}（journal_id：{j.get('id', '')}）")
            for r in (it.get("reasons") or [])[:6]:
                lines.append(f"   - {str(r)[:_EXCERPT]}")
            reqs = it.get("requirements") or []
            if reqs:
                req = reqs[0]
                parts = []
                if req.get("word_limit"):
                    parts.append(f"词数 ≤{req['word_limit']}")
                if req.get("abstract_limit"):
                    parts.append(f"摘要 ≤{req['abstract_limit']}")
                if req.get("figure_limit"):
                    parts.append(f"图 ≤{req['figure_limit']}")
                if req.get("reference_style"):
                    parts.append(f"引文 {req['reference_style']}")
                if parts:
                    tag = "已核证" if req.get("verified_at") else "草稿待核证"
                    lines.append(f"   - 要求（{req.get('article_type', '?')}，{tag}）：" + "；".join(parts))
        return "\n".join(lines)


class ResearchSubmissionCheckInput(BaseModel):
    submission_id: str = Field("", description="已有投稿台账 id（直接对该投稿自检）")
    journal_id: str = Field("", description="目标刊物 id（无 submission_id 时用于建台账行，research_journal_suggest 返回）")
    paper_id: str = Field("", description="库内稿件文献 id（建行路径，与 manuscript_kb_doc_id 二选一）")
    manuscript_kb_doc_id: str = Field("", description="稿件 kb 文档 id（库外稿件建行路径）")
    title: str = Field("", description="稿件标题（manuscript 路径必填；paper 路径自动取文献标题）")
    text: str = Field("", description="可选：待检正文直接给出（缺省依次取 manuscript 包内容/文献摘要）")
    article_type: str = Field("original", description="稿件类型：original|review|letter|case_report")


class ResearchSubmissionCheckTool(CustomBaseTool):
    def __init__(self):
        super().__init__()
        self.name = "research_submission_check"
        self.description = "投稿格式自检：按目标刊物结构化投稿要求逐项检查（词数/摘要/图表数/参考文献风格），返回逐项 通过/未达标/跳过 与结论；无可检项时明确说明，不臆造通过。投稿打包前、核查稿件是否达标时使用；结果同时落控制面投稿台账 checklist 包。"
        self.args_schema = ResearchSubmissionCheckInput

    @safe_tool_operation("research_submission_check", fallback_value="Error: 格式自检失败")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run(**kwargs))

    async def _async_run(
        self,
        submission_id: str = "",
        journal_id: str = "",
        paper_id: str = "",
        manuscript_kb_doc_id: str = "",
        title: str = "",
        text: str = "",
        article_type: str = "original",
    ) -> str:
        # 1) 定位/创建台账行（无 submission_id 时按 journal+稿件建行，status=preparing）
        if not submission_id:
            if not journal_id or not (paper_id or manuscript_kb_doc_id):
                return "Error: 需要 submission_id，或 journal_id + paper_id/manuscript_kb_doc_id（manuscript 路径另需 title）"
            body: dict[str, Any] = {"journal_id": journal_id}
            if paper_id:
                body["paper_id"] = paper_id
            else:
                body["manuscript_kb_doc_id"] = manuscript_kb_doc_id
                if not title:
                    return "Error: manuscript 路径建台账行需要 title"
            if title:
                body["title"] = title
            created = await _call_research("POST", "/api/v1/submissions", json_data=body)
            if e := _err(created):
                return e
            submission_id = str(created.get("id", ""))
        # 2) 逐项自检（正文来源：payload > manuscript 包 > 文献摘要）
        check_body: dict[str, Any] = {"article_type": article_type}
        if text and text.strip():
            check_body["text"] = text
        result = await _call_research("POST", f"/api/v1/submissions/{submission_id}/format-check", json_data=check_body)
        if e := _err(result):
            return e
        fc = result.get("format_check_json") or {}
        items = fc.get("items") or []
        passed = fc.get("passed")
        verdict = "✅ 全部通过" if passed is True else ("❌ 存在未达标项" if passed is False else "⚠️ 无可检项（刊物未配置该稿型要求，不臆造结论）")
        lines = [
            f"## 格式自检（submission：{submission_id}）",
            f"- 结论：{verdict}（{fc.get('passed_count', 0)}/{fc.get('checked_count', 0)} 项通过；正文来源：{fc.get('source', '?')}）",
            "",
        ]
        for it in items[:_MAX_RENDER]:
            mark = "✅" if it.get("passed") is True else ("❌" if it.get("passed") is False else "⏭️")
            lines.append(f"- {mark} {it.get('item')}：{str(it.get('note', ''))[:_EXCERPT]}")
        req = fc.get("requirement")
        if req:
            lines.append(f"\n依据：刊物 {req.get('article_type', '?')} 要求 — 词数 {req.get('word_limit') or '未配置'} / 摘要 {req.get('abstract_limit') or '未配置'} / 图 {req.get('figure_limit') or '未配置'} / 引文风格 {req.get('reference_style') or '未配置'}")
        return "\n".join(lines)


# ============================================================================
# Registry
# ============================================================================

RESEARCH_TOOLS: list[CustomBaseTool] = [
    ResearchJournalLookupTool,
    ResearchJournalRubricTool,
    ResearchPaperSearchTool,
    ResearchPaperGetTool,
    ResearchPaperImportTool,
    ResearchReviewRunCreateTool,
    ResearchReviewSubmitTool,
    ResearchJournalSuggestTool,
    ResearchSubmissionCheckTool,
]
RESEARCH_TOOL_NAMES: set[str] = {t().name for t in RESEARCH_TOOLS}  # module-level convenience (tests)
