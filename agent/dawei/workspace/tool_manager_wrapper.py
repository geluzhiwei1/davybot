# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Workspace工具管理器

负责工作区的工具配置、加载、过滤和MCP管理
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dawei.tools.mcp_tool_manager import MCPConfig, MCPToolManager
from dawei.tools.tool_manager import ToolManager

if TYPE_CHECKING:
    from .models import WorkspaceSettings


logger = logging.getLogger(__name__)


class WorkspaceToolManager:
    """工作区工具管理器

    职责：
    - 初始化和管理工具管理器（ToolManager）
    - 初始化和管理MCP工具管理器（MCPToolManager）
    - 工具配置的加载和重新加载
    - 工具启用/禁用管理
    - 工具过滤（按模式、按工作区设置）
    - MCP服务器连接管理
    - 工具和MCP统计信息
    """

    def __init__(self, workspace_path: Path):
        """初始化工具管理器

        Args:
            workspace_path: 工作区路径

        """
        self.workspace_path = Path(workspace_path).resolve()
        self.absolute_path = str(self.workspace_path)

        # 工具管理器
        self.tool_manager: ToolManager | None = None
        self.mcp_tool_manager: MCPToolManager | None = None

        # SkillManager（用于 skills 发现和管理）
        self.skill_manager = None

        # Skills工具
        self._skills_tools: list | None = None

        # 工作区设置（由外部注入）
        self.workspace_settings: WorkspaceSettings | None = None

        # 模式管理器（由外部注入）
        self.mode_manager = None

        logger.info(f"WorkspaceToolManager created for: {self.absolute_path}")

    # ==================== 初始化方法 ====================

    async def initialize(self, mode_manager=None):
        """初始化工具管理器

        Args:
            mode_manager: 模式管理器（可选）

        """
        self.mode_manager = mode_manager
        await self._initialize_tools()
        await self._initialize_mcp_tools()

    async def _initialize_mcp_tools(self):
        """初始化MCP工具管理器"""
        logger.info("Initializing MCP tool manager...")

        # 创建 MCP 工具管理器，传入工作区路径以支持工作区级配置
        self.mcp_tool_manager = MCPToolManager(workspace_path=self.absolute_path)
        logger.info("MCPToolManager created.")

        # 记录 MCP 配置统计信息
        stats = self.mcp_tool_manager.get_statistics()
        logger.info(
            f"MCP configurations loaded: {stats['total_servers']} total, system: {stats['by_source_level']['system']}, user: {stats['by_source_level']['user']}, workspace: {stats['by_source_level']['workspace']}",
        )

        # 记录覆盖信息
        override_info = stats.get("override_summary", {})
        if override_info.get("total_overridden", 0) > 0:
            logger.info(f"Found {override_info['total_overridden']} overridden MCP configs")
            for info in override_info.get("override_details", [])[:3]:  # 只记录前3个
                logger.info(
                    f"  - {info['server_name']}: {info['active_source']} overrides other sources",
                )

    async def _initialize_tools(self):
        """初始化工具管理器"""
        logger.info("Initializing tools...")

        # 创建工具管理器，传入工作区路径以支持工作区级配置
        self.tool_manager = ToolManager(workspace_path=self.absolute_path)
        logger.info("ToolManager created.")

        # 初始化Skills工具 - 直接使用 SkillManager
        self._init_skill_manager()
        self._skills_tools = self._create_skills_tools()
        logger.info(f"Created {len(self._skills_tools)} skills tools")

    def _init_skill_manager(self):
        """初始化 SkillManager - 复用其发现逻辑"""
        from dawei.tools.skill_manager import SkillManager

        # 构建 skills roots（按优先级从高到低）
        roots = []

        # Level 1: Workspace 级别
        roots.append(Path(self.absolute_path))

        # Level 2: User 级别
        roots.append(Path.home())

        logger.info(f"Initializing SkillManager with {len(roots)} roots: {roots}")

        # 获取当前 mode（用于 mode-specific skills）
        current_mode = None
        if self.mode_manager:
            current_mode = self.mode_manager.current_mode

        logger.debug(f"Current mode for skills: {current_mode}")

        # 创建 SkillManager（它会自动发现 skills）
        self.skill_manager = SkillManager(skills_roots=roots, current_mode=current_mode)

        # 触发发现
        self.skill_manager.discover_skills()
        logger.info(f"SkillManager discovered {len(self.skill_manager._skills)} skills")

    def _create_skills_tools(self) -> list:
        """创建 Skills 工具 - 使用已初始化的 SkillManager"""
        try:
            from dawei.tools.custom_tools.skills_tool import (
                GetSkillTool,
                ListSkillResourcesTool,
                ListSkillsTool,
                ReadSkillResourceTool,
                SearchSkillsTool,
            )

            return [
                ListSkillsTool(self.skill_manager),
                SearchSkillsTool(self.skill_manager),
                GetSkillTool(self.skill_manager),
                ListSkillResourcesTool(self.skill_manager),
                ReadSkillResourceTool(self.skill_manager),
            ]

        except ImportError as e:
            logger.warning(f"Failed to import skills tools: {e}")
            return []

    async def update_allowed_tools(self):
        """更新允许的工具列表"""
        logger.debug("Updating allowed tools...")
        # 工具列表更新逻辑（如果有需要的话）

    # ==================== 工具查询和配置 ====================

    @property
    def allowed_tools(self) -> list[dict[str, Any]]:
        """获取允许的工具列表"""
        if self.tool_manager:
            # 从 ToolManager 获取最新数据并应用工作区过滤
            all_tools = self.tool_manager.load_tools()
            allowed_tool_names = self._get_filtered_tool_names(all_tools)
            tools = [tool for tool in all_tools if tool["name"] in allowed_tool_names]

            # 添加skills工具
            if self._skills_tools:
                for skill_tool in self._skills_tools:
                    tools.append(
                        {
                            "name": skill_tool.name,
                            "description": skill_tool.description,
                            "original_tool": skill_tool,
                            "category": "skills",
                            "enabled": True,
                        },
                    )

            return tools
        return []

    def _get_filtered_tool_names(self, tools: list[dict[str, Any]]) -> set[str]:
        """根据工作区设置过滤工具名称"""
        if self.tool_manager:
            return self.tool_manager.get_filtered_tool_names(tools, self.workspace_settings)
        # 如果 ToolManager 不可用，使用基本过滤逻辑
        if not self.workspace_settings:
            return {tool["name"] for tool in tools}

        allowed_tools = set()

        for tool in tools:
            tool_name = tool["name"]

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
                if self.workspace_settings.always_allow_mcp:
                    allowed_tools.add(tool_name)
                continue

            # 浏览器工具需要检查设置
            if "browser" in tool_name.lower() or "chrome" in tool_name.lower():
                if self.workspace_settings.always_allow_browser:
                    allowed_tools.add(tool_name)
                continue

            # 默认允许其他工具
            allowed_tools.add(tool_name)

        return allowed_tools

    def get_tool_config(self, tool_name: str):
        """获取特定工具的配置"""
        if self.tool_manager:
            return self.tool_manager.get_tool_config(tool_name)
        return None

    def is_tool_enabled(self, tool_name: str) -> bool:
        """检查工具是否启用"""
        if self.tool_manager:
            return self.tool_manager.is_tool_enabled(tool_name)
        return False

    def enable_tool(self, tool_name: str) -> bool:
        """启用工具"""
        if self.tool_manager:
            success = self.tool_manager.enable_tool(tool_name)
            if success:
                logger.info(f"Tool '{tool_name}' enabled successfully")
            return success
        return False

    def disable_tool(self, tool_name: str) -> bool:
        """禁用工具"""
        if self.tool_manager:
            success = self.tool_manager.disable_tool(tool_name)
            if success:
                logger.info(f"Tool '{tool_name}' disabled successfully")
            return success
        return False

    def get_tools_by_category(self, category: str) -> list[dict[str, Any]]:
        """按类别获取工具"""
        if self.tool_manager:
            tool_configs = self.tool_manager.get_tools_by_category(category)
            return [config.to_dict() for config in tool_configs]
        return []

    def get_mode_available_tools(self, mode: str) -> dict[str, Any]:
        """获取指定模式下可用的工具

        Args:
            mode: 模式名称

        Returns:
            Dict[str, Any]: 过滤后的工具字典

        Raises:
            ValueError: 当工具管理器或模式管理器未初始化时

        """
        logger.debug(f"get_mode_available_tools called for mode: {mode}")

        # 获取所有工具
        if self.tool_manager is None:
            raise ValueError("tool_manager is None, cannot get available tools")

        all_tools = self.tool_manager.load_tools()
        logger.debug(f"Loaded {len(all_tools)} tools from tool_manager")

        # 获取模式配置
        if self.mode_manager is None:
            logger.warning("mode_manager is None, returning all tools without mode filtering")
            filtered_tools = all_tools
        else:
            mode_info = self.mode_manager.get_mode_info(mode)
            logger.debug(f"Mode info for {mode}: {mode_info}")

            # 根据模式过滤工具
            filtered_tools = self._filter_tools_by_mode(all_tools, mode_info)

        # 应用工作区设置过滤
        if self.workspace_settings:
            allowed_tool_names = self._get_filtered_tool_names(filtered_tools)
            final_tools = [tool for tool in filtered_tools if tool["name"] in allowed_tool_names]
        else:
            final_tools = filtered_tools

        return {
            "tools": final_tools,
            "mode": mode,
            "total_count": len(all_tools),
            "mode_filtered_count": len(filtered_tools),
            "final_count": len(final_tools),
            "workspace_settings_applied": self.workspace_settings is not None,
        }

    def _filter_tools_by_mode(
        self,
        tools: list[dict[str, Any]],
        mode_info: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """根据模式信息过滤工具

        Args:
            tools: 工具列表
            mode_info: 模式信息

        Returns:
            过滤后的工具列表

        """
        if not mode_info:
            return tools

        filtered_tools = []
        for tool in tools:
            tool_name = tool.get("name")

            # 检查工具是否在模式的允许列表中
            allowed_tools = mode_info.get("allowed_tools", [])
            denied_tools = mode_info.get("denied_tools", [])

            # 如果有明确的允许列表，只允许列表中的工具
            if allowed_tools:
                if tool_name in allowed_tools:
                    filtered_tools.append(tool)
            # 如果有明确的拒绝列表，排除被拒绝的工具
            elif denied_tools and tool_name in denied_tools:
                continue
            else:
                # 默认允许工具
                filtered_tools.append(tool)

        return filtered_tools

    def get_tool_statistics(self) -> dict[str, Any]:
        """获取工具统计信息"""
        if self.tool_manager:
            stats = self.tool_manager.get_tool_statistics()

            # 添加工作区特定的统计信息
            all_tools = self.tool_manager.load_tools()
            allowed_tool_names = self._get_filtered_tool_names(all_tools)
            stats["workspace_specific"] = {
                "available_tools_count": len(all_tools),
                "allowed_tools_count": len(allowed_tool_names),
                "workspace_path": self.absolute_path,
            }

            return stats
        return {}

    def reload_tool_configs(self):
        """重新加载工具配置"""
        if self.tool_manager:
            # 重新加载所有配置
            self.tool_manager.reload_configs()

            # 记录重新加载后的统计信息
            stats = self.tool_manager.get_tool_statistics()
            logger.info(
                f"Tool configurations reloaded: {stats['total_tools']} total, {stats['overridden_tools']} overridden",
            )

        logger.info("Tool configurations reloaded")

    def get_tool_sources(self, tool_name: str) -> dict[str, bool]:
        """获取工具配置来源信息"""
        if self.tool_manager:
            return self.tool_manager.get_tool_sources(tool_name)
        return {}

    # ==================== MCP管理方法 ====================

    def get_mcp_config(self, server_name: str) -> MCPConfig | None:
        """获取指定服务器的MCP配置"""
        if self.mcp_tool_manager:
            return self.mcp_tool_manager.get_config(server_name)
        return None

    def get_all_mcp_configs(self) -> dict[str, MCPConfig]:
        """获取所有MCP配置"""
        if self.mcp_tool_manager:
            return self.mcp_tool_manager.get_all_configs()
        return {}

    def get_mcp_server_info(self, server_name: str):
        """获取MCP服务器信息"""
        if self.mcp_tool_manager:
            return self.mcp_tool_manager.get_server_info(server_name)
        return None

    def get_all_mcp_servers(self) -> dict[str, Any]:
        """获取所有MCP服务器信息"""
        if self.mcp_tool_manager:
            return self.mcp_tool_manager.get_all_servers()
        return {}

    def get_mcp_config_sources(self, server_name: str) -> dict[str, bool]:
        """获取MCP配置来源信息"""
        if self.mcp_tool_manager:
            return self.mcp_tool_manager.get_config_sources(server_name)
        return {}

    def get_mcp_statistics(self) -> dict[str, Any]:
        """获取MCP统计信息"""
        if self.mcp_tool_manager:
            return self.mcp_tool_manager.get_statistics()
        return {}

    async def connect_mcp_server(self, server_name: str) -> bool:
        """连接MCP服务器"""
        if self.mcp_tool_manager:
            return await self.mcp_tool_manager.connect_server(server_name)
        return False

    async def disconnect_mcp_server(self, server_name: str) -> bool:
        """断开MCP服务器连接"""
        if self.mcp_tool_manager:
            return await self.mcp_tool_manager.disconnect_server(server_name)
        return False

    async def connect_all_mcp_servers(self) -> dict[str, bool]:
        """连接所有MCP服务器"""
        if self.mcp_tool_manager:
            return await self.mcp_tool_manager.connect_all_servers()
        return {}

    async def disconnect_all_mcp_servers(self) -> dict[str, bool]:
        """断开所有MCP服务器连接"""
        if self.mcp_tool_manager:
            return await self.mcp_tool_manager.disconnect_all_servers()
        return {}

    def reload_mcp_configs(self):
        """重新加载MCP配置"""
        if self.mcp_tool_manager:
            self.mcp_tool_manager.reload_configs()
            logger.info("MCP configurations reloaded")
