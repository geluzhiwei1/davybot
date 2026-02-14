# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""解析器缓存管理器

管理流式解析器的缓存，避免重复创建
"""

import logging
import time

from dawei.llm_api.base_llm_api import StreamChunkParser
from dawei.llm_api.impl.ollama_api import OllamaParser
from dawei.llm_api.impl.openai_compatible_api import OpenAICompatibleParser

logger = logging.getLogger(__name__)


class ParserCache:
    """解析器缓存管理器

    为不同的 LLM 提供商缓存 StreamChunkParser 实例，
    避免重复创建，提高性能。
    """

    DEFAULT_TTL = 300  # 缓存生存时间（秒）

    def __init__(self, cache_ttl: int = DEFAULT_TTL):
        """初始化解析器缓存

        Args:
            cache_ttl: 缓存生存时间（秒），默认 300 秒

        """
        self._cache: dict[str, StreamChunkParser] = {}
        self._cache_ttl = cache_ttl
        self._cache_timestamps: dict[str, float] = {}

    def _is_cache_valid(self, provider: str) -> bool:
        """检查缓存是否有效"""
        if provider not in self._cache_timestamps:
            return False

        age = time.time() - self._cache_timestamps[provider]
        is_valid = age < self._cache_ttl
        logger.debug(f"Parser cache for '{provider}': valid={is_valid}, age={age:.1f}s")
        return is_valid

    def _create_parser(self, provider: str) -> StreamChunkParser:
        """根据提供商类型创建解析器

        Args:
            provider: LLM 提供商名称

        Returns:
            StreamChunkParser 实例

        """
        provider_lower = provider.lower()

        if provider_lower == "ollama":
            logger.debug(f"Creating OllamaParser for provider '{provider}'")
            return OllamaParser()
        # 默认使用 OpenAI 兼容解析器（适用于 deepseek, moonshot 等）
        logger.debug(f"Creating OpenAICompatibleParser for provider '{provider}'")
        return OpenAICompatibleParser()

    def get_parser(self, provider: str) -> StreamChunkParser:
        """获取指定提供商的解析器

        优先从缓存获取，缓存失效时创建新实例

        Args:
            provider: LLM 提供商名称

        Returns:
            StreamChunkParser 实例

        """
        if self._is_cache_valid(provider):
            logger.debug(f"Using cached parser for '{provider}'")
            return self._cache[provider]

        # 创建新解析器并缓存
        parser = self._create_parser(provider)
        self._cache[provider] = parser
        self._cache_timestamps[provider] = time.time()
        logger.info(f"Created and cached new parser for '{provider}'")
        return parser

    def clear_cache(self) -> None:
        """清除所有缓存"""
        count = len(self._cache)
        self._cache.clear()
        self._cache_timestamps.clear()
        logger.info(f"Parser cache cleared ({count} entries)")
