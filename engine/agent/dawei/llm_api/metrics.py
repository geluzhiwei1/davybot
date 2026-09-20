# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""LLM API 监控指标

提供 Prometheus 监控指标，用于观测 LLM API 调用情况。
"""

try:
    from prometheus_client import Counter, Gauge, Histogram, Info

    PROMETHEUS_AVAILABLE = True
except ImportError:
    # 如果没有安装 prometheus_client，使用空实现
    PROMETHEUS_AVAILABLE = False

    class Counter:
        def __init__(self, *args, **kwargs):
            pass

        def labels(self, *_args, **_kwargs):
            return self

        def inc(self, amount=1):
            pass

        def metrics(self):
            return []

    class Histogram:
        def __init__(self, *args, **kwargs):
            pass

        def labels(self, *_args, **_kwargs):
            return self

        def observe(self, amount):
            pass

        def metrics(self):
            return []

    class Gauge:
        def __init__(self, *args, **kwargs):
            pass

        def labels(self, *_args, **_kwargs):
            return self

        def set(self, value):
            pass

        def inc(self, amount=1):
            pass

        def dec(self, amount=1):
            pass

        def metrics(self):
            return []

    class Info:
        def __init__(self, *args, **kwargs):
            pass

        def info(self, info_dict):
            pass

        def metrics(self):
            return []


from dawei.logg.logging import get_logger

logger = get_logger(__name__)


# ==================== 速率限制指标 ====================

rate_limiter_current_rate = Gauge("llm_rate_limiter_current_rate", "Current rate limit (req/s)")

rate_limiter_adjustments = Counter(
    "llm_rate_limiter_adjustments_total",
    "Total rate adjustments",
    ["direction"],  # up/down
)

rate_limiter_wait_time = Histogram(
    "llm_rate_limiter_wait_seconds",
    "Time waiting for rate limiter",
    buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0),
)

# ==================== 请求队列指标 ====================

queue_size = Gauge(
    "llm_request_queue_size",
    "Current queue size",
    ["priority"],  # critical, high, normal, low
)

queue_waiting_time = Histogram(
    "llm_request_queue_waiting_seconds",
    "Time waiting in queue",
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0),
)

queue_processing_time = Histogram(
    "llm_request_queue_processing_seconds",
    "Time processing request",
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0),
)

queue_requests_total = Counter(
    "llm_request_queue_requests_total",
    "Total queue requests",
    ["status"],  # completed, failed, cancelled, timeout
)

# ==================== 断路器指标 ====================

circuit_breaker_state = Gauge(
    "llm_circuit_breaker_state",
    "Circuit breaker state (0=CLOSED, 1=OPEN, 2=HALF_OPEN)",
    ["provider"],
)

circuit_breaker_failures = Counter(
    "llm_circuit_breaker_failures_total",
    "Total circuit breaker failures",
    ["provider"],
)

circuit_breaker_successes = Counter(
    "llm_circuit_breaker_successes_total",
    "Total circuit breaker successes",
    ["provider"],
)

circuit_breaker_retries = Histogram(
    "llm_circuit_breaker_retry_attempts",
    "Retry attempts before success/failure",
    ["provider"],
    buckets=(1, 2, 3, 4, 5, 6, 7, 8, 9, 10),
)

# ==================== LLM API 指标 ====================

llm_requests_total = Counter(
    "llm_requests_total",
    "Total LLM API requests",
    ["provider", "model", "status"],  # status: success, error, timeout
)

llm_request_duration = Histogram(
    "llm_request_duration_seconds",
    "LLM API request duration",
    ["provider", "model"],
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0),
)

llm_request_size = Histogram(
    "llm_request_size_bytes",
    "LLM API request size (bytes)",
    ["provider", "model"],
    buckets=(100, 500, 1000, 5000, 10000, 50000, 100000, 500000),
)

llm_response_size = Histogram(
    "llm_response_size_bytes",
    "LLM API response size (bytes)",
    ["provider", "model"],
    buckets=(100, 500, 1000, 5000, 10000, 50000, 100000, 500000, 1000000),
)

llm_rate_limit_errors = Counter(
    "llm_rate_limit_errors_total",
    "Total rate limit errors (429)",
    ["provider", "model"],
)

llm_timeout_errors = Counter(
    "llm_timeout_errors_total",
    "Total timeout errors",
    ["provider", "model"],
)

llm_active_requests = Gauge(
    "llm_active_requests",
    "Current number of active LLM requests",
    ["provider"],
)

llm_tokens_used = Counter(
    "llm_tokens_used_total",
    "Total tokens used",
    ["provider", "model", "type"],  # Label names: prompt, completion
)

# ==================== 工具函数 ====================


def update_rate_limiter_metrics(stats: dict):
    """更新速率限制器指标"""
    rate_limiter_current_rate.set(stats.get("current_rate", 0.0))
    logger.debug(f"Updated rate limiter metrics: {stats}")


def update_queue_metrics(stats: dict):
    """更新请求队列指标"""
    queue_size.labels(priority="all").set(stats.get("current_queue_size", 0))
    queue_size.labels(priority="running").set(stats.get("current_running", 0))

    # 更新计数器
    for status in ["completed", "failed", "cancelled", "timeout"]:
        key = f"total_{status}"
        if key in stats:
            queue_requests_total.labels(status=status).inc(stats[key])

    logger.debug(f"Updated queue metrics: {stats}")


def update_circuit_breaker_metrics(provider: str, stats: dict):
    """更新断路器指标"""
    state_map = {"CLOSED": 0, "OPEN": 1, "HALF_OPEN": 2}
    state_value = state_map.get(stats.get("state", "CLOSED"), 0)
    circuit_breaker_state.labels(provider=provider).set(state_value)

    logger.debug(f"Updated circuit breaker metrics for {provider}: {stats}")


def record_llm_request(
    provider: str,
    model: str,
    duration: float,
    status: str,
    request_size: int = 0,
    response_size: int = 0,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
):
    """记录 LLM 请求指标"""
    # 请求总数
    llm_requests_total.labels(provider=provider, model=model, status=status).inc()

    # 请求时长
    llm_request_duration.labels(provider=provider, model=model).observe(duration)

    # 请求/响应大小
    if request_size > 0:
        llm_request_size.labels(provider=provider, model=model).observe(request_size)

    if response_size > 0:
        llm_response_size.labels(provider=provider, model=model).observe(response_size)

    # Token 使用
    if prompt_tokens > 0:
        llm_tokens_used.labels(provider=provider, model=model, type="prompt").inc(prompt_tokens)

    if completion_tokens > 0:
        llm_tokens_used.labels(provider=provider, model=model, type="completion").inc(
            completion_tokens,
        )

    logger.debug(
        f"Recorded LLM request: provider={provider}, model={model}, duration={duration:.2f}s, status={status}",
    )


def record_llm_rate_limit_error(provider: str, model: str):
    """记录速率限制错误"""
    llm_rate_limit_errors.labels(provider=provider, model=model).inc()
    logger.warning(f"Recorded rate limit error: provider={provider}, model={model}")


def record_llm_timeout_error(provider: str, model: str):
    """记录超时错误"""
    llm_timeout_errors.labels(provider=provider, model=model).inc()
    logger.warning(f"Recorded timeout error: provider={provider}, model={model}")


def increment_active_requests(provider: str):
    """增加活动请求数"""
    llm_active_requests.labels(provider=provider).inc()


def decrement_active_requests(provider: str):
    """减少活动请求数"""
    llm_active_requests.labels(provider=provider).dec()


def get_all_metrics() -> str:
    """获取所有 Prometheus 指标

    Returns:
        Prometheus 文本格式的指标

    """
    if not PROMETHEUS_AVAILABLE:
        return "# Prometheus metrics not available\n"

    try:
        from prometheus_client import REGISTRY, generate_latest

        metrics_bytes = generate_latest(REGISTRY)
        return metrics_bytes.decode("utf-8")
    except Exception as e:
        logger.exception("Failed to generate metrics: ")
        return f"# Error generating metrics: {e}\n"


def check_prometheus_available() -> bool:
    """检查 Prometheus 客户端是否可用"""
    return PROMETHEUS_AVAILABLE


if not PROMETHEUS_AVAILABLE:
    logger.warning(
        "prometheus_client not installed. Metrics will be collected but not exposed. Install with: pip install prometheus_client",
    )
