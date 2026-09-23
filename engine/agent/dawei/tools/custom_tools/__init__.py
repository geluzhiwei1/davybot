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
from .expand_tool_result import ExpandToolResultTool

# Knowledge base tools
from .knowledge_tool import (
    KnowledgeRAGTool,
    KnowledgeSearchTool,
    LegalAnalyticsTool,
    LegalAskTool,
    LegalDocumentTimelineTool,
    LegalDocumentTool,
    LegalGraphSearchTool,
    LegalKnowledgeBasesTool,
    LegalSearchFacetsTool,
    LegalSearchTool,
)
from .mcp_tools import AccessMCPResource, ConnectMCPServer, DisconnectMCPServer, ListMCPServers, UseMCPTool

# Market Flow business tools (multi-tenant, per-user JWT — MarketingAgent 编队, group "market")
from .market_tools import (
    MARKET_TOOLS,
    MarketCalibrationTool,
    MarketCompetitorContentsTool,
    MarketCompetitorProfileTool,
    MarketDashboardTool,
    MarketDraftActionTool,
    MarketEvaluateDemandTool,
    MarketGenerateProfileTool,
    MarketGenerateReportTool,
    MarketGeoChecksTool,
    MarketGeoSummaryTool,
    MarketGetEventTool,
    MarketGetSignalTool,
    MarketInsightFeedbackTool,
    MarketListActionsTool,
    MarketListBriefsTool,
    MarketListCompetitorsTool,
    MarketListEventsTool,
    MarketListInsightsTool,
    MarketListKeywordSetsTool,
    MarketListOpportunitiesTool,
    MarketListProductsTool,
    MarketListSignalsTool,
    MarketRunGeoTool,
    MarketRunPipelineTool,
    MarketRunSnapshotTool,
    MarketRunSourceTool,
    MarketSeoChecksTool,
    MarketTrendsTool,
)

# Memory tools
from .memory_tools import SaveMemoryTool

# NormFlow business tools (multi-tenant, per-user JWT — replaces old normflow MCP)
from .normflow_tools import (
    NORMFLOW_TOOLS,
    NormflowAdvanceWorkflowTool,
    NormflowCaseDetailTool,
    NormflowCaseDocumentsTool,
    NormflowCaseTasksTool,
    NormflowCaseTimesheetTool,
    NormflowClientCasesTool,
    NormflowClientDetailTool,
    NormflowCreateFollowUpTool,
    NormflowPaymentStatusTool,
    NormflowSearchCasesTool,
    NormflowSearchClientsTool,
    NormflowWorkflowTemplatesTool,
)

# Custom tools
from .read_tools import ListFilesTool, ReadFileTool

# Research Flow business tools (multi-tenant, per-user JWT — gelu-research-team, group "research")
from .research_tools import (
    RESEARCH_TOOLS,
    ResearchJournalLookupTool,
    ResearchJournalRubricTool,
    ResearchJournalSuggestTool,
    ResearchPaperGetTool,
    ResearchPaperImportTool,
    ResearchPaperSearchTool,
    ResearchReviewRunCreateTool,
    ResearchReviewSubmitTool,
    ResearchSubmissionCheckTool,
)

# Sanctions tools (multi-tenant, per-user JWT — replaces old sanctions MCP)
from .sanctions_tools import (
    SanctionsDashboardTool,
    SanctionsFiltersTool,
    SanctionsGetEntityTool,
    SanctionsGraphTool,
    SanctionsMonitoringTool,
    SanctionsScreenTool,
    SanctionsSearchTool,
    SanctionsWatchlistTool,
)
from .search_tools import SearchToolsTool
from .smart_file_edit import SmartFileEditTool

# Timer/Scheduler tools
from .timer_tools import TimerTool

# Import from fixed workflow tools to avoid circular import
from .workflow_tools_fixed import (
    AskFollowupQuestionTool,
    AttemptCompletionTool,
    GetTaskStatusTool,
    NewTaskTool,
    RunTaskTool,
    SwitchModeTool,
    UpdateTodoListTool,
    WaitTasksTool,
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
    # Governance Tools
    "ExpandToolResultTool",
    # Discovery Tools
    "SearchToolsTool",
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
    "RunTaskTool",
    "UpdateTodoListTool",
    "GetTaskStatusTool",
    "WaitTasksTool",
    # Timer/Scheduler Tools
    "TimerTool",
    # Knowledge Base Tools
    "KnowledgeSearchTool",
    "KnowledgeRAGTool",
    # Legal Search Tools (nn-kb-searcher)
    "LegalSearchTool",
    "LegalAskTool",
    "LegalDocumentTool",
    # Docx Tools
    "DocxReadStructuredTool",
    "DocxDiffTool",
    "DocxEditTool",
    # Market Flow business tools (market-team only, group "market")
    "MARKET_TOOLS",
    "MarketDashboardTool",
    "MarketListProductsTool",
    "MarketListSignalsTool",
    "MarketGetSignalTool",
    "MarketListEventsTool",
    "MarketGetEventTool",
    "MarketListBriefsTool",
    "MarketListInsightsTool",
    "MarketListCompetitorsTool",
    "MarketCompetitorProfileTool",
    "MarketCompetitorContentsTool",
    "MarketTrendsTool",
    "MarketGeoSummaryTool",
    "MarketGeoChecksTool",
    "MarketSeoChecksTool",
    "MarketListKeywordSetsTool",
    "MarketListActionsTool",
    "MarketListOpportunitiesTool",
    "MarketCalibrationTool",
    "MarketRunPipelineTool",
    "MarketRunSourceTool",
    "MarketRunGeoTool",
    "MarketRunSnapshotTool",
    "MarketGenerateProfileTool",
    "MarketGenerateReportTool",
    "MarketDraftActionTool",
    "MarketEvaluateDemandTool",
    "MarketInsightFeedbackTool",
    # Memory Tools
    "SaveMemoryTool",
    # NormFlow business tools (firm-team only, group "normflow")
    "NORMFLOW_TOOLS",
    "NormflowSearchCasesTool",
    "NormflowCaseDetailTool",
    "NormflowCaseTasksTool",
    "NormflowCaseTimesheetTool",
    "NormflowCaseDocumentsTool",
    "NormflowAdvanceWorkflowTool",
    "NormflowWorkflowTemplatesTool",
    "NormflowSearchClientsTool",
    "NormflowClientDetailTool",
    "NormflowClientCasesTool",
    "NormflowCreateFollowUpTool",
    "NormflowPaymentStatusTool",
    # Research Flow business tools (gelu-research-team only, group "research")
    "RESEARCH_TOOLS",
    "ResearchJournalLookupTool",
    "ResearchJournalRubricTool",
    "ResearchPaperSearchTool",
    "ResearchPaperGetTool",
    "ResearchPaperImportTool",
    "ResearchReviewRunCreateTool",
    "ResearchReviewSubmitTool",
    "ResearchJournalSuggestTool",
    "ResearchSubmissionCheckTool",
]
