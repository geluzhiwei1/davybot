# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Governance Metrics — 工具输出治理的指标收集。

轻量级内存计数器，不依赖 prometheus_client。
可被日志系统或 API 查询。
"""

import logging
import threading
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class GovernanceMetrics:
    """治理指标收集器（线程安全）。"""

    # ── 总体计数 ──
    total_calls: int = 0
    total_truncated: int = 0
    total_passthrough: int = 0  # 在预算内直接通过
    total_errors: int = 0

    # ── 字节/Token 统计 ──
    total_original_bytes: int = 0
    total_governed_bytes: int = 0
    total_tokens_saved: int = 0  # 估算节省的 token 数

    # ── 按工具统计 ──
    per_tool_calls: dict[str, int] = field(default_factory=dict)
    per_tool_truncated: dict[str, int] = field(default_factory=dict)
    per_tool_bytes_saved: dict[str, int] = field(default_factory=dict)

    # ── 按格式类型 ──
    per_format_count: dict[str, int] = field(default_factory=dict)

    # ── 快照统计 ──
    total_snapshots: int = 0
    total_snapshot_errors: int = 0

    # ── 时间统计 ──
    _start_time: float = field(default_factory=time.time)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def record_call(
        self,
        tool_name: str,
        original_bytes: int,
        governed_bytes: int,
        was_truncated: bool,
        format_type: str,
        tokens_saved: int = 0,
    ) -> None:
        """记录一次治理调用。"""
        with self._lock:
            self.total_calls += 1
            self.total_original_bytes += original_bytes
            self.total_governed_bytes += governed_bytes

            self.per_tool_calls[tool_name] = self.per_tool_calls.get(tool_name, 0) + 1
            self.per_format_count[format_type] = self.per_format_count.get(format_type, 0) + 1

            if was_truncated:
                self.total_truncated += 1
                self.per_tool_truncated[tool_name] = self.per_tool_truncated.get(tool_name, 0) + 1
                bytes_saved = original_bytes - governed_bytes
                self.per_tool_bytes_saved[tool_name] = self.per_tool_bytes_saved.get(tool_name, 0) + bytes_saved
                self.total_tokens_saved += tokens_saved
            else:
                self.total_passthrough += 1

    def record_snapshot(self, success: bool) -> None:
        """记录快照操作。"""
        with self._lock:
            if success:
                self.total_snapshots += 1
            else:
                self.total_snapshot_errors += 1

    def record_error(self) -> None:
        """记录治理错误。"""
        with self._lock:
            self.total_errors += 1

    def get_summary(self) -> dict:
        """获取指标摘要。"""
        with self._lock:
            uptime = time.time() - self._start_time
            compression_ratio = 0.0
            if self.total_original_bytes > 0:
                compression_ratio = 1.0 - (self.total_governed_bytes / self.total_original_bytes)

            return {
                "uptime_seconds": round(uptime, 1),
                "total_calls": self.total_calls,
                "total_truncated": self.total_truncated,
                "total_passthrough": self.total_passthrough,
                "total_errors": self.total_errors,
                "truncation_rate": round(self.total_truncated / max(self.total_calls, 1), 4),
                "total_original_bytes": self.total_original_bytes,
                "total_governed_bytes": self.total_governed_bytes,
                "total_bytes_saved": self.total_original_bytes - self.total_governed_bytes,
                "compression_ratio": round(compression_ratio, 4),
                "total_tokens_saved": self.total_tokens_saved,
                "total_snapshots": self.total_snapshots,
                "total_snapshot_errors": self.total_snapshot_errors,
                "top_truncated_tools": sorted(
                    self.per_tool_truncated.items(), key=lambda x: x[1], reverse=True
                )[:10],
                "top_bytes_saved_tools": sorted(
                    self.per_tool_bytes_saved.items(), key=lambda x: x[1], reverse=True
                )[:10],
                "format_distribution": dict(self.per_format_count),
            }

    def reset(self) -> None:
        """重置所有指标。"""
        with self._lock:
            self.total_calls = 0
            self.total_truncated = 0
            self.total_passthrough = 0
            self.total_errors = 0
            self.total_original_bytes = 0
            self.total_governed_bytes = 0
            self.total_tokens_saved = 0
            self.per_tool_calls.clear()
            self.per_tool_truncated.clear()
            self.per_tool_bytes_saved.clear()
            self.per_format_count.clear()
            self.total_snapshots = 0
            self.total_snapshot_errors = 0
            self._start_time = time.time()


# 单例
_metrics: GovernanceMetrics | None = None


def get_metrics() -> GovernanceMetrics:
    """获取全局 GovernanceMetrics 单例。"""
    global _metrics
    if _metrics is None:
        _metrics = GovernanceMetrics()
    return _metrics
