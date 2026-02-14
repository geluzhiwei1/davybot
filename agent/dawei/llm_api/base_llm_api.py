# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from typing import Any

from dawei.entity.lm_messages import LLMMessage
from dawei.entity.stream_message import StreamMessages


class StreamChunkParser(ABC):
    """流式数据块解析器抽象基类"""

    @abstractmethod
    def parse_chunk(self, chunk: dict[str, Any]) -> list[StreamMessages]:
        """解析单个数据块

        Args:
            chunk: 原始数据块

        Returns:
            解析后的消息列表

        """


class LlmApi(ABC):
    """LLM 提供者抽象接口"""

    @abstractmethod
    async def create_message(
        self,
        messages: list[LLMMessage],
        **kwargs,
    ) -> AsyncGenerator[StreamMessages, None]:
        """创建消息并返回流式响应"""
