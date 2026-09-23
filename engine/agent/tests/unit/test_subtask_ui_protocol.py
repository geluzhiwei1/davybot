# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""第五批：子任务 UI 协议层（§6.2，服务前端可视化）单测

覆盖：
- WS 消息类型 subtask_lifecycle（SubtaskLifecycleMessage 序列化 / validator 注册 / 包导出）
- emit_subtask_lifecycle → websocket broadcast 桥（fire-and-forget；workspace_id 显式 > 活动引擎解析）
- REST /api/workspaces/{ws}/subtasks（树 bootstrap 字段）
- REST /api/workspaces/{ws}/subtasks/{id}/conversation（会话历史 / 降级 / 404）
- REST /api/workspaces/{ws}/agents/profiles（内置 profile）
- REST steer / abort 端点（复用 MessageTaskTool / AbortTaskTool）
- new_task / run_task 工具结果增强（conversation_id / agent 字段）
"""

import json
from types import SimpleNamespace

import pytest

from dawei.entity.task_types import TaskStatus

pytestmark = pytest.mark.unit

# ==================== Fakes ====================


class FakeBus:
    def __init__(self):
        self.published = []

    async def publish(self, event_type, data, task_id="", source=""):
        self.published.append((event_type, data))


class FakeBroadcastManager:
    def __init__(self):
        self.calls = []

    async def broadcast(self, message, exclude_sessions=None, workspace_id=None):
        self.calls.append((message, workspace_id))


class FakeTaskNode:
    def __init__(self, node_id, status=TaskStatus.PENDING, parent_id=None, description="fake task", child_ids=None):
        self.task_node_id = node_id
        self.task_id = node_id
        self.parent_id = parent_id
        self.status = status
        self.child_ids = list(child_ids or [])
        self.data = SimpleNamespace(
            description=description,
            metadata={},
            mode="pdca",
            depth=0,
            conversation_id=None,
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

    def update_status(self, status):
        self.status = status


class FakeTaskGraph:
    def __init__(self, tasks=None):
        self.tasks = list(tasks or [])
        self.status_updates = []
        self.created_subtasks = []

    async def get_root_task(self):
        roots = [t for t in self.tasks if t.parent_id is None]
        return roots[0] if roots else None

    async def get_all_tasks(self):
        return list(self.tasks)

    async def update_task_status(self, node_id, status):
        self.status_updates.append((node_id, status))
        for t in self.tasks:
            if t.task_node_id == node_id:
                t.status = status

    async def create_subtask(self, parent_id, subtask_data):
        self.created_subtasks.append((parent_id, subtask_data))
        return subtask_data

    async def finalize_task(self, node_id, status, result=None):
        """真实 TaskGraph.finalize_task 语义子集（P1a：终态幂等 + result 先行写入）"""
        node = await self.get_task(node_id)
        if node is None:
            return False
        if node.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.ABORTED, TaskStatus.CANCELLED):
            return False
        if result and not getattr(node.data, "result", None):
            node.data.result = result
        await self.update_task_status(node_id, status)
        return True

    async def reset_task_for_rerun(self, node_id, reason=None):
        """真实 TaskGraph.reset_task_for_rerun 语义子集（P2-D：stash → clear → PENDING）"""
        node = await self.get_task(node_id)
        if node is None:
            return False
        if node.status not in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.ABORTED):
            return False
        data = node.data
        if getattr(data, "result", None):
            data.metadata["prev_result"] = data.result
        if getattr(data, "tokens_used", None) is not None:
            data.metadata["prev_tokens_used"] = data.tokens_used
        data.metadata["rerun_reason"] = reason or ""
        data.result = None
        data.tokens_used = None
        data.completed_at = None
        data.started_at = None
        await self.update_task_status(node_id, TaskStatus.PENDING)
        return True

    async def get_task(self, node_id):
        for t in self.tasks:
            if t.task_node_id == node_id:
                return t
        return None


class FakeApiWorkspace:
    """REST 路由测试用 workspace 替身（不触发真实 initialize）"""

    def __init__(self, task_graph=None, conversations=None, workspace_path="/tmp/fake-ws"):
        self.task_graph = task_graph
        self.absolute_path = workspace_path
        self.workspace_path = workspace_path
        conv_map = conversations or {}
        self.conversation_history_manager = SimpleNamespace(
            get_by_id=lambda cid: _async_return(conv_map.get(cid)),
        )

    def is_initialized(self):
        return True

    async def initialize(self):  # 万一被调用也不炸
        return None


async def _async_return(value):
    return value


# ==================== protocol: SubtaskLifecycleMessage ====================


def test_message_type_enum_has_subtask_lifecycle():
    from dawei.websocket.protocol import MessageType

    assert MessageType.SUBTASK_LIFECYCLE.value == "subtask_lifecycle"


def test_subtask_lifecycle_message_roundtrip():
    from dawei.websocket.protocol import SubtaskLifecycleMessage

    msg = SubtaskLifecycleMessage(
        session_id="",
        task_id="root",
        subtask_id="sub1",
        event="created",
        status="pending",
        parent_id="root",
        conversation_id="conv-1",
        agent="worker",
        depth=1,
        metadata={"reason": ""},
    )
    d = msg.to_dict()
    assert d["type"] == "subtask_lifecycle"
    assert d["subtask_id"] == "sub1"
    assert d["event"] == "created"
    assert d["conversation_id"] == "conv-1"
    assert d["agent"] == "worker"

    m2 = SubtaskLifecycleMessage.from_dict(d)
    assert m2.subtask_id == "sub1"
    assert m2.event == "created"
    assert m2.agent == "worker"


def test_subtask_lifecycle_registered_in_validator_map():
    from dawei.websocket.protocol import MessageValidator, SubtaskLifecycleMessage

    assert MessageValidator.get_message_class("subtask_lifecycle") is SubtaskLifecycleMessage


def test_websocket_package_reexports_subtask_message():
    import dawei.websocket as wspkg
    from dawei.websocket.protocol import SubtaskLifecycleMessage

    assert wspkg.SubtaskLifecycleMessage is SubtaskLifecycleMessage


# ==================== bridge: emit_subtask_lifecycle → WS broadcast ====================


async def test_emit_broadcasts_with_explicit_workspace_id(monkeypatch):
    import dawei.websocket.ws_server as wss

    mgr = FakeBroadcastManager()
    monkeypatch.setattr(wss, "websocket_server", SimpleNamespace(websocket_manager=mgr))

    from dawei.agentic.subtask_events import emit_subtask_lifecycle

    bus = FakeBus()
    await emit_subtask_lifecycle("created", task_node_id="sub1", parent_id="root", status="pending", event_bus=bus, workspace_id="ws-1")

    assert len(bus.published) == 1  # bus 事件照发
    assert len(mgr.calls) == 1  # 广播恰好一次
    msg, ws_id = mgr.calls[0]
    assert ws_id == "ws-1"
    assert msg.subtask_id == "sub1"
    assert msg.event == "created"
    assert msg.parent_id == "root"


async def test_emit_broadcast_workspace_id_resolved_from_engine(monkeypatch):
    """未显式传 workspace_id 时，从活动引擎的 _user_workspace 解析"""
    import dawei.tools.custom_tools.workflow_tools_fixed as wtf_mod
    import dawei.websocket.ws_server as wss

    mgr = FakeBroadcastManager()
    monkeypatch.setattr(wss, "websocket_server", SimpleNamespace(websocket_manager=mgr))

    fake_engine = SimpleNamespace(
        _event_bus=FakeBus(),
        _user_workspace=SimpleNamespace(workspace_id="ws-from-engine"),
    )
    monkeypatch.setattr(wtf_mod, "get_active_execution_engine", lambda: fake_engine)

    from dawei.agentic.subtask_events import emit_subtask_lifecycle

    await emit_subtask_lifecycle("started", task_node_id="sub1", status="running")

    assert len(mgr.calls) == 1
    assert mgr.calls[0][1] == "ws-from-engine"


async def test_emit_broadcast_skipped_without_ws_server(monkeypatch):
    import dawei.websocket.ws_server as wss

    monkeypatch.setattr(wss, "websocket_server", None)

    from dawei.agentic.subtask_events import emit_subtask_lifecycle

    bus = FakeBus()
    await emit_subtask_lifecycle("failed", task_node_id="sub1", status="failed", event_bus=bus, workspace_id="ws-1")
    assert len(bus.published) == 1  # 不抛异常，bus 事件照发


async def test_emit_broadcast_failure_is_swallowed(monkeypatch):
    import dawei.websocket.ws_server as wss

    class Boom:
        async def broadcast(self, *a, **k):
            raise RuntimeError("boom")

    monkeypatch.setattr(wss, "websocket_server", SimpleNamespace(websocket_manager=Boom()))

    from dawei.agentic.subtask_events import emit_subtask_lifecycle

    bus = FakeBus()
    await emit_subtask_lifecycle("aborted", task_node_id="sub1", status="aborted", event_bus=bus, workspace_id="ws-1")
    assert len(bus.published) == 1  # 广播失败不影响 bus 发布


# ==================== REST: subtasks router ====================


def _make_client(monkeypatch, workspace):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import dawei.api.workspaces.subtasks as subtasks_mod
    from dawei.api.workspaces.subtasks import router as subtasks_router

    async def _fake_get_user_workspace(workspace_id, request):
        return workspace

    monkeypatch.setattr(subtasks_mod, "get_user_workspace", _fake_get_user_workspace)

    app = FastAPI()
    app.include_router(subtasks_router, prefix="/api/workspaces")
    return TestClient(app)


def _sample_graph():
    root = FakeTaskNode("root", status=TaskStatus.RUNNING)
    sub = FakeTaskNode("sub1", status=TaskStatus.RUNNING, parent_id="root")
    sub.data.conversation_id = "conv-1"
    sub.data.metadata["agent"] = "worker"
    sub.data.depth = 1
    shared = FakeTaskNode("sub2", status=TaskStatus.PENDING, parent_id="root")
    shared.data.depth = 1
    return FakeTaskGraph([root, sub, shared])


def test_list_subtasks_returns_tree_fields(monkeypatch):
    graph = _sample_graph()
    client = _make_client(monkeypatch, FakeApiWorkspace(task_graph=graph))

    resp = client.get("/api/workspaces/ws1/subtasks")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["total"] == 2  # 根任务排除
    ids = {s["task_id"] for s in body["subtasks"]}
    assert ids == {"sub1", "sub2"}
    sub1 = next(s for s in body["subtasks"] if s["task_id"] == "sub1")
    assert sub1["parent_id"] == "root"
    assert sub1["status"] == "running"
    assert sub1["agent"] == "worker"
    assert sub1["depth"] == 1
    assert sub1["conversation_id"] == "conv-1"


def test_subtask_conversation_found(monkeypatch):
    graph = _sample_graph()
    conv_dict = {"id": "conv-1", "title": "subtask-sub1", "messages": [{"role": "user", "content": "hi"}]}
    conv = SimpleNamespace(to_dict=lambda: conv_dict)
    client = _make_client(monkeypatch, FakeApiWorkspace(task_graph=graph, conversations={"conv-1": conv}))

    resp = client.get("/api/workspaces/ws1/subtasks/sub1/conversation")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["degraded"] is False
    assert body["conversation_id"] == "conv-1"
    assert body["conversation"]["id"] == "conv-1"
    assert body["conversation"]["messages"][0]["content"] == "hi"


def test_subtask_conversation_degrades_when_shared(monkeypatch):
    """flag off（无 conversation_id）→ 降级响应而非报错"""
    graph = _sample_graph()
    client = _make_client(monkeypatch, FakeApiWorkspace(task_graph=graph))

    resp = client.get("/api/workspaces/ws1/subtasks/sub2/conversation")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["degraded"] is True
    assert body["reason"] == "shared_conversation"
    assert body["conversation"] is None


def test_subtask_conversation_degrades_when_missing_on_disk(monkeypatch):
    graph = _sample_graph()
    client = _make_client(monkeypatch, FakeApiWorkspace(task_graph=graph, conversations={}))

    resp = client.get("/api/workspaces/ws1/subtasks/sub1/conversation")
    assert resp.status_code == 200
    body = resp.json()
    assert body["degraded"] is True
    assert body["reason"] == "conversation_not_found"


def test_subtask_conversation_404_for_unknown_task(monkeypatch):
    graph = _sample_graph()
    client = _make_client(monkeypatch, FakeApiWorkspace(task_graph=graph))

    resp = client.get("/api/workspaces/ws1/subtasks/nope/conversation")
    assert resp.status_code == 404


def test_agents_profiles_lists_builtins(monkeypatch):
    client = _make_client(monkeypatch, FakeApiWorkspace(task_graph=_sample_graph()))

    resp = client.get("/api/workspaces/ws1/agents/profiles")
    assert resp.status_code == 200
    body = resp.json()
    names = {p["agent"] for p in body["profiles"]}
    assert {"default", "worker", "explorer"} <= names
    explorer = next(p for p in body["profiles"] if p["agent"] == "explorer")
    assert explorer["builtin"] is True
    assert explorer["sandbox_mode"] == "read-only"


def test_steer_endpoint_pending_subtask(monkeypatch):
    graph = _sample_graph()
    client = _make_client(monkeypatch, FakeApiWorkspace(task_graph=graph))

    resp = client.post("/api/workspaces/ws1/subtasks/sub2/steer", json={"message": "focus on X"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["result"]["status"] == "steered"
    assert body["result"]["delivery"] == "description"


def test_abort_endpoint_aborts_subtree(monkeypatch):
    """P1a：abort 端点 → CANCELLED（主动取消语义，区别于系统中止 ABORTED）"""
    graph = _sample_graph()
    client = _make_client(monkeypatch, FakeApiWorkspace(task_graph=graph))

    resp = client.post("/api/workspaces/ws1/subtasks/sub1/abort", json={"reason": "user cancelled"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["result"]["status"] == "cancelled"
    assert body["result"]["cancelled_count"] == 1
    assert body["result"]["cancelled_ids"] == ["sub1"]
    assert graph.status_updates and graph.status_updates[0] == ("sub1", TaskStatus.CANCELLED)
    # 不变量 3：status+result 同笔写（finalize_task 主路径）
    sub1 = graph.tasks[1]
    assert sub1.status is TaskStatus.CANCELLED
    assert "user cancelled" in sub1.data.result


# ==================== REST: rerun 端点（P2-D 原位重跑）====================


def test_rerun_endpoint_resets_failed_subtask(monkeypatch):
    """FAILED → 200：PENDING + 旧 result stash 到 prev_* + 审计键 + result 清空"""
    failed = FakeTaskNode("subf", status=TaskStatus.FAILED, parent_id="root")
    failed.data.result = "boom: LLM 400"
    failed.data.tokens_used = 1234
    graph = FakeTaskGraph([FakeTaskNode("root", status=TaskStatus.COMPLETED), failed])
    client = _make_client(monkeypatch, FakeApiWorkspace(task_graph=graph))

    resp = client.post("/api/workspaces/ws1/subtasks/subf/rerun", json={"reason": "换个策略重试"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["status"] == "pending"
    assert body["steer"] is None
    assert failed.status is TaskStatus.PENDING
    assert ("subf", TaskStatus.PENDING) in graph.status_updates
    # P2-D：stash 旧值（审计）+ 清空（防先到先得残值吞掉第二次执行结果）
    assert failed.data.metadata["prev_result"] == "boom: LLM 400"
    assert failed.data.metadata["prev_tokens_used"] == 1234
    assert failed.data.metadata["rerun_reason"] == "换个策略重试"
    assert failed.data.result is None


def test_rerun_endpoint_with_message_injects_description(monkeypatch):
    """带 message：重置后经 MessageTaskTool PENDING 路径注入描述（起跑时可见）"""
    done = FakeTaskNode("subd", status=TaskStatus.COMPLETED, parent_id="root")
    done.data.result = "old"
    graph = FakeTaskGraph([FakeTaskNode("root", status=TaskStatus.COMPLETED), done])
    client = _make_client(monkeypatch, FakeApiWorkspace(task_graph=graph))

    resp = client.post("/api/workspaces/ws1/subtasks/subd/rerun", json={"message": "只重跑检索步骤"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["steer"]["status"] == "steered"
    assert body["steer"]["delivery"] == "description"
    assert "[steer] 只重跑检索步骤" in done.data.description
    # message 未显式给 reason → 自动派生审计原因
    assert done.data.metadata["rerun_reason"].startswith("user rerun:")


def test_rerun_endpoint_running_conflict_409(monkeypatch):
    """RUNNING → 409：运行中重跑 = 先终结再重跑（FAST FAIL 不包装假成功）"""
    graph = _sample_graph()  # sub1 RUNNING
    client = _make_client(monkeypatch, FakeApiWorkspace(task_graph=graph))

    resp = client.post("/api/workspaces/ws1/subtasks/sub1/rerun")
    assert resp.status_code == 409
    assert "running" in resp.json()["detail"]


def test_rerun_endpoint_cancelled_stays_cancelled(monkeypatch):
    """CANCELLED → 409：用户取消先到先得，不隐式复活"""
    cancelled = FakeTaskNode("subc", status=TaskStatus.CANCELLED, parent_id="root")
    graph = FakeTaskGraph([FakeTaskNode("root", status=TaskStatus.COMPLETED), cancelled])
    client = _make_client(monkeypatch, FakeApiWorkspace(task_graph=graph))

    resp = client.post("/api/workspaces/ws1/subtasks/subc/rerun")
    assert resp.status_code == 409
    assert cancelled.status is TaskStatus.CANCELLED


def test_rerun_endpoint_root_refused_400(monkeypatch):
    """根任务 → 400（与 message_task 同契约）"""
    graph = _sample_graph()
    client = _make_client(monkeypatch, FakeApiWorkspace(task_graph=graph))

    resp = client.post("/api/workspaces/ws1/subtasks/root/rerun")
    assert resp.status_code == 400


def test_rerun_endpoint_unknown_task_404(monkeypatch):
    graph = _sample_graph()
    client = _make_client(monkeypatch, FakeApiWorkspace(task_graph=graph))

    resp = client.post("/api/workspaces/ws1/subtasks/nope/rerun")
    assert resp.status_code == 404


# ==================== tool_execution 结果增强（§6.2 第 6 行） ====================


async def test_new_task_result_carries_agent_and_conversation_fields(monkeypatch):
    from dawei.tools.custom_tools import workflow_tools_fixed as wtf

    graph = FakeTaskGraph([FakeTaskNode("root", status=TaskStatus.RUNNING)])
    tool = wtf.NewTaskTool(task_graph=graph, workspace_root=None)
    monkeypatch.setattr(tool, "_load_available_modes", lambda: {"pdca": "PDCA 模式"})

    raw = await tool._run(mode="pdca", message="do something", agent="worker", acceptance="报告包含全部 7 段", deliverable="交付/do.md")
    result = json.loads(raw)

    assert result["status"] == "created"
    assert result["agent"] == "worker"
    assert result["acceptance"] == "报告包含全部 7 段"  # P1b ⑦: 验收标准回显
    assert "conversation_id" in result  # 键必在（值可为 None：会话在子任务起跑时才分配）
    # 验收标准落 TaskData（报告回注回显的数据源）
    assert graph.created_subtasks, "subtask should be created"
    _, subtask_data = graph.created_subtasks[0]
    assert subtask_data.acceptance_criteria == "报告包含全部 7 段"


async def test_run_task_result_carries_agent_and_conversation_fields(monkeypatch):
    from dawei.entity.task_types import TaskStatus as TS
    from dawei.tools.custom_tools import workflow_tools_fixed as wtf

    sub = FakeTaskNode("sub1", status=TaskStatus.PENDING, parent_id="root")
    sub.data.conversation_id = "conv-9"
    sub.data.metadata["agent"] = "worker"
    graph = FakeTaskGraph([FakeTaskNode("root", status=TaskStatus.RUNNING), sub])

    async def _fake_create(*args, **kwargs):
        return "sub1"

    async def _fake_execute(node):
        sub.update_status(TS.COMPLETED)
        return TS.COMPLETED

    fake_engine = SimpleNamespace(_execute_task_graph_recursive=_fake_execute, _node_executors={}, _user_workspace=None)
    monkeypatch.setattr(wtf, "get_active_execution_engine", lambda: fake_engine)
    monkeypatch.setattr(wtf.NewTaskTool, "_load_available_modes", lambda self: {"pdca": "PDCA 模式"})
    monkeypatch.setattr(wtf.NewTaskTool, "_create_subtask", _fake_create)

    tool = wtf.RunTaskTool(task_graph=graph, workspace_root=None)
    raw = await tool._run(mode="pdca", message="do something", agent="worker")
    result = json.loads(raw)

    assert result["status"] == "completed"
    assert result["conversation_id"] == "conv-9"
    assert result["agent"] == "worker"
