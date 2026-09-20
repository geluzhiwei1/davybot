# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""统一错误处理模块
定义所有 agentic 模块相关的异常类
"""

import time
from typing import List, Dict, Any


class AgenticError(Exception):
    """基础异常类"""

    def __init__(
        self,
        message: str,
        error_code: str | None = None,
        details: Dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        self.timestamp = time.time()

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "error": self.__class__.__name__,
            "message": self.message,
            "error_code": self.error_code,
            "details": self.details,
            "timestamp": self.timestamp,
        }


class TaskNotFoundError(AgenticError):
    """任务未找到错误"""

    def __init__(self, task_id: str):
        super().__init__(
            f"Task not found: {task_id}",
            error_code="TASK_NOT_FOUND",
            details={"task_id": task_id},
        )


class TaskExecutionError(AgenticError):
    """任务执行错误"""

    def __init__(self, task_id: str, reason: str):
        super().__init__(
            f"Task execution failed: {task_id} - {reason}",
            error_code="TASK_EXECUTION_ERROR",
            details={"task_id": task_id, "reason": reason},
        )


class SubtaskBreadthLimitExceededError(AgenticError):
    """同父活跃子任务数超上限（P1b ⑦ 广度闸，图谱层结构不变量）。

    与 PermissionError(深度闸)区分：这是流控信号而非权限拒绝——
    父 LLM 应等待现有子任务到终态或主动终结后再派发，
    工具层据此返回可操作的 error result（携带活跃子任务 ID 列表）。
    """

    def __init__(self, parent_id: str, active_ids: list[str], limit: int):
        super().__init__(
            f"Active subtasks of parent {parent_id} reached breadth limit "
            f"{limit} (active={len(active_ids)}); wait for terminal states or abort.",
            error_code="SUBTASK_BREADTH_LIMIT",
            details={
                "parent_id": parent_id,
                "active_subtask_ids": list(active_ids),
                "active_count": len(active_ids),
                "limit": limit,
            },
        )
        self.parent_id = parent_id
        self.active_subtask_ids = list(active_ids)
        self.limit = limit


class DuplicateSubtaskError(AgenticError):
    """同父下已存在同目标（归一化描述前缀一致）的未终结/已完成子任务（P1-3 重复派发熔断）。

    与广度闸（SubtaskBreadthLimitExceededError）区分：这不是并发流控，而是
    "同一目标被重复派发"的结构信号——父 LLM 应复用/等待既有子任务，
    而不是等价重派（E2E 2026-09-18：6× 等价派发单子任务烧 1.79M tokens）。
    FAILED/ABORTED 的历史子任务不算重复（显式重试合法）。
    """

    def __init__(self, parent_id: str, existing_id: str, existing_status: str, desc_key: str):
        super().__init__(
            f"An equivalent subtask already exists under parent {parent_id} "
            f"(subtask_id={existing_id}, status={existing_status}). Re-dispatching the "
            f"same goal is blocked; reuse or wait for it instead.",
            error_code="SUBTASK_DUPLICATE",
            details={
                "parent_id": parent_id,
                "existing_subtask_id": existing_id,
                "existing_status": existing_status,
                "description_key": desc_key,
            },
        )
        self.parent_id = parent_id
        self.existing_subtask_id = existing_id
        self.existing_status = existing_status


class ConfigurationError(AgenticError):
    """配置错误"""

    def __init__(self, message: str, config_key: str | None = None):
        super().__init__(
            f"Configuration error: {message}",
            error_code="CONFIGURATION_ERROR",
            details={"config_key": config_key},
        )


class ToolExecutionError(AgenticError):
    """工具执行错误"""

    def __init__(self, tool_name: str, reason: str):
        super().__init__(
            f"Tool execution failed: {tool_name} - {reason}",
            error_code="TOOL_EXECUTION_ERROR",
            details={"tool_name": tool_name, "reason": reason},
        )


class StateTransitionError(AgenticError):
    """状态转换错误"""

    def __init__(self, from_state: str, to_state: str, reason: str):
        super().__init__(
            f"Invalid state transition from {from_state} to {to_state}: {reason}",
            error_code="STATE_TRANSITION_ERROR",
            details={"from_state": from_state, "to_state": to_state, "reason": reason},
        )


class CheckpointError(AgenticError):
    """检查点错误"""

    def __init__(self, checkpoint_id: str, reason: str):
        super().__init__(
            f"Checkpoint error: {checkpoint_id} - {reason}",
            error_code="CHECKPOINT_ERROR",
            details={"checkpoint_id": checkpoint_id, "reason": reason},
        )


class ModeSwitchError(AgenticError):
    """模式切换错误"""

    def __init__(self, from_mode: str, to_mode: str, reason: str):
        super().__init__(
            f"Mode switch failed from {from_mode} to {to_mode}: {reason}",
            error_code="MODE_SWITCH_ERROR",
            details={"from_mode": from_mode, "to_mode": to_mode, "reason": reason},
        )


class ValidationError(AgenticError):
    """验证错误"""

    def __init__(self, field_name: str, field_value: Any, reason: str):
        super().__init__(
            f"Validation failed for {field_name}: {reason}",
            error_code="VALIDATION_ERROR",
            details={
                "field_name": field_name,
                "field_value": str(field_value),
                "reason": reason,
            },
        )


class ResourceError(AgenticError):
    """资源错误"""

    def __init__(self, resource_type: str, resource_id: str, reason: str):
        super().__init__(
            f"Resource error for {resource_type}:{resource_id} - {reason}",
            error_code="RESOURCE_ERROR",
            details={
                "resource_type": resource_type,
                "resource_id": resource_id,
                "reason": reason,
            },
        )
