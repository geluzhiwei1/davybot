# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""对话压缩结构不变量回归测试 —— GLM 400 code=1214 ("messages 参数非法")。

背景(2026-09-24 事故, conversation e839ac91):
对话达到压缩阈值后,ConversationCompressor 把唯一 user 消息压掉、并在会话
中间插入 role="system" 的 [Conversation Summary]。GLM 等端点只允许 system
位于整个 messages 首位且要求至少一条 user 轮,该请求直接 400 1214,任务中止。

本文件锁定 Claude Code compact 语义:
1. 摘要以 user 角色注入,置于对话段最前部(system prompt 之后)
2. 摘要保留被压缩 user 消息原文(任务意图)并带继续指令
3. 压缩输出不含 mid-conversation system
4. 至少一条 user 消息;结构无法满足时回退原始消息(fail fast)
5. tool_calls / tool 配对在压缩后仍可被 sanitize_tool_call_pairs 修复
"""

import pytest

from dawei.agentic.conversation_compressor import (
    ConversationCompressor,
    enforce_chat_message_invariants,
)
from dawei.prompts.llm_message_builder import sanitize_tool_call_pairs


def _make_conversation(rounds: int = 60) -> list[dict]:
    """构造单 user + N 轮 assistant(tool_calls)/tool 的对话(复现事故形态)。"""
    msgs = [{"role": "user", "content": "请你审查 研究任务/research-us-image-synthesis/paper"}]
    for i in range(rounds):
        msgs.append(
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": f"call_{i}",
                        "type": "function",
                        "function": {"name": "read_file", "arguments": '{"file_path": "f.txt"}'},
                    }
                ],
            }
        )
        msgs.append({"role": "tool", "tool_call_id": f"call_{i}", "content": f"1 | result {i}"})
    return msgs


class TestEnforceChatMessageInvariants:
    def test_mid_system_converted_to_user(self):
        msgs = [
            {"role": "user", "content": "hi"},
            {"role": "system", "content": "[Conversation Summary]\n..."},
            {"role": "assistant", "content": "ok"},
        ]
        fixed = enforce_chat_message_invariants(msgs)
        assert fixed is not None
        assert [m["role"] for m in fixed] == ["user", "user", "assistant"]
        assert fixed[1]["content"].startswith("[system-note]")

    def test_allow_leading_system_keeps_prompt_converts_mid_system(self):
        """防御参数:全量 messages 调用时(allow_leading_system=True),
        首位 system prompt 保留,中间的 system 仍被转换。"""
        msgs = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "hi"},
            {"role": "system", "content": "legacy poison"},
            {"role": "assistant", "content": "ok"},
        ]
        fixed = enforce_chat_message_invariants(msgs, allow_leading_system=True)
        assert fixed is not None
        assert [m["role"] for m in fixed] == ["system", "user", "user", "assistant"]
        assert fixed[0]["content"] == "You are a helpful assistant."  # 原样保留
        assert fixed[2]["content"].startswith("[system-note]")

    def test_default_converts_leading_system_too(self):
        """默认(对话段模式):首位 system 也会被转换——防止全量调用方漏传参数时
        静默放过(转换后请求仍合法,只是 prompt 降级,日志可见)。"""
        msgs = [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "hi"},
        ]
        fixed = enforce_chat_message_invariants(msgs)
        assert fixed is not None
        assert [m["role"] for m in fixed] == ["user", "user"]

    def test_allow_leading_system_validation_only_mode(self):
        msgs = [
            {"role": "system", "content": "prompt"},
            {"role": "user", "content": "hi"},
        ]
        assert enforce_chat_message_invariants(msgs, repair=False, allow_leading_system=True) == msgs
        msgs.append({"role": "system", "content": "mid"})
        assert enforce_chat_message_invariants(msgs, repair=False, allow_leading_system=True) is None

    def test_no_user_returns_none(self):
        msgs = [
            {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "t", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "c1", "content": "r"},
        ]
        assert enforce_chat_message_invariants(msgs) is None

    def test_valid_messages_untouched(self):
        msgs = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "ok"},
        ]
        assert enforce_chat_message_invariants(msgs) == msgs


class TestIntelligentCompression:
    def test_summary_is_front_user_message(self):
        compressor = ConversationCompressor(preserve_recent=10)
        original = _make_conversation()
        compressed, stats = compressor._intelligent_compression(original, 100000, 10**9)

        assert stats.compression_ratio > 0
        # 不变量 3:首条为 user 摘要(Claude Code compact 语义)
        assert compressed[0]["role"] == "user"
        assert compressed[0]["content"].startswith("[Conversation Summary]")
        # 不变量 1:对话段内无 system
        assert all(m["role"] != "system" for m in compressed)
        # 不变量 2:至少一条 user
        assert any(m["role"] == "user" for m in compressed)

    def test_summary_preserves_user_request_and_continuation(self):
        compressor = ConversationCompressor(preserve_recent=10)
        compressed, _ = compressor._intelligent_compression(_make_conversation(), 100000, 10**9)

        summary = compressed[0]["content"]
        # 原始任务意图进入摘要(Primary Request and Intent)
        assert "research-us-image-synthesis" in summary
        # 继续任务指令
        assert "Continue with the current task" in summary

    def test_compressed_output_survives_tool_pair_sanitizer(self):
        compressor = ConversationCompressor(preserve_recent=10)
        compressed, _ = compressor._intelligent_compression(_make_conversation(), 100000, 10**9)

        sanitized = sanitize_tool_call_pairs(compressed)
        # sanitize 后结构仍合法:无 mid-system、有 user、配对闭环
        assert all(m["role"] != "system" for m in sanitized)
        assert any(m["role"] == "user" for m in sanitized)
        pending = set()
        for m in sanitized:
            if m["role"] == "assistant" and m.get("tool_calls"):
                pending = {tc["id"] for tc in m["tool_calls"]}
            elif m["role"] == "tool":
                assert m["tool_call_id"] in pending
                pending.discard(m["tool_call_id"])


class TestAggressiveCompression:
    def test_no_mid_system_and_front_user_summary(self):
        compressor = ConversationCompressor(preserve_recent=10)
        original = _make_conversation()
        compressed, stats = compressor._aggressive_compression(original, 100000, 10**9)

        assert stats.strategy_used == "aggressive"
        assert compressed[0]["role"] == "user"
        assert "compacted" in compressed[0]["content"]
        assert all(m["role"] != "system" for m in compressed)
        assert any(m["role"] == "user" for m in compressed)


class TestCompressConversationFallback:
    def test_fallback_when_no_user_message(self):
        """全是 assistant/tool 的对话:压缩无法满足不变量时必须回退原始消息。"""
        compressor = ConversationCompressor(preserve_recent=5)
        original = [
            {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "t", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "c1", "content": "r1"},
        ] * 10

        compressed, stats = compressor.compress_conversation(original, target_tokens=1)
        assert stats.strategy_used == "none"
        assert compressed == original

    def test_intelligent_path_via_public_api(self):
        """公开入口:压缩结果满足全部不变量(事故场景回归)。"""
        compressor = ConversationCompressor(preserve_recent=10, max_tokens=2000)
        original = _make_conversation(rounds=60)

        compressed, stats = compressor.compress_conversation(original)
        assert stats.strategy_used in ("intelligent", "aggressive")
        assert compressed[0]["role"] == "user"
        assert all(m["role"] != "system" for m in compressed)
        assert any(m["role"] == "user" for m in compressed)


@pytest.mark.parametrize(
    "strategy",
    ["intelligent", "aggressive"],
)
def test_regression_accident_shape(strategy):
    """事故形态端到端:压缩 → sanitize → enforce 全链路合法。"""
    compressor = ConversationCompressor(preserve_recent=10)
    original = _make_conversation(rounds=60)
    if strategy == "intelligent":
        compressed, _ = compressor._intelligent_compression(original, 100000, 10**9)
    else:
        compressed, _ = compressor._aggressive_compression(original, 100000, 10**9)

    final = enforce_chat_message_invariants(sanitize_tool_call_pairs(compressed))
    assert final is not None
    assert final[0]["role"] == "user"
    assert all(m["role"] != "system" for m in final)


def test_builder_fallback_also_repairs_mid_system():
    """审查修复:无-user 早退返回 None 时,注入 continuation 后必须重跑 enforce,
    否则残留的 mid-system 会再次触发 GLM 1214。"""
    poisoned = [
        {"role": "assistant", "content": "a"},
        {"role": "system", "content": "[Conversation Summary] legacy poison"},
        {"role": "assistant", "content": "b"},
    ]
    sanitized = sanitize_tool_call_pairs(poisoned)
    assert enforce_chat_message_invariants(sanitized) is None  # 无 user 早退

    # builder 兜底路径(与 llm_message_builder 实现一致)
    enforced = enforce_chat_message_invariants(
        [{"role": "user", "content": "[Continuation] continue."}, *sanitized],
    )
    assert enforced is not None, "re-run after injection must succeed"
    roles = [m["role"] for m in enforced]
    assert roles == ["user", "assistant", "user", "assistant"]  # mid-system 已转换
    assert enforced[2]["content"].startswith("[system-note]")


def test_convert_system_handles_none_and_multimodal_content():
    from dawei.agentic.conversation_compressor import _convert_system_to_user

    # content=None 不应渲染成 "None"
    fixed = _convert_system_to_user({"role": "system", "content": None})
    assert fixed["role"] == "user"
    assert fixed["content"] == "[system-note] "

    # 多模态 list content:前置文本块,原块保留,不渲染 repr
    blocks = [{"type": "text", "text": "hi"}, {"type": "image_url", "image_url": {"url": "x"}}]
    fixed = _convert_system_to_user({"role": "system", "content": blocks})
    assert fixed["content"][0] == {"type": "text", "text": "[system-note]"}
    assert fixed["content"][1:] == blocks


def test_user_excerpt_count_bounded():
    """长对话(大量 user 追问)摘要不无界膨胀:摘录条数有上限且首尾保留。"""
    msgs = [{"role": "user", "content": f"问题 {i}: " + "y" * 100} for i in range(50)]
    msgs += [{"role": "assistant", "content": "ok"}] * 10
    compressor = ConversationCompressor(preserve_recent=2)
    compressed, _ = compressor._intelligent_compression(msgs, 100000, 10**9)

    summary = compressed[0]["content"]
    assert "问题 0:" in summary  # 首条(初始意图)保留
    assert "问题 49:" in summary  # 尾条(最新指令)保留
    assert "omitted" in summary  # 中间省略标记
    n_excerpts = sum(1 for line in summary.splitlines() if line.strip().startswith(tuple(f"{i}." for i in range(1, 51))))
    assert n_excerpts <= 12  # 上限 10 + 省略占位


def test_aggressive_preserves_message_order():
    """审查修复(遗留 bug):aggressive 的 key_indices 是 set,乱序迭代会把
    tool 响应排到配对 assistant 之前(sanitize 时被当孤儿丢弃)。"""
    compressor = ConversationCompressor(preserve_recent=2)
    original = _make_conversation(rounds=30)
    compressed, _ = compressor._aggressive_compression(original, 100000, 10**9)

    # 压缩输出中 assistant(tool_calls) 必须先于其 tool 响应出现
    seen_assistant_calls = set()
    for m in compressed:
        if m["role"] == "assistant" and m.get("tool_calls"):
            seen_assistant_calls.update(tc["id"] for tc in m["tool_calls"])
        elif m["role"] == "tool":
            assert m["tool_call_id"] in seen_assistant_calls, "tool response precedes its assistant tool_calls"
    # sanitize 后无孤儿被丢
    sanitized = sanitize_tool_call_pairs(compressed)
    kept_tools = sum(1 for m in sanitized if m["role"] == "tool")
    total_tools = sum(1 for m in compressed if m["role"] == "tool")
    assert kept_tools == total_tools, "ordered output should lose no tool results in sanitize"
