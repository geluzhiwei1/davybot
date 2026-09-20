# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest


class _Model:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _AgentMessageChunk:
    def __init__(self, content):
        self.content = content


class _FakeRequestError(Exception):
    @classmethod
    def invalid_params(cls, data=None):
        return cls(f"invalid_params: {data}")

    @classmethod
    def method_not_found(cls, method: str):
        return cls(f"method_not_found: {method}")


class _FakeACP:
    PROTOCOL_VERSION = 1
    RequestError = _FakeRequestError

    schema = SimpleNamespace(
        SessionMode=_Model,
        SessionModeState=_Model,
        InitializeResponse=_Model,
        AgentCapabilities=_Model,
        SessionCapabilities=_Model,
        SessionListCapabilities=_Model,
        SessionResumeCapabilities=_Model,
        SessionCloseCapabilities=_Model,
        SessionForkCapabilities=_Model,
        Implementation=_Model,
        AuthenticateResponse=_Model,
        NewSessionResponse=_Model,
        LoadSessionResponse=_Model,
        SessionInfo=_Model,
        ListSessionsResponse=_Model,
        SetSessionModeResponse=_Model,
        SetSessionModelResponse=_Model,
        PromptResponse=_Model,
        ForkSessionResponse=_Model,
        ResumeSessionResponse=_Model,
        CloseSessionResponse=_Model,
    )

    @staticmethod
    def update_agent_message_text(text: str):
        return _AgentMessageChunk(content=SimpleNamespace(text=text))


class _FakeUserWorkspace:
    def __init__(self, workspace_path: str):
        self.workspace_path = workspace_path
        self.mode = "orchestrator"
        self.llm_manager = SimpleNamespace(set_provider=lambda *_: None)
        self.current_conversation = SimpleNamespace(assistant_messages=[])

    async def initialize(self):
        return None

    async def cleanup(self):
        return None


class _FakeAgentInstance:
    def __init__(self, user_workspace):
        self.user_workspace = user_workspace
        self.stopped = False

    async def process_message(self, user_message):
        await asyncio.sleep(0)
        self.user_workspace.current_conversation.assistant_messages.append(
            SimpleNamespace(content=f"echo:{user_message.text}")
        )

    async def stop(self):
        self.stopped = True

    async def cleanup(self):
        return None


class _FakeAgentClass:
    @staticmethod
    async def create_with_default_engine(user_workspace, config=None):
        return _FakeAgentInstance(user_workspace)


class _FakeConn:
    def __init__(self):
        self.updates = []

    async def session_update(self, session_id: str, update, **kwargs):
        self.updates.append({"session_id": session_id, "update": update, "kwargs": kwargs})


@pytest.mark.asyncio
async def test_dawei_acp_agent_prompt_roundtrip(monkeypatch, tmp_path):
    from dawei.acp import agent_server as mod

    monkeypatch.setattr(mod, "import_acp", lambda: _FakeACP)
    monkeypatch.setattr(mod, "UserWorkspace", _FakeUserWorkspace)
    monkeypatch.setattr(mod, "Agent", _FakeAgentClass)

    agent = mod.DaweiACPAgent(workspace=str(tmp_path), llm=None, mode="orchestrator", prompt_timeout=5)
    conn = _FakeConn()
    agent.on_connect(conn)

    session = await agent.new_session(cwd=str(tmp_path))
    prompt_resp = await agent.prompt(prompt=[SimpleNamespace(text="hello")], session_id=session.session_id)

    assert prompt_resp.stop_reason == "end_turn"
    assert len(conn.updates) == 1
    assert conn.updates[0]["session_id"] == session.session_id
    assert "echo:hello" in conn.updates[0]["update"].content.text


@pytest.mark.asyncio
async def test_dawei_acp_agent_list_sessions(monkeypatch, tmp_path):
    from dawei.acp import agent_server as mod

    monkeypatch.setattr(mod, "import_acp", lambda: _FakeACP)
    monkeypatch.setattr(mod, "UserWorkspace", _FakeUserWorkspace)
    monkeypatch.setattr(mod, "Agent", _FakeAgentClass)

    agent = mod.DaweiACPAgent(workspace=str(tmp_path), llm=None, mode="orchestrator")

    s1 = await agent.new_session(cwd=str(tmp_path))
    s2 = await agent.new_session(cwd=str(tmp_path))
    resp = await agent.list_sessions()

    session_ids = {item.session_id for item in resp.sessions}
    assert s1.session_id in session_ids
    assert s2.session_id in session_ids
