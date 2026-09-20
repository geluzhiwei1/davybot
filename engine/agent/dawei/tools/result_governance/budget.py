# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""L3 — Token 预算

渲染期运行预算：边写边扣，用尽即停。
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .token_estimator import TokenEstimator


class TokenBudget:
    """渲染期运行预算：边写边扣，用尽即停。"""

    def __init__(self, total_tokens: int, estimator: "TokenEstimator"):
        self._total = total_tokens
        self._remaining = total_tokens
        self._est = estimator
        self.consumed = 0

    def remaining(self) -> int:
        return self._remaining

    def fits(self, text: str) -> bool:
        """检查文本是否在剩余预算内（不扣减）。"""
        return self._est.estimate(text) <= self._remaining

    def consume(self, text: str) -> bool:
        """扣减预算。返回 False = 超限，调用方应停止追加。"""
        cost = self._est.estimate(text)
        if cost > self._remaining:
            return False
        self._remaining -= cost
        self.consumed += cost
        return True

    def split(self, *ratios: float) -> tuple["TokenBudget", ...]:
        """按比例拆分子预算（用于 C 类嵌套对象的预算分摊）。

        ratios 的和应 ≤ 1.0。剩余部分不分配。
        """
        # 验证 ratios
        total_ratio = sum(ratios)
        if total_ratio > 1.0 + 1e-6:
            # 归一化
            ratios = tuple(r / total_ratio for r in ratios)

        sub_budgets = []
        for r in ratios:
            allocated = int(self._remaining * r)
            sb = TokenBudget(allocated, self._est)
            sub_budgets.append(sb)

        return tuple(sub_budgets)

    def truncate_to_budget(self, text: str) -> str:
        """截断字符串到剩余预算内，尾部加省略号。"""
        if not text:
            return ""

        # 快速路径：如果 fits，直接返回
        if self.fits(text):
            self.consume(text)
            return text

        # 二分搜索截断点
        # 估算字符/token 比率
        sample_len = min(len(text), 200)
        sample_tokens = self._est.estimate(text[:sample_len])
        if sample_tokens == 0:
            chars_per_token = 4
        else:
            chars_per_token = sample_len / sample_tokens

        # 估算可容纳的字符数
        max_chars = int(self._remaining * chars_per_token * 0.9)  # 90% 安全余量
        if max_chars <= 0:
            return ""

        truncated = text[:max_chars]
        # 逐步缩减直到 fit
        while truncated and not self._est.estimate(truncated + "\n…(已截断)") <= self._remaining:
            truncated = truncated[:-100]
            if len(truncated) <= 0:
                break

        self.consume(truncated)
        return truncated
