# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Task 模块的数据类型定义
包含枚举、数据类和基础接口定义
"""

from __future__ import annotations

import contextlib
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any

# 只在类型检查时导入，避免运行时循环导入
if TYPE_CHECKING:
    from collections.abc import Callable

    from dawei.task_graph.task_node_data import TaskContext


# ============================================================================
# 枚举定义
# ============================================================================


class TaskStatus(Enum):
    """任务状态枚举"""

    PENDING = "pending"
    RUNNING = "running"
    WAITING_FOR_TOOL = "waiting_for_tool"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED = "aborted"
    IDLE = "idle"
    INTERACTIVE = "interactive"
    RESUMABLE = "resumable"


class TaskMode(Enum):
    """任务模式枚举"""

    ARCHITECT = "architect"
    CODE = "code"
    ASK = "ask"
    PLAN = "plan"
    DEBUG = "debug"


class ToolProtocol(Enum):
    """工具协议枚举"""

    XML = "xml"
    NATIVE = "native"


# ============================================================================
# 数据模型
# ============================================================================


@dataclass
class TokenUsage:
    """Token 使用统计"""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0
    total_cost: float = 0.0


@dataclass
class ToolUsage:
    """工具使用统计"""

    attempts: int = 0
    failures: int = 0


@dataclass
class ToolCall:
    """工具调用模型"""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    result: Any | None = None
    error: str | None = None
    status: str = "pending"  # pending, executing, completed, failed


# ============================================================================
# 事件系统
# ============================================================================


class TaskEvent:
    """任务事件基类"""

    def __init__(
        self,
        task_id: str = "",
        event_type: str = "",
        data: Any = None,
        event_id: str = "",
        timestamp: float = 0.0,
        source: str = "",
        priority: int = 0,
    ):
        self.task_id = task_id
        self.event_type = event_type
        self.data = data
        self.event_id = event_id
        self.timestamp = timestamp or time.time()
        self.source = source
        self.priority = priority


class EventEmitter:
    """事件发射器"""

    def __init__(self):
        self._listeners: dict[str, list[Callable]] = {}
        self._websocket_callback: Callable | None = None

    def on(self, event_type: str, callback: Callable):
        """注册事件监听器"""
        if event_type not in self._listeners:
            self._listeners[event_type] = []
        self._listeners[event_type].append(callback)

    def emit(self, event: TaskEvent):
        """发射事件"""
        # 调用本地监听器
        listeners = self._listeners.get(event.event_type, [])
        for listener in listeners:
            try:
                listener(event)
            # User callback - tolerate errors to prevent cascade failures
            except (TypeError, AttributeError, ValueError, RuntimeError) as e:
                print(f"Error in event listener: {e}")

        # 如果有 WebSocket 回调，也调用它
        if self._websocket_callback:
            try:
                import asyncio

                # 如果回调是协程函数，需要异步调用
                if asyncio.iscoroutinefunction(self._websocket_callback):
                    asyncio.create_task(self._websocket_callback(event))
                else:
                    self._websocket_callback(event)
            # User callback - tolerate errors to prevent cascade failures
            except (TypeError, AttributeError, ValueError, RuntimeError) as e:
                print(f"Error in WebSocket callback: {e}")

    def off(self, event_type: str, callback: Callable):
        """移除事件监听器"""
        if event_type in self._listeners:
            with contextlib.suppress(ValueError):
                self._listeners[event_type].remove(callback)


class Tool(ABC):
    """工具抽象接口"""

    @property
    @abstractmethod
    def name(self) -> str:
        """工具名称"""

    @property
    @abstractmethod
    def description(self) -> str:
        """工具描述"""

    @abstractmethod
    async def execute(self, parameters: dict[str, Any], context: TaskContext) -> Any:
        """执行工具"""


class MessageQueueService:
    """消息队列服务"""

    def __init__(self):
        self._messages: list[dict[str, Any]] = []
        self._state_changed_handlers: list[Callable] = []

    def enqueue(self, message: dict[str, Any]):
        """入队消息"""
        self._messages.append(message)
        self._notify_state_changed()

    def dequeue(self) -> dict[str, Any] | None:
        """出队消息"""
        if self._messages:
            return self._messages.pop(0)
        return None

    def is_empty(self) -> bool:
        """检查队列是否为空"""
        return len(self._messages) == 0

    def on_state_changed(self, handler: Callable):
        """注册状态变化处理器"""
        self._state_changed_handlers.append(handler)

    def _notify_state_changed(self):
        """通知状态变化"""
        for handler in self._state_changed_handlers:
            try:
                handler()
            # User callback - tolerate errors to prevent cascade failures
            except (TypeError, AttributeError, ValueError, RuntimeError) as e:
                print(f"Error in state change handler: {e}")


class CheckpointService(ABC):
    """检查点服务抽象接口"""

    @abstractmethod
    async def create(self, task_id: str, state: dict[str, Any], force: bool = False) -> str:
        """创建检查点"""

    @abstractmethod
    async def restore(self, checkpoint_id: str) -> dict[str, Any] | None:
        """恢复检查点"""

    @abstractmethod
    async def list(self, task_id: str) -> list[dict[str, Any]]:
        """列出检查点"""

    @abstractmethod
    async def delete(self, checkpoint_id: str) -> bool:
        """删除检查点"""


# ============================================================================
# 辅助类
# ============================================================================


class ToolRepetitionDetector:
    """工具重复检测器"""

    def __init__(self, limit: int = 5):
        self.limit = limit
        self.consecutive_count = 0
        self.last_tool_name: str | None = None

    def check_repetition(self, tool_name: str) -> bool:
        """检查工具重复"""
        if self.last_tool_name == tool_name:
            self.consecutive_count += 1
        else:
            self.consecutive_count = 1
            self.last_tool_name = tool_name

        return self.consecutive_count >= self.limit

    def reset(self):
        """重置计数器"""
        self.consecutive_count = 0
        self.last_tool_name = None


@dataclass
class ModeTransition:
    """模式转换信息"""

    from_mode: str
    to_mode: str
    reason: str
    confidence: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class SkillCall:
    """Claude Skill 调用信息"""

    skill_name: str
    parameters: dict[str, Any]
    result: Any | None = None
    error: str | None = None
    execution_time: float = 0.0


@dataclass
class MCPRequest:
    """MCP 请求信息"""

    server_name: str
    method: str
    parameters: dict[str, Any]
    result: Any | None = None
    error: str | None = None


@dataclass
class TaskExecutionPlan:
    """任务执行计划"""

    steps: list[dict[str, Any]]
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def add_step(self, step: dict[str, Any]) -> None:
        """添加执行步骤"""
        self.steps.append(step)

    def get_step(self, index: int) -> dict[str, Any] | None:
        """获取指定索引的步骤"""
        if 0 <= index < len(self.steps):
            return self.steps[index]
        return None

    def total_steps(self) -> int:
        """获取总步骤数"""
        return len(self.steps)


@dataclass
class TaskSummary:
    """任务完成摘要"""

    task_id: str
    instance_id: str
    initial_mode: str
    final_mode: str
    mode_transitions: int
    skill_calls: int
    mcp_requests: int
    subtasks_created: int
    tool_usage: dict[str, dict[str, int]]
    token_usage: dict[str, Any]
    completed_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class TaskState:
    """任务状态快照"""

    task_id: str
    status: str
    initial_mode: str
    current_mode: str
    messages: list[Any]  # 使用 Any 避免循环导入
    mode_history: list[dict[str, Any]]
    skill_calls: list[dict[str, Any]]
    mcp_requests: list[dict[str, Any]]
    tool_usage: dict[str, dict[str, int]]
    token_usage: dict[str, Any]
    saved_at: datetime = field(default_factory=lambda: datetime.now(UTC))
