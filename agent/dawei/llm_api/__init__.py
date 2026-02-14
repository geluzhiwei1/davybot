# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""LLM 模块 - 提供统一的 LLM 管理和提供者接口

主要组件：
- LLMProvider: LLM 配置和提供者管理器（推荐使用）
- LlmApi: LLM 提供者抽象接口
- 各种 LLM 客户端实现

支持的提供商（10个，全部支持 Function Call）：
- OpenAI, DeepSeek, Moonshot(Kimi), MiniMax, Qwen, GLM, Gemini, Claude, Ollama, OpenRouter

子模块：
- provider: 拆分的组件（StreamState, ParserCache, LLMClientFactory）
- constants: 配置常量和提供商信息
"""

# 主要接口 - 推荐使用 LLMProvider
from dawei.entity.llm_config import LLMConfig, LLMProviderConfig

from .base_client import BaseClient
from .base_llm_api import LlmApi

# 常量
from .constants import (
    CACHE,
    CIRCUIT_BREAKER,
    LLM_PROVIDER,
    RATE_LIMIT,
    REQUEST_QUEUE,
    TIMEOUT,
    CacheDefaults,
    CircuitBreakerDefaults,
    RateLimitDefaults,
    RequestQueueDefaults,
    TimeoutDefaults,
)
from .constants import (
    LLMProviderConfig as LLMProviderConstants,
)

# LLM 提供者实现
from .impl.openai_compatible_api import OpenaiCompatibleClient
from .impl.openrouter_api import OpenRouterClient
from .llm_provider import LLMProvider

# Provider 子模块
from .provider import LLMClientFactory, ParserCache, StreamState

__all__ = [
    # 主要接口
    "LLMProvider",
    "LLMConfig",
    "LLMProviderConfig",
    "LlmApi",
    "BaseClient",
    # 客户端实现
    "OpenaiCompatibleClient",
    # Provider 子模块
    "StreamState",
    "ParserCache",
    "LLMClientFactory",
    # 常量
    "CircuitBreakerDefaults",
    "RateLimitDefaults",
    "RequestQueueDefaults",
    "CacheDefaults",
    "TimeoutDefaults",
    "LLMProviderConstants",
    "CIRCUIT_BREAKER",
    "RATE_LIMIT",
    "REQUEST_QUEUE",
    "CACHE",
    "TIMEOUT",
    "LLM_PROVIDER",
]
