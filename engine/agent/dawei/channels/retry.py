"""Configurable exponential-backoff retry for async callables."""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

T = TypeVar("T")


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    attempts: int = 3
    min_delay_s: float = 0.3
    max_delay_s: float = 30.0
    jitter: float = 0.1


@dataclass
class RetryInfo:
    """Information passed to the on_retry callback."""

    attempt: int
    max_attempts: int
    delay_s: float
    error: Exception
    label: str | None = None


async def retry_async(
    fn: Callable[[], Awaitable[T]],
    config: RetryConfig | None = None,
    *,
    should_retry: Callable[[Exception, int], bool] | None = None,
    retry_after_s: Callable[[Exception], float | None] | None = None,
    on_retry: Callable[[RetryInfo], None] | None = None,
    label: str | None = None,
) -> T:
    """Execute fn with exponential-backoff retry."""
    if config is None:
        config = RetryConfig()

    last_exc: Exception | None = None
    for attempt in range(1, config.attempts + 1):
        try:
            return await fn()
        except Exception as exc:
            last_exc = exc

            if attempt >= config.attempts:
                raise

            if should_retry is not None and not should_retry(exc, attempt):
                raise

            server_delay: float | None = None
            if retry_after_s is not None:
                server_delay = retry_after_s(exc)

            if server_delay is not None:
                base_delay = max(server_delay, config.min_delay_s)
            else:
                base_delay = config.min_delay_s * (2 ** (attempt - 1))

            jittered = base_delay * (1 + random.uniform(-config.jitter, config.jitter))
            delay = max(config.min_delay_s, min(jittered, config.max_delay_s))

            if on_retry is not None:
                on_retry(
                    RetryInfo(
                        attempt=attempt,
                        max_attempts=config.attempts,
                        delay_s=delay,
                        error=exc,
                        label=label,
                    )
                )

            await asyncio.sleep(delay)

    assert last_exc is not None
    raise last_exc


TELEGRAM_RETRY = RetryConfig(attempts=3, min_delay_s=0.4, max_delay_s=30.0, jitter=0.1)
DEFAULT_RETRY = RetryConfig()

RETRY_PRESETS: dict[str, RetryConfig] = {
    "telegram": TELEGRAM_RETRY,
}
