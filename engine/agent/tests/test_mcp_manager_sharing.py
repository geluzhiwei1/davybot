# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""MCPToolManager 进程级共享注册表单元测试。

回归背景：connect_mcp_server 与 use_mcp_tool 曾各自持有私有 MCPToolManager
（_get_shared_mcp_manager fallback 每次 new 新实例），导致「连接成功但调用报
disconnected」的状态分裂。修复后所有按 (workspace_root, user_id) 的获取都走
get_or_create_mcp_manager() 注册表，同 key 必须同实例。
"""

import pytest

pytestmark = pytest.mark.unit

from dawei.tools import mcp_tool_manager as mtm  # noqa: E402
from dawei.tools.custom_tools.mcp_tools import _get_shared_mcp_manager  # noqa: E402
from dawei.tools.mcp_tool_manager import (  # noqa: E402
    _reset_manager_registry,
    get_or_create_mcp_manager,
)

UID = "mgr-share-user"


@pytest.fixture(autouse=True)
def fresh_manager_registry():
    _reset_manager_registry()
    yield
    _reset_manager_registry()


# ── 注册表基本不变量 ──────────────────────────────────────────


def test_registry_same_key_returns_same_instance(tmp_path):
    a = get_or_create_mcp_manager(workspace_root=str(tmp_path), user_id=UID)
    b = get_or_create_mcp_manager(workspace_root=str(tmp_path), user_id=UID)
    assert a is b


def test_registry_different_keys_distinct_instances(tmp_path):
    a = get_or_create_mcp_manager(workspace_root=str(tmp_path / "ws1"), user_id=UID)
    b = get_or_create_mcp_manager(workspace_root=str(tmp_path / "ws2"), user_id=UID)
    c = get_or_create_mcp_manager(workspace_root=str(tmp_path / "ws1"), user_id="other-user")
    assert a is not b
    assert a is not c
    assert b is not c


def test_registry_none_workspace_normalized(tmp_path):
    """workspace_root=None 与显式空串视为同一 key（用户级管理器）。"""
    a = get_or_create_mcp_manager(workspace_root=None, user_id=UID)
    b = get_or_create_mcp_manager(workspace_root="", user_id=UID)
    assert a is b
    assert b.workspace_root is None


def test_registry_default_user_id_normalized(tmp_path):
    a = get_or_create_mcp_manager(workspace_root=str(tmp_path))
    b = get_or_create_mcp_manager(workspace_root=str(tmp_path), user_id="default_user")
    assert a is b


# ── 工具类 fallback 与注册表一致性（核心回归） ────────────────


def test_fallback_without_context_shares_registry_instance(tmp_path, monkeypatch):
    """ctx 查不到（initialize 期间）时，fallback 必须走注册表而非各 new 各的。

    这是 connect/use 状态分裂 BUG 的直接回归测试：ConnectMCPServer 与
    UseMCPTool 实例化时各调一次 _get_shared_mcp_manager，必须拿到同一 manager。
    """
    monkeypatch.setattr(
        "dawei.workspace.workspace_service.WorkspaceService.get_context_if_initialized",
        staticmethod(lambda *_a, **_k: None),
    )
    ws = str(tmp_path)
    m_from_connect_side = _get_shared_mcp_manager(ws, UID)
    m_from_use_side = _get_shared_mcp_manager(ws, UID)
    assert m_from_connect_side is m_from_use_side
    assert m_from_connect_side is get_or_create_mcp_manager(workspace_root=ws, user_id=UID)


def test_fallback_on_lookup_error_still_consistent(tmp_path, monkeypatch):
    """ctx 查找抛异常（FAST FAIL 记 warning）也不得退化为私有实例。"""

    def boom(*a, **k):
        raise RuntimeError("workspace service unavailable")

    monkeypatch.setattr(
        "dawei.workspace.workspace_service.WorkspaceService.get_context_if_initialized",
        staticmethod(boom),
    )
    ws = str(tmp_path)
    a = _get_shared_mcp_manager(ws, UID)
    b = _get_shared_mcp_manager(ws, UID)
    assert a is b
    assert a is get_or_create_mcp_manager(workspace_root=ws, user_id=UID)


def test_fallback_prefers_context_instance(tmp_path, monkeypatch):
    """ctx 已初始化时优先返回 ctx.mcp_tool_manager（注册表之上的第一优先级）。"""

    class FakeCtx:
        def __init__(self, mgr):
            self.mcp_tool_manager = mgr

    shared = get_or_create_mcp_manager(workspace_root=str(tmp_path), user_id=UID)
    monkeypatch.setattr(
        "dawei.workspace.workspace_service.WorkspaceService.get_context_if_initialized",
        staticmethod(lambda *_a, **_k: FakeCtx(shared)),
    )
    assert _get_shared_mcp_manager(str(tmp_path), UID) is shared


def test_state_visible_across_tool_instances(tmp_path, monkeypatch):
    """连接状态跨工具实例可见：一侧 connect 更新 status，另一侧立即读到。"""
    monkeypatch.setattr(
        "dawei.workspace.workspace_service.WorkspaceService.get_context_if_initialized",
        staticmethod(lambda *_a, **_k: None),
    )
    ws = str(tmp_path)
    connect_side = _get_shared_mcp_manager(ws, UID)
    use_side = _get_shared_mcp_manager(ws, UID)

    # 模拟 connect_server 成功后的状态落位（不实际起子进程/relay）
    connect_side._servers["fake-relay"] = mtm.MCPServerInfo(
        name="fake-relay",
        config=mtm.MCPConfig(server_name="fake-relay", command="", transport="local"),
        status="connected",
    )
    info = use_side.get_server_info("fake-relay")
    assert info is not None
    assert info.status == "connected"


# ── relay stub 优先级与陈旧快照刷新（2026-09-18 paper-search 回归） ──────────
# 背景：market 资源包向任务工作区落盘 stdio 版 paper-search（占位符命令
# ${PAPER_SEARCH_MCP_HOME} 不展开），后端当 stdio 启动秒败（Connection closed）。
# 修复语义：light-app 壳注册的 relay stub 优先级最高，覆盖同名 user/workspace
# 配置；共享管理器 connect 前刷新 stub（陈旧快照修复）。


def _stdio_config(name: str) -> mtm.MCPConfig:
    return mtm.MCPConfig(server_name=name, command="uv", args=["run", "${PAPER_SEARCH_MCP_HOME}"], transport="stdio")


def _stub_config(name: str) -> mtm.MCPConfig:
    return mtm.MCPConfig(server_name=name, command="", transport="local")


class _FakeRelayRegistry:
    """替身 relay 注册表：只回固定 stub 面，免联网/免进程内单例。"""

    def __init__(self, stubs: dict):
        self._stubs = stubs

    def get_stub_configs(self, user_id: str) -> dict:  # noqa: ARG002 — 对齐真实签名
        return self._stubs


def test_relay_stub_overrides_same_name_workspace_stdio(tmp_path):
    """壳在线时，同名 workspace stdio 配置必须让位给 relay stub。"""
    m = get_or_create_mcp_manager(workspace_root=str(tmp_path), user_id=UID)
    m._workspace_configs = {"paper-search": _stdio_config("paper-search")}
    m._local_configs = {"paper-search": _stub_config("paper-search")}
    m._merge_configs()
    m._initialize_servers()
    assert m.get_config("paper-search").transport == "local"
    assert m.get_config_override_info("paper-search")["active_source"] == "local"


def test_file_config_priority_workspace_over_user_unchanged(tmp_path):
    """user/workspace 相对优先级不变：workspace 覆盖 user（仅 local 提到最高）。"""
    m = get_or_create_mcp_manager(workspace_root=str(tmp_path), user_id=UID)
    m._user_configs = {"x": _stdio_config("x")}
    m._workspace_configs = {"x": mtm.MCPConfig(server_name="x", command="ws-cmd", transport="stdio")}
    m._local_configs = {}
    m._merge_configs()
    assert m.get_config("x").command == "ws-cmd"


def test_refresh_relay_stubs_swaps_stale_stdio_snapshot(tmp_path):
    """共享管理器构造时壳未注册 → 快照为 stdio；刷新后同名配置换为 relay。"""
    m = get_or_create_mcp_manager(workspace_root=str(tmp_path), user_id=UID)
    m._workspace_configs = {"paper-search": _stdio_config("paper-search")}
    m._local_configs = {}
    m._merge_configs()
    m._initialize_servers()
    assert m.get_config("paper-search").transport == "stdio"

    stub = _stub_config("paper-search")
    # 模拟注册表返回 stub（绕过进程内 relay 注册表的联网依赖）
    import dawei.tools.mcp_relay as relay_mod

    orig = relay_mod.get_relay_registry
    try:
        relay_mod.get_relay_registry = lambda: _FakeRelayRegistry({"paper-search": stub})
        m._refresh_relay_stubs()
    finally:
        relay_mod.get_relay_registry = orig

    assert m.get_config("paper-search") is stub
    assert m.get_server_info("paper-search").config is stub


def test_refresh_relay_stubs_keeps_connected_server(tmp_path):
    """已连接 server 不被刷新撕裂（活跃会话优先）。"""
    m = get_or_create_mcp_manager(workspace_root=str(tmp_path), user_id=UID)
    stdio = _stdio_config("paper-search")
    m._merged_configs = {"paper-search": stdio}
    m._servers = {
        "paper-search": mtm.MCPServerInfo(name="paper-search", config=stdio, status="connected"),
    }
    stub = _stub_config("paper-search")
    import dawei.tools.mcp_relay as relay_mod

    orig = relay_mod.get_relay_registry
    try:
        relay_mod.get_relay_registry = lambda: _FakeRelayRegistry({"paper-search": stub})
        m._refresh_relay_stubs()
    finally:
        relay_mod.get_relay_registry = orig
    assert m.get_server_info("paper-search").config is stdio
    assert m.get_server_info("paper-search").status == "connected"
