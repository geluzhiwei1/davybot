# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""LLM API 配置常量

统一管理 LLM 模块的硬编码配置常量
遵循 KISS 原则:集中管理,易于维护
"""

from dataclasses import dataclass
from enum import Enum, auto
from typing import ClassVar


class RateLimitStrategy(Enum):
    """速率限制策略"""

    TOKEN_BUCKET = "token_bucket"  # 令牌桶
    SLIDING_WINDOW = "sliding_window"  # 滑动窗口
    LEAKY_BUCKET = "leaky_bucket"  # 漏桶


class RequestPriority(Enum):
    """请求优先级"""

    CRITICAL = auto()  # 关键请求(用户交互)
    HIGH = auto()  # 高优先级(实时任务)
    NORMAL = auto()  # 普通请求(批处理)
    LOW = auto()  # 低优先级(后台任务)


class CircuitState(Enum):
    """断路器状态"""

    CLOSED = auto()  # 关闭(正常工作)
    OPEN = auto()  # 打开(熔断,拒绝请求)
    HALF_OPEN = auto()  # 半开(尝试恢复)


# ==================== 断路器配置 ====================


@dataclass
class CircuitBreakerDefaults:
    """断路器默认配置"""

    FAILURE_THRESHOLD: ClassVar[int] = 5  # 失败阈值
    SUCCESS_THRESHOLD: ClassVar[int] = 2  # 恢复阈值
    TIMEOUT: ClassVar[float] = 60.0  # 熔断超时(秒)
    WINDOW_SIZE: ClassVar[int] = 100  # 滑动窗口大小

    # 指数退避配置
    MAX_RETRIES: ClassVar[int] = 5  # 最大重试次数
    BASE_DELAY: ClassVar[float] = 1.0  # 基础延迟(秒)
    MAX_DELAY: ClassVar[float] = 60.0  # 最大延迟(秒)
    JITTER: ClassVar[bool] = True  # 是否添加抖动
    JITTER_FACTOR: ClassVar[float] = 0.25  # 抖动因子


# ==================== 速率限制配置 ====================


@dataclass
class RateLimitDefaults:
    """速率限制默认配置"""

    INITIAL_RATE: ClassVar[float] = 5.0  # 初始速率 (req/s)
    MIN_RATE: ClassVar[float] = 0.5  # 最小速率
    MAX_RATE: ClassVar[float] = 50.0  # 最大速率
    BURST_CAPACITY: ClassVar[int] = 20  # 突发容量

    # 自适应调整参数
    SCALE_UP_FACTOR: ClassVar[float] = 1.2  # 扩容因子
    SCALE_DOWN_FACTOR: ClassVar[float] = 0.7  # 缩容因子
    SCALE_UP_THRESHOLD: ClassVar[int] = 10  # 扩容成功阈值
    SCALE_DOWN_THRESHOLD: ClassVar[int] = 3  # 缩容失败阈值

    # 速率限制策略
    STRATEGY: ClassVar[RateLimitStrategy] = RateLimitStrategy.SLIDING_WINDOW


# ==================== 请求队列配置 ====================


@dataclass
class RequestQueueDefaults:
    """请求队列默认配置"""

    MAX_CONCURRENT: ClassVar[int] = 5  # 最大并发数
    MAX_QUEUE_SIZE: ClassVar[int] = 1000  # 最大队列大小
    DEFAULT_TIMEOUT: ClassVar[float] = 300.0  # 默认超时(秒)


# ==================== 缓存配置 ====================


@dataclass
class CacheDefaults:
    """缓存默认配置"""

    PARSER_CACHE_TTL: ClassVar[int] = 300  # 解析器缓存生存时间(秒)
    CONFIG_CACHE_TTL: ClassVar[int] = 300  # 配置缓存生存时间(秒)


# ==================== 超时配置 ====================


@dataclass
class TimeoutDefaults:
    """超时默认配置"""

    HTTP_REQUEST: ClassVar[float] = 180.0  # HTTP 请求超时(秒)
    RATE_LIMIT_ACQUIRE: ClassVar[float] = 30.0  # 速率限制获取超时(秒)
    QUEUE_SUBMIT: ClassVar[float] = 60.0  # 队列提交超时(秒)


# ==================== 导出单例实例 ====================

CIRCUIT_BREAKER = CircuitBreakerDefaults()
RATE_LIMIT = RateLimitDefaults()
REQUEST_QUEUE = RequestQueueDefaults()
CACHE = CacheDefaults()
TIMEOUT = TimeoutDefaults()


class LLMProviderConfig:
    """LLM 提供商默认配置"""


@dataclass
class SnapshotDefaults:
    """文件快照默认配置"""

    MAX_SNAPSHOTS_PER_FILE: ClassVar[int] = 50  # 每个文件最大快照数
    RETENTION_DAYS: ClassVar[int] = 30  # 快照保留天数


SNAPSHOT = SnapshotDefaults()
