# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""user_id 传播契约（账户隔离,2026-09-18 paper-search 回归）。

核心约束:真实账号必须在 UserWorkspace.initialize() **之前**注入 ——
WorkspaceContext 按 (path, user_id) 分键,MCP/relay stub 等账户隔离资源
跟随 context 键;事后注入只改 _user_id 不换 context,造成「壳按真实账号
注册、引擎按 default_user 取面」的拆分。

覆盖:
- graphs._ensure_workspace_initialized:initialize 前注入认证 user_id;
  已初始化则不再触发认证/初始化。
- UserWorkspace.user_id setter:initialize 后变更只大声告警,不静默换键。
"""

import pytest

pytestmark = pytest.mark.unit


# ── graphs._ensure_workspace_initialized ──────────────────────


class _FakeWorkspace:
    def __init__(self) -> None:
        self.user_id = "default_user"

    def is_initialized(self) -> bool:
        return False

    async def initialize(self) -> None:
        self.init_seen_user_id = self.user_id


async def test_graphs_ensure_injects_auth_user_before_initialize(monkeypatch):
    from dawei.api.workspaces import graphs as graphs_mod

    async def fake_auth_uid(request):  # noqa: ARG001
        return "web-user-1"

    # 函数内延迟 import → 打在源模块属性上即可生效
    monkeypatch.setattr("dawei.api.auth.get_authenticated_user_id", fake_auth_uid, raising=False)

    ws = _FakeWorkspace()
    await graphs_mod._ensure_workspace_initialized(ws, request=object())
    assert ws.user_id == "web-user-1"
    assert ws.init_seen_user_id == "web-user-1", "user_id 必须在 initialize() 之前注入"


async def test_graphs_ensure_skips_auth_when_already_initialized(monkeypatch):
    from dawei.api.workspaces import graphs as graphs_mod

    async def auth_must_not_run(request):  # noqa: ARG001
        raise AssertionError("已初始化的工作区不应再走认证注入/初始化")

    monkeypatch.setattr("dawei.api.auth.get_authenticated_user_id", auth_must_not_run, raising=False)

    class _Initialized:
        user_id = "default_user"

        def is_initialized(self) -> bool:
            return True

        async def initialize(self) -> None:
            raise AssertionError("不应重复 initialize")

    await graphs_mod._ensure_workspace_initialized(_Initialized(), request=object())


# ── UserWorkspace.user_id setter ──────────────────────────────


def test_user_workspace_late_user_id_change_warns(tmp_path):
    import logging

    from dawei.workspace.user_workspace import UserWorkspace

    ws = UserWorkspace(str(tmp_path / "ws"))
    # 模拟「已初始化」状态(不跑真实 initialize,避免磁盘/管理器副作用)
    ws._initialized = True
    ws._context = object()

    records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    # dawei 的 logger 不向 root 传播,caplog 捕不到 → 直接挂到目标 logger
    lg = logging.getLogger("dawei.workspace.user_workspace")
    handler = _Capture()
    lg.addHandler(handler)
    try:
        ws.user_id = "someone-else"
    finally:
        lg.removeHandler(handler)

    assert ws.user_id == "someone-else"  # setter 仍赋值(不静默吞掉)
    assert any("initialize() 前注入" in r.getMessage() for r in records), "事后注入必须大声告警"


def test_user_workspace_user_id_set_before_init_is_silent(tmp_path):
    from dawei.workspace.user_workspace import UserWorkspace

    ws = UserWorkspace(str(tmp_path / "ws"))
    ws.user_id = "web-user-1"  # 未初始化 → 正常路径,无告警
    assert ws.user_id == "web-user-1"

    ws.user_id = None  # 空值不覆盖
    assert ws.user_id == "web-user-1"
