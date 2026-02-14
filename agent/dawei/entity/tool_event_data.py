# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""工具执行事件数据类
定义工具执行过程中的强类型事件数据结构
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class ToolExecutionStatus(StrEnum):
    """工具执行状态枚举"""

    STARTED = "started"
    VALIDATING = "validating"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass
class ToolCallStartData:
    """工具调用开始事件数据"""

    tool_name: str
    tool_input: dict[str, Any]
    tool_call_id: str | None = None
    task_id: str = ""

    def get_event_data(self) -> dict[str, Any]:
        """获取事件数据的字典表示"""
        return {
            "tool_name": self.tool_name,
            "tool_input": self.tool_input,
            "tool_call_id": self.tool_call_id,
            "task_id": self.task_id,
        }


@dataclass
class ToolCallProgressData:
    """工具调用进度事件数据"""

    tool_name: str
    status: ToolExecutionStatus
    message: str
    progress_percentage: int | None = None
    tool_call_id: str | None = None
    task_id: str = ""
    current_step: str | None = None
    total_steps: int | None = None
    current_step_index: int | None = None

    def get_event_data(self) -> dict[str, Any]:
        """获取事件数据的字典表示"""
        data = {
            "tool_name": self.tool_name,
            "status": self.status.value,
            "message": self.message,
            "tool_call_id": self.tool_call_id,
            "task_id": self.task_id,
        }

        if self.progress_percentage is not None:
            data["progress_percentage"] = self.progress_percentage
        if self.current_step is not None:
            data["current_step"] = self.current_step
        if self.total_steps is not None:
            data["total_steps"] = self.total_steps
        if self.current_step_index is not None:
            data["current_step_index"] = self.current_step_index

        return data


@dataclass
class ToolCallResultData:
    """工具调用结果事件数据"""

    tool_name: str
    result: Any
    is_error: bool = False
    error_message: str | None = None
    error_code: str | None = None
    tool_call_id: str | None = None
    task_id: str = ""
    execution_time: float | None = None

    def get_event_data(self) -> dict[str, Any]:
        """获取事件数据的字典表示"""
        data = {
            "tool_name": self.tool_name,
            "result": self.result,
            "is_error": self.is_error,
            "tool_call_id": self.tool_call_id,
            "task_id": self.task_id,
        }

        if self.error_message:
            data["error_message"] = self.error_message
        if self.error_code:
            data["error_code"] = self.error_code
        if self.execution_time is not None:
            data["execution_time"] = self.execution_time

        return data


@dataclass
class ToolCallDetailedProgressData:
    """工具调用详细进度事件数据（用于复杂工具）"""

    tool_name: str
    status: ToolExecutionStatus
    message: str
    tool_call_id: str | None = None
    task_id: str = ""

    # 进度信息
    progress_percentage: int | None = None
    current_step: str | None = None
    total_steps: int | None = None
    current_step_index: int | None = None

    # 执行信息
    execution_time: float | None = None
    estimated_remaining_time: float | None = None

    # 额外数据
    extra_data: dict[str, Any] | None = None

    def get_event_data(self) -> dict[str, Any]:
        """获取事件数据的字典表示"""
        data = {
            "tool_name": self.tool_name,
            "status": self.status.value,
            "message": self.message,
            "tool_call_id": self.tool_call_id,
            "task_id": self.task_id,
        }

        # 添加进度信息
        if self.progress_percentage is not None:
            data["progress_percentage"] = self.progress_percentage
        if self.current_step is not None:
            data["current_step"] = self.current_step
        if self.total_steps is not None:
            data["total_steps"] = self.total_steps
        if self.current_step_index is not None:
            data["current_step_index"] = self.current_step_index

        # 添加执行信息
        if self.execution_time is not None:
            data["execution_time"] = self.execution_time
        if self.estimated_remaining_time is not None:
            data["estimated_remaining_time"] = self.estimated_remaining_time

        # 添加额外数据
        if self.extra_data:
            data["extra_data"] = self.extra_data

        return data


# 导出所有事件数据类
__all__ = [
    "ToolCallDetailedProgressData",
    "ToolCallProgressData",
    "ToolCallResultData",
    "ToolCallStartData",
    "ToolExecutionStatus",
]
