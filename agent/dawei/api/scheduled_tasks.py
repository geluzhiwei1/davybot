# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""定时任务管理 API 路由

提供定时任务的 CRUD 操作和执行历史查询功能。
使用统一的 ScheduledTaskStorage 存储系统。
"""

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from dawei.entity.scheduled_task import ScheduleType, ScheduledTask, TriggerStatus
from dawei.logg.logging import get_logger
from dawei.tools.scheduler import scheduler_manager
from dawei.workspace import workspace_manager

logger = get_logger(__name__)

router = APIRouter(prefix="/api/workspaces/{workspace_id}/scheduled-tasks", tags=["scheduled-tasks"])


async def _get_workspace_path(workspace_id: str) -> str:
    """获取 workspace 路径"""
    workspace_info = workspace_manager.get_workspace_by_id(workspace_id)
    if not workspace_info:
        raise HTTPException(
            status_code=404,
            detail=f"Workspace '{workspace_id}' not found.",
        )
    return workspace_info["path"]


@router.get("")
async def list_scheduled_tasks(workspace_id: str):
    """获取工作区的所有定时任务"""
    workspace_path = await _get_workspace_path(workspace_id)

    # 获取 scheduler
    scheduler = await scheduler_manager.get_scheduler(workspace_id, workspace_path)

    # 从 ScheduledTaskStorage 读取
    tasks = await scheduler.storage.list_tasks()

    # 转换为字典格式
    task_list = [task.to_dict() for task in tasks]

    # 检查调度器状态
    active_workspaces = await scheduler_manager.get_active_workspaces()
    has_active_scheduler = workspace_id in active_workspaces

    return {
        "success": True,
        "tasks": task_list,
        "total": len(task_list),
        "scheduler_active": has_active_scheduler,
    }


@router.post("")
async def create_scheduled_task(workspace_id: str, task: dict[str, Any]):
    """创建新的定时任务

    请求体格式:
    {
        "description": "任务描述",
        "schedule_type": "delay|at_time|recurring|cron",
        "trigger_time": "2026-02-25T14:00:00Z",
        "repeat_interval": 3600,  // 可选
        "max_repeats": 10,  // 可选
        "cron_expression": "0 14 * * *",  // 可选
        "execution_type": "message",
        "execution_data": {
            "message": "要执行的消息",
            "llm": "deepseek/deepseek-chat",  // 可选：覆盖默认 LLM
            "mode": "orchestrator"  // 可选：覆盖默认模式
        }
    }
    """
    workspace_path = await _get_workspace_path(workspace_id)

    # 验证必填字段
    required_fields = [
        "description",
        "schedule_type",
        "trigger_time",
        "execution_type",
        "execution_data",
    ]
    for field in required_fields:
        if field not in task:
            raise HTTPException(
                status_code=400,
                detail=f"Missing required field: {field}",
            )

    # 验证 cron 表达式
    if task.get("schedule_type") == "cron" and task.get("cron_expression"):
        try:
            from croniter import croniter

            # 验证表达式有效性
            try:
                cron = croniter(task["cron_expression"])
            except ValueError as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid cron expression syntax: {e}",
                )

            # 验证执行间隔（最小60秒）
            base = datetime.now(UTC)
            try:
                cron_iter = croniter(task["cron_expression"], base)
                next_time = cron_iter.get_next(datetime)
                interval = (next_time - base).total_seconds()
                if interval < 60:
                    raise HTTPException(
                        status_code=400,
                        detail="Cron execution interval must be at least 60 seconds for safety",
                    )
            except Exception as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid cron expression: {e}",
                )

        except ImportError:
            raise HTTPException(
                status_code=500,
                detail="croniter package is required for cron scheduling. Please install it with: pip install croniter",
            )

    # 验证 execution_type
    if task["execution_type"] != "message":
        raise HTTPException(
            status_code=400,
            detail=f"Invalid execution_type: {task['execution_type']}. Only 'message' is supported.",
        )

    # 解析 trigger_time
    try:
        trigger_time = datetime.fromisoformat(task["trigger_time"])
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid trigger_time format: {e}. Use ISO format like '2025-01-01T12:00:00'",
        )

    # 生成任务 ID
    task_id = f"task-{uuid.uuid4().hex[:12]}"

    # 创建 ScheduledTask 实体
    scheduled_task = ScheduledTask(
        task_id=task_id,
        workspace_id=workspace_id,
        description=task["description"],
        schedule_type=ScheduleType(task["schedule_type"]),
        trigger_time=trigger_time,
        repeat_interval=task.get("repeat_interval"),
        max_repeats=task.get("max_repeats"),
        cron_expression=task.get("cron_expression"),
        execution_type=task["execution_type"],
        execution_data=task["execution_data"],
        status=TriggerStatus.PENDING,
        created_at=datetime.now(UTC),
        repeat_count=0,
        tags=task.get("tags", []),
        metadata=task.get("metadata"),
    )

    # 获取 scheduler 并保存
    scheduler = await scheduler_manager.get_scheduler(workspace_id, workspace_path)
    success = await scheduler.storage.save_task(scheduled_task)

    if not success:
        raise HTTPException(
            status_code=500,
            detail="Failed to save scheduled task",
        )

    logger.info(f"Created scheduled task {task_id}: {task.get('description')}")

    return {
        "success": True,
        "task": scheduled_task.to_dict(),
        "message": "定时任务创建成功",
    }


@router.get("/{task_id}")
async def get_scheduled_task(workspace_id: str, task_id: str):
    """获取单个定时任务详情"""
    workspace_path = await _get_workspace_path(workspace_id)

    scheduler = await scheduler_manager.get_scheduler(workspace_id, workspace_path)
    task = await scheduler.storage.get_task(task_id)

    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")

    return {
        "success": True,
        "task": task.to_dict(),
    }


@router.put("/{task_id}")
async def update_scheduled_task(workspace_id: str, task_id: str, updates: dict[str, Any]):
    """更新定时任务

    支持更新的字段:
    - description
    - schedule_type
    - trigger_time
    - repeat_interval
    - max_repeats
    - cron_expression
    - execution_data
    - status (pending/paused/completed/failed/cancelled)
    """
    workspace_path = await _get_workspace_path(workspace_id)

    scheduler = await scheduler_manager.get_scheduler(workspace_id, workspace_path)
    task = await scheduler.storage.get_task(task_id)

    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")

    # 更新允许的字段
    allowed_fields = [
        "description",
        "schedule_type",
        "trigger_time",
        "repeat_interval",
        "max_repeats",
        "cron_expression",
        "execution_data",
        "status",
    ]

    for field in allowed_fields:
        if field in updates:
            if field == "schedule_type":
                task.schedule_type = ScheduleType(updates[field])
            elif field == "trigger_time":
                task.trigger_time = datetime.fromisoformat(updates[field])
            elif field == "status":
                task.status = TriggerStatus(updates[field])
            else:
                setattr(task, field, updates[field])

    # 更新时间戳
    task.updated_at = datetime.now(UTC)

    # 保存更新
    success = await scheduler.storage.save_task(task)

    if not success:
        raise HTTPException(
            status_code=500,
            detail="Failed to update scheduled task",
        )

    logger.info(f"Updated scheduled task {task_id}")

    return {
        "success": True,
        "task": task.to_dict(),
        "message": "定时任务更新成功",
    }


@router.delete("/{task_id}")
async def delete_scheduled_task(workspace_id: str, task_id: str):
    """删除定时任务"""
    workspace_path = await _get_workspace_path(workspace_id)

    scheduler = await scheduler_manager.get_scheduler(workspace_id, workspace_path)

    # 检查任务是否存在
    task = await scheduler.storage.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")

    # 删除任务
    success = await scheduler.storage.delete_task(task_id)

    if not success:
        raise HTTPException(
            status_code=500,
            detail="Failed to delete scheduled task",
        )

    logger.info(f"Deleted scheduled task {task_id}")

    return {
        "success": True,
        "message": "定时任务删除成功",
    }


@router.get("/{task_id}/executions")
async def get_task_executions(
    workspace_id: str,
    task_id: str,
    page: int = 1,
    page_size: int = 20,
):
    """获取定时任务的执行历史

    返回该定时任务触发的所有 conversation 记录，支持分页

    Args:
        workspace_id: workspace ID
        task_id: 任务 ID
        page: 页码（从1开始）
        page_size: 每页数量
    """
    # 验证分页参数
    if page < 1:
        raise HTTPException(status_code=400, detail="Page must be >= 1")
    if page_size < 1 or page_size > 100:
        raise HTTPException(status_code=400, detail="Page size must be between 1 and 100")

    # 获取 conversation 目录
    workspace_info = workspace_manager.get_workspace_by_id(workspace_id)
    if not workspace_info:
        raise HTTPException(
            status_code=404,
            detail=f"Workspace '{workspace_id}' not found.",
        )

    base_path = Path(workspace_info["path"])
    conversations_dir = base_path / ".dawei" / "conversations"

    if not conversations_dir.exists():
        return {
            "success": True,
            "task_id": task_id,
            "executions": [],
            "total": 0,
            "page": page,
            "page_size": page_size,
            "total_pages": 0,
        }

    # 查找所有相关的 conversation
    conversation_files = list(conversations_dir.glob("*.json"))
    executions = []

    for file_path in conversation_files:
        try:
            with file_path.open(encoding="utf-8") as f:
                conv_data = json.load(f)

            # 过滤出该定时任务的执行记录
            if (
                conv_data.get("task_type") == "scheduled"
                and conv_data.get("source_task_id") == task_id
            ):
                execution = {
                    "conversation_id": conv_data.get("id"),
                    "title": conv_data.get("title", ""),
                    "created_at": conv_data.get("createdAt"),
                    "updated_at": conv_data.get("updatedAt"),
                    "message_count": conv_data.get("messageCount", len(conv_data.get("messages", []))),
                    "repeat_count": conv_data.get("metadata", {}).get("repeat_count", 0),
                    "triggered_at": conv_data.get("metadata", {}).get("triggered_at"),
                }
                executions.append(execution)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to load conversation {file_path}: {e}")
            continue

    # 按触发时间排序（最新的在前）
    executions.sort(key=lambda x: x.get("triggered_at", ""), reverse=True)

    # 分页
    total = len(executions)
    total_pages = (total + page_size - 1) // page_size if total > 0 else 0
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    paginated_executions = executions[start_idx:end_idx]

    return {
        "success": True,
        "task_id": task_id,
        "executions": paginated_executions,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


@router.post("/{task_id}/pause")
async def pause_scheduled_task(workspace_id: str, task_id: str):
    """暂停定时任务"""
    workspace_path = await _get_workspace_path(workspace_id)

    scheduler = await scheduler_manager.get_scheduler(workspace_id, workspace_path)
    task = await scheduler.storage.get_task(task_id)

    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")

    # 更新状态为暂停
    task.status = TriggerStatus.PAUSED
    task.paused_at = datetime.now(UTC)

    # 保存更新
    success = await scheduler.storage.save_task(task)

    if not success:
        raise HTTPException(
            status_code=500,
            detail="Failed to pause scheduled task",
        )

    logger.info(f"Paused scheduled task {task_id}")

    return {
        "success": True,
        "message": "定时任务已暂停",
    }


@router.post("/{task_id}/resume")
async def resume_scheduled_task(workspace_id: str, task_id: str):
    """恢复定时任务"""
    workspace_path = await _get_workspace_path(workspace_id)

    scheduler = await scheduler_manager.get_scheduler(workspace_id, workspace_path)
    task = await scheduler.storage.get_task(task_id)

    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")

    # 更新状态为待执行
    task.status = TriggerStatus.PENDING
    task.resumed_at = datetime.now(UTC)

    # 保存更新
    success = await scheduler.storage.save_task(task)

    if not success:
        raise HTTPException(
            status_code=500,
            detail="Failed to resume scheduled task",
        )

    logger.info(f"Resumed scheduled task {task_id}")

    return {
        "success": True,
        "message": "定时任务已恢复",
    }


@router.post("/{task_id}/trigger")
async def trigger_scheduled_task(workspace_id: str, task_id: str):
    """手动触发定时任务

    立即执行定时任务，不改变原调度时间
    适用于待执行或已失败的任务
    """
    workspace_path = await _get_workspace_path(workspace_id)

    scheduler = await scheduler_manager.get_scheduler(workspace_id, workspace_path)
    task = await scheduler.storage.get_task(task_id)

    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")

    # 检查任务状态
    if task.status == TriggerStatus.TRIGGERED:
        raise HTTPException(
            status_code=400,
            detail="Task is currently running, cannot trigger again",
        )

    # 检查调度器是否运行
    active_workspaces = await scheduler_manager.get_active_workspaces()
    if workspace_id not in active_workspaces:
        raise HTTPException(
            status_code=400,
            detail="Scheduler is not active for this workspace. Please activate the workspace first.",
        )

    # 将任务加入执行队列
    await scheduler._execution_queue.put(task)

    logger.info(f"Manually triggered scheduled task {task_id}")

    return {
        "success": True,
        "message": "任务已触发执行",
    }
