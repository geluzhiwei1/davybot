# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""PDCA 上下文管理

管理 PDCA 各阶段之间的上下文传递和状态保持。
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from dawei.agentic.domain_adapter import DomainType


class PDCAPhase(Enum):
    """PDCA 阶段枚举"""

    PLAN = "plan"
    DO = "do"
    CHECK = "check"
    ACT = "act"


@dataclass
class PhaseContext:
    """阶段上下文 - 每个阶段的上下文信息"""

    phase: PDCAPhase
    start_time: datetime
    end_time: datetime | None = None
    status: str = "in_progress"  # in_progress, completed, failed

    # 阶段特定的数据
    plan_data: dict[str, Any] = field(default_factory=dict)
    do_data: dict[str, Any] = field(default_factory=dict)
    check_data: dict[str, Any] = field(default_factory=dict)
    act_data: dict[str, Any] = field(default_factory=dict)

    # 通用数据
    metadata: dict[str, Any] = field(default_factory=dict)
    artifacts: list[str] = field(default_factory=list)  # 产出物列表
    issues: list[dict[str, Any]] = field(default_factory=list)  # 问题列表

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "phase": self.phase.value,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "status": self.status,
            "plan_data": self.plan_data,
            "do_data": self.do_data,
            "check_data": self.check_data,
            "act_data": self.act_data,
            "metadata": self.metadata,
            "artifacts": self.artifacts,
            "issues": self.issues,
        }


@dataclass
class PDCACycleContext:
    """PDCA 循环上下文 - 完整的 PDCA 循环状态"""

    # 基本信息
    session_id: str
    cycle_id: str
    domain: DomainType
    start_time: datetime

    # 阶段管理
    current_phase: PDCAPhase = PDCAPhase.PLAN
    phase_history: list[PDCAPhase] = field(default_factory=list)
    phase_contexts: dict[PDCAPhase, PhaseContext] = field(default_factory=dict)

    # 任务信息
    task_description: str = ""
    task_goals: list[str] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=list)

    # 循环计数
    cycle_count: int = 0  # 当前是第几轮循环
    max_cycles: int = 10  # 最大循环次数

    # 状态管理
    status: str = "active"  # active, completed, failed, cancelled
    completion_percentage: float = 0.0

    # 元数据
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """初始化后处理"""
        # 初始化 Plan 阶段上下文
        if PDCAPhase.PLAN not in self.phase_contexts:
            self.phase_contexts[PDCAPhase.PLAN] = PhaseContext(
                phase=PDCAPhase.PLAN,
                start_time=self.start_time,
            )

    def advance_to_phase(self, next_phase: PDCAPhase, current_data: dict[str, Any]) -> PhaseContext:
        """推进到下一阶段

        Args:
            next_phase: 下一阶段
            current_data: 当前阶段的数据

        Returns:
            新阶段的上下文

        """
        # 结束当前阶段
        current_context = self.phase_contexts[self.current_phase]
        current_context.end_time = datetime.now(timezone.utc)
        current_context.status = "completed"

        # 保存当前阶段数据
        if self.current_phase == PDCAPhase.PLAN:
            current_context.plan_data.update(current_data)
        elif self.current_phase == PDCAPhase.DO:
            current_context.do_data.update(current_data)
        elif self.current_phase == PDCAPhase.CHECK:
            current_context.check_data.update(current_data)
        elif self.current_phase == PDCAPhase.ACT:
            current_context.act_data.update(current_data)

        # 记录历史
        self.phase_history.append(self.current_phase)

        # 如果完成一轮循环
        if self.current_phase == PDCAPhase.ACT and next_phase == PDCAPhase.PLAN:
            self.cycle_count += 1

        # 创建新阶段上下文
        new_context = PhaseContext(phase=next_phase, start_time=datetime.now(timezone.utc))
        self.phase_contexts[next_phase] = new_context
        self.current_phase = next_phase

        return new_context

    def get_current_phase_context(self) -> PhaseContext:
        """获取当前阶段上下文"""
        return self.phase_contexts.get(self.current_phase)

    def get_phase_context(self, phase: PDCAPhase) -> PhaseContext | None:
        """获取指定阶段的上下文"""
        return self.phase_contexts.get(phase)

    def is_complete(self) -> bool:
        """检查循环是否完成"""
        return self.status == "completed"

    def should_continue_cycle(self) -> bool:
        """判断是否应该继续循环"""
        if self.cycle_count >= self.max_cycles:
            return False

        # 检查是否还有显著改进空间
        act_context = self.get_phase_context(PDCAPhase.ACT)
        return not (act_context and not act_context.metadata.get("next_cycle"))

    def get_summary(self) -> dict[str, Any]:
        """获取循环摘要"""
        return {
            "session_id": self.session_id,
            "cycle_id": self.cycle_id,
            "domain": self.domain.value,
            "current_phase": self.current_phase.value,
            "cycle_count": self.cycle_count,
            "phase_history": [p.value for p in self.phase_history],
            "status": self.status,
            "completion_percentage": self.completion_percentage,
            "task_description": self.task_description,
            "task_goals": self.task_goals,
            "artifacts": self._collect_all_artifacts(),
            "issues": self._collect_all_issues(),
        }

    def _collect_all_artifacts(self) -> list[str]:
        """收集所有产出物"""
        artifacts = []
        for context in self.phase_contexts.values():
            artifacts.extend(context.artifacts)
        return list(set(artifacts))  # 去重

    def _collect_all_issues(self) -> list[dict[str, Any]]:
        """收集所有问题"""
        issues = []
        for context in self.phase_contexts.values():
            issues.extend(context.issues)
        return issues

    def calculate_completion(self) -> float:
        """计算完成度"""
        # 简单实现：根据阶段完成度计算
        phase_weights = {
            PDCAPhase.PLAN: 0.25,
            PDCAPhase.DO: 0.35,
            PDCAPhase.CHECK: 0.25,
            PDCAPhase.ACT: 0.15,
        }

        completion = 0.0
        for phase, context in self.phase_contexts.items():
            if context.status == "completed":
                completion += phase_weights.get(phase, 0) * 1.0
            elif context.status == "in_progress":
                # 进行中按 50% 计算
                completion += phase_weights.get(phase, 0) * 0.5

        self.completion_percentage = min(completion * 100, 100)
        return self.completion_percentage


class PDCAContextManager:
    """PDCA 上下文管理器"""

    def __init__(self):
        self._cycles: dict[str, PDCACycleContext] = {}

    def create_cycle(
        self,
        session_id: str,
        task_description: str,
        domain: DomainType,
        task_goals: list[str] | None = None,
        success_criteria: list[str] | None = None,
    ) -> PDCACycleContext:
        """创建新的 PDCA 循环

        Args:
            session_id: 会话 ID
            task_description: 任务描述
            domain: 任务领域
            task_goals: 任务目标列表
            success_criteria: 成功标准列表

        Returns:
            PDCA 循环上下文

        """
        import uuid

        cycle_id = f"cycle_{uuid.uuid4().hex[:8]}"
        cycle = PDCACycleContext(
            session_id=session_id,
            cycle_id=cycle_id,
            domain=domain,
            start_time=datetime.now(timezone.utc),
            task_description=task_description,
            task_goals=task_goals or [],
            success_criteria=success_criteria or [],
        )

        self._cycles[cycle_id] = cycle
        return cycle

    def get_cycle(self, cycle_id: str) -> PDCACycleContext | None:
        """获取循环上下文"""
        return self._cycles.get(cycle_id)

    def get_latest_cycle(self, session_id: str) -> PDCACycleContext | None:
        """获取指定会话的最新循环"""
        session_cycles = [cycle for cycle in self._cycles.values() if cycle.session_id == session_id]
        if session_cycles:
            return max(session_cycles, key=lambda c: c.start_time)
        return None

    def save_checkpoint(self, cycle_id: str) -> dict[str, Any]:
        """保存检查点

        Args:
            cycle_id: 循环 ID

        Returns:
            检查点数据

        """
        cycle = self.get_cycle(cycle_id)
        if not cycle:
            return {}

        return {
            "cycle_id": cycle_id,
            "summary": cycle.get_summary(),
            "phases": {phase.value: context.to_dict() for phase, context in cycle.phase_contexts.items()},
        }

    def restore_from_checkpoint(
        self,
        checkpoint_data: dict[str, Any],
    ) -> PDCACycleContext | None:
        """从检查点恢复

        Args:
            checkpoint_data: 检查点数据

        Returns:
            恢复的循环上下文

        """
        summary = checkpoint_data.get("summary", {})
        phases_data = checkpoint_data.get("phases", {})

        # 重建循环上下文
        cycle = PDCACycleContext(
            session_id=summary["session_id"],
            cycle_id=summary["cycle_id"],
            domain=DomainType(summary["domain"]),
            start_time=datetime.fromisoformat(
                summary.get("start_time", datetime.now(timezone.utc).isoformat()),
            ),
            task_description=summary.get("task_description", ""),
            task_goals=summary.get("task_goals", []),
            success_criteria=summary.get("success_criteria", []),
            cycle_count=summary.get("cycle_count", 0),
            status=summary.get("status", "active"),
            completion_percentage=summary.get("completion_percentage", 0.0),
        )

        # 恢复阶段上下文
        for phase_str, phase_data in phases_data.items():
            phase = PDCAPhase(phase_str)
            phase_context = PhaseContext(
                phase=phase,
                start_time=datetime.fromisoformat(phase_data["start_time"]),
                end_time=(datetime.fromisoformat(phase_data["end_time"]) if phase_data.get("end_time") else None),
                status=phase_data.get("status", "in_progress"),
                plan_data=phase_data.get("plan_data", {}),
                do_data=phase_data.get("do_data", {}),
                check_data=phase_data.get("check_data", {}),
                act_data=phase_data.get("act_data", {}),
                metadata=phase_data.get("metadata", {}),
                artifacts=phase_data.get("artifacts", []),
                issues=phase_data.get("issues", []),
            )
            cycle.phase_contexts[phase] = phase_context

        # 恢复当前阶段
        if summary.get("current_phase"):
            cycle.current_phase = PDCAPhase(summary["current_phase"])

        # 恢复历史
        if summary.get("phase_history"):
            cycle.phase_history = [PDCAPhase(p) for p in summary["phase_history"]]

        self._cycles[cycle.cycle_id] = cycle
        return cycle


# 单例实例
_context_manager_instance = None


def get_pdca_context_manager() -> PDCAContextManager:
    """获取 PDCA 上下文管理器单例"""
    global _context_manager_instance
    if _context_manager_instance is None:
        _context_manager_instance = PDCAContextManager()
    return _context_manager_instance
