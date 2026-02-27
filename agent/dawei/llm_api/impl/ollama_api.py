# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Ollama API客户端实现

Ollama是一个本地运行大语言模型的工具，提供OpenAI兼容的API。
文档：https://github.com/ollama/ollama
API文档：https://github.com/ollama/ollama/blob/main/docs/api.md
"""

import json
from collections.abc import AsyncGenerator
from typing import Any

import aiohttp

from dawei.core import local_context
from dawei.core.error_handler import handle_errors
from dawei.core.errors import LLMError, ValidationError
from dawei.entity.lm_messages import (
    AssistantMessage,
    ChatGeneration,
    ChatResult,
    LLMMessage,
    UserMessage,
)
from dawei.entity.stream_message import (
    CompleteMessage,
    ContentMessage,
    StreamMessages,
    UsageMessage,
)
from dawei.llm_api.base_llm_api import StreamChunkParser
from dawei.llm_api.impl.stream_processor import StreamProcessor
from dawei.logg.logging import get_logger, log_performance

from .openai_compatible_api import OpenaiCompatibleClient

logger = get_logger(__name__)


class OllamaParser(StreamChunkParser):
    """Ollama API的流式数据解析器

    Ollama的流式响应格式与OpenAI兼容，但有细微差异：
    - 使用"response"字段而不是"delta"
    - 可能返回"done"字段表示完成
    - 可能包含"prompt_eval_count"和"eval_count"等token统计
    """

    def __init__(self):
        self.content = ""
        self.final_usage = None
        self.is_done = False

    def parse_chunk(self, chunk: dict[str, Any]) -> list[StreamMessages]:
        """解析Ollama格式的数据块

        Args:
            chunk: Ollama API返回的数据块
                格式：{
                    "model": "llama3.1",
                    "created_at": "2024-01-23T12:00:00Z",
                    "response": "文本内容",
                    "done": false,
                    "context": [512, 1234, ...],
                    "prompt_eval_count": 20,
                    "eval_count": 50
                }

        Returns:
            消息列表

        """
        messages = []

        # 检查是否完成
        if chunk.get("done", False):
            self.is_done = True

            # 添加使用统计消息
            usage_data = {
                "prompt_tokens": chunk.get("prompt_eval_count", 0),
                "completion_tokens": chunk.get("eval_count", 0),
                "total_tokens": chunk.get("prompt_eval_count", 0) + chunk.get("eval_count", 0),
            }

            messages.append(
                UsageMessage(user_message_id=local_context.get_message_id(), data=usage_data),
            )

            # 添加完成消息
            messages.append(
                CompleteMessage(
                    user_message_id=local_context.get_message_id(),
                    finish_reason="stop",
                ),
            )

            return messages

        # 提取响应内容
        response_content = chunk.get("response", "")
        # 只处理非空白内容，避免发送空白字符导致的空消息
        if response_content and response_content.strip():
            self.content += response_content

            messages.append(
                ContentMessage(
                    user_message_id=local_context.get_message_id(),
                    content=response_content,
                    role="assistant",
                ),
            )

        return messages


class OllamaClient(OpenaiCompatibleClient):
    """Ollama客户端实现

    继承自OpenaiCompatibleClient，复用大部分功能，
    只需要覆盖Ollama特有的端点和解析逻辑。

    配置要求：
        - apiProvider: "ollama"
        - ollamaBaseUrl: "http://localhost:11434" (默认)
        - ollamaModelId: "llama3.1" 或其他已安装的模型
        - ollamaApiKey: 可选，默认为"ollama"

    使用示例：
        ```python
        client = OllamaClient({
            "apiProvider": "ollama",
            "ollamaBaseUrl": "http://localhost:11434",
            "ollamaModelId": "llama3.1",
            "ollamaApiKey": "ollama",  # 可选
            "temperature": 0.7,
            "max_tokens": 2000
        })
        ```
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """初始化Ollama客户端

        Args:
            config: 配置字典

        """
        # 调用父类初始化
        super().__init__(config)

        # 确保provider是ollama
        self.provider = "ollama"

        # Ollama特定配置
        self.base_url = config.get("ollamaBaseUrl", "http://localhost:11434").rstrip("/")
        self.api_key = config.get("ollamaApiKey", "ollama")
        self.model = config.get("ollamaModelId", config.get("model_id", "llama3.1"))

        # 验证配置
        if not self.base_url:
            raise ValidationError("ollamaBaseUrl", self.base_url, "Ollama base URL is required")

        if not self.model:
            raise ValidationError("ollamaModelId", self.model, "Ollama model ID is required")

        self.logger.info(f"Initialized Ollama client for model: {self.model}")

    def _prepare_headers(self) -> dict[str, str]:
        """准备请求头

        Ollama不需要Authorization头，但可以包含其他自定义头
        """
        headers = {
            "Content-Type": "application/json",
        }

        # 如果提供了额外的自定义头
        custom_headers = self.config.get("openAiHeaders", {})
        headers.update(custom_headers)

        return headers

    def _prepare_request_params(
        self,
        messages: list[LLMMessage],
        stream: bool = True,
        **_kwargs,
    ) -> dict[str, Any]:
        """准备请求参数

        Ollama API使用与OpenAI兼容的格式，但有一些参数名称不同

        Args:
            messages: 消息列表
            stream: 是否流式输出
            **kwargs: 额外参数

        Returns:
            请求参数字典

        """
        # 转换消息格式
        ollama_messages = []
        for msg in messages:
            if isinstance(msg, UserMessage):
                ollama_messages.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AssistantMessage):
                ollama_messages.append({"role": "assistant", "content": msg.content})
            elif hasattr(msg, "role") and hasattr(msg, "content"):
                ollama_messages.append({"role": msg.role, "content": msg.content})
            else:
                # 默认当作user消息
                ollama_messages.append({"role": "user", "content": str(msg)})

        # 构建请求参数
        params = {
            "model": self.model,
            "messages": ollama_messages,
            "stream": stream,
        }

        # 可选参数
        if "temperature" in self.config:
            params["options"] = params.get("options", {})
            params["options"]["temperature"] = self.config["temperature"]

        if "max_tokens" in self.config and self.config["max_tokens"] > 0:
            params["options"] = params.get("options", {})
            params["options"]["num_predict"] = self.config["max_tokens"]

        # 其他Ollama特定选项
        if "top_p" in self.config:
            params["options"] = params.get("options", {})
            params["options"]["top_p"] = self.config["top_p"]

        if "top_k" in self.config:
            params["options"] = params.get("options", {})
            params["options"]["top_k"] = self.config["top_k"]

        return params

    @handle_errors(component="ollama_api", operation="create_message")
    @log_performance("ollama_api.create_message")
    async def create_message(
        self,
        messages: list[LLMMessage],
        **kwargs,
    ) -> AsyncGenerator[StreamMessages, None]:
        """创建消息，使用Ollama的流式API

        Args:
            messages: 消息列表
            **kwargs: 额外参数

        Yields:
            StreamMessages对象

        """
        if not messages:
            raise ValidationError("messages", messages, "must be non-empty list")

        params = self._prepare_request_params(messages, stream=True, **kwargs)

        self.logger.info(
            f"Creating Ollama message with model: {self.model}",
            context={"message_count": len(messages)},
        )

        endpoint = "api/chat"

        # 创建流式生成器
        async def ollama_stream_generator():
            session = self._get_client_session()
            url = f"{self.base_url}/{endpoint}"

            self.logger.info(f"POST {url}")
            self.logger.debug(f"Request params: {json.dumps(params, indent=2)}")

            try:
                # 准备请求参数（包括代理配置）
                request_kwargs = self._prepare_request_kwargs(params, url)

                async with session.post(url, **request_kwargs) as response:
                    self.logger.info(f"Response status: {response.status}")

                    if response.status != 200:
                        error_text = await response.text()
                        self.logger.error(f"Ollama API error: {error_text}")
                        raise LLMError(
                            f"Ollama API request failed: {response.status} - {error_text}",
                        )

                    # 处理流式响应
                    parser = OllamaParser()

                    async for line in response.content:
                        line = line.decode("utf-8").strip()
                        if not line:
                            continue

                        # Ollama返回NDJSON格式的数据
                        if line.startswith("data: "):
                            data_str = line[6:]  # 移除 "data: " 前缀

                            try:
                                data = json.loads(data_str)

                                # 解析数据块
                                messages = parser.parse_chunk(data)

                                for msg in messages:
                                    yield msg

                            except json.JSONDecodeError as e:
                                # Log and continue - malformed JSON chunks should not break the stream
                                self.logger.warning(f"Failed to parse JSON: {data_str}, error: {e}")
                                continue

                    # 确保最后发送完成消息
                    if not parser.is_done:
                        yield CompleteMessage(
                            user_message_id=local_context.get_message_id(),
                            finish_reason="stop",
                        )

            except (TimeoutError, aiohttp.ClientError, aiohttp.ServerTimeoutError) as e:
                # Network/timeout errors - fast fail with clear message
                self.logger.error(f"Ollama connection error: {e}", exc_info=True)
                raise LLMError(f"Ollama connection failed: {e}")
            except (json.JSONDecodeError, ValueError, KeyError) as e:
                # Data parsing errors - fast fail with clear message
                self.logger.error(f"Ollama response parsing error: {e}", exc_info=True)
                raise LLMError(f"Ollama response parsing failed: {e}")

        # 使用StreamProcessor处理流式响应
        processor = StreamProcessor(provider="ollama")
        task_id = local_context.get_task_id()
        context = local_context.get_task_context()

        async for content in processor.process_message(ollama_stream_generator(), task_id, context):
            yield content

    async def generate(self, messages: list[LLMMessage], **kwargs) -> ChatResult:
        """生成文本（非流式）

        Args:
            messages: 消息列表
            **kwargs: 额外参数

        Returns:
            ChatResult对象

        """
        if not messages:
            raise ValidationError("messages", messages, "must be non-empty list")

        params = self._prepare_request_params(messages, stream=False, **kwargs)

        self.logger.info(f"Generating text with Ollama model: {self.model}")

        endpoint = "api/chat"

        try:
            session = self._get_client_session()
            url = f"{self.base_url}/{endpoint}"

            # 准备请求参数（包括代理配置）
            request_kwargs = self._prepare_request_kwargs(params, url)

            async with session.post(url, **request_kwargs) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise LLMError(f"Ollama API request failed: {response.status} - {error_text}")

                response_data = await response.json()

                # 解析响应
                content = response_data.get("message", {}).get("content", "")

                ai_message = AssistantMessage(content=content)
                generation = ChatGeneration(message=ai_message, text=content, finish_reason="stop")

                # 构建usage信息
                usage = {
                    "prompt_tokens": response_data.get("prompt_eval_count", 0),
                    "completion_tokens": response_data.get("eval_count", 0),
                    "total_tokens": response_data.get("prompt_eval_count", 0) + response_data.get("eval_count", 0),
                }

                return ChatResult(
                    generations=[generation],
                    llm_output={"model_name": self.model},
                    usage=usage,
                    response_metadata=response_data,
                )

        except (aiohttp.ClientError, aiohttp.ServerTimeoutError) as e:
            # Network errors - fast fail with clear message
            self.logger.error(f"Ollama connection error: {e}", exc_info=True)
            raise LLMError(f"Ollama connection failed: {e}")
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            # Data parsing errors - fast fail with clear message
            self.logger.error(f"Ollama response parsing error: {e}", exc_info=True)
            raise LLMError(f"Ollama response parsing failed: {e}")

    async def close(self):
        """关闭客户端连接"""
        if self._session and not self._session.closed:
            await self._session.close()
            self.logger.info("Ollama client closed")


# 工厂函数
def create_ollama_client(config: dict[str, Any]) -> OllamaClient:
    """创建Ollama客户端的工厂函数

    Args:
        config: 配置字典

    Returns:
        OllamaClient实例

    """
    return OllamaClient(config)
