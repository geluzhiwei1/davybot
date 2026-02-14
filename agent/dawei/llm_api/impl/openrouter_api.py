# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""OpenRouter API 客户端实现
基于 TypeScript 版本的 OpenRouterHandler 实现 Python 版本
支持多提供商路由、推理令牌、工具调用和图像生成
"""

import asyncio
import json
import logging
import re
from collections.abc import AsyncGenerator
from typing import Any

import aiohttp
from aiohttp import ClientError, ClientTimeout

from dawei.entity.lm_messages import (
    AssistantMessage,
    LLMMessage,
    SystemMessage,
    UserMessage,
)
from dawei.entity.stream_message import StreamMessages
from dawei.llm_api.base_client import BaseClient
from dawei.llm_api.utils import stream_processor

logger = logging.getLogger(__name__)


class OpenRouterClient(BaseClient):
    """OpenRouter API 客户端
    基于 TypeScript 版本的 OpenRouterHandler 实现
    支持多提供商路由、推理令牌、工具调用和图像生成
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """初始化 OpenRouter 客户端

        Args:
            config: 配置字典，包含以下字段：
                - openRouterBaseUrl: OpenRouter API 基础 URL（默认 https://openrouter.ai/api/v1）
                - openRouterApiKey: API 密钥
                - openRouterModelId: 模型 ID
                - openRouterSpecificProvider: 特定提供商
                - openRouterUseMiddleOutTransform: 是否使用中间输出转换
                - temperature: 温度参数
                - max_tokens: 最大生成令牌数
                - timeout: 请求超时时间（默认 180 秒）
                - maxRetries: 最大重试次数（默认 3）
                - retryDelay: 重试延迟时间（默认 1.0 秒）

        """
        super().__init__(config)

        # OpenRouter 特定配置
        self.base_url = config.get("openRouterBaseUrl", "https://openrouter.ai/api/v1").rstrip("/")
        self.api_key = config.get("openRouterApiKey", "not-provided")
        self.model = config.get("openRouterModelId", "openrouter/auto")
        self.specific_provider = config.get("openRouterSpecificProvider")
        self.use_middle_out_transform = config.get("openRouterUseMiddleOutTransform", True)

        self.temperature = config.get("temperature", 0.7)
        self.max_tokens = config.get("max_tokens")

        # 动态数据
        self.models = {}
        self.endpoints = {}

        # 初始化 timeout 和重试参数
        self.timeout = config.get("timeout", 180)
        self.max_retries = config.get("maxRetries", 3)
        self.retry_delay = config.get("retryDelay", 1.0)

    def _prepare_headers(self) -> dict[str, str]:
        """准备请求头"""
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://github.com/RooVetGit/Roo-Code",
            "X-Title": "Roo Code",
        }

    async def _load_dynamic_models(self) -> None:
        """异步加载动态模型信息

        Note:
            INTENTIONAL TOLERANCE: Model loading failure shouldn't prevent client initialization.
            Errors are logged but empty model cache is used as fallback.

        """
        try:
            # 这里应该调用模型缓存，为了简化直接使用空字典
            # 在实际实现中，应该调用 getModels 和 getModelEndpoints
            self.models = {}
            self.endpoints = {}
        except (ConnectionError, TimeoutError, aiohttp.ClientError) as e:
            # Network/API errors during initialization - log but continue with empty cache
            logger.warning(
                f"[OpenRouterClient] Failed to load dynamic models due to network error: {e}",
            )
        except (KeyError, ValueError, TypeError) as e:
            # Model data parsing error - log but continue with empty cache
            logger.warning(f"[OpenRouterClient] Failed to parse model data: {e}")

    def _convert_messages_to_openai_format(
        self,
        messages: list[LLMMessage],
    ) -> list[dict[str, Any]]:
        """将消息转换为 OpenAI API 格式"""
        openai_messages = []
        for message in messages:
            if isinstance(message, LLMMessage):
                role = "user"
                if isinstance(message, UserMessage):
                    role = "user"
                elif isinstance(message, AssistantMessage):
                    role = "assistant"
                elif isinstance(message, SystemMessage):
                    role = "system"

                openai_messages.append({"role": role, "content": message.content})
            elif isinstance(message, dict):
                openai_messages.append(message)

        return openai_messages

    def _is_deepseek_r1_model(self) -> bool:
        """检查是否为 DeepSeek R1 模型"""
        return self.model.startswith("deepseek/deepseek-r1") or self.model == "perplexity/sonar-reasoning"

    def _add_cache_breakpoints(
        self,
        _system_prompt: str,
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """添加缓存断点（简化实现）"""
        # 这里应该根据模型类型添加不同的缓存断点
        # 为了简化，直接返回原消息
        return messages

    def _prepare_request_params(
        self,
        system_prompt: str,
        messages: list[LLMMessage],
        stream: bool = False,
        **kwargs,
    ) -> dict[str, Any]:
        """准备请求参数"""
        openai_messages = self._convert_messages_to_openai_format(messages)

        # 添加系统提示
        full_messages = [{"role": "system", "content": system_prompt}, *openai_messages]

        # DeepSeek R1 特殊处理
        if self._is_deepseek_r1_model():
            # 将系统提示转换为用户消息并包装在 think 标签中
            wrapped_system = f"<think>\n{system_prompt}\n</think>"
            full_messages = [
                {"role": "user", "content": wrapped_system},
                *openai_messages,
            ]

        # 添加缓存断点
        full_messages = self._add_cache_breakpoints(system_prompt, full_messages)

        # 基础参数
        params = {
            "model": self.model,
            "messages": full_messages,
            "stream": stream,
            "stream_options": {"include_usage": True},
            "parallel_tool_calls": False,  # 确保一次只有一个工具调用
        }

        # 添加温度
        if self._is_deepseek_r1_model():
            params["temperature"] = 0.7  # DeepSeek R1 默认温度
        else:
            params["temperature"] = self.temperature

        # 添加 max_tokens
        if self.max_tokens:
            params["max_tokens"] = self.max_tokens

        # 添加转换
        if self.use_middle_out_transform:
            params["transforms"] = ["middle-out"]

        # 添加特定提供商
        if self.specific_provider and self.specific_provider != "[default]":
            params["provider"] = {
                "order": [self.specific_provider],
                "only": [self.specific_provider],
                "allow_fallbacks": False,
            }

        # 添加推理参数
        if kwargs.get("reasoning"):
            params["reasoning"] = kwargs["reasoning"]

        return params

    async def _make_stream_request(
        self,
        endpoint: str,
        params: dict[str, Any],
    ) -> AsyncGenerator[dict[str, Any], None]:
        """发送流式请求到 OpenRouter API

        Args:
            endpoint: API 端点
            params: 请求参数

        Yields:
            流式响应块

        """
        url = f"{self.base_url}/{endpoint}"

        async with aiohttp.ClientSession(
            timeout=ClientTimeout(total=self.timeout),
            headers=self._prepare_headers(),
        ) as session:
            retry_count = 0

            while retry_count < self.max_retries:
                try:
                    async with session.post(url, json=params) as response:
                        if response.status == 200:
                            async for line in response.content:
                                line = line.decode("utf-8").strip()
                                if line.startswith("data: "):
                                    data = line[6:]
                                    if data == "[DONE]":
                                        continue
                                    try:
                                        yield json.loads(data)
                                    except json.JSONDecodeError:
                                        continue
                        else:
                            error_text = await response.text()
                            logger.error(f"OpenRouter API error: {response.status} - {error_text}")
                            raise aiohttp.ClientResponseError(
                                request_info=response.request_info,
                                history=response.history,
                                status=response.status,
                                message=f"OpenRouter API error: {response.status}",
                            )
                            break

                except (TimeoutError, ClientError) as e:
                    retry_count += 1
                    if retry_count < self.max_retries:
                        delay = self.retry_delay * retry_count
                        logger.warning(
                            f"Retry {retry_count}/{self.max_retries} after {delay}s: {e}",
                        )
                        await asyncio.sleep(delay)
                        continue
                    else:
                        logger.error(
                            f"Max retries exceeded for _make_stream_request: {e}",
                            exc_info=True,
                        )
                        raise ConnectionError(
                            f"OpenRouter API connection failed after {self.max_retries} retries: {e}",
                        )

    async def create_message(
        self,
        messages: list[LLMMessage],
        **kwargs,
    ) -> AsyncGenerator[StreamMessages, None]:
        """创建消息并返回流式响应
        与其他客户端保持一致的接口

        Args:
            messages: 消息列表
            **kwargs: 其他参数

        Yields:
            流式响应块

        Raises:
            ValueError: If messages are invalid
            ConnectionError: If API connection fails
            aiohttp.ClientError: If HTTP request fails

        """
        try:
            # 获取模型信息用于日志记录
            model_info = self.get_model_info()
            model_name = model_info.get("name", "unknown")

            logger.info(f"Creating message with model: {model_name}")

            # 从 kwargs 中获取 system_prompt
            system_prompt = kwargs.get("system_prompt", "")

            # 准备请求参数
            params = self._prepare_request_params(system_prompt, messages, stream=True, **kwargs)

            # 使用 OpenRouter 的 API 端点
            endpoint = "chat/completions"

            # 创建原始流数据生成器
            async def raw_stream_generator():
                async for chunk in self._make_stream_request(endpoint, params):
                    yield chunk

            # 使用流式处理器处理数据并返回 BaseStreamMessage
            async for message in stream_processor.process_stream(raw_stream_generator()):
                yield message

        except (ValueError, TypeError, KeyError) as e:
            # Message preparation error - fast fail
            logger.error(f"Invalid message format in create_message: {e}", exc_info=True)
            raise ValueError(f"Failed to prepare messages: {e}")
        except (TimeoutError, ConnectionError, aiohttp.ClientError) as e:
            # Network/API error - fast fail
            logger.error(f"API request failed in create_message: {e}", exc_info=True)
            raise
        except Exception as e:
            # Unexpected error - log and fast fail
            logger.critical(f"Unexpected error in create_message: {e}", exc_info=True)
            raise RuntimeError(f"Unexpected error in message creation: {e}")

    async def generate_image(
        self,
        prompt: str,
        model: str,
        api_key: str,
        input_image: str | None = None,
    ) -> dict[str, Any]:
        """生成图像

        Args:
            prompt: 文本提示
            model: 使用的模型
            api_key: OpenRouter API 密钥（必须显式提供）
            input_image: 可选的 base64 编码输入图像数据

        Returns:
            生成的图像数据和格式，或错误

        """
        if not api_key:
            return {
                "success": False,
                "error": "OpenRouter API key is required for image generation",
            }

        try:
            url = f"{self.base_url}/chat/completions"

            # 准备请求体
            messages = []
            if input_image:
                messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt,
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": input_image,
                                },
                            },
                        ],
                    },
                )
            else:
                messages.append(
                    {
                        "role": "user",
                        "content": prompt,
                    },
                )

            request_body = {
                "model": model,
                "messages": messages,
                "modalities": ["image", "text"],
            }

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/RooVetGit/Roo-Code",
                "X-Title": "Roo Code",
            }

            logger.info(f"Generating image with model: {model}")

            async with aiohttp.ClientSession(headers=headers) as session, session.post(url, json=request_body) as response:
                if not response.ok:
                    error_text = await response.text()
                    error_message = f"Failed to generate image: {response.status} {response.status_text}"
                    try:
                        error_json = json.loads(error_text)
                        if error_json.get("error", {}).get("message"):
                            error_message = f"Failed to generate image: {error_json['error']['message']}"
                    except (
                        json.JSONDecodeError,
                        KeyError,
                        TypeError,
                    ) as parse_error:
                        # 错误响应解析失败，使用默认错误消息
                        logger.debug(f"Failed to parse error response JSON: {parse_error}")
                    except Exception as e:
                        # 未预期的错误
                        logger.warning(
                            f"Unexpected error parsing error response: {e}",
                            exc_info=True,
                        )

                    return {
                        "success": False,
                        "error": error_message,
                    }

                result = await response.json()

                if result.get("error"):
                    return {
                        "success": False,
                        "error": f"Failed to generate image: {result['error']['message']}",
                    }

                # 提取生成的图像
                images = result.get("choices", [{}])[0].get("message", {}).get("images", [])
                if not images or len(images) == 0:
                    return {
                        "success": False,
                        "error": "No image was generated in the response",
                    }

                image_data = images[0].get("image_url", {}).get("url", "")
                if not image_data:
                    return {
                        "success": False,
                        "error": "Invalid image data in response",
                    }

                # 提取 base64 数据
                base64_match = re.match(r"^data:image/(png|jpeg|jpg);base64,(.+)$", image_data)
                if not base64_match:
                    return {
                        "success": False,
                        "error": "Invalid image format received",
                    }

                return {
                    "success": True,
                    "imageData": image_data,
                    "imageFormat": base64_match.group(1),
                }

        except (TimeoutError, aiohttp.ClientError) as e:
            # Network/API error - return error dict (graceful degradation for image API)
            logger.error(f"Image generation API request failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Network error during image generation: {e!s}",
            }
        except (ValueError, KeyError) as e:
            # Response parsing error - return error dict
            logger.error(f"Failed to parse image generation response: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Invalid response format: {e!s}",
            }
        except Exception as e:
            # Unexpected error - return error dict
            logger.critical(f"Unexpected error in generate_image: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Unexpected error: {str(e) if hasattr(e, '__str__') else 'Unknown error'}",
            }

    def get_model_info(self) -> dict[str, Any]:
        """获取模型信息

        Returns:
            包含模型信息的字典

        """
        return {
            "id": self.model,
            "name": self.model,
            "provider": "openrouter",
            "base_url": self.base_url,
            "type": "openrouter",
            "temperature": self.temperature,
            "timeout": self.timeout,
            "max_retries": self.max_retries,
            "retry_delay": self.retry_delay,
            "max_tokens": self.max_tokens,
            "specific_provider": self.specific_provider,
            "use_middle_out_transform": self.use_middle_out_transform,
            "is_deepseek_r1": self._is_deepseek_r1_model(),
        }

    def __repr__(self) -> str:
        return f"OpenRouterClient(model={self.model}, base_url={self.base_url})"
