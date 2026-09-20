# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""NormFlow (nn-flow) business tools — 律所案件/客户/工作流/回款数据工具。

设计文档：project/firmAgent升级.md
认证：复用 AuthenticatedServiceClient，每请求从 local_context 注入当前用户 JWT
（多租户隔离，JWT 不进入 LLM 上下文）。替代旧 normflow MCP server（已删除）。
隔离约束（§3.2d）：本组工具仅通过 "normflow" tool group 暴露给 firm-team。
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from dawei.core.decorators import safe_tool_operation
from dawei.tools.custom_base_tool import CustomBaseTool
from dawei.tools.custom_tools._service_client import (
    ServiceAuthError,
    ServiceUnavailableError,
    normflow_client,
)
from dawei.tools.custom_tools.async_utils import run_async

logger = logging.getLogger(__name__)

# inner-layer governance: 列表渲染上限（对齐 sanctions 组）
_MAX_RENDER = 20

_WRITE_OP_NOTE = "（写操作：需在确认用户意图后调用）"


async def _call_normflow(method: str, path: str, *, json_data: dict = None, params: dict = None, timeout: float = 20.0) -> dict:
    """Call nn-flow API with the current user's JWT injected.

    Returns parsed JSON body, or {"error": ...} on failure (preserves the
    contract used by callers; mirrors knowledge_tool._call_kb_searcher).
    """
    try:
        if method.upper() == "GET":
            return await normflow_client.get(path, params=params, timeout=timeout)
        return await normflow_client.post(path, json_body=json_data, timeout=timeout)
    except ServiceAuthError as e:
        return {"error": "AUTH", "detail": str(e)}
    except ServiceUnavailableError as e:
        return {"error": "UNAVAILABLE", "detail": str(e)}
    except Exception as e:
        return {"error": f"normflow call failed: {e}"}


def _err(result: dict) -> str | None:
    """Extract error message from a _call_normflow result, if any."""
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
        for k in keys or ("items", "results", "data", "cases", "clients", "documents", "tasks"):
            v = result.get(k)
            if isinstance(v, list):
                return v
    return []


def _total_of(result: Any) -> int:
    if isinstance(result, dict):
        for k in ("total", "count", "total_count"):
            v = result.get(k)
            if isinstance(v, int):
                return v
    return -1


# ============================================================================
# Case / Project tools
# ============================================================================


class NormflowSearchCasesInput(BaseModel):
    search: str = Field("", description="按案件名称或编号搜索")
    status: str = Field("", description="状态过滤：pending/active/on_hold/closed/archived（「在处理」= active）")
    project_type: str = Field("", description="项目类型：litigation/non_litigation/retainer/internal")
    case_type: str = Field("", description="案件类型：civil/criminal/commercial 等")
    page: int = Field(1, ge=1, description="页码")
    page_size: int = Field(20, ge=1, le=50, description="每页条数")


class NormflowSearchCasesTool(CustomBaseTool):
    def __init__(self):
        super().__init__()
        self.name = "normflow_search_cases"
        self.description = "检索律所案件/项目列表（NormFlow）。支持按名称/编号搜索及状态、类型过滤。回答「我有几个案件」「哪些案件在处理」等问题时必用此工具（status=active）。"
        self.args_schema = NormflowSearchCasesInput

    @safe_tool_operation("normflow_search_cases", fallback_value="Error: 案件检索失败")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run(**kwargs))

    async def _async_run(self, search: str = "", status: str = "", project_type: str = "", case_type: str = "", page: int = 1, page_size: int = 20) -> str:
        params: dict[str, Any] = {"page": page, "page_size": page_size}
        if search:
            params["search"] = search
        if status:
            params["status"] = status
        if project_type:
            params["project_type"] = project_type
        if case_type:
            params["case_type"] = case_type
        result = await _call_normflow("GET", "/cases", params=params)
        if e := _err(result):
            return e
        items = _items_of(result)
        total = _total_of(result)
        if not items:
            return f"## NormFlow 案件检索\n\n未找到匹配的案件（search={search or '*'}, status={status or '*'}）。"
        lines = [f"## NormFlow 案件列表（共 {total if total >= 0 else len(items)} 条，显示 {min(len(items), _MAX_RENDER)} 条）\n"]
        for i, c in enumerate(items[:_MAX_RENDER], 1):
            name = c.get("name") or c.get("case_name") or c.get("case_number") or c.get("id", "?")
            lines.append(f"{i}. **{name}**")
            meta = []
            for k, label in (("status", "状态"), ("project_type", "类型"), ("case_type", "案由"), ("client_name", "客户"), ("responsible_lawyer", "负责律师")):
                if c.get(k):
                    meta.append(f"{label}:{c[k]}")
            if meta:
                lines.append(f"   {' | '.join(str(m) for m in meta)}")
        return "\n".join(lines)


class NormflowCaseDetailInput(BaseModel):
    case_id: str = Field(..., description="案件 UUID（来自 normflow_search_cases 结果）")


class NormflowCaseDetailTool(CustomBaseTool):
    def __init__(self):
        super().__init__()
        self.name = "normflow_get_case_detail"
        self.description = "获取单个案件的完整详情（当事人、案由、状态、负责人、重要日期等）。"
        self.args_schema = NormflowCaseDetailInput

    @safe_tool_operation("normflow_get_case_detail", fallback_value="Error: 案件详情获取失败")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run(**kwargs))

    async def _async_run(self, case_id: str) -> str:
        result = await _call_normflow("GET", f"/cases/{case_id}")
        if e := _err(result):
            return e
        if not isinstance(result, dict):
            return f"Error: 案件 {case_id} 返回了非预期数据。"
        lines = [f"## 案件详情 `{case_id}`\n"]
        for k, label in (
            ("name", "名称"),
            ("case_number", "编号"),
            ("status", "状态"),
            ("project_type", "项目类型"),
            ("case_type", "案件类型"),
            ("client_name", "客户"),
            ("responsible_lawyer", "负责律师"),
            ("start_date", "开始日期"),
            ("expected_end_date", "预计结案"),
            ("description", "描述"),
            ("amount", "标的额"),
            ("created_at", "创建时间"),
        ):
            v = result.get(k)
            if v:
                lines.append(f"- **{label}:** {v}")
        return "\n".join(lines)


class NormflowCaseTasksInput(BaseModel):
    case_id: str = Field(..., description="案件 UUID")


class NormflowCaseTasksTool(CustomBaseTool):
    def __init__(self):
        super().__init__()
        self.name = "normflow_get_case_tasks"
        self.description = "获取某案件下的全部任务（含期限/截止时间），用于进度跟进、期限提醒。"
        self.args_schema = NormflowCaseTasksInput

    @safe_tool_operation("normflow_get_case_tasks", fallback_value="Error: 案件任务获取失败")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run(**kwargs))

    async def _async_run(self, case_id: str) -> str:
        result = await _call_normflow("GET", f"/cases/{case_id}/tasks")
        if e := _err(result):
            return e
        items = _items_of(result, "tasks", "items")
        if not items:
            return f"案件 `{case_id}` 暂无任务。"
        lines = [f"## 案件任务（{len(items)} 项）\n"]
        for i, t in enumerate(items[:_MAX_RENDER], 1):
            if not isinstance(t, dict):
                continue
            title = t.get("title") or t.get("name") or t.get("id", "?")
            meta = []
            for k, label in (("status", "状态"), ("priority", "优先级"), ("due_date", "截止"), ("assignee", "负责人")):
                if t.get(k):
                    meta.append(f"{label}:{t[k]}")
            lines.append(f"{i}. **{title}**" + (f"（{' | '.join(str(m) for m in meta)}）" if meta else ""))
        return "\n".join(lines)


class NormflowCaseTimesheetInput(BaseModel):
    case_id: str = Field(..., description="案件 UUID")


class NormflowCaseTimesheetTool(CustomBaseTool):
    def __init__(self):
        super().__init__()
        self.name = "normflow_get_case_timesheet"
        self.description = "获取某案件的工时统计摘要（计费/非计费小时数等）。"
        self.args_schema = NormflowCaseTimesheetInput

    @safe_tool_operation("normflow_get_case_timesheet", fallback_value="Error: 工时统计获取失败")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run(**kwargs))

    async def _async_run(self, case_id: str) -> str:
        result = await _call_normflow("GET", f"/cases/{case_id}/timesheet-summary")
        if e := _err(result):
            return e
        if not isinstance(result, dict):
            return "（无工时数据）"
        lines = [f"## 案件工时摘要 `{case_id}`\n"]
        for k, v in result.items():
            if isinstance(v, (str, int, float, bool)):
                lines.append(f"- **{k}:** {v}")
        return "\n".join(lines) if len(lines) > 1 else "（无工时数据）"


class NormflowCaseDocumentsInput(BaseModel):
    case_id: str = Field(..., description="案件 UUID")


class NormflowCaseDocumentsTool(CustomBaseTool):
    def __init__(self):
        super().__init__()
        self.name = "normflow_get_case_documents"
        self.description = "获取某案件的文档列表（合同、文书、证据等）。"
        self.args_schema = NormflowCaseDocumentsInput

    @safe_tool_operation("normflow_get_case_documents", fallback_value="Error: 案件文档获取失败")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run(**kwargs))

    async def _async_run(self, case_id: str) -> str:
        result = await _call_normflow("GET", "/documents", params={"case_id": case_id})
        if e := _err(result):
            return e
        items = _items_of(result, "documents", "items")
        if not items:
            return f"案件 `{case_id}` 暂无文档。"
        lines = [f"## 案件文档（{len(items)} 份）\n"]
        for i, d in enumerate(items[:_MAX_RENDER], 1):
            if not isinstance(d, dict):
                continue
            name = d.get("name") or d.get("title") or d.get("filename") or d.get("id", "?")
            meta = []
            for k, label in (("doc_type", "类型"), ("status", "状态"), ("updated_at", "更新")):
                if d.get(k):
                    meta.append(f"{label}:{d[k]}")
            lines.append(f"{i}. **{name}**" + (f"（{' | '.join(str(m) for m in meta)}）" if meta else ""))
        return "\n".join(lines)


# ============================================================================
# Workflow tools
# ============================================================================


class NormflowAdvanceWorkflowInput(BaseModel):
    instance_id: str = Field(..., description="WorkflowInstance UUID")
    target_node_id: str = Field(..., description="目标节点 ID")


class NormflowAdvanceWorkflowTool(CustomBaseTool):
    def __init__(self):
        super().__init__()
        self.name = "normflow_advance_workflow"
        self.description = "将工作流实例推进到指定节点/步骤。" + _WRITE_OP_NOTE
        self.args_schema = NormflowAdvanceWorkflowInput

    @safe_tool_operation("normflow_advance_workflow", fallback_value="Error: 工作流推进失败")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run(**kwargs))

    async def _async_run(self, instance_id: str, target_node_id: str) -> str:
        result = await _call_normflow("POST", f"/workflows/instances/{instance_id}/advance-to", json_data={"target_node_id": target_node_id})
        if e := _err(result):
            return e
        return f"工作流 `{instance_id}` 已请求推进到节点 `{target_node_id}`。\n\n{result if isinstance(result, dict) else ''}"


class NormflowWorkflowTemplatesInput(BaseModel):
    project_type: str = Field("", description="按项目类型过滤（litigation/non_litigation/retainer/internal）")


class NormflowWorkflowTemplatesTool(CustomBaseTool):
    def __init__(self):
        super().__init__()
        self.name = "normflow_get_workflow_templates"
        self.description = "获取可用的项目/工作流模板清单。"
        self.args_schema = NormflowWorkflowTemplatesInput

    @safe_tool_operation("normflow_get_workflow_templates", fallback_value="Error: 模板获取失败")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run(**kwargs))

    async def _async_run(self, project_type: str = "") -> str:
        params = {"category": project_type} if project_type else None
        result = await _call_normflow("GET", "/workflows/templates", params=params)
        if e := _err(result):
            return e
        items = _items_of(result, "templates", "items")
        if not items:
            return "（无工作流模板）"
        lines = [f"## 工作流模板（{len(items)} 个）\n"]
        for i, t in enumerate(items[:_MAX_RENDER], 1):
            if not isinstance(t, dict):
                continue
            name = t.get("name") or t.get("title") or t.get("id", "?")
            meta = []
            for k, label in (("category", "类别"), ("description", "描述")):
                if t.get(k):
                    meta.append(f"{label}:{t[k]}")
            lines.append(f"{i}. **{name}**" + (f"（{' | '.join(str(m) for m in meta)}）" if meta else ""))
        return "\n".join(lines)


# ============================================================================
# Client tools
# ============================================================================


class NormflowSearchClientsInput(BaseModel):
    search: str = Field("", description="按客户名称搜索")
    category: str = Field("", description="漏斗阶段：potential/interested/signed")
    client_type: str = Field("", description="类型：individual/company")


class NormflowSearchClientsTool(CustomBaseTool):
    def __init__(self):
        super().__init__()
        self.name = "normflow_search_clients"
        self.description = "检索律所客户列表（NormFlow），支持按名称、漏斗阶段、类型过滤。"
        self.args_schema = NormflowSearchClientsInput

    @safe_tool_operation("normflow_search_clients", fallback_value="Error: 客户检索失败")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run(**kwargs))

    async def _async_run(self, search: str = "", category: str = "", client_type: str = "") -> str:
        params: dict[str, Any] = {}
        if search:
            params["search"] = search
        if category:
            params["category"] = category
        if client_type:
            params["client_type"] = client_type
        result = await _call_normflow("GET", "/clients", params=params)
        if e := _err(result):
            return e
        items = _items_of(result)
        if not items:
            return f"未找到匹配的客户（search={search or '*'}）。"
        lines = [f"## NormFlow 客户列表（{len(items)} 位，显示 {min(len(items), _MAX_RENDER)} 位）\n"]
        for i, c in enumerate(items[:_MAX_RENDER], 1):
            if not isinstance(c, dict):
                continue
            name = c.get("name") or c.get("company_name") or c.get("id", "?")
            meta = []
            for k, label in (("category", "阶段"), ("client_type", "类型"), ("phone", "电话"), ("email", "邮箱")):
                if c.get(k):
                    meta.append(f"{label}:{c[k]}")
            lines.append(f"{i}. **{name}**" + (f"（{' | '.join(str(m) for m in meta)}）" if meta else ""))
        return "\n".join(lines)


class NormflowClientDetailInput(BaseModel):
    client_id: str = Field(..., description="客户 UUID")


class NormflowClientDetailTool(CustomBaseTool):
    def __init__(self):
        super().__init__()
        self.name = "normflow_get_client_detail"
        self.description = "获取客户完整详情（联系方式、标签、漏斗阶段等）。"
        self.args_schema = NormflowClientDetailInput

    @safe_tool_operation("normflow_get_client_detail", fallback_value="Error: 客户详情获取失败")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run(**kwargs))

    async def _async_run(self, client_id: str) -> str:
        result = await _call_normflow("GET", f"/clients/{client_id}")
        if e := _err(result):
            return e
        if not isinstance(result, dict):
            return f"Error: 客户 {client_id} 返回了非预期数据。"
        lines = [f"## 客户详情 `{client_id}`\n"]
        for k, label in (
            ("name", "名称"),
            ("company_name", "公司"),
            ("client_type", "类型"),
            ("category", "漏斗阶段"),
            ("phone", "电话"),
            ("email", "邮箱"),
            ("address", "地址"),
            ("description", "备注"),
        ):
            v = result.get(k)
            if v:
                lines.append(f"- **{label}:** {v}")
        tags = result.get("tags") or []
        if tags:
            lines.append(f"- **标签:** {', '.join(str(t) for t in tags[:10])}")
        return "\n".join(lines)


class NormflowClientCasesInput(BaseModel):
    client_id: str = Field(..., description="客户 UUID")


class NormflowClientCasesTool(CustomBaseTool):
    def __init__(self):
        super().__init__()
        self.name = "normflow_get_client_cases"
        self.description = "获取某客户名下的全部关联案件。"
        self.args_schema = NormflowClientCasesInput

    @safe_tool_operation("normflow_get_client_cases", fallback_value="Error: 客户案件获取失败")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run(**kwargs))

    async def _async_run(self, client_id: str) -> str:
        result = await _call_normflow("GET", f"/clients/{client_id}/cases")
        if e := _err(result):
            return e
        items = _items_of(result)
        if not items:
            return f"客户 `{client_id}` 暂无关联案件。"
        lines = [f"## 客户关联案件（{len(items)} 个）\n"]
        for i, c in enumerate(items[:_MAX_RENDER], 1):
            if not isinstance(c, dict):
                continue
            name = c.get("name") or c.get("case_name") or c.get("id", "?")
            status = c.get("status", "")
            lines.append(f"{i}. **{name}**" + (f"（状态:{status}）" if status else ""))
        return "\n".join(lines)


class NormflowCreateFollowUpInput(BaseModel):
    client_id: str = Field(..., description="客户 UUID")
    contact_method: str = Field(..., description="联系方式：phone/email/meeting/wechat/site_visit/other")
    content: str = Field(..., description="沟通内容/要点")
    case_id: str = Field("", description="关联案件 UUID（可选）")
    next_contact_at: str = Field("", description="下次联系时间 ISO datetime（可选）")


class NormflowCreateFollowUpTool(CustomBaseTool):
    def __init__(self):
        super().__init__()
        self.name = "normflow_create_follow_up"
        self.description = "为客户创建一条跟进记录（沟通方式+内容，可选关联案件和下次联系时间）。" + _WRITE_OP_NOTE
        self.args_schema = NormflowCreateFollowUpInput

    @safe_tool_operation("normflow_create_follow_up", fallback_value="Error: 跟进记录创建失败")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run(**kwargs))

    async def _async_run(self, client_id: str, contact_method: str, content: str, case_id: str = "", next_contact_at: str = "") -> str:
        body: dict[str, Any] = {"contact_method": contact_method, "content": content}
        if case_id:
            body["case_id"] = case_id
        if next_contact_at:
            body["next_contact_at"] = next_contact_at
        result = await _call_normflow("POST", f"/clients/{client_id}/follow-ups", json_data=body)
        if e := _err(result):
            return e
        return f"已为客户 `{client_id}` 创建跟进记录（{contact_method}）。"


# ============================================================================
# Finance tool
# ============================================================================


class NormflowPaymentStatusInput(BaseModel):
    pass


class NormflowPaymentStatusTool(CustomBaseTool):
    def __init__(self):
        super().__init__()
        self.name = "normflow_get_payment_status"
        self.description = "获取案件回款仪表盘：每案件的预估额/已开票/已回款/未回款/逾期金额。用于「回款情况」「欠款」「应收」类问题。"
        self.args_schema = NormflowPaymentStatusInput

    @safe_tool_operation("normflow_get_payment_status", fallback_value="Error: 回款数据获取失败")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run(**kwargs))

    async def _async_run(self) -> str:
        result = await _call_normflow("GET", "/cases/payment-dashboard")
        if e := _err(result):
            return e
        items = _items_of(result, "cases", "items", "data")
        if not items:
            return "（暂无回款数据）"
        lines = ["## 案件回款仪表盘\n"]
        lines.append("| 案件 | 预估 | 已开票 | 已回款 | 未回款 | 逾期 |")
        lines.append("|---|---|---|---|---|---|")
        for c in items[:_MAX_RENDER]:
            if not isinstance(c, dict):
                continue
            name = c.get("name") or c.get("case_name") or c.get("case_id", "?")
            row = [str(name)]
            for k in ("estimated_amount", "invoiced_amount", "collected_amount", "outstanding_amount", "overdue_amount"):
                v = c.get(k)
                row.append(str(v) if v is not None else "—")
            lines.append("| " + " | ".join(row) + " |")
        if isinstance(result, dict):
            for k in ("total_estimated", "total_invoiced", "total_collected", "total_outstanding", "total_overdue"):
                if result.get(k) is not None:
                    lines.append(f"\n**合计 {k}:** {result[k]}")
        return "\n".join(lines)


NORMFLOW_TOOLS: list[CustomBaseTool] = [
    NormflowSearchCasesTool,
    NormflowCaseDetailTool,
    NormflowCaseTasksTool,
    NormflowCaseTimesheetTool,
    NormflowCaseDocumentsTool,
    NormflowAdvanceWorkflowTool,
    NormflowWorkflowTemplatesTool,
    NormflowSearchClientsTool,
    NormflowClientDetailTool,
    NormflowClientCasesTool,
    NormflowCreateFollowUpTool,
    NormflowPaymentStatusTool,
]

NORMFLOW_TOOL_NAMES: set[str] = {t().name for t in NORMFLOW_TOOLS}  # module-level convenience (tests)
