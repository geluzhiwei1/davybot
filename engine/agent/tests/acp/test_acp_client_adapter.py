# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from dawei.acp.client_adapter import ACPAgentClient


class _Model:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _AgentMessageChunk:
    def __init__(self, content):
        self.content = content


class _FakeRequestError(Exception):
    @classmethod
    def method_not_found(cls, method: str):
        return cls(method)


class _FakeConn:
    def __init__(self, client):
        self._client = client
        self.cancel_called = False

    async def initialize(self, **kwargs):
        return _Model()

    async def new_session(self, **kwargs):
        return _Model(session_id="sess-1")

    async def prompt(self, session_id: str, prompt: list, **kwargs):
        chunk = _AgentMessageChunk(content=SimpleNamespace(text="hello from acp"))
        await self._client.session_update(session_id, chunk)
        return _Model(stop_reason="end_turn")

    async def cancel(self, session_id: str, **kwargs):
        self.cancel_called = True


class _FakeProcess:
    def __init__(self):
        self.returncode = None
        self.terminated = False

    def terminate(self):
        self.terminated = True
        self.returncode = 0

    async def wait(self):
        return 0


class _FakeACP:
    PROTOCOL_VERSION = 1
    RequestError = _FakeRequestError

    schema = SimpleNamespace(
        AgentMessageChunk=_AgentMessageChunk,
        ClientCapabilities=_Model,
        Implementation=_Model,
    )

    @staticmethod
    def text_block(text: str):
        return {"type": "text", "text": text}

    @staticmethod
    @asynccontextmanager
    async def spawn_agent_process(client, command: str, *args, cwd=None):
        conn = _FakeConn(client)
        process = _FakeProcess()
        yield conn, process


@pytest.mark.asyncio
async def test_invoke_collects_agent_chunks(monkeypatch):
    from dawei.acp import client_adapter as mod

    monkeypatch.setattr(mod, "import_acp", lambda: _FakeACP)

    client = ACPAgentClient()
    result = await client.invoke(command="fake-agent", args=[], prompt="hi")

    assert result.status == "success"
    assert result.session_id == "sess-1"
    assert result.stop_reason == "end_turn"
    assert "hello from acp" in result.output
    assert result.chunks == ["hello from acp"]
