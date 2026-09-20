# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Workspace工具管理器

负责工作区的工具配置、加载、过滤和MCP管理
"""

import logging
from pathlib import Path
from typing import List, Dict, TYPE_CHECKING, Any

from dawei.tools.mcp_tool_manager import MCPConfig, MCPToolManager, get_or_create_mcp_manager
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

    def __init__(self, workspace_root: Path, user_id: str = "default_user"):
        """初始化工具管理器

        Args:
            workspace_root: 工作区路径
            user_id: 用户 ID（多租户：透传给 per-user 工具/配置合并）

        """
        self.workspace_root = Path(workspace_root).resolve()
        self.absolute_path = str(self.workspace_root)
        self.user_id = user_id or "default_user"

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

        # 创建 MCP 工具管理器，传入工作区路径以支持工作区级配置。
        # 走进程级注册表：与 WorkspaceContext / MCP 工具类同 key 共享同一实例，
        # reload/connect 状态彼此立即可见。
        self.mcp_tool_manager = get_or_create_mcp_manager(workspace_root=self.absolute_path, user_id=self.user_id)
        logger.info("MCPToolManager created.")

        # 记录 MCP 配置统计信息
        stats = self.mcp_tool_manager.get_statistics()
        by_source = stats.get("by_source_level", {})
        logger.info(
            f"MCP configurations loaded: {stats['total_servers']} total, system: {by_source.get('system', 0)}, user: {by_source.get('user', 0)}, workspace: {by_source.get('workspace', 0)}",
        )

        # 记录覆盖信息
        override_info = stats.get("override_summary", {})
        if override_info.get("total_overridden", 0) > 0:
            logger.info(f"Found {override_info['total_overridden']} overridden MCP configs")
            for info in override_info.get("override_details", [])[:3]:  # 只记录前3个
                logger.info(
                    f"  - {info['server_name']}: {info['active_source']} overrides other sources",
                )

        # 自动连接已配置 server（后台任务，不阻塞 workspace 初始化）：
        # MCP 一级工具注入依赖 connected 状态；local relay 壳未上线时
        # FAST FAIL 仅记录告警。持有 task 引用防 GC（asyncio 文档约定）。
        import asyncio

        try:
            task = asyncio.get_running_loop().create_task(self._autoconnect_mcp())
            if not hasattr(self, "_mcp_connect_tasks"):
                self._mcp_connect_tasks = set()
            self._mcp_connect_tasks.add(task)
            task.add_done_callback(self._mcp_connect_tasks.discard)
        except RuntimeError:  # 无运行中的 loop（同步初始化路径）
            pass

    async def _autoconnect_mcp(self) -> None:
        """后台自动连接 MCP servers（见 MCPToolManager.auto_connect_all）。"""
        try:
            await self.mcp_tool_manager.auto_connect_all()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"MCP auto-connect failed: {e}")

    async def _initialize_tools(self):
        """初始化工具管理器"""
        logger.info("Initializing tools...")

        # 读取工作区 tools 段用于层门控（config.json → 运行时桥接）
        # override-or-inherit：合并用户级 tools 默认 + 工作区覆盖
        ws_cfg = self._read_workspace_config()
        tools_cfg = self._effective_tools_config(ws_cfg)

        # 创建工具管理器，传入工作区路径以支持工作区级配置
        self.tool_manager = ToolManager(workspace_root=self.absolute_path, tools_config=tools_cfg, user_id=self.user_id)
        logger.info("ToolManager created.")

        # 初始化Skills工具 - 直接使用 SkillManager
        self._init_skill_manager()
        self._skills_tools = self._create_skills_tools()
        logger.info(f"Created {len(self._skills_tools)} skills tools")

    def _effective_tools_config(self, ws_cfg):
        """override-or-inherit：合并 user 级 tools 默认（configs/skills_tools.json）+ ws 覆盖。

        ws 非 None 字段胜出。失败回退到 ws raw（None 时按 ToolManager 默认全开）。
        """
        try:
            from dawei.api.users.skills_tools import load_user_skills_tools
            from dawei.workspace.models import ToolsConfig

            user_cfg = load_user_skills_tools(self.user_id)
            user_tools = user_cfg.get("tools", {}) or {}
            ws_tools_dict = ws_cfg.tools.model_dump() if (ws_cfg is not None and ws_cfg.tools) else {}
            eff = {**user_tools, **{k: v for k, v in ws_tools_dict.items() if v is not None}}
            return ToolsConfig(**eff)
        except Exception as e:
            logger.warning(f"effective tools config merge failed, fallback to ws raw: {e}")
            return ws_cfg.tools if ws_cfg is not None else None

    def _read_workspace_config(self):
        """从 {workspace}/.dawei/config.json 读取 WorkspaceConfig；失败返回 None（按默认全开）。

        config.json 由前端工作区设置写入；这里读取用于 skills/tools 门控（config.json →
        运行时桥接）。无文件或解析失败时返回 None，调用方按默认（全开）处理。
        """
        try:
            import json

            from dawei.workspace.models import WorkspaceConfig

            cfg_file = self.workspace_root / ".dawei" / "config.json"
            if not cfg_file.exists():
                return None
            with cfg_file.open("r", encoding="utf-8") as f:
                return WorkspaceConfig.from_dict(json.load(f))
        except Exception as e:
            logger.warning(f"read workspace config failed, defaults apply: {e}")
            return None

    def _init_skill_manager(self):
        """初始化 SkillManager - 复用其发现逻辑"""
        from dawei.tools.skill_manager import SkillManager

        ws_cfg = self._read_workspace_config()
        # override-or-inherit：合并用户级 skills 默认 + 工作区覆盖
        eff_skills = self._effective_skills_config(ws_cfg)

        # skills.enabled=False → 完全不加载 skills
        if not eff_skills.get("enabled", True):
            logger.info(
                "Skills disabled by effective config (user+ws merged); skipping"
            )
            self.skill_manager = None
            return

        # 构建 skills roots（按优先级从高到低）
        roots = []

        # Level 1: Workspace 级别
        roots.append(Path(self.absolute_path))

        # Level 2: User 级别
        from dawei import get_dawei_home

        roots.append(get_dawei_home())

        logger.info(f"Initializing SkillManager with {len(roots)} roots: {roots}")

        # 获取当前 mode（用于 mode-specific skills）
        current_mode = None
        if self.mode_manager:
            current_mode = self.mode_manager.current_mode

        logger.debug(f"Current mode for skills: {current_mode}")

        # 创建 SkillManager（它会自动发现 skills）
        self.skill_manager = SkillManager(skills_roots=roots, current_mode=current_mode)

        # auto_discovery=False → 建 manager 但不自动发现（skills 系统开，但不扫描）
        if not eff_skills.get("auto_discovery", True):
            logger.info(
                "Skills auto_discovery disabled by effective config; "
                "SkillManager created without discovery"
            )
            return

        # 触发发现
        self.skill_manager.discover_skills()
        logger.info(f"SkillManager discovered {len(self.skill_manager._skills)} skills")

    def _effective_skills_config(self, ws_cfg) -> dict:
        """override-or-inherit：合并 user 级 skills 默认 + ws 覆盖（ws 非 None 胜）。"""
        try:
            from dawei.api.users.skills_tools import load_user_skills_tools

            user_cfg = load_user_skills_tools(self.user_id)
            user_skills = user_cfg.get("skills", {}) or {}
            ws_skills = ws_cfg.skills.model_dump() if (ws_cfg is not None and ws_cfg.skills) else {}
            return {**user_skills, **{k: v for k, v in ws_skills.items() if v is not None}}
        except Exception as e:
            logger.warning(f"effective skills config merge failed, fallback to ws raw: {e}")
            if ws_cfg is not None and ws_cfg.skills:
                return ws_cfg.skills.model_dump()
            return {}

    def _create_skills_tools(self) -> list:
        """创建 Skills 工具 - 使用已初始化的 SkillManager"""
        # skills 被工作区配置禁用时（_init_skill_manager 置 None），不产出 skills 工具
        if self.skill_manager is None:
            return []
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
    def allowed_tools(self) -> List[Dict[str, Any]]:
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

            # MCP 一级工具：已连接 server 的工具直接进工具面（mcp__ 前缀）。
            # 受 workspace_settings.always_allow_mcp（UI: mcpEnabled）门控——
            # 关闭时不可见也不可执行
            try:
                from dawei.tools.mcp_dynamic_tools import build_mcp_tool_dicts

                mcp_dynamic = build_mcp_tool_dicts(self.mcp_tool_manager)
                if mcp_dynamic:
                    mcp_allowed = self._get_filtered_tool_names(mcp_dynamic)
                    tools.extend(t for t in mcp_dynamic if t["name"] in mcp_allowed)
            except Exception:  # noqa: BLE001
                logger.exception("build first-class MCP tools (wrapper) failed")

            return tools
        return []

    def _get_filtered_tool_names(self, tools: List[Dict[str, Any]]) -> set[str]:
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
                "write_text_file",
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

    def get_tools_by_category(self, category: str) -> List[Dict[str, Any]]:
        """按类别获取工具"""
        if self.tool_manager:
            tool_configs = self.tool_manager.get_tools_by_category(category)
            return [config.to_dict() for config in tool_configs]
        return []

    def get_tool_statistics(self) -> Dict[str, Any]:
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

    def get_tool_sources(self, tool_name: str) -> Dict[str, bool]:
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

    def get_all_mcp_configs(self) -> Dict[str, MCPConfig]:
        """获取所有MCP配置"""
        if self.mcp_tool_manager:
            return self.mcp_tool_manager.get_all_configs()
        return {}

    def get_mcp_server_info(self, server_name: str):
        """获取MCP服务器信息"""
        if self.mcp_tool_manager:
            return self.mcp_tool_manager.get_server_info(server_name)
        return None

    def get_all_mcp_servers(self) -> Dict[str, Any]:
        """获取所有MCP服务器信息"""
        if self.mcp_tool_manager:
            return self.mcp_tool_manager.get_all_servers()
        return {}

    def get_mcp_config_sources(self, server_name: str) -> Dict[str, bool]:
        """获取MCP配置来源信息"""
        if self.mcp_tool_manager:
            return self.mcp_tool_manager.get_config_sources(server_name)
        return {}

    def get_mcp_statistics(self) -> Dict[str, Any]:
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

    async def connect_all_mcp_servers(self) -> Dict[str, bool]:
        """连接所有MCP服务器"""
        if self.mcp_tool_manager:
            return await self.mcp_tool_manager.connect_all_servers()
        return {}

    async def disconnect_all_mcp_servers(self) -> Dict[str, bool]:
        """断开所有MCP服务器连接"""
        if self.mcp_tool_manager:
            return await self.mcp_tool_manager.disconnect_all_servers()
        return {}

    def reload_mcp_configs(self):
        """重新加载MCP配置"""
        if self.mcp_tool_manager:
            self.mcp_tool_manager.reload_configs()
            logger.info("MCP configurations reloaded")
