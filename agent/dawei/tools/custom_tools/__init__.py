# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Custom tools package for the Dawei agent system.

This package provides a comprehensive set of tools organized by functionality:
- Document Tools: Document parsing, diff application
- Read Tools: File reading, listing, code definition search
- Search Tools: File search, codebase search
- Edit Tools: Content insertion, file writing, enhanced diff application
- Browser Tools: Browser automation, navigation, interaction
- Command Tools: Command execution, slash commands, shell commands
- MCP Tools: Model Context Protocol tool integration
- Workflow Tools: Todo management, mode switching, task control
"""

# Original tools
from .browser_tools import (
    BrowserActionTool,
    ClickElementTool,
    NavigatePageTool,
    TakeScreenshotTool,
    TypeTextTool,
)
from .command_tools import ExecuteCommandTool, RunSlashCommandTool, ShellCommandTool
from .diagram_generator import GenerateDiagramTool
from .diff_applier import ApplyDiffTool
from .document_parser import DocumentParsingTool
from .edit_tools import ApplyDiffTool as EnhancedApplyDiffTool
from .edit_tools import InsertContentTool, WriteToFileTool

# Market tools
from .market_tools import (
    AgentInstallTool,
    AgentListTool,
    AgentSearchTool,
    AgentUninstallTool,
    MarketSlashCommandsTool,
    PluginInstallTool,
    PluginListTool,
    PluginSearchTool,
    PluginUninstallTool,
    SkillInstallTool,
    SkillListTool,
    SkillSearchTool,
)
from .mcp_tools import AccessMCPResourceTool, ListMCPServersTool, UseMCPToolTool
from .mermaid_charting import MermaidChartingTool

# Custom tools
from .read_tools import ListCodeDefinitionsTool, ListFilesTool, ReadFileTool
from .search_tools import CodebaseSearchTool, SearchFilesTool
from .smart_file_edit import SmartFileEditTool

# Timer/Scheduler tools
from .timer_tools import TimerTool

# Import from fixed workflow tools to avoid circular import
from .workflow_tools_fixed import (
    AskFollowupQuestionTool,
    AttemptCompletionTool,
    GetTaskStatusTool,
    NewTaskTool,
    SwitchModeTool,
    UpdateTodoListTool,
)

__all__ = [
    # Original tools
    "DocumentParsingTool",
    "ApplyDiffTool",
    "GenerateDiagramTool",
    "MermaidChartingTool",
    # Read Tools
    "ReadFileTool",
    "ListFilesTool",
    "ListCodeDefinitionsTool",
    # Search Tools
    "SearchFilesTool",
    "CodebaseSearchTool",
    # Edit Tools
    "InsertContentTool",
    "WriteToFileTool",
    "ApplyDiffTool",  # Enhanced version from edit_tools
    "SmartFileEditTool",  # New tool for large file editing
    # Browser Tools
    "BrowserActionTool",
    "NavigatePageTool",
    "ClickElementTool",
    "TypeTextTool",
    "TakeScreenshotTool",
    # Command Tools
    "ExecuteCommandTool",
    "RunSlashCommandTool",
    "ShellCommandTool",
    # MCP Tools
    "UseMCPToolTool",
    "AccessMCPResourceTool",
    "ListMCPServersTool",
    # Workflow Tools
    "AskFollowupQuestionTool",
    "AttemptCompletionTool",
    "SwitchModeTool",
    "NewTaskTool",
    "UpdateTodoListTool",
    "GetTaskStatusTool",
    # Timer/Scheduler Tools
    "TimerTool",
    # Market Tools
    "SkillSearchTool",
    "SkillInstallTool",
    "SkillListTool",
    "AgentSearchTool",
    "AgentInstallTool",
    "AgentListTool",
    "AgentUninstallTool",
    "PluginSearchTool",
    "PluginInstallTool",
    "PluginListTool",
    "PluginUninstallTool",
    "MarketSlashCommandsTool",
]
