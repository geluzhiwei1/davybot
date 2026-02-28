# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Timer/Scheduler Tools

定时任务管理工具
提供延迟执行、定时执行和重复执行功能
"""

import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta, timezone

from pydantic import BaseModel, Field

from dawei.entity.scheduled_task import ScheduledTask, ScheduleType, TriggerStatus
from dawei.logg.logging import get_logger
from dawei.tools.custom_base_tool import CustomBaseTool
from dawei.tools.scheduler import scheduler_manager


def _run_async(coro):
    """在现有事件循环中运行协程，或者创建新的事件循环

    Args:
        coro: 要运行的协程

    Returns:
        协程的返回值
    """
    try:
        asyncio.get_running_loop()
        # 已经在运行的事件循环中，创建 task 并等待
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result()
    except RuntimeError:
        # 没有运行的事件循环，使用 asyncio.run
        return asyncio.run(coro)


class TimerSetInput(BaseModel):
    """创建定时任务输入"""

    description: str = Field(..., description="任务描述")
    delay_seconds: int | None = Field(None, description="延迟秒数")
    execute_at: str | None = Field(None, description="执行时间(ISO格式)")
    repeat_interval: int | None = Field(None, description="重复间隔(秒)")
    max_repeats: int | None = Field(None, description="最大重复次数")
    cron: str | None = Field(None, description="Cron表达式 (如: '0 9 * * *' 每天9点)")
    execution_type: str = Field("message", description="执行类型: 仅支持 message")
    llm: str | None = Field(None, description="LLM 模型 (可选，覆盖默认值)")
    mode: str | None = Field(None, description="Agent 模式 (可选，覆盖默认值)")


class TimerInput(BaseModel):
    """Timer tool input schema - 支持所有操作"""

    action: str = Field(..., description="操作类型: set/cancel/list/check")
    set: TimerSetInput | None = Field(None, description="创建任务的参数 (action='set'时使用)")
    task_id: str | None = Field(None, description="任务ID (action='cancel'/'check'时使用)")


class TimerTool(CustomBaseTool):
    """定时任务工具

    支持以下操作:
    - set: 创建定时任务
    - cancel: 取消任务
    - list: 列出任务
    - check: 检查任务状态

    Examples:
    - timer(action='set', set={'description': 'Check status', 'delay_seconds': 60})
    - timer(action='cancel', task_id='timer_abc123')
    - timer(action='list')
    - timer(action='check', task_id='timer_abc123')

    """

    name: str = "timer"
    description: str = (
        "定时任务管理工具。\n"
        "set: 创建定时任务 - timer(action='set', set={'description': 'xxx', 'delay_seconds': 60})\n"
        "cancel: 取消任务 - timer(action='cancel', task_id='xxx')\n"
        "list: 列出任务 - timer(action='list')\n"
        "check: 检查任务 - timer(action='check', task_id='xxx')\n\n"
        "参数说明:\n"
        "- delay_seconds: 延迟执行的秒数\n"
        "- execute_at: 指定执行时间(ISO格式, 如 '2025-01-01T12:00:00')\n"
        "- repeat_interval: 重复间隔(秒)\n"
        "- max_repeats: 最大重复次数\n"
        "- cron: Cron表达式 (如 '0 9 * * *' 每天9点, '*/5 * * * *' 每5分钟)\n"
        "- llm: LLM 模型 (可选, 如 'deepseek/deepseek-chat', 覆盖 workspace 默认值)\n"
        "- mode: Agent 模式 (可选, 如 'orchestrator/plan/do/check/act', 覆盖 workspace 默认值)\n\n"
        "Cron表达式格式: 分 时 日 月 周 (如: '0 9 * * 1-5' 工作日每天9点)"
    )
    args_schema: type[BaseModel] = TimerInput

    def __init__(self):
        super().__init__()
        self.logger = get_logger(__name__)

    def _run(
        self,
        action: str,
        set: dict | None = None,
        task_id: str | None = None,
        **kwargs,
    ) -> str:
        """执行定时任务操作

        Args:
            action: 操作类型 (set/cancel/list/check)
            set: 创建任务的参数字典
            task_id: 任务ID (用于cancel/check操作)

        Returns:
            JSON格式的操作结果

        """
        try:
            # 检查scheduler_manager是否已初始化
            if not scheduler_manager.is_initialized():
                return json.dumps(
                    {
                        "status": "error",
                        "message": "Scheduler manager not initialized. Please start the server first.",
                    },
                    indent=2,
                )

            # 获取workspace上下文
            # Check both self.user_workspace (set by tool executor) and self.context.user_workspace
            workspace = None
            if hasattr(self, "user_workspace") and self.user_workspace:
                workspace = self.user_workspace
            elif self.context and hasattr(self.context, "user_workspace"):
                workspace = self.context.user_workspace

            if not workspace:
                return json.dumps(
                    {"status": "error", "message": "No workspace context available"},
                    indent=2,
                )

            workspace_id = workspace.workspace_info.id
            workspace_path = workspace.absolute_path  # UserWorkspace uses absolute_path

            if action == "set":
                return self._set_task(workspace_id, workspace_path, set or {})
            if action == "cancel":
                return self._cancel_task(workspace_id, workspace_path, task_id)
            if action == "list":
                return self._list_tasks(workspace_id, workspace_path)
            if action == "check":
                return self._check_task(workspace_id, workspace_path, task_id)
            return json.dumps(
                {
                    "status": "error",
                    "message": f"Unknown action: {action}. Valid actions: set, cancel, list, check",
                },
                indent=2,
            )

        except Exception as e:
            self.logger.error(f"Error executing timer tool: {e}", exc_info=True)
            return json.dumps({"status": "error", "message": f"Error: {e!s}"}, indent=2)

    def _set_task(self, workspace_id: str, workspace_path: str, params: dict) -> str:
        """创建定时任务"""
        try:
            # ✅ 使用 _run_async 包装异步操作
            return _run_async(self._set_task_async(workspace_id, workspace_path, params))
        except Exception as e:
            self.logger.error(f"Error in _set_task: {e}", exc_info=True)
            return json.dumps({"status": "error", "message": f"Error: {e!s}"}, indent=2)

    async def _set_task_async(self, workspace_id: str, workspace_path: str, params: dict) -> str:
        """异步创建定时任务"""
        description = params.get("description")
        if not description:
            return json.dumps({"status": "error", "message": "'description' is required"}, indent=2)

        delay = params.get("delay_seconds")
        execute_at_str = params.get("execute_at")
        cron_expression = params.get("cron")

        # 确定触发时间和类型
        if cron_expression:
            # 使用Cron表达式
            try:
                from croniter import croniter

                # 验证Cron表达式并计算第一次执行时间
                try:
                    cron = croniter(cron_expression, datetime.now(UTC))
                    trigger_time = cron.get_next(datetime)
                    schedule_type = ScheduleType.CRON
                except Exception as e:
                    return json.dumps(
                        {
                            "status": "error",
                            "message": f"Invalid cron expression '{cron_expression}': {e!s}\n"
                            "Expected format: 'minute hour day month weekday' (e.g., '0 9 * * *')",
                        },
                        indent=2,
                    )
            except ImportError:
                return json.dumps(
                    {
                        "status": "error",
                        "message": "croniter library not installed. Install with: pip install croniter",
                    },
                    indent=2,
                )
        elif execute_at_str:
            try:
                trigger_time = datetime.fromisoformat(execute_at_str)
                schedule_type = ScheduleType.AT_TIME
            except ValueError as e:
                return json.dumps(
                    {
                        "status": "error",
                        "message": f"Invalid execute_at format: {e}. Use ISO format like '2025-01-01T12:00:00'",
                    },
                    indent=2,
                )
        elif delay is not None:
            if delay < 0:
                return json.dumps(
                    {
                        "status": "error",
                        "message": "delay_seconds must be non-negative",
                    },
                    indent=2,
                )
            trigger_time = datetime.now(UTC) + timedelta(seconds=delay)
            schedule_type = ScheduleType.DELAY
        else:
            return json.dumps(
                {
                    "status": "error",
                    "message": "Either 'cron', 'delay_seconds' or 'execute_at' must be specified",
                },
                indent=2,
            )

        # 验证重复参数
        repeat_interval = params.get("repeat_interval")
        max_repeats = params.get("max_repeats")

        if repeat_interval is not None and repeat_interval <= 0:
            return json.dumps(
                {"status": "error", "message": "repeat_interval must be positive"},
                indent=2,
            )

        if max_repeats is not None and max_repeats <= 0:
            return json.dumps(
                {"status": "error", "message": "max_repeats must be positive"},
                indent=2,
            )

        # 创建任务
        execution_type = params.get("execution_type", "message")

        # 自动设置 execution_data（如果未提供且是 message 类型）
        execution_data = params.get("execution_data")
        if execution_type == "message" and not execution_data:
            # 将 description 作为默认消息
            execution_data = {"message": description}

        task = ScheduledTask(
            task_id=f"timer_{uuid.uuid4().hex[:8]}",
            workspace_id=workspace_id,
            description=description,
            schedule_type=schedule_type,
            trigger_time=trigger_time,
            repeat_interval=repeat_interval,
            max_repeats=max_repeats,
            cron_expression=cron_expression if schedule_type == ScheduleType.CRON else None,
            execution_type=execution_type,
            execution_data=execution_data,
            tags=params.get("tags", []),
            metadata=params.get("metadata"),
        )

        # 异步保存任务
        try:
            scheduler = await scheduler_manager.get_scheduler(workspace_id, workspace_path)
            await scheduler.storage.save_task(task)
            self.logger.info(f"Task {task.task_id} scheduled for {trigger_time.isoformat()}")
        except Exception as e:
            self.logger.error(f"Failed to save task {task.task_id}: {e}", exc_info=True)
            return json.dumps(
                {"status": "error", "message": f"Failed to save task: {e!s}"},
                indent=2,
            )

        return json.dumps(
            {
                "status": "success",
                "message": f"Task scheduled for {trigger_time.isoformat()}",
                "task": {
                    "task_id": task.task_id,
                    "description": task.description,
                    "trigger_time": task.trigger_time.isoformat(),
                    "schedule_type": task.schedule_type.value,
                    "repeat_interval": task.repeat_interval,
                    "max_repeats": task.max_repeats,
                    "cron_expression": task.cron_expression,
                    "execution_type": task.execution_type,
                },
            },
            indent=2,
        )

    def _cancel_task(self, workspace_id: str, workspace_path: str, task_id: str) -> str:
        """取消定时任务"""
        if not task_id:
            return json.dumps(
                {
                    "status": "error",
                    "message": "'task_id' is required for cancel action",
                },
                indent=2,
            )

        try:
            # ✅ 使用 _run_async 包装异步操作
            result = _run_async(self._cancel_task_async(workspace_id, workspace_path, task_id))
            return json.dumps(result, indent=2)
        except Exception as e:
            self.logger.error(f"Failed to cancel task {task_id}: {e}", exc_info=True)
            return json.dumps({"status": "error", "message": f"Error: {e!s}"}, indent=2)

    async def _cancel_task_async(self, workspace_id: str, workspace_path: str, task_id: str) -> dict:
        """异步取消任务"""
        scheduler = await scheduler_manager.get_scheduler(workspace_id, workspace_path)
        task = await scheduler.storage.get_task(task_id)

        if not task:
            return {"status": "error", "message": f"Task {task_id} not found"}

        # 更新状态为已取消
        task.status = TriggerStatus.CANCELLED
        await scheduler.storage.save_task(task)

        # 从缓存中移除
        if task_id in scheduler.storage._cache:
            del scheduler.storage._cache[task_id]

        return {
            "status": "success",
            "message": f"Task {task_id} cancelled",
            "task": {
                "task_id": task.task_id,
                "description": task.description,
                "status": task.status.value,
            },
        }

    def _list_tasks(self, workspace_id: str, workspace_path: str) -> str:
        """列出所有定时任务"""
        try:
            # ✅ 使用 _run_async 包装异步操作
            result = _run_async(self._list_tasks_async(workspace_id, workspace_path))
            return json.dumps(result, indent=2)
        except Exception as e:
            self.logger.error(f"Failed to list tasks: {e}", exc_info=True)
            return json.dumps({"status": "error", "message": f"Error: {e!s}"}, indent=2)

    async def _list_tasks_async(self, workspace_id: str, workspace_path: str) -> dict:
        """异步列出任务"""
        scheduler = await scheduler_manager.get_scheduler(workspace_id, workspace_path)
        tasks = await scheduler.storage.list_tasks()

        task_list = []
        for task in tasks:
            task_list.append(
                {
                    "task_id": task.task_id,
                    "description": task.description,
                    "trigger_time": task.trigger_time.isoformat(),
                    "status": task.status.value,
                    "schedule_type": task.schedule_type.value,
                    "repeat_interval": task.repeat_interval,
                    "max_repeats": task.max_repeats,
                    "repeat_count": task.repeat_count,
                    "cron_expression": task.cron_expression,
                    "created_at": task.created_at.isoformat(),
                },
            )

        return {
            "status": "success",
            "count": len(task_list),
            "tasks": task_list,
        }

    def _check_task(self, workspace_id: str, workspace_path: str, task_id: str) -> str:
        """检查任务状态"""
        if not task_id:
            return json.dumps(
                {
                    "status": "error",
                    "message": "'task_id' is required for check action",
                },
                indent=2,
            )

        try:
            # ✅ 使用 _run_async 包装异步操作
            result = _run_async(self._check_task_async(workspace_id, workspace_path, task_id))
            return json.dumps(result, indent=2)
        except Exception as e:
            self.logger.error(f"Failed to check task {task_id}: {e}", exc_info=True)
            return json.dumps({"status": "error", "message": f"Error: {e!s}"}, indent=2)

    async def _check_task_async(self, workspace_id: str, workspace_path: str, task_id: str) -> dict:
        """异步检查任务状态"""
        scheduler = await scheduler_manager.get_scheduler(workspace_id, workspace_path)
        task = await scheduler.storage.get_task(task_id)

        if not task:
            return {"status": "error", "message": f"Task {task_id} not found"}

        is_due = task.is_due()
        should_repeat = task.should_repeat()

        return {
            "status": "success",
            "task": {
                "task_id": task.task_id,
                "description": task.description,
                "trigger_time": task.trigger_time.isoformat(),
                "status": task.status.value,
                "schedule_type": task.schedule_type.value,
                "repeat_interval": task.repeat_interval,
                "max_repeats": task.max_repeats,
                "repeat_count": task.repeat_count,
                "cron_expression": task.cron_expression,
                "created_at": task.created_at.isoformat(),
                "triggered_at": (task.triggered_at.isoformat() if task.triggered_at else None),
                "last_error": task.last_error,
                "is_due": is_due,
                "should_repeat": should_repeat,
            },
        }


__all__ = [
    "TimerTool",
]
