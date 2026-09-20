# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""全局定时任务 API

跨工作空间的定时任务管理，支持：
- 全局任务列表（分页、状态筛选）
- 创建任务（可选 auto_create_workspace）
- 获取单个任务（自动解析所属 workspace）
"""

import logging
from datetime import datetime
from dawei.core.datetime_compat import UTC
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query

from dawei.api.scheduled_tasks import _create_task_in_workspace, _get_workspace_path
from dawei.entity.scheduled_task import TriggerStatus
from dawei.workspace import workspace_manager
from dawei.workspace.models import WorkspaceLifecycle, WorkspaceType
from dawei.workspace.scheduled_task_storage import ScheduledTaskStorage
from dawei.workspace.temp_workspace_manager import temp_workspace_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/scheduled-tasks", tags=["global-scheduled-tasks"])


def _enrich_task_with_workspace(task_dict: Dict[str, Any]) -> Dict[str, Any]:
    """为任务字典补充工作空间信息（返回新字典，不修改原始数据）"""
    result = dict(task_dict)
    workspace_id = result.get("workspace_id")
    if not workspace_id:
        return result

    workspace_info = workspace_manager.get_workspace_by_id(workspace_id)
    if workspace_info:
        result["workspace_name"] = workspace_info.get("name", "")
        result["workspace_display_name"] = workspace_info.get("display_name", workspace_info.get("name", ""))
        result["is_temp_workspace"] = workspace_info.get("lifecycle") == WorkspaceLifecycle.TEMPORARY.value
    else:
        result["workspace_name"] = ""
        result["workspace_display_name"] = ""
        result["is_temp_workspace"] = False

    # 优先从 metadata 中读取 last_execution_conversation_id（由 scheduler 写入）
    metadata = result.get("metadata")
    if isinstance(metadata, dict) and metadata.get("last_execution_conversation_id"):
        result["last_execution_conversation_id"] = metadata["last_execution_conversation_id"]
    else:
        result["last_execution_conversation_id"] = None

    return result


@router.get("")
async def list_global_scheduled_tasks(
    status: str | None = Query(None, description="按状态筛选"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
):
    """列出所有工作空间的定时任务（分页）"""
    all_tasks: List[Dict[str, Any]] = []
    all_workspaces = workspace_manager.get_all_workspaces()

    for ws in all_workspaces:
        ws_id = ws.get("id")
        ws_path = ws.get("path")
        if not ws_id or not ws_path:
            continue

        # 通过 ScheduledTaskStorage 读取（与正常调度流程一致）
        storage = ScheduledTaskStorage(ws_path)
        tasks = await storage.list_tasks()

        for task in tasks:
            task_dict = task.to_dict()
            # 按状态筛选
            if status and task_dict.get("status") != status:
                continue
            # 补充 workspace 信息
            task_dict["workspace_id"] = ws_id
            task_dict = _enrich_task_with_workspace(task_dict)
            all_tasks.append(task_dict)

    # 按创建时间倒序排列
    all_tasks.sort(key=lambda t: t.get("created_at", ""), reverse=True)

    # 分页
    total = len(all_tasks)
    total_pages = (total + page_size - 1) // page_size if total > 0 else 0
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    paginated_tasks = all_tasks[start_idx:end_idx]

    return {
        "success": True,
        "tasks": paginated_tasks,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


@router.post("")
async def create_scheduled_task_global(task: Dict[str, Any]):
    """创建定时任务（全局接口，支持自动创建临时工作空间）

    请求体:
    {
        "description": "任务描述",
        "schedule_type": "cron",
        "trigger_time": "2026-05-04T09:00:00Z",
        "cron_expression": "0 9 * * 1-5",
        "execution_type": "message",
        "execution_data": { "message": "...", "llm": "...", "mode": "..." },
        "tags": ["标签"],
        "workspace_id": null  // null=自动创建临时工作空间, 或指定已有 workspace ID
    }
    """
    workspace_id = task.get("workspace_id")

    if workspace_id:
        # 使用已有 workspace
        workspace_info = workspace_manager.get_workspace_by_id(workspace_id)
        if not workspace_info:
            raise HTTPException(status_code=404, detail=f"Workspace '{workspace_id}' not found")
        workspace_path = workspace_info["path"]
    else:
        # 自动创建临时 workspace
        display_name = f"[自动] {task.get('description', '')[:30]}"
        temp_ws = await temp_workspace_manager.create_temp_workspace(
            display_name=display_name,
            workspace_type=WorkspaceType.SCHEDULED_TASK.value,
            source_task_id=task.get("task_id"),
            source_task_type="scheduled",
        )
        workspace_id = temp_ws["id"]
        workspace_path = temp_ws["path"]

    # 复用核心创建逻辑
    result = await _create_task_in_workspace(workspace_id, workspace_path, task)

    # 补充 workspace 信息到返回结果（不修改原始字典）
    if result.get("task"):
        result["task"] = _enrich_task_with_workspace(result["task"])

    return result


@router.get("/{task_id}")
async def get_global_scheduled_task(task_id: str):
    """获取单个定时任务（自动查找所属 workspace）"""
    all_workspaces = workspace_manager.get_all_workspaces()

    for ws in all_workspaces:
        ws_id = ws.get("id")
        ws_path = ws.get("path")
        if not ws_id or not ws_path:
            continue

        # 通过 ScheduledTaskStorage 读取
        storage = ScheduledTaskStorage(ws_path)
        task = await storage.get_task(task_id)

        if task:
            task_dict = task.to_dict()
            task_dict["workspace_id"] = ws_id
            task_dict = _enrich_task_with_workspace(task_dict)
            return {
                "success": True,
                "task": task_dict,
            }

    raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
