# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

import json
import os
import subprocess

from pydantic import BaseModel, Field

from dawei.core.decorators import safe_tool_operation
from dawei.tools.custom_base_tool import CustomBaseTool

# ============================================================================
# Shared Utilities
# ============================================================================

DANGEROUS_COMMANDS = ["rm -rf", "sudo", "chmod 777", "dd if=", "mkfs", "format"]
ALLOWED_SHELL_COMMANDS = [
    "ls",
    "pwd",
    "echo",
    "cat",
    "grep",
    "find",
    "wc",
    "head",
    "tail",
    "sort",
    "uniq",
]


def _check_dangerous_command(command: str) -> str | None:
    """Check if command contains dangerous patterns.

    Args:
        command: Command string to check

    Returns:
        Error message if dangerous, None otherwise

    """
    # SUPER MODE: Bypass dangerous command checks
    from dawei.core.super_mode import is_super_mode_enabled, log_security_bypass

    if is_super_mode_enabled():
        log_security_bypass("_check_dangerous_command", f"command={command}")
        return None

    command_lower = command.lower()
    for dangerous in DANGEROUS_COMMANDS:
        if dangerous in command_lower:
            return f"Command blocked for security reasons: contains '{dangerous}'"
    return None


def _build_command_result(
    command: str,
    exit_code: int,
    stdout: str,
    stderr: str,
    cwd: str | None = None,
) -> str:
    """Build standardized JSON result for command execution.

    Args:
        command: Executed command
        exit_code: Process exit code
        stdout: Standard output
        stderr: Standard error
        cwd: Working directory

    Returns:
        JSON string with execution result

    """
    output = {
        "command": command,
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "status": "success" if exit_code == 0 else "error",
    }

    if cwd:
        output["cwd"] = cwd

    if exit_code == 0:
        output["message"] = "Command executed successfully"
    else:
        output["message"] = f"Command failed with exit code {exit_code}"

    return json.dumps(output, indent=2)


# ============================================================================
# Execute Command Tool
# ============================================================================


# Execute Command Tool
class ExecuteCommandInput(BaseModel):
    """Input schema for ExecuteCommandTool."""

    command: str = Field(..., description="Command to execute")
    cwd: str | None = Field(
        None,
        description="Working directory (ignored, always uses workspace)",
    )
    timeout: int = Field(30, description="Timeout in seconds")
    shell: bool = Field(True, description="Whether to use shell for command execution")


class ExecuteCommandTool(CustomBaseTool):
    """Tool for executing system commands with security checks.

    Note: This tool ALWAYS executes in the workspace directory. The cwd parameter is ignored.
    """

    name: str = "execute_command"
    description: str = "Runs system commands and programs with optional working directory and timeout. Always executes in the workspace directory for security."
    args_schema: type[BaseModel] = ExecuteCommandInput

    @safe_tool_operation(
        "execute_command",
        fallback_value='{"status": "error", "message": "Failed to execute command"}',
    )
    def _run(
        self,
        command: str,
        _cwd: str | None = None,
        timeout: int = 30,
        shell: bool = True,
    ) -> str:
        """Execute system command with security checks.

        Args:
            command: Command string to execute
            cwd: Ignored (always uses workspace directory)
            timeout: Execution timeout in seconds
            shell: Whether to use shell

        Returns:
            JSON string with execution result

        """
        # Security check
        error_msg = _check_dangerous_command(command)
        if error_msg:
            return json.dumps({"status": "error", "message": error_msg}, indent=2)

        # Get current working directory (tool_executor has already switched to workspace)
        actual_cwd = os.getcwd()

        # Execute command
        result = subprocess.run(
            command,
            shell=shell,
            cwd=actual_cwd,
            timeout=timeout,
            capture_output=True,
            text=True,
        )

        return _build_command_result(
            command=command,
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            cwd=actual_cwd,
        )


# ============================================================================
# Run Slash Command Tool
# ============================================================================


class RunSlashCommandInput(BaseModel):
    """Input schema for RunSlashCommandTool."""

    command: str = Field(..., description="Slash command to execute (e.g., '/help', '/commit')")
    args: str | None = Field(None, description="Optional arguments for the slash command")


class RunSlashCommandTool(CustomBaseTool):
    """Tool for executing predefined slash commands with 3-tier priority system.

    Supports built-in commands, user commands, and workspace-specific commands.
    """

    name: str = "run_slash_command"
    description: str = "Execute predefined slash commands for templated workflows and instructions"
    args_schema: type[BaseModel] = RunSlashCommandInput

    def __init__(self, command_manager=None):
        """Initialize RunSlashCommandTool.

        Args:
            command_manager: CommandManager instance (optional, will create if not provided)

        """
        super().__init__()
        from dawei.tools.command_manager import CommandManager

        self.command_manager = command_manager or CommandManager()
        self.command_manager.create_default_builtin_commands()
        self.command_manager.scan_commands()

    @safe_tool_operation(
        "run_slash_command",
        fallback_value='{"status": "error", "message": "Failed to execute slash command"}',
    )
    def _run(self, command: str, args: str | None = None) -> str:
        """Execute slash command.

        Args:
            command: Command name (e.g., '/help', 'help', '/commit')
            args: Optional arguments for the command

        Returns:
            JSON string with command execution result

        """
        # Strip leading / if present
        command_name = command.strip().lstrip("/")
        cmd = self.command_manager.get_command(command_name)

        if not cmd:
            available_commands = self.command_manager.get_command_names()
            return json.dumps(
                {
                    "command": f"/{command_name}",
                    "status": "error",
                    "message": f"Unknown slash command: /{command_name}",
                    "available_commands": available_commands,
                    "hint": "Type /help to see all available commands",
                },
                indent=2,
            )

        # Build formatted result
        formatted_parts = [
            f"# Command: /{cmd.name}",
        ]

        if cmd.description:
            formatted_parts.append(f"**Description**: {cmd.description}")
        if cmd.argument_hint:
            formatted_parts.append(f"**Arguments**: {cmd.argument_hint}")
        if cmd.mode:
            formatted_parts.append(f"**Mode**: {cmd.mode}")

        formatted_parts.append(f"**Source**: {cmd.source}")

        if args:
            formatted_parts.append(f"**Provided Arguments**: {args}")

        formatted_parts.append("\n--- Command Content ---\n")
        formatted_parts.append(cmd.content)

        return json.dumps(
            {
                "command": f"/{cmd.name}",
                "status": "success",
                "description": cmd.description,
                "mode": cmd.mode,
                "source": cmd.source,
                "content": cmd.content,
                "formatted": "\n".join(formatted_parts),
            },
            indent=2,
        )

    def list_commands(self) -> str:
        """List all available commands.

        Returns:
            JSON string with all commands

        """
        commands = self.command_manager.get_all_commands()
        commands_list = [
            {
                "name": f"/{name}",
                "description": cmd.description,
                "argument_hint": cmd.argument_hint,
                "mode": cmd.mode,
                "source": cmd.source,
            }
            for name, cmd in commands.items()
        ]

        return json.dumps({"total": len(commands_list), "commands": commands_list}, indent=2)


# ============================================================================
# Shell Command Tool (Secure Version)
# ============================================================================


class ShellCommandInput(BaseModel):
    """Input schema for ShellCommandTool."""

    command: str = Field(..., description="Command to execute")
    args: list[str] = Field(..., description="Command arguments as list")
    cwd: str | None = Field(
        None,
        description="Working directory (ignored, always uses workspace)",
    )


class ShellCommandTool(CustomBaseTool):
    """Tool for executing shell commands with argument list for better security.

    Only allows a predefined set of safe commands.
    Always executes in the workspace directory.

    Note: This tool ALWAYS executes in the workspace directory. The cwd parameter is ignored.
    """

    name: str = "shell_command"
    description: str = "Executes shell commands with argument list for better security. Only allows safe commands: " + ", ".join(ALLOWED_SHELL_COMMANDS)
    args_schema: type[BaseModel] = ShellCommandInput

    @safe_tool_operation(
        "shell_command",
        fallback_value='{"status": "error", "message": "Failed to execute shell command"}',
    )
    def _run(self, command: str, args: list[str], _cwd: str | None = None) -> str:
        """Execute shell command with arguments.

        Args:
            command: Command to execute
            args: Command arguments as list
            cwd: Ignored (always uses workspace directory)

        Returns:
            JSON string with execution result

        """
        # Security check - only allow whitelisted commands
        if command not in ALLOWED_SHELL_COMMANDS:
            return json.dumps(
                {
                    "command": command,
                    "status": "error",
                    "message": f"Command '{command}' not in allowed list: {ALLOWED_SHELL_COMMANDS}",
                },
                indent=2,
            )

        # Get current working directory (tool_executor has already switched to workspace)
        actual_cwd = os.getcwd()

        # Execute command
        result = subprocess.run([command, *args], cwd=actual_cwd, capture_output=True, text=True)

        return _build_command_result(
            command=str([command, *args]),
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            cwd=actual_cwd,
        )
