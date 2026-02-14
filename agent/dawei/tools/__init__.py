# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""工具模块
包含工具包装器和执行器
"""

from .custom_base_tool import CustomBaseTool
from .custom_tools import (
    ApplyDiffTool,
    DocumentParsingTool,
    GenerateDiagramTool,
    MermaidChartingTool,
    NewTaskTool,
    SmartFileEditTool,
    UpdateTodoListTool,
)
from .custom_tools.skills_tool import (
    GetSkillTool,
    ListSkillResourcesTool,
    ListSkillsTool,
    ReadSkillResourceTool,
    SearchSkillsTool,
    create_skills_tools,
)
from .custom_tools.timer_tools import TimerTool
from .scheduler import scheduler_manager
from .skill_manager import Skill, SkillManager
from .tool_executor import ToolExecutor
from .tool_manager import ToolManager


def get_tools_for_mode(mode: str, user_workspace=None):
    """获取指定模式的工具列表

    Args:
        mode: 模式名称
        user_workspace: 用户工作区实例（可选）

    Returns:
        List[Dict]: 工具列表

    """
    if user_workspace and hasattr(user_workspace, "get_mode_available_tools"):
        result = user_workspace.get_mode_available_tools(mode)
        return result.get("tools", [])

    # 如果没有用户工作区，返回空列表
    return []


__all__ = [
    "ApplyDiffTool",
    "CustomBaseTool",
    "DocumentParsingTool",
    "GenerateDiagramTool",
    "GetSkillTool",
    "ListSkillResourcesTool",
    "ListSkillsTool",
    "MermaidChartingTool",
    "NewTaskTool",
    "ReadSkillResourceTool",
    "SearchSkillsTool",
    "Skill",
    "SkillManager",
    "SmartFileEditTool",
    "TimerTool",
    "ToolExecutor",
    "ToolManager",
    "UpdateTodoListTool",
    "create_skills_tools",
    "get_all_tools",
    "get_tool_by_name",
    "get_tools_for_mode",
    "register_tool",
    "scheduler_manager",
    "unregister_tool",
]
