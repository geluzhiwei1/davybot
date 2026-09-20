# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""记忆工具 — Agent 主动保存记忆到 auto-memory.

当用户说"记住..."或 Agent 发现值得保存的信息时调用。
写入 auto-memory markdown 文件, 下次对话自动注入。
"""

from pydantic import BaseModel, Field

from dawei.core.decorators import safe_tool_operation
from dawei.tools.custom_base_tool import CustomBaseTool


class SaveMemoryInput(BaseModel):
    """Input for SaveMemoryTool."""

    category: str = Field(
        ...,
        description="Memory category: 'facts' (事实), 'preferences' (偏好), 'procedures' (操作经验), 'debugging' (调试记录)",
    )
    summary: str = Field(
        ...,
        description="One-line summary of the memory (will appear in MEMORY.md index)",
    )
    detail: str | None = Field(
        None,
        description="Optional detailed content (written to topic file)",
    )
    scope: str = Field(
        "workspace",
        description="Memory scope: 'user' (跨工作区, 关于用户本人) or 'workspace' (仅当前项目)",
    )


class SaveMemoryTool(CustomBaseTool):
    """Save a memory to auto-memory files.

    Use when:
    - User says "记住", "remember", "记下来"
    - You discover a user preference worth remembering
    - You learn a project-specific fact or debugging insight

    The memory will be injected into future conversations automatically.
    """

    name: str = "save_memory"
    description: str = (
        "Save a memory for future conversations. "
        "Use when the user says '记住' or you discover something worth remembering. "
        "Categories: facts, preferences, procedures, debugging. "
        "Scope: 'user' (about the user, cross-workspace) or 'workspace' (project-specific)."
    )
    args_schema: type[BaseModel] = SaveMemoryInput

    def __init__(self, agent=None):
        super().__init__()
        self.agent = agent

    def set_agent(self, agent):
        self.agent = agent

    @safe_tool_operation(
        "save_memory",
        fallback_value='{"status": "error", "message": "Failed to save memory"}',
    )
    def _run(
        self,
        category: str = "facts",
        summary: str = "",
        detail: str | None = None,
        scope: str = "workspace",
    ) -> str:
        """Save memory to auto-memory file.

        Args:
            category: facts / preferences / procedures / debugging
            summary: One-line summary
            detail: Optional detailed content
            scope: user (cross-workspace) or workspace (project-specific)

        Returns:
            JSON status string
        """
        import json

        # Validate category
        valid_categories = {"facts", "preferences", "procedures", "debugging"}
        if category not in valid_categories:
            return json.dumps(
                {
                    "status": "error",
                    "message": f"Invalid category '{category}'. Must be one of: {valid_categories}",
                }
            )

        # Get workspace info from context (set by tool executor)
        user_id = "default_user"
        workspace_path = None

        # Try context first (set at execution time)
        if self.context:
            uw = getattr(self.context, "user_workspace", None)
            if uw:
                user_id = getattr(uw, "user_id", "default_user") or "default_user"
                workspace_path = getattr(uw, "absolute_path", None)
            # Also try agent from context
            agent = getattr(self.context, "agent", None)
            if agent and not workspace_path:
                uw = getattr(agent, "user_workspace", None)
                if uw:
                    user_id = getattr(uw, "user_id", "default_user") or "default_user"
                    workspace_path = getattr(uw, "absolute_path", None)

        # Fallback to self.agent (set via constructor or set_agent)
        if not workspace_path and self.agent:
            uw = getattr(self.agent, "user_workspace", None)
            if uw:
                user_id = getattr(uw, "user_id", "default_user") or "default_user"
                workspace_path = getattr(uw, "absolute_path", None)

        if scope == "workspace" and not workspace_path:
            return json.dumps(
                {"status": "error", "message": "No workspace available for workspace-scoped memory"}
            )

        # Write to auto-memory
        from dawei.memory.auto_memory import (
            user_auto_memory_dir,
            workspace_auto_memory_dir,
            append_memory,
        )

        try:
            if scope == "user":
                base_dir = user_auto_memory_dir(user_id)
            else:
                base_dir = workspace_auto_memory_dir(workspace_path)

            append_memory(
                base_dir=base_dir,
                category=category,  # type: ignore
                summary=summary,
                detail=detail,
            )

            return json.dumps(
                {
                    "status": "success",
                    "message": f"Memory saved: [{category}] {summary[:60]}",
                    "scope": scope,
                    "category": category,
                }
            )
        except Exception as e:
            return json.dumps({"status": "error", "message": f"Failed to save: {e}"})
