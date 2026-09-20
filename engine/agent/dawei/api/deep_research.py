# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Deep Research 通用调研框架 API（PRD §10 #4/#5）。

端点:
- GET  /api/deep-research/pipelines                                已注册流水线清单
- GET  /api/deep-research/share/{token}                            公开只读报告（跨流水线 token 反查）

通用工作区面（任意注册流水线，与产品调研 REST 契约一致）:
- POST /api/deep-research/pipelines/{pipeline}/workspaces          创建工作区
- GET  /api/deep-research/pipelines/{pipeline}/workspaces          工作区列表
- GET  /api/deep-research/pipelines/{pipeline}/workspaces/{id}     详情
- POST /api/deep-research/pipelines/{pipeline}/workspaces/{id}/start           启动
- POST /api/deep-research/pipelines/{pipeline}/workspaces/{id}/gates/{gateId}/decide   GATE 决策
- POST /api/deep-research/pipelines/{pipeline}/workspaces/{id}/retry           单阶段重试
- POST /api/deep-research/pipelines/{pipeline}/workspaces/{id}/duplicate       复制为新任务
- GET  /api/deep-research/pipelines/{pipeline}/workspaces/{id}/audit-log       审计日志
- GET  /api/deep-research/pipelines/{pipeline}/workspaces/{id}/files           浏览产物
- GET  /api/deep-research/pipelines/{pipeline}/workspaces/{id}/files/download  下载（?inline=true 预览）
- GET  /api/deep-research/pipelines/{pipeline}/workspaces/{id}/files/download-all  打包下载
- GET  /api/deep-research/pipelines/{pipeline}/workspaces/{id}/dao-history     需求文档历史
- POST /api/deep-research/pipelines/{pipeline}/workspaces/{id}/share           生成分享 token
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

# 导入触发流水线自注册（product / industry 注册到 PIPELINE_REGISTRY）
from dawei.workspace import industry_research_service  # noqa: F401
from dawei.workspace import product_survey_service as _product_module  # noqa: E402,F401
from dawei.workspace.deep_research_framework import (
    DeepResearchError,
    find_shared,
    get_pipeline,
    list_pipelines,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/deep-research", tags=["deep-research"])


def _http(e: DeepResearchError) -> HTTPException:
    return HTTPException(status_code=e.status_code, detail=str(e))


async def _request_identity(http_request: Request) -> tuple[str, str]:
    """提取请求身份（工作区注册归属）；无鉴权上下文时回退请求体默认值。"""
    try:
        from dawei.api.auth import get_authenticated_tenant_id, get_authenticated_user_id

        return await get_authenticated_user_id(http_request), await get_authenticated_tenant_id(http_request)
    except Exception:  # noqa: BLE001
        return "anonymous", "default"


class CreateGenericWorkspaceRequest(BaseModel):
    """通用创建请求（字段与 DeepResearchServiceBase.create_workspace 对齐）。"""

    topic: str
    mode: str = Field(default="direct", pattern="^(direct|wizard)$")
    background: str = ""
    audience: str = ""
    user_input: str = ""
    scope: Optional[dict[str, Any]] = None
    dimensions: Optional[list[dict[str, Any]]] = None
    success_criteria: Optional[dict[str, Any]] = None
    input_doc: Optional[str] = None  # 自带需求文档（跳过默认渲染）
    template_slug: Optional[str] = None
    template_name: Optional[str] = None
    user_id: str = "anonymous"
    tenant_id: str = "default"
    auto_start: bool = False
    dry_run: bool = True


class GateDecideGenericRequest(BaseModel):
    action: str = Field(pattern="^(approve|reject|edit)$")
    note: str = ""
    dao_md: str = ""
    actor: str = "user"


# ============================================================
# Pipelines / Share（公开）
# ============================================================


@router.get("/pipelines", summary="已注册调研流水线清单")
async def api_list_pipelines():
    pipelines = list_pipelines()
    return {"pipelines": pipelines, "total": len(pipelines)}


@router.get("/share/{token}", summary="公开只读报告（分享 token，跨流水线反查）")
async def api_get_shared(token: str):
    try:
        return find_shared(token)
    except DeepResearchError as e:
        raise _http(e) from e


# ============================================================
# 通用工作区面
# ============================================================


@router.post("/pipelines/{pipeline}/workspaces", summary="创建工作区（任意注册流水线）")
async def api_create_workspace(pipeline: str, req: CreateGenericWorkspaceRequest, http_request: Request):
    try:
        import inspect

        svc = get_pipeline(pipeline)
        user_id, tenant_id = await _request_identity(http_request)
        # 各流水线 create_workspace 签名可能不同（如 product 为 dao_md，框架为 input_doc）
        # → 按目标签名过滤关键字参数，两种形态均兼容
        kwargs = {
            "topic": req.topic,
            "mode": req.mode,
            "background": req.background,
            "audience": req.audience,
            "user_input": req.user_input,
            "scope": req.scope,
            "dimensions": req.dimensions,
            "success_criteria": req.success_criteria,
            "input_doc": req.input_doc,
            "dao_md": req.input_doc,
            "template_slug": req.template_slug or (svc.default_template_slug or None),
            "template_name": req.template_name,
            "user_id": user_id if user_id != "anonymous" else req.user_id,
            "tenant_id": tenant_id if tenant_id != "default" else req.tenant_id,
            "dry_run": req.dry_run,
        }
        accepted = set(inspect.signature(svc.create_workspace).parameters)
        meta = await svc.create_workspace(**{k: v for k, v in kwargs.items() if k in accepted})
        if req.auto_start:
            meta = svc.start(meta["workspace_id"], dry_run=req.dry_run)
        return meta
    except DeepResearchError as e:
        raise _http(e) from e


@router.get("/pipelines/{pipeline}/workspaces", summary="工作区列表")
async def api_list_workspaces(pipeline: str):
    try:
        workspaces = get_pipeline(pipeline).list_workspaces()
        return {"workspaces": workspaces, "total": len(workspaces)}
    except DeepResearchError as e:
        raise _http(e) from e


@router.get("/pipelines/{pipeline}/workspaces/{workspace_id}", summary="工作区详情")
async def api_get_workspace(pipeline: str, workspace_id: str):
    try:
        return get_pipeline(pipeline).get_workspace(workspace_id)
    except DeepResearchError as e:
        raise _http(e) from e


@router.delete("/pipelines/{pipeline}/workspaces/{workspace_id}", summary="删除工作区（目录 + 注册 + 分享 token，不可恢复）")
async def api_delete_workspace(pipeline: str, workspace_id: str, http_request: Request):
    try:
        user_id, _ = await _request_identity(http_request)
        return await get_pipeline(pipeline).delete_workspace(workspace_id, actor=user_id)
    except DeepResearchError as e:
        raise _http(e) from e


@router.post("/pipelines/{pipeline}/workspaces/{workspace_id}/start", summary="启动/继续流水线（?dry_run=false 真实 LLM 执行）")
async def api_start_workspace(pipeline: str, workspace_id: str, dry_run: bool = True):
    try:
        return get_pipeline(pipeline).start(workspace_id, dry_run=dry_run)
    except DeepResearchError as e:
        raise _http(e) from e


@router.post("/pipelines/{pipeline}/workspaces/{workspace_id}/gates/{gate_id}/decide", summary="GATE 决策")
async def api_decide_gate(pipeline: str, workspace_id: str, gate_id: str, req: GateDecideGenericRequest):
    try:
        return get_pipeline(pipeline).decide_gate(
            workspace_id, gate_id, req.action, note=req.note, dao_md=req.dao_md, actor=req.actor
        )
    except DeepResearchError as e:
        raise _http(e) from e


@router.post("/pipelines/{pipeline}/workspaces/{workspace_id}/retry", summary="从指定 stage 重跑")
async def api_retry_workspace(
    pipeline: str,
    workspace_id: str,
    from_stage: str = Query(..., description="起始 stage id"),
):
    try:
        return get_pipeline(pipeline).retry(workspace_id, from_stage)
    except DeepResearchError as e:
        raise _http(e) from e


@router.post("/pipelines/{pipeline}/workspaces/{workspace_id}/duplicate", summary="复制为新任务")
async def api_duplicate_workspace(pipeline: str, workspace_id: str):
    try:
        return await get_pipeline(pipeline).duplicate(workspace_id)
    except DeepResearchError as e:
        raise _http(e) from e


@router.get("/pipelines/{pipeline}/workspaces/{workspace_id}/audit-log", summary="审计日志")
async def api_get_audit_log(pipeline: str, workspace_id: str):
    try:
        entries = get_pipeline(pipeline).get_audit_log(workspace_id)
        return {"entries": entries, "total": len(entries)}
    except DeepResearchError as e:
        raise _http(e) from e


@router.get("/pipelines/{pipeline}/workspaces/{workspace_id}/files", summary="浏览工作区产物")
async def api_list_files(pipeline: str, workspace_id: str, path: str = Query(default="")):
    try:
        return get_pipeline(pipeline).list_files(workspace_id, path)
    except DeepResearchError as e:
        raise _http(e) from e


@router.get("/pipelines/{pipeline}/workspaces/{workspace_id}/files/download", summary="下载单个文件（?inline=true 预览）")
async def api_download_file(
    pipeline: str,
    workspace_id: str,
    path: str = Query(...),
    inline: bool = Query(default=False),
):
    import mimetypes

    try:
        fpath = get_pipeline(pipeline).file_path(workspace_id, path)
        media_type = mimetypes.guess_type(str(fpath))[0] or "application/octet-stream"
        if inline:
            return FileResponse(str(fpath), media_type=media_type)
        return FileResponse(str(fpath), media_type=media_type, filename=fpath.name)
    except DeepResearchError as e:
        raise _http(e) from e


@router.get("/pipelines/{pipeline}/workspaces/{workspace_id}/files/download-all", summary="打包下载（ZIP）")
async def api_download_all(pipeline: str, workspace_id: str):
    try:
        data = get_pipeline(pipeline).zip_bytes(workspace_id)
        return Response(
            content=data,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{workspace_id}.zip"'},
        )
    except DeepResearchError as e:
        raise _http(e) from e


@router.get("/pipelines/{pipeline}/workspaces/{workspace_id}/dao-history", summary="需求文档历史（diff 视图数据源）")
async def api_get_dao_history(pipeline: str, workspace_id: str):
    try:
        return get_pipeline(pipeline).get_input_doc_history(workspace_id)
    except DeepResearchError as e:
        raise _http(e) from e


@router.post("/pipelines/{pipeline}/workspaces/{workspace_id}/share", summary="生成只读分享 token")
async def api_create_share(pipeline: str, workspace_id: str):
    try:
        return get_pipeline(pipeline).create_share(workspace_id)
    except DeepResearchError as e:
        raise _http(e) from e
