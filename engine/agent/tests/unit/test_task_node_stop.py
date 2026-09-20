# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""TASK_NODE_STOP(用户终结任务节点)回归测试 —— P1b ⑩ 独立 handler 接线。

背景:task_node_control.py 的 TASK_NODE_STOP 处理器从未注册且为空壳
(success = True placeholder),P0 将分发接进 ChatHandler;P1a 升级为
CANCELLED 语义 + BFS 级联 + finalize(status/result 同笔)+ 同步取消执行;
P1b ⑩ 将真实逻辑整体迁入 TaskNodeControlHandler 并经 ws_server 注册
(ChatHandler 摘除该类型——路由器按类型并行执行所有声明处理器,双声明
= 双发)。锁定语义:
- 运行中 → finalize(CANCELLED+原因) + engine.cancel_task_execution
- 终态 → 不做任何变更,success 回执
- PENDING → finalize(不触发 engine cancel)
- 子孙节点 → 级联 finalize,运行中的子孙也 cancel
- 节点不存在 → success 回执(镜像 AGENT_STOP 幂等语义)
- ChatHandler 不再声明 TASK_NODE_STOP(防双发回归)
- PAUSE/RESUME 占位实现不声明类型(不接线假成功回执)
"""

from unittest.mock import AsyncMock

import pytest

from dawei.entity.task_types import TaskStatus as GraphTaskStatus
from dawei.websocket.handlers.chat import ChatHandler
from dawei.websocket.handlers.task_node_control import TaskNodeControlHandler
from dawei.websocket.protocol import MessageType, TaskNodeStopMessage


class _FakeNode:
    def __init__(self, status: GraphTaskStatus, node_id: str = "node-1", child_ids=None):
        self.status = status
        self.task_node_id = node_id
        self.child_ids = child_ids or []
        # P2-B: 审计 metadata 载体(与真实 TaskData.metadata 同构)
        self.data = type("Data", (), {"metadata": {}})()


class _FakeGraph:
    def __init__(self, nodes: dict):
        self._nodes = nodes
        self.update_task_status = AsyncMock(return_value=True)
        self.finalize_task = AsyncMock(return_value=True)

    async def get_task(self, task_id: str) -> _FakeNode | None:
        return self._nodes.get(task_id)


class _FakeEngine:
    def __init__(self):
        self.cancel_task_execution = AsyncMock(return_value=True)


class _FakeWorkspace:
    def __init__(self, graph, engine):
        self.task_graph = graph
        self.execution_engine = engine


class _FakeAgent:
    def __init__(self, ws):
        self.user_workspace = ws


@pytest.fixture
def chat_singleton(monkeypatch):
    """把 chat_handler_instance 单例指向带 _active_agents 的替身(生产接线同构)"""
    import dawei.websocket.handlers.chat as chat_mod

    holder = type("Holder", (), {})()

    def _install(agents: dict):
        holder.instance = type("FakeChat", (), {"_active_agents": agents})()
        monkeypatch.setattr(chat_mod, "chat_handler_instance", holder.instance, raising=False)
        return holder.instance

    # monkeypatch 在 fixture 结束时自动恢复单例,无需 teardown
    return _install


def _make_handler(nodes: dict, chat_singleton) -> tuple[TaskNodeControlHandler, _FakeEngine, _FakeGraph]:
    engine = _FakeEngine()
    graph = _FakeGraph(nodes)
    chat_singleton({"task-a": _FakeAgent(_FakeWorkspace(graph, engine))})
    handler = TaskNodeControlHandler()
    sent: list = []
    handler.send_message = AsyncMock(side_effect=lambda _sid, msg: sent.append(msg))
    handler._sent = sent
    return handler, engine, graph


async def _stop(handler: TaskNodeControlHandler, node_id="node-1", **kwargs):
    msg = TaskNodeStopMessage(session_id="s1", task_node_id=node_id, **kwargs)
    return await handler._handle_stop("s1", msg), msg


@pytest.mark.unit
async def test_supported_types_single_claim(chat_singleton):  # noqa: ARG001
    """⑩ 接线不变量:仅 TaskNodeControlHandler 声明 TASK_NODE_STOP(防双发);
    PAUSE/RESUME 占位实现不声明(不接线假成功回执)。"""
    handler = TaskNodeControlHandler()
    assert MessageType.TASK_NODE_STOP in handler.get_supported_types()
    # 协议层无 PAUSE/RESUME 消息类(枚举成员亦不存在),用 getattr 安全断言
    assert len(handler.get_supported_types()) == 1
    _pause = getattr(MessageType, "TASK_NODE_PAUSE", None)
    _resume = getattr(MessageType, "TASK_NODE_RESUME", None)
    assert _pause is None or _pause not in handler.get_supported_types()
    assert _resume is None or _resume not in handler.get_supported_types()

    # ChatHandler 必须已摘除(路由器并行执行所有声明处理器 → 双声明=双发)
    chat = ChatHandler()
    assert MessageType.TASK_NODE_STOP not in chat.get_supported_types()


@pytest.mark.unit
async def test_running_node_finalizes_cancelled_then_cancels_engine(chat_singleton):
    handler, engine, _ = _make_handler({"node-1": _FakeNode(GraphTaskStatus.RUNNING)}, chat_singleton)
    result, _ = await _stop(handler, reason="方向错了")

    engine.cancel_task_execution.assert_awaited_once_with("node-1")
    assert result["success"] is True
    assert len(handler._sent) == 1
    assert handler._sent[0].type == MessageType.TASK_NODE_STOPPED


@pytest.mark.unit
async def test_terminal_node_is_idempotent_noop(chat_singleton):
    handler, engine, _ = _make_handler({"node-1": _FakeNode(GraphTaskStatus.COMPLETED)}, chat_singleton)
    result, _ = await _stop(handler)

    engine.cancel_task_execution.assert_not_awaited()
    assert result["success"] is True
    assert "终态" in result["reason"]


@pytest.mark.unit
async def test_cancelled_is_recognized_terminal(chat_singleton):
    """已 CANCELLED 的节点再次 STOP → 幂等,不重复 finalize。"""
    handler, engine, _ = _make_handler({"node-1": _FakeNode(GraphTaskStatus.CANCELLED)}, chat_singleton)
    result, _ = await _stop(handler)

    engine.cancel_task_execution.assert_not_awaited()
    assert "终态" in result["reason"]


@pytest.mark.unit
async def test_pending_node_finalizes_without_engine_cancel(chat_singleton):
    nodes = {"node-1": _FakeNode(GraphTaskStatus.PENDING)}
    handler, engine, graph = _make_handler(nodes, chat_singleton)
    result, _ = await _stop(handler)

    engine.cancel_task_execution.assert_not_awaited()  # PENDING 不在运行,无需 cancel
    graph.finalize_task.assert_awaited_once()
    args = graph.finalize_task.await_args.args
    assert args[0] == "node-1"
    assert args[1] == GraphTaskStatus.CANCELLED
    assert "用户终结" in args[2]
    assert result["success"] is True


@pytest.mark.unit
async def test_cascade_cancels_subtree_and_running_descendants(chat_singleton):
    """父 RUNNING + 子 RUNNING + 孙 PENDING → 三个全 finalize,两个运行中的全 cancel。"""
    nodes = {
        "node-1": _FakeNode(GraphTaskStatus.RUNNING, "node-1", child_ids=["child-1"]),
        "child-1": _FakeNode(GraphTaskStatus.RUNNING, "child-1", child_ids=["grand-1"]),
        "grand-1": _FakeNode(GraphTaskStatus.PENDING, "grand-1"),
        # 无关分支不受影响
        "other": _FakeNode(GraphTaskStatus.RUNNING, "other"),
    }
    handler, engine, graph = _make_handler(nodes, chat_singleton)
    result, _ = await _stop(handler)

    finalized = {c.args[0] for c in graph.finalize_task.await_args_list}
    assert finalized == {"node-1", "child-1", "grand-1"}
    assert "other" not in finalized

    cancelled = {c.args[0] for c in engine.cancel_task_execution.await_args_list}
    assert cancelled == {"node-1", "child-1"}  # grand-1 PENDING 不 cancel,other 不波及
    assert "级联 3" in result["reason"]
    # P2-B 补全:级联子节点也写审计键(此前仅目标节点)
    assert nodes["node-1"].data.metadata["cancelled_by"] == "user(TASK_NODE_STOP)"
    assert nodes["child-1"].data.metadata["cancelled_by"] == "user(TASK_NODE_STOP,cascade)"
    assert nodes["grand-1"].data.metadata["cancelled_by"] == "user(TASK_NODE_STOP,cascade)"
    assert "随父节点终结" in nodes["child-1"].data.metadata["cancelled_reason"]


@pytest.mark.unit
async def test_unknown_node_replies_already_ended(chat_singleton):
    handler, engine, _ = _make_handler({}, chat_singleton)  # graph 里没有该节点
    result, _ = await _stop(handler)

    engine.cancel_task_execution.assert_not_awaited()
    assert result["success"] is True
    assert "不存在" in result["reason"]


@pytest.mark.unit
async def test_stop_writes_cancel_audit_metadata(chat_singleton):
    """P2-B: 用户终结写审计 metadata(cancelled_by/reason/at,对齐 abort_task 的 aborted_* 键位)。"""
    nodes = {"node-1": _FakeNode(GraphTaskStatus.RUNNING)}
    handler, _, _ = _make_handler(nodes, chat_singleton)
    await _stop(handler, reason="方向错了")

    meta = nodes["node-1"].data.metadata
    assert meta["cancelled_by"] == "user(TASK_NODE_STOP)"
    assert meta["cancelled_reason"] == "方向错了"
    assert meta["cancelled_at"]  # ISO 时间戳非空


@pytest.mark.unit
async def test_terminal_idempotent_path_writes_no_audit(chat_singleton):
    """终态幂等路径不做任何变更——审计 metadata 也不写。"""
    nodes = {"node-1": _FakeNode(GraphTaskStatus.COMPLETED)}
    handler, _, _ = _make_handler(nodes, chat_singleton)
    await _stop(handler)

    assert nodes["node-1"].data.metadata == {}


@pytest.mark.unit
async def test_ws_server_registers_task_node_control_handler():
    """⑩ 接线:ws_server 构造/注册/注销 TaskNodeControlHandler"""
    from dawei.websocket.ws_server import WebSocketServer

    srv = WebSocketServer()
    assert isinstance(srv.task_node_control_handler, TaskNodeControlHandler)
