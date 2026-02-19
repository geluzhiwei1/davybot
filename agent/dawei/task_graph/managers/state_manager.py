# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""状态管理器
新架构中专门负责任务状态管理的组件
"""

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone
from typing import Any, ClassVar

from dawei.core.errors import (
    StateTransitionError,
    TaskNotFoundError,
    TaskStateError,
    ValidationError,
)
from dawei.entity.task_types import TaskStatus
from dawei.logg.logging import get_logger
from dawei.task_graph.task_node_data import StateTransition, ValidationResult


# 使用延迟导入避免循环导入
def get_core_event_bus():
    """获取核心事件总线的延迟导入函数"""
    from dawei.core import CORE_EVENT_BUS

    return CORE_EVENT_BUS


def get_emit_typed_event():
    """获取 emit_typed_event 函数的延迟导入"""
    from dawei.core.events import emit_typed_event

    return emit_typed_event


def get_TaskEventType():
    """获取 TaskEventType 的延迟导入"""
    from dawei.core.events import TaskEventType

    return TaskEventType


@dataclass
class StatusUpdate:
    """状态更新操作"""

    task_id: str
    new_status: TaskStatus
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class StateValidator:
    """状态转换验证器"""

    # 定义允许的状态转换
    VALID_TRANSITIONS: ClassVar[dict[TaskStatus, set[TaskStatus]]] = {
        TaskStatus.PENDING: {TaskStatus.RUNNING, TaskStatus.ABORTED},
        TaskStatus.RUNNING: {
            TaskStatus.PAUSED,
            TaskStatus.COMPLETED,
            TaskStatus.ABORTED,
            TaskStatus.FAILED,
        },
        TaskStatus.PAUSED: {TaskStatus.RUNNING, TaskStatus.ABORTED},
        TaskStatus.COMPLETED: {
            # 完成状态通常是终态，不允许转换
        },
        TaskStatus.ABORTED: {
            # 中止状态通常是终态，但可以重启
            TaskStatus.PENDING,
            TaskStatus.RUNNING,
        },
    }

    def validate_transition(
        self,
        from_status: TaskStatus,
        to_status: TaskStatus,
    ) -> ValidationResult:
        """验证状态转换是否有效"""
        result = ValidationResult(is_valid=True)

        # 相同状态不需要转换
        if from_status == to_status:
            result.add_warning(f"No status change needed: {from_status.value}")
            return result

        # 检查是否为有效转换
        valid_targets = self.VALID_TRANSITIONS.get(from_status, set())
        if to_status not in valid_targets:
            result.add_error(
                f"Invalid status transition: {from_status.value} -> {to_status.value}. Valid targets: {[s.value for s in valid_targets]}",
            )

        return result

    def is_terminal_state(self, status: TaskStatus) -> bool:
        """判断是否为终态"""
        return status in {TaskStatus.COMPLETED, TaskStatus.ABORTED}

    def can_transition(self, from_status: TaskStatus, to_status: TaskStatus) -> bool:
        """检查是否可以转换"""
        if from_status == to_status:
            return True

        valid_targets = self.VALID_TRANSITIONS.get(from_status, set())
        return to_status in valid_targets


class StateManager:
    """状态管理器"""

    def __init__(self, event_bus=None):
        self._event_bus = event_bus
        self._states: dict[str, TaskStatus] = {}
        self._state_history: dict[str, list[StateTransition]] = {}
        self._lock = asyncio.Lock()
        self._validator = StateValidator()
        self.logger = get_logger(__name__)

    @property
    def event_bus(self):
        """获取 event_bus"""
        return self._event_bus

    @event_bus.setter
    def event_bus(self, value):
        """设置 event_bus"""
        self._event_bus = value

    async def update_status(
        self,
        task_id: str,
        new_status: TaskStatus,
        reason: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """更新任务状态"""
        try:
            async with self._lock:
                current_status = self._states.get(task_id, TaskStatus.PENDING)
                metadata = metadata or {}

                # 验证状态转换
                validation_result = self._validator.validate_transition(current_status, new_status)
                if not validation_result.is_valid:
                    self.logger.error(
                        f"Invalid status transition for task {task_id}: {validation_result.errors}",
                    )
                    return False

                # 记录状态转换
                transition = StateTransition(
                    from_status=current_status,
                    to_status=new_status,
                    timestamp=datetime.now(UTC),
                    reason=reason,
                    metadata=metadata,
                )

                # 更新状态
                self._states[task_id] = new_status

                # 记录历史
                if task_id not in self._state_history:
                    self._state_history[task_id] = []
                self._state_history[task_id].append(transition)

                # 发送事件
                emit_typed_event = get_emit_typed_event()
                taskeventtype = get_TaskEventType()
                # 使用 emit_typed_event 便利函数，传入事件类型枚举和数据
                await emit_typed_event(
                    taskeventtype.STATE_CHANGED,
                    {
                        "old_state": current_status.value,
                        "new_state": new_status.value,
                        "reason": reason,
                        "task_id": task_id,
                    },
                    self.event_bus,  # 🔧 修复：添加 event_bus 参数
                    task_id=task_id,
                    source="state_manager",
                )

                self.logger.info(
                    f"Updated status for task {task_id}: {current_status.value} -> {new_status.value}",
                )
                return True

        except (TaskStateError, TaskNotFoundError, KeyError):
            self.logger.exception("Failed to update status for task {task_id}: ")
            return False

    async def get_status(self, task_id: str) -> TaskStatus | None:
        """获取任务状态"""
        try:
            async with self._lock:
                return self._states.get(task_id)
        except (KeyError, TaskNotFoundError):
            self.logger.exception("Failed to get status for task {task_id}: ")
            return None

    async def get_state_history(self, task_id: str) -> list[StateTransition]:
        """获取状态转换历史"""
        try:
            async with self._lock:
                return self._state_history.get(task_id, []).copy()
        except (TaskStateError, StateTransitionError, ValidationError):
            self.logger.exception("Failed to get state history for task {task_id}: ")
            return []

    async def is_terminal_state(self, task_id: str) -> bool:
        """判断任务是否处于终态"""
        try:
            status = await self.get_status(task_id)
            if status is None:
                return False
            return self._validator.is_terminal_state(status)
        except (TaskStateError, StateTransitionError, ValidationError):
            self.logger.exception("Failed to check terminal state for task {task_id}: ")
            return False

    async def can_transition(self, task_id: str, new_status: TaskStatus) -> bool:
        """检查是否可以进行状态转换"""
        try:
            current_status = await self.get_status(task_id)
            if current_status is None:
                return new_status == TaskStatus.PENDING

            return self._validator.can_transition(current_status, new_status)
        except (TaskStateError, StateTransitionError, ValidationError):
            self.logger.exception("Failed to check transition for task {task_id}: ")
            return False

    async def batch_update_status(
        self,
        updates: list[StatusUpdate],
        _source: str = "system",
    ) -> bool:
        """批量更新状态"""
        try:
            async with self._lock:
                results = []

                for update in updates:
                    result = await self.update_status(
                        update.task_id,
                        update.new_status,
                        update.reason,
                        update.metadata,
                    )
                    results.append(result)

                # 发送批量更新事件 - 为每个更新发送单独的状态变更事件
                emit_typed_event = get_emit_typed_event()
                taskeventtype = get_TaskEventType()
                for update in updates:
                    await emit_typed_event(
                        taskeventtype.STATE_CHANGED,
                        {
                            "old_state": "",
                            "new_state": update.new_status.value,
                            "reason": update.reason,
                            "task_id": update.task_id,
                        },
                        self.event_bus,  # 🔧 修复：添加 event_bus 参数
                        task_id=update.task_id,
                        source="state_manager_batch",
                    )

                success_count = sum(results)
                self.logger.info(f"Batch updated status: {success_count}/{len(updates)} successful")
                return success_count == len(updates)

        except (TaskStateError, TaskNotFoundError, KeyError):
            self.logger.exception("Failed to batch update status: ")
            return False

    async def get_all_states(self) -> dict[str, TaskStatus]:
        """获取所有任务状态"""
        try:
            async with self._lock:
                return self._states.copy()
        except (TaskStateError, StateTransitionError, ValidationError):
            self.logger.exception("Failed to get all states: ")
            return {}

    async def get_state_statistics(self) -> dict[str, Any]:
        """获取状态统计信息"""
        try:
            all_states = await self.get_all_states()

            stats = {
                "total_tasks": len(all_states),
                "status_counts": {},
                "terminal_tasks": 0,
                "active_tasks": 0,
            }

            for status in TaskStatus:
                stats["status_counts"][status.value] = 0

            for _task_id, status in all_states.items():
                stats["status_counts"][status.value] += 1

                if self._validator.is_terminal_state(status):
                    stats["terminal_tasks"] += 1
                else:
                    stats["active_tasks"] += 1

            return stats

        except (TaskStateError, StateTransitionError, ValidationError):
            self.logger.exception("Failed to get state statistics: ")
            return {
                "total_tasks": 0,
                "status_counts": {},
                "terminal_tasks": 0,
                "active_tasks": 0,
            }

    async def reset_task_state(self, task_id: str, reason: str = "") -> bool:
        """重置任务状态"""
        try:
            async with self._lock:
                if task_id in self._states:
                    old_status = self._states[task_id]
                    self._states[task_id] = TaskStatus.PENDING

                    # 记录重置操作
                    transition = StateTransition(
                        from_status=old_status,
                        to_status=TaskStatus.PENDING,
                        timestamp=datetime.now(UTC),
                        reason=f"Reset: {reason}",
                        metadata={"reset": True},
                    )

                    if task_id not in self._state_history:
                        self._state_history[task_id] = []
                    self._state_history[task_id].append(transition)

                    # 发送事件
                    emit_typed_event = get_emit_typed_event()
                    taskeventtype = get_TaskEventType()
                    await emit_typed_event(
                        taskeventtype.STATE_CHANGED,
                        {
                            "old_state": old_status.value,
                            "new_state": TaskStatus.PENDING.value,
                            "reason": f"Reset: {reason}",
                            "task_id": task_id,
                        },
                        self.event_bus,  # 🔧 修复：添加 event_bus 参数
                        task_id=task_id,
                        source="state_manager",
                    )

                    self.logger.info(
                        f"Reset state for task {task_id}: {old_status.value} -> {TaskStatus.PENDING.value}",
                    )
                    return True

                self.logger.warning(f"Task {task_id} not found for state reset")
                return False

        except (TaskStateError, StateTransitionError, ValidationError):
            self.logger.exception("Failed to reset state for task {task_id}: ")
            return False

    async def save_state(self, task_id: str) -> dict[str, Any]:
        """保存任务状态到持久化存储"""
        try:
            status = await self.get_status(task_id)
            history = await self.get_state_history(task_id)

            return {
                "task_id": task_id,
                "status": status.value if status else None,
                "history": [transition.to_dict() for transition in history],
                "timestamp": datetime.now(UTC).isoformat(),
            }
        except (TaskStateError, StateTransitionError, ValidationError) as e:
            self.logger.exception(f"Failed to save state for task {task_id}: {e}")
            raise  # Re-raise to fail fast - state save failures should not be silent

    async def load_state(self, task_id: str, data: dict[str, Any]) -> bool:
        """从持久化存储加载任务状态"""
        try:
            if not data or "status" not in data:
                return False

            status = TaskStatus(data["status"])
            reason = f"Loaded from persistence at {data.get('timestamp', 'unknown time')}"

            # 设置状态
            async with self._lock:
                self._states[task_id] = status

                # 加载历史记录
                if "history" in data:
                    history = [StateTransition.from_dict(trans_data) for trans_data in data["history"]]
                    self._state_history[task_id] = history

                # 发送事件
                emit_typed_event = get_emit_typed_event()
                taskeventtype = get_TaskEventType()
                await emit_typed_event(
                    taskeventtype.STATE_CHANGED,
                    {
                        "old_state": "",
                        "new_state": status.value,
                        "reason": reason,
                        "task_id": task_id,
                    },
                    self.event_bus,  # 🔧 修复：添加 event_bus 参数
                    task_id=task_id,
                    source="state_manager",
                )

                self.logger.info(f"Loaded state for task {task_id}: {status.value}")
                return True

        except (TaskStateError, StateTransitionError, ValidationError):
            self.logger.exception("Failed to load state for task {task_id}: ")
            return False
