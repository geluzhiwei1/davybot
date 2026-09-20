# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""异步任务状态管理模块

提供统一的异步任务管理、状态跟踪和WebSocket连接状态管理功能。
"""

from .interfaces import (
    IAsyncTaskManager,
    ICheckpointService,
    ITaskContext,
    ITaskExecutor,
    IWebSocketStateManager,
)
from .task_context import TaskContext
from .task_manager import AsyncTaskManager
from .types import (
    CheckpointData,
    ConnectionState,
    RetryPolicy,
    TaskDefinition,
    TaskError,
    TaskResult,
    TaskStatus,
    WebSocketState,
)
from .websocket_state_manager import WebSocketStateManager

__all__ = [
    # 核心类
    "AsyncTaskManager",
    "TaskContext",
    "WebSocketStateManager",
    # 类型定义
    "TaskStatus",
    "ConnectionState",
    "TaskDefinition",
    "RetryPolicy",
    "TaskResult",
    "TaskError",
    "CheckpointData",
    "WebSocketState",
    # 接口定义
    "IAsyncTaskManager",
    "ITaskContext",
    "IWebSocketStateManager",
    "ICheckpointService",
    "ITaskExecutor",
]
