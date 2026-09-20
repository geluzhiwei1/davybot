# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""finalize_task（P1a 不变量 3：status+result 同笔写）真实 TaskGraph 单测。

锁定语义(docs/子任务组织管理交互方案.md)：
- 正常路径：result 先行写入节点，再转终态（读到终态必有 result）
- result 为空 → 按 status 写默认文案（崩溃路径兜底，父 LLM 不盲试）
- 幂等：已终态节点 finalize 返回 False，不做任何变更
- 不覆盖：已有非空 result 不被 finalize 默认文案吞掉（先到先得）
- 未知节点 → False
- 状态机：RUNNING/PENDING/PAUSED → CANCELLED 合法；CANCELLED 为终态锁死
"""

import pytest

from dawei.core.events import SimpleEventBus
from dawei.entity.task_types import TaskStatus
from dawei.task_graph.task_graph import TaskGraph
from dawei.task_graph.task_node_data import TaskContext, TaskData, TaskPriority
from dawei.task_graph.task_validator import StatusTransitionValidationRule


async def _make_graph_with_root(status: TaskStatus = TaskStatus.RUNNING) -> tuple[TaskGraph, str]:
    graph = TaskGraph("graph-1", event_bus=SimpleEventBus())
    root = await graph.create_root_task(
        TaskData(
            task_node_id="root-1",
            description="root task for finalize tests",
            mode="orchestrator",
            status=status,
            context=TaskContext(user_id="u1", session_id="s1", message_id="m1"),
            todos=[],
            priority=TaskPriority.MEDIUM,
        ),
    )
    assert root is not None
    return graph, "root-1"


@pytest.mark.unit
async def test_finalize_writes_result_then_status():
    """运行中 → finalize(CANCELLED+原因)：result 与 status 同笔落节点"""
    graph, root_id = await _make_graph_with_root(TaskStatus.RUNNING)

    changed = await graph.finalize_task(root_id, TaskStatus.CANCELLED, "用户终结: 方向错误")

    assert changed is True
    node = await graph.get_task(root_id)
    assert node.status is TaskStatus.CANCELLED
    assert node.data.result == "用户终结: 方向错误"


@pytest.mark.unit
async def test_finalize_default_result_when_none():
    """result=None → 按 status 写默认文案（崩溃路径不留空 result）"""
    graph, root_id = await _make_graph_with_root(TaskStatus.RUNNING)

    changed = await graph.finalize_task(root_id, TaskStatus.FAILED)

    assert changed is True
    node = await graph.get_task(root_id)
    assert node.status is TaskStatus.FAILED
    assert node.data.result == "(任务失败,无错误详情)"


@pytest.mark.unit
async def test_finalize_idempotent_on_terminal():
    """已终态 → 返回 False，result/status 不被二次改写"""
    graph, root_id = await _make_graph_with_root(TaskStatus.RUNNING)
    assert await graph.finalize_task(root_id, TaskStatus.CANCELLED, "第一次原因") is True

    changed = await graph.finalize_task(root_id, TaskStatus.COMPLETED, "晚到的完成")

    assert changed is False
    node = await graph.get_task(root_id)
    assert node.status is TaskStatus.CANCELLED  # 终态先到先得
    assert node.data.result == "第一次原因"


@pytest.mark.unit
async def test_finalize_does_not_overwrite_existing_result():
    """已有非空 result（attempt_completion 先写）→ finalize 不覆盖"""
    graph, root_id = await _make_graph_with_root(TaskStatus.RUNNING)
    node = await graph.get_task(root_id)
    node.data.result = "explicit completion result"

    changed = await graph.finalize_task(root_id, TaskStatus.CANCELLED, "(任务被取消)")

    assert changed is True
    refreshed = await graph.get_task(root_id)
    assert refreshed.status is TaskStatus.CANCELLED
    assert refreshed.data.result == "explicit completion result"  # 先到先得


@pytest.mark.unit
async def test_finalize_pending_node_allowed():
    """PENDING → CANCELLED 合法（用户终结未起跑的子任务）"""
    graph, root_id = await _make_graph_with_root(TaskStatus.PENDING)

    changed = await graph.finalize_task(root_id, TaskStatus.CANCELLED, "用户终结: 不用跑了")

    assert changed is True
    assert (await graph.get_task(root_id)).status is TaskStatus.CANCELLED


@pytest.mark.unit
async def test_finalize_unknown_node_returns_false():
    graph, _ = await _make_graph_with_root()
    assert await graph.finalize_task("no-such-node", TaskStatus.CANCELLED) is False


@pytest.mark.unit
def test_cancelled_transitions_in_state_machine():
    """⑤ 状态机拆分：非终态可 → CANCELLED；CANCELLED 终态锁死（空集）"""
    rule = StatusTransitionValidationRule()
    for src in (TaskStatus.PENDING, TaskStatus.RUNNING, TaskStatus.PAUSED):
        assert rule.validate({"from_status": src, "to_status": TaskStatus.CANCELLED}).is_valid, src
    # 终态锁死：CANCELLED 不可转出（含转 ABORTED —— 取消竞态不得改写取消语义）
    for dst in (TaskStatus.PENDING, TaskStatus.RUNNING, TaskStatus.ABORTED, TaskStatus.COMPLETED):
        assert not rule.validate({"from_status": TaskStatus.CANCELLED, "to_status": dst}).is_valid, dst
    # ABORTED 保留系统中止语义（可重试恢复）
    assert rule.validate({"from_status": TaskStatus.ABORTED, "to_status": TaskStatus.RUNNING}).is_valid


# ==================== P1b 前置：set_task_result + TaskData SSOT 序列化 ====================


@pytest.mark.unit
async def test_set_task_result_writes_and_no_overwrite():
    """set_task_result：首写成功；已有非空 result → False（先到先得，取消竞态不吞结果）"""
    graph, root_id = await _make_graph_with_root(TaskStatus.RUNNING)

    assert await graph.set_task_result(root_id, "attempt_completion 结果") is True
    assert await graph.set_task_result(root_id, "晚到的预算超限原因") is False

    node = await graph.get_task(root_id)
    assert node.data.result == "attempt_completion 结果"


@pytest.mark.unit
async def test_set_task_result_rejects_missing_node_and_empty():
    graph, root_id = await _make_graph_with_root()
    assert await graph.set_task_result("no-such-node", "x") is False
    assert await graph.set_task_result(root_id, "") is False
    assert await graph.set_task_result(root_id, None) is False  # type: ignore[arg-type]


@pytest.mark.unit
def test_task_data_result_roundtrip_survives_serialization():
    """P1b SSOT：result 此前是未声明动态属性，to_dict 不序列化 → 持久化/重载即丢失。锁定修复。"""
    td = TaskData(
        task_node_id="t-ssot",
        description="demo",
        mode="pdca",
        acceptance_criteria="全部单测通过",
        result="已完成，94 tests green",
        tokens_used=12345,
    )
    restored = TaskData.from_dict(td.to_dict())
    assert restored.result == "已完成，94 tests green"
    assert restored.acceptance_criteria == "全部单测通过"
    assert restored.tokens_used == 12345
    assert restored.started_at is None and restored.completed_at is None


@pytest.mark.unit
def test_task_data_accounting_datetimes_roundtrip():
    """P1b ⑧ 记账字段时间戳 roundtrip + 存量数据（无新 key）兼容"""
    from datetime import timedelta

    from dawei.core.datetime_compat import UTC
    from datetime import datetime as _dt

    td = TaskData(task_node_id="t-acc", description="d", mode="pdca")
    td.started_at = _dt.now(UTC)
    td.completed_at = td.started_at + timedelta(seconds=90)
    restored = TaskData.from_dict(td.to_dict())
    assert restored.started_at == td.started_at
    assert restored.completed_at == td.completed_at

    # 存量持久化数据（写入机制上线前）不含新字段 → from_dict 容错为 None，不抛
    legacy = TaskData.from_dict(
        {"task_node_id": "t-old", "description": "old", "mode": "pdca"},
    )
    assert legacy.result is None
    assert legacy.acceptance_criteria is None
    assert legacy.tokens_used is None
    assert legacy.started_at is None and legacy.completed_at is None
