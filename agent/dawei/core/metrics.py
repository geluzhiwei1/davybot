# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""指标收集系统
实现架构设计文档中定义的指标收集功能
"""

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MetricType(Enum):
    """指标类型"""

    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    TIMER = "timer"


@dataclass
class MetricValue:
    """指标值"""

    value: float
    timestamp: float
    tags: dict[str, str] = field(default_factory=dict)


class Counter:
    """计数器指标"""

    def __init__(self, name: str, tags: dict[str, str] | None = None):
        self.name = name
        self.tags = tags or {}
        self.value = 0.0
        self.created_at = time.time()
        self._lock = threading.Lock()

    def increment(self, value: float = 1.0):
        """增加计数"""
        with self._lock:
            self.value += value

    def get_value(self) -> float:
        """获取当前值"""
        with self._lock:
            return self.value

    def reset(self):
        """重置计数器"""
        with self._lock:
            self.value = 0.0


class Gauge:
    """仪表盘指标"""

    def __init__(self, name: str, tags: dict[str, str] | None = None):
        self.name = name
        self.tags = tags or {}
        self.value = 0.0
        self.created_at = time.time()
        self._lock = threading.Lock()

    def set(self, value: float):
        """设置值"""
        with self._lock:
            self.value = value

    def get_value(self) -> float:
        """获取当前值"""
        with self._lock:
            return self.value

    def increment(self, value: float = 1.0):
        """增加值"""
        with self._lock:
            self.value += value

    def decrement(self, value: float = 1.0):
        """减少值"""
        with self._lock:
            self.value -= value


class Histogram:
    """直方图指标"""

    def __init__(
        self,
        name: str,
        tags: dict[str, str] | None = None,
        buckets: list[float] | None = None,
    ):
        self.name = name
        self.tags = tags or {}
        self.buckets = buckets or [0.1, 0.5, 1.0, 2.5, 5.0, 10.0, float("inf")]
        self.bucket_counts = dict.fromkeys(self.buckets, 0)
        self.count = 0
        self.sum = 0.0
        self.values = deque(maxlen=1000)  # 保留最近1000个值
        self.created_at = time.time()
        self._lock = threading.Lock()

    def observe(self, value: float):
        """观察一个值"""
        with self._lock:
            self.count += 1
            self.sum += value
            self.values.append(value)

            for bucket in self.buckets:
                if value <= bucket:
                    self.bucket_counts[bucket] += 1

    def get_count(self) -> int:
        """获取观察次数"""
        with self._lock:
            return self.count

    def get_sum(self) -> float:
        """获取总和"""
        with self._lock:
            return self.sum

    def get_average(self) -> float:
        """获取平均值"""
        with self._lock:
            return self.sum / self.count if self.count > 0 else 0.0

    def get_bucket_counts(self) -> dict[float, int]:
        """获取桶计数"""
        with self._lock:
            return self.bucket_counts.copy()

    def get_percentile(self, percentile: float) -> float:
        """获取百分位数"""
        with self._lock:
            if not self.values:
                return 0.0

            sorted_values = sorted(self.values)
            index = int(len(sorted_values) * percentile / 100)
            return sorted_values[min(index, len(sorted_values) - 1)]


class Timer:
    """计时器指标"""

    def __init__(self, name: str, tags: dict[str, str] | None = None):
        self.name = name
        self.tags = tags or {}
        self.histogram = Histogram(f"{name}_duration", tags)
        self.created_at = time.time()

    def time(self, duration: float):
        """记录时间"""
        self.histogram.observe(duration)

    def get_average(self) -> float:
        """获取平均时间"""
        return self.histogram.get_average()

    def get_percentile(self, percentile: float) -> float:
        """获取百分位数"""
        return self.histogram.get_percentile(percentile)

    def __enter__(self):
        """上下文管理器入口"""
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        duration = time.time() - self.start_time
        self.time(duration)


class MetricsConfig:
    """指标配置"""

    def __init__(
        self,
        enabled: bool = True,
        retention_period: int = 3600,
        max_metrics: int = 10000,  # 1小时
    ):
        self.enabled = enabled
        self.retention_period = retention_period
        self.max_metrics = max_metrics


class MetricsCollector:
    """指标收集器"""

    def __init__(self, config: MetricsConfig | None = None):
        self.config = config or MetricsConfig()
        self.counters: dict[str, Counter] = {}
        self.gauges: dict[str, Gauge] = {}
        self.histograms: dict[str, Histogram] = {}
        self.timers: dict[str, Timer] = {}
        self._lock = threading.Lock()

        # 启动清理线程
        if self.config.enabled:
            self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
            self._cleanup_thread.start()

    def _make_key(self, name: str, tags: dict[str, str] | None = None) -> str:
        """生成指标键"""
        if not tags:
            return name

        tag_str = ",".join(f"{k}={v}" for k, v in sorted(tags.items()))
        return f"{name}{{{tag_str}}}"

    def increment_counter(
        self,
        name: str,
        value: float = 1.0,
        tags: dict[str, str] | None = None,
    ):
        """增加计数器"""
        if not self.config.enabled:
            return

        key = self._make_key(name, tags)
        with self._lock:
            if key not in self.counters:
                self.counters[key] = Counter(name, tags)
            self.counters[key].increment(value)

    def set_gauge(self, name: str, value: float, tags: dict[str, str] | None = None):
        """设置仪表盘值"""
        if not self.config.enabled:
            return

        key = self._make_key(name, tags)
        with self._lock:
            if key not in self.gauges:
                self.gauges[key] = Gauge(name, tags)
            self.gauges[key].set(value)

    def record_histogram(self, name: str, value: float, tags: dict[str, str] | None = None):
        """记录直方图数据"""
        if not self.config.enabled:
            return

        key = self._make_key(name, tags)
        with self._lock:
            if key not in self.histograms:
                self.histograms[key] = Histogram(name, tags)
            self.histograms[key].observe(value)

    def record_timer(self, name: str, duration: float, tags: dict[str, str] | None = None):
        """记录计时器数据"""
        if not self.config.enabled:
            return

        key = self._make_key(name, tags)
        with self._lock:
            if key not in self.timers:
                self.timers[key] = Timer(name, tags)
            self.timers[key].time(duration)

    def timer(self, name: str, tags: dict[str, str] | None = None) -> Timer:
        """获取计时器实例"""
        if not self.config.enabled:
            return DummyTimer()

        key = self._make_key(name, tags)
        with self._lock:
            if key not in self.timers:
                self.timers[key] = Timer(name, tags)
            return self.timers[key]

    def get_counter(self, name: str, tags: dict[str, str] | None = None) -> Counter | None:
        """获取计数器"""
        key = self._make_key(name, tags)
        with self._lock:
            return self.counters.get(key)

    def get_gauge(self, name: str, tags: dict[str, str] | None = None) -> Gauge | None:
        """获取仪表盘"""
        key = self._make_key(name, tags)
        with self._lock:
            return self.gauges.get(key)

    def get_histogram(
        self,
        name: str,
        tags: dict[str, str] | None = None,
    ) -> Histogram | None:
        """获取直方图"""
        key = self._make_key(name, tags)
        with self._lock:
            return self.histograms.get(key)

    def get_timer(self, name: str, tags: dict[str, str] | None = None) -> Timer | None:
        """获取计时器"""
        key = self._make_key(name, tags)
        with self._lock:
            return self.timers.get(key)

    def get_all_metrics(self) -> dict[str, dict[str, Any]]:
        """获取所有指标"""
        metrics = {}

        with self._lock:
            # 计数器
            for key, counter in self.counters.items():
                metrics[key] = {
                    "type": "counter",
                    "value": counter.get_value(),
                    "tags": counter.tags,
                    "created_at": counter.created_at,
                }

            # 仪表盘
            for key, gauge in self.gauges.items():
                metrics[key] = {
                    "type": "gauge",
                    "value": gauge.get_value(),
                    "tags": gauge.tags,
                    "created_at": gauge.created_at,
                }

            # 直方图
            for key, histogram in self.histograms.items():
                metrics[key] = {
                    "type": "histogram",
                    "count": histogram.get_count(),
                    "sum": histogram.get_sum(),
                    "average": histogram.get_average(),
                    "bucket_counts": histogram.get_bucket_counts(),
                    "tags": histogram.tags,
                    "created_at": histogram.created_at,
                }

            # 计时器
            for key, timer in self.timers.items():
                metrics[key] = {
                    "type": "timer",
                    "average": timer.get_average(),
                    "p50": timer.get_percentile(50),
                    "p95": timer.get_percentile(95),
                    "p99": timer.get_percentile(99),
                    "tags": timer.tags,
                    "created_at": timer.created_at,
                }

        return metrics

    def reset_metric(self, name: str, tags: dict[str, str] | None = None):
        """重置指标"""
        key = self._make_key(name, tags)

        with self._lock:
            if key in self.counters:
                self.counters[key].reset()

            # 直方图和计时器不能重置，只能删除
            if key in self.histograms:
                del self.histograms[key]

            if key in self.timers:
                del self.timers[key]

    def reset_all_metrics(self):
        """重置所有指标"""
        with self._lock:
            for counter in self.counters.values():
                counter.reset()

            self.histograms.clear()
            self.timers.clear()

    def _cleanup_loop(self):
        """清理循环"""
        while True:
            try:
                self._cleanup_old_metrics()
                time.sleep(300)  # 每5分钟清理一次
            except (OSError, RuntimeError, KeyError) as e:
                # Log specific expected errors in background cleanup loop
                # OSError: File system issues during cleanup
                # RuntimeError: Thread state issues
                # KeyError: Dictionary mutation during iteration
                print(f"Metrics cleanup error: {e}")
            except Exception as e:
                # Background loop must never crash - catch all unexpected errors
                # This is a daemon thread, broad exception handling is intentional
                print(f"Unexpected metrics cleanup error: {e}")

    def _cleanup_old_metrics(self):
        """清理旧指标"""
        current_time = time.time()
        cutoff_time = current_time - self.config.retention_period

        with self._lock:
            # 清理计数器
            expired_counters = [key for key, counter in self.counters.items() if counter.created_at < cutoff_time]
            for key in expired_counters:
                del self.counters[key]

            # 清理仪表盘
            expired_gauges = [key for key, gauge in self.gauges.items() if gauge.created_at < cutoff_time]
            for key in expired_gauges:
                del self.gauges[key]

            # 清理直方图
            expired_histograms = [key for key, histogram in self.histograms.items() if histogram.created_at < cutoff_time]
            for key in expired_histograms:
                del self.histograms[key]

            # 清理计时器
            expired_timers = [key for key, timer in self.timers.items() if timer.created_at < cutoff_time]
            for key in expired_timers:
                del self.timers[key]


class DummyTimer:
    """虚拟计时器，用于禁用指标时"""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def time(self, duration: float):
        pass


# 全局指标收集器实例
_global_metrics_collector: MetricsCollector | None = None


def get_metrics_collector(config: MetricsConfig | None = None) -> MetricsCollector:
    """获取全局指标收集器实例"""
    global _global_metrics_collector
    if _global_metrics_collector is None:
        _global_metrics_collector = MetricsCollector(config)
    return _global_metrics_collector


def increment_counter(name: str, value: float = 1.0, tags: dict[str, str] | None = None):
    """增加计数器（便捷函数）"""
    get_metrics_collector().increment_counter(name, value, tags)


def set_gauge(name: str, value: float, tags: dict[str, str] | None = None):
    """设置仪表盘值（便捷函数）"""
    get_metrics_collector().set_gauge(name, value, tags)


def record_histogram(name: str, value: float, tags: dict[str, str] | None = None):
    """记录直方图数据（便捷函数）"""
    get_metrics_collector().record_histogram(name, value, tags)


def record_timer(name: str, duration: float, tags: dict[str, str] | None = None):
    """记录计时器数据（便捷函数）"""
    get_metrics_collector().record_timer(name, duration, tags)


def timer(name: str, tags: dict[str, str] | None = None) -> Timer:
    """获取计时器实例（便捷函数）"""
    return get_metrics_collector().timer(name, tags)


# 指标装饰器
def count_calls(name: str, tags: dict[str, str] | None = None):
    """调用计数装饰器"""

    def decorator(func):
        import functools

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            increment_counter(name, tags=tags)
            return func(*args, **kwargs)

        return wrapper

    return decorator


def measure_time(name: str, tags: dict[str, str] | None = None):
    """执行时间测量装饰器"""

    def decorator(func):
        import functools

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                return func(*args, **kwargs)
            finally:
                duration = time.time() - start_time
                record_timer(name, duration, tags)

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):

            start_time = time.time()
            try:
                return await func(*args, **kwargs)
            finally:
                duration = time.time() - start_time
                record_timer(name, duration, tags)

        import asyncio

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return decorator
