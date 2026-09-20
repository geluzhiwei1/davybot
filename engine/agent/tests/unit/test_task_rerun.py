# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""P2-D 重跑语义 + P2-C 终态广播携带 result 回归测试。

锁定语义(docs/子任务组织管理交互方案.md §6 重跑 / 预算耗尽 UX):
- 双验证表同步:StateValidator.VALID_TRANSITIONS == StatusTransitionValidationRule.valid_transitions
- COMPLETED/FAILED → PENDING 放开(经 reset_task_for_rerun 显式重跑入口)
- CANCELLED → PENDING 仍锁死(用户终结语义先到先得,不变量 6)
- RUNNING/WAITING_FOR_TOOL → PENDING 放开(崩溃残留对账,此前被外层 except 吞掉)
- reset_task_for_rerun:stash prev_* 到 metadata + 清空 result/tokens/time +
  retry 清零 + 状态机 PENDING;之后 set_task_result 可再写(先到先得冲突消解)
- RUNNING/CANCELLED 节点拒绝重跑
- 终态 WS 广播(Complete 分支)携带 data.result;aborted 也走 Complete 分支
"""

from unittest.mock import AsyncMock

import pytest

from dawei.core.events import SimpleEventBus
from dawei.entity.task_types import TaskStatus
from dawei.task_graph.managers.state_manager import StateValidator
from dawei.task_graph.task_graph import TaskGraph
from dawei.task_graph.task_node_data import TaskContext, TaskData, TaskPriority
from dawei.task_graph.task_validator import StatusTransitionValidationRule


async def _make_graph_with_root(status: TaskStatus = TaskStatus.COMPLETED) -> tuple[TaskGraph, str]:
    graph = TaskGraph("graph-rerun", event_bus=SimpleEventBus())
    root = await graph.create_root_task(
        TaskData(
            task_node_id="root-1",
            description="root task for rerun tests",
            mode="orchestrator",
            status=status,
            context=TaskContext(user_id="u1", session_id="s1", message_id="m1"),
            todos=[],
            priority=TaskPriority.MEDIUM,
        ),
    )
    assert root is not None
    return graph, "root-1"


# ==================== 双验证表同步(P2-D 前置) ====================


@pytest.mark.unit
def test_dual_validator_tables_in_sync():
    """StateValidator 与 StatusTransitionValidationRule 两张表必须逐项一致(历史镜像债)"""
    rule = StatusTransitionValidationRule()
    assert StateValidator.VALID_TRANSITIONS == rule.valid_transitions


@pytest.mark.unit
def test_rerun_transitions_opened_and_cancelled_locked():
    """P2-D 转换放开/锁死矩阵"""
    rule = StatusTransitionValidationRule()
    # 放开:显式重跑入口
    assert rule.validate({"from_status": TaskStatus.COMPLETED, "to_status": TaskStatus.PENDING}).is_valid
    assert rule.validate({"from_status": TaskStatus.FAILED, "to_status": TaskStatus.PENDING}).is_valid
    # 崩溃残留对账
    assert rule.validate({"from_status": TaskStatus.RUNNING, "to_status": TaskStatus.PENDING}).is_valid
    assert rule.validate({"from_status": TaskStatus.WAITING_FOR_TOOL, "to_status": TaskStatus.PENDING}).is_valid
    # 锁死:用户终结语义不可改写(不变量 6)
    assert not rule.validate({"from_status": TaskStatus.CANCELLED, "to_status": TaskStatus.PENDING}).is_valid
    # 常规执行路径仍不可从终态直接转运行(重跑必须经 PENDING)
    assert not rule.validate({"from_status": TaskStatus.COMPLETED, "to_status": TaskStatus.RUNNING}).is_valid
    assert not rule.validate({"from_status": TaskStatus.FAILED, "to_status": TaskStatus.RUNNING}).is_valid


# ==================== reset_task_for_rerun(P2-D 核心) ====================


@pytest.mark.unit
async def test_reset_completed_node_stashes_and_clears():
    """COMPLETED + 已有 result → stash prev_* → 清空 → PENDING;之后可再写 result"""
    graph, root_id = await _make_graph_with_root(TaskStatus.RUNNING)
    await graph.finalize_task(root_id, TaskStatus.COMPLETED, "第一次执行结果")
    node = await graph.get_task(root_id)
    node.data.tokens_used = 12345
    node.data.retry_count = 2

    assert await graph.reset_task_for_rerun(root_id, reason="用户要求重跑") is True

    refreshed = await graph.get_task(root_id)
    assert refreshed.status is TaskStatus.PENDING
    assert refreshed.data.result is None  # 先到先得的锁由重置原语显式解开
    assert refreshed.data.tokens_used is None
    assert refreshed.data.retry_count == 0
    meta = refreshed.data.metadata
    assert meta["prev_result"] == "第一次执行结果"
    assert meta["prev_tokens_used"] == 12345
    assert meta["rerun_reason"] == "用户要求重跑"

    # 冲突消解:第二次执行的 result 可正常写入(此前被第一次残值吞掉)
    assert await graph.set_task_result(root_id, "第二次执行结果") is True


@pytest.mark.unit
async def test_reset_failed_node_allowed():
    """FAILED(如预算耗尽)也可重跑——用户提额/修因后原位再来"""
    graph, root_id = await _make_graph_with_root(TaskStatus.RUNNING)
    await graph.finalize_task(root_id, TaskStatus.FAILED, "[token_budget_exceeded] used 100 tokens")

    assert await graph.reset_task_for_rerun(root_id) is True
    refreshed = await graph.get_task(root_id)
    assert refreshed.status is TaskStatus.PENDING
    assert refreshed.data.metadata["prev_result"].startswith("[token_budget_exceeded]")


@pytest.mark.unit
async def test_reset_rejects_running_and_cancelled():
    """RUNNING(先终结再重跑)/ CANCELLED(用户语义不复活)拒绝"""
    graph, root_id = await _make_graph_with_root(TaskStatus.RUNNING)

    assert await graph.reset_task_for_rerun(root_id) is False  # RUNNING
    assert (await graph.get_task(root_id)).status is TaskStatus.RUNNING

    await graph.finalize_task(root_id, TaskStatus.CANCELLED, "用户终结")
    assert await graph.reset_task_for_rerun(root_id) is False  # CANCELLED 锁死
    assert (await graph.get_task(root_id)).status is TaskStatus.CANCELLED


@pytest.mark.unit
async def test_reset_unknown_node_returns_false():
    graph, _ = await _make_graph_with_root()
    assert await graph.reset_task_for_rerun("no-such-node") is False


# ==================== 终态广播携带 result(P2-C) ====================


@pytest.fixture
def broadcast_capture(monkeypatch):
    """截获 update_task_status 的 WS 广播(替身 websocket_server)"""
    import dawei.websocket.ws_server as ws_mod

    sent: list = []
    fake = type("FakeServer", (), {})()
    fake.websocket_manager = type("FakeWM", (), {})()
    fake.websocket_manager.broadcast = AsyncMock(side_effect=lambda msg, **kw: sent.append(msg))
    monkeypatch.setattr(ws_mod, "websocket_server", fake, raising=False)
    return sent


@pytest.mark.unit
async def test_complete_broadcast_carries_result(broadcast_capture):
    """终态 Complete 广播回填 data.result(预算耗尽原因前端可见,不再恒 None)"""
    graph, root_id = await _make_graph_with_root(TaskStatus.RUNNING)

    await graph.finalize_task(root_id, TaskStatus.FAILED, "[token_budget_exceeded] used 100 tokens")

    completes = [m for m in broadcast_capture if type(m).__name__ == "TaskNodeCompleteMessage"]
    assert completes, "终态必须发 TaskNodeCompleteMessage"
    assert completes[-1].result == "[token_budget_exceeded] used 100 tokens"


@pytest.mark.unit
async def test_aborted_broadcast_goes_to_complete_branch(broadcast_capture):
    """aborted 纳入 Complete 分支(此前落 Progress 分支,前端无终态卡片)"""
    graph, root_id = await _make_graph_with_root(TaskStatus.RUNNING)

    await graph.finalize_task(root_id, TaskStatus.ABORTED, "(父任务取消)")

    completes = [m for m in broadcast_capture if type(m).__name__ == "TaskNodeCompleteMessage"]
    assert any(m.metadata.get("new_status") == "aborted" for m in completes), "aborted 终态必须走 Complete 分支"
