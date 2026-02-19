# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""LLM API 工具函数

提供各种工具函数和处理器，用于支持 LLM API 客户端。
"""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

from aiohttp import ClientResponse

logger = logging.getLogger(__name__)


class StreamProcessor:
    """流式响应处理器"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    async def process_stream(
        self,
        stream_generator: AsyncGenerator[bytes, None],
    ) -> AsyncGenerator[dict[str, Any], None]:
        """处理流式响应

        Args:
            stream_generator: 原始流式响应生成器

        Yields:
            处理后的消息字典

        Raises:
            UnicodeDecodeError: If chunk cannot be decoded as UTF-8
            json.JSONDecodeError: If JSON parsing fails (logged, continues)
            asyncio.CancelledError: If stream processing is cancelled

        """
        try:
            async for chunk in stream_generator:
                chunk_str = chunk.decode("utf-8").strip()
                if chunk_str.startswith("data: "):
                    data = chunk_str[6:]  # 移除 'data: ' 前缀
                    if data == "[DONE]":
                        break

                    message = json.loads(data)
                    yield message
                elif chunk_str:
                    self.logger.debug(f"Received non-JSON chunk: {chunk_str}")

        except UnicodeDecodeError:
            self.logger.exception("Stream encoding error: ")
            raise
        except (asyncio.CancelledError, GeneratorExit):
            # Stream was cancelled or closed - propagate immediately
            raise
        except (OSError, ConnectionError):
            self.logger.exception("Stream connection error: ")
            raise
        except Exception:
            self.logger.exception("Unexpected error processing stream: ")
            raise

    async def process_http_stream(
        self,
        response: ClientResponse,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """处理 HTTP 流式响应

        Args:
            response: HTTP 响应对象

        Yields:
            处理后的消息字典

        """
        async for line in response.content:
            line_str = line.decode("utf-8").strip()
            if line_str.startswith("data: "):
                data = line_str[6:]
                if data == "[DONE]":
                    break

                message = json.loads(data)
                yield message
            elif line_str:
                self.logger.debug(f"Received non-JSON line: {line_str}")


# 创建全局流处理器实例
stream_processor = StreamProcessor()


class AsyncUtils:
    """异步工具函数"""

    @staticmethod
    async def run_with_timeout(coro, timeout: float):
        """带超时的异步函数执行

        Args:
            coro: 协程对象
            timeout: 超时时间（秒）

        Returns:
            协程结果

        Raises:
            asyncio.TimeoutError: 超时异常

        """
        try:
            return await asyncio.wait_for(coro, timeout=timeout)
        except TimeoutError:
            logger.warning(f"Operation timed out after {timeout} seconds")
            raise

    @staticmethod
    async def gather_with_timeout(*coros, timeout: float):
        """带超时的异步任务收集

        Args:
            *coros: 协程对象
            timeout: 超时时间（秒）

        Returns:
            任务结果列表

        """
        try:
            return await asyncio.wait_for(asyncio.gather(*coros), timeout=timeout)
        except TimeoutError:
            logger.warning(f"Operation timed out after {timeout} seconds")
            raise


class ResponseUtils:
    """响应处理工具"""

    @staticmethod
    def extract_error_message(response_data: dict[str, Any]) -> str:
        """从响应数据中提取错误消息

        Args:
            response_data: 响应数据字典

        Returns:
            错误消息字符串

        """
        if isinstance(response_data, dict):
            if response_data.get("error"):
                error = response_data["error"]
                if isinstance(error, dict):
                    return error.get("message", str(error))
                return str(error)
            if response_data.get("message"):
                return str(response_data["message"])
            if response_data.get("detail"):
                return str(response_data["detail"])
        return str(response_data)

    @staticmethod
    def is_rate_limit_error(error_message: str) -> bool:
        """检查是否为速率限制错误

        Args:
            error_message: 错误消息

        Returns:
            是否为速率限制错误

        """
        error_lower = error_message.lower()
        return "429" in error_message or "rate limit" in error_lower or "too many requests" in error_lower or "quota exceeded" in error_lower

    @staticmethod
    def is_timeout_error(error_message: str) -> bool:
        """检查是否为超时错误

        Args:
            error_message: 错误消息

        Returns:
            是否为超时错误

        """
        error_lower = error_message.lower()
        return "timeout" in error_lower or "timed out" in error_lower


class JsonUtils:
    """JSON 处理工具"""

    @staticmethod
    def safe_loads(json_str: str) -> dict[str, Any] | None:
        """安全解析 JSON 字符串

        Args:
            json_str: JSON 字符串

        Returns:
            解析后的字典，失败返回 None

        """
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            logger.debug(f"Failed to parse JSON: {json_str}")
            return None

    @staticmethod
    def safe_dumps(obj: Any, indent: int | None = None) -> str:
        """安全序列化对象为 JSON 字符串

        Args:
            obj: 要序列化的对象
            indent: 缩进空格数

        Returns:
            JSON 字符串

        """
        try:
            return json.dumps(obj, ensure_ascii=False, indent=indent)
        except (TypeError, ValueError):
            logger.exception("Failed to serialize to JSON: ")
            return str(obj)
