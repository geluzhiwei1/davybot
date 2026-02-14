# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Plan Mode 工作流状态机

管理 Plan mode 的 5 阶段工作流
"""

import logging
from datetime import UTC, datetime, timezone
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class PlanPhase(Enum):
    """Plan 阶段枚举"""

    UNDERSTANDING = "understanding"  # Phase 1: 理解
    DESIGN = "design"  # Phase 2: 设计
    REVIEW = "review"  # Phase 3: 审查
    FINAL_PLAN = "final_plan"  # Phase 4: 最终计划
    EXIT = "exit"  # Phase 5: 退出

    @classmethod
    def get_phase_order(cls) -> list["PlanPhase"]:
        """获取阶段顺序"""
        return [cls.UNDERSTANDING, cls.DESIGN, cls.REVIEW, cls.FINAL_PLAN, cls.EXIT]

    def get_phase_number(self) -> int:
        """获取阶段编号（1-5）"""
        return self.get_phase_order().index(self) + 1

    def get_next_phase(self) -> Optional["PlanPhase"]:
        """获取下一个阶段"""
        order = self.get_phase_order()
        current_index = order.index(self)
        if current_index < len(order) - 1:
            return order[current_index + 1]
        return None


class PlanWorkflowState:
    """Plan 工作流状态"""

    def __init__(self, session_id: str):
        """初始化工作流状态

        Args:
            session_id: 会话 ID

        """
        self.session_id = session_id
        self.current_phase = PlanPhase.UNDERSTANDING
        self.explore_agents_launched = 0
        self.plan_agents_launched = 0
        self.questions_asked = 0
        self.plan_file_created = False
        self.plan_exit_called = False
        self.created_at = datetime.now(UTC)

        # Phase-specific data
        self.phase_data: dict[str, Any] = {
            "understanding": {
                "explore_results": [],
                "user_requirements": None,
                "ambiguities_resolved": [],
            },
            "design": {"approaches": [], "selected_approach": None, "tradeoffs": []},
            "review": {
                "critical_files": [],
                "verification_points": [],
                "user_confirmations": [],
            },
            "final_plan": {"plan_path": None, "plan_content": None},
        }

    def can_advance_to_phase(self, target_phase: PlanPhase) -> bool:
        """检查是否可以进入目标阶段

        Args:
            target_phase: 目标阶段

        Returns:
            是否可以进入

        """
        return target_phase.get_phase_number() >= self.current_phase.get_phase_number()

    def advance_to_phase(self, target_phase: PlanPhase) -> bool:
        """推进到目标阶段

        Args:
            target_phase: 目标阶段

        Returns:
            是否成功推进

        """
        if not self.can_advance_to_phase(target_phase):
            logger.warning(
                f"Cannot advance from {self.current_phase.value} to {target_phase.value}",
            )
            return False

        old_phase = self.current_phase
        self.current_phase = target_phase
        logger.info(
            f"Plan workflow advanced from {old_phase.value} to {target_phase.value} (Phase {target_phase.get_phase_number()}/5)",
        )
        return True

    def record_explore_agent(self, result: dict[str, Any]):
        """记录 explore agent 结果

        Args:
            result: Explore agent 结果

        """
        self.phase_data["understanding"]["explore_results"].append(result)
        self.explore_agents_launched += 1
        logger.debug(f"Recorded explore agent result. Total: {self.explore_agents_launched}")

    def record_plan_agent(self, approach: dict[str, Any]):
        """记录 plan agent 设计方案

        Args:
            approach: 设计方案

        """
        self.phase_data["design"]["approaches"].append(approach)
        self.plan_agents_launched += 1
        logger.debug(f"Recorded plan agent result. Total: {self.plan_agents_launched}")

    def select_approach(self, approach: dict[str, Any]):
        """选择最终方案

        Args:
            approach: 选定的方案

        """
        self.phase_data["design"]["selected_approach"] = approach
        logger.info("Selected final approach for implementation")

    def add_critical_file(self, file_path: str, description: str = ""):
        """添加关键文件列表

        Args:
            file_path: 文件路径
            description: 描述

        """
        self.phase_data["review"]["critical_files"].append(
            {
                "path": file_path,
                "description": description,
                "added_at": datetime.now(UTC).isoformat(),
            },
        )
        logger.debug(f"Added critical file: {file_path}")

    def add_verification_point(self, point: str):
        """添加验证点

        Args:
            point: 验证点描述

        """
        self.phase_data["review"]["verification_points"].append(point)
        logger.debug(f"Added verification point: {point}")

    def set_plan_file(self, plan_path: str, content: str = ""):
        """设置计划文件路径

        Args:
            plan_path: 计划文件路径
            content: 计划内容

        """
        self.phase_data["final_plan"]["plan_path"] = plan_path
        self.phase_data["final_plan"]["plan_content"] = content
        self.plan_file_created = True
        logger.info(f"Plan file set: {plan_path}")

    def mark_plan_exit_called(self):
        """标记 plan_exit 已调用"""
        self.plan_exit_called = True
        logger.info("Plan exit called, workflow complete")

    def is_complete(self) -> bool:
        """检查工作流是否完成

        Returns:
            是否完成

        """
        return self.current_phase == PlanPhase.EXIT and self.plan_file_created and self.plan_exit_called

    def get_progress_percentage(self) -> int:
        """获取工作流进度百分比

        Returns:
            进度百分比 (0-100)

        """
        phase_number = self.current_phase.get_phase_number()
        # 每个阶段占 20%
        return phase_number * 20

    def get_phase_summary(self) -> dict[str, Any]:
        """获取阶段摘要

        Returns:
            阶段摘要信息

        """
        return {
            "current_phase": self.current_phase.value,
            "phase_number": self.current_phase.get_phase_number(),
            "total_phases": 5,
            "progress_percentage": self.get_progress_percentage(),
            "explore_agents_launched": self.explore_agents_launched,
            "plan_agents_launched": self.plan_agents_launched,
            "questions_asked": self.questions_asked,
            "plan_file_created": self.plan_file_created,
            "is_complete": self.is_complete(),
            "created_at": self.created_at.isoformat(),
            "elapsed_seconds": (datetime.now(UTC) - self.created_at).total_seconds(),
        }


class PlanWorkflowExecutor:
    """Plan 工作流执行器"""

    def __init__(self, session_id: str, workspace_root: str):
        """初始化工作流执行器

        Args:
            session_id: 会话 ID
            workspace_root: 工作区根目录

        """
        self.session_id = session_id
        self.workspace_root = workspace_root
        self.state = PlanWorkflowState(session_id)

        # 初始化 PlanFileManager（延迟导入）
        try:
            from dawei.workspace.plan_file_manager import PlanFileManager

            self.plan_manager = PlanFileManager(workspace_root)
        except ImportError as e:
            logger.warning(f"PlanFileManager not available, file operations will be limited: {e}")
            self.plan_manager = None
        except Exception:
            logger.exception("Failed to initialize PlanFileManager: ")
            self.plan_manager = None

    def get_current_phase(self) -> PlanPhase:
        """获取当前阶段

        Returns:
            当前阶段

        """
        return self.state.current_phase

    def advance_to_phase(self, phase_name: str) -> bool:
        """推进到指定阶段

        Args:
            phase_name: 阶段名称

        Returns:
            是否成功推进

        """
        try:
            target_phase = PlanPhase(phase_name)
            return self.state.advance_to_phase(target_phase)
        except ValueError:
            logger.exception(f"Invalid phase name: {phase_name}")
            return False

    def get_system_reminder(self) -> str:
        """获取系统提醒（包含当前阶段的工作流）

        Returns:
            系统提醒文本

        """
        phase_name = self.state.current_phase.value
        phase_number = self.state.current_phase.get_phase_number()
        progress = self.state.get_progress_percentage()

        # 获取计划文件信息
        plan_info = self._get_plan_file_info()

        return f"""**Current Phase**: Phase {phase_number}/5 - {phase_name.upper()}
**Progress**: {progress}%
{plan_info}"""

    def _get_plan_file_info(self) -> str:
        """获取计划文件信息

        Returns:
            计划文件信息文本

        """
        if self.plan_manager is None:
            return "**Plan File**: Not available (PlanFileManager not initialized)"

        try:
            if self.plan_manager.plan_file_exists(self.session_id):
                metadata = self.plan_manager.get_plan_metadata(self.session_id)
                if metadata:
                    return f"""**Plan File**: `{metadata["path"]}`
**Modified**: {metadata["modified"]}"""
                return "**Plan File**: Created (details unavailable)"
            plan_path = self.plan_manager.get_plan_path(self.session_id)
            relative_path = plan_path.relative_to(self.workspace_root)
            return f"""**Plan File**: Not created yet
**Target Path**: `{relative_path}`"""
        except Exception as e:
            logger.exception("Failed to get plan file info: ")
            return f"**Plan File**: Error loading information ({type(e).__name__})"

    def get_template_context(self) -> dict[str, Any]:
        """获取模板渲染上下文

        Returns:
            模板上下文字典

        """
        return {
            "session_id": self.session_id,
            "current_phase": self.state.current_phase.value,
            "current_phase_name": self.state.current_phase.value.upper(),
            "phase_number": self.state.current_phase.get_phase_number(),
            "explore_agents_launched": self.state.explore_agents_launched,
            "plan_agents_launched": self.state.plan_agents_launched,
            "questions_asked": self.state.questions_asked,
            "phase_progress": self.state.get_progress_percentage(),
            "plan_file_exists": (self.plan_manager.plan_file_exists(self.session_id) if self.plan_manager else False),
            "plan_file_path": self._get_plan_file_path_display(),
            "state_summary": self.state.get_phase_summary(),
        }

    def _get_plan_file_path_display(self) -> str:
        """获取用于显示的计划文件路径

        Returns:
            相对路径字符串

        """
        if self.plan_manager is None:
            return ".dawei/plans/{timestamp}-{session_id}.md"

        plan_path = self.plan_manager.get_plan_path(self.session_id)
        try:
            return str(plan_path.relative_to(self.workspace_root))
        except ValueError:
            return str(plan_path)

    def record_activity(self, activity_type: str, data: dict[str, Any] | None = None):
        """记录活动

        Args:
            activity_type: 活动类型
            data: 活动数据

        """
        if activity_type == "explore_agent":
            self.state.record_explore_agent(data or {})
        elif activity_type == "plan_agent":
            self.state.record_plan_agent(data or {})
        elif activity_type == "question":
            self.state.questions_asked += 1
        elif activity_type == "plan_file_created":
            plan_path = data.get("plan_path") if data else None
            content = data.get("content") if data else ""
            if plan_path:
                self.state.set_plan_file(plan_path, content)

    def get_workflow_summary(self) -> dict[str, Any]:
        """获取工作流摘要

        Returns:
            工作流摘要信息

        """
        return self.state.get_phase_summary()
