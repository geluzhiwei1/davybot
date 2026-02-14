# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""成本追踪工具 - 显示 LLM 使用成本和优化建议"""

import json
from datetime import UTC, datetime, timezone

from pydantic import BaseModel, Field

from dawei.core.decorators import safe_tool_operation
from dawei.tools.custom_base_tool import CustomBaseTool


class ShowCostInput(BaseModel):
    """Input for ShowCostTool."""

    detail_level: str = Field(
        "summary",
        description="Detail level: 'summary' for brief overview, 'detailed' for full breakdown, 'suggestions' for optimization tips.",
    )


class ShowCostTool(CustomBaseTool):
    """Tool for displaying LLM usage costs and optimization suggestions."""

    name: str = "show_cost"
    description: str = "Display current session LLM costs, token usage, and optimization suggestions."
    args_schema: type[BaseModel] = ShowCostInput

    def __init__(self, agent=None):
        """Initialize ShowCostTool

        Args:
            agent: Agent instance (optional, will try to get from context if not provided)

        """
        super().__init__()
        self.agent = agent

    def set_agent(self, agent):
        """Set agent reference"""
        self.agent = agent

    @safe_tool_operation(
        "show_cost",
        fallback_value='{"status": "error", "message": "Cost tracking not available"}',
    )
    def _run(self, detail_level: str = "summary") -> str:
        """Display cost information

        Args:
            detail_level: Level of detail ('summary', 'detailed', 'suggestions')

        Returns:
            Formatted cost report as JSON string

        """
        # Get cost tracker from agent
        if not self.agent or not hasattr(self.agent, "cost_tracker"):
            return json.dumps(
                {"status": "error", "message": "Cost tracker not initialized"},
                indent=2,
            )

        tracker = self.agent.cost_tracker
        summary = tracker.get_summary()

        # Build response based on detail level
        if detail_level == "summary":
            return self._format_summary(summary, tracker)
        if detail_level == "detailed":
            return self._format_detailed(summary, tracker)
        if detail_level == "suggestions":
            return self._format_suggestions(summary, tracker)
        return self._format_summary(summary, tracker)

    def _format_summary(self, summary, tracker) -> str:
        """Format summary level report"""
        duration = datetime.now(UTC) - tracker.session_start
        hours = duration.total_seconds() / 3600

        output = {
            "status": "success",
            "level": "summary",
            "session_duration": f"{hours:.2f} hours",
            "total_cost": f"${summary.total_cost:.4f}",
            "total_calls": summary.total_calls,
            "total_tokens": summary.total_input_tokens + summary.total_output_tokens,
            "input_tokens": summary.total_input_tokens,
            "output_tokens": summary.total_output_tokens,
            "top_model": self._get_top_model(summary),
            "average_cost_per_call": f"${summary.total_cost / max(summary.total_calls, 1):.4f}",
        }

        return json.dumps(output, indent=2, ensure_ascii=False)

    def _format_detailed(self, summary, tracker) -> str:
        """Format detailed level report"""
        duration = datetime.now(UTC) - tracker.session_start
        hours = duration.total_seconds() / 3600

        output = {
            "status": "success",
            "level": "detailed",
            "session_info": {
                "start_time": tracker.session_start.strftime("%Y-%m-%d %H:%M:%S"),
                "duration_hours": f"{hours:.2f}",
                "duration_formatted": str(duration).split(".")[0],  # Remove microseconds
            },
            "overall_stats": {
                "total_cost": f"${summary.total_cost:.4f}",
                "total_calls": summary.total_calls,
                "total_tokens": summary.total_input_tokens + summary.total_output_tokens,
                "input_tokens": summary.total_input_tokens,
                "output_tokens": summary.total_output_tokens,
                "average_cost_per_1k_tokens": f"${(summary.total_cost / max(summary.total_input_tokens + summary.total_output_tokens, 1)) * 1000:.4f}",
            },
            "by_model": {},
            "by_task_type": {},
        }

        # Model breakdown
        for model, data in summary.by_model.items():
            output["by_model"][model] = {
                "calls": data["calls"],
                "tokens": data["tokens"],
                "cost": f"${data['cost']:.4f}",
                "percentage": f"{(data['cost'] / max(summary.total_cost, 1)) * 100:.1f}%",
            }

        # Task type breakdown
        for task_type, data in summary.by_task_type.items():
            output["by_task_type"][task_type] = {
                "calls": data["calls"],
                "cost": f"${data['cost']:.4f}",
                "percentage": f"{(data['cost'] / max(summary.total_cost, 1)) * 100:.1f}%",
            }

        return json.dumps(output, indent=2, ensure_ascii=False)

    def _format_suggestions(self, summary, tracker) -> str:
        """Format optimization suggestions"""
        suggestions = tracker.get_optimization_suggestions()

        output = {
            "status": "success",
            "level": "suggestions",
            "current_cost": f"${summary.total_cost:.4f}",
            "suggestions_count": len(suggestions),
            "suggestions": suggestions,
            "quick_wins": self._get_quick_wins(summary),
        }

        return json.dumps(output, indent=2, ensure_ascii=False)

    def _get_top_model(self, summary) -> str:
        """Get most used model by cost"""
        if not summary.by_model:
            return "N/A"

        top_model = max(summary.by_model.items(), key=lambda x: x[1]["cost"])
        return f"{top_model[0]} (${top_model[1]['cost']:.4f})"

    def _get_quick_wins(self, summary) -> list:
        """Get quick optimization wins"""
        wins = []

        # Check for high-cost model usage
        for model, data in summary.by_model.items():
            if data["cost"] > summary.total_cost * 0.3:
                wins.append(
                    {
                        "type": "model_substitution",
                        "description": f"Consider using cheaper alternatives for {model}",
                        "potential_savings": f"~${data['cost'] * 0.7:.4f}",
                    },
                )

        # Check for high output/input ratio (might need optimization)
        if summary.total_output_tokens > summary.total_input_tokens * 2:
            wins.append(
                {
                    "type": "output_optimization",
                    "description": "High output/token ratio - consider using max_tokens parameter",
                    "potential_savings": "20-30%",
                },
            )

        return wins
