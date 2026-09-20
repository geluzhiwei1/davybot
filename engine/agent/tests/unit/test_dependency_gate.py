# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""P3 部分屏障（依赖失败闸门）单元测试

覆盖 _execute_subtasks_parallel 的 wave 间依赖闸门：
- 集合内依赖（父节点）FAILED/ABORTED/CANCELLED → 后继节点不起跑，
  以 ABORTED 终结（result 写原因 + metadata 审计键）
- 同 wave 无关节点不受牵连（部分屏障而非全图熔断）
- 依赖 COMPLETED → 正常执行（零行为变化）
- 无 finalize_task 的图 → _update_task_status 回落路径

不依赖 LLM / 网络 / 持久化，_execute_subtask_with_semaphore 以可编程 fake 替换。
"""

from types import SimpleNamespace

import pytest

from dawei.agentic.task_graph_excutor import TaskGraphExecutionEngine
from dawei.entity.task_types import TaskStatus

pytestmark = pytest.mark.unit


class FakeTaskNode:
    def __init__(self, node_id, parent_id=None):
        self.task_node_id = node_id
        self.parent_id = parent_id
        self.status = TaskStatus.PENDING
        self.data = SimpleNamespace(metadata={}, result=None)


class FakeGraph:
    """带 P1a 语义子集 finalize_task 的内存图（has_finalize=False 时剥离）"""

    def __init__(self, tasks, has_finalize=True):
        self.tasks = list(tasks)
        self.has_finalize = has_finalize
        self.status_updates: list[tuple[str, TaskStatus]] = []

    async def get_task(self, node_id):
        return next((t for t in self.tasks if t.task_node_id == node_id), None)

    async def update_task_status(self, node_id, status):
        self.status_updates.append((node_id, status))
        node = await self.get_task(node_id)
        if node is not None:
            node.status = status

    async def finalize_task(self, node_id, status, result=None):
        assert self.has_finalize, "test misuse: finalize_task stripped"
        node = await self.get_task(node_id)
        if node is None or node.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.ABORTED, TaskStatus.CANCELLED):
            return False
        if result:
            node.data.result = result
        await self.update_task_status(node_id, status)
        return True


class FakeEventBus:
    def __init__(self):
        self.events: list[tuple[str, str]] = []

    async def publish(self, event_type, data, task_id="", source=""):
        self.events.append((getattr(event_type, "value", str(event_type)), task_id))


def make_engine(graph):
    ws = SimpleNamespace(task_graph=graph, current_conversation=None)
    engine = TaskGraphExecutionEngine(
        user_workspace=ws,
        message_processor=object(),
        llm_service=object(),
        tool_call_service=object(),
        config=SimpleNamespace(max_parallel_tasks=2),
        agent=SimpleNamespace(event_bus=object()),
    )
    bus = FakeEventBus()
    engine._event_bus = bus
    return engine, bus


def program_semaphore(engine, results: dict[str, TaskStatus]):
    """替换 _execute_subtask_with_semaphore：按 node_id 返回编程状态并记录调用"""
    calls: list[str] = []

    async def fake(node):
        calls.append(node.task_node_id)
        return results[node.task_node_id]

    engine._execute_subtask_with_semaphore = fake  # type: ignore[method-assign]
    return calls


async def test_dependent_skipped_when_dependency_failed():
    """A FAILED → B(parent=A) 不起跑，ABORTED + 审计 metadata + 原因 result"""
    a = FakeTaskNode("A", parent_id="root")
    b = FakeTaskNode("B", parent_id="A")
    graph = FakeGraph([a, b])
    engine, _ = make_engine(graph)
    calls = program_semaphore(engine, {"A": TaskStatus.FAILED, "B": TaskStatus.COMPLETED})

    out = await engine._execute_subtasks_parallel([a, b])

    assert calls == ["A"]  # B 从未起跑
    assert out == [TaskStatus.FAILED, TaskStatus.ABORTED]  # 原顺序聚合
    assert b.status == TaskStatus.ABORTED
    assert engine._execution_status["B"] == TaskStatus.ABORTED
    assert b.data.metadata["skipped_by"] == "dependency_gate"
    assert "dependency A failed" in b.data.metadata["skipped_reason"]
    assert "依赖未通过" in (b.data.result or "")


async def test_sibling_unaffected_by_failure():
    """同 wave 无依赖关系的兄弟节点不受失败牵连（部分屏障，非全图熔断）"""
    a1 = FakeTaskNode("A1", parent_id="root")
    c = FakeTaskNode("C", parent_id="root")
    b = FakeTaskNode("B", parent_id="A1")
    graph = FakeGraph([a1, c, b])
    engine, _ = make_engine(graph)
    calls = program_semaphore(engine, {"A1": TaskStatus.FAILED, "C": TaskStatus.COMPLETED, "B": TaskStatus.COMPLETED})

    out = await engine._execute_subtasks_parallel([a1, c, b])

    assert sorted(calls) == ["A1", "C"]  # C 照常执行
    assert out == [TaskStatus.FAILED, TaskStatus.COMPLETED, TaskStatus.ABORTED]
    assert "skipped_by" not in c.data.metadata  # C 未被闸门触及（fake 不改图状态，仅验证闸门语义）
    assert b.status == TaskStatus.ABORTED


async def test_skip_cascades_to_grandchild():
    """A FAILED → B 跳过（ABORTED）→ G(parent=B) 因依赖 ABORTED 同样跳过"""
    a = FakeTaskNode("A", parent_id="root")
    b = FakeTaskNode("B", parent_id="A")
    g = FakeTaskNode("G", parent_id="B")
    graph = FakeGraph([a, b, g])
    engine, _ = make_engine(graph)
    calls = program_semaphore(engine, {"A": TaskStatus.FAILED, "B": TaskStatus.COMPLETED, "G": TaskStatus.COMPLETED})

    out = await engine._execute_subtasks_parallel([a, b, g])

    assert calls == ["A"]
    assert out == [TaskStatus.FAILED, TaskStatus.ABORTED, TaskStatus.ABORTED]
    assert "dependency B aborted" in g.data.metadata["skipped_reason"]


async def test_completed_dependency_runs_dependent():
    """依赖 COMPLETED → 正常执行（闸门零介入）"""
    a = FakeTaskNode("A", parent_id="root")
    b = FakeTaskNode("B", parent_id="A")
    graph = FakeGraph([a, b])
    engine, _ = make_engine(graph)
    calls = program_semaphore(engine, {"A": TaskStatus.COMPLETED, "B": TaskStatus.COMPLETED})

    out = await engine._execute_subtasks_parallel([a, b])

    assert calls == ["A", "B"]
    assert out == [TaskStatus.COMPLETED, TaskStatus.COMPLETED]
    assert b.status != TaskStatus.ABORTED  # fake 不改图状态；闸门未触碰 B
    assert "skipped_by" not in b.data.metadata


async def test_cancelled_dependency_also_skips():
    """依赖 CANCELLED 同样触发闸门（三态：FAILED/ABORTED/CANCELLED）"""
    a = FakeTaskNode("A", parent_id="root")
    b = FakeTaskNode("B", parent_id="A")
    graph = FakeGraph([a, b])
    engine, _ = make_engine(graph)
    calls = program_semaphore(engine, {"A": TaskStatus.CANCELLED, "B": TaskStatus.COMPLETED})

    out = await engine._execute_subtasks_parallel([a, b])

    assert calls == ["A"]
    assert out == [TaskStatus.CANCELLED, TaskStatus.ABORTED]


async def test_gate_falls_back_to_update_task_status():
    """图无 finalize_task → 回落 _update_task_status（状态/生命周期仍收敛）"""
    a = FakeTaskNode("A", parent_id="root")
    b = FakeTaskNode("B", parent_id="A")
    graph = FakeGraph([a, b], has_finalize=False)
    engine, _ = make_engine(graph)
    # 实例级剥离 finalize_task（getattr 拿到 None → callable False → 回落路径）
    engine._user_workspace.task_graph.finalize_task = None  # type: ignore[assignment]
    calls = program_semaphore(engine, {"A": TaskStatus.FAILED, "B": TaskStatus.COMPLETED})

    out = await engine._execute_subtasks_parallel([a, b])

    assert calls == ["A"]
    assert out == [TaskStatus.FAILED, TaskStatus.ABORTED]
    assert ("B", TaskStatus.ABORTED) in graph.status_updates
    assert engine._execution_status["B"] == TaskStatus.ABORTED
    assert b.data.metadata["skipped_by"] == "dependency_gate"


async def test_gate_emits_subtask_aborted_lifecycle():
    """跳过路径发射 SUBTASK_ABORTED 生命周期事件（UI 可观测）"""
    from dawei.core.events import TaskEventType

    a = FakeTaskNode("A", parent_id="root")
    b = FakeTaskNode("B", parent_id="A")
    graph = FakeGraph([a, b])
    engine, bus = make_engine(graph)
    program_semaphore(engine, {"A": TaskStatus.FAILED, "B": TaskStatus.COMPLETED})

    await engine._execute_subtasks_parallel([a, b])

    aborted_events = [e for e in bus.events if e[0] == TaskEventType.SUBTASK_ABORTED.value]
    assert any(e[1] == "B" for e in aborted_events)
