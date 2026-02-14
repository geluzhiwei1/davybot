# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""任务执行器接口定义

定义了任务执行相关的抽象接口，包括任务调度、状态跟踪和结果收集等功能。
"""

from abc import ABC, abstractmethod
from typing import Any

# 使用已有的枚举定义
from dawei.entity.task_types import TaskStatus
from dawei.task_graph.task_node_data import TaskPriority


class ITaskExecutor(ABC):
    """任务执行器接口

    负责执行和管理各种类型的任务，包括任务调度、状态跟踪和结果收集。
    """

    @abstractmethod
    async def execute_task(
        self,
        task_id: str,
        task_data: dict[str, Any],
        priority: TaskPriority = TaskPriority.MEDIUM,
    ) -> dict[str, Any]:
        """执行指定任务

        Args:
            task_id: 任务唯一标识符
            task_data: 任务数据
            priority: 任务优先级

        Returns:
            任务执行结果

        """

    @abstractmethod
    async def pause_task(self, task_id: str) -> bool:
        """暂停任务

        Args:
            task_id: 任务ID

        Returns:
            是否成功暂停

        """

    @abstractmethod
    async def resume_task(self, task_id: str) -> bool:
        """恢复任务

        Args:
            task_id: 任务ID

        Returns:
            是否成功恢复

        """

    @abstractmethod
    async def cancel_task(self, task_id: str) -> bool:
        """取消任务

        Args:
            task_id: 任务ID

        Returns:
            是否成功取消

        """

    @abstractmethod
    def get_task_status(self, task_id: str) -> TaskStatus | None:
        """获取任务状态

        Args:
            task_id: 任务ID

        Returns:
            任务状态，如果任务不存在则返回None

        """

    @abstractmethod
    def list_running_tasks(self) -> list[str]:
        """列出所有正在运行的任务

        Returns:
            正在运行的任务ID列表

        """
