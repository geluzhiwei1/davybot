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

    # ── C15 粒度/批量/单项失败（docs/子任务编排最优架构方案.md §4 C15）──
    granularity_rejected_total: int = 0  # 粒度硬闸 R1-R3 熔断次数
    granularity_by_rule: dict[str, int] = field(default_factory=dict)  # 按 R1/R2/R3 分布
    batch_dispatch_total: int = 0  # new_task_batch 派发次数
    batch_items_total: int = 0  # 批量条目总数
    batch_items_created: int = 0  # 批量创建成功数
    batch_items_duplicate: int = 0  # 批量去重命中数
    batch_items_error: int = 0  # 批量单项错误数（模板/粒度/创建失败）
    subtask_terminal_total: int = 0  # 子任务终态计数（parent_id 非空）
    subtask_terminal_by_status: dict[str, int] = field(default_factory=dict)  # 按终态分布
    batch_item_terminal_total: int = 0  # 批量条目到达终态数（单项失败率分母）
    batch_item_failed_total: int = 0  # 批量条目非 COMPLETED 终态数（分子）

    # ── C13/C15 自动重试命中率 ──
    llm_retry_scheduled_total: int = 0  # 瞬时错误自动重试发起次数（事件粒度）
    llm_retry_success_total: int = 0  # 经历过重试后最终成功的任务数（任务粒度）

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

    def record_granularity_rejected(self, rule: str = "unknown") -> None:
        """C15：记录一次粒度硬闸熔断（rule=R1/R2/R3）。"""
        with self._lock:
            self.granularity_rejected_total += 1
            self.granularity_by_rule[rule] = self.granularity_by_rule.get(rule, 0) + 1

    def record_batch_dispatch(self, items: int, created: int, duplicate: int = 0, error: int = 0) -> None:
        """C15：记录一次 new_task_batch 派发（含逐项结果分布）。"""
        with self._lock:
            self.batch_dispatch_total += 1
            self.batch_items_total += items
            self.batch_items_created += created
            self.batch_items_duplicate += duplicate
            self.batch_items_error += error

    def record_subtask_terminal(self, status: str, batch_item: bool = False) -> None:
        """C15：记录一次子任务终态转换（graph executor 状态写回 choke point）。

        batch_item=True 时额外累计批量单项终态/失败（单项失败率分子分母）。
        """
        with self._lock:
            self.subtask_terminal_total += 1
            self.subtask_terminal_by_status[status] = self.subtask_terminal_by_status.get(status, 0) + 1
            if batch_item:
                self.batch_item_terminal_total += 1
                if status != "completed":
                    self.batch_item_failed_total += 1

    def record_llm_retry_scheduled(self) -> None:
        """C13/C15：记录一次瞬时错误自动重试发起（事件粒度）。"""
        with self._lock:
            self.llm_retry_scheduled_total += 1

    def record_llm_retry_success(self) -> None:
        """C13/C15：记录一个经历过自动重试后最终成功的任务（任务粒度）。"""
        with self._lock:
            self.llm_retry_success_total += 1

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
                # C15 粒度/批量/单项失败率
                "granularity_rejected_total": self.granularity_rejected_total,
                "granularity_by_rule": dict(self.granularity_by_rule),
                "batch_dispatch_total": self.batch_dispatch_total,
                "batch_items_total": self.batch_items_total,
                "batch_items_created": self.batch_items_created,
                "batch_items_duplicate": self.batch_items_duplicate,
                "batch_items_error": self.batch_items_error,
                "batch_item_creation_rate": round(self.batch_items_created / max(self.batch_items_total, 1), 4),
                "subtask_terminal_total": self.subtask_terminal_total,
                "subtask_terminal_by_status": dict(self.subtask_terminal_by_status),
                "batch_item_terminal_total": self.batch_item_terminal_total,
                "batch_item_failed_total": self.batch_item_failed_total,
                "batch_item_failure_rate": round(self.batch_item_failed_total / max(self.batch_item_terminal_total, 1), 4),
                # C13/C15 自动重试命中率（任务粒度成功 / 事件粒度发起）
                "llm_retry_scheduled_total": self.llm_retry_scheduled_total,
                "llm_retry_success_total": self.llm_retry_success_total,
                "llm_retry_success_rate": round(self.llm_retry_success_total / max(self.llm_retry_scheduled_total, 1), 4),
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
            self.granularity_rejected_total = 0
            self.granularity_by_rule.clear()
            self.batch_dispatch_total = 0
            self.batch_items_total = 0
            self.batch_items_created = 0
            self.batch_items_duplicate = 0
            self.batch_items_error = 0
            self.subtask_terminal_total = 0
            self.subtask_terminal_by_status.clear()
            self.batch_item_terminal_total = 0
            self.batch_item_failed_total = 0
            self.llm_retry_scheduled_total = 0
            self.llm_retry_success_total = 0
            self._start_time = time.time()


# 单例
_metrics: SubtaskMetrics | None = None


def get_metrics() -> SubtaskMetrics:
    """获取全局 SubtaskMetrics 单例。"""
    global _metrics
    if _metrics is None:
        _metrics = SubtaskMetrics()
    return _metrics
