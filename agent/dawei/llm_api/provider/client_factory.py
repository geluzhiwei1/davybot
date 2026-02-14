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
from dawei.llm_api.impl.ollama_api import OllamaClient
from dawei.llm_api.impl.openai_compatible_api import OpenaiCompatibleClient
from dawei.llm_api.impl.openrouter_api import OpenRouterClient

logger = logging.getLogger(__name__)


class LLMClientFactory:
    """LLM 客户端工厂

    根据配置创建对应的 LLM 客户端实例

    KISS 原则：大多数提供商使用 OpenAI 兼容 API，统一使用 OpenaiCompatibleClient
    只需要配置正确的 base_url 和 api_key 即可
    """

    # 支持的提供商类型
    # 注意：所有标记为 OpenAI 兼容的提供商都使用 OpenaiCompatibleClient
    # 只需要配置正确的 base_url 和 api_key
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
        "ollama": OllamaClient,
        "openrouter": OpenRouterClient,
    }

    # 推荐的 Function Call 模型（仅支持有函数调用能力的模型）
    RECOMMENDED_MODELS = {
        "openai": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
        "deepseek": ["deepseek-chat", "deepseek-coder"],
        "moonshot": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
        "minimax": ["abab6.5s-chat", "abab6.5-chat"],
        "qwen": ["qwen-turbo", "qwen-plus", "qwen-max"],
        "glm": ["glm-4", "glm-4-flash", "glm-3-turbo"],
        "gemini": ["gemini-2.0-flash-exp", "gemini-1.5-pro", "gemini-1.5-flash"],
        "claude": ["claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022"],
        "ollama": ["llama3.1", "llama3.2", "qwen2.5", "gemma2"],
        "openrouter": ["openai/gpt-4o", "anthropic/claude-3.5-sonnet"],
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
    def get_recommended_models(cls, provider: str) -> list[str]:
        """获取指定提供商的推荐模型列表

        Args:
            provider: 提供商名称

        Returns:
            推荐模型列表

        Raises:
            ConfigurationError: 提供商不支持

        """
        provider = provider.lower() if provider else "openai"
        models = cls.RECOMMENDED_MODELS.get(provider)

        if not models:
            raise ConfigurationError(
                f"No recommended models found for provider '{provider}'. Supported providers: {list(cls.RECOMMENDED_MODELS.keys())}",
            )

        return models

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
