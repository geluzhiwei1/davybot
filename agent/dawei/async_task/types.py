# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""异步任务管理相关的类型定义

定义了任务状态、连接状态、任务定义、重试策略等核心数据类型。
"""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class TaskStatus(Enum):
    """任务状态枚举"""

    PENDING = "pending"  # 待执行
    RUNNING = "running"  # 执行中
    WAITING = "waiting"  # 等待中（如等待资源）
    PAUSED = "paused"  # 已暂停
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"  # 执行失败
    CANCELLED = "cancelled"  # 已取消
    TIMEOUT = "timeout"  # 执行超时


class ConnectionState(Enum):
    """WebSocket连接状态枚举"""

    DISCONNECTED = "disconnected"  # 未连接
    CONNECTING = "connecting"  # 连接中
    CONNECTED = "connected"  # 已连接
    RECONNECTING = "reconnecting"  # 重连中
    ERROR = "error"  # 连接错误


@dataclass
class RetryPolicy:
    """重试策略配置"""

    max_attempts: int = 3  # 最大重试次数
    base_delay: float = 1.0  # 基础延迟时间（秒）
    max_delay: float = 60.0  # 最大延迟时间（秒）
    exponential_base: float = 2.0  # 指数退避基数
    jitter: bool = True  # 是否添加随机抖动
    retryable_exceptions: list[type] = field(default_factory=list)  # 可重试的异常类型

    def calculate_delay(self, attempt: int) -> float:
        """计算重试延迟时间

        Args:
            attempt: 当前重试次数（从1开始）

        Returns:
            延迟时间（秒）

        """
        if attempt <= 0:
            return 0.0

        # 指数退避计算
        delay = self.base_delay * (self.exponential_base ** (attempt - 1))

        # 限制最大延迟
        delay = min(delay, self.max_delay)

        # 添加随机抖动
        if self.jitter:
            import random

            delay *= 0.5 + random.random() * 0.5

        return delay

    def should_retry(self, exception: Exception, attempt: int) -> bool:
        """判断是否应该重试

        Args:
            exception: 发生的异常
            attempt: 当前重试次数

        Returns:
            是否应该重试

        """
        if attempt >= self.max_attempts:
            return False

        if not self.retryable_exceptions:
            return True  # 如果没有指定异常类型，默认所有异常都可重试

        return any(isinstance(exception, exc_type) for exc_type in self.retryable_exceptions)


@dataclass
class TaskDefinition:
    """任务定义"""

    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    executor: Callable[..., Awaitable[Any]] | None = None  # 任务执行函数
    parameters: dict[str, Any] = field(default_factory=dict)
    priority: int = 5  # 优先级（1-10，数字越大优先级越高）
    timeout: float | None = None  # 超时时间（秒）
    retry_policy: RetryPolicy | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self):
        """初始化后处理"""
        if not self.name:
            self.name = f"Task-{self.task_id[:8]}"
        if self.retry_policy is None:
            self.retry_policy = RetryPolicy()


@dataclass
class TaskResult:
    """任务执行结果"""

    task_id: str
    status: TaskStatus
    result: Any | None = None
    error: Exception | None = None
    execution_time: float = 0.0
    attempts: int = 1
    started_at: datetime | None = None
    completed_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_success(self) -> bool:
        """是否执行成功"""
        return self.status == TaskStatus.COMPLETED

    @property
    def is_failure(self) -> bool:
        """是否执行失败"""
        return self.status in [
            TaskStatus.FAILED,
            TaskStatus.TIMEOUT,
            TaskStatus.CANCELLED,
        ]

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "result": self.result,
            "error": str(self.error) if self.error else None,
            "execution_time": self.execution_time,
            "attempts": self.attempts,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "metadata": self.metadata,
            "is_success": self.is_success,
            "is_failure": self.is_failure,
        }


@dataclass
class TaskError:
    """任务错误信息"""

    task_id: str
    error_type: str
    error_message: str
    error_details: dict[str, Any] | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    recoverable: bool = True
    retry_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return {
            "task_id": self.task_id,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "error_details": self.error_details,
            "timestamp": self.timestamp.isoformat(),
            "recoverable": self.recoverable,
            "retry_count": self.retry_count,
        }


@dataclass
class CheckpointData:
    """检查点数据"""

    checkpoint_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str = ""
    state_data: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    version: int = 1

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return {
            "checkpoint_id": self.checkpoint_id,
            "task_id": self.task_id,
            "state_data": self.state_data,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "version": self.version,
        }


@dataclass
class WebSocketState:
    """WebSocket连接状态"""

    session_id: str
    state: ConnectionState = ConnectionState.DISCONNECTED
    connected_at: datetime | None = None
    last_heartbeat: datetime | None = None
    message_count: int = 0
    error_count: int = 0
    last_error: str | None = None
    reconnect_attempts: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_connected(self) -> bool:
        """是否已连接"""
        return self.state == ConnectionState.CONNECTED

    @property
    def is_healthy(self) -> bool:
        """连接是否健康"""
        if not self.is_connected:
            return False

        # 如果连接刚建立且还没有心跳，认为是健康的
        if self.last_heartbeat is None:
            # 检查连接时间，如果连接时间在30秒内，认为是健康的
            if self.connected_at:
                import time

                try:
                    connection_age = time.time() - self.connected_at.timestamp()
                    return connection_age < 30  # 30秒内的连接认为是健康的
                except (AttributeError, TypeError):
                    return False
            return False

        # 检查心跳是否超时（超过60秒认为不健康）
        import time

        try:
            return (time.time() - self.last_heartbeat.timestamp()) < 60
        except (AttributeError, TypeError):
            return False

    def update_heartbeat(self):
        """更新心跳时间"""
        self.last_heartbeat = datetime.now(timezone.utc)

    def increment_message_count(self):
        """增加消息计数"""
        self.message_count += 1

    def increment_error_count(self, error: str | None = None):
        """增加错误计数"""
        self.error_count += 1
        if error:
            self.last_error = error

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return {
            "session_id": self.session_id,
            "state": self.state.value,
            "connected_at": self.connected_at.isoformat() if self.connected_at else None,
            "last_heartbeat": self.last_heartbeat.isoformat() if self.last_heartbeat else None,
            "message_count": self.message_count,
            "error_count": self.error_count,
            "last_error": self.last_error,
            "reconnect_attempts": self.reconnect_attempts,
            "metadata": self.metadata,
            "is_connected": self.is_connected,
            "is_healthy": self.is_healthy,
        }


@dataclass
class TaskProgress:
    """任务进度信息"""

    task_id: str
    progress: int  # 进度百分比（0-100）
    message: str = ""
    data: dict[str, Any] | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return {
            "task_id": self.task_id,
            "progress": self.progress,
            "message": self.message,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
        }


# 类型别名定义
TaskExecutor = Callable[..., Awaitable[Any]]
ProgressCallback = Callable[[TaskProgress], Awaitable[None]]
StateChangeCallback = Callable[[str, TaskStatus, TaskStatus], Awaitable[None]]
ErrorCallback = Callable[[TaskError], Awaitable[None]]
CompletionCallback = Callable[[TaskResult], Awaitable[None]]

# 事件类型定义
TaskEventType = str
EventData = dict[str, Any]


# 配置类型定义
@dataclass
class AsyncTaskManagerConfig:
    """异步任务管理器配置"""

    max_concurrent_tasks: int = 10
    default_timeout: float = 900.0  # 15分钟（支持大型HTML/代码生成）
    checkpoint_interval: int = 30  # 30秒
    cleanup_interval: int = 60  # 60秒
    enable_metrics: bool = True
    enable_checkpoints: bool = True
    checkpoint_storage_path: str = "checkpoints"


@dataclass
class WebSocketManagerConfig:
    """WebSocket管理器配置"""

    heartbeat_interval: int = 30  # 30秒
    connection_timeout: int = 60  # 60秒
    max_reconnect_attempts: int = 5
    reconnect_delay: float = 1.0  # 1秒
    enable_auto_reconnect: bool = True
    message_buffer_size: int = 1000
