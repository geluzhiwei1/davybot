# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""自适应速率限制器

提供生产级的 LLM API 速率限制功能，支持多种策略和动态调整。
"""

import asyncio
import time
from collections import deque
from dataclasses import dataclass
from enum import Enum

from dawei.logg.logging import get_logger

logger = get_logger(__name__)


class RateLimitStrategy(Enum):
    """速率限制策略"""

    TOKEN_BUCKET = "token_bucket"  # 令牌桶
    SLIDING_WINDOW = "sliding_window"  # 滑动窗口
    LEAKY_BUCKET = "leaky_bucket"  # 漏桶


@dataclass
class RateLimitConfig:
    """速率限制配置"""

    initial_rate: float = 5.0  # 初始速率 (req/s)
    min_rate: float = 0.5  # 最小速率
    max_rate: float = 50.0  # 最大速率
    burst_capacity: int = 20  # 突发容量

    # 自适应调整参数
    scale_up_factor: float = 1.2  # 扩容因子
    scale_down_factor: float = 0.7  # 缩容因子
    scale_up_threshold: int = 10  # 扩容成功阈值
    scale_down_threshold: int = 3  # 缩容失败阈值

    # 速率限制策略
    strategy: RateLimitStrategy = RateLimitStrategy.SLIDING_WINDOW


class AdaptiveRateLimiter:
    """自适应速率限制器

    特性：
    - 动态调整请求速率
    - 支持突发流量
    - 基于历史成功率自动扩缩容
    - 多种速率限制策略

    使用示例：
        config = RateLimitConfig(initial_rate=5.0)
        limiter = AdaptiveRateLimiter(config)

        # 获取令牌
        success, wait_time = await limiter.acquire(timeout=30.0)
        if success:
            # 执行请求
            await call_llm_api()
            limiter.record_success()
        else:
            limiter.record_failure()
    """

    def __init__(self, config: RateLimitConfig):
        self.config = config
        self._current_rate = config.initial_rate
        self._success_count = 0
        self._failure_count = 0
        self._last_adjust_time = time.time()

        # 滑动窗口：记录最近的请求时间戳
        self._request_history = deque(maxlen=config.burst_capacity)

        # 统计信息
        self._total_requests = 0
        self._total_successes = 0
        self._total_failures = 0
        self._total_rate_limit_errors = 0

        logger.info(
            f"AdaptiveRateLimiter initialized: initial_rate={config.initial_rate}, strategy={config.strategy.value}",
        )

    async def acquire(
        self,
        tokens: int = 1,
        timeout: float | None = None,
    ) -> tuple[bool, float | None]:
        """获取令牌

        Args:
            tokens: 需要的令牌数
            timeout: 超时时间（秒），None表示不等待

        Returns:
            (success, wait_time): 是否成功, 等待时间

        """
        start_time = time.time()

        while True:
            # 尝试获取令牌
            success, wait_time = self._try_acquire(tokens)

            if success:
                self._total_requests += 1
                return True, wait_time

            # 令牌不足
            if timeout is None:
                # 不等待，直接失败
                return False, wait_time

            # 检查是否超时
            elapsed = time.time() - start_time
            if elapsed >= timeout:
                logger.warning(
                    f"Rate limiter timeout after {elapsed:.1f}s, current_rate={self._current_rate:.2f}",
                )
                return False, wait_time

            # 等待后重试
            wait_time = min(wait_time, timeout - elapsed)
            await asyncio.sleep(wait_time)

    def _try_acquire(self, tokens: int) -> tuple[bool, float]:
        """尝试获取令牌（内部方法）"""
        now = time.time()

        if self.config.strategy == RateLimitStrategy.SLIDING_WINDOW:
            return self._sliding_window_acquire(now, tokens)
        if self.config.strategy == RateLimitStrategy.TOKEN_BUCKET:
            return self._token_bucket_acquire(now, tokens)
        return self._leaky_bucket_acquire(now, tokens)

    def _sliding_window_acquire(self, now: float, tokens: int) -> tuple[bool, float]:
        """滑动窗口算法

        原理：统计当前窗口内的请求数，判断是否允许新请求
        """
        # 清理过期请求（超过1秒的请求）
        while self._request_history and now - self._request_history[0] > 1.0:
            self._request_history.popleft()

        # 检查是否超过速率限制（处理零速率边界）
        window_size = len(self._request_history)
        max_requests = max(1, int(self._current_rate))  # 确保至少为1

        if window_size + tokens <= max_requests:
            # 允许请求
            for _ in range(tokens):
                self._request_history.append(now)
            return True, 0.0
        # 计算需要等待的时间
        if window_size >= max_requests:
            # 窗口已满，等待最老的请求过期
            oldest_request = self._request_history[0]
            wait_time = max(0.01, 1.0 - (now - oldest_request) + 0.01)
        else:
            # 窗口未满，但剩余容量不足
            remaining_capacity = max_requests - window_size
            if remaining_capacity >= tokens:
                wait_time = 0.1  # 短暂等待
            else:
                # 需要等待部分容量释放
                wait_time = 0.5

        return False, wait_time

    def _token_bucket_acquire(self, now: float, tokens: int) -> tuple[bool, float]:
        """令牌桶算法

        原理：以固定速率向桶中添加令牌，请求时从桶中取令牌
        """
        # 计算需要补充的令牌数
        if not hasattr(self, "_last_refill_time"):
            self._last_refill_time = now

        elapsed = max(0, now - self._last_refill_time)  # 确保不会为负值
        tokens_to_add = elapsed * self._current_rate

        # 获取当前令牌数
        if not hasattr(self, "_bucket_tokens"):
            self._bucket_tokens = float(self.config.burst_capacity)

        # 补充令牌（确保不会出现负值）
        self._bucket_tokens = min(
            self.config.burst_capacity,
            max(0.0, self._bucket_tokens + tokens_to_add),
        )
        self._last_refill_time = now

        # 检查令牌是否足够
        if self._bucket_tokens >= tokens:
            self._bucket_tokens -= tokens
            return True, 0.0
        # 计算需要等待的时间（确保不会出现负值）
        wait_time = max(0.01, (tokens - self._bucket_tokens) / self._current_rate)
        return False, wait_time

    def _leaky_bucket_acquire(self, now: float, tokens: int) -> tuple[bool, float]:
        """漏桶算法

        原理：以固定速率处理请求，请求进入桶中等待处理
        """
        # 简化实现：使用滑动窗口模拟漏桶
        return self._sliding_window_acquire(now, tokens)

    def record_success(self):
        """记录成功请求"""
        self._success_count += 1
        self._failure_count = 0
        self._total_successes += 1

        # 检查是否应该提升速率
        if self._success_count >= self.config.scale_up_threshold:
            self._adjust_rate(up=True)
            self._success_count = 0

    def record_failure(self, is_rate_limit: bool = False):
        """记录失败请求"""
        self._failure_count += 1
        self._success_count = 0
        self._total_failures += 1

        if is_rate_limit:
            self._total_rate_limit_errors += 1
            # 速率限制错误，立即大幅降低
            self._current_rate = max(self.config.min_rate, self._current_rate * 0.5)
            # 不重置失败计数，让问题持续暴露
            # self._failure_count = 0  # 已移除：遵循 FAST FAIL 原则
            logger.warning(
                f"Rate limit hit! Reduced rate to {self._current_rate:.2f}, failure_count={self._failure_count}",
            )
        elif self._failure_count >= self.config.scale_down_threshold:
            # 连续失败，适度降低
            self._adjust_rate(up=False)
            self._failure_count = 0

    def _adjust_rate(self, up: bool):
        """调整速率"""
        old_rate = self._current_rate

        if up:
            new_rate = self._current_rate * self.config.scale_up_factor
            self._current_rate = min(self.config.max_rate, max(self.config.min_rate, new_rate))
        else:
            new_rate = self._current_rate * self.config.scale_down_factor
            self._current_rate = max(self.config.min_rate, min(self.config.max_rate, new_rate))

        self._last_adjust_time = time.time()

        logger.info(
            f"Rate adjusted: {old_rate:.2f} -> {self._current_rate:.2f} ({'+💪' if up else '-🔻'})",
        )

    def get_stats(self) -> dict:
        """获取统计信息"""
        success_rate = 0.0
        if self._total_requests > 0:
            success_rate = self._total_successes / self._total_requests

        return {
            "current_rate": self._current_rate,
            "total_requests": self._total_requests,
            "total_successes": self._total_successes,
            "total_failures": self._total_failures,
            "total_rate_limit_errors": self._total_rate_limit_errors,
            "success_rate": success_rate,
            "strategy": self.config.strategy.value,
        }

    def reset(self):
        """重置速率限制器"""
        self._current_rate = self.config.initial_rate
        self._success_count = 0
        self._failure_count = 0
        self._request_history.clear()

        if hasattr(self, "_bucket_tokens"):
            delattr(self, "_bucket_tokens")
        if hasattr(self, "_last_refill_time"):
            delattr(self, "_last_refill_time")

        logger.info("Rate limiter reset")
