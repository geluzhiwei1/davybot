# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Checkpoint Management API Routes

任务检查点管理
"""

import logging
from datetime import UTC, datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from dawei.api.error_codes import ErrorCodes, error_detail
from dawei.workspace import workspace_manager
from dawei.workspace.user_workspace import UserWorkspace

logger = logging.getLogger(__name__)

# 创建路由器
router = APIRouter(tags=["workspaces-checkpoints"])


# --- Pydantic 模型 ---


class CheckpointInfo(BaseModel):
    """检查点信息"""

    checkpoint_id: str
    task_id: str
    created_at: str
    description: str | None
    execution_state: dict[str, Any] | None


# --- 辅助函数 ---


async def _ensure_workspace_initialized(workspace: UserWorkspace) -> None:
    """确保工作区已初始化"""
    if not workspace.is_initialized():
        await workspace.initialize()


def get_user_workspace(workspace_id: str) -> UserWorkspace:
    """Dependency to get a UserWorkspace instance."""
    workspace_info = workspace_manager.get_workspace_by_id(workspace_id)
    if not workspace_info:
        raise HTTPException(status_code=404, detail=error_detail("workspace.not_found", workspace_id=workspace_id))

    workspace_path = workspace_info.get("path")
    if not workspace_path:
        raise HTTPException(status_code=404, detail=error_detail("workspace.path_not_found", workspace_id=workspace_id))

    return UserWorkspace(workspace_path=workspace_path)


# --- Checkpoint管理路由 ---


@router.get("/{workspace_id}/tasks/{task_id}/checkpoints")
async def get_task_checkpoints(workspace_id: str, task_id: str):
    """获取任务的所有检查点"""
    try:
        workspace = get_user_workspace(workspace_id)
        await _ensure_workspace_initialized(workspace)

        # 简化实现：从checkpoint_manager获取检查点列表
        checkpoint_manager = workspace.checkpoint_manager

        if not checkpoint_manager:
            return {"success": True, "checkpoints": [], "total": 0}

        checkpoints = await checkpoint_manager.get_checkpoints(task_id)

        return {"success": True, "checkpoints": checkpoints, "total": len(checkpoints)}

    except (AttributeError, KeyError, ValueError, OSError) as e:
        logger.error(f"Failed to get checkpoints for task {task_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=error_detail("checkpoint.list_failed", error=str(e)))


@router.post("/{workspace_id}/tasks/{task_id}/checkpoints")
async def create_task_checkpoint(
    workspace_id: str,
    task_id: str,
    description: str | None = None,
):
    """创建任务检查点"""
    try:
        workspace = get_user_workspace(workspace_id)
        await _ensure_workspace_initialized(workspace)

        checkpoint_manager = workspace.checkpoint_manager

        if not checkpoint_manager:
            raise HTTPException(status_code=501, detail=error_detail("checkpoint.not_available"))

        # 创建检查点
        checkpoint_id = await checkpoint_manager.create_checkpoint(
            task_id=task_id,
            description=description or f"Checkpoint for task {task_id}",
        )

        logger.info(f"Created checkpoint {checkpoint_id} for task {task_id}")

        return {
            "success": True,
            "message": "Checkpoint created successfully",
            "checkpoint_id": checkpoint_id,
            "created_at": datetime.now(UTC).isoformat(),
        }

    except HTTPException:
        raise
    except (AttributeError, KeyError, ValueError, OSError) as e:
        logger.error(f"Failed to create checkpoint for task {task_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=error_detail("checkpoint.create_failed", error=str(e)))


@router.get("/{workspace_id}/tasks/{task_id}/checkpoints/{checkpoint_id}")
async def get_task_checkpoint_detail(workspace_id: str, task_id: str, checkpoint_id: str):
    """获取检查点详细信息"""
    try:
        workspace = get_user_workspace(workspace_id)
        await _ensure_workspace_initialized(workspace)

        checkpoint_manager = workspace.checkpoint_manager

        if not checkpoint_manager:
            raise HTTPException(status_code=501, detail=error_detail("checkpoint.not_available"))

        checkpoint_data = await checkpoint_manager.get_checkpoint(checkpoint_id)

        if not checkpoint_data:
            raise HTTPException(status_code=404, detail=error_detail("checkpoint.not_found", checkpoint_id=checkpoint_id))

        return {"success": True, "checkpoint": checkpoint_data}

    except HTTPException:
        raise
    except (AttributeError, KeyError, ValueError, OSError) as e:
        logger.error(f"Failed to get checkpoint {checkpoint_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get checkpoint: {e!s}")


@router.post("/{workspace_id}/tasks/{task_id}/checkpoints/{checkpoint_id}/restore")
async def restore_task_checkpoint(workspace_id: str, task_id: str, checkpoint_id: str):
    """从检查点恢复任务"""
    try:
        workspace = get_user_workspace(workspace_id)
        await _ensure_workspace_initialized(workspace)

        checkpoint_manager = workspace.checkpoint_manager

        if not checkpoint_manager:
            raise HTTPException(status_code=501, detail=error_detail("checkpoint.not_available"))

        # 恢复检查点
        success = await checkpoint_manager.restore_checkpoint(
            task_id=task_id,
            checkpoint_id=checkpoint_id,
        )

        if not success:
            raise HTTPException(status_code=500, detail="Failed to restore checkpoint")

        logger.info(f"Restored checkpoint {checkpoint_id} for task {task_id}")

        return {
            "success": True,
            "message": "Checkpoint restored successfully",
            "checkpoint_id": checkpoint_id,
            "restored_at": datetime.now(UTC).isoformat(),
        }

    except HTTPException:
        raise
    except (AttributeError, KeyError, ValueError, OSError) as e:
        logger.error(f"Failed to restore checkpoint {checkpoint_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to restore checkpoint: {e!s}",
        )
