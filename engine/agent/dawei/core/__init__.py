# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""核心模块
包含事件系统、错误处理、日志记录等核心功能
"""

from dawei.interfaces.event_bus import IEventBus

from .dependency_container import (
    DependencyContainer,
    get_global_container,
    inject,
    reset_global_container,
    service_factory,
    singleton_service,
    transient_service,
)
from .error_handler import ErrorContext, handle_errors
from .errors import (
    ToolExecutionError,
    ToolNotFoundError,
    ToolSecurityError,
    ValidationError,
    WebSocketError,
)
from .events import SimpleEventBus, TaskEvent, TaskEventType  # 🔴 修复：移除 CORE_EVENT_BUS 导入

# from .structured_logger import get_logger, log_performance, StructuredLogger  # 已移除
from .metrics import increment_counter, set_gauge, timer

# 为了向后兼容，提供EventBus别名
EventBus = SimpleEventBus

# 为了向后兼容，提供ErrorHandler别名
ErrorHandler = handle_errors

__all__ = [
    "SimpleEventBus",
    "EventBus",
    "IEventBus",
    "TaskEventType",
    "TaskEvent",
    "WebSocketError",
    "ValidationError",
    "ToolNotFoundError",
    "ToolExecutionError",
    "ToolSecurityError",
    "handle_errors",
    "ErrorHandler",
    "ErrorContext",
    "increment_counter",
    "set_gauge",
    "timer",
    "DependencyContainer",
    "get_global_container",
    "reset_global_container",
    "inject",
    "service_factory",
    "singleton_service",
    "transient_service",
]
