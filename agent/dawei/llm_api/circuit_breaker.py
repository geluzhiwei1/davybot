# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""断路器模式实现

提供生产级的 LLM API 断路器功能，防止级联故障。
"""

import asyncio
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any

from dawei.core.exceptions import (
    CircuitBreakerError,
    LLMConnectionError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from dawei.logg.logging import get_logger

logger = get_logger(__name__)


class CircuitState(Enum):
    """断路器状态"""

    CLOSED = auto()  # 关闭（正常工作）
    OPEN = auto()  # 打开（熔断，拒绝请求）
    HALF_OPEN = auto()  # 半开（尝试恢复）


@dataclass
class CircuitBreakerConfig:
    """断路器配置"""

    failure_threshold: int = 5  # 失败阈值
    success_threshold: int = 2  # 恢复阈值
    timeout: float = 60.0  # 熔断超时（秒）
    window_size: int = 100  # 滑动窗口大小

    # 指数退避配置
    max_retries: int = 5  # 最大重试次数
    base_delay: float = 1.0  # 基础延迟
    max_delay: float = 60.0  # 最大延迟
    jitter: bool = True  # 是否添加抖动
    jitter_factor: float = 0.25  # 抖动因子


class CircuitBreaker:
    """断路器模式实现

    用途：
    - 防止级联故障
    - 快速失败
    - 自动恢复

    使用示例：
        config = CircuitBreakerConfig(failure_threshold=5)
        breaker = CircuitBreaker(config)

        try:
            result = await breaker.call(llm_api_function, messages, tools)
        except Exception as e:
            # 处理错误
            pass
    """

    def __init__(self, config: CircuitBreakerConfig):
        self.config = config
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = 0.0
        self._opened_time = 0.0

        # 滑动窗口记录最近的请求结果
        self._request_history = []  # True=成功, False=失败

        logger.info(
            f"CircuitBreaker initialized: failure_threshold={config.failure_threshold}, timeout={config.timeout}s",
        )

    def _should_allow_request(self) -> bool:
        """判断是否应该允许请求"""
        if self._state == CircuitState.CLOSED:
            return True

        if self._state == CircuitState.OPEN:
            # 检查是否应该尝试恢复
            if time.time() - self._opened_time >= self.config.timeout:
                logger.info("CircuitBreaker entering HALF_OPEN state")
                self._state = CircuitState.HALF_OPEN
                self._success_count = 0
                return True
            return False

        if self._state == CircuitState.HALF_OPEN:
            # 半开状态，允许部分请求通过
            return True

        return False

    def _record_success(self):
        """记录成功"""
        self._failure_count = 0
        self._request_history.append(True)

        # 维持滑动窗口
        if len(self._request_history) > self.config.window_size:
            self._request_history.pop(0)

        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1

            # 如果连续成功次数达到阈值，恢复到关闭状态
            if self._success_count >= self.config.success_threshold:
                logger.info("CircuitBreaker recovered to CLOSED state")
                self._state = CircuitState.CLOSED
                self._success_count = 0

    def _record_failure(self):
        """记录失败"""
        self._failure_count += 1
        self._last_failure_time = time.time()
        self._request_history.append(False)

        # 维持滑动窗口
        if len(self._request_history) > self.config.window_size:
            self._request_history.pop(0)

        # 检查是否应该熔断
        if self._state == CircuitState.HALF_OPEN:
            # 半开状态下失败，立即重新熔断
            logger.warning("CircuitBreaker failed in HALF_OPEN, returning to OPEN")
            self._state = CircuitState.OPEN
            self._opened_time = time.time()
            self._success_count = 0

        elif self._failure_count >= self.config.failure_threshold:
            logger.warning(f"CircuitBreaker opened after {self._failure_count} failures")
            self._state = CircuitState.OPEN
            self._opened_time = time.time()

    async def call(self, func: Callable, *args, max_retries: int | None = None, **kwargs) -> Any:
        """通过断路器调用函数

        Args:
            func: 要调用的函数
            *args, **kwargs: 函数参数
            max_retries: 最大重试次数（None使用配置值）

        Returns:
            函数执行结果

        Raises:
            Exception: 执行失败或断路器打开

        """
        # 检查断路器状态
        if not self._should_allow_request():
            remaining_wait = self.config.timeout - (time.time() - self._opened_time)
            raise CircuitBreakerError(
                f"CircuitBreaker is OPEN, will retry in {remaining_wait:.1f}s",
                circuit_state=self._state.name,
                retry_after=remaining_wait,
            )

        # 执行指数退避重试
        max_retries = max_retries or self.config.max_retries
        last_error = None

        for attempt in range(max_retries + 1):
            try:
                result = await func(*args, **kwargs)

                # 成功，记录并返回
                self._record_success()
                return result

            except Exception as e:
                last_error = e
                error_str = str(e)

                # 检查是否可重试
                is_retryable = self._is_retryable_error(error_str)

                if not is_retryable or attempt == max_retries:
                    # 不可重试或达到最大重试次数
                    try:
                        self._record_failure()
                    except Exception as record_error:
                        logger.exception(f"Failed to record failure: {record_error}")

                    # 根据错误类型抛出更具体的异常
                    if not is_retryable:
                        if "429" in error_str or "rate_limit" in error_str.lower():
                            raise LLMRateLimitError(f"Rate limit exceeded, not retryable: {error_str}")
                        if "timeout" in error_str.lower():
                            raise LLMTimeoutError(f"Timeout, not retryable: {error_str}")
                        if any(status in error_str for status in ["503", "502", "500"]):
                            raise LLMConnectionError(f"Server error, not retryable: {error_str}")
                        raise last_error
                    raise last_error

                # 计算退避时间
                delay = self._calculate_backoff_delay(attempt)

                logger.warning(
                    f"Request failed (attempt {attempt + 1}/{max_retries + 1}), retrying in {delay:.1f}s: {error_str[:100]}",
                )

                await asyncio.sleep(delay)

        # 理论上不会到这里，如果到达这里说明有逻辑错误
        logger.error("Circuit breaker logic error - should not reach this point")
        try:
            self._record_failure()
        except Exception as record_error:
            logger.exception(f"Failed to record failure at unreachable code: {record_error}")

        # 如果到达这里，抛出断路器逻辑错误
        raise CircuitBreakerError(
            "Circuit breaker logic error - unreachable code reached",
            circuit_state=self._state.name,
            failure_count=self._failure_count,
        )

    def _is_retryable_error(self, error_str: str) -> bool:
        """判断错误是否可重试"""
        retryable_patterns = [
            "429",  # Rate limit
            "timeout",  # 超时
            "503",  # Service unavailable
            "502",  # Bad gateway
            "connection",  # 连接错误
            "temporarily",  # 临时错误
        ]

        error_str_lower = error_str.lower()
        return any(pattern in error_str_lower for pattern in retryable_patterns)

    def _calculate_backoff_delay(self, attempt: int) -> float:
        """计算指数退避延迟"""
        # 基础指数退避
        delay = self.config.base_delay * (2**attempt)
        delay = min(delay, self.config.max_delay)

        # 添加抖动
        if self.config.jitter:
            jitter_range = delay * self.config.jitter_factor
            jitter = (random.random() * 2 - 1) * jitter_range
            delay += jitter

        return max(0.1, delay)

    def get_state(self) -> CircuitState:
        """获取断路器状态"""
        return self._state

    def get_stats(self) -> dict:
        """获取统计信息"""
        # 计算窗口内的成功率
        if self._request_history:
            recent_success = sum(1 for r in self._request_history if r)
            success_rate = recent_success / len(self._request_history)
        else:
            success_rate = 1.0

        return {
            "state": self._state.name,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "window_size": len(self._request_history),
            "success_rate": success_rate,
            "last_failure_time": self._last_failure_time,
            "opened_time": self._opened_time,
        }

    def reset(self):
        """重置断路器"""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._request_history.clear()
        logger.info("CircuitBreaker reset")
