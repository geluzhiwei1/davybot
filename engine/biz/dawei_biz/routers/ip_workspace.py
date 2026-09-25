"""
IP 工作区 API 路由。

提供 IP 模块专用的工作区创建/查询/恢复/清理端点。
所有 IP LLM 任务通过工作区生命周期管理。
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from dawei.models.ip import (
    InheritRequest,
    IpTaskContext,
    WorkspaceStatus,
)
from dawei_biz.services.ip_workspace_service import ip_workspace_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ip/workspace", tags=["ip-workspace"])

portfolio_router = APIRouter(prefix="/api/ip/portfolio", tags=["ip-portfolio"])


# ============================================================
# POST /api/ip/workspace/{module}/create
#   为指定 IP 模块创建任务工作区
# ============================================================

@router.post(
    "/{module}/create",
    response_model=WorkspaceStatus,
    summary="创建 IP 任务工作区",
    description="为指定 IP 模块创建临时/持久工作区，安装模块专属资源",
)
async def create_ip_workspace(
    module: str,
    context: IpTaskContext,
    http_request: Request,
):
    """
    Args:
        module: IP 模块标识 (e.g., "ip-draft", "ip-disclosure")
        context: 任务上下文 (module, task_type, parent_workspace_id 等)
    """
    # 验证 module
    valid_modules = [
        "ip-idea-vault", "ip-disclosure", "ip-draft", "ip-application",
        "ip-filing", "ip-oa-reply", "ip-reverse-detection",
        "ip-portfolio", "ip-trademark",
    ]
    if module not in valid_modules:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown IP module: {module}. Valid: {valid_modules}",
        )

    # 从 context 覆盖 module 字段（来自 URL 路由）
    context.module = module

    from dawei.api.auth import extract_market_token

    try:
        return await ip_workspace_service.create_ip_workspace(
            module=module,
            task_context=context,
            market_token=extract_market_token(http_request),
        )
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        logger.exception(f"Failed to create IP workspace for {module}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# GET /api/ip/workspace/{workspace_id}/status
#   获取工作区状态
# ============================================================

@router.get(
    "/{workspace_id}/status",
    response_model=WorkspaceStatus,
    summary="获取工作区状态",
)
async def get_workspace_status(workspace_id: str):
    """获取指定工作区的运行状态，包含 checkpoint、进度、文件数等。"""
    try:
        return await ip_workspace_service.get_workspace_status(workspace_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception(f"Failed to get workspace status: {workspace_id}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# POST /api/ip/workspace/{workspace_id}/resume
#   恢复未完成的任务
# ============================================================

@router.post(
    "/{workspace_id}/resume",
    response_model=WorkspaceStatus,
    summary="恢复任务",
    description="检查工作区状态并返回可恢复的 checkpoint 信息",
)
async def resume_workspace(workspace_id: str):
    """检查工作区是否可以恢复。"""
    try:
        return await ip_workspace_service.resume_workspace(workspace_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=410, detail=str(e))  # Gone — expired
    except Exception as e:
        logger.exception(f"Failed to resume workspace: {workspace_id}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# DELETE /api/ip/workspace/{workspace_id}
#   手动清理工作区
# ============================================================

@router.delete(
    "/{workspace_id}",
    summary="清理工作区",
)
async def cleanup_workspace(
    workspace_id: str,
    force: bool = Query(False, description="强制清理，跳过活跃检查"),
):
    """
    Args:
        workspace_id: 工作区 ID
        force: 强制清理（即使任务运行中）
    """
    try:
        success = await ip_workspace_service.cleanup_workspace(
            workspace_id, force=force
        )
        if success:
            return {"deleted": True, "workspace_id": workspace_id}
        return {"deleted": False, "workspace_id": workspace_id, "reason": "not_found"}
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        logger.exception(f"Failed to cleanup workspace: {workspace_id}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# GET /api/ip/workspace/{workspace_id}/files
#   列出工作区文件
# ============================================================

@router.get(
    "/{workspace_id}/files",
    summary="列出工作区文件",
)
async def list_workspace_files(workspace_id: str):
    """获取工作区 .dawei/files/ 中的所有文件列表。"""
    try:
        return await ip_workspace_service.get_workspace_files(workspace_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception(f"Failed to list files: {workspace_id}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# GET /api/ip/workspace/resumable
#   获取所有可恢复的 IP 任务
# ============================================================

@router.get(
    "/resumable",
    summary="获取可恢复任务列表",
)
async def list_resumable_tasks():
    """获取所有有未完成 checkpoint 的 IP 任务。"""
    try:
        return await ip_workspace_service.list_resumable_tasks()
    except Exception as e:
        logger.exception("Failed to list resumable tasks")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# POST /api/ip/workspace/{workspace_id}/inherit
#   从另一个工作区继承文件
# ============================================================

@router.post(
    "/{workspace_id}/inherit",
    summary="继承父工作区文件",
)
async def inherit_files(workspace_id: str, request: InheritRequest):
    """
    从 parent_workspace_id 复制指定文件到当前工作区。

    Args:
        workspace_id: 目标工作区 ID
        request: 继承请求体 {parent_workspace_id, file_names}
    """
    try:
        inherited = await ip_workspace_service.inherit_files(
            workspace_id=workspace_id,
            request=request,
        )
        return {
            "inherited": inherited,
            "count": len(inherited),
            "workspace_id": workspace_id,
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception(f"Failed to inherit files: {workspace_id}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# POST /api/ip/workspace/create
#   创建 IP 工作区 (flat convenience endpoint — wraps /{module}/create)
# ============================================================


class CreateWorkspaceRequest(BaseModel):
    """Flat create request from frontend."""
    workspace_type: str
    task_type: str
    subtype: str | None = None
    description: str | None = None
    parent_workspace_id: str | None = None
    language: str | None = "zh-CN"


@router.post(
    "/create",
    response_model=WorkspaceStatus,
    summary="创建 IP 工作区 (flat endpoint)",
)
async def create_ip_workspace_flat(req: CreateWorkspaceRequest, http_request: Request):
    """
    Flat convenience endpoint that maps frontend's {workspace_type, task_type}
    to the module-scoped POST /{module}/create.
    """
    valid_modules = [
        "ip-idea-vault", "ip-disclosure", "ip-draft", "ip-application",
        "ip-filing", "ip-oa-reply", "ip-reverse-detection",
        "ip-portfolio", "ip-trademark",
    ]
    if req.workspace_type not in valid_modules:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown workspace_type: {req.workspace_type}. Valid: {valid_modules}",
        )

    context = IpTaskContext(
        module=req.workspace_type,
        task_type=req.task_type,
        description=req.description,
        parent_workspace_id=req.parent_workspace_id,
        language=req.language or "zh-CN",
        user_preferences={"subtype": req.subtype} if req.subtype else {},
    )

    from dawei.api.auth import extract_market_token

    try:
        return await ip_workspace_service.create_ip_workspace(
            module=req.workspace_type,
            task_context=context,
            market_token=extract_market_token(http_request),
        )
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        logger.exception("Failed to create IP workspace")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# GET /api/ip/workspace/list
#   列出 IP 工作区（按 workspace_type 筛选 + 按名称搜索）
# ============================================================

@router.get(
    "/list",
    summary="列出 IP 工作区",
)
async def list_ip_workspaces(
    workspace_type: str | None = Query(None, description="工作区类型筛选"),
    q: str | None = Query(None, description="名称搜索关键词"),
):
    """返回前端的 Workspace[] 兼容格式列表。

    返回格式: { items: [...] }
    """
    try:
        items = await ip_workspace_service.list_ip_workspaces(
            workspace_type=workspace_type,
            search_query=q,
        )
        return {"items": items}
    except Exception as e:
        logger.exception("Failed to list IP workspaces")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# POST /api/ip/workspace/{workspace_id}/archive
#   归档工作区（标记为不再自动清理）
# ============================================================

@router.post(
    "/{workspace_id}/archive",
    summary="归档工作区",
)
async def archive_ip_workspace(workspace_id: str):
    """标记工作区为已归档，阻止自动清理。

    (当前实现：标记 lifecycle=persistent 阻止自动清理)
    """
    try:
        ws_path = await ip_workspace_service._resolve_workspace_path(workspace_id)
        if ws_path is None:
            raise HTTPException(status_code=404, detail=f"Workspace not found: {workspace_id}")

        import json
        workspace_json = ws_path / ".dawei" / "workspace.json"
        if workspace_json.exists():
            with workspace_json.open() as f:
                config = json.load(f)
            config["lifecycle"] = "persistent"
            if "ip_metadata" in config:
                config["ip_metadata"]["expires_at"] = None
            with workspace_json.open("w") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)

        return {"archived": True, "workspace_id": workspace_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to archive workspace: {workspace_id}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# POST /api/ip/workspace/{workspace_id}/checkpoint
#   IP 任务 checkpoint 保存
# ============================================================


class CheckpointSaveRequest(BaseModel):
    """Checkpoint 保存请求体"""
    phase: str
    description: str = ""
    progress_current: int = 0
    progress_total: int = 0
    metadata: dict | None = None


class CheckpointListResponse(BaseModel):
    """Checkpoint 列表项"""
    id: str
    phase: str
    description: str
    timestamp: str
    progress_current: int
    progress_total: int


@router.post(
    "/{workspace_id}/checkpoint",
    summary="保存 IP 任务 checkpoint",
)
async def save_ip_checkpoint(workspace_id: str, body: CheckpointSaveRequest):
    """保存 IP 任务执行进度 checkpoint 到工作区。

    写入 .dawei/checkpoints/checkpoint-{timestamp}.json，
    供 get_workspace_status 读取恢复。
    """
    try:
        result = await ip_workspace_service.save_checkpoint(
            workspace_id=workspace_id,
            phase=body.phase,
            description=body.description,
            progress_current=body.progress_current,
            progress_total=body.progress_total,
            metadata=body.metadata,
        )
        return {"success": True, "checkpoint": result}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception(f"Failed to save checkpoint: {workspace_id}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/{workspace_id}/checkpoint",
    summary="获取最新 IP checkpoint",
)
async def get_latest_ip_checkpoint(workspace_id: str):
    """获取工作区最新 checkpoint（用于断点恢复）。"""
    try:
        cp = await ip_workspace_service.get_latest_checkpoint(workspace_id)
        if cp is None:
            raise HTTPException(status_code=404, detail=f"No checkpoint found: {workspace_id}")
        return {"success": True, "checkpoint": cp}
    except HTTPException:
        raise
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception(f"Failed to get checkpoint: {workspace_id}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/{workspace_id}/checkpoints",
    summary="列出所有 IP checkpoints",
)
async def list_ip_checkpoints(workspace_id: str):
    """列出工作区所有 checkpoint（按时间降序）。"""
    try:
        cps = await ip_workspace_service.list_checkpoints(workspace_id)
        return {"success": True, "checkpoints": cps, "count": len(cps)}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception(f"Failed to list checkpoints: {workspace_id}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# POST /api/ip/workspace/cleanup-expired
#   清理过期 IP 工作区
# ============================================================

@router.post(
    "/cleanup-expired",
    summary="清理过期 IP 工作区",
)
async def cleanup_expired_ip_workspaces():
    """扫描并清理已过期的 IP 临时工作区（72h TTL）。

    返回清理的工作区数量。
    """
    try:
        cleaned = await ip_workspace_service.cleanup_expired_ip_workspaces()
        return {"success": True, "cleaned": cleaned}
    except Exception as e:
        logger.exception("Failed to cleanup expired IP workspaces")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# GET /api/ip/workspace/{module}/resources
#   获取模块资源清单
# ============================================================

@router.get(
    "/{module}/resources",
    summary="获取模块资源清单",
)
async def get_module_resources(module: str):
    """返回指定 IP 模块需要的 skills/mcps/knowledges/agents 清单。"""
    return ip_workspace_service.get_module_resources(module)


# ============================================================
# GET /api/ip/portfolio/stats
#   IP 资产组合聚合统计
# ============================================================

@portfolio_router.get(
    "/stats",
    summary="IP 资产组合统计",
)
async def get_portfolio_stats():
    """聚合所有 IP 工作区数据，返回 KPI 统计。"""
    try:
        items = await ip_workspace_service.list_ip_workspaces()
    except Exception:
        items = []

    from datetime import datetime
    from collections import Counter

    total = len(items)
    modules = Counter()
    recent = []
    this_year = datetime.now().year

    for ws in items:
        ws_type = ws.get("workspace_type", ws.get("module", "unknown"))
        modules[ws_type] += 1
        created = ws.get("created_at", "")
        if created and str(this_year) in created[:4]:
            pass  # count handled below
        recent.append({
            "id": ws.get("id", ""),
            "name": ws.get("name", ""),
            "workspace_type": ws_type,
            "created_at": created,
        })

    new_this_year = sum(
        1 for ws in items
        if ws.get("created_at", "") and str(this_year) in ws.get("created_at", "")[:4]
    )

    recent.sort(key=lambda x: x.get("created_at", ""), reverse=True)

    return {
        "total_workspaces": total,
        "patents_granted": 0,
        "patents_pending": 0,
        "trademarks_registered": 0,
        "trademarks_pending": 0,
        "new_this_year": new_this_year,
        "modules": [{"type": t, "count": c} for t, c in modules.most_common()],
        "recent_workspaces": recent[:10],
    }
