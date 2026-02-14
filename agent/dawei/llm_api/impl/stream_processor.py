# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""流式消息处理器"""

import contextlib
import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

from dawei.core.events import TaskEventType
from dawei.entity.lm_messages import ToolCall
from dawei.entity.stream_message import (
    ContentMessage,
    StreamMessages,
    ToolCallMessage,
    UsageMessage,
)
from dawei.entity.task_types import TokenUsage
from dawei.llm_api.base_llm_api import StreamChunkParser
from dawei.task_graph.task_node_data import TaskContext

logger = logging.getLogger(__name__)


class StreamProcessor:
    """流式消息处理器

    新增功能（从适配器合并）：
    - 实现 IStreamProcessor 接口
    - 基本的状态管理和统计功能
    - 事件处理支持
    """

    def __init__(self, provider: str = "openai"):
        """初始化流式处理器

        Args:
            provider: LLM提供商类型，支持 openai、deepseek、moonshot、ollama

        """
        self.provider = provider.lower()
        self.parser = self._create_parser()

        # 从适配器合并的功能
        self.is_streaming_flag = False
        self.token_usage = None
        self.processing_state: dict[str, bool | str | dict[str, ToolCall]] = {
            "is_processing": False,
            "current_content": "",
            "current_tool_calls": {},
        }
        self.event_handlers = {}

    def _create_parser(self) -> StreamChunkParser:
        """根据提供商类型创建解析器"""
        if self.provider == "deepseek":
            from .deepseek_api import DeepSeekParser

            return DeepSeekParser()
        if self.provider == "moonshot":
            from .moonshot_api import MoonshotParser

            return MoonshotParser()
        if self.provider == "ollama":
            from .ollama_api import OllamaParser

            return OllamaParser()
        # 默认使用OpenAI兼容解析器
        from .openai_compatible_api import OpenAICompatibleParser

        return OpenAICompatibleParser()

    async def process_message(
        self,
        stream_response: AsyncGenerator,
        task_id: str,
        context: Any,
    ) -> list[Any]:
        """处理流式消息（实现 IStreamProcessor 接口）

        Args:
            stream_response: 流式响应生成器
            task_id: 任务ID
            context: 任务上下文

        Returns:
            处理后的内容块列表

        Raises:
            ValueError: 如果上下文类型无效
            RuntimeError: 如果流式处理失败

        """
        # 确保上下文是 TaskContext 类型
        if not isinstance(context, TaskContext):
            if isinstance(context, dict):
                context = TaskContext.from_dict(context)
            else:
                raise ValueError(
                    f"Invalid context type: expected TaskContext or dict, got {type(context).__name__}",
                )

        # 简化的流式消息处理实现
        result = []
        self.is_streaming_flag = True
        self.processing_state["is_processing"] = True

        try:
            async for chunk in stream_response:
                # 处理流式块
                processed_chunks = await self.handle_stream_chunk(chunk, context)
                result.extend(processed_chunks)
        except Exception as e:
            # 清理状态
            self.is_streaming_flag = False
            self.processing_state["is_processing"] = False
            raise RuntimeError(f"Failed to process stream message for task {task_id}: {e}")
        finally:
            self.is_streaming_flag = False
            self.processing_state["is_processing"] = False

        return result

    def get_token_usage(self) -> TokenUsage:
        """获取 Token 使用统计（实现 IStreamProcessor 接口）

        Returns:
            Token 使用统计对象

        Note:
            如果未设置 token_usage，返回空的 TokenUsage 对象

        """
        return self.token_usage or TokenUsage()

    def get_stream_statistics(self) -> dict[str, Any]:
        """获取流统计信息（实现 IStreamProcessor 接口）

        Returns:
            流统计信息字典

        """
        return {
            "is_streaming": self.is_streaming_flag,
            "token_usage": self.token_usage.__dict__ if self.token_usage else {},
            "processing_statistics": self.processing_state,
            "provider": self.provider,
        }

    def reset_stream_state(self) -> None:
        """重置流式处理状态（实现 IStreamProcessor 接口）"""
        self.is_streaming_flag = False
        self.token_usage = None
        self.processing_state: dict[str, bool | str | dict[str, ToolCall]] = {
            "is_processing": False,
            "current_content": "",
            "current_tool_calls": {},
        }

    def is_streaming(self) -> bool:
        """检查是否正在流式处理（实现 IStreamProcessor 接口）

        Returns:
            是否正在流式处理

        """
        return self.is_streaming_flag

    def get_processing_state(self) -> dict[str, bool | str | dict[str, ToolCall]]:
        """获取处理状态（实现 IStreamProcessor 接口）

        Returns:
            处理状态字典

        """
        return self.processing_state.copy()

    def set_event_handler(self, event_type: str, handler: Any) -> None:
        """设置事件处理器（实现 IStreamProcessor 接口）

        Args:
            event_type: 事件类型
            handler: 事件处理器

        Raises:
            ValueError: 如果 event_type 为空
            TypeError: 如果 handler 不是可调用对象

        """
        if not event_type:
            raise ValueError("event_type cannot be empty")

        if not callable(handler):
            raise TypeError(f"handler must be callable, got {type(handler).__name__}")

        # 尝试将字符串转换为 TaskEventType，如果失败则使用原始字符串
        with contextlib.suppress(ValueError):
            TaskEventType(event_type)

        # 设置事件处理器
        self.event_handlers[event_type] = handler

    async def handle_stream_chunk(self, chunk: Any, _context: Any) -> list[Any]:
        """处理单个流式块（实现 IStreamProcessor 接口）

        Args:
            chunk: 流式块数据
            context: 任务上下文

        Returns:
            处理后的内容块列表

        Raises:
            ValueError: 如果 chunk 类型无效
            RuntimeError: 如果解析失败

        """
        result = []

        # 如果是字符串，尝试解析为JSON
        if isinstance(chunk, str):
            try:
                chunk = json.loads(chunk)
            except json.JSONDecodeError:
                # 如果不是有效的JSON，直接作为内容处理
                # 但要过滤掉空白字符串
                if chunk.strip():  # 只处理非空白内容
                    result.append(ContentMessage(content=chunk))
                return result

        # 如果是字典，使用解析器处理
        if isinstance(chunk, dict):
            try:
                messages = self.parser.parse_chunk(chunk)
                result.extend(messages)

                # 更新处理状态
                for message in messages:
                    if isinstance(message, ContentMessage):
                        self.processing_state["current_content"] += message.content
                    elif isinstance(message, ToolCallMessage):
                        tool_call = message.tool_call
                        # 直接使用 ToolCall 对象
                        self.processing_state["current_tool_calls"][tool_call.tool_call_id] = tool_call
                    elif isinstance(message, UsageMessage):
                        self.token_usage = message.data
            except Exception as e:
                raise RuntimeError(f"Failed to parse chunk: {e}")
        else:
            raise ValueError(
                f"Invalid chunk type: expected str or dict, got {type(chunk).__name__}",
            )

        return result

    async def process_stream(
        self,
        stream: AsyncGenerator[str, None],
    ) -> AsyncGenerator[StreamMessages, None]:
        """处理流式数据

        Args:
            stream: 原始流式数据生成器

        Yields:
            解析后的流式消息

        Raises:
            ValueError: 如果数据格式无效
            RuntimeError: 如果流式处理失败
            UnicodeDecodeError: 如果字节解码失败

        """
        last_chunk = None

        try:
            async for line in stream:
                # 解码字节行
                try:
                    line = line.decode("utf-8").strip() if isinstance(line, bytes) else line.strip()
                except UnicodeDecodeError as e:
                    raise ValueError(f"Failed to decode line as UTF-8: {e}")

                # 跳过空行和注释
                if not line or line.startswith(":"):
                    continue

                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        break

                    # 解析 JSON
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        raise ValueError(f"Invalid JSON in stream data: {data[:100]}...")

                    last_chunk = chunk

                    # 解析数据块
                    try:
                        messages = self.parser.parse_chunk(chunk)
                        for message in messages:
                            yield message
                    except Exception as e:
                        raise RuntimeError(f"Failed to parse stream chunk: {e}")

            # 流式结束后，发送完成消息
            try:
                complete_message = self.parser.complete(last_chunk)
                yield complete_message
            except Exception as e:
                raise RuntimeError(f"Failed to generate complete message: {e}")

        except Exception:
            # 重新抛出已处理的异常
            raise
