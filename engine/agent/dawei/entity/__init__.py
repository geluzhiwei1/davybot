# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""数据模型模块
包含专利相关的数据结构、消息类、输出类和任务实体
"""

# 专利模型
# 消息类
from .lm_messages import (
    AssistantMessage,
    ContentType,
    MessageRole,
    SystemMessage,
    ToolMessage,
    UserMessage,
)

# 定时任务
from .scheduled_task import (
    ScheduledTask,
    ScheduleType,
    TriggerStatus,
)

# 任务实体
from .task_types import (
    MCPRequest,
    ModeTransition,
    SkillCall,
    TaskExecutionPlan,
    TaskState,
    TaskSummary,
)

__all__ = [
    # 消息类
    "UserMessage",
    "AssistantMessage",
    "SystemMessage",
    "ToolMessage",
    "MessageRole",
    "ContentType",
    # 任务实体
    "ModeTransition",
    "SkillCall",
    "MCPRequest",
    "TaskExecutionPlan",
    "TaskSummary",
    "TaskState",
    # 定时任务
    "ScheduleType",
    "TriggerStatus",
    "ScheduledTask",
]
