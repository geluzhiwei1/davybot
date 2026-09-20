# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Timer/Scheduler Tools

定时任务管理工具
提供延迟执行、定时执行和重复执行功能
"""

import json
import uuid
from datetime import datetime, timedelta, timezone
from dawei.core.datetime_compat import UTC

from pydantic import BaseModel, Field

from dawei.entity.scheduled_task import ScheduledTask, ScheduleType, TriggerStatus
from dawei.core.decorators import safe_tool_operation
from dawei.logg.logging import get_logger
from dawei.tools.custom_base_tool import CustomBaseTool
from dawei.tools.custom_tools.async_utils import run_async
from dawei.tools.scheduler import scheduler_manager


class TimerSetInput(BaseModel):
    """Input for creating a scheduled task."""

    description: str = Field(..., description="Human-readable description of the task to execute.")
    delay_seconds: int | None = Field(None, description="Number of seconds to wait before executing the task.")
    execute_at: str | None = Field(None, description="Absolute execution time in ISO format (e.g., '2025-01-01T12:00:00').")
    repeat_interval: int | None = Field(None, description="Interval in seconds between repeated executions.")
    max_repeats: int | None = Field(None, description="Maximum number of times the task can repeat.")
    cron: str | None = Field(None, description="Cron expression for scheduling (e.g., '0 9 * * *' for daily at 9am, '*/5 * * * *' for every 5 minutes).")
    execution_type: str = Field("message", description="Execution type. Currently only 'message' is supported.")
    llm: str | None = Field(None, description="LLM model name to use for execution (optional, overrides workspace default).")
    mode: str | None = Field(None, description="Agent mode for execution (e.g., 'orchestrator', 'pdca'; optional, overrides workspace default).")


class TimerInput(BaseModel):
    """Timer tool input schema."""

    action: str = Field(..., description="Operation type: 'set' to create a task, 'cancel' to cancel, 'list' to list all tasks, 'check' to check a task's status.")
    set: TimerSetInput | None = Field(None, description="Parameters for creating a task (used when action='set').")
    task_id: str | None = Field(None, description="Task ID to cancel or check (used when action='cancel' or action='check').")


class TimerTool(CustomBaseTool):
    """Scheduled task management tool.

    Supported operations:
    - set: Create a scheduled task
    - cancel: Cancel a task
    - list: List all tasks
    - check: Check task status

    Examples:
    - timer(action='set', set={'description': 'Check status', 'delay_seconds': 60})
    - timer(action='cancel', task_id='timer_abc123')
    - timer(action='list')
    - timer(action='check', task_id='timer_abc123')

    """

    name: str = "timer"
    description: str = (
        "Scheduled task management tool.\n"
        "set: Create a scheduled task - timer(action='set', set={'description': 'xxx', 'delay_seconds': 60})\n"
        "cancel: Cancel a task - timer(action='cancel', task_id='xxx')\n"
        "list: List all tasks - timer(action='list')\n"
        "check: Check task status - timer(action='check', task_id='xxx')\n\n"
        "Scheduling options (specify one):\n"
        "- delay_seconds: Seconds to wait before execution\n"
        "- execute_at: Absolute time in ISO format (e.g., '2025-01-01T12:00:00')\n"
        "- cron: Cron expression (e.g., '0 9 * * *' daily at 9am, '*/5 * * * *' every 5 min)\n\n"
        "Repeat options:\n"
        "- repeat_interval: Seconds between repeated executions\n"
        "- max_repeats: Maximum number of repetitions\n\n"
        "Optional overrides:\n"
        "- llm: LLM model name for execution (overrides workspace default)\n"
        "- mode: Agent PDCA mode for execution (e.g., 'orchestrator/plan/do/check/act'; overrides workspace default)\n\n"
        "Cron format: minute hour day month weekday (e.g., '0 9 * * 1-5' weekdays at 9am)"
    )
    args_schema: type[BaseModel] = TimerInput

    def __init__(self):
        super().__init__()
        self.logger = get_logger(__name__)

    @safe_tool_operation("timer", fallback_value="Error: Timer operation failed")
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
            return run_async(self._set_task_async(workspace_id, workspace_path, params))
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
                            "message": f"Invalid cron expression '{cron_expression}': {e!s}\nExpected format: 'minute hour day month weekday' (e.g., '0 9 * * *')",
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
            result = run_async(self._cancel_task_async(workspace_id, workspace_path, task_id))
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
            result = run_async(self._list_tasks_async(workspace_id, workspace_path))
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
            result = run_async(self._check_task_async(workspace_id, workspace_path, task_id))
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
