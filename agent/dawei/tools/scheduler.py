# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Scheduler Engine and Manager

定时任务调度引擎和全局管理器
采用 Server 级调度器架构，实现全局单例管理
"""

import asyncio
import contextlib
import logging
from datetime import UTC, datetime, timezone
from pathlib import Path

from dawei.core.events import SimpleEventBus, TaskEventType
from dawei.entity.scheduled_task import ScheduledTask, TriggerStatus
from dawei.workspace.scheduled_task_storage import ScheduledTaskStorage

logger = logging.getLogger(__name__)


class SchedulerEngine:
    """单 workspace 调度引擎

    负责单个 workspace 的任务调度和执行
    """

    def __init__(self, workspace_id: str, workspace_path: str, event_bus: SimpleEventBus):
        """初始化调度引擎

        Args:
            workspace_id: workspace ID
            workspace_path: workspace 路径
            event_bus: 事件总线

        """
        self.workspace_id = workspace_id
        self.workspace_path = Path(workspace_path)
        self.event_bus = event_bus  # 🔴 修复：使用独立的 event_bus

        self.storage = ScheduledTaskStorage(str(workspace_path))

        self._running = False
        self._check_interval = 1.0
        self._check_task: asyncio.Task | None = None

        self._execution_queue: asyncio.Queue = asyncio.Queue()
        self._max_concurrent = 3
        self._workers: list[asyncio.Task] = []

    async def start(self) -> None:
        """启动调度器"""
        if self._running:
            logger.warning(
                f"[SCHEDULER] Scheduler already running for workspace {self.workspace_id}",
            )
            return

        self._running = True
        await self.storage._ensure_loaded()

        self._check_task = asyncio.create_task(self._check_loop())

        for i in range(self._max_concurrent):
            worker = asyncio.create_task(self._worker(f"worker-{i}"))
            self._workers.append(worker)

        logger.info(f"[SCHEDULER] Started for workspace {self.workspace_id}")

    async def stop(self) -> None:
        """停止调度器"""
        if not self._running:
            return

        self._running = False

        # Cancel check task
        if self._check_task and not self._check_task.done():
            self._check_task.cancel()
            with contextlib.suppress(TimeoutError, asyncio.CancelledError, RuntimeError):
                await asyncio.wait_for(self._check_task, timeout=1.0)

        # Cancel workers
        for worker in self._workers:
            if not worker.done():
                worker.cancel()

        # Wait for workers to finish
        if self._workers:
            with contextlib.suppress(TimeoutError, RuntimeError):
                await asyncio.wait_for(
                    asyncio.gather(*self._workers, return_exceptions=True),
                    timeout=2.0,
                )

        self._workers.clear()
        logger.info(f"[SCHEDULER] Stopped for workspace {self.workspace_id}")

    async def _check_loop(self) -> None:
        """主检查循环 - 每秒检查到期任务"""
        while self._running:
            try:
                due_tasks = await self.storage.get_due_tasks()
                for task in due_tasks:
                    await self._execution_queue.put(task)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[SCHEDULER] Check loop error: {e}", exc_info=True)

            await asyncio.sleep(self._check_interval)

    async def _worker(self, name: str) -> None:
        """工作线程 - 从队列中获取任务并执行

        Args:
            name: 工作线程名称

        """
        while self._running:
            try:
                task: ScheduledTask = await self._execution_queue.get()
                await self._execute_task(task)
                self._execution_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[SCHEDULER] Worker {name} error: {e}", exc_info=True)

    async def _execute_task(self, task: ScheduledTask) -> None:
        """执行定时任务

        Args:
            task: 要执行的任务

        """
        try:
            # 更新任务状态
            task.status = TriggerStatus.TRIGGERED
            task.triggered_at = datetime.now(UTC)
            await self.storage.save_task(task)

            # 发出触发事件
            await self.event_bus.publish(
                TaskEventType.TIMER_TRIGGERED,
                {
                    "task_id": task.task_id,
                    "description": task.description,
                    "workspace_id": task.workspace_id,
                    "execution_type": task.execution_type,
                    "execution_data": task.execution_data,
                    "repeat_count": task.repeat_count,
                },
                task.task_id,
                "scheduler",
            )

            # 根据执行类型处理
            if task.execution_type == "message":
                logger.info(f"[SCHEDULER] Message task triggered: {task.description}")
            elif task.execution_type == "tool":
                logger.info(f"[SCHEDULER] Tool task: {task.execution_data}")
            elif task.execution_type == "agent":
                logger.info(f"[SCHEDULER] Agent task: {task.description}")
            else:
                logger.warning(f"[SCHEDULER] Unknown execution type: {task.execution_type}")

            # 处理重复
            if task.should_repeat():
                task.schedule_next()
                await self.storage.save_task(task)
                logger.info(
                    f"[SCHEDULER] Task {task.task_id} rescheduled for {task.trigger_time.isoformat()}",
                )
            else:
                task.status = TriggerStatus.COMPLETED
                await self.storage.save_task(task)

                # 发出完成事件
                await self.event_bus.publish(
                    TaskEventType.TIMER_COMPLETED,
                    {
                        "task_id": task.task_id,
                        "description": task.description,
                        "workspace_id": task.workspace_id,
                    },
                    task.task_id,
                    "scheduler",
                )
                logger.info(f"[SCHEDULER] Task {task.task_id} completed")

        except Exception as e:
            logger.error(f"[SCHEDULER] Failed to execute task {task.task_id}: {e}", exc_info=True)
            task.status = TriggerStatus.FAILED
            task.last_error = str(e)
            await self.storage.save_task(task)

            # 发出失败事件
            try:
                await self.event_bus.publish(
                    TaskEventType.TIMER_FAILED,
                    {
                        "task_id": task.task_id,
                        "description": task.description,
                        "workspace_id": task.workspace_id,
                        "error": str(e),
                    },
                    task.task_id,
                    "scheduler",
                )
            except Exception as event_error:
                logger.exception(f"[SCHEDULER] Failed to publish TIMER_FAILED event: {event_error}")


class SchedulerManager:
    """全局调度管理器 (单例)

    管理所有 workspace 的调度器
    """

    def __init__(self):
        self._engines: dict[str, SchedulerEngine] = {}
        self._lock = asyncio.Lock()
        self._initialized = False
        self._event_bus = SimpleEventBus()  # 🔴 修复：创建独立的 event_bus 给 scheduler 使用

    async def initialize(self) -> None:
        """初始化（在 server lifespan 启动时调用）"""
        if self._initialized:
            logger.warning("[SCHEDULER] Manager already initialized")
            return

        self._initialized = True
        logger.info("[SCHEDULER] Manager initialized")

    async def shutdown(self) -> None:
        """关闭（在 server lifespan 关闭时调用）"""
        async with self._lock:
            for workspace_id, engine in list(self._engines.items()):
                try:
                    await engine.stop()
                except Exception as e:
                    logger.error(
                        f"[SCHEDULER] Error stopping engine for {workspace_id}: {e}",
                        exc_info=True,
                    )
            self._engines.clear()

        self._initialized = False
        logger.info("[SCHEDULER] Manager shutdown")

    async def get_scheduler(self, workspace_id: str, workspace_path: str) -> SchedulerEngine:
        """获取或创建 workspace 调度器

        Args:
            workspace_id: workspace ID
            workspace_path: workspace 路径

        Returns:
            SchedulerEngine 实例

        """
        async with self._lock:
            if workspace_id not in self._engines:
                engine = SchedulerEngine(workspace_id, workspace_path, self._event_bus)  # 🔴 修复：传递 event_bus
                await engine.start()
                self._engines[workspace_id] = engine
                logger.info(f"[SCHEDULER] Created scheduler for workspace {workspace_id}")
            return self._engines[workspace_id]

    async def remove_workspace(self, workspace_id: str) -> None:
        """移除 workspace（当 workspace 关闭时）

        Args:
            workspace_id: workspace ID

        """
        async with self._lock:
            if workspace_id in self._engines:
                await self._engines[workspace_id].stop()
                del self._engines[workspace_id]
                logger.info(f"[SCHEDULER] Removed scheduler for workspace {workspace_id}")

    def is_initialized(self) -> bool:
        """检查管理器是否已初始化"""
        return self._initialized

    async def get_active_workspaces(self) -> list[str]:
        """获取活跃的 workspace ID 列表"""
        async with self._lock:
            return list(self._engines.keys())


# 全局单例
scheduler_manager = SchedulerManager()


__all__ = [
    "SchedulerEngine",
    "SchedulerManager",
    "scheduler_manager",
]
