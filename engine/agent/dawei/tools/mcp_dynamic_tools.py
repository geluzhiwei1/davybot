# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""MCP 一级工具注入 —— 已连接 MCP server 的工具直接映射为 agent 工具。

背景（2026-09-18 排障：workspace 68c14cf4 / 任务 2bebf2c2 报"无浏览器工具"）：
MCP 工具此前只能经 use_mcp_tool 元工具间接调用，且 server 需 agent 手动
connect——已配置的 server（如 paper-search）从不进入会话工具面。

本模块把每个 connected server 的工具包装为 ``mcp__{server}__{tool}`` 一级工具：

- schema 注入：UserWorkspace.allowed_tools 追加；
- mode-工具解耦（2026-09-19）：无 mode 组过滤——安装（连接）即可见；
- 渐进披露：``mcp__`` 前缀视同 Tier-0 常驻（llm_message_builder 池过滤放行）；
- 执行：CustomBaseTool.run() → _run → MCPToolManager.call_tool（安全策略
  allow/deny 与超时沿用 call_tool 内部闸门）。

命名约束：OpenAI function name ``^[a-zA-Z0-9_-]{1,64}$``；非法字符归一为
"-"。前缀 ``mcp__`` 使既有工作区过滤（startswith "mcp_"）继续生效。
"""

import json
import logging
import re

from dawei.tools.custom_base_tool import CustomBaseTool

logger = logging.getLogger(__name__)

MCP_TOOL_PREFIX = "mcp__"

_NAME_SAFE = re.compile(r"[^0-9A-Za-z_-]+")


def mcp_tool_name(server: str, tool: str) -> str:
    """server/tool 名 → 合法一级工具名 ``mcp__{server}__{tool}``。"""
    s = _NAME_SAFE.sub("-", server or "").strip("-_")
    t = _NAME_SAFE.sub("-", tool or "").strip("-_")
    return f"{MCP_TOOL_PREFIX}{s}__{t}"


class MCPDynamicTool(CustomBaseTool):
    """单个 MCP server 工具的一级包装（运行时动态实例，非反射扫描产物）。

    args_schema 置 None：参数透传给 server 端校验；LLM 侧 schema 由工具
    dict 的 ``parameters``（server inputSchema）直接提供。
    """

    def __init__(self, mcp_manager, server_name: str, server_tool_name: str, description: str):
        self.mcp_manager = mcp_manager
        self.server_name = server_name
        self.server_tool_name = server_tool_name
        self.name = mcp_tool_name(server_name, server_tool_name)
        self.description = description or f"MCP tool '{server_tool_name}' on server '{server_name}'"
        self.args_schema = None
        super().__init__()

    def _call_timeout(self) -> int:
        try:
            cfg = self.mcp_manager.get_config(self.server_name)
            return int(getattr(cfg, "timeout", 300) or 300)
        except Exception:  # noqa: BLE001 — 配置缺失用默认超时
            return 300

    def _run(self, **kwargs) -> str:
        from dawei.tools.custom_tools.async_utils import run_on_main_loop

        timeout = self._call_timeout() + 15  # 略大于 server 超时，让 server 侧错误优先返回
        try:
            coro = self.mcp_manager.call_tool(self.server_name, self.server_tool_name, kwargs)
            result = run_on_main_loop(coro, timeout=timeout)
        except Exception as e:  # noqa: BLE001 — 错误回传给 LLM 自纠
            logger.warning(f"[MCP] {self.name} call failed: {e}")
            return json.dumps({"error": f"{type(e).__name__}: {e}"}, ensure_ascii=False)

        if isinstance(result, (dict, list)):
            return json.dumps(result, ensure_ascii=False)
        return str(result)


def build_mcp_tool_dicts(mcp_manager) -> list[dict]:
    """已连接 server 的工具 → 一级工具 dict（对齐 ToolManager.load_tools 条目形态）。

    只处理 status == "connected" 的 server（工具清单在 connect 时填充）；
    任何单个 server/工具的包装失败都不影响其余条目（FAST FAIL 局部化）。
    """
    tools: list[dict] = []
    if mcp_manager is None:
        return tools

    try:
        servers = mcp_manager.get_all_servers()
    except Exception:  # noqa: BLE001
        logger.exception("[MCP] list servers for dynamic tools failed")
        return tools

    seen: set[str] = set()
    for server_name, info in servers.items():
        if getattr(info, "status", "") != "connected":
            continue
        for t in getattr(info, "tools", None) or []:
            try:
                raw_name = t.get("name") if isinstance(t, dict) else None
                if not raw_name:
                    continue
                instance = MCPDynamicTool(
                    mcp_manager,
                    server_name,
                    raw_name,
                    (t.get("description") or "") if isinstance(t, dict) else "",
                )
                if instance.name in seen:
                    continue
                seen.add(instance.name)
                tools.append(
                    {
                        "name": instance.name,
                        "description": f"[mcp:{server_name}] {instance.description}".strip(),
                        "parameters": (t.get("parameters") if isinstance(t, dict) else None)
                        or {"type": "object", "properties": {}, "required": []},
                        "callable": instance,
                        "original_tool": instance,  # ToolExecutor 执行入口
                        "category": "mcp",
                        "enabled": True,
                    },
                )
            except Exception:  # noqa: BLE001
                logger.exception("[MCP] wrap tool %s/%s failed", server_name, t)
    if tools:
        # 每次 LLM 请求都会重建工具面,INFO 会刷屏;稳定后仅在连接数变化时由
        # 连接层打 INFO,这里用 debug
        logger.debug(f"[MCP] injected {len(tools)} first-class MCP tools from {len(servers)} servers")
    return tools
