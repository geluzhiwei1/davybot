# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""任务数据模型
新架构中的基础数据类，职责单一，类型安全
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone
from enum import Enum
from typing import Any

from dawei.entity.task_types import TaskStatus

from .todo_models import TodoItem


class TaskPriority(Enum):
    """任务优先级枚举"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class TaskContext:
    """任务上下文数据模型"""

    # 基础上下文信息
    user_id: str
    session_id: str
    message_id: str
    workspace_path: str | None = None

    # 任务相关上下文
    parent_context: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    # 文件和资源
    task_files: list[str] = field(default_factory=list)
    task_images: list[str] = field(default_factory=list)

    # 时间戳
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return {
            "user_id": self.user_id,
            "session_id": self.session_id,
            "message_id": self.message_id,
            "workspace_path": self.workspace_path,
            "parent_context": self.parent_context,
            "metadata": self.metadata,
            "task_files": self.task_files,
            "task_images": self.task_images,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskContext":
        """从字典创建实例"""
        created_at = datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(UTC)
        updated_at = datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else datetime.now(UTC)

        return cls(
            user_id=data["user_id"],
            session_id=data["session_id"],
            message_id=data["message_id"],
            workspace_path=data.get("workspace_path"),
            parent_context=data.get("parent_context"),
            metadata=data.get("metadata", {}),
            task_files=data.get("task_files", []),
            task_images=data.get("task_images", []),
            created_at=created_at,
            updated_at=updated_at,
        )

    def merge(self, updates: dict[str, Any]) -> None:
        """合并更新"""
        for key, value in updates.items():
            if hasattr(self, key):
                setattr(self, key, value)
        self.updated_at = datetime.now(UTC)


from dawei.entity.user_input_message import UserInputMessage


@dataclass
class TaskData:
    """任务数据类，封装任务的基本信息"""

    # 基础标识
    task_node_id: str
    description: UserInputMessage
    mode: str

    # 状态信息
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.MEDIUM

    # 上下文信息
    context: TaskContext = field(
        default_factory=lambda: TaskContext(user_id="", session_id="", message_id=""),
    )

    # TODO 列表
    todos: list[TodoItem] = field(default_factory=list)

    # 元数据
    metadata: dict[str, Any] = field(default_factory=dict)

    # 时间戳
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self):
        """初始化后处理"""
        # 确保时间戳一致
        if self.created_at == self.updated_at:
            self.updated_at = self.created_at

    def update_description(self, description: str) -> None:
        """更新任务描述"""
        self.description = description
        self.updated_at = datetime.now(UTC)

    def update_status(self, status: TaskStatus) -> None:
        """更新任务状态"""
        self.status = status
        self.updated_at = datetime.now(UTC)

    def update_mode(self, mode: str) -> None:
        """更新任务模式"""
        self.mode = mode
        self.updated_at = datetime.now(UTC)

    def update_priority(self, priority: TaskPriority) -> None:
        """更新任务优先级"""
        self.priority = priority
        self.updated_at = datetime.now(UTC)

    def add_metadata(self, key: str, value: Any) -> None:
        """添加元数据"""
        self.metadata[key] = value
        self.updated_at = datetime.now(UTC)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return {
            "task_node_id": self.task_node_id,
            "description": self.description,
            "mode": self.mode,
            "status": self.status.value,
            "priority": self.priority.value,
            "context": self.context.to_dict(),
            "todos": [todo.to_dict() for todo in self.todos],
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskData":
        """从字典创建实例"""
        created_at = datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(UTC)
        updated_at = datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else datetime.now(UTC)

        # 处理上下文
        context_data = data.get("context", {})
        context = TaskContext.from_dict(context_data) if context_data else TaskContext(user_id=data.get("user_id", ""), session_id=data.get("session_id", ""), message_id=data.get("message_id", ""))

        # 处理TODO列表
        todos = [TodoItem.from_dict(todo) for todo in data.get("todos", [])]

        # 处理状态和优先级
        status = TaskStatus(data.get("status", "pending"))
        priority = TaskPriority(data.get("priority", "medium"))

        return cls(
            task_node_id=data["task_node_id"],
            description=data["description"],
            mode=data["mode"],
            status=status,
            priority=priority,
            context=context,
            todos=todos,
            metadata=data.get("metadata", {}),
            created_at=created_at,
            updated_at=updated_at,
        )


@dataclass
class StateTransition:
    """状态转换记录"""

    from_status: TaskStatus
    to_status: TaskStatus
    timestamp: datetime
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return {
            "from_status": self.from_status.value,
            "to_status": self.to_status.value,
            "timestamp": self.timestamp.isoformat(),
            "reason": self.reason,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StateTransition":
        """从字典创建实例"""
        return cls(
            from_status=TaskStatus(data["from_status"]),
            to_status=TaskStatus(data["to_status"]),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            reason=data.get("reason", ""),
            metadata=data.get("metadata", {}),
        )


@dataclass
class ValidationResult:
    """验证结果"""

    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_error(self, error: str) -> None:
        """添加错误"""
        self.errors.append(error)
        self.is_valid = False

    def add_warning(self, warning: str) -> None:
        """添加警告"""
        self.warnings.append(warning)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return {
            "is_valid": self.is_valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "metadata": self.metadata,
        }
