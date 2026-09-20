# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""任务数据模型
新架构中的基础数据类，职责单一，类型安全
"""

from dataclasses import dataclass, field
from datetime import datetime
from dawei.core.datetime_compat import UTC
from enum import Enum
from typing import List, Dict, Any

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
    parent_context: Dict[str, Any] | None = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    # 文件和资源
    task_files: List[str] = field(default_factory=list)
    task_images: List[str] = field(default_factory=list)

    # 时间戳
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> Dict[str, Any]:
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
    def from_dict(cls, data: Dict[str, Any]) -> "TaskContext":
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

    def merge(self, updates: Dict[str, Any]) -> None:
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

    # 模型路由（P3-0b/F1）：None = 继承当前 provider 配置
    model: str | None = None
    reasoning_effort: str | None = None

    # 派生深度（P3-5）：root=0，子任务 = 父深度 + 1
    depth: int = 0

    # P2-7 会话隔离：子任务独立 Conversation 的 id（None = 共享父对话）
    conversation_id: str | None = None

    # 超时与预算（P3-3）：None/非正数 = 不限制
    timeout_seconds: float | None = None  # 主循环墙钟 deadline（秒）
    token_budget: int | None = None  # 子任务级 token 上限（UsageMessage 累计）

    # 验收标准（P1b ⑧ 派发协议）：可判定的完成条件，new_task 必填；
    # 报告回注时回显给父 LLM，父据此判定"完成"vs"完成但未达标"
    acceptance_criteria: str | None = None

    # 结果 SSOT（P1a ④/P1b ⑧）：终态结果文本（attempt_completion / finalize_task 写入，
    # 报告回注与父 LLM 消费的单一事实源）。此前是未声明动态属性，
    # to_dict 不序列化 → 持久化/重载即丢失（2026-09-17 勘察实证）
    result: str | None = None

    # 成本/耗时记账（P1b ⑧）：executor 生命周期内 UsageMessage 累计与起止时间，
    # 报告回注回显给父 LLM；None = 未起跑/未记账
    tokens_used: int | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    # 上下文信息
    context: TaskContext = field(
        default_factory=lambda: TaskContext(user_id="", session_id="", message_id=""),
    )

    # TODO 列表
    todos: List[TodoItem] = field(default_factory=list)

    # 重试追踪 (Phase 4: idempotent execution)
    retry_count: int = 0  # Current retry count
    max_retries: int = 3  # Maximum retries for this node
    is_retryable: bool = True  # Whether this node can be retried
    require_confirmation_on_retry: bool = False  # Non-idempotent nodes need confirmation

    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)

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

    def can_retry(self) -> bool:
        """Check if this node can be retried (Phase 4: idempotent execution)."""
        return self.is_retryable and self.retry_count < self.max_retries

    def increment_retry(self) -> int:
        """Increment retry count and return new value. Updates updated_at."""
        self.retry_count += 1
        self.updated_at = datetime.now(UTC)
        return self.retry_count

    def mark_non_retryable(self, reason: str = "") -> None:
        """Mark this node as non-retryable (e.g., sent email, issued payment)."""
        self.is_retryable = False
        self.require_confirmation_on_retry = True
        self.updated_at = datetime.now(UTC)
        if reason:
            self.metadata["non_retryable_reason"] = reason

    def add_metadata(self, key: str, value: Any) -> None:
        """添加元数据"""
        self.metadata[key] = value
        self.updated_at = datetime.now(UTC)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "task_node_id": self.task_node_id,
            "description": self.description,
            "mode": self.mode,
            "status": self.status.value,
            "priority": self.priority.value,
            "model": self.model,
            "reasoning_effort": self.reasoning_effort,
            "depth": self.depth,
            "conversation_id": self.conversation_id,
            "timeout_seconds": self.timeout_seconds,
            "token_budget": self.token_budget,
            "acceptance_criteria": self.acceptance_criteria,
            "result": self.result,
            "tokens_used": self.tokens_used,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "context": self.context.to_dict(),
            "todos": [todo.to_dict() for todo in self.todos],
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "is_retryable": self.is_retryable,
            "require_confirmation_on_retry": self.require_confirmation_on_retry,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskData":
        """从字典创建实例"""
        created_at = datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(UTC)
        updated_at = datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else datetime.now(UTC)

        # P1b ⑧ 记账字段：起止时间容错解析（存量数据缺失/格式异常 → None）
        def _parse_dt(v: Any) -> datetime | None:
            if not v:
                return None
            try:
                return datetime.fromisoformat(v)
            except (ValueError, TypeError):
                return None

        started_at = _parse_dt(data.get("started_at"))
        completed_at = _parse_dt(data.get("completed_at"))

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
            model=data.get("model"),
            reasoning_effort=data.get("reasoning_effort"),
            depth=int(data.get("depth", 0) or 0),
            conversation_id=data.get("conversation_id"),
            timeout_seconds=data.get("timeout_seconds"),
            token_budget=data.get("token_budget"),
            acceptance_criteria=data.get("acceptance_criteria"),
            result=data.get("result"),
            tokens_used=data.get("tokens_used"),
            started_at=started_at,
            completed_at=completed_at,
            context=context,
            todos=todos,
            retry_count=data.get("retry_count", 0),
            max_retries=data.get("max_retries", 3),
            is_retryable=data.get("is_retryable", True),
            require_confirmation_on_retry=data.get("require_confirmation_on_retry", False),
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
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "from_status": self.from_status.value,
            "to_status": self.to_status.value,
            "timestamp": self.timestamp.isoformat(),
            "reason": self.reason,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StateTransition":
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
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_error(self, error: str) -> None:
        """添加错误"""
        self.errors.append(error)
        self.is_valid = False

    def add_warning(self, warning: str) -> None:
        """添加警告"""
        self.warnings.append(warning)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "is_valid": self.is_valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "metadata": self.metadata,
        }
