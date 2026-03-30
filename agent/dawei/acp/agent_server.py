# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""ACP server adapter for exposing Dawei as an ACP-compatible agent."""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from dawei import __version__
from dawei.agentic.agent import Agent
from dawei.core.datetime_compat import UTC
from dawei.entity.user_input_message import UserInputText
from dawei.workspace.user_workspace import UserWorkspace

from .sdk_loader import import_acp


@dataclass
class ACPDaweiSession:
    session_id: str
    cwd: str
    mode: str
    llm: str | None
    updated_at: datetime
    title: str | None = None
    user_workspace: UserWorkspace | None = None
    agent: Agent | None = None
    prompt_task: asyncio.Task[Any] | None = None


def _content_block_to_text(block: Any) -> str:
    if block is None:
        return ""

    if isinstance(block, dict):
        if isinstance(block.get("text"), str):
            return block["text"]
        if isinstance(block.get("uri"), str):
            return f"[resource:{block['uri']}]"
        return str(block)

    text = getattr(block, "text", None)
    if isinstance(text, str):
        return text

    uri = getattr(block, "uri", None)
    if isinstance(uri, str):
        return f"[resource:{uri}]"

    return str(block)


def _assistant_content_to_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            text = getattr(item, "text", None)
            if isinstance(text, str):
                parts.append(text)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n".join(part for part in parts if part)
    return str(content)


class DaweiACPAgent:
    """ACP Agent implementation backed by Dawei runtime."""

    def __init__(
        self,
        workspace: str,
        llm: str | None = None,
        mode: str = "orchestrator",
        prompt_timeout: int = 1800,
        verbose: bool = False,
    ):
        self.workspace = workspace
        self.default_llm = llm
        self.default_mode = mode
        self.prompt_timeout = prompt_timeout
        self.verbose = verbose

        self._acp = import_acp()
        self._conn: Any | None = None
        self._sessions: dict[str, ACPDaweiSession] = {}

    def on_connect(self, conn: Any) -> None:
        self._conn = conn

    def _build_mode_state(self) -> Any:
        schema = self._acp.schema
        available_modes = [
            schema.SessionMode(id="orchestrator", name="Orchestrator", description="Default Dawei orchestration mode"),
            schema.SessionMode(id="plan", name="Plan", description="PDCA Plan mode"),
            schema.SessionMode(id="do", name="Do", description="PDCA Do mode"),
            schema.SessionMode(id="check", name="Check", description="PDCA Check mode"),
            schema.SessionMode(id="act", name="Act", description="PDCA Act mode"),
        ]
        return schema.SessionModeState(available_modes=available_modes, current_mode_id=self.default_mode)

    async def _ensure_runtime(self, session: ACPDaweiSession) -> None:
        if session.agent and session.user_workspace:
            return

        workspace = UserWorkspace(workspace_path=session.cwd)
        await workspace.initialize()

        agent_config: dict[str, Any] = {
            "enable_auto_mode_switch": False,
            "enable_skills": True,
            "enable_mcp": True,
            "max_iterations": 100,
            "checkpoint_interval": 60.0,
        }
        if session.llm:
            agent_config["llm_model"] = session.llm

        agent = await Agent.create_with_default_engine(user_workspace=workspace, config=agent_config)
        workspace.mode = session.mode

        if session.llm:
            with contextlib.suppress(Exception):
                workspace.llm_manager.set_provider(session.llm)

        session.user_workspace = workspace
        session.agent = agent

    async def _extract_new_assistant_output(self, session: ACPDaweiSession, previous_assistant_count: int) -> str:
        workspace = session.user_workspace
        if not workspace or not workspace.current_conversation:
            return ""

        messages = workspace.current_conversation.assistant_messages
        if previous_assistant_count >= len(messages):
            return ""

        new_messages = messages[previous_assistant_count:]
        text_chunks = []
        for message in new_messages:
            text = _assistant_content_to_text(getattr(message, "content", None))
            if text:
                text_chunks.append(text)

        return "\n".join(text_chunks)

    async def initialize(
        self,
        protocol_version: int,
        client_capabilities: Any | None = None,
        client_info: Any | None = None,
        **kwargs: Any,
    ) -> Any:
        schema = self._acp.schema
        return schema.InitializeResponse(
            protocol_version=self._acp.PROTOCOL_VERSION,
            agent_capabilities=schema.AgentCapabilities(
                load_session=True,
                session_capabilities=schema.SessionCapabilities(
                    list=schema.SessionListCapabilities(),
                    resume=schema.SessionResumeCapabilities(),
                    close=schema.SessionCloseCapabilities(),
                    fork=schema.SessionForkCapabilities(),
                ),
            ),
            agent_info=schema.Implementation(
                name="dawei-acp-agent",
                title="Dawei ACP Agent",
                version=__version__,
            ),
        )

    async def authenticate(self, method_id: str, **kwargs: Any) -> Any:
        return self._acp.schema.AuthenticateResponse()

    async def new_session(self, cwd: str, mcp_servers: list[Any] | None = None, **kwargs: Any) -> Any:
        schema = self._acp.schema
        session_id = uuid.uuid4().hex
        self._sessions[session_id] = ACPDaweiSession(
            session_id=session_id,
            cwd=cwd or self.workspace,
            mode=self.default_mode,
            llm=self.default_llm,
            updated_at=datetime.now(UTC),
            title="Dawei ACP Session",
        )
        return schema.NewSessionResponse(session_id=session_id, modes=self._build_mode_state())

    async def load_session(self, cwd: str, session_id: str, mcp_servers: list[Any] | None = None, **kwargs: Any) -> Any:
        if session_id not in self._sessions:
            raise self._acp.RequestError.invalid_params({"sessionId": session_id, "reason": "unknown session"})

        session = self._sessions[session_id]
        if cwd:
            session.cwd = cwd
        session.updated_at = datetime.now(UTC)
        return self._acp.schema.LoadSessionResponse(modes=self._build_mode_state())

    async def list_sessions(self, cursor: str | None = None, cwd: str | None = None, **kwargs: Any) -> Any:
        schema = self._acp.schema
        sessions = []
        for session in self._sessions.values():
            if cwd and session.cwd != cwd:
                continue
            sessions.append(
                schema.SessionInfo(
                    session_id=session.session_id,
                    cwd=session.cwd,
                    title=session.title,
                    updated_at=session.updated_at.isoformat(),
                )
            )
        return schema.ListSessionsResponse(sessions=sessions, next_cursor=None)

    async def set_session_mode(self, mode_id: str, session_id: str, **kwargs: Any) -> Any:
        session = self._sessions.get(session_id)
        if not session:
            raise self._acp.RequestError.invalid_params({"sessionId": session_id, "reason": "unknown session"})

        session.mode = mode_id
        session.updated_at = datetime.now(UTC)
        if session.user_workspace:
            session.user_workspace.mode = mode_id

        return self._acp.schema.SetSessionModeResponse()

    async def set_session_model(self, model_id: str, session_id: str, **kwargs: Any) -> Any:
        session = self._sessions.get(session_id)
        if not session:
            raise self._acp.RequestError.invalid_params({"sessionId": session_id, "reason": "unknown session"})

        session.llm = model_id
        session.updated_at = datetime.now(UTC)
        if session.user_workspace:
            with contextlib.suppress(Exception):
                session.user_workspace.llm_manager.set_provider(model_id)

        return self._acp.schema.SetSessionModelResponse()

    async def set_config_option(self, config_id: str, session_id: str, value: str | bool, **kwargs: Any) -> Any:
        return None

    async def prompt(self, prompt: list[Any], session_id: str, message_id: str | None = None, **kwargs: Any) -> Any:
        session = self._sessions.get(session_id)
        if not session:
            raise self._acp.RequestError.invalid_params({"sessionId": session_id, "reason": "unknown session"})

        prompt_text = "\n".join(filter(None, (_content_block_to_text(block) for block in prompt))).strip()
        if not prompt_text:
            prompt_text = "(empty prompt)"

        await self._ensure_runtime(session)

        if session.user_workspace and session.user_workspace.mode != session.mode:
            session.user_workspace.mode = session.mode

        if session.llm and session.user_workspace:
            with contextlib.suppress(Exception):
                session.user_workspace.llm_manager.set_provider(session.llm)

        previous_assistant_count = 0
        if session.user_workspace and session.user_workspace.current_conversation:
            previous_assistant_count = len(session.user_workspace.current_conversation.assistant_messages)

        try:
            user_message = UserInputText(text=prompt_text, task_node_id=None)
            session.prompt_task = asyncio.create_task(session.agent.process_message(user_message))

            await asyncio.wait_for(session.prompt_task, timeout=self.prompt_timeout)
            await asyncio.sleep(0.1)

            assistant_output = await self._extract_new_assistant_output(session, previous_assistant_count)
            if not assistant_output:
                assistant_output = "任务已执行完成。"

            if self._conn:
                await self._conn.session_update(
                    session_id=session_id,
                    update=self._acp.update_agent_message_text(assistant_output),
                    source="dawei_acp",
                )

            session.updated_at = datetime.now(UTC)
            return self._acp.schema.PromptResponse(stop_reason="end_turn")

        except TimeoutError:
            if session.agent:
                with contextlib.suppress(Exception):
                    await session.agent.stop()
            return self._acp.schema.PromptResponse(stop_reason="cancelled")

        except asyncio.CancelledError:
            if session.agent:
                with contextlib.suppress(Exception):
                    await session.agent.stop()
            return self._acp.schema.PromptResponse(stop_reason="cancelled")

        except Exception as exc:
            if self._conn:
                with contextlib.suppress(Exception):
                    await self._conn.session_update(
                        session_id=session_id,
                        update=self._acp.update_agent_message_text(f"执行失败: {exc}"),
                        source="dawei_acp",
                    )
            return self._acp.schema.PromptResponse(stop_reason="end_turn")

        finally:
            session.prompt_task = None

    async def fork_session(self, cwd: str, session_id: str, mcp_servers: list[Any] | None = None, **kwargs: Any) -> Any:
        original = self._sessions.get(session_id)
        if not original:
            raise self._acp.RequestError.invalid_params({"sessionId": session_id, "reason": "unknown session"})

        new_session_id = uuid.uuid4().hex
        self._sessions[new_session_id] = ACPDaweiSession(
            session_id=new_session_id,
            cwd=cwd or original.cwd,
            mode=original.mode,
            llm=original.llm,
            updated_at=datetime.now(UTC),
            title=original.title,
        )
        return self._acp.schema.ForkSessionResponse(session_id=new_session_id, modes=self._build_mode_state())

    async def resume_session(self, cwd: str, session_id: str, mcp_servers: list[Any] | None = None, **kwargs: Any) -> Any:
        session = self._sessions.get(session_id)
        if not session:
            raise self._acp.RequestError.invalid_params({"sessionId": session_id, "reason": "unknown session"})

        if cwd:
            session.cwd = cwd
        session.updated_at = datetime.now(UTC)
        return self._acp.schema.ResumeSessionResponse(modes=self._build_mode_state())

    async def close_session(self, session_id: str, **kwargs: Any) -> Any:
        session = self._sessions.pop(session_id, None)
        if session and session.agent:
            with contextlib.suppress(Exception):
                await session.agent.cleanup()
        if session and session.user_workspace:
            with contextlib.suppress(Exception):
                await session.user_workspace.cleanup()

        return self._acp.schema.CloseSessionResponse()

    async def cancel(self, session_id: str, **kwargs: Any) -> None:
        session = self._sessions.get(session_id)
        if not session:
            return

        if session.prompt_task and not session.prompt_task.done():
            session.prompt_task.cancel()

        if session.agent:
            with contextlib.suppress(Exception):
                await session.agent.stop()

    async def ext_method(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        raise self._acp.RequestError.method_not_found(method)

    async def ext_notification(self, method: str, params: dict[str, Any]) -> None:
        raise self._acp.RequestError.method_not_found(method)


async def run_dawei_acp_server(
    workspace: str,
    llm: str | None = None,
    mode: str = "orchestrator",
    prompt_timeout: int = 1800,
    verbose: bool = False,
) -> None:
    """Run Dawei ACP server over stdio."""
    acp = import_acp()
    await acp.run_agent(
        DaweiACPAgent(
            workspace=workspace,
            llm=llm,
            mode=mode,
            prompt_timeout=prompt_timeout,
            verbose=verbose,
        )
    )
