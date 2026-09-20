# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Sliding-window rate limiter for tool execution (P3 域11).

Stops runaway agents from hammering tools. Process-global, per-category.
The per-minute cap is read from ``effective.rate_limit`` (default ``0`` =
unlimited → no-op until configured, so this is a safe, zero-behavior rollout).

A check that fails to read the policy or acquire state NEVER blocks execution
(fail-open) — rate limiting is a guard, not a hard dependency.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Dict, List

logger = logging.getLogger(__name__)

_WINDOW_SECONDS = 60.0


class ToolRateLimiter:
    """Sliding-window per-category rate limiter."""

    def __init__(self) -> None:
        self._windows: Dict[str, List[float]] = {}
        self._lock = threading.Lock()

    def _limit_for(self, category: str) -> int:
        """Resolve the per-minute limit from the effective policy (0 = unlimited)."""
        try:
            from dawei.core.security_manager import security_manager

            policy = security_manager.get_policy().rate_limit
            if category == "tool":
                return policy.tool_calls_per_minute
        except Exception as e:  # pragma: no cover - never block on policy read
            logger.warning(f"ToolRateLimiter: policy read failed: {e}")
        return 0

    def check_and_consume(self, category: str = "tool") -> bool:
        """Return True if allowed (and consume one slot); False if over the limit."""
        limit = self._limit_for(category)
        if limit <= 0:
            return True  # unlimited
        now = time.monotonic()
        cutoff = now - _WINDOW_SECONDS
        with self._lock:
            timestamps = self._windows.setdefault(category, [])
            # prune entries older than the window
            timestamps[:] = [t for t in timestamps if t >= cutoff]
            if len(timestamps) >= limit:
                return False
            timestamps.append(now)
            return True

    def reset(self) -> None:
        """Clear all windows (for tests)."""
        with self._lock:
            self._windows.clear()


#: Module-level singleton shared by ToolExecutor.
tool_rate_limiter = ToolRateLimiter()
