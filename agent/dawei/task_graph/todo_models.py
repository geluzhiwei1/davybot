# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""TODO 列表相关的数据模型"""

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum


class TodoStatus(Enum):
    """TODO 状态枚举"""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


@dataclass
class TodoItem:
    """TODO 项数据模型

    Attributes:
        id: TODO 项的唯一标识符
        content: TODO 项的内容描述
        status: TODO 项的当前状态
        task_node_id: 关联的 TaskNode ID（用于自动同步）
        auto_update: 是否自动更新状态（默认 True）
        created_at: 创建时间戳
        updated_at: 更新时间戳

    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    content: str = ""
    status: TodoStatus = TodoStatus.PENDING

    # ✅ 新增字段：支持自动关联和更新
    task_node_id: str | None = None  # 关联的 TaskNode ID
    auto_update: bool = True  # 是否自动更新状态
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "id": self.id,
            "content": self.content,
            "status": self.status.value,
            "task_node_id": self.task_node_id,  # ✅ 序列化新字段
            "auto_update": self.auto_update,  # ✅ 序列化新字段
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TodoItem":
        """从字典创建实例"""
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            content=data.get("content", ""),
            status=TodoStatus(data.get("status", "pending")),
            task_node_id=data.get("task_node_id"),
            auto_update=data.get("auto_update", True),
            created_at=data.get("created_at", time.time()),
            updated_at=data.get("updated_at", time.time()),
        )

    @classmethod
    def create(
        cls,
        content: str,
        status: TodoStatus = TodoStatus.PENDING,
        task_node_id: str | None = None,
        auto_update: bool = True,
    ) -> "TodoItem":
        """创建新的 TODO 项

        Args:
            content: TODO 内容
            status: 初始状态
            task_node_id: 关联的 TaskNode ID
            auto_update: 是否自动更新状态

        Returns:
            TodoItem 实例

        """
        return cls(
            id=str(uuid.uuid4()),
            content=content,
            status=status,
            task_node_id=task_node_id,
            auto_update=auto_update,
            created_at=time.time(),
            updated_at=time.time(),
        )

    def update_timestamp(self):
        """更新 updated_at 时间戳"""
        self.updated_at = time.time()
