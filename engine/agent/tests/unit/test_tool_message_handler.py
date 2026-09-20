# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Unit tests for ToolMessageHandle.execute_tool_call.

回归背景（2026-09-15 线上任务 dd6f52ce 中止）：模型下发非法 JSON 参数时，
内层 json.JSONDecodeError 分支补了一条错误 ToolMessage 后 re-raise，
而 JSONDecodeError 是 ValueError 子类，被外层
except (ToolExecutionError, ValueError, KeyError) 再次捕获又追加一条
同 tool_call_id 的 ToolMessage —— 连续两条 tool 消息违反 OpenAI 协议
（tool 必须紧跟带 tool_calls 的 assistant），下一轮请求被 400 拒绝。
"""

import json
from unittest.mock import AsyncMock

import pytest

from dawei.agentic.tool_message_handler import ToolMessageHandle
from dawei.entity.lm_messages import FunctionCall, ToolCall, ToolMessage


class _RecordingConversation:
    def __init__(self):
        self.said: list = []

    def say(self, msg) -> None:
        self.said.append(msg)


class _FakeTaskNode:
    task_node_id = "tn-test"
    context = None


class _FakeWorkspace:
    def __init__(self, conv: _RecordingConversation):
        self.current_conversation = conv

    def create_task_context(self):
        return object()


class _FakeToolService:
    def __init__(self):
        self.execute_tool = AsyncMock(return_value={"success": True})


@pytest.fixture
def env(monkeypatch):
    conv = _RecordingConversation()
    service = _FakeToolService()
    handler = ToolMessageHandle(
        task_node=_FakeTaskNode(),
        user_workspace=_FakeWorkspace(conv),
        tool_call_service=service,
        event_bus=None,
    )

    async def _noop_emit(*args, **kwargs):  # 事件直发 no-op：单测不接真实总线
        return None

    monkeypatch.setattr("dawei.agentic.tool_message_handler.emit_typed_event", _noop_emit)
    return handler, conv, service


@pytest.mark.unit
async def test_invalid_json_args_appends_single_tool_message(env):
    """非法 JSON 参数 → 仅追加一条错误 ToolMessage、不执行工具、不抛异常。

    旧代码会追加两条（内层 + 外层 ValueError 分支），导致下一轮 LLM 400。
    """
    handler, conv, service = env
    bad_args = '{"todos": [x] 诊断: 会话文件挂载异常}'  # [x] 为非法 JSON
    call = ToolCall(tool_call_id="call_00_bad", function=FunctionCall(name="update_todo_list", arguments=bad_args))

    result = await handler.execute_tool_call(call)

    # 不执行真实工具
    assert service.execute_tool.await_count == 0
    # 关键回归断言：恰好一条 ToolMessage
    assert len(conv.said) == 1
    msg = conv.said[0]
    assert isinstance(msg, ToolMessage)
    assert msg.tool_call_id == "call_00_bad"
    payload = json.loads(msg.content)
    assert "Invalid arguments" in payload["error"]
    assert payload["raw_arguments"] == bad_args
    # 返回错误结果（FAST FAIL：错误随返回值交付，而非异常）
    assert "Invalid arguments" in result["error"]


@pytest.mark.unit
async def test_valid_args_executes_and_appends_single_tool_message(env):
    """合法参数 → 工具执行一次、追加一条 ToolMessage、返回工具结果。"""
    handler, conv, service = env
    call = ToolCall(
        tool_call_id="call_00_ok",
        function=FunctionCall(name="update_todo_list", arguments='{"todos": ["a", "b"]}'),
    )

    result = await handler.execute_tool_call(call)

    service.execute_tool.assert_awaited_once()
    # 传给工具服务的是解析后的 dict
    args = service.execute_tool.await_args.args[1]
    assert args == {"todos": ["a", "b"]}
    assert len(conv.said) == 1
    assert json.loads(conv.said[0].content) == {"success": True}
    assert result == {"success": True}


@pytest.mark.unit
async def test_update_todo_list_string_format_converted(env):
    """update_todo_list 字符串格式自动转数组（既有兼容逻辑不回归）。"""
    handler, conv, service = env
    call = ToolCall(
        tool_call_id="call_00_str",
        function=FunctionCall(name="update_todo_list", arguments='{"todos": "line1\\nline2"}'),
    )

    await handler.execute_tool_call(call)

    args = service.execute_tool.await_args.args[1]
    assert args == {"todos": ["line1", "line2"]}
    assert len(conv.said) == 1
