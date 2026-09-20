# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""WS 工作区绑定 —— 测试即规格。

背景(修复前):前端 ws-client 连 /ws 始终携带 workspace_id 查询参数,但端点
签名只声明 token,FastAPI 静默丢弃该参数 → 连接注册为无工作区绑定
(handle_websocket → WebSocketManager.connect(workspace_id=None)),而
task_node_* / subtask_lifecycle 等广播均按 workspace 过滤(manager.broadcast),
全部跳过该连接 —— 工作区监视页只剩 REST 快照,无实时流。

规格:
  WS-1 /ws 转发 workspace_id 与 user_id(连接绑定到该工作区);
  WS-2 /ws 不带 workspace_id → None(未绑定,历史行为不变);
  WS-3 broadcast 过滤语义:仅绑定匹配工作区的连接收到;未绑定连接与他区
      绑定连接被跳过;无 workspace 广播(None)送达全部连接。
"""

import time

import pytest

pytestmark = pytest.mark.unit

from dawei.api import websocket as ws_api  # noqa: E402
from dawei.websocket.manager import ConnectionInfo, WebSocketManager  # noqa: E402


def _mint_token(sub: str = "ws-bind-user") -> str:
    """与 _authenticate_ws 同源校验(Settings 同一 JWT 秘钥)。"""
    import jwt

    from dawei.config.settings import get_settings

    sec = get_settings().security
    now = int(time.time())
    return jwt.encode({"sub": sub, "iat": now, "exp": now + 3600}, sec.jwt_secret, algorithm=sec.jwt_algorithm)


class _HandleRecorder:
    """替身 handle_websocket:accept 后记录 kwargs(避免初始化整个 ws_server)。"""

    def __init__(self):
        self.calls: list[dict] = []

    async def __call__(self, websocket, **kwargs):
        await websocket.accept()
        self.calls.append(kwargs)


@pytest.fixture
def rec(monkeypatch):
    r = _HandleRecorder()
    monkeypatch.setattr(ws_api.websocket_server, "handle_websocket", r)
    return r


def _client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(ws_api.router)
    return TestClient(app)


def _wait_calls(rec, n=1, timeout=3.0):
    deadline = time.time() + timeout
    while time.time() < deadline and len(rec.calls) < n:
        time.sleep(0.02)
    return rec.calls


def test_ws1_forwards_workspace_id(rec):
    token = _mint_token()
    with _client().websocket_connect(f"/ws?token={token}&workspace_id=ws-a"):
        calls = _wait_calls(rec)
    assert calls, "端点应调用 handle_websocket"
    assert calls[0]["workspace_id"] == "ws-a"
    assert calls[0]["user_id"] == "ws-bind-user"


def test_ws2_without_param_binds_none(rec):
    token = _mint_token()
    with _client().websocket_connect(f"/ws?token={token}"):
        calls = _wait_calls(rec)
    assert calls, "端点应调用 handle_websocket"
    assert calls[0]["workspace_id"] is None


async def test_ws3_broadcast_workspace_filter(monkeypatch):
    """过滤语义:绑定匹配 → 收;未绑定/他区 → 跳过;无 workspace → 全体收。"""
    mgr = WebSocketManager()
    sent: dict[str, int] = {}

    async def fake_send(session_id, message, _skip_lock=False):
        sent[session_id] = sent.get(session_id, 0) + 1
        return True

    monkeypatch.setattr(mgr, "send_message", fake_send)

    class _FakeWS:
        client_state = None

    mgr.active_connections["s-bound-a"] = ConnectionInfo(_FakeWS(), "s-bound-a", workspace_id="ws-a")
    mgr.active_connections["s-bound-b"] = ConnectionInfo(_FakeWS(), "s-bound-b", workspace_id="ws-b")
    mgr.active_connections["s-unbound"] = ConnectionInfo(_FakeWS(), "s-unbound", workspace_id=None)

    await mgr.broadcast({"type": "task_node_start"}, workspace_id="ws-a")
    assert sent == {"s-bound-a": 1}, "只有 ws-a 绑定连接应收到 ws-a 广播"

    sent.clear()
    await mgr.broadcast({"type": "subtask_lifecycle"})
    assert sent == {"s-bound-a": 1, "s-bound-b": 1, "s-unbound": 1}, "无 workspace 广播送达全部连接"
