# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""统一错误处理模块
定义所有 agentic 模块相关的异常类
"""

import time
from typing import Any


class AgenticError(Exception):
    """基础异常类"""

    def __init__(
        self,
        message: str,
        error_code: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        self.timestamp = time.time()

    def to_dict(self) -> dict[str, Any]:
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
