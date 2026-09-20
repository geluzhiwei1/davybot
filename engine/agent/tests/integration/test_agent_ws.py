# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""A3 — Agent run over WebSocket (backend core, the heart of dawei).

Client sends USER_MESSAGE → server streams STREAM_REASONING / STREAM_CONTENT /
STREAM_TOOL_CALL / STREAM_USAGE → STREAM_COMPLETE. Gated behind a real model
backend (DAWEI_TEST_LLM=1) and the optional `websockets` dev dependency.
"""

import uuid

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def _types(messages):
    return [m.get("type") for m in messages]


@pytest.mark.asyncio
async def test_agent_basic_dialogue(ws, require_llm):
    """A3.1/A3.2 — send a message, get streamed content, end with stream_complete, no error."""
    await ws.send({"type": "user_message", "content": "请只回复两个字：你好", "data": {}})

    complete = ws.wait_for(lambda m: m.get("type") == "stream_complete", timeout=120)
    types = _types(ws.messages)

    assert "stream_error" not in types, f"got stream_error: {[_m for _m in ws.messages if _m.get('type')=='stream_error']}"
    assert complete is not None, f"no stream_complete within timeout; types={types}"

    # Either stream_content deltas or a final assistant message must carry text
    has_text = any(
        m.get("type") in ("stream_content", "stream_reasoning", "assistant_message") and m.get("content")
        for m in ws.messages
    )
    assert has_text, f"no streamed text; messages={ws.messages[:5]}"


@pytest.mark.asyncio
async def test_agent_stream_usage_emitted(ws, require_llm):
    """A3.2 — a STREAM_USAGE (token stats) is emitted before completion (when the model reports it)."""
    await ws.send({"type": "user_message", "content": "1+1=?", "data": {}})
    ws.wait_for(lambda m: m.get("type") == "stream_complete", timeout=120)
    # Usage is best-effort (some providers omit); only assert it's well-formed when present
    usage = [m for m in ws.messages if m.get("type") == "stream_usage"]
    for u in usage:
        assert isinstance(u.get("data", u), dict)


@pytest.mark.asyncio
async def test_agent_two_turn_context(ws, require_llm):
    """A3.5 — a second message on the same connection completes too (context continuity smoke)."""
    await ws.send({"type": "user_message", "content": "我的代号是猎鹰。", "data": {}})
    ws.wait_for(lambda m: m.get("type") == "stream_complete", timeout=120)

    n_before = len(ws.messages)
    await ws.send({"type": "user_message", "content": "我的代号是什么？只回答代号。", "data": {}})
    complete = ws.wait_for(
        lambda m: m.get("type") == "stream_complete",
        timeout=120,
    )
    assert complete is not None, "second turn did not complete"
    # Confirm a fresh assistant turn streamed after the second user message
    assert any(
        m.get("type") in ("stream_content", "assistant_message") and m.get("content")
        for m in ws.messages[n_before:]
    ), "no assistant output for the second turn"
