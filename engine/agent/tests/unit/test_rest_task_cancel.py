# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""P2-A REST 对齐端点回归测试:POST /{workspace_id}/tasks/{task_id}/cancel。

锁定语义(docs/子任务组织管理交互方案.md §6 REST 对齐):
- 复用 AbortTaskTool 级联语义(CANCELLED 子树级联 + 审计 metadata),
  与 WS 侧 TASK_NODE_STOP / subtasks/abort 三通道同一终结语义
- 根任务拒绝(AbortTaskTool 契约)→ success=False 如实透传(FAST FAIL)
- 未知任务 → 404
- 终态任务 → AbortTaskTool 幂等语义(不报错)
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dawei.api.workspaces import graphs as graphs_mod
from dawei.api.workspaces.graphs import router
from dawei.core.events import SimpleEventBus
from dawei.entity.task_types import TaskStatus
from dawei.task_graph.task_graph import TaskGraph
from dawei.task_graph.task_node_data import TaskContext, TaskData, TaskPriority


async def _make_graph() -> tuple[TaskGraph, str, str]:
    """root(RUNNING) + child(RUNNING) 真实图谱"""
    graph = TaskGraph("graph-cancel", event_bus=SimpleEventBus())
    root = await graph.create_root_task(
        TaskData(
            task_node_id="root-1",
            description="root task",
            mode="orchestrator",
            status=TaskStatus.RUNNING,
            context=TaskContext(user_id="u1", session_id="s1", message_id="m1"),
            todos=[],
            priority=TaskPriority.MEDIUM,
        ),
    )
    child = await graph.create_subtask(
        root.task_node_id,
        TaskData(
            task_node_id="child-1",
            description="child task",
            mode="task",
            status=TaskStatus.RUNNING,
            context=TaskContext(user_id="u1", session_id="s1", message_id="m1"),
            todos=[],
            priority=TaskPriority.MEDIUM,
        ),
    )
    return graph, root.task_node_id, child.task_node_id


@pytest.fixture
def client(monkeypatch):
    """TestClient + 工作区替身(真实 TaskGraph)注入 graphs 路由"""
    app = FastAPI()
    app.include_router(router)

    holder: dict = {}

    class _FakeWorkspace:
        task_graph = None
        absolute_path = None

    async def _fake_get_user_workspace(workspace_id, request):  # noqa: ARG001
        ws = _FakeWorkspace()
        ws.task_graph = holder["graph"]
        return ws

    async def _fake_ensure(ws, request=None):  # noqa: ARG001
        return None

    monkeypatch.setattr(graphs_mod, "get_user_workspace", _fake_get_user_workspace, raising=False)
    monkeypatch.setattr(graphs_mod, "_ensure_workspace_initialized", _fake_ensure, raising=False)
    holder["client"] = TestClient(app)
    return holder


@pytest.mark.unit
async def test_cancel_task_cascades_child_subtree(client):
    graph, root_id, child_id = await _make_graph()
    client["graph"] = graph

    resp = client["client"].post(f"/ws-1/tasks/{child_id}/cancel", json={"reason": "方向错误"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert (await graph.get_task(child_id)).status is TaskStatus.CANCELLED
    # 审计 metadata(AbortTaskTool 写 aborted_* 键)
    child_meta = (await graph.get_task(child_id)).data.metadata
    assert child_meta.get("aborted_reason") == "方向错误"
    # 兄弟/父节点不受波及
    assert (await graph.get_task(root_id)).status is TaskStatus.RUNNING


@pytest.mark.unit
async def test_cancel_root_refused_fast_fail(client):
    """根任务拒绝(AbortTaskTool 契约),success=False 如实透传"""
    graph, root_id, _ = await _make_graph()
    client["graph"] = graph

    resp = client["client"].post(f"/ws-1/tasks/{root_id}/cancel", json={"reason": "x"})

    assert resp.status_code == 200
    assert resp.json()["success"] is False
    assert (await graph.get_task(root_id)).status is TaskStatus.RUNNING  # 状态不变


@pytest.mark.unit
async def test_cancel_unknown_task_404(client):
    graph, _, _ = await _make_graph()
    client["graph"] = graph

    resp = client["client"].post("/ws-1/tasks/no-such-task/cancel")

    assert resp.status_code == 404


@pytest.mark.unit
async def test_cancel_terminal_task_idempotent(client):
    """已 CANCELLED → 幂等成功回执(镜像 AGENT_STOP 语义)"""
    graph, _, child_id = await _make_graph()
    await graph.finalize_task(child_id, TaskStatus.CANCELLED, "第一次终结")
    client["graph"] = graph

    resp = client["client"].post(f"/ws-1/tasks/{child_id}/cancel")

    assert resp.status_code == 200
    node = await graph.get_task(child_id)
    assert node.status is TaskStatus.CANCELLED
    assert node.data.result == "第一次终结"  # 先到先得,不被改写
