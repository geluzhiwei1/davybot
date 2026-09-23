# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""P1b ⑦ 广度上限（图谱层 SSOT 强制）+ §8 验收埋点 回归测试。

锁定语义(docs/子任务组织管理交互方案.md §2.2 / §8)：
- 同父活跃(非终态，**含 INTERACTIVE**)子任务数 ≤ max_active_subtasks，
  超限 raise SubtaskBreadthLimitExceededError 且不挂接节点
- 终态(COMPLETED/CANCELLED/...)子节点不占名额
- 锁内原子判定：并发创建竞态下恰好一个成功（兜工具层预检 TOCTOU）
- 重派检测：同父已终结子节点同目标(strip 精确匹配)→ 计数打 prior 标签，不阻断
- 报告埋点：占位条目/正常条目/扫描回退(隔离/共享)分别计数，派生比率正确
- 工具层 fast-path 的 _UNFINISHED 必须含 INTERACTIVE(2026-09-17 漏计修复守卫)
"""

import asyncio
import inspect
from types import SimpleNamespace

import pytest

from dawei.agentic.errors import SubtaskBreadthLimitExceededError
from dawei.agentic.subtask_metrics import SubtaskMetrics, get_metrics
from dawei.agentic.task_graph_excutor import TaskGraphExecutionEngine
from dawei.conversation.conversation import Conversation
from dawei.core.events import SimpleEventBus
from dawei.entity.task_types import TaskStatus
from dawei.task_graph.task_graph import TaskGraph
from dawei.task_graph.task_node_data import TaskContext, TaskData, TaskPriority
from dawei.tools.custom_tools import workflow_tools_fixed as wtf

pytestmark = pytest.mark.unit


# ==================== 真实 TaskGraph 夹具 ====================


async def _make_graph() -> tuple[TaskGraph, str]:
    graph = TaskGraph("graph-breadth", event_bus=SimpleEventBus())
    root = await graph.create_root_task(
        TaskData(
            task_node_id="root-1",
            description="root task for breadth tests",
            mode="orchestrator",
            status=TaskStatus.RUNNING,
            context=TaskContext(user_id="u1", session_id="s1", message_id="m1"),
            todos=[],
            priority=TaskPriority.MEDIUM,
        ),
    )
    assert root is not None
    return graph, "root-1"


def _subtask_data(
    node_id: str,
    description: str = "goal X",
    status: TaskStatus = TaskStatus.PENDING,
    metadata: dict | None = None,
) -> TaskData:
    return TaskData(
        task_node_id=node_id,
        description=description,
        mode="executor",
        status=status,
        context=TaskContext(user_id="u1", session_id="s1", message_id="m1"),
        todos=[],
        priority=TaskPriority.MEDIUM,
        metadata=metadata or {},
    )


@pytest.fixture
def fresh_metrics():
    """隔离指标单例：每测复位"""
    get_metrics().reset()
    yield get_metrics()
    get_metrics().reset()


@pytest.fixture
def gate3(monkeypatch):
    """C9 闸门重划（2026-09-23）：默认 max_active_subtasks 3→8。本文件既有
    用例以 3 为刻画粒度（语义测试不随默认值漂移），显式压回 3。"""
    from dawei.config.settings import get_settings

    monkeypatch.setattr(get_settings().agent_execution, "max_active_subtasks", 3)


# ==================== 广度闸（图谱层）====================


async def test_breadth_limit_enforced_at_graph_level(fresh_metrics, gate3):
    """3 个活跃子任务(压回上限)后，第 4 个创建被拒且不挂接节点"""
    graph, root_id = await _make_graph()
    for i in range(3):
        node = await graph.create_subtask(root_id, _subtask_data(f"sub-{i}"))
        assert node is not None

    with pytest.raises(SubtaskBreadthLimitExceededError) as exc_info:
        await graph.create_subtask(root_id, _subtask_data("sub-overflow"))
    det = exc_info.value.details
    assert det["limit"] == 3
    assert sorted(det["active_subtask_ids"]) == ["sub-0", "sub-1", "sub-2"]
    # 节点未挂接（SSOT 不变：拒绝即无痕）
    assert await graph.get_task("sub-overflow") is None
    assert "sub-overflow" not in graph._nodes[root_id].child_ids
    # 埋点：拒绝计数
    assert fresh_metrics.breadth_rejected_total == 1


async def test_terminal_children_do_not_count(fresh_metrics):
    """终态子节点不占名额：3 个 COMPLETED 后仍可创建"""
    graph, root_id = await _make_graph()
    for i in range(3):
        await graph.create_subtask(root_id, _subtask_data(f"sub-{i}", status=TaskStatus.RUNNING))
        await graph.update_task_status(f"sub-{i}", TaskStatus.COMPLETED)
    node = await graph.create_subtask(root_id, _subtask_data("sub-new"))
    assert node is not None


async def test_cancelled_children_do_not_count(fresh_metrics):
    """CANCELLED 子节点不占名额（终结释放槽位语义）"""
    graph, root_id = await _make_graph()
    for i in range(3):
        await graph.create_subtask(root_id, _subtask_data(f"sub-{i}", status=TaskStatus.RUNNING))
        await graph.update_task_status(f"sub-{i}", TaskStatus.CANCELLED)
    node = await graph.create_subtask(root_id, _subtask_data("sub-new"))
    assert node is not None


async def test_interactive_counts_towards_breadth(fresh_metrics, gate3):
    """回归守卫：INTERACTIVE(追问等待)占用在飞名额——此前两侧闸门均漏计"""
    graph, root_id = await _make_graph()
    await graph.create_subtask(root_id, _subtask_data("sub-a", status=TaskStatus.PENDING))
    await graph.create_subtask(root_id, _subtask_data("sub-b", status=TaskStatus.PENDING))
    # RUNNING → INTERACTIVE（状态机无该转换，直改模拟 interactive 实态）
    await graph.create_subtask(root_id, _subtask_data("sub-c", status=TaskStatus.RUNNING))
    graph._nodes["sub-c"].update_status(TaskStatus.INTERACTIVE)

    with pytest.raises(SubtaskBreadthLimitExceededError):
        await graph.create_subtask(root_id, _subtask_data("sub-overflow"))


async def test_concurrent_creates_exactly_one_wins(fresh_metrics, gate3):
    """锁内原子判定：上限 3、已有 2 个活跃，并发 2 个创建恰好 1 个成功（TOCTOU 兜底）"""
    graph, root_id = await _make_graph()
    await graph.create_subtask(root_id, _subtask_data("sub-0"))
    await graph.create_subtask(root_id, _subtask_data("sub-1"))

    results = await asyncio.gather(
        graph.create_subtask(root_id, _subtask_data("sub-race-a")),
        graph.create_subtask(root_id, _subtask_data("sub-race-b")),
        return_exceptions=True,
    )
    wins = [r for r in results if not isinstance(r, BaseException)]
    rejects = [r for r in results if isinstance(r, SubtaskBreadthLimitExceededError)]
    assert len(wins) == 1
    assert len(rejects) == 1
    assert len(graph._nodes[root_id].child_ids) == 3


async def test_batch_item_bypasses_breadth_gate(fresh_metrics, gate3):
    """C9：metadata.batch_id 在场（new_task_batch 展开项）→ 满 active 也放行；
    同状态下普通子任务仍被拒（合法批量不惩罚，零散堆叠照拦）。"""
    graph, root_id = await _make_graph()
    for i in range(3):
        await graph.create_subtask(root_id, _subtask_data(f"sub-{i}"))

    with pytest.raises(SubtaskBreadthLimitExceededError):
        await graph.create_subtask(root_id, _subtask_data("sub-plain"))

    node = await graph.create_subtask(
        root_id,
        _subtask_data(
            "sub-batch",
            description="batch item goal",
            metadata={"batch_id": "b1", "item_identity": "file-0"},
        ),
    )
    assert node is not None
    assert "sub-batch" in graph._nodes[root_id].child_ids


async def test_redispatch_detected_and_counted_not_blocked(fresh_metrics):
    """同父 CANCELLED 子节点同目标重派 → 计数打 prior 标签，创建仍成功（判别归提示词层）"""
    graph, root_id = await _make_graph()
    await graph.create_subtask(root_id, _subtask_data("sub-1", description="goal X", status=TaskStatus.RUNNING))
    await graph.update_task_status("sub-1", TaskStatus.CANCELLED)

    node = await graph.create_subtask(root_id, _subtask_data("sub-2", description="  goal X  "))
    assert node is not None  # 只计数不阻断
    summary = fresh_metrics.get_summary()
    assert summary["creations_total"] == 2
    assert summary["redispatch_total"] == 1
    assert summary["redispatch_by_prior"].get("cancelled") == 1


# ==================== 工具层 fast-path 守卫 ====================


def test_tool_level_unfinished_set_includes_interactive():
    """_create_subtask 图级 fast-path 的 _UNFINISHED 必须含 INTERACTIVE（源断言守卫）"""
    src = inspect.getsource(wtf.NewTaskTool._create_subtask)
    assert "TaskStatus.INTERACTIVE" in src


def test_new_task_translates_breadth_error():
    """new_task 必须有 SubtaskBreadthLimitExceededError → 可操作 error result 的转译分支"""
    src = inspect.getsource(wtf.NewTaskTool._run)
    assert "SubtaskBreadthLimitExceededError" in src
    assert '"breadth_limit"' in src


# ==================== 报告埋点（镜像 test_subtask_delegation 夹具）====================


class FakeTaskNode:
    def __init__(self, node_id, status=TaskStatus.PENDING, parent_id=None, description="fake task", result=None):
        self.task_node_id = node_id
        self.task_id = node_id
        self.parent_id = parent_id
        self.status = status
        self.child_ids = []
        self.data = SimpleNamespace(
            description=description,
            metadata={},
            result=result,
            context=SimpleNamespace(
                user_id="u1",
                session_id="s1",
                message_id="m1",
                workspace_path="/tmp/ws",
                task_files=[],
                task_images=[],
                to_dict=lambda: {"user_id": "u1"},
            ),
        )


class FakeTaskGraph:
    def __init__(self, tasks=None):
        self.tasks = list(tasks or [])

    async def get_root_task(self):
        roots = [t for t in self.tasks if t.parent_id is None]
        return roots[0] if roots else None

    async def get_all_tasks(self):
        return list(self.tasks)


class FakeWorkspace:
    def __init__(self, task_graph, conversation=None):
        self.task_graph = task_graph
        self.current_conversation = conversation

    async def save_current_conversation(self):
        return True


def make_engine(graph, conversation=None):
    engine = TaskGraphExecutionEngine.__new__(TaskGraphExecutionEngine)
    engine._user_workspace = FakeWorkspace(graph, conversation)
    engine._node_executors = {}
    engine.logger = SimpleNamespace(
        warning=lambda *_a, **_k: None,
        info=lambda *_a, **_k: None,
        exception=lambda *_a, **_k: None,
    )
    return engine


async def test_report_metrics_placeholder_and_normal(fresh_metrics):
    """SSOT 有 result → 普通条目；无 result 无扫描命中 → 占位条目 + 扫描回退(shared)"""
    conv = Conversation(title="t")
    engine = make_engine(FakeTaskGraph(), conversation=conv)

    with_result = FakeTaskNode("sub-ok", parent_id="root", result="真实执行结果")
    no_result = FakeTaskNode("sub-bad", parent_id="root", result=None)

    await engine._inject_subtask_summaries(
        [with_result, no_result],
        [TaskStatus.COMPLETED, TaskStatus.FAILED],
        msg_snapshot=0,
    )
    summary = fresh_metrics.get_summary()
    assert summary["reports_total"] == 2
    assert summary["reports_placeholder"] == 1
    assert summary["placeholder_rate"] == 0.5
    assert summary["scan_fallback_total"] == 1  # 仅无 result 的节点走回退
    assert summary["scan_fallback_shared"] == 1  # 无隔离会话 → 共享对话路径


async def test_report_metrics_scan_fallback_isolated(fresh_metrics):
    """无 result + 隔离会话存在 → 回退计 isolated 侧"""
    conv = Conversation(title="t")
    engine = make_engine(FakeTaskGraph(), conversation=conv)
    # 提供隔离会话（executor 持有 _conversation）
    iso_holder = SimpleNamespace(_conversation=Conversation(title="iso"))
    engine._node_executors["sub-iso"] = iso_holder

    sub = FakeTaskNode("sub-iso", parent_id="root", result=None)
    await engine._inject_subtask_summaries([sub], [TaskStatus.COMPLETED], msg_snapshot=0)
    summary = fresh_metrics.get_summary()
    assert summary["scan_fallback_isolated"] == 1
    assert summary["scan_fallback_shared"] == 0


# ==================== 指标模块本体 ====================


def test_metrics_record_and_rates():
    m = SubtaskMetrics()
    for _ in range(3):
        m.record_creation()
    m.record_creation()
    m.record_breadth_rejected()
    for ok in (True, True, True, False):
        m.record_report(placeholder=not ok)
    m.record_scan_fallback(isolated=True)
    m.record_scan_fallback(isolated=False)
    m.record_redispatch("cancelled")
    m.record_redispatch("completed")

    s = m.get_summary()
    assert s["creations_total"] == 4
    assert s["breadth_rejected_total"] == 1
    assert s["reports_total"] == 4
    assert s["reports_placeholder"] == 1
    assert s["placeholder_rate"] == 0.25
    assert s["scan_fallback_total"] == 2
    assert s["scan_fallback_rate"] == 0.5
    assert s["redispatch_total"] == 2
    assert s["redispatch_by_prior"] == {"cancelled": 1, "completed": 1}
    assert s["redispatch_rate"] == 0.5

    m.reset()
    assert m.get_summary()["reports_total"] == 0


def test_metrics_singleton():
    assert get_metrics() is get_metrics()
