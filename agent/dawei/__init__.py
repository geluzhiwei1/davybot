# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Dawei - AI Agent Core Module

Provides core functionality for the AI agent system:
- Asynchronous task management
- WebSocket communication
- Tool execution
- Event system
- Conversation management
"""

from pathlib import Path
from dotenv import find_dotenv, load_dotenv

# Priority: CWD > find_dotenv()
cwd_env = Path.cwd() / ".env"
if cwd_env.exists():
    env_path = str(cwd_env)
else:
    env_path = find_dotenv()

if env_path:
    load_dotenv(env_path, override=True)
    # Note: We don't print here to avoid output before CLI is ready

# 版本信息
__version__ = "1.0.0"
__author__ = "Dawei Team"
__description__ = "AI agent API with dawei as top-level package"

# 核心模块导入
from . import (
    agentic,
    async_task,
    conversation,
    core,
    entity,
    interfaces,
    tools,
    websocket,
)

# 异步任务管理模块
from .async_task import (
    AsyncTaskManager,
    CheckpointData,
    ConnectionState,
    RetryPolicy,
    TaskContext,
    TaskDefinition,
    TaskError,
    TaskResult,
    TaskStatus,
    WebSocketState,
    WebSocketStateManager,
)

# 核心模块
from .core import (
    ErrorHandler,
    # StructuredLogger  # 已移至 dawei.logg.logging
    EventBus,
)

# 实体模块
from .entity import (
    AssistantMessage,
    ContentType,
    MessageRole,
    SystemMessage,
    ToolMessage,
    UserMessage,
)

# 工具模块
from .tools import CustomBaseTool, ToolExecutor, ToolManager

# WebSocket模块
from .websocket import (
    BaseWebSocketMessage,
    MessageSerializer,
    MessageType,
    MessageValidator,
    WebSocketManager,
)

# 导出主要类和函数
__all__ = [
    # 版本信息
    "__version__",
    "__author__",
    "__description__",
    # 异步任务管理
    "AsyncTaskManager",
    "TaskContext",
    "WebSocketStateManager",
    "TaskStatus",
    "ConnectionState",
    "TaskDefinition",
    "RetryPolicy",
    "TaskResult",
    "TaskError",
    "CheckpointData",
    "WebSocketState",
    # WebSocket通信
    "WebSocketManager",
    "BaseWebSocketMessage",
    "MessageType",
    "MessageSerializer",
    "MessageValidator",
    # 工具系统
    "ToolExecutor",
    "ToolManager",
    "CustomBaseTool",
    # 核心系统
    "EventBus",
    "ErrorHandler",
    # "StructuredLogger",  # 已移至 dawei.logg.logging
    # 消息实体
    "UserMessage",
    "AssistantMessage",
    "SystemMessage",
    "ToolMessage",
    "MessageRole",
    "ContentType",
    # 模块
    "async_task",
    "websocket",
    "tools",
    "agentic",
    "core",
    "conversation",
    "entity",
    "interfaces",
]


def get_version():
    """获取版本信息"""
    return __version__


def get_module_info():
    """获取模块信息"""
    return {
        "name": "dawei",
        "version": __version__,
        "author": __author__,
        "description": __description__,
        "modules": [
            "async_task",
            "websocket",
            "tools",
            "agentic",
            "core",
            "conversation",
            "entity",
            "interfaces",
        ],
    }
