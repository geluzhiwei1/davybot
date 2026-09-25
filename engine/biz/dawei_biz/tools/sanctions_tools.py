# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Sanctions-knowledge native tools (multi-tenant, per-user JWT).

Calls the sanctions service HTTP API (`/api/v1/*`) via the authenticated client
— the current user's JWT is injected transparently from local_context. Replaces
the old DB-coupled MCP server. Tool surface per 业务工具升级.md §4.2.
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
    sanctions_client,
)
from dawei.tools.custom_tools.async_utils import run_async

logger = logging.getLogger(__name__)

_MAX_LIST = 20  # cap items returned to the LLM to bound context


def _friendly_error(e: Exception) -> str:
    if isinstance(e, ServiceAuthError):
        return "⚠️ 认证失败：登录已过期或无权限，请重新登录后再试。"
    if isinstance(e, ServiceUnavailableError):
        return f"⚠️ 制裁服务暂不可用：{e}"
    return f"⚠️ 调用制裁服务失败：{type(e).__name__}: {e}"


def _fmt_entity(ent: dict, idx: int) -> str:
    name = ent.get("caption") or ent.get("name") or ent.get("first_name", "")
    schema = ent.get("schema") or ent.get("schema_type") or ent.get("type", "")
    countries = ent.get("countries") or ent.get("country") or []
    if isinstance(countries, str):
        countries = [countries]
    datasets = ent.get("datasets") or []
    eid = ent.get("id") or ent.get("entity_id") or "?"
    line = f"{idx}. **{name}**"
    if schema:
        line += f" ({schema})"
    if countries:
        line += f" [{','.join(countries[:3])}]"
    if datasets:
        line += f" <{','.join(datasets[:3])}>"
    line += f" `id={eid}`"
    return line


# ── 1. search_entities ─────────────────────────────────────────────


class SanctionsSearchInput(BaseModel):
    q: str = Field(..., description="实体名称或关键词")
    schema_type: str | None = Field(None, description="实体类型：Person/Company/Organization/LegalEntity…")
    country: str | None = Field(None, description="国家代码：US/CN/RU/IR…")
    dataset: str | None = Field(None, description="数据集：us_ofac_sdn/eu_sanctions/wikidata…")
    page_size: int = Field(10, ge=1, le=50, description="返回条数（上限 50）")


class SanctionsSearchTool(CustomBaseTool):
    def __init__(self):
        super().__init__()
        self.name = "sanctions_search_entities"
        self.description = (
            "检索受制裁实体（人/公司/组织）。按名称/关键词搜索，可按类型、国家、数据集过滤。"
            "用于尽调、合规筛查前的查询。用 sanctions_filters 查可用数据集/国家。"
        )
        self.args_schema = SanctionsSearchInput

    @safe_tool_operation("sanctions_search", fallback_value="Error: 制裁实体检索失败")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run(**kwargs))

    async def _async_run(self, q: str, schema_type: str | None = None, country: str | None = None,
                         dataset: str | None = None, page_size: int = 10) -> str:
        params: dict[str, Any] = {"q": q, "pageSize": page_size}
        if schema_type:
            params["schemaType"] = schema_type
        if country:
            params["country"] = country
        if dataset:
            params["dataset"] = dataset
        try:
            data = await sanctions_client.get("/api/v1/entities/search", params=params, timeout=20)
        except (ServiceAuthError, ServiceUnavailableError) as e:
            return _friendly_error(e)

        items = data.get("items") or data.get("results") or data.get("entities") or [] if isinstance(data, dict) else []
        total = data.get("total", len(items)) if isinstance(data, dict) else len(items)
        if not items:
            return f"未找到与 '{q}' 相关的受制裁实体。"
        lines = [f"## 制裁实体检索：'{q}'（共 {total}，显示 {min(len(items), _MAX_LIST)}）\n"]
        for i, ent in enumerate(items[:_MAX_LIST], 1):
            lines.append(_fmt_entity(ent, i))
        return "\n".join(lines)


# ── 2. get_entity ──────────────────────────────────────────────────


class SanctionsGetEntityInput(BaseModel):
    entity_id: str = Field(..., description="实体 ID（来自检索结果）")
    include_statements: bool = Field(True, description="是否包含实体制裁声明/属性明细")


class SanctionsGetEntityTool(CustomBaseTool):
    def __init__(self):
        super().__init__()
        self.name = "sanctions_get_entity"
        self.description = "获取受制裁实体详情（含制裁项目、当局、 Identifiers、声明/属性）。"
        self.args_schema = SanctionsGetEntityInput

    @safe_tool_operation("sanctions_get_entity", fallback_value="Error: 获取实体详情失败")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run(**kwargs))

    async def _async_run(self, entity_id: str, include_statements: bool = True) -> str:
        try:
            ent = await sanctions_client.get(f"/api/v1/entities/{entity_id}", timeout=20)
        except (ServiceAuthError, ServiceUnavailableError) as e:
            return _friendly_error(e)
        if not isinstance(ent, dict) or (ent.get("_error")):
            return f"未找到实体 {entity_id}。"

        lines = [f"## 实体详情：{ent.get('caption') or ent.get('name', entity_id)}\n"]
        for k in ("schema", "type", "countries", "datasets", "first_seen", "last_seen", "modified_at"):
            v = ent.get(k)
            if v:
                lines.append(f"- **{k}**: {v}")
        ids = ent.get("identifiers") or []
        if ids:
            lines.append("\n**Identifiers:**")
            for ident in ids[:15]:
                lines.append(f"- {ident}")

        sanctions = ent.get("sanctions") or []
        if sanctions:
            lines.append(f"\n**制裁记录 ({len(sanctions)})：**")
            for s in sanctions[:15]:
                auth = s.get("authority", "")
                prog = s.get("program", "")
                lines.append(f"- [{auth}] {prog}")

        if include_statements:
            try:
                st = await sanctions_client.get(f"/api/v1/entities/{entity_id}/statements", timeout=20)
                stmts = st.get("statements") or st.get("items") or [] if isinstance(st, dict) else []
                if stmts:
                    lines.append(f"\n**声明/属性 ({len(stmts)})：**")
                    for s in stmts[:20]:
                        prop = s.get("prop") or s.get("property") or "?"
                        val = s.get("value") or s.get("text") or ""
                        lines.append(f"- {prop}: {str(val)[:100]}")
            except (ServiceAuthError, ServiceUnavailableError) as e:
                lines.append(f"\n（声明获取失败：{e}）")
        return "\n".join(lines)


# ── 3. graph_search ────────────────────────────────────────────────


class SanctionsGraphInput(BaseModel):
    q: str = Field(..., description="实体名称/关键词")
    entity_type: str | None = Field(None, description="实体类型过滤")
    country: str | None = Field(None, description="国家代码")
    dataset: str | None = Field(None, description="数据集")
    limit: int = Field(10, ge=1, le=30)


class SanctionsGraphTool(CustomBaseTool):
    def __init__(self):
        super().__init__()
        self.name = "sanctions_graph_search"
        self.description = "在制裁知识图谱中检索实体/关联关系（实体邻域、关联实体）。用于关系挖掘、受益人追踪。"
        self.args_schema = SanctionsGraphInput

    @safe_tool_operation("sanctions_graph", fallback_value="Error: 图谱检索失败")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run(**kwargs))

    async def _async_run(self, q: str, entity_type: str | None = None, country: str | None = None,
                         dataset: str | None = None, limit: int = 10) -> str:
        params: dict[str, Any] = {"q": q, "limit": limit}
        if entity_type:
            params["entityType"] = entity_type
        if country:
            params["country"] = country
        if dataset:
            params["dataset"] = dataset
        try:
            data = await sanctions_client.get("/api/v1/graph/search", params=params, timeout=20)
        except (ServiceAuthError, ServiceUnavailableError) as e:
            return _friendly_error(e)
        items = data.get("entities") or data.get("items") or data.get("results") or [] if isinstance(data, dict) else []
        if not items:
            return f"图谱中未找到 '{q}' 的相关实体。"
        lines = [f"## 制裁图谱检索：'{q}'（{len(items)} 条）\n"]
        for i, ent in enumerate(items[:_MAX_LIST], 1):
            lines.append(_fmt_entity(ent, i))
        return "\n".join(lines)


# ── 4. screen_entity ───────────────────────────────────────────────


class SanctionsScreenInput(BaseModel):
    name: str = Field(..., description="待筛查实体名称")
    entity_type: str | None = Field(None, description="实体类型：Person/Company…")
    identifiers: dict | None = Field(None, description="附加标识（如 passport, id_no, dob, address）")
    datasets: list[str] | None = Field(None, description="限定数据集；省略=全数据集")


class SanctionsScreenTool(CustomBaseTool):
    def __init__(self):
        super().__init__()
        self.name = "sanctions_screen_entity"
        self.description = "对单个名称/实体做制裁筛查（匹配受制裁名单），返回命中与风险评级。用于客户/合作方尽调。"
        self.args_schema = SanctionsScreenInput

    @safe_tool_operation("sanctions_screen", fallback_value="Error: 制裁筛查失败")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run(**kwargs))

    async def _async_run(self, name: str, entity_type: str | None = None,
                         identifiers: dict | None = None, datasets: list[str] | None = None) -> str:
        body: dict[str, Any] = {"name": name}
        if entity_type:
            body["entity_type"] = entity_type
        if entity_type:
            body["schema"] = entity_type
        if identifiers:
            body["identifiers"] = identifiers
        if datasets:
            body["datasets"] = datasets
        try:
            data = await sanctions_client.post("/api/v1/screen", json_body=body, timeout=45)
        except (ServiceAuthError, ServiceUnavailableError) as e:
            return _friendly_error(e)
        if isinstance(data, dict) and data.get("_error"):
            return f"⚠️ 筛查请求被拒：{data['_error']} {str(data.get('detail'))[:160]}"
        risk = data.get("risk_level") or data.get("risk") or "未知"
        matches = data.get("matches") or data.get("hits") or data.get("results") or [] if isinstance(data, dict) else []
        lines = [f"## 制裁筛查：{name}\n- 风险评级：**{risk}**\n- 命中数：{len(matches)}"]
        for i, m in enumerate(matches[:_MAX_LIST], 1):
            lines.append(_fmt_entity(m, i))
        if not matches:
            lines.append("\n（无命中）")
        return "\n".join(lines)


# ── 5. create_watchlist ────────────────────────────────────────────


class SanctionsWatchlistInput(BaseModel):
    name: str = Field(..., description="监控名单名称")
    entities: list[dict] = Field(..., description="要加入监控的实体（每项含 name，可选 entity_type/identifiers）")


class SanctionsWatchlistTool(CustomBaseTool):
    def __init__(self):
        super().__init__()
        self.name = "sanctions_create_watchlist"
        self.description = "创建制裁监控名单（定期复查实体是否新增制裁命中）。用于持续尽调/风控。"
        self.args_schema = SanctionsWatchlistInput

    @safe_tool_operation("sanctions_watchlist", fallback_value="Error: 创建监控名单失败")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run(**kwargs))

    async def _async_run(self, name: str, entities: list[dict]) -> str:
        try:
            data = await sanctions_client.post("/api/v1/monitoring/watchlists", json_body={"name": name}, timeout=30)
        except (ServiceAuthError, ServiceUnavailableError) as e:
            return _friendly_error(e)
        if isinstance(data, dict) and data.get("_error"):
            return f"⚠️ 创建失败：{data['_error']} {str(data.get('detail'))[:160]}"
        wid = data.get("id") or data.get("watchlist_id") or "?"
        # add entities
        added = 0
        if wid != "?" and entities:
            try:
                await sanctions_client.post(
                    f"/api/v1/monitoring/watchlists/{wid}/entities",
                    json_body={"entities": entities}, timeout=30,
                )
                added = len(entities)
            except (ServiceAuthError, ServiceUnavailableError):
                pass
        return f"✅ 监控名单已创建：**{name}** (id=`{wid}`)，已加入 {added} 个实体。用 sanctions_run_monitoring_check 触发复查。"


# ── 6. run_monitoring_check ────────────────────────────────────────


class SanctionsMonitoringInput(BaseModel):
    watchlist_id: str = Field(..., description="监控名单 ID")


class SanctionsMonitoringTool(CustomBaseTool):
    def __init__(self):
        super().__init__()
        self.name = "sanctions_run_monitoring_check"
        self.description = "对一个监控名单立即触发制裁复查，返回新增命中/告警。"
        self.args_schema = SanctionsMonitoringInput

    @safe_tool_operation("sanctions_monitoring", fallback_value="Error: 触发监控复查失败")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run(**kwargs))

    async def _async_run(self, watchlist_id: str) -> str:
        try:
            data = await sanctions_client.post(
                "/api/v1/monitoring/check", json_body={"watchlist_id": watchlist_id}, timeout=60,
            )
        except (ServiceAuthError, ServiceUnavailableError) as e:
            return _friendly_error(e)
        if isinstance(data, dict) and data.get("_error"):
            return f"⚠️ 复查失败：{data['_error']} {str(data.get('detail'))[:160]}"
        alerts = data.get("alerts") or data.get("new_matches") or data.get("results") or [] if isinstance(data, dict) else []
        lines = [f"## 监控复查：watchlist `{watchlist_id}`\n- 新增告警/命中：{len(alerts)}"]
        for i, a in enumerate(alerts[:_MAX_LIST], 1):
            lines.append(_fmt_entity(a, i))
        if not alerts:
            lines.append("\n（无新增命中）")
        return "\n".join(lines)


# ── 7. dashboard ───────────────────────────────────────────────────


class SanctionsDashboardInput(BaseModel):
    days: int | None = Field(None, description="统计时间窗（天数），用于趋势")


class SanctionsDashboardTool(CustomBaseTool):
    def __init__(self):
        super().__init__()
        self.name = "sanctions_dashboard"
        self.description = "获取制裁/合规看板统计（实体数、数据集覆盖、命中趋势等）。用于概览与汇报。"
        self.args_schema = SanctionsDashboardInput

    @safe_tool_operation("sanctions_dashboard", fallback_value="Error: 获取看板失败")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run(**kwargs))

    async def _async_run(self, days: int | None = None) -> str:
        params = {"days": days} if days else None
        try:
            stats = await sanctions_client.get("/api/v1/dashboard/stats", params=params, timeout=20)
        except (ServiceAuthError, ServiceUnavailableError) as e:
            return _friendly_error(e)
        lines = ["## 制裁看板统计\n"]
        if isinstance(stats, dict):
            for k, v in stats.items():
                if isinstance(v, (str, int, float, bool)) or v is None:
                    lines.append(f"- **{k}**: {v}")
                elif isinstance(v, list) and v and isinstance(v[0], (str, int)):
                    lines.append(f"- **{k}**: {', '.join(map(str, v[:8]))}")
        return "\n".join(lines) if len(lines) > 1 else "（看板无数据）"


# ── 8. filters ─────────────────────────────────────────────────────


class SanctionsFiltersTool(CustomBaseTool):
    def __init__(self):
        super().__init__()
        self.name = "sanctions_filters"
        self.description = "列出制裁检索可用的过滤项（数据集、国家、实体类型等）。检索前用它了解可用的过滤值。"
        self.args_schema = None

    @safe_tool_operation("sanctions_filters", fallback_value="Error: 获取过滤项失败")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run(**kwargs))

    async def _async_run(self) -> str:
        try:
            data = await sanctions_client.get("/api/v1/filters", timeout=20)
        except (ServiceAuthError, ServiceUnavailableError) as e:
            return _friendly_error(e)
        if not isinstance(data, dict):
            return "（过滤项无数据）"
        lines = ["## 制裁检索可用过滤项\n"]
        for k, v in data.items():
            if isinstance(v, list):
                sample = ", ".join(map(str, v[:20]))
                lines.append(f"- **{k}** ({len(v)}): {sample}")
            elif isinstance(v, dict):
                sub = ", ".join(f"{dk}" for dk in list(v.keys())[:20])
                lines.append(f"- **{k}**: {sub}")
            else:
                lines.append(f"- **{k}**: {v}")
        return "\n".join(lines)


# S2 工具组注册源（dawei_biz/__init__ 经此派生 sanctions 组，防名称漂移）
SANCTIONS_TOOLS: list[CustomBaseTool] = [
    SanctionsSearchTool,
    SanctionsGetEntityTool,
    SanctionsGraphTool,
    SanctionsScreenTool,
    SanctionsWatchlistTool,
    SanctionsMonitoringTool,
    SanctionsDashboardTool,
    SanctionsFiltersTool,
]
SANCTIONS_TOOL_NAMES: set[str] = {t().name for t in SANCTIONS_TOOLS}  # module-level convenience (tests)
