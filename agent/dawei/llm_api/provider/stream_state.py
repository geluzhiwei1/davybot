# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""流式处理状态管理

提供统一的流式上下文状态管理，遵循 KISS 原则
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from dawei.entity.lm_messages import ToolCall

logger = logging.getLogger(__name__)


@dataclass
class StreamState:
    """流处理状态数据类

    用于跟踪 LLM 流式响应的当前状态
    """

    is_processing: bool = False
    is_streaming: bool = False
    current_content: str = ""
    current_tool_calls: dict[str, ToolCall] = field(default_factory=dict)
    token_usage: dict[str, Any] | None = None
    error_count: int = 0
    last_error: str | None = None

    def reset(self) -> None:
        """重置状态到初始值"""
        self.is_processing = False
        self.is_streaming = False
        self.current_content = ""
        self.current_tool_calls.clear()
        self.token_usage = None
        self.error_count = 0
        self.last_error = None
        logger.debug("StreamState reset")

    def start_processing(self) -> None:
        """开始处理"""
        self.is_processing = True
        self.is_streaming = True
        logger.debug("StreamState: started processing")

    def stop_processing(self) -> None:
        """停止处理"""
        self.is_processing = False
        self.is_streaming = False
        logger.debug("StreamState: stopped processing")

    def record_error(self, error: str) -> None:
        """记录错误"""
        self.error_count += 1
        self.last_error = error
        logger.warning(f"StreamState: error recorded (count={self.error_count}): {error}")
