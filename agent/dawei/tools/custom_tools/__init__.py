# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Custom tools package for the Dawei agent system.

This package provides a comprehensive set of tools organized by functionality:
- Read Tools: File reading, listing
- Edit Tools: Content insertion, file writing, enhanced diff application
- Command Tools: Command execution, slash commands, shell commands
- MCP Tools: Model Context Protocol tool integration
- Workflow Tools: Todo management, mode switching, task control
- Timer Tools: Scheduled task management and reminders
- Knowledge Tools: Knowledge base search and RAG
- Docx Tools: DOCX reading, editing, diffing
- Cost Tools: LLM usage cost tracking and optimization
"""

# Original tools
from .acp_tools import CallACPAgentTool
from .command_tools import ExecuteCommandTool, RunSlashCommandTool, ShellCommandTool

# Cost tools
from .cost_tools import ShowCostTool

# Docx tools
from .docx_diff_tool import DocxDiffTool
from .docx_edit_tool import DocxEditTool
from .docx_read_tool import DocxReadStructuredTool
from .edit_tools import InsertContentTool, WriteToFileTool

# Knowledge base tools
from .knowledge_tool import KnowledgeRAGTool, KnowledgeSearchTool

from .mcp_tools import AccessMCPResource, ConnectMCPServer, DisconnectMCPServer, ListMCPServers, UseMCPTool

# Custom tools
from .read_tools import ListFilesTool, ReadFileTool
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
    # Read Tools
    "ReadFileTool",
    "ListFilesTool",
    # Edit Tools
    "InsertContentTool",
    "WriteToFileTool",
    "SmartFileEditTool",
    # Command Tools
    "ExecuteCommandTool",
    "RunSlashCommandTool",
    "ShellCommandTool",
    "CallACPAgentTool",
    # Cost Tools
    "ShowCostTool",
    # MCP Tools
    "UseMCPTool",
    "AccessMCPResource",
    "ListMCPServers",
    "ConnectMCPServer",
    "DisconnectMCPServer",
    # Workflow Tools
    "AskFollowupQuestionTool",
    "AttemptCompletionTool",
    "SwitchModeTool",
    "NewTaskTool",
    "UpdateTodoListTool",
    "GetTaskStatusTool",
    # Timer/Scheduler Tools
    "TimerTool",
    # Knowledge Base Tools
    "KnowledgeSearchTool",
    "KnowledgeRAGTool",
    # Docx Tools
    "DocxReadStructuredTool",
    "DocxDiffTool",
    "DocxEditTool",
]
