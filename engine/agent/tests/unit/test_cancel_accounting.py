# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""P2-E 取消回收审计回归测试(docs/子任务组织管理交互方案.md §6 P2 预算回收审计)。

锁定语义:
- executor.reclaim_accounting_on_cancel:无论 CancelledError 落点在 execute_task
  内还是外(重试退避/信号量等待/编排间隙——finally 根本不跑),已消耗 tokens
  必须回收,不允许静默丢失
- 终态节点 → tokens_used/completed_at 补写 TaskData(None 才写,幂等)
- 非终态节点(agent.abort_task 直连路径)→ reclaimed_* 审计键落 metadata
- 引擎 cancel_task_execution:回收先于拆除,回收有写入 → 补偿持久化
  (TaskGraph.emit_graph_updated);回收抛错不阻断取消
- AbortTaskTool/TASK_NODE_STOP 级联:审计键逐节点写(此前仅目标节点)
"""

import logging
from types import SimpleNamespace

import pytest

from dawei.agentic.task_graph_excutor import TaskGraphExecutionEngine
from dawei.agentic.task_node_executor import TaskNodeExecutionEngine
from dawei.entity.task_types import TaskStatus

pytestmark = pytest.mark.unit


# ==================== Fakes ====================


class FakeTaskNode:
    def __init__(self, node_id, status=TaskStatus.PENDING, parent_id=None):
        self.task_node_id = node_id
        self.parent_id = parent_id
        self.status = status
        self.child_ids = []
        self.data = SimpleNamespace(metadata={}, result=None, tokens_used=None, started_at=None, completed_at=None)


def _bare_node_executor(node, tokens=0):
    """跳过 __init__ 的 TaskNodeExecutionEngine(只挂记账所需属性)"""
    ex = TaskNodeExecutionEngine.__new__(TaskNodeExecutionEngine)
    ex.task_node = node
    ex.logger = logging.getLogger("test.cancel-accounting")
    ex._tokens_used = tokens
    ex._loop_started_at = None
    ex._conversation = None
    ex._user_workspace = SimpleNamespace(current_conversation=None)
    return ex


class StubNodeExecutor:
    """引擎 cancel 路径的 executor 替身:记录调用顺序"""

    def __init__(self, tokens=500, reclaim_raises=False, reclaim_returns=True):
        self._tokens_used = tokens
        self.calls: list = []
        self._reclaim_raises = reclaim_raises
        self._reclaim_returns = reclaim_returns

    def reclaim_accounting_on_cancel(self, reason=None):
        self.calls.append(("reclaim", reason))
        if self._reclaim_raises:
            raise RuntimeError("reclaim boom")
        return self._reclaim_returns

    async def cancel_task_execution(self):
        self.calls.append(("cancel",))


class SpyGraph:
    """emit_graph_updated 间谍(补偿持久化触发器)"""

    def __init__(self):
        self.emitted: list[tuple[str, str]] = []

    async def emit_graph_updated(self, node_id, reason="manual"):
        self.emitted.append((node_id, reason))


def make_engine(task_graph):
    ws = SimpleNamespace(task_graph=task_graph)
    return TaskGraphExecutionEngine(
        user_workspace=ws,
        message_processor=object(),
        llm_service=object(),
        tool_call_service=object(),
        config=SimpleNamespace(max_parallel_tasks=2),
        agent=SimpleNamespace(event_bus=object()),
    )


# ==================== reclaim_accounting_on_cancel 单元 ====================


def test_reclaim_terminal_node_writes_tokens_and_completed_at():
    node = FakeTaskNode("sub", status=TaskStatus.CANCELLED)
    ex = _bare_node_executor(node, tokens=1234)

    assert ex.reclaim_accounting_on_cancel(reason="user stop") is True
    assert node.data.tokens_used == 1234
    assert node.data.completed_at is not None
    assert node.data.metadata["reclaimed_tokens"] == 1234
    assert node.data.metadata["reclaimed_reason"] == "user stop"
    assert node.data.metadata["reclaimed_at"]


def test_reclaim_non_terminal_node_metadata_only():
    """agent.abort_task 直连路径(无 finalize)→ 不碰状态字段,审计键落 metadata"""
    node = FakeTaskNode("sub", status=TaskStatus.RUNNING)
    ex = _bare_node_executor(node, tokens=777)

    ex.reclaim_accounting_on_cancel()
    assert node.data.tokens_used is None  # 未终态不写
    assert node.data.completed_at is None
    assert node.data.metadata["reclaimed_tokens"] == 777


def test_reclaim_idempotent_does_not_clobber():
    """二次回收(双通道调用)不覆盖既有值——先到先得"""
    node = FakeTaskNode("sub", status=TaskStatus.CANCELLED)
    ex = _bare_node_executor(node, tokens=100)
    node.data.completed_at = "first-timestamp"

    ex.reclaim_accounting_on_cancel()
    first_tokens = node.data.tokens_used
    first_at = node.data.completed_at
    ex.reclaim_accounting_on_cancel()

    assert node.data.tokens_used == first_tokens
    assert node.data.completed_at == first_at  # 不被第二次覆盖


def test_reclaim_zero_tokens_terminal_writes_completed_at_only():
    node = FakeTaskNode("sub", status=TaskStatus.CANCELLED)
    ex = _bare_node_executor(node, tokens=0)

    assert ex.reclaim_accounting_on_cancel() is True  # reclaimed_at 审计键仍写
    assert node.data.tokens_used is None  # 0 = 未记账语义(None)
    assert node.data.completed_at is not None
    assert "reclaimed_tokens" not in node.data.metadata


def test_reclaim_existing_tokens_used_not_overwritten():
    """"""
    node = FakeTaskNode("sub", status=TaskStatus.FAILED)
    node.data.tokens_used = 42  # _record_accounting_on_finish 已写
    ex = _bare_node_executor(node, tokens=999)

    ex.reclaim_accounting_on_cancel()
    assert node.data.tokens_used == 42  # 既有值优先


# ==================== 引擎 cancel_task_execution 集成 ====================


async def test_engine_cancel_reclaims_before_teardown_and_persists():
    graph = SpyGraph()
    engine = make_engine(graph)
    stub = StubNodeExecutor(tokens=500)
    engine._node_executors["sub"] = stub

    assert await engine.cancel_task_execution("sub") is True

    assert stub.calls[0][0] == "reclaim"  # 回收先于拆除
    assert stub.calls[-1][0] == "cancel"
    assert graph.emitted == [("sub", "cancel_accounting_reclaim")]  # 补偿持久化
    assert "sub" not in engine._node_executors


async def test_engine_cancel_reclaim_failure_does_not_block():
    """回收抛错 → 取消主流程照常(FAST FAIL 日志,不阻断停止执行)"""
    graph = SpyGraph()
    engine = make_engine(graph)
    stub = StubNodeExecutor(reclaim_raises=True)
    engine._node_executors["sub"] = stub

    assert await engine.cancel_task_execution("sub") is True
    assert ("cancel",) in stub.calls
    assert graph.emitted == []  # 无写入 → 无补偿持久化


async def test_engine_cancel_without_reclaim_method_still_works():
    """旧 executor 无 reclaim 方法 → getattr 探测跳过,不崩"""
    graph = SpyGraph()
    engine = make_engine(graph)
    stub = SimpleNamespace(cancel_task_execution=StubNodeExecutor().cancel_task_execution)
    engine._node_executors["sub"] = stub

    assert await engine.cancel_task_execution("sub") is True
    assert graph.emitted == []


async def test_engine_cancel_reclaim_wrote_nothing_no_persist():
    """reclaim 返回 False(无任何写入)→ 不触发补偿持久化"""
    graph = SpyGraph()
    engine = make_engine(graph)
    engine._node_executors["sub"] = StubNodeExecutor(reclaim_returns=False)

    await engine.cancel_task_execution("sub")
    assert graph.emitted == []


# ==================== TaskGraph.emit_graph_updated(补偿持久化原语) ====================


async def test_emit_graph_updated_publishes_task_graph_updated():
    """真实 TaskGraph:emit_graph_updated 只发持久化事件,不改状态/不广播"""
    from dawei.core.events import SimpleEventBus, TaskEventType
    from dawei.task_graph.task_graph import TaskGraph

    captured: list = []

    class RecordingBus(SimpleEventBus):
        async def publish(self, event_type, data, task_id="", source=""):  # type: ignore[override]
            captured.append((event_type, data, task_id, source))

    graph = TaskGraph("graph-reclaim", event_bus=RecordingBus())
    await graph.emit_graph_updated("node-1", reason="cancel_accounting_reclaim")

    assert captured, "TASK_GRAPH_UPDATED 必须发射"
    etype, data, task_id, source = captured[0]
    assert etype is TaskEventType.TASK_GRAPH_UPDATED
    assert data["updated_node_id"] == "node-1"
    assert data["reason"] == "cancel_accounting_reclaim"
    assert source == "task_graph_persistence"


# ==================== 级联审计键逐节点(P2-B 补全) ====================


async def test_abort_task_cascade_writes_audit_on_children():
    """AbortTaskTool 级联:子树每个节点都有 aborted_*(此前仅目标节点)"""
    import json

    from dawei.tools.custom_tools import workflow_tools_fixed as wtf

    class _Graph:
        def __init__(self, nodes):
            self._nodes = nodes

        async def get_task(self, nid):
            return self._nodes.get(nid)

        async def finalize_task(self, nid, status, result=None):
            n = self._nodes[nid]
            if n.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.ABORTED, TaskStatus.CANCELLED):
                return False
            if result and not n.data.result:
                n.data.result = result
            n.status = status
            return True

        async def update_task_status(self, nid, status):
            self._nodes[nid].status = status
            return True

    root = FakeTaskNode("root", status=TaskStatus.RUNNING)
    sub = FakeTaskNode("sub", status=TaskStatus.RUNNING, parent_id="root")
    g1 = FakeTaskNode("g1", status=TaskStatus.PENDING, parent_id="sub")
    sub.child_ids = ["g1"]
    tool = wtf.AbortTaskTool(task_graph=_Graph({"root": root, "sub": sub, "g1": g1}))

    out = json.loads(await tool._run(subtask_id="sub", reason="方向错误"))
    assert out["status"] == "cancelled"
    assert sub.data.metadata["aborted_by"] == "AbortTaskTool"
    assert g1.data.metadata["aborted_by"] == "AbortTaskTool(cascade)"  # 级联子节点也有审计键
    assert "方向错误" in g1.data.metadata["aborted_reason"]
