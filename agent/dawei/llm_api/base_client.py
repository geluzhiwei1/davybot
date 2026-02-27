# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""LLM 客户端基类
提供所有 LLM 实现类的共同功能和模式，集成速率限制、请求队列和断路器
"""

import asyncio
import json
import logging
import time
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from typing import Any, ClassVar

from aiohttp import ClientError, ClientSession, ClientTimeout

from dawei.core.exceptions import (
    ConfigurationError,
    LLMConnectionError,
    LLMError,
    LLMRateLimitError,
    ValidationError,
)
from dawei.entity.lm_messages import LLMMessage

from .base_llm_api import LlmApi
from .circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitState
from .metrics import (
    check_prometheus_available,
    decrement_active_requests,
    increment_active_requests,
    record_llm_rate_limit_error,
    record_llm_request,
    record_llm_timeout_error,
)

# 导入保护机制
from .rate_limiter import AdaptiveRateLimiter, RateLimitConfig
from .request_queue import RequestQueue

logger = logging.getLogger(__name__)


class BaseClient(LlmApi, ABC):
    """LLM 客户端基类

    提供所有 LLM 实现类的共同功能和模式，集成：
    - 自适应速率限制
    - 智能请求队列
    - 断路器模式
    - 完整监控指标
    """

    # 全局保护组件（所有子类共享）
    _global_rate_limiter: ClassVar[AdaptiveRateLimiter | None] = None
    _global_request_queue: ClassVar[RequestQueue | None] = None
    _circuit_breakers: ClassVar[dict[str, CircuitBreaker]] = {}
    _protection_initialized = False

    def __init__(self, config: dict[str, Any]) -> None:
        """初始化基础客户端

        Args:
            config: 配置字典

        Raises:
            ValidationError: 如果配置无效

        """
        # Fast Fail: 验证配置输入
        if not isinstance(config, dict):
            raise ValueError(f"config must be a dictionary, got {type(config).__name__}")

        self.config = config

        # 通用配置 - 带验证
        self.timeout = self._validate_timeout(config.get("timeout", 180))
        self.max_retries = self._validate_retries(config.get("maxRetries", 3))
        self.retry_delay = self._validate_retry_delay(config.get("retryDelay", 1.0))

        # 创建会话
        self._session: ClientSession | None = None

        # 初始化全局保护组件
        self._initialize_global_protection(config)

    def _validate_timeout(self, timeout: Any) -> float:
        """验证timeout参数"""
        if not isinstance(timeout, (int, float)):
            raise ValueError(f"timeout must be a number, got {type(timeout).__name__}")
        if timeout <= 0:
            raise ValueError(f"timeout must be positive, got {timeout}")
        return float(timeout)

    def _validate_retries(self, retries: Any) -> int:
        """验证maxRetries参数"""
        if not isinstance(retries, int):
            raise ValueError(f"maxRetries must be an integer, got {type(retries).__name__}")
        if retries < 0:
            raise ValueError(f"maxRetries must be non-negative, got {retries}")
        return retries

    def _validate_retry_delay(self, delay: Any) -> float:
        """验证retryDelay参数"""
        if not isinstance(delay, (int, float)):
            raise ValueError(f"retryDelay must be a number, got {type(delay).__name__}")
        if delay < 0:
            raise ValueError(f"retryDelay must be non-negative, got {delay}")
        return float(delay)

    @staticmethod
    def _ensure_rate_limiter(config: dict[str, Any]):
        """确保速率限制器已初始化（惰性初始化）

        这是一个防御性方法，确保在使用速率限制器之前它已被初始化。
        可以在任何时候调用，即使 __init__ 中的初始化被跳过。
        """
        if BaseClient._global_rate_limiter is not None:
            return

        logger.info("Lazy initializing global rate limiter")

        rate_limit_config = RateLimitConfig(
            initial_rate=config.get("initial_rate", 5.0),
            min_rate=config.get("min_rate", 0.5),
            max_rate=config.get("max_rate", 50.0),
            burst_capacity=config.get("burst_capacity", 20),
        )
        BaseClient._global_rate_limiter = AdaptiveRateLimiter(rate_limit_config)
        logger.info("✓ Global rate limiter initialized (lazy)")

    def _initialize_global_protection(self, config: dict[str, Any]):
        """初始化全局保护组件"""
        # 防御性检查：即使 _protection_initialized 为 True，也要确保 rate_limiter 存在
        # 这处理了初始化可能未正确完成的边缘情况
        if BaseClient._protection_initialized and BaseClient._global_rate_limiter is not None:
            return

        logger.info("Initializing global LLM API protection layer")

        # 1. 初始化速率限制器
        if BaseClient._global_rate_limiter is None:
            rate_limit_config = RateLimitConfig(
                initial_rate=config.get("initial_rate", 5.0),
                min_rate=config.get("min_rate", 0.5),
                max_rate=config.get("max_rate", 50.0),
                burst_capacity=config.get("burst_capacity", 20),
            )
            BaseClient._global_rate_limiter = AdaptiveRateLimiter(rate_limit_config)
            logger.info("✓ Global rate limiter initialized")

        # 2. 初始化请求队列
        if BaseClient._global_request_queue is None:
            BaseClient._global_request_queue = RequestQueue(
                max_concurrent=config.get("max_concurrent", 5),
                max_queue_size=config.get("max_queue_size", 1000),
            )
            logger.info("✓ Global request queue initialized")

        # 3. 初始化断路器（延迟，在第一次使用时创建）
        logger.info("✓ Circuit breakers will be created on-demand")

        BaseClient._protection_initialized = True

    def _get_circuit_breaker(self) -> CircuitBreaker:
        """获取当前 provider 的断路器"""
        provider = self.get_provider_name()

        if provider not in BaseClient._circuit_breakers:
            circuit_config = CircuitBreakerConfig(
                failure_threshold=self.config.get("failure_threshold", 5),
                timeout=self.config.get("circuit_timeout", 60.0),
                max_retries=self.config.get("max_retries", 5),
            )
            BaseClient._circuit_breakers[provider] = CircuitBreaker(circuit_config)
            logger.info(f"✓ Circuit breaker created for provider: {provider}")

        return BaseClient._circuit_breakers[provider]

    def get_provider_name(self) -> str:
        """获取 provider 名称（子类需要实现）"""
        # 默认使用类名的小写形式
        class_name = self.__class__.__name__.lower()
        # 移除 'client' 后缀和下划线
        return class_name.replace("client", "").replace("_", "")

    def _get_client_session(self) -> ClientSession:
        """获取或创建 HTTP 会话"""
        if self._session is None or self._session.closed:
            timeout = ClientTimeout(total=self.timeout)
            headers = self._prepare_headers()

            # 创建会话
            session_kwargs = {"timeout": timeout, "headers": headers}

            self._session = ClientSession(**session_kwargs)
        return self._session

    def _get_proxy_config(self) -> dict[str, Any] | None:
        """获取代理配置

        Returns:
            代理配置字典，如果没有配置则返回 None
        """
        # 从配置中读取代理设置（支持驼峰和下划线两种命名）
        http_proxy = self.config.get("http_proxy", self.config.get("httpProxy", ""))
        https_proxy = self.config.get("https_proxy", self.config.get("httpsProxy", ""))

        # 如果两个都是空的，返回 None
        if not http_proxy and not https_proxy:
            return None

        # 使用 https_proxy 优先，否则使用 http_proxy
        proxy_url = https_proxy or http_proxy

        return {
            "http": http_proxy or proxy_url,
            "https": https_proxy or proxy_url,
        }

    def _prepare_request_kwargs(self, params: dict[str, Any], url: str) -> dict[str, Any]:
        """准备请求参数（包括代理配置）

        Args:
            params: 请求参数
            url: 请求URL

        Returns:
            包含代理配置的请求参数字典
        """
        request_kwargs = {"json": params}

        # 获取并添加代理配置
        proxy_config = self._get_proxy_config()
        if proxy_config:
            # 根据URL的schema选择代理
            proxy = proxy_config.get("https" if url.startswith("https") else "http")
            request_kwargs["proxy"] = proxy

        return request_kwargs

    @abstractmethod
    def _prepare_headers(self) -> dict[str, str]:
        """准备请求头"""

    @abstractmethod
    def _prepare_request_params(
        self,
        messages: list[LLMMessage | dict[str, Any]],
        **kwargs,
    ) -> dict[str, Any]:
        """准备请求参数"""

    async def _make_http_request(
        self,
        endpoint: str,
        params: dict[str, Any],
        with_protection: ClassVar[bool] = True,
    ) -> dict[str, Any]:
        """执行单次 HTTP 请求（受保护）

        Args:
            endpoint: API 端点
            params: 请求参数
            with_protection: 是否使用保护机制

        """
        provider = self.get_provider_name()
        model = getattr(self, "model", "unknown")

        start_time = time.time()

        if with_protection:
            increment_active_requests(provider)

        try:
            if with_protection:
                # 通过断路器调用受保护的请求
                result = await self._make_protected_http_request(endpoint, params)
            else:
                # 直接调用（不受保护）
                result = await self._make_unprotected_http_request(endpoint, params)

            # 记录成功指标
            duration = time.time() - start_time
            if with_protection:
                record_llm_request(
                    provider=provider,
                    model=model,
                    duration=duration,
                    status="success",
                )

            return result

        except Exception as e:
            # 记录失败指标
            duration = time.time() - start_time
            error_str = str(e)

            if "429" in error_str or "rate_limit" in error_str.lower():
                record_llm_request(
                    provider=provider,
                    model=model,
                    duration=duration,
                    status="rate_limit_error",
                )
                if with_protection:
                    record_llm_rate_limit_error(provider, model)
            elif "timeout" in error_str.lower():
                record_llm_request(
                    provider=provider,
                    model=model,
                    duration=duration,
                    status="timeout",
                )
                if with_protection:
                    record_llm_timeout_error(provider, model)
            else:
                record_llm_request(
                    provider=provider,
                    model=model,
                    duration=duration,
                    status="error",
                )

            raise

        finally:
            if with_protection:
                decrement_active_requests(provider)

    async def _make_protected_http_request(
        self,
        endpoint: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """受保护的 HTTP 请求（KISS 原则：线性执行，清晰简单）

        执行顺序：
        1. 断路器状态检查
        2. 速率限制获取
        3. 执行 HTTP 请求
        4. 记录结果（成功/失败）

        Raises:
            CircuitBreakerError: 断路器已打开
            LLMRateLimitError: 速率限制超出
            LLMError: HTTP 请求失败

        """
        circuit_breaker = self._get_circuit_breaker()
        provider = self.get_provider_name()

        # 1. 断路器状态检查（快速失败）
        if circuit_breaker.state == CircuitState.OPEN:
            raise CircuitBreakerError(
                f"Circuit breaker is open for {provider}. Retry after {circuit_breaker.remaining_time():.1f}s",
            )

        # 2. 确保速率限制器已初始化（防御性惰性初始化）
        BaseClient._ensure_rate_limiter(self.config)

        # 3. 速率限制获取
        success, wait_time = await BaseClient._global_rate_limiter.acquire(timeout=30.0)
        if not success:
            raise LLMRateLimitError(f"Rate limit exceeded for {provider}. Wait time: {wait_time:.1f}s")

        # 4. 执行 HTTP 请求
        try:
            result = await self._make_unprotected_http_request(endpoint, params)
            # 成功：记录统计
            BaseClient._global_rate_limiter.record_success()
            circuit_breaker.record_success()
            return result

        except Exception as e:
            # 失败：记录统计并重新抛出
            error_str = str(e)
            is_rate_limit = "429" in error_str or "rate_limit" in error_str.lower()

            BaseClient._global_rate_limiter.record_failure(is_rate_limit=is_rate_limit)
            circuit_breaker.record_failure()
            raise

    async def _make_unprotected_http_request(
        self,
        endpoint: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """不受保护的 HTTP 请求（原有逻辑）"""
        try:
            session = self._get_client_session()
            url = f"{self.base_url}/{endpoint}"

            logger.info("=== HTTP Request ===")
            logger.info(f"URL: {url}")
            logger.info(f"Headers: {session.headers}")
            logger.info(f"Body: {json.dumps(params, indent=2, ensure_ascii=False)}")

            # 准备请求参数（包括代理配置）
            request_kwargs = self._prepare_request_kwargs(params, url)

            async with session.post(url, **request_kwargs) as response:
                logger.info(f"Response Status: {response.status}")
                logger.info(f"Response Headers: {dict(response.headers)}")

                if 200 <= response.status < 300:
                    response_data = await response.json()
                    logger.info(
                        f"Response Data: {json.dumps(response_data, indent=2, ensure_ascii=False)}",
                    )
                    return response_data
                error_text = await response.text()
                logger.error(f"Error Response: {error_text}")

                # Map HTTP status codes to specific exception types
                if response.status == 401:
                    raise LLMError(f"Authentication failed: {error_text}")
                if response.status == 429:
                    raise LLMRateLimitError(f"Rate limit exceeded: {error_text}")
                if response.status >= 500:
                    raise LLMConnectionError(f"Server error: {response.status} - {error_text}")
                if response.status == 400:
                    raise ConfigurationError(f"Bad request: {error_text}")
                raise LLMError(
                    f"Request failed, status: {response.status}, error: {error_text}",
                )

        # Input validation errors should fail fast
        except (ValueError, TypeError) as e:
            # Re-raise validation errors with context
            raise ValidationError(
                param_name="request_params",
                param_value=params,
                message=f"Invalid request parameters: {e!s}",
            )
        except (
            LLMError,
            LLMRateLimitError,
            LLMConnectionError,
            ConfigurationError,
        ):
            # Re-raise our custom exceptions as-is
            raise
        except ClientError as e:
            # aiohttp client errors (network, connection, timeout)
            raise LLMConnectionError(
                message=f"HTTP client error: {e!s}",
                provider=self.get_provider_name(),
            )

    async def _make_stream_request(
        self,
        endpoint: str,
        params: dict[str, Any],
    ) -> AsyncGenerator[dict[str, Any], None]:
        """执行流式 HTTP 请求（受保护）"""
        provider = self.get_provider_name()
        model = getattr(self, "model", "unknown")

        increment_active_requests(provider)
        start_time = time.time()

        try:
            # 确保速率限制器已初始化（防御性惰性初始化）
            BaseClient._ensure_rate_limiter(self.config)

            # 流式请求同样通过速率限制
            success, wait_time = await BaseClient._global_rate_limiter.acquire(timeout=30.0)

            if not success:
                raise LLMRateLimitError(f"Rate limit exceeded, wait time: {wait_time:.1f}s")

            session = self._get_client_session()
            url = f"{self.base_url}/{endpoint}"

            logger.info("=== Stream Request ===")
            logger.info(f"URL: {url}")
            logger.info(f"Headers: {session.headers}")
            logger.info(f"Body: {json.dumps(params, indent=2, ensure_ascii=False)}")

            # 准备请求参数（包括代理配置）
            request_kwargs = self._prepare_request_kwargs(params, url)

            async with session.post(url, **request_kwargs) as response:
                if response.status != 200:
                    error_text = await response.text()

                    # Map HTTP status codes to specific exception types for streaming requests
                    if response.status == 401:
                        raise LLMError(f"Authentication failed: {error_text}")
                    elif response.status == 429:
                        raise LLMRateLimitError(f"Rate limit exceeded: {error_text}")
                    elif response.status >= 500:
                        raise LLMConnectionError(f"Server error: {response.status} - {error_text}")
                    elif response.status == 400:
                        raise ConfigurationError(f"Bad request: {error_text}")
                    else:
                        raise LLMError(
                            f"Stream request failed, status: {response.status}, error: {error_text}",
                        )

                async for line in response.content:
                    line = line.decode("utf-8").strip()

                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break

                        chunk = json.loads(data)
                        yield chunk

            # 记录成功
            duration = time.time() - start_time
            record_llm_request(provider=provider, model=model, duration=duration, status="success")
            BaseClient._global_rate_limiter.record_success()

        # JSON decode errors and streaming errors
        except (ValueError, json.JSONDecodeError) as e:
            raise ValidationError(
                param_name="stream_response",
                param_value=data if "data" in locals() else None,
                message=f"Failed to decode stream chunk: {e!s}",
            )
        except (
            LLMError,
            LLMRateLimitError,
            LLMConnectionError,
            ConfigurationError,
        ):
            # Re-raise our custom exceptions as-is
            raise
        except ClientError as e:
            # aiohttp client errors (network, connection, timeout)
            raise LLMConnectionError(
                message=f"HTTP streaming error: {e!s}",
                provider=self.get_provider_name(),
            )
        except Exception as e:
            # 记录失败
            duration = time.time() - start_time
            error_str = str(e)

            if "429" in error_str or "rate_limit" in error_str.lower():
                BaseClient._global_rate_limiter.record_failure(is_rate_limit=True)
                record_llm_rate_limit_error(provider, model)
            else:
                BaseClient._global_rate_limiter.record_failure(is_rate_limit=False)

            record_llm_request(provider=provider, model=model, duration=duration, status="error")

            raise

        finally:
            decrement_active_requests(provider)

    async def close(self) -> None:
        """关闭客户端会话"""
        if self._session and not self._session.closed:
            await self._session.close()
            # Wait for the connector to fully close (aiohttp requirement)
            # This prevents "Unclosed connector" warnings
            await asyncio.sleep(0.25)  # Give time for cleanup
            logger.info(f"{self.__class__.__name__} session closed")

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(model={getattr(self, 'model', 'unknown')}, base_url={getattr(self, 'base_url', 'unknown')})"

    # ==================== 全局组件管理 ====================

    @staticmethod
    async def initialize_global_components():
        """初始化全局组件（应用启动时调用）"""
        if BaseClient._global_request_queue and not BaseClient._global_request_queue._running:
            await BaseClient._global_request_queue.start()
            logger.info("✓ Global request queue started")

        if not check_prometheus_available():
            logger.warning(
                "⚠ prometheus_client not installed. Install with: pip install prometheus_client",
            )

    @staticmethod
    async def shutdown_global_components():
        """关闭全局组件（应用关闭时调用）"""
        if BaseClient._global_request_queue and BaseClient._global_request_queue._running:
            await BaseClient._global_request_queue.stop()
            logger.info("✓ Global request queue stopped")

        # 关闭所有会话
        # (由各个实例自己处理)

    @staticmethod
    def get_global_stats() -> dict[str, Any]:
        """获取全局统计信息"""
        return {
            "rate_limiter": (BaseClient._global_rate_limiter.get_stats() if BaseClient._global_rate_limiter else {}),
            "request_queue": (BaseClient._global_request_queue.get_stats() if BaseClient._global_request_queue else {}),
            "circuit_breakers": {provider: cb.get_stats() for provider, cb in BaseClient._circuit_breakers.items()},
            "prometheus_available": check_prometheus_available(),
        }

    @staticmethod
    def get_prometheus_metrics() -> str:
        """获取 Prometheus 指标"""
        from .metrics import get_all_metrics

        return get_all_metrics()
