# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Subtask Metrics — 子任务交付质量指标（§8 验收埋点）。

对应 docs/子任务组织管理交互方案.md §8 验收指标表的可代码度量项：
- 报告"(无显式完成结果)"占位率   → record_report(placeholder=...)
- 会话扫描兜底命中率             → record_scan_fallback(isolated=...)
- 重复子任务率(同父同目标重派)   → record_redispatch(prior_status=...)
- 广度闸拒绝(一轮爆量派发被拦截) → record_breadth_rejected()

设计镜像 dawei/tools/result_governance/metrics.py：轻量内存计数器、
线程安全、不依赖 prometheus_client；经 REST
GET/POST /api/workspaces/{ws}/subtasks/metrics[/reset] 查询/清零。

写入方全部 fire-and-forget：指标失败绝不影响主流程（不变量 5）。
"""

import threading
import time
from dataclasses import dataclass, field

PLACEHOLDER_TEXT = "(无显式完成结果)"


@dataclass
class SubtaskMetrics:
    """子任务质量指标收集器（线程安全，进程级单例）。"""

    # ── 创建侧 ──
    creations_total: int = 0  # 子任务创建成功总数（重派率分母）
    breadth_rejected_total: int = 0  # 图谱层广度闸拒绝次数

    # ── 交付侧（报告条目粒度：每个子任务一条）──
    reports_total: int = 0
    reports_placeholder: int = 0  # result 落占位符（SSOT+扫描链均无果）

    # ── 兼容链路 ──
    scan_fallback_isolated: int = 0  # SSOT 缺失 → 隔离会话定向提取
    scan_fallback_shared: int = 0  # SSOT 缺失 → 共享对话位置匹配

    # ── 重派信号 ──
    redispatch_total: int = 0  # 同父同目标(strip 精确匹配)重派次数
    redispatch_by_prior: dict[str, int] = field(default_factory=dict)  # 按前次终态分布

    _start_time: float = field(default_factory=time.time)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def record_creation(self) -> None:
        """记录一次子任务创建成功。"""
        with self._lock:
            self.creations_total += 1

    def record_breadth_rejected(self) -> None:
        """记录一次图谱层广度闸拒绝。"""
        with self._lock:
            self.breadth_rejected_total += 1

    def record_report(self, placeholder: bool) -> None:
        """记录一条子任务报告条目。"""
        with self._lock:
            self.reports_total += 1
            if placeholder:
                self.reports_placeholder += 1

    def record_scan_fallback(self, isolated: bool) -> None:
        """记录一次 SSOT 缺失回落旧提取链（弃用观察指标）。"""
        with self._lock:
            if isolated:
                self.scan_fallback_isolated += 1
            else:
                self.scan_fallback_shared += 1

    def record_redispatch(self, prior_status: str) -> None:
        """记录一次同父同目标重派（prior_status=前次终态，CANCELLED 违反不变量 6）。"""
        with self._lock:
            self.redispatch_total += 1
            self.redispatch_by_prior[prior_status] = self.redispatch_by_prior.get(prior_status, 0) + 1

    def get_summary(self) -> dict:
        """指标摘要（含 §8 验收表派生比率）。"""
        with self._lock:
            scan_total = self.scan_fallback_isolated + self.scan_fallback_shared
            return {
                "uptime_seconds": round(time.time() - self._start_time, 1),
                "creations_total": self.creations_total,
                "breadth_rejected_total": self.breadth_rejected_total,
                "reports_total": self.reports_total,
                "reports_placeholder": self.reports_placeholder,
                "placeholder_rate": round(self.reports_placeholder / max(self.reports_total, 1), 4),
                "scan_fallback_total": scan_total,
                "scan_fallback_isolated": self.scan_fallback_isolated,
                "scan_fallback_shared": self.scan_fallback_shared,
                "scan_fallback_rate": round(scan_total / max(self.reports_total, 1), 4),
                "redispatch_total": self.redispatch_total,
                "redispatch_by_prior": dict(self.redispatch_by_prior),
                "redispatch_rate": round(self.redispatch_total / max(self.creations_total, 1), 4),
            }

    def reset(self) -> None:
        """重置所有指标。"""
        with self._lock:
            self.creations_total = 0
            self.breadth_rejected_total = 0
            self.reports_total = 0
            self.reports_placeholder = 0
            self.scan_fallback_isolated = 0
            self.scan_fallback_shared = 0
            self.redispatch_total = 0
            self.redispatch_by_prior.clear()
            self._start_time = time.time()


# 单例
_metrics: SubtaskMetrics | None = None


def get_metrics() -> SubtaskMetrics:
    """获取全局 SubtaskMetrics 单例。"""
    global _metrics
    if _metrics is None:
        _metrics = SubtaskMetrics()
    return _metrics
