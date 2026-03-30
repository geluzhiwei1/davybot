# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""ACP command group."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import click


@click.group(name="acp", help="ACP operations (serve Dawei as ACP agent or call external ACP agents)")
def acp_cmd():
    """ACP command group."""


@acp_cmd.command(name="serve", help="Run Dawei ACP server over stdio")
@click.option("--workspace", "-w", required=True, type=click.Path(path_type=Path), help="Workspace path")
@click.option("--llm", "-l", default=None, help="LLM model to use")
@click.option("--mode", "-m", default="orchestrator", show_default=True, help="Default ACP session mode")
@click.option("--timeout", "-t", type=int, default=1800, show_default=True, help="Prompt timeout in seconds")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logs")
def acp_serve(workspace: Path, llm: str | None, mode: str, timeout: int, verbose: bool):
    """Start ACP server on stdio for integration with external ACP clients."""
    from dawei.acp.agent_server import run_dawei_acp_server

    if not workspace.exists():
        workspace.mkdir(parents=True, exist_ok=True)

    try:
        asyncio.run(
            run_dawei_acp_server(
                workspace=str(workspace.resolve()),
                llm=llm,
                mode=mode,
                prompt_timeout=timeout,
                verbose=verbose,
            )
        )
    except KeyboardInterrupt:
        pass


@acp_cmd.command(name="call", help="Call an external ACP agent process once")
@click.option("--command", "-c", required=True, help="ACP agent command, e.g. codex")
@click.option("--arg", "args", multiple=True, help="Command arguments (repeatable)")
@click.option("--prompt", "-p", required=True, help="Prompt text")
@click.option("--cwd", default=None, help="Working directory for spawned agent process")
@click.option("--session-cwd", default=None, help="ACP session cwd sent to the target agent")
@click.option("--timeout", "-t", type=int, default=300, show_default=True, help="Prompt timeout in seconds")
def acp_call(command: str, args: tuple[str, ...], prompt: str, cwd: str | None, session_cwd: str | None, timeout: int):
    """Call an ACP-compatible agent (Codex, custom ACP agent, etc.)."""
    from dawei.acp.client_adapter import ACPAgentClient

    client = ACPAgentClient()
    result = client.invoke_sync(
        command=command,
        args=list(args),
        prompt=prompt,
        cwd=cwd,
        session_cwd=session_cwd,
        timeout_seconds=timeout,
    )

    click.echo(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
