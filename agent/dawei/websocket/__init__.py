# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""WebSocket通信模块

提供优化的WebSocket服务器实现，包括连接管理、消息路由和会话管理功能。
"""

from .manager import WebSocketManager
from .protocol import (
    AssistantWebSocketMessage,
    BaseWebSocketMessage,
    ErrorMessage,
    HeartbeatMessage,
    MessageSerializer,
    MessageType,
    MessageValidator,
    StateSyncMessage,
    StateUpdateMessage,
    TaskNodeCompleteMessage,
    TaskNodeProgressMessage,
    TaskNodeStartMessage,
    UserWebSocketMessage,
)
from .router import MessageRouter
from .session import SessionManager

__all__ = [
    "AssistantWebSocketMessage",
    "BaseWebSocketMessage",
    "ErrorMessage",
    "HeartbeatMessage",
    "MessageRouter",
    "MessageSerializer",
    "MessageType",
    "MessageValidator",
    "SessionManager",
    "StateSyncMessage",
    "StateUpdateMessage",
    "TaskNodeCompleteMessage",
    "TaskNodeProgressMessage",
    "TaskNodeStartMessage",
    "UserWebSocketMessage",
    "WebSocketManager",
]
