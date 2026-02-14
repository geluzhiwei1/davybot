# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Agent PDCA 集成模块

为现有 Agent 类添加 PDCA 循环支持，使其成为通用智能 agent。

这个模块通过扩展方式集成，不修改现有 Agent 核心逻辑。
"""

import logging
from typing import Any

from dawei.agentic.domain_adapter import DomainType, get_domain_adapter
from dawei.agentic.pdca_context import PDCACycleContext, PDCAPhase
from dawei.agentic.pdca_cycle_manager import get_pdca_cycle_manager

logger = logging.getLogger(__name__)


class AgentPDCAExtension:
    """Agent PDCA 扩展类

    为现有 Agent 添加 PDCA 循环能力
    """

    def __init__(self, agent_instance):
        """初始化 PDCA 扩展

        Args:
            agent_instance: Agent 实例

        """
        self.agent = agent_instance
        self.pdca_manager = get_pdca_cycle_manager()
        self.domain_adapter = get_domain_adapter()
        self.current_cycle: PDCACycleContext | None = None
        self._pdca_enabled = True  # PDCA 功能开关

    @property
    def pdca_enabled(self) -> bool:
        """检查 PDCA 是否启用"""
        return self._pdca_enabled

    def enable_pdca(self):
        """启用 PDCA 功能"""
        self._pdca_enabled = True
        logger.info("PDCA functionality enabled")

    def disable_pdca(self):
        """禁用 PDCA 功能（用于简单任务）"""
        self._pdca_enabled = False
        logger.info("PDCA functionality disabled")

    def detect_task_domain(self, task_description: str) -> DomainType:
        """检测任务领域

        Args:
            task_description: 任务描述

        Returns:
            检测到的领域类型

        """
        domain = self.domain_adapter.detect_domain(task_description)
        logger.info(f"Detected domain: {domain.value} for task: {task_description[:50]}...")
        return domain

    async def start_pdca_cycle(
        self,
        session_id: str,
        task_description: str,
        task_goals: list[str] | None = None,
        success_criteria: list[str] | None = None,
    ) -> PDCACycleContext:
        """启动 PDCA 循环

        Args:
            session_id: 会话 ID
            task_description: 任务描述
            task_goals: 任务目标列表
            success_criteria: 成功标准列表

        Returns:
            PDCA 循环上下文

        """
        # 检测领域
        domain = self.detect_task_domain(task_description)

        # 启动循环
        self.current_cycle = await self.pdca_manager.start_cycle(
            session_id=session_id,
            task_description=task_description,
            domain=domain,
            task_goals=task_goals,
            success_criteria=success_criteria,
        )

        logger.info(f"Started PDCA cycle {self.current_cycle.cycle_id} for domain {domain.value}")

        return self.current_cycle

    async def advance_pdca_phase(
        self,
        phase_data: dict[str, Any],
        next_phase: PDCAPhase | None = None,
    ) -> dict[str, Any]:
        """推进到下一个 PDCA 阶段

        Args:
            phase_data: 当前阶段的数据
            next_phase: 下一阶段（如果为 None，则自动决定）

        Returns:
            转换结果

        """
        if not self.current_cycle:
            return {"status": "error", "message": "No active PDCA cycle"}

        result = await self.pdca_manager.advance_phase(
            cycle_id=self.current_cycle.cycle_id,
            phase_data=phase_data,
            next_phase=next_phase,
        )

        # 如果循环完成，清理状态
        if result.get("status") == "success" and result.get("completion_percentage") == 100:
            final_report = await self.pdca_manager.complete_cycle(
                cycle_id=self.current_cycle.cycle_id,
                final_results=phase_data,
            )
            logger.info(f"PDCA cycle completed: {final_report}")

        return result

    def get_pdca_guidance(self) -> dict[str, Any] | None:
        """获取当前阶段的 PDCA 指导

        Returns:
            领域和阶段的指导信息

        """
        if not self.current_cycle:
            return None

        return self.pdca_manager.get_domain_guidance(cycle_id=self.current_cycle.cycle_id)

    def get_pdca_status(self) -> dict[str, Any] | None:
        """获取 PDCA 循环状态

        Returns:
            循环状态信息

        """
        if not self.current_cycle:
            return {"active": False, "message": "No active PDCA cycle"}

        status = self.pdca_manager.get_cycle_status(cycle_id=self.current_cycle.cycle_id)

        if status:
            status["active"] = True

        return status

    def should_use_pdca(self, task_description: str) -> bool:
        """判断任务是否应该使用 PDCA 循环

        Args:
            task_description: 任务描述

        Returns:
            是否应该使用 PDCA

        """
        # 简单判断规则
        task_lower = task_description.lower()

        # 简单任务指示词（不使用 PDCA）
        simple_indicators = [
            "解释",
            "说明",
            "是什么",
            "如何",
            "how to",
            "explain",
            "what is",
        ]

        # 复杂任务指示词（使用 PDCA）
        complex_indicators = [
            "实现",
            "开发",
            "分析",
            "设计",
            "优化",
            "重构",
            "implement",
            "develop",
            "analyze",
            "design",
            "optimize",
        ]

        # 检查是否是简单任务
        for indicator in simple_indicators:
            if indicator in task_lower:
                # 如果只是简单的问题，不需要 PDCA
                # 但要确保这不是一个大任务的描述
                if len(task_description.split()) < 20:  # 简短描述
                    return False

        # 检查是否是复杂任务
        for indicator in complex_indicators:
            if indicator in task_lower:
                return True

        # 默认：根据任务描述长度决定
        # 短任务（< 50 字符）可能不需要完整 PDCA
        # 长任务（> 100 字符）可能需要 PDCA
        return len(task_description) > 50

    def get_current_mode_name(self) -> str:
        """获取当前应该使用的 mode 名称

        根据 PDCA 状态返回应该使用的 mode

        Returns:
            Mode 名称 (orchestrator/plan/do/check/act)

        """
        if not self.pdca_enabled or not self.current_cycle:
            # PDCA 未启用或没有活跃循环，使用 orchestrator
            return "orchestrator"

        current_phase = self.current_cycle.current_phase
        return current_phase.value

    def save_pdca_checkpoint(self) -> dict[str, Any] | None:
        """保存 PDCA 检查点"""
        if not self.current_cycle:
            return None

        return self.pdca_manager.context_manager.save_checkpoint(
            cycle_id=self.current_cycle.cycle_id,
        )

    def restore_pdca_checkpoint(
        self,
        checkpoint_data: dict[str, Any],
    ) -> PDCACycleContext | None:
        """从检查点恢复 PDCA 状态"""
        cycle = self.pdca_manager.context_manager.restore_from_checkpoint(
            checkpoint_data=checkpoint_data,
        )

        if cycle:
            self.current_cycle = cycle
            logger.info(f"Restored PDCA cycle: {cycle.cycle_id}")

        return cycle


def add_pdca_to_agent(agent_instance) -> AgentPDCAExtension:
    """为现有 Agent 实例添加 PDCA 功能

    Args:
        agent_instance: Agent 实例

    Returns:
        PDCA 扩展实例

    Example:
        ```python
        # 为现有 Agent 添加 PDCA 支持
        pdca_extension = add_pdca_to_agent(agent)

        # 启动 PDCA 循环
        cycle = pdca_extension.start_pdca_cycle(
            session_id="session_123",
            task_description="开发用户认证功能",
            task_goals=["实现登录", "实现注册"],
            success_criteria=["测试通过", "无安全漏洞"]
        )

        # 获取当前阶段指导
        guidance = pdca_extension.get_pdca_guidance()
        ```

    """
    # 创建扩展实例
    pdca_extension = AgentPDCAExtension(agent_instance)

    # 将扩展附加到 agent 实例
    agent_instance._pdca_extension = pdca_extension

    logger.info(f"Added PDCA extension to Agent: {agent_instance}")
    return pdca_extension


# 便捷函数
def get_agent_pdca(agent_instance) -> AgentPDCAExtension | None:
    """获取 Agent 的 PDCA 扩展"""
    return getattr(agent_instance, "_pdca_extension", None)


def is_agent_pdcapd(agent_instance) -> bool:
    """检查 Agent 是否支持 PDCA"""
    return hasattr(agent_instance, "_pdca_extension")
