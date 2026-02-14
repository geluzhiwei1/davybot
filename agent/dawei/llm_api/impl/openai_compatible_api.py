# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""OpenAI兼容客户端实现
使用aiohttp实现异步HTTP请求，支持OpenAI API格式的各种LLM服务
"""

import json
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dawei.core import local_context
from dawei.core.error_handler import handle_errors
from dawei.core.errors import LLMError, ValidationError
from dawei.core.metrics import increment_counter
from dawei.entity.lm_messages import (
    AssistantMessage,
    LLMMessage,
    ChatGeneration,
    ChatResult,
    FunctionCall,
    ToolCall,
)
from dawei.entity.stream_message import (
    CompleteMessage,
    ContentMessage,
    ReasoningMessage,
    StreamMessages,
    ToolCallMessage,
    UsageMessage,
)
from dawei.llm_api.base_client import BaseClient
from dawei.llm_api.base_llm_api import StreamChunkParser
from dawei.logg.logging import get_logger, log_performance

from .stream_processor import StreamProcessor

logger = get_logger(__name__)


class OpenaiCompatibleClient(BaseClient):
    """OpenAI兼容的LLM客户端，实现LLMProvider接口
    使用aiohttp实现异步HTTP请求，支持流式和非流式响应

    该类直接实现了LLMProvider接口，提供了与Task模块兼容的API，
    同时保持了原有的generate()和stream_generate()方法以确保向后兼容性。
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """初始化OpenAI兼容客户端

        Args:
            config: LLM配置字典，包含以下字段：
                - apiProvider: 提供商类型（openai、ollama、gemini、deepseek等）
                - openAiBaseUrl: OpenAI兼容API的基础URL
                - openAiApiKey: API密钥
                - openAiModelId: 模型ID
                - temperature: 温度参数（默认0.7）
                - max_tokens: 最大生成令牌数
                - timeout: 请求超时时间（默认180秒）
                - maxRetries: 最大重试次数（默认3）
                - retryDelay: 重试延迟时间（默认1.0秒）
                - reasoningEffort: 推理努力程度（可选）
                - openAiLegacyFormat: 是否使用旧格式（默认False）
                - openAiCustomModelInfo: 自定义模型信息
                - openAiHeaders: 自定义请求头

        """
        super().__init__(config)

        # 初始化logger属性
        self.logger = logger

        self.provider = config.get("apiProvider", "openai")

        # 根据provider获取配置
        if self.provider == "ollama":
            self.base_url = config.get("ollamaBaseUrl", "http://localhost:11434").rstrip("/")
            self.api_key = config.get("ollamaApiKey", "ollama")
            self.model = config.get("ollamaModelId", "llama3.1")
        else:  # 默认为openai兼容
            # 支持两种字段名：openAiBaseUrl（原始配置）和 base_url（LLMConfig内部字段）
            self.base_url = config.get("openAiBaseUrl", config.get("base_url", "")).rstrip("/")
            # 支持两种字段名：openAiApiKey（原始配置）和 api_key（LLMConfig内部字段）
            self.api_key = config.get("openAiApiKey", config.get("api_key", ""))
            # 支持两种字段名：openAiModelId（原始配置）和 model_id（LLMConfig内部字段）
            self.model = config.get("openAiModelId", config.get("model_id", ""))

        # 验证配置 - 使用断言式验证替代assert
        if not self.base_url or not self.base_url.startswith("http"):
            raise ValidationError("base_url", self.base_url, "must be a valid HTTP/HTTPS URL")

        # roo code 特有配置
        self.reasoning_effort = config.get("reasoningEffort", config.get("reasoning_effort"))
        self.legacy_format = config.get("openAiLegacyFormat", False)
        # 支持两种字段名：openAiCustomModelInfo（原始配置）和 custom_model_info（LLMConfig内部字段）
        self.custom_model_info = config.get(
            "openAiCustomModelInfo",
            config.get("custom_model_info", {}),
        )
        self.max_context_tokens = self.custom_model_info.get("max_context_tokens")
        self.max_output_tokens = self.custom_model_info.get("max_output_tokens")

        # 移除tiktoken依赖，使用简单的字符数估算
        self.encoding = None

        # 设置默认参数
        self.default_params = {
            "model": self.model,
            "temperature": config.get("temperature", 0.7),
            # "max_tokens": config.get("max_tokens"),
            # "top_p": config.get("top_p", 1.0),
            # "frequency_penalty": config.get("frequency_penalty", 0.0),
            # "presence_penalty": config.get("presence_penalty", 0.0),
            "stream": False,
        }

    def _prepare_headers(self) -> dict[str, str]:
        """准备请求头"""
        headers = {
            "Content-Type": "application/json",
            # Mimic headers sent by the VSCode extension
            "HTTP-Referer": "https://github.com/RooVetGit/Roo-Cline",
            "X-Title": "Roo Code",
            "User-Agent": "RooCode/3.38.0",  # Hardcoded version for testing
        }

        # roo code 自定义headers
        # 支持两种字段名：openAiHeaders（原始配置）和 custom_headers（LLMConfig内部字段）
        custom_headers = self.config.get("openAiHeaders", self.config.get("custom_headers"))
        if custom_headers and isinstance(custom_headers, dict):
            headers.update(custom_headers)

        # 认证
        if "Authorization" not in headers:
            if self.provider == "gemini":
                # Gemini uses API key in URL, not header
                pass
            elif self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

        return headers

    @handle_errors(component="openai_compatible_api", operation="prepare_log_files")
    def _prepare_log_files(
        self,
        workspace_path: str,
        _endpoint: str,
    ) -> tuple[Path | None, Path | None]:
        """准备日志文件路径

        Args:
            workspace_path: 工作空间路径
            endpoint: API端点

        Returns:
            (request_log_file, response_log_file): 日志文件路径元组

        """
        if not workspace_path:
            return None, None

        log_dir = Path(workspace_path) / ".dawei" / "http"
        log_dir.mkdir(parents=True, exist_ok=True)

        # 生成唯一的日志文件名（基于时间戳）
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        request_log_file = log_dir / f"{timestamp}_request.json"
        response_log_file = log_dir / f"{timestamp}_response.json"

        return request_log_file, response_log_file

    def _log_request(self, request_log_file: Path, endpoint: str, params: dict[str, Any]) -> None:
        """记录请求日志

        Args:
            request_log_file: 请求日志文件路径
            endpoint: API端点
            params: 请求参数

        """
        if not request_log_file:
            return

        request_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "url": f"{self.base_url}/{endpoint}",
            "headers": dict(self._prepare_headers()),
            "params": params,
            "provider": self.provider,
            "model": self.model,
        }

        with request_log_file.open("w", encoding="utf-8") as f:
            json.dump(request_data, f, indent=2, ensure_ascii=False)
        logger.info(f"Request logged to: {request_log_file}")

    @handle_errors(component="openai_compatible_api", operation="execute_http_request")
    @log_performance("openai_compatible_api.execute_http_request")
    async def _execute_http_request(
        self,
        workspace_path: str,
        response_log_file: Path | None,
        endpoint: str,
        params: dict[str, Any],
        _url_suffix: str,
        _original_url: str,
    ) -> tuple[AsyncGenerator[bytes, None], int | None, dict[str, str] | None, str | None]:
        """执行HTTP请求并返回流式响应生成器（带保护层）

        集成了速率限制器、断路器和监控指标

        Args:
            workspace_path: 工作空间路径
            response_log_file: 响应日志文件路径
            endpoint: API端点
            params: 请求参数
            url_suffix: URL后缀
            original_url: 原始URL

        Returns:
            (response_stream, response_status, response_headers, url): 响应流生成器元组

        """
        # ✅ 获取断路器
        circuit_breaker = self._get_circuit_breaker()
        url = f"{self.base_url}/{endpoint}"
        provider = self.get_provider_name()
        model = getattr(self, "model", "unknown")

        # ✅ 定义受保护的流式请求函数
        async def make_protected_streaming_request():
            # 0. 防御性惰性初始化
            BaseClient._ensure_rate_limiter(self.config)

            # 1. 速率限制检查
            success, wait_time = await BaseClient._global_rate_limiter.acquire(timeout=30.0)

            if not success:
                raise Exception(f"Rate limit exceeded, wait time: {wait_time:.1f}s")

            logger.info(f"✅ [RATE_LIMITER] Acquired token for {provider}:{model}")

            try:
                # 2. 执行实际的流式请求
                session = self._get_client_session()

                async def response_stream_generator():
                    """内部流式响应生成器"""
                    response_chunks_for_logging = []
                    response_status_local = None
                    response_headers_local = None
                    url_local = url

                    try:
                        async with session.post(url, json=params) as response:
                            response_status_local = response.status
                            response_headers_local = dict(response.headers)

                            if response.status != 200:
                                error_text = await response.text()

                                # 记录错误响应日志
                                if workspace_path and response_log_file:
                                    self._log_error_response(
                                        response_log_file,
                                        response_status_local,
                                        response_headers_local,
                                        error_text,
                                        url_local,
                                    )

                                raise LLMError(
                                    self.provider,
                                    f"HTTP {response.status}: {error_text}",
                                )

                            # 实时流式处理：立即 yield 每个数据块，同时收集用于日志记录
                            async for chunk in response.content:
                                # 立即 yield 数据块以实现实时流式处理
                                yield chunk
                                # 同时收集数据块用于后续日志记录
                                response_chunks_for_logging.append(chunk)

                    finally:
                        # 确保响应日志一定被记录，无论流是否完全消费
                        if workspace_path and response_log_file:
                            self._log_response(
                                response_log_file,
                                response_chunks_for_logging,
                                response_status_local,
                                response_headers_local,
                                url_local,
                            )

                        self.logger.info(
                            "HTTP request completed",
                            context={
                                "endpoint": endpoint,
                                "status": response_status_local,
                                "provider": self.provider,
                                "component": "openai_compatible_api",
                            },
                        )
                        increment_counter(
                            "openai_compatible_api.http_requests",
                            tags={
                                "provider": self.provider,
                                "status": "success" if response_status_local == 200 else "error",
                            },
                        )

                return response_stream_generator(), None, None, url

            except Exception as e:
                # 3. 记录失败
                error_str = str(e)
                is_rate_limit = "429" in error_str or "rate_limit" in error_str.lower()
                BaseClient._global_rate_limiter.record_failure(is_rate_limit=is_rate_limit)
                logger.exception("❌ [RATE_LIMITER] Request failed for {provider}:{model}: ")
                raise

        # ✅ 通过断路器调用（自动重试）
        logger.info(f"🔄 [CIRCUIT_BREAKER] Executing streaming request for {provider}:{model}")
        result = await circuit_breaker.call(make_protected_streaming_request)

        # ✅ 记录成功
        BaseClient._global_rate_limiter.record_success()
        logger.info(f"✅ [RATE_LIMITER] Request completed successfully for {provider}:{model}")

        return result

    def _log_error_response(
        self,
        response_log_file: Path,
        status: int,
        headers: dict[str, str],
        error_text: str,
        url: str,
    ) -> None:
        """记录错误响应日志

        Args:
            response_log_file: 响应日志文件路径
            status: HTTP状态码
            headers: 响应头
            error_text: 错误文本
            url: 请求URL

        Raises:
            OSError: 文件写入失败
            ValueError: 数据序列化失败

        """
        error_response_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "headers": headers,
            "error": error_text,
            "url": url,
        }

        with response_log_file.open("w", encoding="utf-8") as f:
            json.dump(error_response_data, f, indent=2, ensure_ascii=False)
        logger.info(f"Error response logged to: {response_log_file}")

    def _log_response(
        self,
        response_log_file: Path,
        response_chunks: list[bytes],
        status: int | None,
        headers: dict[str, str] | None,
        url: str | None,
    ) -> None:
        """记录响应日志

        Args:
            response_log_file: 响应日志文件路径
            response_chunks: 响应数据块列表
            status: HTTP状态码
            headers: 响应头
            url: 请求URL

        Raises:
            OSError: 文件写入失败
            ValueError: 数据序列化失败

        """
        if response_chunks:
            # 有响应数据时的日志
            combined_bytes = b"".join(response_chunks)
            response_text = combined_bytes.decode("utf-8", errors="ignore")

            response_data = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": status or "unknown",
                "headers": headers or {},
                "url": url or "unknown",
                "raw_response": response_text,
                "chunks_count": len(response_chunks),
                "total_bytes": len(combined_bytes),
            }
        else:
            # 没有响应数据时的日志
            response_data = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": status or "unknown",
                "headers": headers or {},
                "url": url or "unknown",
                "raw_response": "",
                "chunks_count": 0,
                "total_bytes": 0,
                "note": "No response chunks captured",
            }

        with response_log_file.open("w", encoding="utf-8") as f:
            json.dump(response_data, f, indent=2, ensure_ascii=False)
        logger.info(f"Response logged to: {response_log_file}")

    def get_num_tokens(self, text: str) -> int:
        """估算文本的令牌数量（不使用tiktoken）"""
        if not text:
            return 0
        # 使用简单的字符数估算：平均4个字符约等于1个token
        # 这是一个粗略的估算，对于中文可能不太准确，但足够用于基本的token限制
        return len(text) // 4

    def get_num_tokens_from_messages(self, messages: list[dict[str, Any]]) -> int:
        """计算消息列表的总令牌数"""
        total_tokens = 0
        for message in messages:
            content = message.get("content", "")
            if isinstance(content, list):
                # 处理多模态内容格式
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        text_content = item.get("text", "")
                        total_tokens += self.get_num_tokens(text_content)
            else:
                # 处理纯文本内容
                total_tokens += self.get_num_tokens(content)
        return total_tokens

    def _prepare_request_params(self, messages: list[LLMMessage], **kwargs) -> dict[str, Any]:
        """准备请求参数"""
        params = {**self.default_params, **kwargs}

        # 转换消息为字典格式，确保JSON序列化兼容
        serialized_messages = []
        for message in messages:
            if hasattr(message, "to_dict"):
                serialized_messages.append(message.to_dict())
            else:
                serialized_messages.append(message)

        params["messages"] = serialized_messages

        # if params.get("top_p") == 1.0:
        #     del params["top_p"]
        # if params.get("frequency_penalty") == 0.0:
        #     del params["frequency_penalty"]
        # if params.get("presence_penalty") == 0.0:
        #     del params["presence_penalty"]

        params["stream"] = True
        params["tool_stream"] = True

        # # 添加 reasoning_effort
        # if self.reasoning_effort is not None:
        #     params["reasoning_effort"] = self.reasoning_effort

        # 自动调整 max_tokens
        # if self.max_context_tokens and params.get("max_tokens") is None:
        #     prompt_tokens = self.get_num_tokens_from_messages(openai_messages)
        #     available_tokens = self.max_context_tokens - prompt_tokens

        #     available_tokens -= 100  # Buffer

        #     if self.max_output_tokens:
        #         params["max_tokens"] = min(available_tokens, self.max_output_tokens)
        #     else:
        #         params["max_tokens"] = max(256, available_tokens)

        #     if params["max_tokens"] <= 0:
        #         raise ValueError("Prompt is too long, not enough tokens for generation.")

        return params

    def _convert_response_to_chat_result(self, response_data: dict[str, Any]) -> ChatResult:
        """将API响应转换为ChatResult"""
        choices = response_data.get("choices", [])
        generations = []

        for choice in choices:
            message_data = choice.get("message", {})
            content = message_data.get("content", "")

            ai_message = AssistantMessage(content=content)

            generation = ChatGeneration(
                message=ai_message,
                text=content,
                finish_reason=choice.get("finish_reason"),
                generation_info=choice.get("logprobs"),
            )
            generations.append(generation)

        return ChatResult(
            generations=generations,
            llm_output=({"model_name": response_data.get("model")} if isinstance(response_data.get("model"), str) else response_data.get("model")),
            usage=response_data.get("usage"),
            response_metadata=response_data,
        )

    @handle_errors(component="openai_compatible_api", operation="make_http_request")
    @log_performance("openai_compatible_api.make_http_request")
    async def _make_http_request(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        """执行单次HTTP请求"""
        # 处理 Gemini 特殊情况
        url_suffix = f"?key={self.api_key}" if self.provider == "gemini" else ""
        original_url = self.base_url
        if url_suffix:
            self.base_url = self.base_url + url_suffix

        # 直接调用，移除冗余错误处理
        result = await super()._make_http_request(endpoint, params)

        # 恢复原始 base_url
        if url_suffix:
            self.base_url = original_url

        self.logger.info(
            "HTTP request completed",
            context={
                "endpoint": endpoint,
                "provider": self.provider,
                "component": "openai_compatible_api",
            },
        )
        increment_counter(
            "openai_compatible_api.http_requests",
            tags={"provider": self.provider, "status": "success"},
        )

        return result

    @handle_errors(component="openai_compatible_api", operation="create_message")
    @log_performance("openai_compatible_api.create_message")
    async def create_message(
        self,
        messages: list[LLMMessage],
        **kwargs,
    ) -> AsyncGenerator[StreamMessages, None]:
        """创建消息，支持推理过程、内容和工具调用的分别处理"""
        # 验证输入
        if not messages:
            raise ValidationError("messages", messages, "must be non-empty list")

        # 准备请求参数
        params = self._prepare_request_params(messages, stream=True, **kwargs)

        self.logger.info(
            "Creating message",
            context={
                "model": self.model,
                "message_count": len(messages),
                "component": "openai_compatible_api",
            },
        )

        endpoint = "chat/completions"
        if self.provider == "ollama":
            endpoint = "api/chat"

        # 创建原始流数据生成器
        async def raw_stream_generator():
            # 处理 Gemini 特殊情况
            url_suffix = f"?key={self.api_key}" if self.provider == "gemini" else ""
            original_url = self.base_url
            if url_suffix:
                self.base_url = self.base_url + url_suffix

            # 准备日志目录和文件
            workspace_path = self.config.get("workspace_path", "")
            request_log_file, response_log_file = self._prepare_log_files(workspace_path, endpoint)

            # 记录请求日志
            if request_log_file:
                self._log_request(request_log_file, endpoint, params)

            # 执行HTTP请求并获取流式响应生成器
            (
                response_stream,
                _response_status,
                _response_headers,
                _url,
            ) = await self._execute_http_request(
                workspace_path,
                response_log_file,
                endpoint,
                params,
                url_suffix,
                original_url,
            )

            # 恢复原始 base_url
            if url_suffix:
                self.base_url = original_url

            # 实时流式处理：直接 yield 流式响应中的每个数据块
            async for chunk in response_stream:
                yield chunk

        # 使用流式处理器处理数据并直接返回 BaseStreamMessage
        stream_processor = StreamProcessor(provider=self.provider)
        async for message in stream_processor.process_stream(raw_stream_generator()):
            yield message

        increment_counter(
            "openai_compatible_api.messages_created",
            tags={"provider": self.provider, "message_count": len(messages)},
        )

    @handle_errors(component="openai_compatible_api", operation="astream_chat_completion")
    @log_performance("openai_compatible_api.astream_chat_completion")
    async def astream_chat_completion(
        self,
        messages: list[LLMMessage],
        **kwargs,
    ) -> AsyncGenerator[StreamMessages, None]:
        """异步流式聊天完成，兼容旧接口

        Args:
            messages: 消息列表
            **kwargs: 其他参数

        Returns:
            流式响应生成器

        """
        # 验证输入
        if not messages:
            raise ValidationError("messages", messages, "must be non-empty list")

        # 直接调用 create_message 方法以保持兼容性
        async for message in self.create_message(messages, **kwargs):
            yield message

        increment_counter(
            "openai_compatible_api.stream_chat_completions",
            tags={"provider": self.provider, "message_count": len(messages)},
        )


class OpenAICompatibleParser(StreamChunkParser):
    """OpenAI兼容API的流式数据解析器，每次请求使用新的实例"""

    def __init__(self):
        self.reasoning_content = ""
        self.content = ""
        self.final_tool_calls = {}
        self.tool_call_buffers = {}  # 为每个工具调用维护参数缓冲区
        self.reasoning_started = False
        self.content_started = False
        self.final_usage = None

    def parse_chunk(self, chunk: dict[str, Any]) -> list[StreamMessages]:
        """解析OpenAI兼容格式的数据块"""
        messages = []

        # 解析 chunk 顶层字段
        chunk_id = chunk.get("id")
        chunk_created = chunk.get("created")
        chunk_object = chunk.get("object")
        chunk_model = chunk.get("model")

        # 检查是否有 usage 信息
        if chunk.get("usage"):
            usage_data = chunk.get("usage", {})
            self.final_usage = usage_data
            messages.append(
                UsageMessage(
                    user_message_id=local_context.get_message_id(),
                    data=usage_data,
                    id=chunk_id,
                    created=chunk_created,
                    object=chunk_object,
                    model=chunk_model,
                ),
            )

        if not chunk.get("choices"):
            return messages

        delta = chunk["choices"][0].get("delta", {})

        # 【DEBUG】记录收到的原始delta，用于调试GLM等模型的内容显示问题
        if delta:  # 只在delta非空时记录
            logger.info(f"[LLM_STREAM] Received delta: keys={list(delta.keys())}, has_reasoning={bool(delta.get('reasoning_content'))}, has_content={bool(delta.get('content'))}, has_tool_calls={bool(delta.get('tool_calls'))}")
            if delta.get("reasoning_content"):
                logger.info(f"[LLM_STREAM] reasoning_content preview: {delta['reasoning_content'][:100]!r}")
            if delta.get("content"):
                logger.info(f"[LLM_STREAM] content preview: {delta['content'][:100]!r}")

        # 处理流式推理过程输出
        if delta.get("reasoning_content"):
            reasoning_delta = delta["reasoning_content"]
            # 【关键修复】只处理有实际内容的部分，完全跳过空白或仅包含空白字符的内容
            # 过滤掉只有空格、换行符、制表符等空白字符的内容
            if reasoning_delta and reasoning_delta.strip():
                if not self.reasoning_started:
                    self.reasoning_started = True
                self.reasoning_content += reasoning_delta

                messages.append(
                    ReasoningMessage(
                        user_message_id=local_context.get_message_id(),
                        content=reasoning_delta,
                        id=chunk_id,
                        created=chunk_created,
                        object=chunk_object,
                        model=chunk_model,
                    ),
                )

                # 【关键修复】如果还没有content，也创建ContentMessage以确保assistant气泡能显示
                # 这是为了处理GLM等模型将所有文本放在reasoning_content中的情况
                if not self.content:
                    self.content += reasoning_delta
                    messages.append(
                        ContentMessage(
                            user_message_id=local_context.get_message_id(),
                            content=reasoning_delta,
                            id=chunk_id,
                            created=chunk_created,
                            object=chunk_object,
                            model=chunk_model,
                        ),
                    )
            # 记录被过滤的空推理内容（便于调试）
            elif reasoning_delta:
                logger.debug(f"Filtered empty reasoning content: {reasoning_delta!r}")

        # 处理流式回答内容输出
        if delta.get("content"):
            content_delta = delta["content"]
            # 【关键修复】只处理有实际内容的部分，完全跳过空白或仅包含空白字符的内容
            # 过滤掉只有空格、换行符、制表符等空白字符的内容
            if content_delta and content_delta.strip():
                if not self.content_started:
                    self.content_started = True
                self.content += content_delta

                messages.append(
                    ContentMessage(
                        user_message_id=local_context.get_message_id(),
                        content=content_delta,
                        id=chunk_id,
                        created=chunk_created,
                        object=chunk_object,
                        model=chunk_model,
                    ),
                )
            # 记录被过滤的空内容（便于调试）
            elif content_delta:
                logger.debug(f"Filtered empty content: {content_delta!r}")

        # 处理流式工具调用信息
        if delta.get("tool_calls"):
            for tool_call in delta.get("tool_calls", []):
                index = tool_call.get("index")

                # 初始化工具调用缓冲区
                if index not in self.tool_call_buffers:
                    self.tool_call_buffers[index] = {
                        "id": tool_call.get("id", ""),
                        "type": tool_call.get("type", "function"),
                        "function": {
                            "name": tool_call.get("function", {}).get("name", ""),
                            "arguments": "",  # 初始化空的参数缓冲区
                        },
                    }
                    self.final_tool_calls[index] = self.tool_call_buffers[index].copy()

                # 缓冲参数片段
                arguments_delta = tool_call.get("function", {}).get("arguments", "")
                if arguments_delta:
                    self.tool_call_buffers[index]["function"]["arguments"] += arguments_delta

                # 更新函数名（如果存在）
                if tool_call.get("function", {}).get("name"):
                    self.tool_call_buffers[index]["function"]["name"] = tool_call.get(
                        "function",
                        {},
                    ).get("name")

                # 同步到 final_tool_calls
                self.final_tool_calls[index] = self.tool_call_buffers[index].copy()

                # 创建当前数据块的 ToolCall 对象，使用缓冲的完整参数
                current_arguments = self.tool_call_buffers[index]["function"]["arguments"]
                tool_call_obj = ToolCall(
                    tool_call_id=self.tool_call_buffers[index]["id"],
                    type=self.tool_call_buffers[index]["type"],
                    function=FunctionCall(
                        name=self.tool_call_buffers[index]["function"]["name"],
                        arguments=current_arguments,
                    ),
                )

                # 将所有工具调用字典转换为 ToolCall 对象列表
                all_tool_calls = []
                for tc_dict in self.final_tool_calls.values():
                    all_tool_calls.append(
                        ToolCall(
                            tool_call_id=tc_dict.get("id", ""),
                            type=tc_dict.get("type", "function"),
                            function=FunctionCall(
                                name=tc_dict.get("function", {}).get("name", ""),
                                arguments=tc_dict.get("function", {}).get("arguments", "{}"),
                            ),
                        ),
                    )

                messages.append(
                    ToolCallMessage(
                        user_message_id=local_context.get_message_id(),
                        tool_call=tool_call_obj,
                        all_tool_calls=all_tool_calls,
                        id=chunk_id,
                        created=chunk_created,
                        object=chunk_object,
                        model=chunk_model,
                    ),
                )

        return messages

    def complete(self, chunk: dict[str, Any]) -> CompleteMessage:
        """创建完成消息"""
        # 将工具调用字典转换为 ToolCall 对象列表，使用缓冲的完整参数
        tool_calls = []
        for tc_dict in self.final_tool_calls.values():
            # 【关键修复】优先使用缓冲区中的完整参数
            arguments = tc_dict.get("function", {}).get("arguments", "{}")
            if not arguments or arguments == "{}":
                # 如果参数为空，尝试从缓冲区获取
                index = None
                for idx, buffered_tc in self.tool_call_buffers.items():
                    if buffered_tc["id"] == tc_dict.get("id"):
                        index = idx
                        break
                if index is not None and self.tool_call_buffers[index]["function"]["arguments"]:
                    arguments = self.tool_call_buffers[index]["function"]["arguments"]

            tool_calls.append(
                ToolCall(
                    tool_call_id=tc_dict.get("id", ""),
                    type=tc_dict.get("type", "function"),
                    function=FunctionCall(
                        name=tc_dict.get("function", {}).get("name", ""),
                        arguments=arguments,
                    ),
                ),
            )

        # 获取完成原因，如果chunk为空或没有choices，则默认为"stop"
        finish_reason = "stop"
        if chunk and chunk.get("choices"):
            finish_reason = chunk["choices"][0].get("finish_reason", "stop")

        # 【关键修复】当content为空但reasoning_content有内容时，将reasoning_content复制到content
        # 这是为了处理GLM等模型将所有文本放在reasoning_content中的情况
        final_content = self.content
        if (not final_content or not final_content.strip()) and self.reasoning_content and self.reasoning_content.strip():
            logger.info(
                f"Copying reasoning_content to content as content field is empty. Reasoning length: {len(self.reasoning_content)}",
            )
            final_content = self.reasoning_content

        return CompleteMessage(
            reasoning_content=self.reasoning_content,
            content=final_content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage=self.final_usage,
        )
