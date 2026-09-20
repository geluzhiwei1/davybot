# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""MCP 一级工具注入（mcp__ 前缀）单测。

覆盖 2026-09-18 排障引入的三个面：
- build_mcp_tool_dicts：connected 过滤 / 无名工具跳过 / 去重 / None 容错；
- auto_connect_all：disabled 与已连接跳过、_merged_configs 属性回归
  （首版误用不存在的 _configs，AttributeError 被上层吞成静默失败）；
- mode 过滤放行：mcp__ 前缀工具按 "mcp" 组准入。
"""

import os
from pathlib import Path

import pytest

from dawei.tools.mcp_dynamic_tools import (
    MCP_TOOL_PREFIX,
    build_mcp_tool_dicts,
    mcp_tool_name,
)
from dawei.tools.mcp_tool_manager import MCPConfig, MCPServerInfo, MCPToolManager

pytestmark = pytest.mark.unit


class _Info(MCPServerInfo):
    """免 IO 的 server info 构造（绕开 connect 才有的 tools 填充）。"""


def _info(status: str, tools: list) -> _Info:
    info = _Info(name="x", config=MCPConfig(server_name="x", command="x"))
    info.status = status
    info.tools = tools
    return info


class _Mgr:
    """build_mcp_tool_dicts 最小依赖面。"""

    def __init__(self, servers):
        self._servers = servers

    def get_all_servers(self):
        return self._servers


class TestBuildMcpToolDicts:
    def test_only_connected_and_named(self):
        mgr = _Mgr(
            {
                "paper-search": _info(
                    "connected",
                    [
                        {
                            "name": "search_arxiv",
                            "description": "search arxiv",
                            "parameters": {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]},
                        },
                        {"description": "无 name 字段 → 跳过"},
                    ],
                ),
                "off": _info("disconnected", [{"name": "x"}]),
            }
        )
        tools = build_mcp_tool_dicts(mgr)
        assert [t["name"] for t in tools] == ["mcp__paper-search__search_arxiv"]
        t = tools[0]
        assert t["parameters"]["required"] == ["q"]
        assert t["original_tool"] is t["callable"]
        assert t["category"] == "mcp"
        assert t["description"].startswith("[mcp:paper-search]")

    def test_none_manager_and_empty(self):
        assert build_mcp_tool_dicts(None) == []
        assert build_mcp_tool_dicts(_Mgr({})) == []

    def test_duplicate_names_deduped(self):
        mgr = _Mgr({"s": _info("connected", [{"name": "dup"}, {"name": "dup"}])})
        assert len(build_mcp_tool_dicts(mgr)) == 1

    def test_name_sanitized_and_prefixed(self):
        assert mcp_tool_name("paper-search", "search_arxiv") == "mcp__paper-search__search_arxiv"
        assert mcp_tool_name("internet search!", "q") == f"{MCP_TOOL_PREFIX}internet-search__q"
        # OpenAI function name 约束:^[a-zA-Z0-9_-]{1,64}$
        assert len(mcp_tool_name("internet-search-headless", "browser_take_screenshot")) <= 64


class TestMCPDynamicToolRun:
    def test_run_error_returns_json(self):
        """call_tool 失败 → JSON 错误串（LLM 可自纠），不抛出。"""
        import json

        from dawei.tools.mcp_dynamic_tools import MCPDynamicTool

        class _Boom:
            def get_config(self, name):
                raise KeyError(name)

            def call_tool(self, server, tool, args):
                raise RuntimeError("boom")

        t = MCPDynamicTool(_Boom(), "s", "t", "d")
        out = json.loads(t._run(a=1))
        assert "RuntimeError" in out["error"]


class TestAutoConnectAll:
    def _manager(self):
        mgr = object.__new__(MCPToolManager)  # 免 IO:只装配 auto_connect_all 触碰的属性
        mgr._servers = {}
        mgr._merged_configs = {}
        return mgr

    @pytest.mark.asyncio
    async def test_skips_disabled_and_connected_connects_pending(self):
        mgr = self._manager()
        for name, disabled, status in [
            ("off", True, "disconnected"),
            ("on", False, "disconnected"),
            ("already", False, "connected"),
        ]:
            mgr._servers[name] = _info(status, [])
            mgr._merged_configs[name] = MCPConfig(server_name=name, command="x", disabled=disabled)

        called = []

        async def _connect(name):
            called.append(name)
            return True  # 真实 connect_server 成功时返回 True

        mgr.connect_server = _connect
        await mgr.auto_connect_all()
        assert called == ["on"]  # disabled 跳过;已连接跳过

    @pytest.mark.asyncio
    async def test_connect_returning_false_no_false_success(self, caplog):
        """回归:connect_server 失败时返回 False 而不抛(内部吞错落 last_error)。
        auto_connect_all 必须按返回值分流——否则假记 auto-connected 成功。"""
        import logging

        mgr = self._manager()
        mgr._servers["on"] = _info("disconnected", [])
        mgr._servers["on"].last_error = "shell offline"
        mgr._merged_configs["on"] = MCPConfig(server_name="on", command="x")

        async def _connect(name):  # noqa: RUF029
            return False

        mgr.connect_server = _connect
        with caplog.at_level(logging.WARNING, logger="dawei.tools.mcp_tool_manager"):
            await mgr.auto_connect_all()  # 不抛
        assert any("auto-connect 'on' failed" in m and "shell offline" in m for m in caplog.messages)
        assert not any("auto-connected 'on'" in m for m in caplog.messages)

    @pytest.mark.asyncio
    async def test_connect_raising_logged_not_propagated(self, caplog):
        """双保险分支:connect_server 抛出 → 告警含异常,不向调用方传播。"""
        import logging

        mgr = self._manager()
        mgr._servers["on"] = _info("disconnected", [])
        mgr._merged_configs["on"] = MCPConfig(server_name="on", command="x")

        async def _connect(name):
            raise RuntimeError("unexpected")

        mgr.connect_server = _connect
        with caplog.at_level(logging.WARNING, logger="dawei.tools.mcp_tool_manager"):
            await mgr.auto_connect_all()
        assert any("raised" in m and "unexpected" in m for m in caplog.messages)

    @pytest.mark.asyncio
    async def test_uses_merged_configs_attribute(self):
        """回归:首版误用不存在的 self._configs → AttributeError 静默失败。"""
        mgr = self._manager()
        mgr._servers["on"] = _info("disconnected", [])
        mgr._merged_configs["on"] = MCPConfig(server_name="on", command="x")

        async def _connect(name):  # noqa: RUF029
            return True

        mgr.connect_server = _connect
        await mgr.auto_connect_all()  # 不应抛 AttributeError


class TestConfigExpansion:
    def test_from_dict_expands_vars_and_user(self):
        os.environ.setdefault("PSM_TEST_HOME", "/tmp/psm")
        c = MCPConfig.from_dict(
            "s",
            {
                "command": "uv",
                "args": ["--directory", "${PSM_TEST_HOME}", "run", "x"],
                "cwd": "~/ws",
                "env": {"K": "${KEEP_LITERAL}"},
            },
        )
        assert c.args[1] == "/tmp/psm"
        assert c.cwd == str(Path("~/ws").expanduser())
        assert c.env["K"] == "${KEEP_LITERAL}"  # env 值不展开

    def test_undefined_var_kept_literal(self):
        c = MCPConfig.from_dict("s", {"command": "run", "cwd": "${UNSET_VAR_XYZ}"})
        assert c.cwd == "${UNSET_VAR_XYZ}"


class TestModeFilterRetired:
    """mode-工具解耦（方案 D4）：mode 维度工具过滤方法已删除。

    mcp__ 一级工具的可见性/可执行性仅由 workspace_settings.always_allow_mcp
    门控（行为测试见 TestAlwaysAllowMcpGate），与当前 mode 无关。
    """

    def test_wrapper_mode_filter_method_removed(self):
        from dawei.workspace.tool_manager_wrapper import WorkspaceToolManager

        assert not hasattr(WorkspaceToolManager, "_filter_tools_by_mode")
        assert not hasattr(WorkspaceToolManager, "get_mode_available_tools")

    def test_workspace_mode_filter_method_removed(self):
        from dawei.workspace.user_workspace import UserWorkspace

        assert not hasattr(UserWorkspace, "_filter_tools_by_mode")
        assert not hasattr(UserWorkspace, "get_mode_available_tools")


class _GateTM:
    """allowed_tools 门控测试的 ToolManager 桩:空静态面 + 过滤委托真实静态逻辑。"""

    def load_tools(self):
        return []

    def get_filtered_tool_names(self, tools, settings):
        from dawei.tools.tool_manager import ToolManager

        return ToolManager.get_filtered_tool_names(self, tools, settings)


class TestAlwaysAllowMcpGate:
    """mcp__ 一级工具在静态过滤（get_filtered_tool_names）与装配（allowed_tools）
    两条路上同受 workspace_settings.always_allow_mcp（UI: mcpEnabled）门控。"""

    def test_get_filtered_tool_names_gates_mcp_prefix(self):
        from dawei.tools.tool_manager import ToolManager
        from dawei.workspace.models import WorkspaceSettings

        tools = [{"name": "read_file"}, {"name": "mcp__s__t"}]
        on = ToolManager.get_filtered_tool_names(None, tools, WorkspaceSettings(always_allow_mcp=True))
        assert on == {"read_file", "mcp__s__t"}
        off = ToolManager.get_filtered_tool_names(None, tools, WorkspaceSettings(always_allow_mcp=False))
        assert off == {"read_file"}

    def _wtm(self, always_allow_mcp: bool):
        from dawei.workspace.models import WorkspaceSettings
        from dawei.workspace.tool_manager_wrapper import WorkspaceToolManager

        wtm = object.__new__(WorkspaceToolManager)
        wtm.tool_manager = _GateTM()
        wtm._skills_tools = None
        wtm.mcp_tool_manager = _Mgr({"s": _info("connected", [{"name": "t", "description": "d"}])})
        wtm.workspace_settings = WorkspaceSettings(always_allow_mcp=always_allow_mcp)
        return wtm

    def test_wrapper_allowed_tools_honors_gate(self):
        names_on = [t["name"] for t in self._wtm(True).allowed_tools]
        assert "mcp__s__t" in names_on
        names_off = [t["name"] for t in self._wtm(False).allowed_tools]
        assert "mcp__s__t" not in names_off


class TestStaticAllowlistVsMcpDynamic:
    """静态 allowlist(security policy / workspace settings)对动态 mcp__ 名豁免:
    动态名不可能预置在名单里,由 MCP 专属闸门(always_allow_mcp)治理;
    denied_tools 精确匹配仍封禁动态名。"""

    def _executor(self, monkeypatch, *, policy_allowed=(), settings):
        import logging
        from types import SimpleNamespace

        import dawei.core.security_manager as sec_mod
        import dawei.core.super_mode as super_mod
        from dawei.tools.tool_executor import ToolExecutor

        monkeypatch.setattr(super_mod, "is_super_mode_enabled", lambda: False)
        monkeypatch.setattr(
            sec_mod,
            "security_manager",
            SimpleNamespace(get_policy=lambda: SimpleNamespace(tools=SimpleNamespace(denied_tools=[], allowed_tools=list(policy_allowed)))),
        )
        ex = object.__new__(ToolExecutor)
        ex.logger = logging.getLogger("test-executor")
        ex._agent = None  # 跳过 mode 组段:本用例只钉 allowlist/denylist 语义
        ex.user_workspace = SimpleNamespace(settings=settings)
        return ex

    def test_settings_allowlist_exempts_mcp_dynamic(self, monkeypatch):
        from dawei.workspace.models import WorkspaceSettings

        ex = self._executor(monkeypatch, settings=WorkspaceSettings(allowed_tools=["read_file"], denied_tools=[]))
        assert ex.check_permission("mcp__s__t") is True  # 豁免:避免 schema 可见但执行被拒
        assert ex.check_permission("read_file") is True
        assert ex.check_permission("write_text_file") is False  # 白名单仍管静态名

    def test_policy_allowlist_exempts_mcp_dynamic(self, monkeypatch):
        from dawei.workspace.models import WorkspaceSettings

        ex = self._executor(monkeypatch, policy_allowed=["read_file"], settings=WorkspaceSettings())
        assert ex.check_permission("mcp__s__t") is True
        assert ex.check_permission("write_text_file") is False

    def test_denied_exact_match_still_blocks_mcp_dynamic(self, monkeypatch):
        from dawei.workspace.models import WorkspaceSettings

        ex = self._executor(monkeypatch, settings=WorkspaceSettings(denied_tools=["mcp__s__t"]))
        assert ex.check_permission("mcp__s__t") is False  # 精确 deny 对动态名生效


class TestSyncMcpToolsToIndex:
    """_sync_mcp_tools_to_index:增量注册 mcp__ 工具进 ToolIndex。

    server 会话中途连上时索引一次成型会漏掉晚到的工具 → 每请求 diff;
    seen 防重入(ToolIndex.register 重复调用会使 BM25 的 df 计数虚增)。
    """

    def _builder(self):
        from dawei.prompts.llm_message_builder import EnhancedSystemBuilder

        return object.__new__(EnhancedSystemBuilder)

    def _ws(self):
        from types import SimpleNamespace

        from dawei.tools.tool_discovery.tool_index import ToolIndex

        return SimpleNamespace(_tool_index=ToolIndex())

    def test_incremental_and_idempotent(self):
        builder = self._builder()
        ws = self._ws()
        tools = [{"name": "read_file"}, {"name": "mcp__s__t", "description": "search papers"}]

        builder._sync_mcp_tools_to_index(ws, tools)
        doc = ws._tool_index.get_doc("mcp__s__t")
        assert doc is not None
        assert doc.group == "mcp"
        assert ws._tool_index.get_doc("read_file") is None  # 只注册 mcp__ 前缀

        # 同面再跑:不重复注册(条目数不变);新 server 的工具增量可见
        builder._sync_mcp_tools_to_index(ws, tools)
        assert len(ws._tool_index.list_all()) == 1
        tools.append({"name": "mcp__s2__t2", "description": "another"})
        builder._sync_mcp_tools_to_index(ws, tools)
        assert ws._tool_index.get_doc("mcp__s2__t2") is not None
        assert len(ws._tool_index.list_all()) == 2

    def test_no_index_noop(self):
        from types import SimpleNamespace

        builder = self._builder()
        ws = SimpleNamespace()  # 渐进式披露关闭 → 无 _tool_index,静默跳过
        builder._sync_mcp_tools_to_index(ws, [{"name": "mcp__s__t"}])
        assert not hasattr(ws, "_tool_index_mcp_seen")
