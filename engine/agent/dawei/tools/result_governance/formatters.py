# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""L5 — 渲染器（按类型策略模式）

BlobWindow: 大块文本的 head+tail 窗口渲染
ListPageEnvelope: 同构列表的分页信封
StructuredRenderer: 嵌套对象的字段级预算分摊渲染
"""

import json
import logging
from collections.abc import Callable
from typing import Any, Generic, TypeVar

from .budget import TokenBudget
from .policy import OutputPolicy

logger = logging.getLogger(__name__)

T = TypeVar("T")


# ════════════ A 类：Blob 渲染器 ════════════


class BlobWindow:
    """大块文本的 head+tail 窗口渲染。

    策略：前 blob_head_ratio 的预算给 head，剩余给 tail。
    中间被丢弃的部分用 '...（省略 N 行）...' 标记。
    支持行级偏移（start_line），让 LLM 能翻窗。
    """

    @staticmethod
    def render(
        text: str,
        policy: OutputPolicy,
        budget: TokenBudget,
        *,
        start_line: int = 1,
        total_lines: int | None = None,
    ) -> dict[str, Any]:
        """渲染 head+tail 窗口。

        返回结构化 dict：
        {
            "type": "blob_window",
            "head": [...],      # 头部行列表
            "tail": [...],      # 尾部行列表
            "total_lines": int,
            "omitted": int,     # 省略行数
            "head_lines": int,
            "tail_lines": int,
            "hint": str,
        }
        """
        lines = text.split("\n")
        if total_lines is None:
            total_lines = len(lines)

        max_lines = policy.blob_max_lines
        head_count = max(1, int(max_lines * policy.blob_head_ratio))
        tail_count = max(1, max_lines - head_count)

        if len(lines) <= max_lines:
            # 不需要截断
            return {
                "type": "blob_window",
                "head": lines,
                "tail": [],
                "total_lines": total_lines,
                "omitted": 0,
                "head_lines": len(lines),
                "tail_lines": 0,
                "hint": "",
            }

        # 取 head 和 tail
        head_lines = lines[:head_count]
        tail_lines = lines[-tail_count:]
        omitted = len(lines) - head_count - tail_count

        next_start = start_line + head_count
        hint = policy.blob_window_hint.format(next=next_start)

        return {
            "type": "blob_window",
            "head": head_lines,
            "tail": tail_lines,
            "total_lines": total_lines,
            "omitted": omitted,
            "head_lines": head_count,
            "tail_lines": tail_count,
            "hint": hint,
        }

    @staticmethod
    def render_text(
        text: str,
        policy: OutputPolicy,
        budget: TokenBudget,
        *,
        start_line: int = 1,
    ) -> str:
        """渲染为纯文本格式（用于 LLM）。"""
        result = BlobWindow.render(text, policy, budget, start_line=start_line)
        parts = []

        # 添加行号
        for i, line in enumerate(result["head"]):
            line_num = start_line + i
            parts.append(f"[L{line_num:04d}] {line}")

        if result["omitted"] > 0:
            parts.append(f"\n...（省略 {result['omitted']} 行）...\n")
            parts.append(result["hint"])
            parts.append("")

        tail_start = start_line + result["head_lines"] + result["omitted"]
        for i, line in enumerate(result["tail"]):
            line_num = tail_start + i
            parts.append(f"[L{line_num:04d}] {line}")

        parts.append(f"\n---\n显示 {result['head_lines'] + result['tail_lines']}/{result['total_lines']} 行。")
        if result["hint"]:
            parts.append(result["hint"])

        return "\n".join(parts)


# ════════════ B 类：List 分页信封 ════════════


class ListPageEnvelope(Generic[T]):
    """同构列表的分页信封。"""

    def __init__(
        self,
        items: list[T],
        total: int,
        offset: int = 0,
        limit: int | None = None,
        has_more: bool = False,
        next_offset: int | None = None,
        summary: str | None = None,
    ):
        self.items = items
        self.total = total
        self.offset = offset
        self.limit = limit or len(items)
        self.has_more = has_more
        self.next_offset = next_offset
        self.summary = summary

    @classmethod
    def from_api_result(
        cls,
        raw: dict,
        *,
        items_keys: list[str] | None = None,
        total_keys: list[str] | None = None,
        offset: int = 0,
        limit: int = 20,
    ):
        """从异构 API 响应规范化。

        兼容 items/results/entities/hits 等字段名。
        """
        items_keys = items_keys or ["items", "results", "entities", "hits", "data", "documents", "records"]
        total_keys = total_keys or ["total", "total_count", "count", "num_found", "found"]

        items: list = []
        for key in items_keys:
            if key in raw and isinstance(raw[key], list):
                items = raw[key]
                break

        total = len(items)
        for key in total_keys:
            if key in raw and isinstance(raw[key], int):
                total = raw[key]
                break

        has_more = (offset + len(items)) < total
        next_offset = offset + len(items) if has_more else None

        return cls(
            items=items,
            total=total,
            offset=offset,
            limit=limit,
            has_more=has_more,
            next_offset=next_offset,
        )

    def to_dict(self) -> dict[str, Any]:
        """转换为前端可消费的 dict。"""
        return {
            "type": "list_page",
            "items": self.items,
            "total": self.total,
            "offset": self.offset,
            "limit": self.limit,
            "has_more": self.has_more,
            "next_offset": self.next_offset,
            "summary": self.summary,
        }

    def render_text(
        self,
        policy: OutputPolicy,
        budget: TokenBudget,
        item_summary_fn: Callable[[T], str] | None = None,
        item_detail_fn: Callable[[T, TokenBudget], str] | None = None,
    ) -> str:
        """渲染为纯文本格式（用于 LLM）。"""
        if not self.items:
            return "（无结果）"

        parts = []

        # 如果总数超过 summary_threshold，用概要模式
        use_summary = self.total > policy.list_summary_threshold and item_summary_fn

        if use_summary:
            parts.append(f"📊 共 {self.total} 条结果（仅显示概要）：\n")
            for i, item in enumerate(self.items[: policy.list_max_items]):
                summary = item_summary_fn(item)
                if len(summary) > policy.list_item_max_chars:
                    summary = summary[: policy.list_item_max_chars] + "..."
                line = f"{i + 1 + self.offset}. {summary}"
                if not budget.consume(line + "\n"):
                    parts.append(f"\n...(预算用尽，还有 {len(self.items) - i} 条未显示)")
                    break
                parts.append(line)
        else:
            for i, item in enumerate(self.items[: policy.list_max_items]):
                if item_detail_fn:
                    detail = item_detail_fn(item, budget)
                elif isinstance(item, str):
                    detail = item[: policy.list_item_max_chars]
                else:
                    detail = json.dumps(item, ensure_ascii=False, default=str)[: policy.list_item_max_chars]

                line = f"[{i + 1 + self.offset}] {detail}"
                if not budget.consume(line + "\n"):
                    parts.append(f"\n...(预算用尽，还有 {len(self.items) - i} 条未显示)")
                    break
                parts.append(line)

        # 分页指示器
        shown = min(len(self.items), policy.list_max_items)
        parts.append(f"\n---\n📊 显示 {shown}/{self.total} 条（offset={self.offset}）。")
        if self.has_more and self.next_offset is not None:
            parts.append(policy.list_page_hint.format(next=self.next_offset))

        return "\n".join(parts)


# ════════════ C 类：Structured 渲染器 ════════════


class StructuredRenderer:
    """嵌套对象的字段级预算分摊渲染。

    主对象占固定比例，每个子集合各占 policy.structured_field_budget 指定的比例。
    """

    @staticmethod
    def render(
        main_fields: dict[str, str],
        sub_collections: dict[str, list[dict]],
        policy: OutputPolicy,
        budget: TokenBudget,
    ) -> str:
        """渲染嵌套对象。

        Args:
            main_fields: 主对象 KV
            sub_collections: 子集合 {name: [items]}
            policy: 输出策略
            budget: 总预算

        Returns:
            渲染后的文本
        """
        # 获取字段比例配置
        field_budget = policy.structured_field_budget
        if not field_budget:
            # 默认：main 独占全部
            field_budget = {"main": 1.0}

        # 分配预算
        all_keys = ["main"] + list(sub_collections.keys())
        ratios = [field_budget.get(k, 0.05) for k in all_keys]
        sub_budgets = budget.split(*ratios)

        parts = []

        # 渲染主字段
        main_budget = sub_budgets[0]
        parts.append("📋 基本信息：")
        for k, v in main_fields.items():
            line = f"  {k}: {v}"
            if not main_budget.consume(line + "\n"):
                parts.append("  ...(基本信息预算用尽)")
                break
            parts.append(line)

        # 渲染子集合
        for idx, (name, items) in enumerate(sub_collections.items()):
            sub_budget = sub_budgets[idx + 1] if idx + 1 < len(sub_budgets) else budget
            if not items:
                continue

            parts.append(f"\n📎 {name}（{len(items)} 项）：")
            max_items = min(len(items), policy.structured_array_max)
            for i, item in enumerate(items[:max_items]):
                if isinstance(item, dict):
                    item_str = json.dumps(item, ensure_ascii=False, default=str)
                else:
                    item_str = str(item)

                # 限制单项大小
                max_item_chars = max(100, (sub_budget.remaining() * 4))
                if len(item_str) > max_item_chars:
                    item_str = item_str[: int(max_item_chars)] + "..."

                line = f"  [{i + 1}] {item_str}"
                if not sub_budget.consume(line + "\n"):
                    remaining = len(items) - i
                    if remaining > 0:
                        parts.append(f"  ...({remaining} 项未显示，预算用尽)")
                    break
                parts.append(line)

            if len(items) > max_items:
                parts.append(f"  ...(共 {len(items)} 项，仅显示前 {max_items} 项)")

        return "\n".join(parts)
