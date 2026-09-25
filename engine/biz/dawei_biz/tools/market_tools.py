# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Market Flow（市场智能）业务工具 — 市场营销模块数据工具（MarketingAgent 编队用）。

同名异物消歧（§18.8 外呼扫描）：本组是「市场情报」——外部 market-flow 服务的
营销数据 API（BUSINESS_MARKET_API_URL）；与核心 dawei/market/（「资源市场」，
MARKET_API_URL → nn-user-system agent_market，装 skill/agent/mcp 用）无任何关系。

设计文档：project/MarkkeAgent-prd.md
认证：复用 AuthenticatedServiceClient，每请求从 local_context 注入当前用户 JWT
（多租户隔离，JWT 不进入 LLM 上下文）——与 normflow/sanctions 组同款机制。
可见性（mode-工具解耦后，原 RESTRICTED_GROUPS 组准入已删除）：无组级白名单——
本组工具经 market-team 编队安装进工作区后，任何模式均可经 search_tools 发现并调用。

Phase 0 范围（PRD §13）：read 工具全集；写工具（草稿/幂等类）与工件卡按钮通道在 Phase 1+。
工具纪律（PRD §5.1）：结果瘦身——摘要 + 实体 id + 分页（列表渲染 ≤20 条），
长文本截断并引导用 market_get_signal 看全文。
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from dawei.core.decorators import safe_tool_operation
from dawei.tools.custom_base_tool import CustomBaseTool
from dawei_biz.tools._service_client import (
    ServiceAuthError,
    ServiceUnavailableError,
    market_client,
)
from dawei.tools.custom_tools.async_utils import run_async

logger = logging.getLogger(__name__)

# inner-layer governance: 列表渲染上限（对齐 normflow/sanctions 组）
_MAX_RENDER = 20
# 摘要截断长度（正文/答案摘录等长文本）
_EXCERPT = 160


async def _call_market(method: str, path: str, *, json_data: dict = None, params: dict = None, timeout: float = 20.0) -> dict:
    """Call market-flow API with the current user's JWT injected.

    Returns parsed JSON body, or {"error": ...} / {"_error": ...} on failure
    (mirrors normflow_tools._call_normflow contract).
    """
    try:
        if method.upper() == "GET":
            return await market_client.get(path, params=params, timeout=timeout)
        return await market_client.post(path, json_body=json_data, params=params, timeout=timeout)
    except ServiceAuthError as e:
        return {"error": "AUTH", "detail": str(e)}
    except ServiceUnavailableError as e:
        return {"error": "UNAVAILABLE", "detail": str(e)}
    except Exception as e:
        return {"error": f"market call failed: {e}"}


def _err(result: dict) -> str | None:
    """Extract error message from a _call_market result, if any."""
    if isinstance(result, dict) and result.get("error"):
        detail = result.get("detail") or ""
        return f"Error: {result['error']}" + (f" — {str(detail)[:300]}" if detail else "")
    if isinstance(result, dict) and result.get("_error"):
        detail = result.get("detail") or ""
        return f"Error: {result['_error']}" + (f" — {str(detail)[:300]}" if detail else "")
    return None


def _items_of(result: Any, *keys: str) -> list:
    """Robustly extract a list payload from an unknown-shape response."""
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        for k in keys or ("items", "results", "data", "signals", "events", "briefs", "insights", "competitors", "actions", "opportunities", "products", "checks"):
            v = result.get(k)
            if isinstance(v, list):
                return v
    return []


def _signal_title(s: dict) -> str:
    """信号标题：raw.title 优先，回退 body 截断（PRD §5.1 结果瘦身）。"""
    raw = s.get("raw") if isinstance(s.get("raw"), dict) else {}
    title = (raw.get("title") or "").strip()
    if title:
        return str(title)[:_EXCERPT]
    body = (raw.get("body") or "").strip()
    if body:
        return str(body)[:_EXCERPT] + ("…" if len(body) > _EXCERPT else "")
    return str(s.get("id", "?"))[:12]


def _conf(v: Any) -> str:
    """置信度格式化（None → '—'）。"""
    return f"{v:.2f}" if isinstance(v, (int, float)) else "—"


# ============================================================================
# Orchestrator 层：看板 / 产品
# ============================================================================


class MarketDashboardInput(BaseModel):
    days: int = Field(7, ge=1, le=90, description="统计窗口天数（默认 7）")
    brand_id: str = Field("", description="品牌 id 过滤（空 = 全部品牌）")


class MarketDashboardTool(CustomBaseTool):
    def __init__(self):
        super().__init__()
        self.name = "market_dashboard"
        self.description = "市场智能看板聚合（KPI / 行动漏斗 / 竞品矩阵 / 数据源健康）。回答「市场整体情况怎样」「有多少待处理信号/新事件」「行动漏斗如何」等问题时必用此工具，也是每次会话开局拉当前市场状态的首选。"
        self.args_schema = MarketDashboardInput

    @safe_tool_operation("market_dashboard", fallback_value="Error: 看板获取失败")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run(**kwargs))

    async def _async_run(self, days: int = 7, brand_id: str = "") -> str:
        params: dict[str, Any] = {"days": days}
        if brand_id:
            params["brand_id"] = brand_id
        result = await _call_market("GET", "/api/v1/dashboard", params=params)
        if e := _err(result):
            return e
        lines = [f"## 市场看板（近 {days} 天）\n"]
        kpi = result.get("kpi") or {}
        if kpi:
            lines.append("**KPI：** " + " | ".join(f"{k.replace('_', ' ')}:{v}" for k, v in kpi.items()))
        funnel = result.get("actions") or {}
        if funnel:
            # 真实形状:{counts:{idea/drafted/live…:N}, recent_live:[…]}(dashboard._action_funnel)
            counts = funnel.get("counts") if isinstance(funnel, dict) else funnel
            if isinstance(counts, dict) and counts:
                lines.append("\n**行动漏斗：** " + " | ".join(f"{k}:{v}" for k, v in counts.items()))
            for a in (funnel.get("recent_live") or [])[:3]:
                if isinstance(a, dict):
                    lines.append(f"- 🔗 live：{str(a.get('title', ''))[:_EXCERPT]}（{a.get('action_type', '?')}）")
        sh = result.get("sources_health") or {}
        if sh:
            lines.append(f"\n**数据源健康：** 总数 {sh.get('total', '?')} / 启用 {sh.get('enabled', '?')} / 异常 {sh.get('errored', 0)}" + (f"（最近采集 {sh.get('last_run_at')}）" if sh.get("last_run_at") else ""))
        matrix = result.get("competitor_matrix") or []
        if matrix:
            lines.append(f"\n**竞品×平台矩阵（近 7 天，{len(matrix)} 竞品）**")
            for row in matrix[:_MAX_RENDER]:
                lines.append(f"- {row}")
        push = result.get("social_push_enabled")
        if push is not None:
            lines.append(f"\n**社媒推送通道：** {'已启用' if push else '未启用'}")
        if len(lines) <= 1:
            return "## 市场看板\n\n暂无数据（可能尚未配置数据源或产品）。"
        return "\n".join(lines)


class MarketListProductsInput(BaseModel):
    limit: int = Field(20, ge=1, le=100, description="返回条数上限")


class MarketListProductsTool(CustomBaseTool):
    def __init__(self):
        super().__init__()
        self.name = "market_list_products"
        self.description = "列出市场营销模块管理的产品（含萤火/NormNomos 等在管产品）。回答「我们在追踪哪些产品」及需要 product_id 上下文时使用。"
        self.args_schema = MarketListProductsInput

    @safe_tool_operation("market_list_products", fallback_value="Error: 产品列表获取失败")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run(**kwargs))

    async def _async_run(self, limit: int = 20) -> str:
        result = await _call_market("GET", "/api/v1/products", params={"limit": limit})
        if e := _err(result):
            return e
        items = _items_of(result)
        if not items:
            return "## 产品列表\n\n暂无产品（在 /market/products 页面创建）。"
        lines = [f"## 产品列表（{len(items)} 个）\n"]
        for i, p in enumerate(items[:_MAX_RENDER], 1):
            meta = [f"id:{str(p.get('id', '?'))[:8]}"]
            if p.get("brand_id"):
                meta.append(f"brand:{str(p['brand_id'])[:8]}")
            if p.get("url"):
                meta.append(str(p["url"]))
            lines.append(f"{i}. **{p.get('name', '?')}** — {' | '.join(meta)}")
        return "\n".join(lines)


# ============================================================================
# Radar（发现·信号/事件/早鸟）
# ============================================================================


class MarketListSignalsInput(BaseModel):
    source_type: str = Field("", description="来源类型过滤：rss/api/webhook 等")
    platform: str = Field("", description="平台过滤（如 github/hn/reddit/少数派）")
    brand_id: str = Field("", description="品牌 id 过滤")
    product_id: str = Field("", description="产品 id 过滤")
    days: int = Field(0, ge=0, le=365, description="时间窗口天数（0 = 不过滤）")
    limit: int = Field(20, ge=1, le=50, description="返回条数（≤50，防上下文膨胀）")
    offset: int = Field(0, ge=0, description="分页偏移")


class MarketListSignalsTool(CustomBaseTool):
    def __init__(self):
        super().__init__()
        self.name = "market_list_signals"
        self.description = "检索原始市场信号流（RSS/GitHub/HN/Reddit 等采集的未加工信号）。回答「最近有什么新信号」「某竞品/品牌最近被提及什么」时使用；只给摘要，全文用 market_get_signal。"
        self.args_schema = MarketListSignalsInput

    @safe_tool_operation("market_list_signals", fallback_value="Error: 信号检索失败")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run(**kwargs))

    async def _async_run(self, source_type: str = "", platform: str = "", brand_id: str = "", product_id: str = "", *, days: int = 0, limit: int = 20, offset: int = 0) -> str:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        for key, val in (("source_type", source_type), ("platform", platform), ("brand_id", brand_id), ("product_id", product_id)):
            if val:
                params[key] = val
        if days:
            params["days"] = days
        result = await _call_market("GET", "/api/v1/signals", params=params)
        if e := _err(result):
            return e
        items = _items_of(result)
        if not items:
            return f"## 市场信号\n\n窗口内无信号（source_type={source_type or '*'}, platform={platform or '*'}）。"
        lines = [f"## 市场信号（返回 {len(items)} 条）\n"]
        for i, s in enumerate(items[:_MAX_RENDER], 1):
            raw = s.get("raw") if isinstance(s.get("raw"), dict) else {}
            meta = [str(s.get("source_type") or "?")]
            if s.get("platform"):
                meta.append(str(s["platform"]))
            if raw.get("published_at"):
                meta.append(str(raw["published_at"])[:10])
            lines.append(f"{i}. **{_signal_title(s)}**\n   `{' | '.join(meta)}` | id:{str(s.get('id', '?'))[:8]}")
        return "\n".join(lines)


class MarketGetSignalInput(BaseModel):
    signal_id: str = Field(..., description="信号 id（列表返回的完整 id）")


class MarketGetSignalTool(CustomBaseTool):
    def __init__(self):
        super().__init__()
        self.name = "market_get_signal"
        self.description = "查看单条市场信号的完整原文（标题/正文/链接/发布时间）。溯源或深入分析某条信号时使用。"
        self.args_schema = MarketGetSignalInput

    @safe_tool_operation("market_get_signal", fallback_value="Error: 信号详情获取失败")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run(**kwargs))

    async def _async_run(self, signal_id: str) -> str:
        result = await _call_market("GET", f"/api/v1/signals/{signal_id}")
        if e := _err(result):
            return e
        raw = result.get("raw") if isinstance(result.get("raw"), dict) else {}
        lines = ["## 信号详情\n"]
        lines.append(f"- **标题：** {raw.get('title') or '（无）'}")
        body = (raw.get("body") or "").strip()
        if body:
            lines.append(f"- **正文：** {body[:1200]}" + ("…" if len(body) > 1200 else ""))
        if result.get("url"):
            lines.append(f"- **链接：** {result['url']}")
        if raw.get("author"):
            lines.append(f"- **作者：** {raw['author']}")
        if raw.get("published_at"):
            lines.append(f"- **发布时间：** {raw['published_at']}")
        meta = [f"source_type:{result.get('source_type', '?')}"]
        if result.get("platform"):
            meta.append(f"platform:{result['platform']}")
        lines.append(f"- **采集：** {' | '.join(meta)} | captured_at:{result.get('captured_at')}")
        return "\n".join(lines)


class MarketListEventsInput(BaseModel):
    status: str = Field("", description="状态过滤：event（未成报）/brief（已入简报）/trend（已确认趋势）")
    brand_id: str = Field("", description="品牌 id 过滤")
    product_id: str = Field("", description="产品 id 过滤")
    days: int = Field(0, ge=0, le=365, description="时间窗口天数（0 = 不过滤）")
    limit: int = Field(20, ge=1, le=50, description="返回条数")


class MarketListEventsTool(CustomBaseTool):
    def __init__(self):
        super().__init__()
        self.name = "market_list_events"
        self.description = "检索市场事件（LLM 从信号提取的结构化情报：谁/做了什么/何时/影响/置信度）。回答「竞品最近有什么动作」「有什么高置信事件」时使用；is_emerging=true 是待人工确认的趋势早鸟。"
        self.args_schema = MarketListEventsInput

    @safe_tool_operation("market_list_events", fallback_value="Error: 事件检索失败")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run(**kwargs))

    async def _async_run(self, status: str = "", brand_id: str = "", product_id: str = "", days: int = 0, limit: int = 20) -> str:
        params: dict[str, Any] = {"limit": limit}
        if status:
            params["status"] = status
        if brand_id:
            params["brand_id"] = brand_id
        if product_id:
            params["product_id"] = product_id
        if days:
            params["days"] = days
        result = await _call_market("GET", "/api/v1/events", params=params)
        if e := _err(result):
            return e
        items = _items_of(result)
        if not items:
            return "## 市场事件\n\n窗口内无事件（信号可能未处理，可建议用户触发流水线）。"
        lines = [f"## 市场事件（返回 {len(items)} 条）\n"]
        for i, ev in enumerate(items[:_MAX_RENDER], 1):
            tags = []
            if ev.get("is_emerging"):
                tags.append("早鸟待确认")
            conf = _conf(ev.get("confidence_score"))
            when = str(ev.get("occurred_at") or "")[:10]
            lines.append(f"{i}. **{ev.get('who') or '?'}**：{(ev.get('what') or '（内容缺失）')[:_EXCERPT]}\n   置信 {conf} | {ev.get('status', '?')}{' | ' + when if when else ''}{' | ' + ' '.join(tags) if tags else ''} | id:{str(ev.get('id', '?'))[:8]}")
        return "\n".join(lines)


class MarketGetEventInput(BaseModel):
    event_id: str = Field(..., description="事件 id")


class MarketGetEventTool(CustomBaseTool):
    def __init__(self):
        super().__init__()
        self.name = "market_get_event"
        self.description = "查看单个市场事件完整详情（含溯源 signal_ids，可进一步用 market_get_signal 看原文）。"
        self.args_schema = MarketGetEventInput

    @safe_tool_operation("market_get_event", fallback_value="Error: 事件详情获取失败")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run(**kwargs))

    async def _async_run(self, event_id: str) -> str:
        result = await _call_market("GET", f"/api/v1/events/{event_id}")
        if e := _err(result):
            return e
        lines = ["## 事件详情\n"]
        lines.append(f"- **谁：** {result.get('who') or '—'}")
        lines.append(f"- **什么：** {result.get('what') or '—'}")
        lines.append(f"- **何时：** {result.get('occurred_at') or '—'} | **何地：** {result.get('location') or '—'}")
        lines.append(f"- **影响评估：** {result.get('impact_assessment') or '—'}")
        lines.append(f"- **置信度：** {_conf(result.get('confidence_score'))} | **状态：** {result.get('status', '?')}" + (" | ⚠️ 早鸟待人工确认" if result.get("is_emerging") else ""))
        sids = result.get("signal_ids") or []
        if sids:
            lines.append(f"- **溯源信号（{len(sids)} 条）：** {', '.join(str(s)[:8] for s in sids[:5])}")
        return "\n".join(lines)


# ============================================================================
# 思考层：简报 / 建议 / 竞品 / 趋势
# ============================================================================


class MarketListBriefsInput(BaseModel):
    brand_id: str = Field("", description="品牌 id 过滤")
    product_id: str = Field("", description="产品 id 过滤")
    limit: int = Field(5, ge=1, le=20, description="返回条数（简报较长，默认 5）")


class MarketListBriefsTool(CustomBaseTool):
    def __init__(self):
        super().__init__()
        self.name = "market_list_briefs"
        self.description = "检索市场简报（LLM 聚合事件生成的情报简报，含关键发现与置信度）。回答「最近的市场简报说了什么」「竞品攻势总结」时使用；AI 产物，引用时须带置信度。"
        self.args_schema = MarketListBriefsInput

    @safe_tool_operation("market_list_briefs", fallback_value="Error: 简报检索失败")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run(**kwargs))

    async def _async_run(self, brand_id: str = "", product_id: str = "", limit: int = 5) -> str:
        params: dict[str, Any] = {"limit": limit}
        if brand_id:
            params["brand_id"] = brand_id
        if product_id:
            params["product_id"] = product_id
        result = await _call_market("GET", "/api/v1/briefs", params=params)
        if e := _err(result):
            return e
        items = _items_of(result)
        if not items:
            return "## 市场简报\n\n暂无简报（事件需 ≥3 条且流水线处理后才生成，6 小时一轮）。"
        lines = [f"## 市场简报（{len(items)} 份）\n"]
        for i, b in enumerate(items[:5], 1):
            findings = b.get("key_findings") or []
            lines.append(f"{i}. **{b.get('title', '（无题）')}**\n   置信 {_conf(b.get('confidence_score'))} | {len(findings)} 条发现 | {str(b.get('created_at', ''))[:10]} | id:{str(b.get('id', '?'))[:8]}")
            for f in findings[:3]:
                if isinstance(f, dict):
                    txt = f.get("finding") or f.get("text") or ""
                    if txt:
                        lines.append(f"   - {str(txt)[:_EXCERPT]}")
        return "\n".join(lines)


class MarketListInsightsInput(BaseModel):
    status: str = Field("", description="状态过滤：proposed 待处理/adopted 已采纳/discarded 已驳回")
    brief_id: str = Field("", description="按简报 id 过滤")
    brand_id: str = Field("", description="品牌 id 过滤")
    product_id: str = Field("", description="产品 id 过滤")


class MarketListInsightsTool(CustomBaseTool):
    def __init__(self):
        super().__init__()
        self.name = "market_list_insights"
        self.description = "检索行动建议（insight：简报推导的可执行建议，含 action_type/keywords/建议平台）。回答「有什么建议可采纳」「pricing/content 类建议有哪些」时使用；采纳/驳回由用户决策。"
        self.args_schema = MarketListInsightsInput

    @safe_tool_operation("market_list_insights", fallback_value="Error: 建议检索失败")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run(**kwargs))

    async def _async_run(self, status: str = "", brief_id: str = "", brand_id: str = "", product_id: str = "") -> str:
        params: dict[str, Any] = {}
        if status:
            params["status"] = status
        if brief_id:
            params["brief_id"] = brief_id
        if brand_id:
            params["brand_id"] = brand_id
        if product_id:
            params["product_id"] = product_id
        result = await _call_market("GET", "/api/v1/insights", params=params)
        if e := _err(result):
            return e
        items = _items_of(result)
        if not items:
            return "## 行动建议\n\n暂无建议（简报生成后自动推导）。"
        lines = [f"## 行动建议（{len(items)} 条）\n"]
        for i, ins in enumerate(items[:_MAX_RENDER], 1):
            kws = ins.get("keywords") or []
            plats = ins.get("suggested_platforms") or []
            extra = []
            if kws:
                extra.append("keywords:" + ",".join(str(k) for k in kws[:4]))
            if plats:
                extra.append("platforms:" + ",".join(str(p) for p in plats[:3]))
            lines.append(f"{i}. **[{ins.get('action_type') or 'general'}] {str(ins.get('action_description', ''))[:_EXCERPT]}\n   置信 {_conf(ins.get('confidence_score'))} | {ins.get('status', '?')}" + (f" | {' | '.join(extra)}" if extra else "") + f" | id:{str(ins.get('id', '?'))[:8]}")
        return "\n".join(lines)


class MarketListCompetitorsInput(BaseModel):
    group: str = Field("", description="分组过滤")


class MarketListCompetitorsTool(CustomBaseTool):
    def __init__(self):
        super().__init__()
        self.name = "market_list_competitors"
        self.description = "列出在管竞品（名称/品类/价格带/监控矩阵）。回答「我们在追踪哪些竞品」及需要 competitor_id 时使用。"
        self.args_schema = MarketListCompetitorsInput

    @safe_tool_operation("market_list_competitors", fallback_value="Error: 竞品列表获取失败")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run(**kwargs))

    async def _async_run(self, group: str = "") -> str:
        params: dict[str, Any] = {}
        if group:
            params["group"] = group
        result = await _call_market("GET", "/api/v1/competitors", params=params)
        if e := _err(result):
            return e
        items = _items_of(result)
        if not items:
            return "## 竞品列表\n\n暂无竞品（在 /market/competitors 页面添加）。"
        lines = [f"## 竞品列表（{len(items)} 个）\n"]
        for i, c in enumerate(items[:_MAX_RENDER], 1):
            meta = []
            for k, label in (("category", "品类"), ("target_segment", "客群"), ("price_range", "价格带")):
                if c.get(k):
                    meta.append(f"{label}:{c[k]}")
            mc = c.get("monitoring_config") or {}
            platforms = mc.get("platforms") if isinstance(mc, dict) else None
            if isinstance(platforms, dict) and platforms:
                # 监控矩阵形状:{platform: [内容类型]}(competitors 页矩阵 chips)
                meta.append("监控:" + ",".join(str(p) for p in list(platforms)[:4]))
            elif isinstance(platforms, list) and platforms:
                meta.append("监控:" + ",".join(str(p) for p in platforms[:4]))
            lines.append(f"{i}. **{c.get('name', '?')}** — id:{str(c.get('id', '?'))[:8]}" + (f"\n   {' | '.join(meta)}" if meta else ""))
        return "\n".join(lines)


class MarketCompetitorProfileInput(BaseModel):
    competitor_id: str = Field(..., description="竞品 id")


class MarketCompetitorProfileTool(CustomBaseTool):
    def __init__(self):
        super().__init__()
        self.name = "market_competitor_profile"
        self.description = "获取竞品 AI 画像（定位/主力平台/价格带/内容策略，基于内容库生成，带 model_version）。分析竞品定位或制定对策时使用；未生成过会返回 404，可建议用户先补内容库再生成。"
        self.args_schema = MarketCompetitorProfileInput

    @safe_tool_operation("market_competitor_profile", fallback_value="Error: 竞品画像获取失败")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run(**kwargs))

    async def _async_run(self, competitor_id: str) -> str:
        result = await _call_market("GET", f"/api/v1/competitors/{competitor_id}/profile")
        if e := _err(result):
            return e
        lines = ["## 竞品画像（AI 生成，供参考）\n"]
        lines.append(f"- **定位：** {result.get('positioning') or '—'}")
        lines.append(f"- **主力平台：** {', '.join(str(p) for p in (result.get('main_platforms') or [])) or '—'}")
        lines.append(f"- **价格带：** {result.get('price_band') or '—（未识别）'}")
        lines.append(f"- **内容策略：** {result.get('content_strategy') or '—'}")
        lines.append(f"- **生成时间：** {str(result.get('generated_at', ''))[:19]} | 模型 {result.get('model_version') or '—'}")
        return "\n".join(lines)


class MarketCompetitorContentsInput(BaseModel):
    competitor_id: str = Field(..., description="竞品 id")
    limit: int = Field(20, ge=1, le=50, description="返回条数")


class MarketCompetitorContentsTool(CustomBaseTool):
    def __init__(self):
        super().__init__()
        self.name = "market_competitor_contents"
        self.description = "获取竞品内容库时间线（采集物化的竞品内容标题/平台/链接）。分析竞品最近发了什么内容时使用。"
        self.args_schema = MarketCompetitorContentsInput

    @safe_tool_operation("market_competitor_contents", fallback_value="Error: 竞品内容库获取失败")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run(**kwargs))

    async def _async_run(self, competitor_id: str, limit: int = 20) -> str:
        result = await _call_market("GET", f"/api/v1/competitors/{competitor_id}/contents", params={"limit": limit})
        if e := _err(result):
            return e
        items = _items_of(result)
        if not items:
            return "## 竞品内容库\n\n暂无内容（需将数据源绑定到该竞品后采集）。"
        lines = [f"## 竞品内容库（{len(items)} 条，时间线倒序）\n"]
        for i, c in enumerate(items[:_MAX_RENDER], 1):
            when = str(c.get("captured_at", ""))[:10]
            lines.append(f"{i}. **{c.get('title') or '（无题）'}**\n   {c.get('platform', '?')} | {when}" + (f" | {c.get('url')}" if c.get("url") else ""))
        return "\n".join(lines)


class MarketTrendsTool(CustomBaseTool):
    def __init__(self):
        super().__init__()
        self.name = "market_trends"
        self.description = "获取行业关键词热度趋势（时序 + 三态：rising/flat/declining）。回答「什么在涨」「行业趋势如何」时使用。"
        self.args_schema = None  # 无参数工具

    @safe_tool_operation("market_trends", fallback_value="Error: 趋势获取失败")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run())

    async def _async_run(self) -> str:
        result = await _call_market("GET", "/api/v1/industry/trends")
        if e := _err(result):
            return e
        items = _items_of(result)
        if not items:
            return "## 行业趋势\n\n暂无趋势数据（关键词快照每 24h 一轮，需先配置行业/产品词集）。"
        state_icon = {"rising": "📈", "flat": "➡️", "declining": "📉"}
        lines = [f"## 行业趋势（{len(items)} 词）\n"]
        for i, t in enumerate(items[:_MAX_RENDER], 1):
            vals = t.get("values") or []
            recent = "→".join(str(v) for v in vals[-5:])
            lines.append(f"{i}. {state_icon.get(t.get('state'), '•')} **{t.get('keyword', '?')}**（{t.get('state', '?')}，slope {t.get('slope', '?')}）：{recent}")
        return "\n".join(lines)


# ============================================================================
# Visibility（发现·GEO/SEO）
# ============================================================================


class MarketGeoSummaryTool(CustomBaseTool):
    def __init__(self):
        super().__init__()
        self.name = "market_geo_summary"
        self.description = "获取搜索可见度汇总（GEO 引用率 / SEO 首页词数 / 数据诚实标注）。回答「我们在 AI 回答里的引用率怎样」「搜索可见度如何」时必用；GEO 攻坚进展的第一仪表。"
        self.args_schema = None

    @safe_tool_operation("market_geo_summary", fallback_value="Error: 可见度汇总获取失败")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run())

    async def _async_run(self) -> str:
        result = await _call_market("GET", "/api/v1/visibility/summary")
        if e := _err(result):
            return e
        lines = ["## 搜索可见度汇总\n"]
        for key, val in result.items():
            if isinstance(val, (str, int, float, bool)):
                lines.append(f"- **{key}：** {val}")
            elif isinstance(val, dict):
                summary = " | ".join(f"{k}:{v}" for k, v in list(val.items())[:6])
                lines.append(f"- **{key}：** {summary}")
            elif isinstance(val, list):
                lines.append(f"- **{key}：** {len(val)} 项")
        if len(lines) <= 1:
            return "## 搜索可见度汇总\n\n暂无数据（需配置词集并跑 GEO/SERP 检查）。"
        return "\n".join(lines)


class MarketGeoChecksInput(BaseModel):
    keyword_set_id: str = Field("", description="词集 id 过滤（空 = 全部）")
    limit: int = Field(30, ge=1, le=100, description="返回条数")


class MarketGeoChecksTool(CustomBaseTool):
    def __init__(self):
        super().__init__()
        self.name = "market_geo_checks"
        self.description = "获取 GEO 检查明细（各引擎×关键词的引用情况：cited/position/答案摘录）。定位「哪些词没被 AI 引用」时使用。"
        self.args_schema = MarketGeoChecksInput

    @safe_tool_operation("market_geo_checks", fallback_value="Error: GEO 明细获取失败")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run(**kwargs))

    async def _async_run(self, keyword_set_id: str = "", limit: int = 30) -> str:
        params: dict[str, Any] = {"limit": limit}
        if keyword_set_id:
            params["keyword_set_id"] = keyword_set_id
        result = await _call_market("GET", "/api/v1/visibility/geo", params=params)
        if e := _err(result):
            return e
        items = _items_of(result)
        if not items:
            return "## GEO 检查明细\n\n暂无检查记录（GEO 每 12h 一轮，或手动触发）。"
        cited_n = sum(1 for c in items if c.get("cited"))
        lines = [f"## GEO 检查明细（{len(items)} 条，被引 {cited_n}）\n"]
        for i, c in enumerate(items[:_MAX_RENDER], 1):
            flag = "✅" if c.get("cited") else "❌"
            pos = f"pos {c['position']}" if c.get("position") else "未进引用"
            excerpt = (c.get("answer_excerpt") or "").strip()
            lines.append(f"{i}. {flag} **{c.get('keyword', '?')}**（{c.get('engine', '?')}，{pos}）")
            if excerpt:
                lines.append(f"   > {excerpt[:_EXCERPT]}")
        return "\n".join(lines)


class MarketSeoChecksInput(BaseModel):
    search_engine: str = Field("", description="搜索引擎过滤（baidu/bing/google/duckduckgo 等）")
    limit: int = Field(30, ge=1, le=100, description="返回条数")


class MarketSeoChecksTool(CustomBaseTool):
    def __init__(self):
        super().__init__()
        self.name = "market_seo_checks"
        self.description = "获取 SEO 排名明细（本地 SERP 采集上报的排名：rank 0=未收录，None=失败）。分析搜索排名变化时使用。"
        self.args_schema = MarketSeoChecksInput

    @safe_tool_operation("market_seo_checks", fallback_value="Error: SEO 明细获取失败")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run(**kwargs))

    async def _async_run(self, search_engine: str = "", limit: int = 30) -> str:
        params: dict[str, Any] = {"limit": limit}
        if search_engine:
            params["search_engine"] = search_engine
        result = await _call_market("GET", "/api/v1/visibility/seo", params=params)
        if e := _err(result):
            return e
        items = _items_of(result)
        if not items:
            return "## SEO 排名明细\n\n暂无记录（SERP 采集在桌面端「搜索可见度」页触发）。"
        lines = [f"## SEO 排名明细（{len(items)} 条）\n"]
        for i, c in enumerate(items[:_MAX_RENDER], 1):
            if c.get("rank") is None:
                rank = "采集失败"
            elif c.get("rank") == 0:
                rank = "未收录"
            else:
                rank = f"第 {c['rank']} 位"
            lines.append(f"{i}. **{c.get('keyword', '?')}**（{c.get('search_engine', '?')}）— {rank}" + (f" | {c.get('url')}" if c.get("url") else ""))
        return "\n".join(lines)


class MarketListKeywordSetsInput(BaseModel):
    kind: str = Field("", description="词集类型过滤：brand/product/industry/competitor")


class MarketListKeywordSetsTool(CustomBaseTool):
    def __init__(self):
        super().__init__()
        self.name = "market_list_keyword_sets"
        self.description = "列出可见度监控词集（品牌词/产品词/行业词/竞品词及各词覆盖的引擎）。需要 keyword_set_id 或评估监控覆盖面时使用。"
        self.args_schema = MarketListKeywordSetsInput

    @safe_tool_operation("market_list_keyword_sets", fallback_value="Error: 词集获取失败")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run(**kwargs))

    async def _async_run(self, kind: str = "") -> str:
        params: dict[str, Any] = {}
        if kind:
            params["kind"] = kind
        result = await _call_market("GET", "/api/v1/visibility/keywords", params=params)
        if e := _err(result):
            return e
        items = _items_of(result)
        if not items:
            return "## 词集\n\n暂无词集（在 /market/visibility 页配置，上限 50/租户）。"
        lines = [f"## 可见度词集（{len(items)} 组）\n"]
        for i, ks in enumerate(items[:_MAX_RENDER], 1):
            kws = ks.get("keywords") or []
            engines = ks.get("engines") or []
            lines.append(f"{i}. **[{ks.get('kind', '?')}]** {len(kws)} 词 — " + ", ".join(str(k) for k in kws[:6]) + (" …" if len(kws) > 6 else ""))
            lines.append(f"   引擎：{', '.join(str(e) for e in engines)} | id:{str(ks.get('id', '?'))[:8]}")
        return "\n".join(lines)


# ============================================================================
# 行动层：行动 / 商机 / 校准
# ============================================================================


class MarketListActionsInput(BaseModel):
    product_id: str = Field("", description="产品 id 过滤")
    action_type: str = Field("", description="行动类型：backlink/launch/metadata/content")
    status: str = Field("", description="状态过滤：idea/drafted/submitted/live/verified/dropped")


class MarketListActionsTool(CustomBaseTool):
    def __init__(self):
        super().__init__()
        self.name = "market_list_actions"
        self.description = (
            "检索渠道行动（GTM 外推动作，状态机 idea→drafted→submitted→live→verified）。"
            "回答「行动漏斗/进行中的外推」「哪些 idea 还没动」「某个行动有没有效果」时使用;"
            "带 attribution 归因笔记(证据摘要)——引用时只陈述证据,不下因果结论;"
            "状态流转由用户确认执行。"
        )
        self.args_schema = MarketListActionsInput

    @safe_tool_operation("market_list_actions", fallback_value="Error: 行动检索失败")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run(**kwargs))

    async def _async_run(self, product_id: str = "", action_type: str = "", status: str = "") -> str:
        params: dict[str, Any] = {}
        if product_id:
            params["product_id"] = product_id
        if action_type:
            params["action_type"] = action_type
        if status:
            params["status"] = status
        result = await _call_market("GET", "/api/v1/actions", params=params)
        if e := _err(result):
            return e
        items = _items_of(result)
        if not items:
            return "## 渠道行动\n\n暂无行动（可从已采纳建议生成草稿）。"
        lines = [f"## 渠道行动（{len(items)} 条）\n"]
        for i, a in enumerate(items[:_MAX_RENDER], 1):
            extra = []
            if a.get("target"):
                extra.append(f"target:{a['target']}")
            if a.get("result_url"):
                extra.append("已有结果链接")
            refs = a.get("social_content_ids") or []
            if refs:
                confirmed = sum(1 for r in refs if r.get("matched_by") != "inferred")
                extra.append(f"关联内容 {len(refs)}(确认 {confirmed})")
            attr = a.get("attribution") or {}
            if attr.get("verdict"):
                obs = attr.get("observations") or []
                conf = attr.get("confidence")
                conf_s = f"/{_conf(conf)}" if isinstance(conf, (int, float)) else ""
                extra.append(f"归因:{attr['verdict']}{conf_s}(观察 {len(obs)}"
                             + (f",并发 {len(attr.get('concurrent') or [])}" if attr.get("concurrent") else "")
                             + ")")
            lines.append(f"{i}. **[{a.get('status', '?')}/{a.get('action_type', '?')}] {str(a.get('title', ''))[:_EXCERPT]}" + (f"\n   {' | '.join(extra)}" if extra else "") + f" | id:{str(a.get('id', '?'))[:8]}")
            # 归因笔记要点(有观察时展开一行,证据可引)
            for o in (attr.get("observations") or [])[:3]:
                chg = {"cited": "发布后被引用", "uncited": "发布后失去引用", "indexed": "新收录", "improved": "排名改善"}.get(o.get("change"), o.get("change"))
                pos = f" pos {o['position']}" if o.get("position") else ""
                lines.append(f"   - [{o.get('kind', '?')}] {o.get('keyword', '?')}@{o.get('engine', '?')}:{chg}{pos}(基线 {o.get('baseline_checks', '?')} 次)")
            if attr.get("notes"):
                lines.append(f"   - 备注:{str(attr['notes'])[:_EXCERPT]}")
        return "\n".join(lines)


class MarketListOpportunitiesInput(BaseModel):
    stage: str = Field("", description="阶段过滤：lead/qualified/quoted/sampled/won/lost/not_worth_pursuing")


class MarketListOpportunitiesTool(CustomBaseTool):
    def __init__(self):
        super().__init__()
        self.name = "market_list_opportunities"
        self.description = "检索商机（需求信号评估出的销售机会，阶段 lead→qualified→quoted→sampled→won/lost）。回答「有哪些待跟进商机」时使用。"
        self.args_schema = MarketListOpportunitiesInput

    @safe_tool_operation("market_list_opportunities", fallback_value="Error: 商机检索失败")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run(**kwargs))

    async def _async_run(self, stage: str = "") -> str:
        params: dict[str, Any] = {}
        if stage:
            params["stage"] = stage
        result = await _call_market("GET", "/api/v1/opportunities", params=params)
        if e := _err(result):
            return e
        items = _items_of(result)
        if not items:
            return "## 商机\n\n暂无商机（需求信号经评估后生成）。"
        lines = [f"## 商机（{len(items)} 条）\n"]
        for i, o in enumerate(items[:_MAX_RENDER], 1):
            demand = o.get("demand") or {}
            buyer = demand.get("buyer") or demand.get("buyer_name") or "?"
            intent = demand.get("intent_score")
            lines.append(f"{i}. **[{o.get('stage', '?')}] {buyer}** — {str(demand.get('what') or demand.get('need') or '')[:_EXCERPT]}\n   意向 {intent if intent is not None else '—'} | lead:{str(o.get('lead_id', '?'))[:8]} | id:{str(o.get('id', '?'))[:8]}")
        return "\n".join(lines)


class MarketCalibrationTool(CustomBaseTool):
    def __init__(self):
        super().__init__()
        self.name = "market_calibration"
        self.description = "获取建议置信度校准数据（各置信桶的真实采纳率，样本 <5 不下结论）。给建议前查此数据校准措辞——引用真实比率，禁止无数据推断用户偏好。"
        self.args_schema = None

    @safe_tool_operation("market_calibration", fallback_value="Error: 校准数据获取失败")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run())

    async def _async_run(self) -> str:
        result = await _call_market("GET", "/api/v1/quality/calibration")
        if e := _err(result):
            return e
        lines = ["## 建议置信度校准\n"]
        rendered = False
        for key, val in result.items():
            if isinstance(val, list):
                for bucket in val:
                    if isinstance(bucket, dict):
                        lines.append(f"- 桶 {bucket.get('bucket', '?')}：实际采纳率 {bucket.get('actual_rate', '?')}（样本 {bucket.get('samples', '?')}{'，样本不足不下结论' if (bucket.get('samples') or 0) < 5 else ''}）")
                rendered = True
            elif isinstance(val, (str, int, float, bool)):
                lines.append(f"- **{key}：** {val}")
                rendered = True
        if not rendered:
            return "## 建议置信度校准\n\n暂无数据（需要 insight 采纳/驳回历史）。"
        return "\n".join(lines)


# ============================================================================
# L3 白名单写工具（PRD §8.2:幂等/草稿/配额内;终态与外发不经工具,走工件卡按钮）
# ============================================================================


class MarketRunPipelineInput(BaseModel):
    limit: int = Field(20, ge=1, le=100, description="本批处理信号上限")


class MarketRunPipelineTool(CustomBaseTool):
    def __init__(self):
        super().__init__()
        self.name = "market_run_pipeline"
        self.description = "（写操作，幂等）触发信号→事件处理流水线（LLM 提取结构化事件）。用户要求「处理信号/跑一下流水线」或事件数据滞后时使用；常规由 worker 每 30s-6h 自动跑。"
        self.args_schema = MarketRunPipelineInput

    @safe_tool_operation("market_run_pipeline", fallback_value="Error: 流水线触发失败")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run(**kwargs))

    async def _async_run(self, limit: int = 20) -> str:
        result = await _call_market("POST", "/api/v1/pipeline/process", params={"limit": limit})
        if e := _err(result):
            return e
        lines = ["## 流水线已执行\n"]
        lines.append(f"- 处理 {result.get('processed', '?')} 条信号 → 新事件 {result.get('events_created', '?')} / 合并 {result.get('events_merged', '?')} / 过滤 {result.get('filtered', '?')} / 失败 {result.get('failed', 0)}")
        if result.get("llm_error"):
            lines.append(f"- ⚠️ LLM 错误：{str(result['llm_error'])[:_EXCERPT]}")
        return "\n".join(lines)


class MarketRunSourceInput(BaseModel):
    source_id: str = Field(..., description="数据源 id")


class MarketRunSourceTool(CustomBaseTool):
    def __init__(self):
        super().__init__()
        self.name = "market_run_source"
        self.description = "（写操作，幂等）立即采集指定数据源（RSS/GitHub/HN/Reddit 等）。用户要求「采集一下某源/拉最新数据」时使用。"
        self.args_schema = MarketRunSourceInput

    @safe_tool_operation("market_run_source", fallback_value="Error: 采集触发失败")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run(**kwargs))

    async def _async_run(self, source_id: str) -> str:
        result = await _call_market("POST", f"/api/v1/sources/{source_id}/run")
        if e := _err(result):
            return e
        lines = ["## 数据源采集完成\n"]
        lines.append(f"- 拉取 {result.get('fetched', 0)} 条 → 新增 {result.get('new_signals', 0)} / 去重 {result.get('duplicates', 0)}")
        if result.get("error"):
            lines.append(f"- ⚠️ 错误：{str(result['error'])[:_EXCERPT]}")
        return "\n".join(lines)


class MarketRunGeoInput(BaseModel):
    keyword_set_id: str = Field("", description="词集 id（空 = 全部词集;受每引擎每日配额约束,8h 冷却）")


class MarketRunGeoTool(CustomBaseTool):
    def __init__(self):
        super().__init__()
        self.name = "market_run_geo"
        self.description = "（写操作，配额内）触发一轮 GEO 检查（各引擎对词集提问并记录是否引用我方）。用户要求「测一下引用率/跑一轮 GEO」时使用;服务端强制 8h 冷却与每日配额,超限部分如实跳过。"
        self.args_schema = MarketRunGeoInput

    @safe_tool_operation("market_run_geo", fallback_value="Error: GEO 轮触发失败")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run(**kwargs))

    async def _async_run(self, keyword_set_id: str = "") -> str:
        params: dict[str, Any] = {}
        if keyword_set_id:
            params["keyword_set_id"] = keyword_set_id
        result = await _call_market("POST", "/api/v1/visibility/geo/run", params=params, timeout=300.0)
        if e := _err(result):
            return e
        lines = ["## GEO 检查已执行\n"]
        lines.append(f"- 检查 {result.get('checks', 0)} 项，被引 {result.get('cited', 0)}，配额跳过 {result.get('quota_skipped', 0)}（token {result.get('usage_tokens', 0)}）")
        for err in (result.get("errors") or [])[:5]:
            lines.append(f"- ⚠️ {str(err)[:_EXCERPT]}")
        return "\n".join(lines)


class MarketRunSnapshotTool(CustomBaseTool):
    def __init__(self):
        super().__init__()
        self.name = "market_run_snapshot"
        self.description = "（写操作，幂等）触发一轮行业关键词热度快照（趋势斜率的原料）。用户要求「刷新趋势数据」时使用;常规由 worker 每日执行。"
        self.args_schema = None

    @safe_tool_operation("market_run_snapshot", fallback_value="Error: 快照触发失败")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run())

    async def _async_run(self) -> str:
        result = await _call_market("POST", "/api/v1/industry/snapshots/run")
        if e := _err(result):
            return e
        lines = ["## 热度快照已执行\n"]
        rendered = False
        for key, val in result.items() if isinstance(result, dict) else []:
            if isinstance(val, (str, int, float, bool)):
                lines.append(f"- **{key}：** {val}")
                rendered = True
        if not rendered:
            lines.append(f"- {str(result)[:_EXCERPT]}")
        return "\n".join(lines)


class MarketGenerateProfileInput(BaseModel):
    competitor_id: str = Field(..., description="竞品 id（内容库需 ≥3 条,否则服务端 409 如实返回）")


class MarketGenerateProfileTool(CustomBaseTool):
    def __init__(self):
        super().__init__()
        self.name = "market_generate_profile"
        self.description = "（写操作，版本留痕）重新生成竞品 AI 画像（LLM 基于内容库;多版本保留可回溯）。用户确认要更新画像时使用;生成后建议用 market_competitor_profile 查看。"
        self.args_schema = MarketGenerateProfileInput

    @safe_tool_operation("market_generate_profile", fallback_value="Error: 画像生成失败")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run(**kwargs))

    async def _async_run(self, competitor_id: str) -> str:
        result = await _call_market("POST", f"/api/v1/competitors/{competitor_id}/profile", timeout=120.0)
        if e := _err(result):
            return e
        lines = ["## 竞品画像已生成（AI 产物）\n"]
        lines.append(f"- **定位：** {result.get('positioning') or '—'}")
        lines.append(f"- **主力平台：** {', '.join(str(p) for p in (result.get('main_platforms') or [])) or '—'}")
        lines.append(f"- **价格带：** {result.get('price_band') or '—（未识别）'}")
        lines.append(f"- **内容策略：** {result.get('content_strategy') or '—'}")
        lines.append(f"- **模型：** {result.get('model_version') or '—'} | {str(result.get('generated_at', ''))[:19]}")
        return "\n".join(lines)


class MarketGenerateReportInput(BaseModel):
    kind: str = Field("weekly", description="报告类型（当前仅 weekly）")


class MarketGenerateReportTool(CustomBaseTool):
    def __init__(self):
        super().__init__()
        self.name = "market_generate_report"
        self.description = "（写操作，草稿）生成周报（统计+事件+简报+采纳建议+LLM 执行摘要,落为 draft 草稿）。用户要求「出周报/生成报告」时使用;确认/导出/推送由用户在报告页操作。"
        self.args_schema = MarketGenerateReportInput

    @safe_tool_operation("market_generate_report", fallback_value="Error: 报告生成失败")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run(**kwargs))

    async def _async_run(self, kind: str = "weekly") -> str:
        result = await _call_market("POST", "/api/v1/reports/generate", params={"kind": kind}, timeout=300.0)
        if e := _err(result):
            return e
        if result.get("created"):
            return "## 周报已生成（draft 草稿）\n\n- 已创建本周报告草稿——请到 /market/reports 查看、编辑与确认;确认后可导出或推送社媒。"
        reason = result.get("skipped_reason") or result.get("llm_error") or "未知原因"
        return f"## 周报未生成\n\n- 原因:{str(reason)[:_EXCERPT]}(本期可能已有版本——幂等跳过)"


class MarketDraftActionInput(BaseModel):
    insight_id: str = Field(..., description="建议(insight) id")
    action_type: str = Field("backlink", description="行动类型：backlink 外链 / launch 发布 / metadata 元数据 / content 内容")


class MarketDraftActionTool(CustomBaseTool):
    def __init__(self):
        super().__init__()
        self.name = "market_draft_action"
        self.description = "（写操作，草稿）从已采纳建议生成渠道行动草稿（LLM 按 action_type 产出可粘贴文案,状态 idea,挂 insight+产品溯源）。产出仍是草稿——提交/上线由用户在渠道行动页确认。"
        self.args_schema = MarketDraftActionInput

    @safe_tool_operation("market_draft_action", fallback_value="Error: 行动草稿生成失败")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run(**kwargs))

    async def _async_run(self, insight_id: str, action_type: str = "backlink") -> str:
        result = await _call_market("POST", f"/api/v1/actions/from-insight/{insight_id}", json_data={"action_type": action_type}, timeout=120.0)
        if e := _err(result):
            return e
        lines = ["## 行动草稿已生成（idea 状态,待人工推进）\n"]
        lines.append(f"- **[{result.get('action_type', '?')}] {str(result.get('title', ''))[:_EXCERPT]}")
        lines.append(f"- 目标:{result.get('target') or '—'} | id:{str(result.get('id', '?'))[:8]}")
        payload = (result.get("payload") or "").strip()
        if payload:
            lines.append(f"\n> 草稿文案（可粘贴）:\n> {payload[:600]}")
        lines.append("\n推进到 submitted/live 请在 /market/actions 页面操作（需人工确认）。")
        return "\n".join(lines)


class MarketEvaluateDemandInput(BaseModel):
    source_type: str = Field(..., description="需求信号类型：rfq 询价 / tender 招标 / customs 海关 / exhibition 展会")
    title: str = Field(..., description="标题（≤500 字）")
    body: str = Field("", description="正文/需求描述（≤8000 字）")
    url: str = Field("", description="来源链接")
    platform: str = Field("", description="平台名（≤64 字）")


class MarketEvaluateDemandTool(CustomBaseTool):
    def __init__(self):
        super().__init__()
        self.name = "market_evaluate_demand"
        self.description = "（写操作，评估幂等）录入需求信号并即时 LLM 评估（买家/需求四要素/意向分/是否值得追,生成 lead+opportunity）。用户贴来一条询价/招标信息要求评估时使用。"
        self.args_schema = MarketEvaluateDemandInput

    @safe_tool_operation("market_evaluate_demand", fallback_value="Error: 需求评估失败")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run(**kwargs))

    async def _async_run(self, source_type: str, title: str, body: str = "", url: str = "", platform: str = "") -> str:
        json_body: dict[str, Any] = {"source_type": source_type, "title": title}
        if body:
            json_body["body"] = body
        if url:
            json_body["url"] = url
        if platform:
            json_body["platform"] = platform
        result = await _call_market("POST", "/api/v1/opportunities/demand-signals", json_body=json_body, params={"evaluate": "true"}, timeout=120.0)
        if e := _err(result):
            return e
        lines = ["## 需求信号已评估\n"]
        worth = result.get("worth_pursuing")
        lines.append(f"- **结论:{'✅ 值得跟进' if worth else '❌ 不值得追'}**" + (f"（跳过原因:{str(result['skipped_reason'])[:_EXCERPT]}）" if result.get("skipped_reason") else ""))
        if result.get("llm_error"):
            lines.append(f"- ⚠️ LLM 错误:{str(result['llm_error'])[:_EXCERPT]}")
        if result.get("opportunity_id"):
            lines.append(f"- 商机已建:id {str(result['opportunity_id'])[:8]}（stage=lead）| lead {str(result.get('lead_id') or '?')[:8]}")
        lines.append("- 后续流转（qualified→quoted→…）请在 /market/opportunities 页面操作。")
        return "\n".join(lines)


class MarketInsightFeedbackInput(BaseModel):
    insight_id: str = Field(..., description="建议 id")
    action: str = Field(..., description="adopt 采纳 / discard 驳回")


class MarketInsightFeedbackTool(CustomBaseTool):
    def __init__(self):
        super().__init__()
        self.name = "market_insight_feedback"
        self.description = "（写操作）采纳或驳回一条行动建议（adopt:content 类触发社媒选题推送;discard:进入校准数据）。仅当用户明确表示采纳/驳回某条建议时使用;建议须为 proposed 状态,否则 409 如实返回。"
        self.args_schema = MarketInsightFeedbackInput

    @safe_tool_operation("market_insight_feedback", fallback_value="Error: 建议反馈失败")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run(**kwargs))

    async def _async_run(self, insight_id: str, action: str) -> str:
        act = action.strip().lower()
        if act not in ("adopt", "discard"):
            return "Error: action 仅支持 adopt / discard"
        result = await _call_market("POST", f"/api/v1/insights/{insight_id}/{act}")
        if e := _err(result):
            return e
        if act == "discard":
            return f"## 建议已驳回\n\n- insight {insight_id[:8]} 已标记 discarded（进入校准数据）。"
        lines = ["## 建议已采纳\n"]
        lines.append(f"- 状态:{result.get('status', 'adopted')}")
        if result.get("pushed"):
            lines.append("- 📤 已触发社媒选题推送（幂等键 mkt-insight）。")
        elif result.get("push_error"):
            lines.append(f"- ⚠️ 选题推送失败:{str(result['push_error'])[:_EXCERPT]}（可在看板重试）")
        else:
            lines.append("- 未推送（非 content 类或通道未启用）。")
        return "\n".join(lines)


# ============================================================================
# 注册表
# ============================================================================

MARKET_TOOLS: list[CustomBaseTool] = [
    # Orchestrator
    MarketDashboardTool,
    MarketListProductsTool,
    # Radar（发现）
    MarketListSignalsTool,
    MarketGetSignalTool,
    MarketListEventsTool,
    MarketGetEventTool,
    # 思考
    MarketListBriefsTool,
    MarketListInsightsTool,
    MarketListCompetitorsTool,
    MarketCompetitorProfileTool,
    MarketCompetitorContentsTool,
    MarketTrendsTool,
    # Visibility（发现）
    MarketGeoSummaryTool,
    MarketGeoChecksTool,
    MarketSeoChecksTool,
    MarketListKeywordSetsTool,
    # 行动
    MarketListActionsTool,
    MarketListOpportunitiesTool,
    MarketCalibrationTool,
    # L3 白名单写工具（PRD §8.2）
    MarketRunPipelineTool,
    MarketRunSourceTool,
    MarketRunGeoTool,
    MarketRunSnapshotTool,
    MarketGenerateProfileTool,
    MarketGenerateReportTool,
    MarketDraftActionTool,
    MarketEvaluateDemandTool,
    MarketInsightFeedbackTool,
]

MARKET_TOOL_NAMES: set[str] = {t().name for t in MARKET_TOOLS}  # module-level convenience (tests)
