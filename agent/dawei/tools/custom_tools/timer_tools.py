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


class TimerSetInput(BaseModel):
    """创建定时任务输入"""

    description: str = Field(..., description="任务描述")
    delay_seconds: int | None = Field(None, description="延迟秒数")
    execute_at: str | None = Field(None, description="执行时间(ISO格式)")
    repeat_interval: int | None = Field(None, description="重复间隔(秒)")
    max_repeats: int | None = Field(None, description="最大重复次数")
    execution_type: str = Field("message", description="执行类型: message/tool/agent")


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
        "- execution_type: 执行类型(message/tool/agent, 默认message)"
    )
    args_schema: type[BaseModel] = TimerInput

    def __init__(self):
        super().__init__()
        self.logger = get_logger(__name__)

    def _run_async_safely(self, coro):
        """安全地在同步上下文中运行异步函数

        Args:
            coro: 协程对象

        Returns:
            协程的返回值

        """
        try:
            # 尝试获取当前运行的事件循环
            loop = asyncio.get_running_loop()
            # 如果有正在运行的事件循环，创建任务并在后台运行
            # 对于需要返回值的操作，这种方式不合适
            # 因此我们使用 asyncio.run() 在新循环中运行
            # 注意: 这可能会在有运行循环时抛出 RuntimeError
        except RuntimeError:
            pass

        # 创建新的事件循环运行协程
        try:
            return asyncio.run(coro)
        except RuntimeError as e:
            # 如果已经有运行的事件循环，使用 run_coroutine_threadsafe
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    future = asyncio.run_coroutine_threadsafe(coro, loop)
                    return future.result(timeout=10)
            except Exception:
                raise e

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
        description = params.get("description")
        if not description:
            return json.dumps({"status": "error", "message": "'description' is required"}, indent=2)

        delay = params.get("delay_seconds")
        execute_at_str = params.get("execute_at")

        # 确定触发时间和类型
        if execute_at_str:
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
                    "message": "Either 'delay_seconds' or 'execute_at' must be specified",
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
        task = ScheduledTask(
            task_id=f"timer_{uuid.uuid4().hex[:8]}",
            workspace_id=workspace_id,
            description=description,
            schedule_type=schedule_type,
            trigger_time=trigger_time,
            repeat_interval=repeat_interval,
            max_repeats=max_repeats,
            execution_type=params.get("execution_type", "message"),
            execution_data=params.get("execution_data"),
            tags=params.get("tags", []),
            metadata=params.get("metadata"),
        )

        # 异步保存任务 - fire and forget
        async def save_and_schedule():
            try:
                scheduler = await scheduler_manager.get_scheduler(workspace_id, workspace_path)
                await scheduler.storage.save_task(task)
                self.logger.info(f"Task {task.task_id} scheduled for {trigger_time.isoformat()}")
            except Exception as e:
                self.logger.error(f"Failed to save task {task.task_id}: {e}", exc_info=True)

        # 使用后台任务保存
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 在运行的事件循环中创建后台任务
                asyncio.create_task(save_and_schedule())
            else:
                # 如果没有运行的事件循环，运行一次
                loop.run_until_complete(save_and_schedule())
        except RuntimeError:
            # 如果没有事件循环，创建新的
            asyncio.run(save_and_schedule())

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

        async def do_cancel():
            try:
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
            except Exception as e:
                self.logger.error(f"Failed to cancel task {task_id}: {e}", exc_info=True)
                return {"status": "error", "message": f"Error cancelling task: {e!s}"}

        try:
            # Try to detect if we're in an async context
            try:
                asyncio.get_running_loop()
                # We're in a running event loop, use asyncio.ensure_future
                # But since _run is synchronous, we need to use a different approach
                # Create a new event loop in a thread for blocking operations
                import threading

                result_container = []
                exception_container = []

                def run_in_new_loop():
                    try:
                        new_loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(new_loop)
                        try:
                            result = new_loop.run_until_complete(do_cancel())
                            result_container.append(result)
                        finally:
                            new_loop.close()
                    except Exception as e:
                        exception_container.append(e)

                thread = threading.Thread(target=run_in_new_loop)
                thread.start()
                thread.join(timeout=5)

                if exception_container:
                    raise exception_container[0]
                if result_container:
                    return json.dumps(result_container[0], indent=2)
                return json.dumps({"status": "error", "message": "Timeout"}, indent=2)

            except RuntimeError:
                # No running loop, use asyncio.run
                result = asyncio.run(do_cancel())
                return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": f"Error: {e!s}"}, indent=2)

    def _list_tasks(self, workspace_id: str, workspace_path: str) -> str:
        """列出所有定时任务"""

        async def do_list():
            try:
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
                            "created_at": task.created_at.isoformat(),
                        },
                    )

                return {
                    "status": "success",
                    "count": len(task_list),
                    "tasks": task_list,
                }
            except Exception as e:
                self.logger.error(f"Failed to list tasks: {e}", exc_info=True)
                return {"status": "error", "message": f"Error listing tasks: {e!s}"}

        try:
            # Try to detect if we're in an async context
            try:
                asyncio.get_running_loop()
                # We're in a running event loop, use thread-based approach
                import threading

                result_container = []
                exception_container = []

                def run_in_new_loop():
                    try:
                        new_loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(new_loop)
                        try:
                            result = new_loop.run_until_complete(do_list())
                            result_container.append(result)
                        finally:
                            new_loop.close()
                    except Exception as e:
                        exception_container.append(e)

                thread = threading.Thread(target=run_in_new_loop)
                thread.start()
                thread.join(timeout=5)

                if exception_container:
                    raise exception_container[0]
                if result_container:
                    return json.dumps(result_container[0], indent=2)
                return json.dumps({"status": "error", "message": "Timeout"}, indent=2)

            except RuntimeError:
                # No running loop, use asyncio.run
                result = asyncio.run(do_list())
                return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": f"Error: {e!s}"}, indent=2)

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

        async def do_check():
            try:
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
                        "created_at": task.created_at.isoformat(),
                        "triggered_at": (task.triggered_at.isoformat() if task.triggered_at else None),
                        "last_error": task.last_error,
                        "is_due": is_due,
                        "should_repeat": should_repeat,
                    },
                }
            except Exception as e:
                self.logger.error(f"Failed to check task {task_id}: {e}", exc_info=True)
                return {"status": "error", "message": f"Error checking task: {e!s}"}

        try:
            # Try to detect if we're in an async context
            try:
                asyncio.get_running_loop()
                # We're in a running event loop, use thread-based approach
                import threading

                result_container = []
                exception_container = []

                def run_in_new_loop():
                    try:
                        new_loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(new_loop)
                        try:
                            result = new_loop.run_until_complete(do_check())
                            result_container.append(result)
                        finally:
                            new_loop.close()
                    except Exception as e:
                        exception_container.append(e)

                thread = threading.Thread(target=run_in_new_loop)
                thread.start()
                thread.join(timeout=5)

                if exception_container:
                    raise exception_container[0]
                if result_container:
                    return json.dumps(result_container[0], indent=2)
                return json.dumps({"status": "error", "message": "Timeout"}, indent=2)

            except RuntimeError:
                # No running loop, use asyncio.run
                result = asyncio.run(do_check())
                return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": f"Error: {e!s}"}, indent=2)


__all__ = [
    "TimerTool",
]
