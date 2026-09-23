# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""工具管理器 - 简化版本 (KISS Principle)
支持2层配置加载：default + workspace
统一管理 CustomToolProvider, OpenAIToolProvider

重构说明：
- 移除复杂的ToolConfigLoader缓存逻辑
- 从4层简化为2层：default (builtin+user) + workspace
- 简化合并逻辑为简单的字典更新
- 遵循Fast Fail原则，配置错误立即抛出异常
"""

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any

from dawei import get_dawei_home

from .tool_provider import CustomToolProvider

logger = logging.getLogger(__name__)


# 工具组定义
# 每个 mode 必须在 modes.yaml 中显式声明需要的 groups
# 未声明的组中的工具在该 mode 下不可用
TOOL_GROUPS = {
    "read": {
        "tools": [
            "read_file",
            "list_files",
        ],
    },
    "edit": {
        "tools": [
            "write_text_file",
            "smart_text_edit",
            "insert_text_content",
        ],
    },
    "command": {
        "tools": [
            "execute_command",
            "run_slash_command",
            "shell_command",
        ],
    },
    "mcp": {
        "tools": [
            "use_mcp_tool",
            "access_mcp_resource",
            "call_acp_agent",
            "list_mcp_servers",
            "connect_mcp_server",
            "disconnect_mcp_server",
        ],
    },
    "workflow": {
        "tools": [
            "new_task",
            "new_task_batch",
            "update_todo_list",
            "get_task_status",
            "timer",
            "ask_followup_question",
            "attempt_completion",
            "switch_mode",
            "show_cost",
            "expand_tool_result",
            "search_tools",
            "save_memory",
        ],
    },
    "knowledge": {
        "custom_tools": [
            "search_user_knowledge_base",
            "query_user_knowledge_base",
            "search_legal_knowledge",
            "ask_legal_question",
            "get_legal_document",
            "list_legal_knowledge_bases",
            "legal_search_facets",
            "legal_graph_search",
            "legal_analytics",
            "legal_document_timeline",
        ],
    },
    "social": {
        "custom_tools": [
            "social_read_draft",
            "social_rule_check",
            "social_lookup_trending",
            "social_propose_edit",
            "social_validate_artifact",
            "social_generate_images",
        ],
    },
    "sanctions": {
        "custom_tools": [
            "sanctions_search_entities",
            "sanctions_get_entity",
            "sanctions_graph_search",
            "sanctions_screen_entity",
            "sanctions_create_watchlist",
            "sanctions_run_monitoring_check",
            "sanctions_dashboard",
            "sanctions_filters",
        ],
    },
    "normflow": {
        "custom_tools": [
            "normflow_search_cases",
            "normflow_get_case_detail",
            "normflow_get_case_tasks",
            "normflow_get_case_timesheet",
            "normflow_get_case_documents",
            "normflow_advance_workflow",
            "normflow_get_workflow_templates",
            "normflow_search_clients",
            "normflow_get_client_detail",
            "normflow_get_client_cases",
            "normflow_create_follow_up",
            "normflow_get_payment_status",
        ],
    },
    "market": {
        "custom_tools": [
            "market_dashboard",
            "market_list_products",
            "market_list_signals",
            "market_get_signal",
            "market_list_events",
            "market_get_event",
            "market_list_briefs",
            "market_list_insights",
            "market_list_competitors",
            "market_competitor_profile",
            "market_competitor_contents",
            "market_trends",
            "market_geo_summary",
            "market_geo_checks",
            "market_seo_checks",
            "market_list_keyword_sets",
            "market_list_actions",
            "market_list_opportunities",
            "market_calibration",
            "market_run_pipeline",
            "market_run_source",
            "market_run_geo",
            "market_run_snapshot",
            "market_generate_profile",
            "market_generate_report",
            "market_draft_action",
            "market_evaluate_demand",
            "market_insight_feedback",
        ],
    },
    "research": {
        "custom_tools": [
            "research_journal_lookup",
            "research_journal_rubric",
            "research_journal_suggest",
            "research_paper_search",
            "research_paper_get",
            "research_paper_import",
            "research_review_run_create",
            "research_review_submit",
            "research_submission_check",
        ],
    },
    "docx": {
        "custom_tools": [
            "docx_read_structured",
            "docx_diff",
            "docx_edit",
        ],
    },
    "skills": {
        "custom_tools": [
            "list_skills",
            "search_skills",
            "get_skill",
            "list_skill_resources",
            "read_skill_resource",
        ],
    },
    "browser": {
        # 使用场景:刻意保持空壳 —— 引擎内置工具面不做通用浏览器自动化。
        # 浏览器能力分两条线,均不经此组加载:
        #   1. 互联网检索:三档 internet-search-* MCP 家族(http 直连/无头/真机
        #      Chrome,market: common-team/mcps),经 MCPToolManager 动态注册;
        #   2. 社媒发布/采集:dawei.social 浏览器轨,仅本机执行端(桌面 sidecar/
        #      light-app 壳)claim 执行,SaaS 云引擎不跑(见 social/router.py 守卫)。
        "tools": [],
    },
    "task_graph": {
        "tools": [],  # TaskGraph tools are injected by workspace, not static
    },
}


# ---------------------------------------------------------------------------
# mode-工具解耦（project/docs/mode工具解耦方案.md D5，2026-09-19）
#
# 以下整块退役（无须兼容，直接删除）：
# - RESTRICTED_GROUPS / RESTRICTED_GROUP_NAMES 静态准入白名单
# - derive_restricted_groups / get_restricted_groups（声明即准入派生）
# - INV-1/INV-2/INV-4 工具组不变量
#
# 新语义：工具可用性 = 安装了什么（ToolRegistry），与当前 mode 无关；
# 执行管控 = workspace 级 allow/deny + sandbox 白名单（fail-closed）。
# 保留 check_mode_invariants 的 INV-0（pdca 兜底存在性）与 INV-5（命名/优先级）。
# ---------------------------------------------------------------------------


def check_mode_invariants(mode_registry) -> Dict[str, List[str]]:
    """启动断言（mode工具解耦后仅剩引擎/内容两类的存量子集）。

    返回 {"engine": [...], "content": [...]}：
    - engine（INV-0）：pdca 兜底存在性，违反即拒绝启动；
    - content（INV-5）：命名/优先级规范，仅告警。
    """
    engine: List[str] = []
    content: List[str] = []

    # INV-0: pdca 必须存在（framework 兜底）
    try:
        mode_registry.get("pdca")
    except KeyError:
        engine.append("INV-0: framework mode 'pdca' missing — builtin modes.yaml broken")

    # INV-5: priority 保留段断言（§4.5）
    for mode in mode_registry.all():
        issues = mode.validation_issues()
        if issues:
            content.append(f"INV-5: mode '{mode.slug}': " + "; ".join(issues))

    return {"engine": engine, "content": content}


def assert_mode_invariants(mode_registry) -> List[str]:
    """engine 级断言：返回违规清单（非空 → 调用方 raise / 拒绝启动）；content 级仅告警。"""
    report = check_mode_invariants(mode_registry)
    for issue in report["content"]:
        logger.warning("ModeInvariant (content): %s", issue)
    return report["engine"]


@dataclass
class ToolGroupConfig:
    """工具组配置数据类"""

    tools: List[str] = field(default_factory=list)
    custom_tools: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolGroupConfig":
        """从字典创建工具组配置"""
        return cls(
            tools=data.get("tools", []),
            custom_tools=data.get("custom_tools", []),
        )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "tools": self.tools,
            "custom_tools": self.custom_tools,
        }


@dataclass
class ToolConfig:
    """工具配置数据类"""

    name: str
    description: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    callable: Any = None
    enabled: bool = True
    priority: int = 50
    category: str = "general"
    source_level: str = "builtin"  # builtin, system, user, workspace
    config_overrides: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any], source_level: str = "builtin") -> "ToolConfig":
        """从字典创建工具配置"""
        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            parameters=data.get("parameters", {}),
            callable=data.get("callable"),
            enabled=data.get("enabled", True),
            priority=data.get("priority", 50),
            category=data.get("category", "general"),
            source_level=source_level,
            config_overrides=data.get("config_overrides", {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "enabled": self.enabled,
            "priority": self.priority,
            "category": self.category,
            "source_level": self.source_level,
            "config_overrides": self.config_overrides,
        }

    def merge_with(self, other: "ToolConfig") -> "ToolConfig":
        """与另一个配置合并，other 的值会覆盖当前值"""
        if not other:
            return self

        # 创建新的配置，other 的非空字段覆盖 self 的字段
        merged = ToolConfig.from_dict(self.to_dict(), self.source_level)

        for key, value in other.to_dict().items():
            if value is not None and value not in ("", [], {}):
                setattr(merged, key, value)

        return merged


def _load_builtin_tools(
    workspace_root: str | None = None, user_id: str = "default_user"
) -> Dict[str, ToolConfig]:
    """加载内置工具 (CustomToolProvider)

    Args:
        workspace_root: 工作区路径（可选）
        user_id: 用户 ID（多租户：透传给 per-user 工具，如 MCP）

    Returns:
        工具配置字典

    Raises:
        RuntimeError: 如果必需的工具加载失败

    """
    tools = {}

    # 从 CustomToolProvider 加载自定义工具
    try:
        custom_provider = CustomToolProvider(workspace_root=workspace_root, user_id=user_id)
        custom_tools = custom_provider.get_tools()
        for tool_dict in custom_tools:
            tool_config = ToolConfig.from_dict(tool_dict, "default")
            tools[tool_config.name] = tool_config
        logger.info(f"Loaded {len(custom_tools)} custom tools")
    except Exception as e:
        # Fast Fail: 内置工具加载失败应立即抛出
        logger.error(f"Failed to load custom tools: {e}", exc_info=True)
        raise RuntimeError(f"Cannot load builtin custom tools: {e}")

    logger.info(f"Total builtin tools loaded: {len(tools)}")
    return tools


def _load_user_tools() -> Dict[str, ToolConfig]:
    """加载用户级工具配置

    Returns:
        工具配置字典

    Raises:
        RuntimeError: 如果配置文件存在但加载失败

    """
    tools = {}
    user_config_dir = get_dawei_home() / "configs"
    tools_config_file = user_config_dir / ".tools.json"

    if not tools_config_file.exists():
        logger.debug(f"User tools config not found: {tools_config_file}")
        return {}

    try:
        with Path(tools_config_file).open(encoding="utf-8") as f:
            config_data = json.load(f)

        if "tools" in config_data:
            for tool_data in config_data["tools"]:
                tool_config = ToolConfig.from_dict(tool_data, "default")
                tools[tool_config.name] = tool_config

        logger.info(f"Loaded {len(tools)} user tools from {tools_config_file}")
    except (json.JSONDecodeError, PermissionError, OSError) as e:
        # Fast Fail: 配置文件存在但无法读取应立即抛出
        logger.error(f"Failed to load user tools from {tools_config_file}: {e}", exc_info=True)
        raise RuntimeError(f"Cannot load user tools: {e}")

    return tools


def _load_workspace_tools(workspace_root: str) -> Dict[str, ToolConfig]:
    """加载工作区级工具配置

    Args:
        workspace_root: 工作区路径

    Returns:
        工具配置字典

    Raises:
        RuntimeError: 如果配置文件存在但加载失败

    """
    tools = {}
    workspace_dir = Path(workspace_root)
    workspace_config_dir = workspace_dir / ".dawei" / ".config"
    tools_config_file = workspace_config_dir / ".tools.json"

    if not tools_config_file.exists():
        logger.debug(f"Workspace tools config not found: {tools_config_file}")
        return {}

    try:
        with Path(tools_config_file).open(encoding="utf-8") as f:
            config_data = json.load(f)

        if "tools" in config_data:
            for tool_data in config_data["tools"]:
                tool_config = ToolConfig.from_dict(tool_data, "workspace")
                tools[tool_config.name] = tool_config

        logger.info(f"Loaded {len(tools)} workspace tools from {tools_config_file}")
    except (json.JSONDecodeError, PermissionError, OSError) as e:
        # Fast Fail: 配置文件存在但无法读取应立即抛出
        logger.error(
            f"Failed to load workspace tools from {tools_config_file}: {e}",
            exc_info=True,
        )
        raise RuntimeError(f"Cannot load workspace tools: {e}")

    return tools


class ToolManager:
    """简化的工具管理器 (KISS Principle)

    2层配置加载：
    1. default (builtin + user)
    2. workspace (可选，覆盖default)

    重构说明：
    - 移除复杂的缓存逻辑
    - 简化配置层次：4层 → 2层
    - 简化合并逻辑：简单的字典更新
    - Fast Fail: 配置错误立即抛出异常

    """

    def __init__(
        self,
        workspace_root: str | None = None,
        tools_config=None,
        user_id: str = "default_user",
    ):
        """初始化工具管理器

        Args:
            workspace_root: 工作区路径（可选）
            tools_config: ToolsConfig（来自工作区 config.json），用于按层开关门控；
                None 时全开（向后兼容）
            user_id: 用户 ID（多租户：透传给 per-user 工具，如 MCP）

        Raises:
            RuntimeError: 如果必需的工具加载失败

        """
        self.workspace_root = workspace_root
        self.user_id = user_id or "default_user"
        self._tools_config = tools_config  # config.json → 运行时桥接：工具层门控

        # 加载所有工具（2层：default + workspace）
        self._tools = self._load_tools()

        logger.info(f"ToolManager initialized with {len(self._tools)} total tools")

    def _load_tools(self) -> Dict[str, ToolConfig]:
        """一次性加载所有工具（2层配置）

        Returns:
            合并后的工具配置字典

        Raises:
            RuntimeError: 如果必需的工具加载失败

        """
        tools = {}

        # 工作区 config.tools 的层开关（None → 全开，向后兼容）
        cfg = self._tools_config
        builtin_ok = getattr(cfg, "builtin_tools_enabled", True)
        user_ok = getattr(cfg, "user_tools_enabled", True)
        ws_ok = getattr(cfg, "workspace_tools_enabled", True)
        # 注：system_tools_enabled 无对应加载层（本加载器为 builtin/user/workspace），
        # 预留字段，暂为 no-op。

        # 1. 加载默认工具（builtin + user）
        # Note: knowledge tools are already included in _load_builtin_tools via CustomToolProvider
        try:
            if builtin_ok:
                tools.update(_load_builtin_tools(self.workspace_root, self.user_id))
            if user_ok:
                tools.update(_load_user_tools())
            logger.info(f"Loaded {len(tools)} default tools")
        except Exception as e:
            # Fast Fail: 默认工具加载失败应立即抛出
            logger.error(f"Failed to load default tools: {e}", exc_info=True)
            raise RuntimeError(f"Cannot load default tools: {e}")

        # 2. 如果有工作区，应用工作区覆盖（简单更新）
        if self.workspace_root and ws_ok:
            try:
                workspace_tools = _load_workspace_tools(self.workspace_root)
                override_count = 0
                for name, config in workspace_tools.items():
                    if name in tools:
                        override_count += 1
                        logger.debug(f"Overriding tool '{name}' with workspace config")
                    tools[name] = config

                logger.info(
                    f"Applied {len(workspace_tools)} workspace tools ({override_count} overrides)",
                )
            except Exception as e:
                # 工作区工具加载失败不应阻止系统启动
                logger.warning(f"Failed to load workspace tools (continuing): {e}")

        return tools

    def set_workspace_root(self, workspace_root: str):
        """设置工作区路径并重新加载工具

        Args:
            workspace_root: 新的工作区路径

        """
        self.workspace_root = workspace_root
        self._tools = self._load_tools()
        logger.info(f"Workspace root set to {workspace_root}, tools reloaded")

    def get_builtin_providers_info(self) -> Dict[str, Any]:
        """获取内置工具提供者信息（向后兼容）"""
        default_tools = [t for t in self._tools.values() if t.source_level == "default"]
        return {
            "custom_tools": {
                "provider": "CustomToolProvider",
                "description": "自定义工具提供者，从 custom_tools 包加载工具",
                "count": len(default_tools),
            },
        }

    def reload_builtin_tools(self):
        """重新加载工具（向后兼容）"""
        self._tools = self._load_tools()
        logger.info("Tools reloaded")

    def load_tools(self) -> List[Dict[str, Any]]:
        """加载所有启用的工具

        Returns:
            工具字典列表

        """
        all_tools = []

        for tool_config in self._tools.values():
            if tool_config.enabled:
                tool_dict = tool_config.to_dict()
                # 如果有可调用对象，添加到字典中
                if tool_config.callable:
                    tool_dict["callable"] = tool_config.callable
                all_tools.append(tool_dict)

        logger.info(f"Loaded {len(all_tools)} enabled tools")
        return all_tools

    def get_tool_config(self, tool_name: str) -> ToolConfig | None:
        """获取特定工具的配置

        Args:
            tool_name: 工具名称

        Returns:
            工具配置或None

        """
        return self._tools.get(tool_name)

    def get_all_tool_configs(self) -> Dict[str, ToolConfig]:
        """获取所有工具配置

        Returns:
            工具配置字典的副本

        """
        return self._tools.copy()

    def is_tool_enabled(self, tool_name: str) -> bool:
        """检查工具是否启用

        Args:
            tool_name: 工具名称

        Returns:
            是否启用

        """
        tool_config = self._tools.get(tool_name)
        return tool_config.enabled if tool_config else False

    def get_tools_by_category(self, category: str) -> List[ToolConfig]:
        """按类别获取工具

        Args:
            category: 类别名称

        Returns:
            该类别中已启用的工具配置列表

        """
        return [config for config in self._tools.values() if config.category == category and config.enabled]

    def get_tools_by_source_level(self, level: str) -> List[ToolConfig]:
        """按来源级别获取工具（向后兼容）

        Args:
            level: 来源级别 ("default" 或 "workspace")

        Returns:
            该级别的工具配置列表

        """
        return [config for config in self._tools.values() if config.source_level == level]

    def get_tool_sources(self, tool_name: str) -> Dict[str, bool]:
        """获取工具配置来源信息（向后兼容）

        Args:
            tool_name: 工具名称

        Returns:
            来源信息字典 (builtin, user, workspace)

        """
        tool_config = self._tools.get(tool_name)
        if not tool_config:
            return {"builtin": False, "user": False, "workspace": False}

        # 为了向后兼容，将2层配置映射回3层
        # default -> builtin + user
        # workspace -> workspace
        if tool_config.source_level == "default":
            return {"builtin": True, "user": True, "workspace": False}
        if tool_config.source_level == "workspace":
            return {"builtin": False, "user": False, "workspace": True}
        return {"builtin": False, "user": False, "workspace": False}

    def get_tool_override_info(self, tool_name: str) -> Dict[str, Any]:
        """获取工具覆盖信息（向后兼容）

        Args:
            tool_name: 工具名称

        Returns:
            工具配置信息字典

        """
        sources = self.get_tool_sources(tool_name)
        tool_config = self._tools.get(tool_name)

        if not tool_config:
            return {
                "tool_name": tool_name,
                "sources": sources,
                "active_source": None,
                "is_overridden": False,
                "exists": False,
            }

        # 确定活跃来源
        if sources["workspace"]:
            active_source = "workspace"
        elif sources["builtin"] or sources["user"]:
            active_source = "builtin"  # default映射为builtin
        else:
            active_source = None

        return {
            "tool_name": tool_name,
            "sources": sources,
            "active_source": active_source,
            "is_overridden": (sources["builtin"] and sources["workspace"]) or (sources["user"] and sources["workspace"]),
            "exists": True,
            "config": tool_config.to_dict(),
        }

    def get_all_override_info(self) -> List[Dict[str, Any]]:
        """获取所有工具的覆盖信息（向后兼容）

        Returns:
            被覆盖的工具信息列表

        """
        override_info = []
        for tool_name in self._tools:
            info = self.get_tool_override_info(tool_name)
            # 只返回被覆盖的工具（保持向后兼容）
            if info.get("is_overridden", False):
                override_info.append(info)
        return override_info

    def enable_tool(self, tool_name: str) -> bool:
        """启用工具

        Args:
            tool_name: 工具名称

        Returns:
            是否成功启用

        """
        if tool_name in self._tools:
            self._tools[tool_name].enabled = True
            logger.info(f"Enabled tool: {tool_name}")
            return True
        logger.warning(f"Tool not found: {tool_name}")
        return False

    def disable_tool(self, tool_name: str) -> bool:
        """禁用工具

        Args:
            tool_name: 工具名称

        Returns:
            是否成功禁用

        """
        if tool_name in self._tools:
            self._tools[tool_name].enabled = False
            logger.info(f"Disabled tool: {tool_name}")
            return True
        logger.warning(f"Tool not found: {tool_name}")
        return False

    def update_tool_config(self, tool_name: str, **kwargs) -> bool:
        """更新工具配置

        Args:
            tool_name: 工具名称
            **kwargs: 要更新的配置项

        Returns:
            是否更新成功

        """
        if tool_name not in self._tools:
            logger.warning(f"Tool not found: {tool_name}")
            return False

        tool_config = self._tools[tool_name]
        for key, value in kwargs.items():
            if hasattr(tool_config, key):
                setattr(tool_config, key, value)
                logger.debug(f"Updated {tool_name}.{key} = {value}")

        logger.info(f"Updated tool config: {tool_name}")
        return True

    def reload_configs(self):
        """重新加载所有配置"""
        self._tools = self._load_tools()
        logger.info("All tool configurations reloaded")

    def get_filtered_tool_names(
        self,
        all_tools: List[Dict[str, Any]],
        workspace_settings=None,
    ) -> set[str]:
        """根据工作区设置过滤工具名称

        Args:
            all_tools: 所有工具列表
            workspace_settings: 工作区设置（可选）

        Returns:
            Set[str]: 过滤后的工具名称集合

        """
        if not workspace_settings:
            return {tool["name"] for tool in all_tools}

        allowed_tools = set()

        for tool in all_tools:
            tool_name = tool["name"]

            # MCP工具需要检查设置
            if tool_name.startswith(("mcp_", "use_mcp_")):
                if getattr(workspace_settings, "always_allow_mcp", True):
                    allowed_tools.add(tool_name)
                continue

            # 浏览器工具需要检查设置
            if "browser" in tool_name.lower() or "chrome" in tool_name.lower():
                if getattr(workspace_settings, "always_allow_browser", True):
                    allowed_tools.add(tool_name)
                continue

            # 默认允许其他工具
            allowed_tools.add(tool_name)

        return allowed_tools

    def get_tool_statistics(self) -> Dict[str, Any]:
        """获取工具统计信息（简化版）

        Returns:
            统计信息字典

        """
        # 按来源级别统计
        default_count = len([t for t in self._tools.values() if t.source_level == "default"])
        workspace_count = len([t for t in self._tools.values() if t.source_level == "workspace"])

        stats = {
            "total_tools": len(self._tools),
            "enabled_tools": len([t for t in self._tools.values() if t.enabled]),
            "disabled_tools": len([t for t in self._tools.values() if not t.enabled]),
            "by_category": {},
            "by_source_level": {
                "default": default_count,
                "workspace": workspace_count,
            },
            "builtin_providers": self.get_builtin_providers_info(),
        }

        # 按类别统计
        for tool_config in self._tools.values():
            category = tool_config.category
            if category not in stats["by_category"]:
                stats["by_category"][category] = {"total": 0, "enabled": 0}

            stats["by_category"][category]["total"] += 1
            if tool_config.enabled:
                stats["by_category"][category]["enabled"] += 1

        return stats

    def get_tools_by_group(self, group_name: str) -> List[ToolConfig]:
        """根据工具组名称获取工具配置列表

        Args:
            group_name: 工具组名称 (read, edit, browser, command, mcp, modes)

        Returns:
            List[ToolConfig]: 该组中的工具配置列表

        """
        if group_name not in TOOL_GROUPS:
            logger.warning(f"Unknown tool group: {group_name}")
            return []

        group_config = ToolGroupConfig.from_dict(TOOL_GROUPS[group_name])
        tools = []

        # 获取主要工具
        for tool_name in group_config.tools:
            tool_config = self.get_tool_config(tool_name)
            if tool_config and tool_config.enabled:
                tools.append(tool_config)

        # 获取自定义工具
        for tool_name in group_config.custom_tools:
            tool_config = self.get_tool_config(tool_name)
            if tool_config and tool_config.enabled:
                tools.append(tool_config)

        logger.debug(f"Found {len(tools)} enabled tools in group '{group_name}'")
        return tools

    def get_tool_groups(self) -> Dict[str, ToolGroupConfig]:
        """获取所有工具组配置

        Returns:
            Dict[str, ToolGroupConfig]: 所有工具组的配置字典

        """
        return {group_name: ToolGroupConfig.from_dict(group_data) for group_name, group_data in TOOL_GROUPS.items()}

    def get_group_tools(self, group_names: List[Any]) -> set[str]:
        """获取指定工具组中的所有工具名称

        Args:
            group_names: 工具组名称列表（可能包含字符串或字典）

        Returns:
            Set[str]: 所有工具名称的集合

        """
        tool_names = set()

        for item in group_names:
            # 处理字典类型的group配置
            if isinstance(item, dict):
                group_name = item.get("name") or item.get("slug", "")
                if not group_name:
                    logger.warning(f"Invalid group config (no name/slug): {item}")
                    continue
            else:
                group_name = str(item)

            if group_name not in TOOL_GROUPS:
                logger.warning(f"Unknown tool group: {group_name}")
                continue

            group_config = ToolGroupConfig.from_dict(TOOL_GROUPS[group_name])

            # 添加主要工具
            tool_names.update(group_config.tools)

            # 添加自定义工具
            tool_names.update(group_config.custom_tools)

        logger.debug(f"Found {len(tool_names)} tool names in groups: {group_names}")
        return tool_names

    def get_available_tools_with_groups(self, group_names: List[str]) -> set[str]:
        """根据 mode 声明的工具组获取可用工具列表

        Args:
            group_names: 工具组名称列表

        Returns:
            Set[str]: 指定工具组中的工具名称集合

        """
        available_tools = self.get_group_tools(group_names)

        logger.debug(
            f"Found {len(available_tools)} available tools for groups: {group_names}",
        )
        return available_tools

    async def cleanup(self) -> bool:
        """清理资源（WorkspaceContext销毁时调用）

        Returns:
            是否清理成功

        """
        try:
            # 清空工具字典
            self._tools.clear()
            logger.info("ToolManager cleaned up successfully")
            return True

        except Exception as e:
            logger.error(f"Error cleaning up ToolManager: {e}", exc_info=True)
            return False
