# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""LLM 客户端工厂

负责创建 LLM 客户端实例，遵循单一职责原则
支持所有提供 OpenAI 兼容 API 的提供商
"""

import logging
from typing import Any

from dawei.core.exceptions import ConfigurationError
from dawei.llm_api.base_llm_api import LlmApi
from dawei.llm_api.impl.openai_compatible_api import OpenaiCompatibleClient

logger = logging.getLogger(__name__)


class LLMClientFactory:
    """LLM 客户端工厂

    根据配置创建对应的 LLM 客户端实例

    KISS 原则：大多数提供商使用 OpenAI 兼容 API，统一使用 OpenaiCompatibleClient
    只需要配置正确的 base_url 和 api_key 即可
    """

    SUPPORTED_PROVIDERS = {
        # OpenAI 官方
        "openai": OpenaiCompatibleClient,
        # 国内提供商（OpenAI 兼容）
        "deepseek": OpenaiCompatibleClient,
        "moonshot": OpenaiCompatibleClient,  # Kimi
        "minimax": OpenaiCompatibleClient,
        "qwen": OpenaiCompatibleClient,  # 通义千问
        "glm": OpenaiCompatibleClient,  # 智谱
        # 国际提供商（OpenAI 兼容）
        "gemini": OpenaiCompatibleClient,  # Google Gemini
        "claude": OpenaiCompatibleClient,  # Anthropic Claude（通过兼容层）
        # 特殊提供商
        "ollama": OpenaiCompatibleClient,
        "openrouter": OpenaiCompatibleClient,
    }

    @classmethod
    def create_client(cls, config: dict[str, Any]) -> LlmApi:
        """创建 LLM 客户端实例

        Args:
            config: LLM 配置字典，必须包含 apiProvider 字段

        Returns:
            LlmApi 实例

        Raises:
            ConfigurationError: 配置无效或提供商不支持

        """
        if not config:
            raise ConfigurationError("LLM config cannot be empty")

        provider = config.get("apiProvider", "openai")
        provider = provider.lower() if provider else "openai"

        client_class = cls.SUPPORTED_PROVIDERS.get(provider)

        if not client_class:
            raise ConfigurationError(
                f"Unsupported LLM provider: '{provider}'. Supported providers: {list(cls.SUPPORTED_PROVIDERS.keys())}",
            )

        try:
            logger.info(f"Creating LLM client for provider '{provider}'")
            return client_class(config=config)
        except Exception as e:
            raise ConfigurationError(
                f"Failed to create LLM client for provider '{provider}': {e}",
            )

    @classmethod
    def get_supported_providers(cls) -> list[str]:
        """获取支持的提供商列表

        Returns:
            提供商名称列表

        """
        return list(cls.SUPPORTED_PROVIDERS.keys())

    @classmethod
    def validate_config(cls, config: dict[str, Any]) -> tuple[bool, str]:
        """验证 LLM 配置是否有效

        Args:
            config: LLM 配置字典

        Returns:
            (is_valid, error_message) 元组

        """
        # 检查必需字段
        if not config:
            return False, "Config cannot be empty"

        provider = config.get("apiProvider", "openai")
        provider = provider.lower() if provider else "openai"

        if provider not in cls.SUPPORTED_PROVIDERS:
            return False, f"Unsupported provider: '{provider}'"

        # 检查 API key（除了 ollama）
        if provider != "ollama":
            api_key = config.get("openAiApiKey", config.get("api_key"))
            if not api_key:
                return False, f"API key is required for provider '{provider}'"

        # 检查 base_url
        base_url = config.get("openAiBaseUrl", config.get("base_url"))
        if not base_url:
            return False, f"base_url is required for provider '{provider}'"

        # 检查 model
        model = config.get("openAiModelId", config.get("model_id"))
        if not model:
            return False, f"model_id is required for provider '{provider}'"

        return True, ""
