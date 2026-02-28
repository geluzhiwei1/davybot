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
from typing import Any

from dawei.config import get_dawei_home

from .tool_provider import CustomToolProvider

logger = logging.getLogger(__name__)


# 始终可用的工具列表，参考 TypeScript 版本结构
ALWAYS_AVAILABLE_TOOLS = {
    "ask_followup_question",
    "attempt_completion",
    "switch_mode",
    "run_slash_command",
    "timer",
}

# 工具组定义，参考 TypeScript 版本结构
TOOL_GROUPS = {
    "read": {
        "tools": [
            "read_file",
            "fetch_instructions",
            "search_files",
            "list_files",
            "list_code_definition_names",
            "codebase_search",
        ],
    },
    "edit": {
        "tools": ["apply_diff", "write_to_file", "insert_content", "generate_image"],
        "custom_tools": ["search_and_replace"],
    },
    "browser": {
        "tools": ["browser_action"],
    },
    "command": {
        "tools": ["execute_command"],
    },
    "mcp": {
        "tools": ["use_mcp_tool", "access_mcp_resource"],
    },
    "modes": {
        "tools": ["switch_mode", "new_task"],
        "always_available": True,
    },
    # 任务图和 workflow 工具组
    "task_graph": {
        "tools": [
            "create_task_graph",
            "add_task_node",
            "set_task_dependency",
            "get_task_graph",
            "execute_task_graph",
        ],
    },
    "workflow": {
        "tools": [
            "new_task",
            "update_todo_list",
            "get_task_status",
            "analyze_task_complexity",
            "generate_todo_plan",
            "validate_todo_plan",
            "adjust_todo_order",
            "timer",
        ],
    },
}


@dataclass
class ToolGroupConfig:
    """工具组配置数据类"""

    tools: list[str] = field(default_factory=list)
    always_available: bool = False
    custom_tools: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ToolGroupConfig":
        """从字典创建工具组配置"""
        return cls(
            tools=data.get("tools", []),
            always_available=data.get("always_available", False),
            custom_tools=data.get("custom_tools", []),
        )

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "tools": self.tools,
            "always_available": self.always_available,
            "custom_tools": self.custom_tools,
        }


@dataclass
class ToolConfig:
    """工具配置数据类"""

    name: str
    description: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    callable: Any = None
    enabled: bool = True
    priority: int = 50
    category: str = "general"
    source_level: str = "builtin"  # builtin, system, user, workspace
    config_overrides: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any], source_level: str = "builtin") -> "ToolConfig":
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

    def to_dict(self) -> dict[str, Any]:
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


def _load_builtin_tools(workspace_path: str | None = None) -> dict[str, ToolConfig]:
    """加载内置工具 (CustomToolProvider)

    Args:
        workspace_path: 工作区路径（可选）

    Returns:
        工具配置字典

    Raises:
        RuntimeError: 如果必需的工具加载失败

    """
    tools = {}

    # 从 CustomToolProvider 加载自定义工具
    try:
        custom_provider = CustomToolProvider(workspace_path=workspace_path)
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


def _load_user_tools() -> dict[str, ToolConfig]:
    """加载用户级工具配置

    Returns:
        工具配置字典

    Raises:
        RuntimeError: 如果配置文件存在但加载失败

    """
    tools = {}
    user_config_dir = Path(get_dawei_home()) / "configs"
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


def _load_workspace_tools(workspace_path: str) -> dict[str, ToolConfig]:
    """加载工作区级工具配置

    Args:
        workspace_path: 工作区路径

    Returns:
        工具配置字典

    Raises:
        RuntimeError: 如果配置文件存在但加载失败

    """
    tools = {}
    workspace_dir = Path(workspace_path)
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

    def __init__(self, workspace_path: str | None = None):
        """初始化工具管理器

        Args:
            workspace_path: 工作区路径（可选）

        Raises:
            RuntimeError: 如果必需的工具加载失败

        """
        self.workspace_path = workspace_path

        # 加载所有工具（2层：default + workspace）
        self._tools = self._load_tools()

        logger.info(f"ToolManager initialized with {len(self._tools)} total tools")

    def _load_tools(self) -> dict[str, ToolConfig]:
        """一次性加载所有工具（2层配置）

        Returns:
            合并后的工具配置字典

        Raises:
            RuntimeError: 如果必需的工具加载失败

        """
        tools = {}

        # 1. 加载默认工具（builtin + user）
        try:
            tools.update(_load_builtin_tools(self.workspace_path))
            tools.update(_load_user_tools())
            logger.info(f"Loaded {len(tools)} default tools")
        except Exception as e:
            # Fast Fail: 默认工具加载失败应立即抛出
            logger.error(f"Failed to load default tools: {e}", exc_info=True)
            raise RuntimeError(f"Cannot load default tools: {e}")

        # 2. 如果有工作区，应用工作区覆盖（简单更新）
        if self.workspace_path:
            try:
                workspace_tools = _load_workspace_tools(self.workspace_path)
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

    def set_workspace_path(self, workspace_path: str):
        """设置工作区路径并重新加载工具

        Args:
            workspace_path: 新的工作区路径

        """
        self.workspace_path = workspace_path
        self._tools = self._load_tools()
        logger.info(f"Workspace path set to {workspace_path}, tools reloaded")

    def get_builtin_providers_info(self) -> dict[str, Any]:
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

    def load_tools(self) -> list[dict[str, Any]]:
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

    def get_all_tool_configs(self) -> dict[str, ToolConfig]:
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

    def get_tools_by_category(self, category: str) -> list[ToolConfig]:
        """按类别获取工具

        Args:
            category: 类别名称

        Returns:
            该类别中已启用的工具配置列表

        """
        return [config for config in self._tools.values() if config.category == category and config.enabled]

    def get_tools_by_source_level(self, level: str) -> list[ToolConfig]:
        """按来源级别获取工具（向后兼容）

        Args:
            level: 来源级别 ("default" 或 "workspace")

        Returns:
            该级别的工具配置列表

        """
        return [config for config in self._tools.values() if config.source_level == level]

    def get_tool_sources(self, tool_name: str) -> dict[str, bool]:
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

    def get_tool_override_info(self, tool_name: str) -> dict[str, Any]:
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

    def get_all_override_info(self) -> list[dict[str, Any]]:
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
        all_tools: list[dict[str, Any]],
        workspace_settings=None,
    ) -> set[str]:
        """根据工作区设置过滤工具名称，确保始终可用工具在任何模式下都可用

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

            # 始终可用的工具总是允许的
            if self.is_always_available(tool_name):
                allowed_tools.add(tool_name)
                continue

            # 基本工具总是允许的
            if tool_name in [
                "read_file",
                "write_to_file",
                "list_files",
                "search_files",
            ]:
                allowed_tools.add(tool_name)
                continue

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

    def get_tool_statistics(self) -> dict[str, Any]:
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

    def get_tools_by_group(self, group_name: str) -> list[ToolConfig]:
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

    def get_tool_groups(self) -> dict[str, ToolGroupConfig]:
        """获取所有工具组配置

        Returns:
            Dict[str, ToolGroupConfig]: 所有工具组的配置字典

        """
        return {group_name: ToolGroupConfig.from_dict(group_data) for group_name, group_data in TOOL_GROUPS.items()}

    def get_group_tools(self, group_names: list[Any]) -> set[str]:
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

    def get_always_available_tools(self) -> set[str]:
        """获取始终可用工具集合

        Returns:
            Set[str]: 始终可用的工具名称集合

        """
        return ALWAYS_AVAILABLE_TOOLS.copy()

    def is_always_available(self, tool_name: str) -> bool:
        """检查工具是否始终可用

        Args:
            tool_name: 工具名称

        Returns:
            bool: 如果工具始终可用则返回 True，否则返回 False

        """
        return tool_name in ALWAYS_AVAILABLE_TOOLS

    def get_available_tools_with_groups(self, group_names: list[str]) -> set[str]:
        """结合工具组和始终可用工具获取最终可用工具列表

        Args:
            group_names: 工具组名称列表

        Returns:
            Set[str]: 包含指定工具组工具和始终可用工具的集合

        """
        # 获取指定工具组的工具
        group_tools = self.get_group_tools(group_names)

        # 添加始终可用的工具
        always_available = self.get_always_available_tools()

        # 合并两个集合
        available_tools = group_tools.union(always_available)

        logger.debug(
            f"Found {len(available_tools)} available tools (groups: {group_names}, always available: {len(always_available)})",
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
