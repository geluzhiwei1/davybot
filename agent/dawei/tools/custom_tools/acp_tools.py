# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""ACP (Agent Client Protocol) tools."""

from __future__ import annotations

import json
from typing import List

from pydantic import BaseModel, Field

from dawei.acp.agent_registry import get_tool_description_text, list_available_agents
from dawei.acp.client_adapter import ACPAgentClient
from dawei.core.decorators import safe_tool_operation
from dawei.tools.custom_base_tool import CustomBaseTool


class CallACPAgentInput(BaseModel):
    """Input for CallACPAgentTool."""

    command: str = Field(..., description="ACP agent command, e.g. codex")
    prompt: str = Field(..., description="Prompt text sent to the ACP agent")
    args: List[str] = Field(default_factory=list, description="Command arguments for the ACP agent process")
    cwd: str | None = Field(None, description="Working directory used to start ACP agent process")
    session_cwd: str | None = Field(None, description="Working directory for the ACP agent session. Overrides the default workspace directory if specified.")
    timeout: int = Field(300, description="Prompt timeout in seconds")


class CallACPAgentTool(CustomBaseTool):
    """Tool for invoking external ACP-compatible agents."""

    name: str = "call_acp_agent"
    # Base description; will be overridden dynamically in model_post_init
    description: str = "Calls an external ACP (Agent Client Protocol) agent process and returns its response. Available agents are dynamically loaded from the ACP registry at startup."
    args_schema: type[BaseModel] = CallACPAgentInput

    def model_post_init(self, __context: object) -> None:
        """Override description with dynamic agent list from registry."""
        super().model_post_init(__context)
        try:
            dynamic_desc = get_tool_description_text()
            if dynamic_desc:
                self.description = dynamic_desc
        except Exception:
            pass  # Keep default description on registry errors

    def __init__(self):
        super().__init__()
        self.client = ACPAgentClient()

    @safe_tool_operation(
        "call_acp_agent",
        fallback_value='{"status": "error", "message": "Failed to call ACP agent"}',
    )
    def _run(
        self,
        command: str,
        prompt: str,
        args: List[str] | None = None,
        cwd: str | None = None,
        session_cwd: str | None = None,
        timeout: int = 300,
    ) -> str:
        # Validate command against registry
        available = list_available_agents()
        available_commands = [a.command for a in available]
        if available_commands and command not in available_commands:
            return json.dumps(
                {
                    "status": "error",
                    "message": f"Agent '{command}' not available. Available: {', '.join(available_commands)}",
                },
                ensure_ascii=False,
            )

        result = self.client.invoke_sync(
            command=command,
            prompt=prompt,
            args=args or [],
            cwd=cwd,
            session_cwd=session_cwd,
            timeout_seconds=timeout,
        )
        return json.dumps(result.to_dict(), ensure_ascii=False, indent=2)


__all__ = ["CallACPAgentTool"]
