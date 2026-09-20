# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""max_tokens 截断保护单元测试(2026-09-16 事故回归)

回归场景:推理型模型烧完输出预算(finish_reason=length)、无 tool_calls,
旧逻辑把该轮判为"自然完成" → 任务静默 COMPLETED、前端无任何提示。
现在:截断且无工具调用 → 重试让模型继续(最多 3 轮)→ 仍截断则 LLMError fast-fail。

不依赖 LLM / 网络 / 持久化,全部内存 fake。
"""

import logging
from types import SimpleNamespace

import pytest

from dawei.agentic.task_node_executor import TaskNodeExecutionEngine
from dawei.agentic.tool_message_handler import ToolMessageHandle
from dawei.core.errors import LLMError
from dawei.entity.lm_messages import AssistantMessage
from dawei.entity.stream_message import CompleteMessage
from dawei.entity.task_types import TaskStatus

pytestmark = pytest.mark.unit


class FakeConversation:
    def __init__(self, messages=None):
        self.messages = list(messages or [])

    def say(self, msg):
        self.messages.append(msg)


def make_handler(conversation):
    return ToolMessageHandle(
        task_node=SimpleNamespace(task_node_id="t1", status=TaskStatus.RUNNING),
        user_workspace=SimpleNamespace(current_conversation=conversation),
        tool_call_service=object(),
        event_bus=object(),
        conversation=conversation,
    )


def make_executor(handler, conversation):
    """绕过重量级 __init__,只装配 _should_continue_execution 访问的属性"""
    ex = TaskNodeExecutionEngine.__new__(TaskNodeExecutionEngine)
    ex.task_node = SimpleNamespace(task_node_id="t1", status=TaskStatus.RUNNING)
    ex._tool_message_handler = handler
    ex._conversation = conversation
    ex._user_workspace = SimpleNamespace(current_conversation=conversation)
    ex._consecutive_truncated_rounds = 0
    ex.logger = logging.getLogger("test-truncation")
    return ex


def complete_msg(finish_reason: str, content: str = "部分输出", reasoning: str | None = None):
    return CompleteMessage(content=content, reasoning_content=reasoning, finish_reason=finish_reason)


# ==================== handler: 截断标志 ====================


async def test_handler_flags_length_truncation():
    conv = FakeConversation()
    handler = make_handler(conv)
    await handler.handle_stream_messages(complete_msg("length"))
    assert handler.last_round_truncated is True


async def test_handler_clears_flag_on_normal_stop():
    conv = FakeConversation()
    handler = make_handler(conv)
    await handler.handle_stream_messages(complete_msg("length"))
    await handler.handle_stream_messages(complete_msg("stop"))
    assert handler.last_round_truncated is False


# ==================== executor: 截断 → 重试而非完成 ====================


async def test_truncated_round_retries_instead_of_completing():
    conv = FakeConversation([AssistantMessage(content="被截断的消息")])
    handler = make_handler(conv)
    handler._last_round_truncated = True
    ex = make_executor(handler, conv)

    assert await ex._should_continue_execution() is True  # 重试,不判完成
    assert ex._consecutive_truncated_rounds == 1


async def test_normal_assistant_round_still_completes():
    conv = FakeConversation([AssistantMessage(content="正常回答")])
    handler = make_handler(conv)
    handler._last_round_truncated = False
    ex = make_executor(handler, conv)
    ex._consecutive_truncated_rounds = 2  # 前几轮截断后恢复正常 → 计数应清零

    assert await ex._should_continue_execution() is False  # 正常完成
    assert ex._consecutive_truncated_rounds == 0


async def test_three_consecutive_truncations_fast_fail():
    conv = FakeConversation([AssistantMessage(content="又被截断")])
    handler = make_handler(conv)
    handler._last_round_truncated = True
    ex = make_executor(handler, conv)
    ex._consecutive_truncated_rounds = 2  # 已连截 2 轮

    with pytest.raises(LLMError, match="truncated by max_tokens"):
        await ex._should_continue_execution()
