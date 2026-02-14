# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""PDCA 循环管理器

管理 Plan-Do-Check-Act 循环的状态流转和自动化决策。
"""

import logging
from typing import Any

from dawei.agentic.domain_adapter import DomainType, get_domain_adapter
from dawei.agentic.pdca_context import (
    PDCACycleContext,
    PDCAPhase,
    get_pdca_context_manager,
)
from dawei.core.events import CORE_EVENT_BUS, TaskEventType

logger = logging.getLogger(__name__)


class PDCACycleManager:
    """PDCA 循环管理器

    负责管理 PDCA 循环的状态流转和自动化决策
    """

    def __init__(self):
        self.context_manager = get_pdca_context_manager()
        self.domain_adapter = get_domain_adapter()

    async def start_cycle(
        self,
        session_id: str,
        task_description: str,
        task_goals: list[str] | None = None,
        success_criteria: list[str] | None = None,
        domain: DomainType | None = None,
    ) -> PDCACycleContext:
        """启动新的 PDCA 循环

        Args:
            session_id: 会话 ID
            task_description: 任务描述
            task_goals: 任务目标列表
            success_criteria: 成功标准列表
            domain: 任务领域（如果为 None，则自动检测）

        Returns:
            PDCA 循环上下文

        """
        # 自动检测领域
        if domain is None:
            domain = self.domain_adapter.detect_domain(task_description)
            logger.info(f"Auto-detected domain: {domain.value}")

            # Emit PDCA domain detected event
            await CORE_EVENT_BUS.publish(
                TaskEventType.PDCA_DOMAIN_DETECTED,
                {
                    "domain": domain.value,
                    "task_description": task_description,
                },
                task_id=session_id,
                source="pdca_manager",
            )

        # 创建循环
        cycle = self.context_manager.create_cycle(
            session_id=session_id,
            task_description=task_description,
            domain=domain,
            task_goals=task_goals,
            success_criteria=success_criteria,
        )

        logger.info(f"Started PDCA cycle: {cycle.cycle_id} for domain: {domain.value}")

        # Emit PDCA cycle started event
        await CORE_EVENT_BUS.publish(
            TaskEventType.PDCA_CYCLE_STARTED,
            {
                "cycle_id": cycle.cycle_id,
                "session_id": session_id,
                "domain": domain.value,
                "task_description": task_description,
                "task_goals": task_goals,
                "success_criteria": success_criteria,
            },
            task_id=cycle.cycle_id,
            source="pdca_manager",
        )

        return cycle

    async def advance_phase(
        self,
        cycle_id: str,
        phase_data: dict[str, Any],
        next_phase: PDCAPhase | None = None,
    ) -> dict[str, Any]:
        """推进到下一阶段

        Args:
            cycle_id: 循环 ID
            phase_data: 当前阶段的数据
            next_phase: 下一阶段（如果为 None，则自动决定）

        Returns:
            转换结果和建议

        """
        cycle = self.context_manager.get_cycle(cycle_id)
        if not cycle:
            return {"status": "error", "message": f"Cycle {cycle_id} not found"}

        current_phase = cycle.current_phase

        # 自动决定下一阶段
        if next_phase is None:
            next_phase = self._determine_next_phase(cycle, phase_data)

        # 验证阶段转换是否合法
        if not self._is_valid_transition(current_phase, next_phase):
            return {
                "status": "error",
                "message": f"Invalid transition from {current_phase.value} to {next_phase.value}",
            }

        # 推进阶段
        try:
            cycle.advance_to_phase(next_phase, phase_data)

            # 更新完成度
            cycle.calculate_completion()

            # 获取下一阶段的建议
            suggestion = self._get_phase_suggestion(cycle, next_phase)

            result = {
                "status": "success",
                "previous_phase": current_phase.value,
                "current_phase": next_phase.value,
                "cycle_count": cycle.cycle_count,
                "suggestion": suggestion,
                "completion_percentage": cycle.completion_percentage,
            }

            logger.info(
                f"Advanced {cycle_id}: {current_phase.value} -> {next_phase.value}, cycle: {cycle.cycle_count}, completion: {cycle.completion_percentage:.1f}%",
            )

            # Emit PDCA phase advanced event
            await CORE_EVENT_BUS.publish(
                TaskEventType.PDCA_PHASE_ADVANCED,
                {
                    "cycle_id": cycle_id,
                    "previous_phase": current_phase.value,
                    "current_phase": next_phase.value,
                    "cycle_count": cycle.cycle_count,
                    "completion_percentage": cycle.completion_percentage,
                    "suggestion": suggestion,
                },
                task_id=cycle_id,
                source="pdca_manager",
            )

            return result

        except Exception as e:
            logger.exception("Failed to advance phase: ")
            return {"status": "error", "message": f"Failed to advance phase: {e!s}"}

    def _determine_next_phase(
        self,
        cycle: PDCACycleContext,
        phase_data: dict[str, Any],
    ) -> PDCAPhase:
        """根据当前阶段结果决定下一阶段

        Args:
            cycle: 循环上下文
            phase_data: 当前阶段的数据

        Returns:
            下一阶段

        """
        current_phase = cycle.current_phase

        if current_phase == PDCAPhase.PLAN:
            # Plan 完成后，总是进入 Do
            return PDCAPhase.DO

        if current_phase == PDCAPhase.DO:
            # Do 完成后，总是进入 Check
            return PDCAPhase.CHECK

        if current_phase == PDCAPhase.CHECK:
            # Check 完成后，根据结果决定
            check_status = phase_data.get("overall_status", "")
            if check_status == "pass":
                return PDCAPhase.ACT
            if check_status == "partial":
                # 部分通过，询问用户或进入 Act（记录问题）
                # 这里默认进入 Act，可以记录问题
                return PDCAPhase.ACT
            # fail
            # 重大问题，返回 Plan
            return PDCAPhase.PLAN

        if current_phase == PDCAPhase.ACT:
            # Act 完成后，根据决策结果
            outcome = phase_data.get("outcome", "")
            if outcome == "new_cycle" and cycle.should_continue_cycle():
                return PDCAPhase.PLAN
            # 完成循环
            cycle.status = "completed"
            cycle.completion_percentage = 100.0
            # 返回 ACT 表示循环结束
            return PDCAPhase.ACT

        return PDCAPhase.PLAN

    def _is_valid_transition(self, from_phase: PDCAPhase, to_phase: PDCAPhase) -> bool:
        """验证阶段转换是否合法"""
        valid_transitions = {
            PDCAPhase.PLAN: [PDCAPhase.DO],
            PDCAPhase.DO: [PDCAPhase.CHECK],
            PDCAPhase.CHECK: [PDCAPhase.ACT, PDCAPhase.PLAN],
            PDCAPhase.ACT: [
                PDCAPhase.PLAN,
                PDCAPhase.ACT,
            ],  # ACT can loop back to PLAN or stay (end)
        }
        return to_phase in valid_transitions.get(from_phase, [])

    def _get_phase_suggestion(self, cycle: PDCACycleContext, phase: PDCAPhase) -> str:
        """获取阶段建议"""
        self.domain_adapter.get_domain_context(cycle.domain)
        workflow = self.domain_adapter.get_workflow_for_phase(cycle.domain, phase.value)

        if workflow:
            return f"Follow workflow: {' -> '.join(workflow)}"

        suggestions = {
            PDCAPhase.PLAN: f"Create a detailed plan for {cycle.domain.value} task",
            PDCAPhase.DO: f"Execute the plan systematically for {cycle.domain.value}",
            PDCAPhase.CHECK: f"Verify results against {cycle.domain.value} standards",
            PDCAPhase.ACT: f"Standardize improvements for {cycle.domain.value}",
        }
        return suggestions.get(phase, "")

    def get_cycle_status(self, cycle_id: str) -> dict[str, Any] | None:
        """获取循环状态"""
        cycle = self.context_manager.get_cycle(cycle_id)
        if not cycle:
            return None

        return {
            "summary": cycle.get_summary(),
            "current_phase_context": cycle.get_current_phase_context().to_dict(),
            "domain_context": self.domain_adapter.get_domain_context(cycle.domain).to_dict(),
        }

    def should_continue_cycle(self, cycle_id: str) -> bool:
        """判断是否应该继续循环"""
        cycle = self.context_manager.get_cycle(cycle_id)
        if not cycle:
            return False

        return cycle.should_continue_cycle()

    async def complete_cycle(self, cycle_id: str, final_results: dict[str, Any]) -> dict[str, Any]:
        """完成 PDCA 循环

        Args:
            cycle_id: 循环 ID
            final_results: 最终结果

        Returns:
            完成报告

        """
        cycle = self.context_manager.get_cycle(cycle_id)
        if not cycle:
            return {"status": "error", "message": f"Cycle {cycle_id} not found"}

        # 标记为完成
        cycle.status = "completed"
        cycle.completion_percentage = 100.0

        # 获取最终摘要
        summary = cycle.get_summary()

        report = {
            "status": "completed",
            "cycle_id": cycle_id,
            "domain": cycle.domain.value,
            "cycle_count": cycle.cycle_count,
            "completion_percentage": 100.0,
            "summary": summary,
            "final_results": final_results,
            "artifacts": summary.get("artifacts", []),
            "issues": summary.get("issues", []),
        }

        logger.info(f"Completed PDCA cycle: {cycle_id}")

        # Emit PDCA cycle completed event
        await CORE_EVENT_BUS.publish(
            TaskEventType.PDCA_CYCLE_COMPLETED,
            report,
            task_id=cycle_id,
            source="pdca_manager",
        )

        return report

    def get_domain_guidance(
        self,
        cycle_id: str,
        phase: PDCAPhase | None = None,
    ) -> dict[str, Any]:
        """获取领域特定指导

        Args:
            cycle_id: 循环 ID
            phase: 阶段（如果为 None，使用当前阶段）

        Returns:
            领域指导信息

        """
        cycle = self.context_manager.get_cycle(cycle_id)
        if not cycle:
            return {}

        target_phase = phase or cycle.current_phase
        domain = cycle.domain

        domain_context = self.domain_adapter.get_domain_context(domain)
        workflow = self.domain_adapter.get_workflow_for_phase(domain, target_phase.value)

        return {
            "domain": domain.value,
            "phase": target_phase.value,
            "typical_outputs": domain_context.typical_outputs,
            "quality_criteria": domain_context.quality_criteria,
            "success_metrics": domain_context.success_metrics,
            "workflow": workflow,
            "common_tools": domain_context.common_tools,
        }


# 单例实例
_cycle_manager_instance = None


def get_pdca_cycle_manager() -> PDCACycleManager:
    """获取 PDCA 循环管理器单例"""
    global _cycle_manager_instance
    if _cycle_manager_instance is None:
        _cycle_manager_instance = PDCACycleManager()
    return _cycle_manager_instance
