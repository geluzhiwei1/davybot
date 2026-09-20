"""
IP 模板 API 路由。

提供 IP 模板列表、详情查询、模板化工作区创建、工作区参数复用端点。
"""

import json
import logging
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from dawei.workspace.ip_template import ip_template_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ip/templates", tags=["ip-templates"])


# ============================================================
# Request models
# ============================================================

class CreateTemplateWorkspaceRequest(BaseModel):
    """模板化工作区创建请求"""
    module: str
    template_slug: str
    form_data: dict[str, Any] = {}
    description: Optional[str] = None
    task_type: Optional[str] = None
    language: str = "zh"
    jurisdiction: Optional[str] = None
    target_country: Optional[str] = None
    draft_strategy: Optional[str] = None
    parent_workspace_id: Optional[str] = None
    inherit_from: Optional[list[str]] = None


# ============================================================
# GET /api/ip/templates — 列出可用模板
# ============================================================

@router.get(
    "",
    summary="列出 IP 模板",
    description="列出所有可用的 IP 工作区模板，可按模块筛选",
)
async def list_templates(
    module: Optional[str] = Query(None, description="按模块筛选（如 ip-draft）"),
    lang: str = Query("zh", description="语言代码（zh/en）"),
):
    templates = ip_template_manager.list_templates(module_slug=module, lang=lang)
    return {"templates": templates, "total": len(templates)}


# ============================================================
# GET /api/ip/templates/{template_slug} — 获取模板详情
# ============================================================

@router.get(
    "/{template_slug}",
    summary="获取 IP 模板详情",
    description="获取指定模板的完整定义（含 data_requirements, workspace_structure, phases 等）",
)
async def get_template(
    template_slug: str,
):
    template = ip_template_manager.load_template(template_slug)
    if not template:
        raise HTTPException(status_code=404, detail=f"Template not found: {template_slug}")
    return template


# ============================================================
# POST /api/ip/templates/{template_slug}/create-workspace
#   使用模板创建 IP 工作区
# ============================================================

@router.post(
    "/{template_slug}/create-workspace",
    summary="从模板创建 IP 工作区",
    description="使用指定模板创建并初始化 IP 工作区（Path B: 模板驱动模式）",
)
async def create_template_workspace(
    template_slug: str,
    request: CreateTemplateWorkspaceRequest,
):
    from dawei.models.ip import IpTaskContext
    from dawei.workspace.ip_workspace_service import ip_workspace_service

    # 验证模板存在
    template = ip_template_manager.load_template(template_slug)
    if not template:
        raise HTTPException(status_code=404, detail=f"Template not found: {template_slug}")

    # 构建任务上下文
    task_context = IpTaskContext(
        module=request.module,
        task_type=request.task_type or "template",
        description=request.description or "",
        language=request.language,
        jurisdiction=request.jurisdiction or "",
        target_country=request.target_country or "",
        draft_strategy=request.draft_strategy or "",
        parent_workspace_id=request.parent_workspace_id,
    )

    try:
        workspace_status = await ip_workspace_service.create_ip_workspace(
            module=request.module,
            task_context=task_context,
            template_slug=template_slug,
            template_form_data=request.form_data,
            inherit_from=request.inherit_from,
        )
        return {
            "workspace_id": workspace_status.workspace_id,
            "name": workspace_status.name,
            "display_name": workspace_status.display_name,
            "module": workspace_status.module,
            "status": workspace_status.status,
            "template_slug": template_slug,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Failed to create template workspace: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to create workspace: {e}")


# ============================================================
# GET /api/ip/templates/versions — 列出模板版本
# ============================================================

@router.get(
    "/versions/all",
    summary="列出所有模板版本",
    description="列出所有 IP 模板的版本号信息",
)
async def list_versions(
    module: Optional[str] = Query(None, description="按模块筛选"),
):
    versions = ip_template_manager.list_versions(module_slug=module)
    return {"versions": versions, "total": len(versions)}


# ============================================================
# GET /api/ip/templates/reuse/{workspace_id} — 复用工作区参数
# ============================================================

@router.get(
    "/reuse/{workspace_id}",
    summary="获取工作区表单参数（用于复用）",
    description="从已有工作区读取 task_params.json 和 workspace.json，"
                "返回可复用的表单数据，用于快速创建同类型工作区",
)
async def get_workspace_params_for_reuse(
    workspace_id: str,
):
    """读取已有工作区的 input/task_params.json 和 workspace.json，
    提取可复用的表单参数。"""
    from dawei.workspace.ip_workspace_service import ip_workspace_service

    # 解析工作区路径
    ws_path = await ip_workspace_service._resolve_workspace_path(workspace_id)
    if ws_path is None:
        raise HTTPException(status_code=404, detail=f"Workspace not found: {workspace_id}")

    result: dict[str, Any] = {"workspace_id": workspace_id}

    # 读取 workspace.json 获取元数据
    meta_path = ws_path / "workspace.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            result["template_slug"] = meta.get("template_slug", "")
            result["module"] = meta.get("module", "")
            result["target_country"] = meta.get("target_country", "")
        except (json.JSONDecodeError, OSError):
            pass

    # 读取 input/task_params.json 获取表单数据
    params_path = ws_path / "input" / "task_params.json"
    if params_path.exists():
        try:
            params = json.loads(params_path.read_text(encoding="utf-8"))
            result["form_data"] = params
        except (json.JSONDecodeError, OSError):
            result["form_data"] = {}
    else:
        result["form_data"] = {}

    return result
