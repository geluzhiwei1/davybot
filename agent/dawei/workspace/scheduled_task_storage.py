# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Scheduled Task Storage

定时任务持久化存储层
负责定时任务的CRUD操作和持久化
"""

import logging
from pathlib import Path

from dawei.entity.scheduled_task import ScheduledTask
from dawei.workspace.persistence_manager import (
    ResourceType,
    WorkspacePersistenceManager,
)

logger = logging.getLogger(__name__)


class ScheduledTaskStorage:
    """定时任务存储"""

    def __init__(self, workspace_path: str):
        """初始化存储

        Args:
            workspace_path: workspace路径

        """
        self.workspace_path = Path(workspace_path)
        self.persistence = WorkspacePersistenceManager(str(workspace_path))
        self._cache: dict[str, ScheduledTask] = {}
        self._loaded = False

    async def _ensure_loaded(self, fail_on_error: bool = False) -> None:
        """加载任务到缓存 - 加载所有任务（包括已完成和失败的）

        Args:
            fail_on_error: 如果为True，加载失败时抛出异常（fast fail）

        Raises:
            RuntimeError: 当fail_on_error=True且有任务加载失败时

        """
        if self._loaded:
            return

        tasks_data = await self.persistence.list_resources(ResourceType.SCHEDULED_TASK)

        loaded_count = 0
        failed_tasks = []

        for task_data in tasks_data:
            try:
                task = ScheduledTask.from_dict(task_data)
                # ✅ 加载所有任务到缓存
                self._cache[task.task_id] = task
                loaded_count += 1
            except Exception as e:
                task_id = task_data.get("task_id", "unknown")
                failed_tasks.append(task_id)
                logger.error(
                    f"[SCHEDULER_STORAGE] Failed to load task {task_id}: {e}",
                    exc_info=True,
                )

        # ✅ Fast fail: 如果有任务加载失败，抛出异常
        if fail_on_error and failed_tasks:
            raise RuntimeError(
                f"Failed to load {len(failed_tasks)} scheduled tasks: {failed_tasks}. "
                f"Please check task data integrity in {self.workspace_path}"
            )

        self._loaded = True
        logger.info(
            f"[SCHEDULER_STORAGE] Loaded {loaded_count} scheduled tasks "
            f"(total files: {len(tasks_data)}, failed: {len(failed_tasks)})"
        )

    async def save_task(self, task: ScheduledTask) -> bool:
        """保存任务

        Args:
            task: 要保存的任务

        Returns:
            是否保存成功

        """
        await self._ensure_loaded()

        success = await self.persistence.save_resource(
            ResourceType.SCHEDULED_TASK,
            task.task_id,
            task.to_dict(),
        )

        if success:
            self._cache[task.task_id] = task
            logger.debug(f"[SCHEDULER_STORAGE] Saved task {task.task_id}")
        else:
            logger.error(f"[SCHEDULER_STORAGE] Failed to save task {task.task_id}")

        return success

    async def get_task(self, task_id: str) -> ScheduledTask | None:
        """获取任务

        Args:
            task_id: 任务ID

        Returns:
            任务对象,不存在则返回None

        """
        await self._ensure_loaded()
        return self._cache.get(task_id)

    async def list_tasks(self) -> list[ScheduledTask]:
        """列出所有任务

        Returns:
            任务列表

        """
        await self._ensure_loaded()
        return list(self._cache.values())

    async def delete_task(self, task_id: str) -> bool:
        """删除任务

        Args:
            task_id: 任务ID

        Returns:
            是否删除成功

        """
        await self._ensure_loaded()

        success = await self.persistence.delete_resource(ResourceType.SCHEDULED_TASK, task_id)

        if success and task_id in self._cache:
            del self._cache[task_id]
            logger.debug(f"[SCHEDULER_STORAGE] Deleted task {task_id}")

        return success

    async def get_due_tasks(self) -> list[ScheduledTask]:
        """获取到期任务

        Returns:
            到期任务列表

        """
        await self._ensure_loaded()
        return [t for t in self._cache.values() if t.is_due()]

    async def get_pending_tasks(self) -> list[ScheduledTask]:
        """获取待处理任务

        Returns:
            待处理任务列表

        """
        await self._ensure_loaded()
        return [t for t in self._cache.values() if t.status.value == "pending"]

    async def clear_cache(self) -> None:
        """清空缓存"""
        self._cache.clear()
        self._loaded = False


__all__ = [
    "ScheduledTaskStorage",
]
