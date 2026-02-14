# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""LLM 成本追踪器
实时追踪 LLM 调用成本，提供优化建议
"""

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone

from dawei.llm_api.model_router import ModelCost, load_cost_config


@dataclass
class LLMMCall:
    """单次 LLM 调用记录"""

    model: str
    input_tokens: int
    output_tokens: int
    cost: float
    timestamp: datetime
    task_type: str = "general"
    duration_ms: float | None = None


@dataclass
class CostSummary:
    """成本汇总"""

    total_cost: float
    total_calls: int
    total_input_tokens: int
    total_output_tokens: int
    by_model: dict[str, dict]
    by_task_type: dict[str, dict]
    avg_cost_per_call: float


class CostTracker:
    """LLM 成本追踪器"""

    def __init__(self, cost_config: dict[str, ModelCost] | None = None):
        """初始化成本追踪器

        Args:
            cost_config: 模型定价配置（可选）

        """
        self.cost_config = cost_config or load_cost_config()
        self.calls: list[LLMMCall] = []
        self.session_start = datetime.now(timezone.utc)
        self.logger = logging.getLogger(__name__)

    def record_call(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        task_type: str = "general",
        duration_ms: float | None = None,
    ):
        """记录 LLM 调用

        Args:
            model: 使用的模型
            input_tokens: 输入 token 数
            output_tokens: 输出 token 数
            task_type: 任务类型
            duration_ms: 调用耗时（毫秒）

        """
        # 计算成本
        cost = self._calculate_cost(model, input_tokens, output_tokens)

        call = LLMMCall(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost,
            timestamp=datetime.now(timezone.utc),
            task_type=task_type,
            duration_ms=duration_ms,
        )

        self.calls.append(call)

        # 发布事件（通过 logger 临时实现）
        self.logger.debug(
            f"LLM call recorded: {model} - {input_tokens + output_tokens} tokens = ${cost:.4f}",
        )

    def _calculate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """计算调用成本"""
        cost_info = self.cost_config.get(model)
        if not cost_info:
            # 未知模型，成本记为 0
            return 0.0

        return cost_info.calculate_cost(input_tokens, output_tokens)

    def get_summary(self) -> CostSummary:
        """获取成本汇总

        Returns:
            成本汇总信息

        """
        total_cost = sum(c.cost for c in self.calls)
        total_input = sum(c.input_tokens for c in self.calls)
        total_output = sum(c.output_tokens for c in self.calls)

        # 按模型统计
        by_model = defaultdict(lambda: {"calls": 0, "tokens": 0, "cost": 0.0})
        for call in self.calls:
            by_model[call.model]["calls"] += 1
            by_model[call.model]["tokens"] += call.input_tokens + call.output_tokens
            by_model[call.model]["cost"] += call.cost

        # 按任务类型统计
        by_task = defaultdict(lambda: {"calls": 0, "cost": 0.0})
        for call in self.calls:
            by_task[call.task_type]["calls"] += 1
            by_task[call.task_type]["cost"] += call.cost

        avg_cost = total_cost / len(self.calls) if self.calls else 0.0

        return CostSummary(
            total_cost=round(total_cost, 4),
            total_calls=len(self.calls),
            total_input_tokens=total_input,
            total_output_tokens=total_output,
            by_model=dict(by_model),
            by_task_type=dict(by_task),
            avg_cost_per_call=round(avg_cost, 4),
        )

    def get_optimization_suggestions(self) -> list[str]:
        """获取成本优化建议

        Returns:
            优化建议列表

        """
        suggestions = []
        summary = self.get_summary()

        if summary.total_calls == 0:
            return ["暂无数据，请先进行一些 LLM 调用"]

        # 检查高成本模型使用频率
        expensive_models = [(model, data) for model, data in summary.by_model.items() if data["cost"] > summary.total_cost * 0.5]

        for model, data in expensive_models:
            percentage = (data["cost"] / summary.total_cost) * 100
            cheaper_alternatives = self._find_cheaper_alternatives(model)

            if cheaper_alternatives:
                alternatives_str = ", ".join(cheaper_alternatives[:3])
                suggestions.append(
                    f"模型 {model} 占用了 {percentage:.1f}% 成本。建议为日常任务切换到 {alternatives_str}",
                )
            else:
                suggestions.append(
                    f"模型 {model} 占用了 {percentage:.1f}% 成本。考虑减少使用频率或使用本地模型",
                )

        # 检查是否可以使用本地模型
        code_completion_tasks = summary.by_task_type.get("code_completion", {})
        if code_completion_tasks and "calls" in code_completion_tasks and code_completion_tasks["calls"] > 10:
            potential_savings = code_completion_tasks.get("cost", 0.0)
            suggestions.append(
                f"代码补全已调用 {code_completion_tasks['calls']} 次，建议使用本地 Qwen 模型以节省 ${potential_savings:.2f}",
            )

        # 检查默认模型是否合理
        if summary.total_calls > 20 and summary.by_model:
            most_used_model = max(summary.by_model.items(), key=lambda x: x[1]["calls"])
            if most_used_model[0] in ["anthropic/claude-opus-4", "openai/gpt-4"]:
                suggestions.append(
                    f"最常用模型是 {most_used_model[0]}，成本较高。建议将默认模型改为 deepseek-chat 以降低日常成本",
                )

        if not suggestions:
            suggestions.append("当前配置合理，成本优化良好！")

        return suggestions

    def _find_cheaper_alternatives(self, model: str) -> list[str]:
        """查找更便宜的替代模型"""
        # 获取当前模型成本
        current_cost_info = self.cost_config.get(model)
        if not current_cost_info:
            return []

        current_cost = current_cost_info.input + current_cost_info.output

        # 查找更便宜的模型
        alternatives = []
        for alt_model, alt_cost_info in self.cost_config.items():
            if alt_model == model:
                continue

            alt_cost = alt_cost_info.input + alt_cost_info.output
            if alt_cost < current_cost * 0.5:  # 便宜 50% 以上
                alternatives.append((alt_model, alt_cost))

        # 【修复】使用元组而不是字符串，避免解析问题
        return [f"{model} (${cost:.4f}/1M)" for model, cost in sorted(alternatives, key=lambda x: x[1])]

    def export_report(self) -> dict:
        """导出成本报告

        Returns:
            完整的成本报告

        """
        summary = self.get_summary()
        suggestions = self.get_optimization_suggestions()

        duration = datetime.now(timezone.utc) - self.session_start
        hours = duration.total_seconds() / 3600

        return {
            "session_duration_hours": round(hours, 2),
            "summary": {
                "total_cost": summary.total_cost,
                "total_calls": summary.total_calls,
                "total_tokens": summary.total_input_tokens + summary.total_output_tokens,
                "avg_cost_per_call": summary.avg_cost_per_call,
                "cost_per_hour": round(summary.total_cost / hours, 4) if hours > 0 else 0,
            },
            "by_model": summary.by_model,
            "by_task_type": summary.by_task_type,
            "optimization_suggestions": suggestions,
            "recent_calls": [
                {
                    "model": c.model,
                    "tokens": c.input_tokens + c.output_tokens,
                    "cost": c.cost,
                    "timestamp": c.timestamp.isoformat(),
                }
                for c in self.calls[-10:]  # 最近 10 次调用
            ],
        }

    def reset(self):
        """重置追踪器"""
        self.calls.clear()
        self.session_start = datetime.now(timezone.utc)
        self.logger.info("Cost tracker reset")
