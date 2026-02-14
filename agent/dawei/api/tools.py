# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""工具 API 路由

Provides REST API endpoints for slash command management and tool operations.
"""

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from dawei.tools.command_manager import CommandManager
from dawei.tools.custom_tools.command_tools import RunSlashCommandTool

router = APIRouter(prefix="/api/tools", tags=["tools"])

# Global singleton instances
_command_manager: CommandManager | None = None
_slash_command_tool: RunSlashCommandTool | None = None


# Pydantic models for request/response
class MermaidRequest(BaseModel):
    """Request model for Mermaid chart generation."""

    description: str
    chart_type: str = "flowchart"
    complexity: str = "medium"


# ============================================================================
# Singleton Management
# ============================================================================


def get_command_manager() -> CommandManager:
    """Get or create the global command manager singleton instance.

    Returns:
        CommandManager: Initialized command manager with default commands

    """
    global _command_manager
    if _command_manager is None:
        import logging

        logger = logging.getLogger(__name__)
        logger.info("[CommandManager] Initializing command manager singleton...")
        _command_manager = CommandManager()
        _command_manager.create_default_builtin_commands()
        _command_manager.scan_commands()
        logger.info(f"[CommandManager] Command manager initialized with {len(_command_manager.get_all_commands())} commands")
    return _command_manager


def get_slash_command_tool() -> RunSlashCommandTool:
    """Get or create the global slash command tool singleton instance.

    Returns:
        RunSlashCommandTool: Initialized slash command tool

    """
    global _slash_command_tool
    if _slash_command_tool is None:
        _slash_command_tool = RunSlashCommandTool(command_manager=get_command_manager())
    return _slash_command_tool


def _update_workspace_context(manager: CommandManager, workspace: str | None) -> None:
    """Update command manager workspace context if provided.

    Args:
        manager: Command manager instance to update
        workspace: Optional workspace path string

    """
    if workspace:
        manager.workspace_root = Path(workspace)


def _format_command_for_response(cmd_name: str, cmd: Any) -> dict[str, str | None]:
    """Format command object for API response.

    Args:
        cmd_name: Command name without prefix
        cmd: Command object from CommandManager

    Returns:
        Dictionary with formatted command data

    """
    return {
        "name": f"/{cmd_name}",
        "description": cmd.description,
        "argument_hint": cmd.argument_hint,
        "mode": cmd.mode,
        "source": cmd.source,
        "path": str(cmd.path) if cmd.source != "builtin" else None,
    }


# ============================================================================
# Slash Commands API Endpoints
# ============================================================================


@router.get("/commands")
async def list_commands(workspace: str | None = None, reload: bool = False) -> dict[str, Any]:
    """List all available slash commands.

    Args:
        workspace: Optional workspace path to load workspace-specific commands
        reload: Force reload commands from disk

    Returns:
        Dictionary with command list, total count, and metadata

    Raises:
        HTTPException: If command listing fails

    """
    try:
        cmd_mgr = get_command_manager()

        # Only update workspace context if a valid workspace path is provided
        # Ignore "default" workspace string as it's not a real path
        if workspace and workspace != "default":
            _update_workspace_context(cmd_mgr, workspace)
            if reload:
                cmd_mgr.reload()
        elif reload:
            # Reload without changing workspace context
            cmd_mgr.reload()

        commands = cmd_mgr.get_all_commands()
        commands_list = [_format_command_for_response(name, cmd) for name, cmd in commands.items()]

        # Log for debugging
        import logging

        logger = logging.getLogger(__name__)
        logger.info(f"[API] Returning {len(commands_list)} slash commands (workspace={workspace}, reload={reload})")
        if len(commands_list) == 0:
            logger.warning("[API] No slash commands found! Built-in commands may not be registered.")

        return {
            "success": True,
            "total": len(commands_list),
            "commands": commands_list,
            "workspace": workspace,
            "reload": reload,
        }
    except (OSError, json.JSONDecodeError, AttributeError, KeyError) as e:
        raise HTTPException(status_code=500, detail=f"Failed to list commands: {e!s}")


@router.get("/commands/{command_name}")
async def get_command(command_name: str, workspace: str | None = None) -> dict[str, Any]:
    """Get a specific slash command by name.

    Args:
        command_name: Name of the command (without / prefix)
        workspace: Optional workspace path

    Returns:
        Dictionary with command details including content

    Raises:
        HTTPException: If command not found (404) or retrieval fails (500)

    """
    try:
        cmd_mgr = get_command_manager()
        _update_workspace_context(cmd_mgr, workspace)

        cmd = cmd_mgr.get_command(command_name)
        if not cmd:
            raise HTTPException(status_code=404, detail=f"Command '/{command_name}' not found")

        command_data = _format_command_for_response(cmd.name, cmd)
        command_data["content"] = cmd.content

        return {"success": True, "command": command_data}
    except HTTPException:
        raise
    except (OSError, json.JSONDecodeError, AttributeError, KeyError) as e:
        raise HTTPException(status_code=500, detail=f"Failed to get command: {e!s}")


@router.post("/commands/reload")
async def reload_commands(workspace: str | None = None) -> dict[str, Any]:
    """Reload slash commands from disk.

    Useful after adding/modifying command files without restarting the server.

    Args:
        workspace: Optional workspace path

    Returns:
        Dictionary with reload status and command count

    Raises:
        HTTPException: If reload fails

    """
    try:
        cmd_mgr = get_command_manager()
        _update_workspace_context(cmd_mgr, workspace)

        commands = cmd_mgr.reload()

        return {
            "success": True,
            "message": "Commands reloaded successfully",
            "total": len(commands),
            "workspace": workspace,
        }
    except (OSError, json.JSONDecodeError, AttributeError) as e:
        raise HTTPException(status_code=500, detail=f"Failed to reload commands: {e!s}")


@router.post("/commands/execute")
async def execute_command(
    command: str,
    args: str | None = None,
    workspace: str | None = None,
) -> dict[str, Any]:
    """Execute a slash command and return its result.

    This endpoint provides direct command execution for testing without
    going through the agent/tool execution flow.

    Args:
        command: Command name (with or without / prefix)
        args: Optional command arguments
        workspace: Optional workspace path

    Returns:
        Dictionary with execution success status and result

    Raises:
        HTTPException: If command execution fails

    """
    try:
        tool = get_slash_command_tool()

        if workspace:
            tool.command_manager.workspace_root = Path(workspace)
            tool.command_manager.reload()

        result_json = tool._run(command, args)
        result = json.loads(result_json)

        return {"success": result.get("status") == "success", "result": result}
    except (
        OSError,
        json.JSONDecodeError,
        AttributeError,
        KeyError,
        ValueError,
        TypeError,
    ) as e:
        raise HTTPException(status_code=500, detail=f"Failed to execute command: {e!s}")
