# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""任务节点类
新架构中的任务节点表示，使用ID引用避免循环依赖
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional

from dawei.entity.task_types import TaskStatus

from .task_node_data import TaskData

if TYPE_CHECKING:
    from .task_graph import TaskGraph
else:
    TaskGraph = Any  # type: ignore


@dataclass
class TaskNode:
    """任务节点类，表示任务图中的单个节点"""

    # 基础属性
    task_node_id: str
    data: TaskData

    # 关系管理 - 使用ID引用避免循环依赖
    parent_id: str | None = None
    child_ids: list[str] = field(default_factory=list)

    # 图引用：当前节点所属的图
    graph: Optional["TaskGraph"] = None
    # 子图：当前节点包含的独立子图
    sub_graph: Optional["TaskGraph"] = None

    # 时间戳
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self):
        """初始化后处理"""
        # 确保task_id一致
        if self.data.task_node_id != self.task_node_id:
            raise ValueError(
                f"Task ID mismatch: node.task_node_id={self.task_node_id}, data.task_node_id={self.data.task_node_id}",
            )

    @property
    def status(self) -> TaskStatus:
        """获取任务状态"""
        return self.data.status

    @property
    def description(self) -> str:
        """获取任务描述"""
        return self.data.description

    @property
    def mode(self) -> str:
        """获取任务模式"""
        return self.data.mode

    @property
    def context(self):
        """获取任务上下文"""
        return self.data.context

    @property
    def todos(self):
        """获取TODO列表"""
        return self.data.todos

    @property
    def metadata(self) -> dict[str, Any]:
        """获取元数据"""
        return self.data.metadata

    def is_root(self) -> bool:
        """判断是否为根节点"""
        return self.parent_id is None

    def has_parent(self) -> bool:
        """判断是否有父节点"""
        return self.parent_id is not None

    def has_children(self) -> bool:
        """判断是否有子节点"""
        return len(self.child_ids) > 0

    def add_child(self, child_id: str) -> None:
        """添加子节点ID"""
        if child_id not in self.child_ids:
            self.child_ids.append(child_id)
            self.updated_at = datetime.now(timezone.utc)

    def remove_child(self, child_id: str) -> bool:
        """移除子节点ID"""
        if child_id in self.child_ids:
            self.child_ids.remove(child_id)
            self.updated_at = datetime.now(timezone.utc)
            return True
        return False

    def set_parent(self, parent_id: str | None) -> None:
        """设置父节点ID"""
        self.parent_id = parent_id
        self.updated_at = datetime.now(timezone.utc)

    def update_data(self, **kwargs) -> None:
        """更新任务数据"""
        for key, value in kwargs.items():
            if hasattr(self.data, key):
                setattr(self.data, key, value)
        self.updated_at = datetime.now(timezone.utc)

    def update_status(self, status: TaskStatus) -> None:
        """更新任务状态"""
        self.data.update_status(status)
        self.updated_at = datetime.now(timezone.utc)

    def update_description(self, description: str) -> None:
        """更新任务描述"""
        self.data.update_description(description)
        self.updated_at = datetime.now(timezone.utc)

    def update_mode(self, mode: str) -> None:
        """更新任务模式"""
        self.data.update_mode(mode)
        self.updated_at = datetime.now(timezone.utc)

    def add_metadata(self, key: str, value: Any) -> None:
        """添加元数据"""
        self.data.add_metadata(key, value)
        self.updated_at = datetime.now(timezone.utc)

    def get_hierarchy_info(self) -> dict[str, Any]:
        """获取层级信息"""
        return {
            "task_node_id": self.task_node_id,
            "parent_id": self.parent_id,
            "child_ids": self.child_ids.copy(),
            "is_root": self.is_root(),
            "has_parent": self.has_parent(),
            "has_children": self.has_children(),
            "child_count": len(self.child_ids),
        }

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return {
            "task_node_id": self.task_node_id,
            "data": self.data.to_dict(),
            "parent_id": self.parent_id,
            "child_ids": self.child_ids.copy(),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "hierarchy": self.get_hierarchy_info(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskNode":
        """从字典创建实例"""
        created_at = datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(timezone.utc)
        updated_at = datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else datetime.now(timezone.utc)

        # 创建TaskData对象
        task_data = TaskData.from_dict(data["data"])

        return cls(
            task_node_id=data["task_node_id"],
            data=task_data,
            parent_id=data.get("parent_id"),
            child_ids=data.get("child_ids", []).copy(),
            created_at=created_at,
            updated_at=updated_at,
        )

    @classmethod
    def create_root(cls, task_node_id: str, description: str, mode: str, **kwargs) -> "TaskNode":
        """创建根节点"""
        task_data = TaskData(
            task_node_id=task_node_id,
            description=description,
            mode=mode,
            **kwargs,
        )

        return cls(task_node_id=task_node_id, data=task_data)

    @classmethod
    def create_child(
        cls,
        task_node_id: str,
        description: str,
        mode: str,
        parent_id: str,
        **kwargs,
    ) -> "TaskNode":
        """创建子节点"""
        task_data = TaskData(
            task_node_id=task_node_id,
            description=description,
            mode=mode,
            **kwargs,
        )

        return cls(task_node_id=task_node_id, data=task_data, parent_id=parent_id)
