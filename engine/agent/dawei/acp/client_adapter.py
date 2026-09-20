# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""ACP client adapter for calling external ACP-compatible agents."""

from __future__ import annotations

import asyncio
import contextlib
import os
from dataclasses import dataclass, field
from typing import Any

from dawei import __version__

from .sdk_loader import import_acp


@dataclass
class ACPInvocationResult:
    """Result for a single ACP agent invocation."""

    status: str
    session_id: str | None = None
    stop_reason: str | None = None
    output: str = ""
    chunks: list[str] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "session_id": self.session_id,
            "stop_reason": self.stop_reason,
            "output": self.output,
            "chunks": self.chunks,
            "error": self.error,
        }


def _content_to_text(content: Any) -> str:
    """Convert ACP content block to readable text."""
    if content is None:
        return ""

    if isinstance(content, dict):
        if isinstance(content.get("text"), str):
            return content["text"]
        if isinstance(content.get("uri"), str):
            return f"[resource:{content['uri']}]"
        return str(content)

    text = getattr(content, "text", None)
    if isinstance(text, str):
        return text

    uri = getattr(content, "uri", None)
    if isinstance(uri, str):
        return f"[resource:{uri}]"

    return str(content)


class ACPEventCollector:
    """Minimal ACP client implementation for collecting agent output."""

    def __init__(self, acp_module: Any):
        self._acp = acp_module
        self.conn: Any | None = None
        self.chunks: list[str] = []

    @property
    def output(self) -> str:
        return "".join(self.chunks)

    def on_connect(self, conn: Any) -> None:
        self.conn = conn

    async def request_permission(self, options: list[Any], session_id: str, tool_call: Any, **kwargs: Any) -> Any:
        raise self._acp.RequestError.method_not_found("session/request_permission")

    async def write_text_file(self, content: str, path: str, session_id: str, **kwargs: Any) -> Any:
        raise self._acp.RequestError.method_not_found("fs/write_text_file")

    async def read_text_file(self, path: str, session_id: str, limit: int | None = None, line: int | None = None, **kwargs: Any) -> Any:
        raise self._acp.RequestError.method_not_found("fs/read_text_file")

    async def create_terminal(
        self,
        command: str,
        session_id: str,
        args: list[str] | None = None,
        cwd: str | None = None,
        env: list[Any] | None = None,
        output_byte_limit: int | None = None,
        **kwargs: Any,
    ) -> Any:
        raise self._acp.RequestError.method_not_found("terminal/create")

    async def terminal_output(self, session_id: str, terminal_id: str, **kwargs: Any) -> Any:
        raise self._acp.RequestError.method_not_found("terminal/output")

    async def release_terminal(self, session_id: str, terminal_id: str, **kwargs: Any) -> Any:
        raise self._acp.RequestError.method_not_found("terminal/release")

    async def wait_for_terminal_exit(self, session_id: str, terminal_id: str, **kwargs: Any) -> Any:
        raise self._acp.RequestError.method_not_found("terminal/wait_for_exit")

    async def kill_terminal(self, session_id: str, terminal_id: str, **kwargs: Any) -> Any:
        raise self._acp.RequestError.method_not_found("terminal/kill")

    async def session_update(self, session_id: str, update: Any, **kwargs: Any) -> None:
        message_chunk_type = getattr(self._acp.schema, "AgentMessageChunk")
        if isinstance(update, message_chunk_type):
            text = _content_to_text(getattr(update, "content", None))
            if text:
                self.chunks.append(text)

    async def ext_method(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        raise self._acp.RequestError.method_not_found(method)

    async def ext_notification(self, method: str, params: dict[str, Any]) -> None:
        raise self._acp.RequestError.method_not_found(method)


class ACPAgentClient:
    """Client helper for invoking an ACP agent process."""

    async def invoke(
        self,
        command: str,
        prompt: str,
        args: list[str] | None = None,
        cwd: str | None = None,
        session_cwd: str | None = None,
        timeout_seconds: int = 300,
    ) -> ACPInvocationResult:
        acp = import_acp()
        schema = acp.schema
        command_args = args or []
        session_workdir = session_cwd or os.getcwd()
        collector = ACPEventCollector(acp)

        conn: Any | None = None
        session_id: str | None = None

        try:
            async with acp.spawn_agent_process(collector, command, *command_args, cwd=cwd) as (conn, process):
                await conn.initialize(
                    protocol_version=acp.PROTOCOL_VERSION,
                    client_capabilities=schema.ClientCapabilities(),
                    client_info=schema.Implementation(
                        name="dawei-acp-client",
                        title="Dawei ACP Client",
                        version=__version__,
                    ),
                )

                session = await conn.new_session(cwd=session_workdir, mcp_servers=[])
                session_id = session.session_id

                prompt_response = await asyncio.wait_for(
                    conn.prompt(session_id=session_id, prompt=[acp.text_block(prompt)]),
                    timeout=timeout_seconds,
                )

                if process.returncode is None:
                    process.terminate()
                    with contextlib.suppress(ProcessLookupError, TimeoutError):
                        await asyncio.wait_for(process.wait(), timeout=2)

                return ACPInvocationResult(
                    status="success",
                    session_id=session_id,
                    stop_reason=getattr(prompt_response, "stop_reason", "end_turn"),
                    output=collector.output,
                    chunks=collector.chunks.copy(),
                    error=None,
                )

        except TimeoutError:
            if conn and session_id:
                with contextlib.suppress(Exception):
                    await conn.cancel(session_id=session_id)
            return ACPInvocationResult(
                status="error",
                session_id=session_id,
                stop_reason="cancelled",
                output=collector.output,
                chunks=collector.chunks.copy(),
                error=f"Prompt timeout after {timeout_seconds} seconds",
            )

        except Exception as exc:
            return ACPInvocationResult(
                status="error",
                session_id=session_id,
                output=collector.output,
                chunks=collector.chunks.copy(),
                error=str(exc),
            )

    def invoke_sync(
        self,
        command: str,
        prompt: str,
        args: list[str] | None = None,
        cwd: str | None = None,
        session_cwd: str | None = None,
        timeout_seconds: int = 300,
    ) -> ACPInvocationResult:
        """Synchronous wrapper for ACP invocation."""
        try:
            asyncio.get_running_loop()
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(
                    asyncio.run,
                    self.invoke(
                        command=command,
                        prompt=prompt,
                        args=args,
                        cwd=cwd,
                        session_cwd=session_cwd,
                        timeout_seconds=timeout_seconds,
                    ),
                )
                return future.result()
        except RuntimeError:
            return asyncio.run(
                self.invoke(
                    command=command,
                    prompt=prompt,
                    args=args,
                    cwd=cwd,
                    session_cwd=session_cwd,
                    timeout_seconds=timeout_seconds,
                )
            )
