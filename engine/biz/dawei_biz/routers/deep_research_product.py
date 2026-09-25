# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""深度研究 · 产品调研 API 路由。

设计文档: project/docs/PRD-gelu-diaoyan/prd-产品调研.md §6.11

端点:
- GET  /api/deep-research/product/templates                     模板列表
- GET  /api/deep-research/product/templates/{slug}              模板详情
- POST /api/deep-research/product/templates/{slug}/render-dao   dao.md 预览（向导 Step 5）
- POST /api/deep-research/product/workspaces                    创建工作区（direct / wizard）
- GET  /api/deep-research/product/workspaces                    工作区列表
- GET  /api/deep-research/product/workspaces/{id}               详情（含阶段状态 / GATE 预览）
- POST /api/deep-research/product/workspaces/{id}/start         启动/继续流水线
- GET  /api/deep-research/product/workspaces/{id}/files         浏览产物
- GET  /api/deep-research/product/workspaces/{id}/files/download           下载单个文件
- GET  /api/deep-research/product/workspaces/{id}/files/download-all      打包下载
- POST /api/deep-research/product/workspaces/{id}/gates/{gateId}/decide   GATE 决策
- POST /api/deep-research/product/workspaces/{id}/retry        单阶段重试
- POST /api/deep-research/product/workspaces/{id}/duplicate    复制为新任务
- GET  /api/deep-research/product/workspaces/{id}/audit-log    审计日志
- GET  /api/deep-research/product/workspaces/{id}/dao-history  dao.md 历史版本（diff 视图数据源）
- POST /api/deep-research/product/workspaces/{id}/share        生成只读分享链接 token（需 completed）

服务为模块级单例（storage_root 动态读取 DAWEI_HOME，测试 monkeypatch 环境变量即可隔离）。
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from dawei_biz.services.product_survey_service import (
    ProductSurveyError,
    product_survey_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/deep-research/product", tags=["deep-research-product"])


# ============================================================
# Request models
# ============================================================

class RenderDaoRequest(BaseModel):
    """向导 Step 5 / GATE-0 的 dao.md 预览请求。"""

    topic: str
    background: str = ""
    audience: str = ""
    user_input: str = ""
    dimensions: Optional[list[dict[str, Any]]] = None
    success_criteria: Optional[dict[str, Any]] = None


class CreateWorkspaceRequest(BaseModel):
    """创建工作区（direct 直接开始 / wizard 向导 5 步提交）。"""

    template_slug: str
    topic: str
    mode: str = Field(default="direct", pattern="^(direct|wizard)$")
    background: str = ""
    audience: str = ""
    user_input: str = ""
    scope: Optional[dict[str, Any]] = None
    dimensions: Optional[list[dict[str, Any]]] = None
    success_criteria: Optional[dict[str, Any]] = None
    dao_md: Optional[str] = None  # 用户编辑后的 dao.md（GATE-0 前落盘）
    user_id: str = "anonymous"
    tenant_id: str = "default"
    auto_start: bool = False  # 创建后立即启动（GATE-0 未过则 409）
    dry_run: bool = True  # False = 真实 LLM 执行（ProductSurveyExecutor）


class GateDecideRequest(BaseModel):
    """GATE 决策请求。action: approve / reject / edit（edit 仅 GATE-0，需 dao_md）。"""

    action: str = Field(pattern="^(approve|reject|edit)$")
    note: str = ""
    dao_md: str = ""
    actor: str = "user"


def _http(e: ProductSurveyError) -> HTTPException:
    return HTTPException(status_code=e.status_code, detail=str(e))


async def _request_identity(http_request: Request) -> tuple[str, str]:
    """提取请求身份（工作区注册归属）；无鉴权上下文时回退请求体默认值。"""
    try:
        from dawei.api.auth import get_authenticated_tenant_id, get_authenticated_user_id

        return await get_authenticated_user_id(http_request), await get_authenticated_tenant_id(http_request)
    except Exception:  # noqa: BLE001
        return "anonymous", "default"


# ============================================================
# Templates
# ============================================================

@router.get(
    "/templates",
    summary="产品调研模板列表",
)
async def list_templates():
    templates = product_survey_service.list_templates()
    return {"templates": templates, "total": len(templates)}


@router.get(
    "/templates/{slug}",
    summary="产品调研模板详情",
)
async def get_template(slug: str):
    try:
        return product_survey_service.get_template(slug)
    except ProductSurveyError as e:
        raise _http(e) from e


@router.post(
    "/templates/{slug}/render-dao",
    summary="渲染 dao.md 预览（GATE-0 前端）",
)
async def render_dao(slug: str, req: RenderDaoRequest):
    try:
        content = product_survey_service.render_dao_md(
            slug,
            req.topic,
            req.background,
            req.audience,
            req.dimensions,
            req.success_criteria,
            req.user_input,
        )
        return {"dao_md": content, "validation": product_survey_service.validate_dao_md(content)}
    except ProductSurveyError as e:
        raise _http(e) from e


# ============================================================
# Workspaces
# ============================================================

@router.post(
    "/workspaces",
    summary="创建产品调研工作区",
)
async def create_workspace(req: CreateWorkspaceRequest, http_request: Request):
    try:
        user_id, tenant_id = await _request_identity(http_request)
        meta = await product_survey_service.create_workspace(
            template_slug=req.template_slug,
            topic=req.topic,
            mode=req.mode,
            background=req.background,
            audience=req.audience,
            user_input=req.user_input,
            scope=req.scope,
            dimensions=req.dimensions,
            success_criteria=req.success_criteria,
            dao_md=req.dao_md,
            user_id=user_id or req.user_id,
            tenant_id=tenant_id or req.tenant_id,
            dry_run=req.dry_run,
        )
        if req.auto_start:
            meta = product_survey_service.start(meta["workspace_id"], dry_run=req.dry_run)
        return meta
    except ProductSurveyError as e:
        raise _http(e) from e


@router.get(
    "/workspaces",
    summary="产品调研工作区列表",
)
async def list_workspaces():
    workspaces = product_survey_service.list_workspaces()
    return {"workspaces": workspaces, "total": len(workspaces)}


@router.get(
    "/workspaces/{workspace_id}",
    summary="工作区详情（含阶段状态 / GATE 预览）",
)
async def get_workspace(workspace_id: str):
    try:
        return product_survey_service.get_workspace(workspace_id)
    except ProductSurveyError as e:
        raise _http(e) from e


@router.delete(
    "/workspaces/{workspace_id}",
    summary="删除调研工作区（目录 + 注册 + 分享 token，不可恢复）",
)
async def delete_workspace(workspace_id: str, http_request: Request):
    try:
        user_id, _ = await _request_identity(http_request)
        return await product_survey_service.delete_workspace(workspace_id, actor=user_id)
    except ProductSurveyError as e:
        raise _http(e) from e


@router.post(
    "/workspaces/{workspace_id}/start",
    summary="启动/继续流水线（需 GATE-0 已通过；?dry_run=false 真实 LLM 执行）",
)
async def start_workspace(workspace_id: str, dry_run: bool = True):
    try:
        return product_survey_service.start(workspace_id, dry_run=dry_run)
    except ProductSurveyError as e:
        raise _http(e) from e


@router.post(
    "/workspaces/{workspace_id}/gates/{gate_id}/decide",
    summary="GATE 决策（approve / reject / edit）",
)
async def decide_gate(workspace_id: str, gate_id: str, req: GateDecideRequest):
    try:
        return product_survey_service.decide_gate(
            workspace_id,
            gate_id,
            req.action,
            note=req.note,
            dao_md=req.dao_md,
            actor=req.actor,
        )
    except ProductSurveyError as e:
        raise _http(e) from e


@router.post(
    "/workspaces/{workspace_id}/retry",
    summary="从指定 stage 重跑",
)
async def retry_workspace(
    workspace_id: str,
    from_stage: str = Query(..., description="起始 stage id，如 stage-02-product-collect"),
):
    try:
        return product_survey_service.retry(workspace_id, from_stage)
    except ProductSurveyError as e:
        raise _http(e) from e


@router.post(
    "/workspaces/{workspace_id}/duplicate",
    summary="复制为新任务（跳过 GATE-0）",
)
async def duplicate_workspace(workspace_id: str, http_request: Request):
    try:
        user_id, _tenant_id = await _request_identity(http_request)
        return await product_survey_service.duplicate(workspace_id, actor=user_id if user_id != "anonymous" else "user")
    except ProductSurveyError as e:
        raise _http(e) from e


@router.get(
    "/workspaces/{workspace_id}/audit-log",
    summary="审计日志",
)
async def get_audit_log(workspace_id: str):
    try:
        entries = product_survey_service.get_audit_log(workspace_id)
        return {"entries": entries, "total": len(entries)}
    except ProductSurveyError as e:
        raise _http(e) from e


# ============================================================
# #5 质量提升: dao 历史 / 分享
# ============================================================

@router.get(
    "/workspaces/{workspace_id}/dao-history",
    summary="dao.md 当前版本 + 历史归档（GATE-0 diff 视图数据源）",
)
async def get_dao_history(workspace_id: str):
    try:
        return product_survey_service.get_dao_history(workspace_id)
    except ProductSurveyError as e:
        raise _http(e) from e


@router.post(
    "/workspaces/{workspace_id}/share",
    summary="生成只读分享 token（仅 completed 工作区；公开端点 /api/deep-research/share/{token}）",
)
async def create_share(workspace_id: str):
    try:
        return product_survey_service.create_share(workspace_id)
    except ProductSurveyError as e:
        raise _http(e) from e


# ============================================================
# Files
# ============================================================

@router.get(
    "/workspaces/{workspace_id}/files",
    summary="浏览工作区产物",
)
async def list_files(
    workspace_id: str,
    path: str = Query(default="", description="相对路径，空为根目录"),
):
    try:
        return product_survey_service.list_files(workspace_id, path)
    except ProductSurveyError as e:
        raise _http(e) from e


@router.get(
    "/workspaces/{workspace_id}/files/download",
    summary="下载单个文件（?inline=true 浏览器内预览，如 report.html）",
)
async def download_file(
    workspace_id: str,
    path: str = Query(..., description="文件相对路径"),
    inline: bool = Query(default=False, description="true 时不带 attachment 头，浏览器直接渲染"),
):
    import mimetypes

    try:
        fpath = product_survey_service.file_path(workspace_id, path)
        media_type = mimetypes.guess_type(str(fpath))[0] or "application/octet-stream"
        if inline:
            return FileResponse(str(fpath), media_type=media_type)
        return FileResponse(str(fpath), media_type=media_type, filename=fpath.name)
    except ProductSurveyError as e:
        raise _http(e) from e


@router.get(
    "/workspaces/{workspace_id}/files/download-all",
    summary="打包下载整个工作区（ZIP）",
)
async def download_all(workspace_id: str):
    try:
        data = product_survey_service.zip_bytes(workspace_id)
        return Response(
            content=data,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{workspace_id}.zip"'},
        )
    except ProductSurveyError as e:
        raise _http(e) from e
