# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""子任务独立会话（P2-7，灰度 flag 控制）

executor 持有 conversation 路线（非 workspace 指针交换，避免并行子任务竞态）：
- flag off（默认）：所有函数退化为 no-op / None，走原共享对话路径，零行为变化
- flag on：子任务获得独立 Conversation（task_type="subtask"），父对话只收 summary

本模块保持纯函数 / 无网络，便于单测。
"""

from dawei.conversation.conversation import Conversation
from dawei.entity.lm_messages import UserMessage
from dawei.logg.logging import get_logger

logger = get_logger(__name__)

NO_RESULT_PLACEHOLDER = "(no explicit completion result)"


def is_subtask_isolation_enabled() -> bool:
    """读取灰度 flag（AgentExecutionConfig.subtask_isolated_conversation）。

    读取失败（settings 异常）按 False 处理（保守降级到共享对话）。
    """
    try:
        from dawei.config.settings import get_settings

        return bool(get_settings().agent_execution.subtask_isolated_conversation)
    except Exception:  # noqa: BLE001 — flag 读取失败必须降级而非炸掉主流程
        return False


def _as_text(value) -> str:
    """把 description（可能是 UserInputMessage）等统一转成纯文本"""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    content = getattr(value, "content", None)
    if isinstance(content, str):
        return content
    return str(value)


def create_subtask_conversation(
    task_node_id: str,
    message: str,
    context_note: str | None = None,
    agent: str | None = None,
) -> Conversation:
    """创建子任务独立会话，并写入首条任务指令（UserMessage）。

    通信契约（§4.1 第 4 条）：父 → 子仅 message（+ 可选 context 显式背景）。
    """
    parts = ["[subtask] ", _as_text(message)]
    if context_note:
        parts.append(f"\n[context] {context_note}")
    conv = Conversation(
        title=f"subtask-{task_node_id[:12]}",
        task_type="subtask",
        source_task_id=task_node_id,
        metadata={"agent": agent} if agent else {},
    )
    conv.say(UserMessage(content="".join(parts)))
    return conv


def extract_task_completion(conversation: Conversation | None, max_chars: int = 2000) -> str:
    """从指定会话提取最后一条 task_completion 结果（定向提取，消除 F6/F8）。

    Args:
        conversation: 目标子任务的独立会话（None → 返回占位符）
        max_chars: 结果最大字符数

    """
    import json as _json

    if conversation is None:
        return NO_RESULT_PLACEHOLDER
    for msg in reversed(conversation.messages):
        content = getattr(msg, "content", None)
        if not content or not isinstance(content, str):
            continue
        try:
            data = _json.loads(content)
        except (ValueError, TypeError):
            continue
        if isinstance(data, dict) and data.get("type") == "task_completion" and data.get("result"):
            return str(data["result"])[:max_chars]
    return NO_RESULT_PLACEHOLDER


def get_subtask_conversation(engine, task_node_id: str) -> Conversation | None:
    """从活动引擎的 executor 注册表取子任务的隔离会话（无则 None）"""
    executor = getattr(engine, "_node_executors", {}).get(task_node_id) if engine else None
    return getattr(executor, "_conversation", None) if executor else None


def select_result_conversation(engine, task_node_id: str) -> Conversation | None:
    """run_task 结果提取的会话选择：隔离会话优先，回落共享对话（F8）"""
    conv = get_subtask_conversation(engine, task_node_id)
    if conv is not None:
        return conv
    workspace = getattr(engine, "_user_workspace", None)
    return getattr(workspace, "current_conversation", None) if workspace else None
