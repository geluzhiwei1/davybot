# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Agentic 模块核心接口定义

本模块定义了 LLM 模块与 Agentic 模块解耦所需的核心接口，
包括消息处理、LLM 服务、工具调用服务以及系统管理接口等。
"""

from .event_bus import IEventBus
from .llm_service import ILLMService
from .message_processor import IMessageProcessor
from .task_executor import ITaskExecutor
from .tool_call_service import IToolCallService
from .tool_executor import IToolExecutor

__all__ = [
    "IEventBus",
    "ILLMService",
    "IMessageProcessor",
    "ITaskExecutor",
    "IToolCallService",
    "IToolExecutor",
]
