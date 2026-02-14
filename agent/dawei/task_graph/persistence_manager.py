# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""TaskGraph 持久化管理器
自动监听任务图事件并异步保存到文件系统

设计原则：
1. 事件驱动：监听任务图事件，自动触发保存
2. 异步保存：不阻塞主流程
3. 去重机制：相同资源短时间内只保存一次
4. 错误隔离：保存失败不影响主流程
"""

import asyncio
import contextlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dawei.core.events import CORE_EVENT_BUS, emit_typed_event
from dawei.logg.logging import get_logger
from dawei.workspace.persistence_manager import WorkspacePersistenceManager


class TaskGraphPersistenceManager:
    """TaskGraph 自动持久化管理器

    职责：
    1. 监听任务图事件（创建、更新、状态变化）
    2. 异步保存到文件系统
    3. 管理保存队列和去重
    4. 错误处理和重试

    使用方式：
        persistence_manager = TaskGraphPersistenceManager(
            workspace_path="/path/to/workspace",
            event_bus=event_bus
        )
        await persistence_manager.start()

        # ... 任务图操作会自动触发保存 ...

        await persistence_manager.stop()
    """

    def __init__(self, workspace_path: str, event_bus=None, debounce_seconds: float = 1.0):
        """初始化持久化管理器

        Args:
            workspace_path: 工作区路径
            event_bus: 事件总线（默认使用 CORE_EVENT_BUS）
            debounce_seconds: 防抖时间（秒），相同资源在此时间内只保存一次

        """
        self.workspace_path = Path(workspace_path)
        self.event_bus = event_bus or CORE_EVENT_BUS
        self.persistence_manager = WorkspacePersistenceManager(str(self.workspace_path))
        self.logger = get_logger(__name__)

        # 保存队列和去重
        self._save_queue: asyncio.Queue = asyncio.Queue()
        self._pending_saves: set[str] = set()
        self._save_task: asyncio.Task | None = None
        self._debounce_seconds = debounce_seconds

        # 统计信息
        self._save_count = 0
        self._error_count = 0
        self._last_save_time: datetime | None = None

        # 运行状态
        self._started = False

    async def start(self):
        """启动持久化服务"""
        if self._started:
            self.logger.warning("Persistence manager already started")
            return

        try:
            # 注册事件监听器
            self._setup_event_listeners()

            # 启动后台保存任务
            self._save_task = asyncio.create_task(self._save_loop())
            self._started = True

            self.logger.info(
                f"TaskGraph persistence manager started for workspace: {self.workspace_path}, debounce={self._debounce_seconds}s",
            )

        except Exception as e:
            self.logger.error(f"Failed to start persistence manager: {e}", exc_info=True)
            raise

    def _setup_event_listeners(self):
        """设置事件监听器"""
        from dawei.core.events import TaskEventType

        # 监听任务图创建事件
        self.event_bus.add_handler(TaskEventType.TASK_GRAPH_CREATED, self._on_task_graph_created)

        # 监听任务图更新事件
        self.event_bus.add_handler(TaskEventType.TASK_GRAPH_UPDATED, self._on_task_graph_updated)

        # 监听任务状态变化事件（触发整个任务图保存）
        self.event_bus.add_handler(TaskEventType.STATE_CHANGED, self._on_state_changed)

        self.logger.debug("Event listeners registered")

    async def _on_task_graph_created(self, event: Any):
        """TaskGraph 创建事件处理"""
        try:
            data = self._extract_event_data(event)
            task_graph_id = data.get("task_graph_id")

            if task_graph_id:
                await self._queue_save("task_graph", task_graph_id)
                self.logger.info(f"Queued save for new task graph: {task_graph_id}")

        except Exception as e:
            self.logger.error(f"Error handling TASK_GRAPH_CREATED event: {e}", exc_info=True)

    async def _on_task_graph_updated(self, event: Any):
        """TaskGraph 更新事件处理"""
        try:
            data = self._extract_event_data(event)
            task_graph_id = data.get("task_graph_id")

            if task_graph_id:
                await self._queue_save("task_graph", task_graph_id)
                self.logger.debug(f"Queued save for updated task graph: {task_graph_id}")

        except Exception as e:
            self.logger.error(f"Error handling TASK_GRAPH_UPDATED event: {e}", exc_info=True)

    async def _on_state_changed(self, event: Any):
        """任务状态变化事件处理（触发整个任务图保存）"""
        try:
            data = self._extract_event_data(event)
            # 从状态变化事件中获取 task_graph_id
            # 可能需要从上下文中推断或使用 task_id 查找
            task_graph_id = data.get("task_graph_id")

            # 如果没有直接提供 task_graph_id，可以尝试其他方式获取
            if not task_graph_id:
                # 可能需要从 UserWorkspace 获取
                # 这里暂时跳过，等待其他事件触发保存
                return

            await self._queue_save("task_graph", task_graph_id)
            self.logger.debug(f"Queued save for task graph on state change: {task_graph_id}")

        except Exception as e:
            self.logger.error(f"Error handling STATE_CHANGED event: {e}", exc_info=True)

    def _extract_event_data(self, event: Any) -> dict[str, Any]:
        """提取事件数据（兼容不同的事件格式）"""
        try:
            # 尝试从强类型事件中提取
            if hasattr(event, "data") and hasattr(event.data, "get_event_data"):
                return event.data.get_event_data()
            # 从普通事件中提取
            if hasattr(event, "data"):
                return event.data if isinstance(event.data, dict) else {}
            # 事件本身就是数据
            if isinstance(event, dict):
                return event
            return {}
        except Exception as e:
            self.logger.warning(f"Error extracting event data: {e}")
            return {}

    async def _queue_save(self, resource_type: str, resource_id: str):
        """队列化保存请求（带防抖去重）"""
        key = f"{resource_type}:{resource_id}"

        # 如果已经在待保存队列中，跳过
        if key in self._pending_saves:
            self.logger.debug(f"Save already pending for {key}, skipping duplicate request")
            return

        # 添加到待保存集合和队列
        self._pending_saves.add(key)
        await self._save_queue.put((resource_type, resource_id, key))

        self.logger.debug(f"Queued save request: {key}")

    async def _save_loop(self):
        """后台保存循环"""
        self.logger.info("Save loop started")

        try:
            while True:
                try:
                    # 从队列获取保存请求
                    resource_type, resource_id, key = await self._save_queue.get()

                    # 防抖：等待一小段时间，看看是否有更多更新
                    await asyncio.sleep(self._debounce_seconds)

                    # 执行保存
                    await self._perform_save(resource_type, resource_id)

                    # 从待保存集合移除
                    self._pending_saves.discard(key)

                    # 更新统计
                    self._save_count += 1
                    self._last_save_time = datetime.now(timezone.utc)

                    self.logger.debug(
                        f"Save completed: {key} (total: {self._save_count}, errors: {self._error_count})",
                    )

                except asyncio.CancelledError:
                    self.logger.info("Save loop cancelled")
                    break
                except Exception as e:
                    self.logger.error(f"Error in save loop iteration: {e}", exc_info=True)
                    self._error_count += 1
                    # 从待保存集合移除，避免阻塞后续保存
                    self._pending_saves.discard(key)

        except Exception as e:
            self.logger.error(f"Fatal error in save loop: {e}", exc_info=True)

    async def _perform_save(self, resource_type: str, resource_id: str):
        """执行实际的保存操作"""
        try:
            if resource_type == "task_graph":
                await self._save_task_graph(resource_id)
            else:
                self.logger.warning(f"Unknown resource type: {resource_type}")

        except Exception as e:
            self.logger.error(f"Failed to save {resource_type} {resource_id}: {e}", exc_info=True)
            # 不重新抛出异常，避免中断保存循环

    async def _save_task_graph(self, task_graph_id: str):
        """触发任务图保存

        注意：这里通过事件总线发送请求，让 UserWorkspace 处理实际保存
        因为 TaskGraph 实例在 UserWorkspace 中维护
        """
        try:
            from dawei.core.events import TaskEventType

            # 通过事件总线请求持久化（使用枚举）
            await emit_typed_event(
                TaskEventType.PERSIST_TASK_GRAPH,
                {
                    "task_graph_id": task_graph_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                task_id=task_graph_id,
            )

            self.logger.debug(f"Triggered save for task graph: {task_graph_id}")

        except Exception as e:
            self.logger.error(
                f"Error triggering task graph save for {task_graph_id}: {e}",
                exc_info=True,
            )
            raise

    async def stop(self):
        """停止持久化服务"""
        if not self._started:
            self.logger.warning("Persistence manager not started")
            return

        try:
            # 1. 先等待队列中的保存完成（在取消任务之前）
            timeout = 5.0  # 5秒超时
            start_time = datetime.now(timezone.utc)

            while self._pending_saves and (datetime.now(timezone.utc) - start_time).total_seconds() < timeout:
                self.logger.info(
                    f"Waiting for {len(self._pending_saves)} pending saves to complete...",
                )
                await asyncio.sleep(0.5)

            if self._pending_saves:
                self.logger.warning(f"Stop timeout: {len(self._pending_saves)} saves still pending")

            # 2. 取消后台任务（在等待完成之后）
            if self._save_task and not self._save_task.done():
                self._save_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._save_task

            self._started = False

            self.logger.info(
                f"TaskGraph persistence manager stopped. Total saves: {self._save_count}, errors: {self._error_count}",
            )

        except Exception as e:
            self.logger.error(f"Error stopping persistence manager: {e}", exc_info=True)

    async def force_save(self, task_graph_id: str):
        """强制立即保存指定任务图（同步等待完成）"""
        await self._queue_save("task_graph", task_graph_id)

        # 等待保存完成
        key = f"task_graph:{task_graph_id}"
        timeout = 10.0  # 10秒超时
        start_time = datetime.now(timezone.utc)

        while key in self._pending_saves and (datetime.now(timezone.utc) - start_time).total_seconds() < timeout:
            await asyncio.sleep(0.1)

        if key in self._pending_saves:
            raise TimeoutError(f"Force save timeout for task graph: {task_graph_id}")

        self.logger.info(f"Force save completed for task graph: {task_graph_id}")

    def get_stats(self) -> dict[str, Any]:
        """获取统计信息"""
        return {
            "started": self._started,
            "total_saves": self._save_count,
            "error_count": self._error_count,
            "pending_saves": len(self._pending_saves),
            "last_save_time": self._last_save_time.isoformat() if self._last_save_time else None,
            "debounce_seconds": self._debounce_seconds,
            "queue_size": self._save_queue.qsize() if self._save_queue else 0,
        }
