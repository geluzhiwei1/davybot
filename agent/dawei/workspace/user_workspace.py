# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""用户工作区实体类 - 重构版本

提供工作区管理、对话管理、配置加载和工具集成功能
核心特性：
- 持有Conversation属性作为当前对话
- 持有ConversationHistoryManager管理历史对话
- 支持工作区生命周期管理
- 不考虑后向兼容
"""

import asyncio
import json
import logging
import os
import uuid
from datetime import UTC, datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dawei.config import get_dawei_home
from dawei.conversation.conversation import Conversation, create_conversation
# from dawei.core.events import CORE_EVENT_BUS  # REMOVED: CORE_EVENT_BUS deleted
from dawei.entity.llm_config import LLMConfig
from dawei.task_graph.task_node_data import TaskContext
from dawei.tools.mcp_tool_manager import MCPConfig, MCPToolManager

from .exceptions import (
    ConversationPersistenceError,
    TaskGraphPersistenceError,
    WorkspaceInfoPersistenceError,
)
from .models import WorkspaceInfo, WorkspaceSettings
from .persistence_manager import ResourceType, WorkspacePersistenceManager

logger = logging.getLogger(__name__)

# Import super mode utilities
from dawei.core.super_mode import is_super_mode_enabled, log_security_bypass

if TYPE_CHECKING:
    from dawei.conversation.conversation_history_manager import (
        ConversationHistoryManager,
    )
    from dawei.llm_api.llm_provider import LLMProvider
    from dawei.tools.tool_manager import ToolManager


class UserWorkspace:
    """用户工作区类 - 重构版本

    核心功能：
    - 持有Conversation属性作为当前对话
    - 持有ConversationHistoryManager管理历史对话
    - 支持工作区生命周期管理
    - 提供配置加载和工具集成功能
    """

    def __init__(self, workspace_path: str):
        """初始化用户工作区

        Args:
            workspace_path: 工作区路径

        """
        self.logger = logging.getLogger(__name__)
        self.logger.info(f"UserWorkspace __init__ called for path: {workspace_path}")

        # 基本路径信息
        self.workspace_path = Path(workspace_path).resolve()
        self.absolute_path = str(self.workspace_path)
        self.uuid = str(uuid.uuid4())

        # ⭐ 新增：WorkspaceContext 引用（延迟加载）
        self._context = None

        # 工作区信息
        self.workspace_info: WorkspaceInfo | None = None

        # 持久化管理器 - 现在从 context 获取（向后兼容）
        self.persistence_manager: WorkspacePersistenceManager | None = None

        # TaskGraph 自动持久化管理器 - 现在从 context 获取（向后兼容）
        self.task_graph_persistence_manager = None

        # 对话管理 - 核心功能
        self.current_conversation: Conversation | None = None
        self.conversation_history_manager: ConversationHistoryManager | None = None

        # 自动保存机制
        self._auto_save_task: asyncio.Task | None = None
        self._auto_save_interval = 30  # 默认30秒自动保存一次
        self._last_message_count = 0  # 上次保存时的消息数量
        self._auto_save_enabled = True  # 是否启用自动保存

        # 持久化重试机制
        self._max_retry_attempts = 3  # 最大重试次数
        self._retry_base_delay = 1.0  # 基础重试延迟(秒)
        self._retry_max_delay = 30.0  # 最大重试延迟(秒)
        self._retry_backoff_multiplier = 2.0  # 退避乘数

        # UI 上下文自动保存
        self._ui_context_dirty = False  # UI 上下文是否需要保存

        # 配置路径定义
        self.user_config_dir = self.workspace_path / ".dawei"
        self.settings_file = self.user_config_dir / "settings.json"
        self.workspace_info_file = self.workspace_path / ".dawei" / "workspace.json"
        self.chat_history_dir = self.workspace_path / ".dawei" / "chat-history"
        self.tasks_file = self.workspace_path / ".dawei" / "tasks.json"

        # 配置数据
        self.workspace_settings: WorkspaceSettings | None = None

        # ✨ 新增：统一工作区配置（Pydantic 模型）
        from .models import PluginsConfig, WorkspaceConfig

        self.workspace_config: WorkspaceConfig | None = None
        self.plugins_config: PluginsConfig | None = None  # ✨ 新增：插件配置（独立文件）

        # LLM 管理 - 由 LLMProvider 统一管理
        self.llm_manager: LLMProvider | None = None

        # 工具管理 - 由 ToolManager 和 MCPToolManager 统一管理
        self.tool_manager: ToolManager | None = None
        self.mcp_tool_manager: MCPToolManager | None = None

        # 🔴 修复：UserWorkspace 不再拥有 event_bus
        # 所有 event_bus 由 Agent 创建和管理，避免多个 Agent 共享 event_bus 导致的 handler 干扰
        # self.event_bus = None  # 不再需要

        # Skills工具 - 单独管理
        self._skills_tools: list | None = None

        # 模式管理 - 延迟初始化以避免循环依赖
        self._mode_manager = None

        # 安全相关
        self._forbidden_paths: set[str] = set()
        self._allowed_commands_cache: set[str] | None = None

        # 生命周期状态
        self._initialized = False
        self._loaded = False

        # event_bus 已在 __init__ 前面设置为独立实例（不使用全局单例）

        logger.info(f"UserWorkspace initialized: {self.absolute_path}")

    # ==================== WorkspaceContext 属性访问代理 ====================

    @property
    def context(self):
        """获取工作区上下文（懒加载）"""
        if self._context is None:
            raise RuntimeError(f"Workspace not initialized. Call initialize() first. Workspace: {self.absolute_path}")
        return self._context

    @property
    def tool_manager(self):
        """工具管理器（从共享 context 获取）"""
        # 向后兼容：如果已有直接引用，使用它；否则从 context 获取
        if hasattr(self, "_tool_manager_ref") and self._tool_manager_ref:
            return self._tool_manager_ref
        if self._context:
            return self._context.tool_manager
        # 如果还没初始化，返回 None（向后兼容）
        return None

    @tool_manager.setter
    def tool_manager(self, value):
        """设置工具管理器（用于向后兼容）"""
        self._tool_manager_ref = value

    @property
    def llm_manager(self):
        """LLM 管理器（从共享 context 获取）"""
        if hasattr(self, "_llm_manager_ref") and self._llm_manager_ref:
            return self._llm_manager_ref
        if self._context:
            return self._context.llm_manager
        return None

    @llm_manager.setter
    def llm_manager(self, value):
        """设置 LLM 管理器（用于向后兼容）"""
        self._llm_manager_ref = value

    @property
    def persistence_manager(self):
        """持久化管理器（从共享 context 获取）"""
        if self._context:
            return self._context.persistence_manager
        return None

    @persistence_manager.setter
    def persistence_manager(self, value):
        """设置持久化管理器（用于向后兼容）"""
        # 不保存，因为现在从 context 获取

    @property
    def task_graph_persistence_manager(self):
        """TaskGraph 持久化管理器（从共享 context 获取）"""
        if self._context:
            return self._context.task_graph_persistence_manager
        return None

    @task_graph_persistence_manager.setter
    def task_graph_persistence_manager(self, value):
        """设置 TaskGraph 持久化管理器（用于向后兼容）"""
        # 不保存，因为现在从 context 获取

    @property
    def workspace_settings(self):
        """工作区配置（从共享 context 获取）"""
        if self._context:
            return self._context.workspace_settings
        return None

    @workspace_settings.setter
    def workspace_settings(self, value):
        """设置工作区配置（同步到 context）"""
        if self._context:
            self._context.workspace_settings = value
        # 保存本地引用（向后兼容）
        self._workspace_settings_ref = value

    @property
    def conversation_history_manager(self):
        """对话历史管理器（从共享 context 获取）"""
        if self._context:
            return self._context.conversation_history_manager
        return None

    @conversation_history_manager.setter
    def conversation_history_manager(self, value):
        """设置对话历史管理器（用于向后兼容）"""
        # 不保存，因为现在从 context 获取

    # ==================== 原有方法 ====================

    def is_command_allowed(self, command: str) -> bool:
        """检查命令是否允许执行

        Args:
            command: 要检查的命令字符串

        Returns:
            bool: 命令是否在允许列表中

        """
        # SUPER MODE: Allow all commands
        if is_super_mode_enabled():
            log_security_bypass("is_command_allowed", f"command={command}")
            return True

        if not command:
            return False

        # 提取命令的第一个单词（命令名称）
        command_parts = command.strip().split()
        if not command_parts:
            return False

        command_name = command_parts[0]

        # 如果有缓存的允许命令列表，使用缓存
        if self._allowed_commands_cache is not None:
            return command_name in self._allowed_commands_cache

        # 从workspace_settings获取允许的命令
        if self.workspace_settings and hasattr(self.workspace_settings, "allowed_commands"):
            allowed_commands = self.workspace_settings.allowed_commands
            if allowed_commands:
                # 缓存结果
                self._allowed_commands_cache = set(allowed_commands)
                return command_name in allowed_commands

        # 如果没有配置允许的命令，默认允许所有命令（向后兼容）
        logger.debug(
            f"is_command_allowed: no allowed_commands configured, allowing '{command_name}'",
        )
        return True

    @property
    def mode(self):
        """当前mode"""
        return self.workspace_info.user_ui_context.current_mode

    @mode.setter
    def mode(self, value):
        self.workspace_info.user_ui_context.current_mode = value

    @property
    def mode_manager(self):
        """延迟初始化 ModeManager 以避免循环依赖"""
        if self._mode_manager is None:
            from dawei.mode.mode_manager import ModeManager

            # 传入工作区路径以支持工作区级配置
            self._mode_manager = ModeManager(workspace_path=self.absolute_path)
        return self._mode_manager

    async def initialize(self) -> bool:
        """异步初始化工作区（使用 WorkspaceService）

        ⭐ 改进：使用共享的 WorkspaceContext，避免重复创建资源

        Returns:
            bool: 初始化是否成功

        """
        if self._initialized:
            return True

        logger.info(f"Initializing workspace: {self.absolute_path}")

        try:
            # ⭐ 核心改动：获取共享的 WorkspaceContext（每个 workspace_id 一个单例）
            from .workspace_service import WorkspaceService

            self._context = await WorkspaceService.get_context(self.absolute_path)
            logger.info(f"  ✓ Acquired WorkspaceContext (refs={self.context.ref_count})")

            # 加载工作区信息（使用共享的 persistence_manager）
            await self._load_workspace_info()
            logger.info("  ✓ Workspace info loaded")

            # 加载配置
            await self._load_configurations()
            logger.info("  ✓ Configurations loaded")

            # 初始化对话管理（使用共享的 conversation_history_manager）
            await self._initialize_conversation_management()
            logger.info("  ✓ Conversation management initialized")

            # 🔧 修复：不在 UserWorkspace 创建 TaskGraph
            # TaskGraph 应该由 Agent 创建并使用 Agent 的 event_bus
            # 这里设置为 None,Agent 稍后会创建自己的 TaskGraph
            self.task_graph = None
            logger.info("  ✓ Task graph placeholder set (will be created by Agent)")

            # 启动对话自动保存任务
            await self._start_auto_save_conversation()
            logger.info("  ✓ Auto-save started")

            self._initialized = True
            self._loaded = True
            logger.info(f"✓ Workspace initialization completed successfully: {self.absolute_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize workspace: {e}", exc_info=True)
            # 清理已获取的上下文
            if self._context:
                await self._context.release()
                self._context = None
            # 发送持久化失败告警
            await self._alert_persistence_failure("workspace_initialization", str(e))
            raise

    async def _initialize_persistence_manager(self):
        """初始化持久化管理器（现在从 WorkspaceContext 获取）

        ⭐ 改动：不再创建持久化管理器，直接使用 WorkspaceContext 中的
        """
        # 不再需要创建，persistence_manager 已经在 WorkspaceContext 中初始化
        # 通过 @property persistence_manager 自动获取
        logger.debug("Persistence manager provided by WorkspaceContext")

    async def _load_workspace_info(self):
        """加载工作区信息 (使用持久化管理器)"""
        try:
            # 首先尝试从新的持久化管理器加载
            if self.persistence_manager:
                workspace_data = await self.persistence_manager.load_resource(
                    ResourceType.WORKSPACE_INFO,
                    "workspace",
                )

                if workspace_data:
                    self.workspace_info = WorkspaceInfo.from_dict(workspace_data)
                    logger.info(
                        f"Loaded workspace info from persistence manager: {self.workspace_info.name}",
                    )
                    return

            # 回退到旧格式文件
            if self.workspace_info_file.exists():
                with Path(self.workspace_info_file).open(encoding="utf-8") as f:
                    data = json.load(f)
                self.workspace_info = WorkspaceInfo.from_dict(data)
                logger.info(f"Loaded workspace info from legacy file: {self.workspace_info.name}")

                # 迁移到新的持久化管理器
                if self.persistence_manager:
                    await self._migrate_workspace_info_to_persistence_manager()
            else:
                # 创建默认工作区信息
                self.workspace_info = WorkspaceInfo(
                    id=str(uuid.uuid4()),
                    name=self.workspace_path.name,
                    display_name=self.workspace_path.name,
                    description=f"Workspace at {self.workspace_path}",
                    created_at=datetime.now(UTC),
                )
                await self._save_workspace_info()

        except Exception as e:
            logger.error(f"Failed to load workspace info: {e}", exc_info=True)
            raise WorkspaceInfoPersistenceError(
                f"Failed to load workspace info: {e}",
                workspace_id=self.uuid,
            )

    async def _save_workspace_info(self):
        """保存工作区信息 (使用持久化管理器)"""
        if not self.workspace_info:
            logger.warning("Cannot save workspace info: workspace_info is None")
            return False

        try:
            # 使用持久化管理器保存
            if self.persistence_manager:
                success = await self.persistence_manager.save_resource(
                    ResourceType.WORKSPACE_INFO,
                    "workspace",
                    self.workspace_info.to_dict(),
                    use_timestamp=False,
                )

                if success:
                    logger.debug("Workspace info saved via persistence manager.")
                    return True
                raise WorkspaceInfoPersistenceError(
                    "Persistence manager returned False",
                    workspace_id=self.workspace_info.id,
                )

        except Exception as e:
            logger.error(f"Failed to save workspace info: {e}", exc_info=True)
            # 发送持久化失败告警
            await self._alert_persistence_failure("workspace_info", str(e))
            raise WorkspaceInfoPersistenceError(
                f"Failed to save workspace info: {e}",
                workspace_id=self.workspace_info.id,
            )

    async def _initialize_llm_manager(self):
        """初始化 LLM 管理器（现在从 WorkspaceContext 获取）

        ⭐ 改动：不再创建，直接使用 WorkspaceContext 中的
        """
        # LLM 管理器已经在 WorkspaceContext 中初始化
        # 通过 @property llm_manager 自动获取
        logger.debug("LLM manager provided by WorkspaceContext")

    async def _initialize_conversation_management(self):
        """初始化对话管理"""
        # ConversationHistoryManager 现在从 WorkspaceContext 获取
        logger.info("Initializing conversation management...")

        # 如果没有当前对话，创建一个新的
        if self.current_conversation is None:
            current_llm_config = self.llm_manager.get_current_config_name() if self.llm_manager else "glm"
            self.current_conversation = create_conversation(
                title="新对话",
                agent_mode="orchestrator",
                llm_model=current_llm_config or "glm",
            )

        logger.info("Conversation management initialized successfully.")

    async def _load_configurations(self):
        """加载所有配置文件"""
        logger.info("Loading configurations...")

        # 加载统一工作区配置（config.json）
        await self._load_workspace_config()

        # 加载插件配置（.dawei/plugins/{plugin_id}.json）
        await self._load_plugins_config()

        # 加载工作区设置（settings.json）
        await self._load_settings()

        logger.info("Configurations loaded successfully.")

    async def _load_workspace_config(self):
        """加载工作区配置（config.json）到 Pydantic 模型"""
        config_file = self.workspace_path / ".dawei" / "config.json"

        if not config_file.exists():
            # 使用默认配置
            from dawei.api.workspaces.config import DEFAULT_CONFIG

            config_dict = DEFAULT_CONFIG.copy()
            logger.info(f"Config file not found, using defaults: {config_file}")
        else:
            try:
                with config_file.open(encoding="utf-8") as f:
                    config_dict = json.load(f)
                logger.info(f"Loading config from: {config_file}")
            except (OSError, json.JSONDecodeError) as e:
                # Fast Fail: 配置文件存在但无效
                from dawei.core.exceptions import ConfigurationError

                raise ConfigurationError(f"Invalid workspace config file {config_file}: {e}") from e

        # 使用 Pydantic 模型验证和加载
        from .models import WorkspaceConfig

        self.workspace_config = WorkspaceConfig.from_dict(config_dict)

        logger.info("Workspace config loaded successfully.")

    def get_config(self):
        """获取工作区配置（Fast Fail 如果未加载）

        Returns:
            WorkspaceConfig: 工作区配置对象

        Raises:
            RuntimeError: 如果配置未加载（调用 initialize() 前访问）
        """
        if self.workspace_config is None:
            raise RuntimeError(f"Workspace config not loaded. Call initialize() first. Workspace: {self.absolute_path}")
        return self.workspace_config

    async def save_workspace_config(self):
        """保存工作区配置到 config.json"""
        if self.workspace_config is None:
            raise RuntimeError("No config to save")

        config_file = self.workspace_path / ".dawei" / "config.json"

        # 确保配置目录存在
        config_file.parent.mkdir(parents=True, exist_ok=True)

        # 序列化为 JSON
        config_dict = self.workspace_config.model_dump_custom()

        with config_file.open("w", encoding="utf-8") as f:
            json.dump(config_dict, f, indent=2, ensure_ascii=False)

        logger.info(f"Workspace config saved: {config_file}")

    async def _load_settings(self):
        """加载设置配置（合并全局配置和工作区配置）

        配置继承规则：
        1. 全局配置：~/.dawei/configs/settings.json
        2. 工作区配置：{workspace}/.dawei/settings.json
        3. 工作区配置覆盖全局配置（相同字段）
        4. 工作区不存在的字段继承全局配置

        注意：
        - 空字符串、空列表、False、0 等假值会正确覆盖全局配置
        - 显式设置的字段会继承全局默认值
        - 例如：全局 config["allowedCommands"] = ["pnpm"]，
          工作区不设置该字段时，会继承 ["pnpm"]
          工作区设置 "allowedCommands": [] 时，会覆盖为 []
        """
        # 1. 先加载全局配置作为基础
        global_settings_path = Path.home() / ".dawei" / "configs" / "settings.json"
        global_settings_dict = {}

        if global_settings_path.exists():
            try:
                with global_settings_path.open(encoding="utf-8") as f:
                    global_data = json.load(f)
                    global_settings_dict = global_data.get("globalSettings", {})
                    logger.info(f"Loaded global settings from {global_settings_path}")
            except (OSError, json.JSONDecodeError) as e:
                logger.warning(f"Failed to load global settings: {e}")

        # 2. 加载工作区配置（覆盖全局配置）
        workspace_settings_dict = {}
        if self.settings_file.exists():
            try:
                with Path(self.settings_file).open(encoding="utf-8") as f:
                    config_data = json.load(f)
                    workspace_settings_dict = config_data.get("globalSettings", {})
                    logger.info(f"Loaded workspace settings from {self.settings_file}")
            except (OSError, json.JSONDecodeError) as e:
                logger.warning(f"Failed to load workspace settings: {e}")
        else:
            logger.info("Workspace settings file not found, using global settings")

        # 3. 合并配置（工作区配置覆盖全局配置）
        merged_settings = {**global_settings_dict, **workspace_settings_dict}

        # 4. 创建 WorkspaceSettings 对象
        self.workspace_settings = WorkspaceSettings.from_dict(merged_settings)

        # 5. 记录配置来源
        if workspace_settings_dict:
            overridden_fields = set(workspace_settings_dict.keys()) & set(global_settings_dict.keys())
            if overridden_fields:
                logger.info(f"Workspace settings override global fields: {overridden_fields}")
            else:
                logger.info("Workspace settings only add new fields to global settings")

        logger.info("Workspace settings loaded successfully.")

    async def _save_settings(self, only_fields: set[str] | None = None):
        """保存设置配置到 settings.json

        Args:
            only_fields: 只保存指定的字段（驼峰命名，如 {"httpProxy", "httpsProxy"}），
                        None 表示保存所有字段
        """
        if self.workspace_settings is None:
            self.workspace_settings = WorkspaceSettings()

        # 读取现有的 settings.json（如果存在）
        existing_data = {}
        if self.settings_file.exists():
            try:
                with Path(self.settings_file).open(encoding="utf-8") as f:
                    existing_data = json.load(f)
            except (OSError, json.JSONDecodeError):
                pass

        # 字段名映射：Python 字段名 -> JSON 字段名
        field_mapping = {
            "auto_approval_enabled": "autoApprovalEnabled",
            "always_allow_read_only": "alwaysAllowReadOnly",
            "always_allow_read_only_outside_workspace": "alwaysAllowReadOnlyOutsideWorkspace",
            "always_allow_write": "alwaysAllowWrite",
            "always_allow_write_outside_workspace": "alwaysAllowWriteOutsideWorkspace",
            "always_allow_write_protected": "alwaysAllowWriteProtected",
            "write_delay_ms": "writeDelayMs",
            "always_allow_browser": "browserToolEnabled",
            "always_approve_resubmit": "alwaysApproveResubmit",
            "request_delay_seconds": "requestDelaySeconds",
            "always_allow_mcp": "mcpEnabled",
            "always_allow_mode_switch": "alwaysAllowModeSwitch",
            "always_allow_subtasks": "alwaysAllowSubtasks",
            "always_allow_execute": "alwaysAllowExecute",
            "always_allow_followup_questions": "alwaysAllowFollowupQuestions",
            "followup_auto_approve_timeout_ms": "followupAutoApproveTimeoutMs",
            "always_allow_update_todo_list": "alwaysAllowUpdateTodoList",
            "allowed_commands": "allowedCommands",
            "denied_commands": "deniedCommands",
            "max_concurrent_file_reads": "maxConcurrentFileReads",
            "max_workspace_files": "maxWorkspaceFiles",
            "max_read_file_line": "maxReadFileLine",
            "max_image_file_size": "maxImageFileSize",
            "max_total_image_size": "maxTotalImageSize",
            "terminal_output_line_limit": "terminalOutputLineLimit",
            "terminal_output_character_limit": "terminalOutputCharacterLimit",
            "http_proxy": "httpProxy",
            "https_proxy": "httpsProxy",
            "no_proxy": "noProxy",
        }

        # 增量更新或全量更新
        if only_fields:
            # 增量模式：只更新指定的字段
            if "globalSettings" not in existing_data:
                existing_data["globalSettings"] = {}

            for py_field, json_field in field_mapping.items():
                if json_field in only_fields:
                    # 更新指定字段
                    value = getattr(self.workspace_settings, py_field)
                    existing_data["globalSettings"][json_field] = value

            logger.info(f"Workspace settings incremental update: {only_fields}")
        else:
            # 全量模式：保存所有字段（向后兼容）
            settings_dict = {
                json_field: getattr(self.workspace_settings, py_field)
                for py_field, json_field in field_mapping.items()
            }
            existing_data["globalSettings"] = settings_dict
            logger.info("Workspace settings full update")

        # 确保 settings 目录存在
        self.settings_file.parent.mkdir(parents=True, exist_ok=True)

        # 写入文件
        with self.settings_file.open("w", encoding="utf-8") as f:
            json.dump(existing_data, f, indent=2, ensure_ascii=False)

        logger.info(f"Workspace settings saved: {self.settings_file}")

    async def _load_plugins_config(self):
        """加载插件配置

        格式：.dawei/plugins/{plugin_id}.json
        每个插件一个配置文件，包含 enabled、activated、settings
        """
        plugins_dir = self.workspace_path / ".dawei" / "plugins"

        from .models import PluginInstanceConfig, PluginsConfig

        # 从 .dawei/plugins/*.json 加载
        if plugins_dir.exists() and plugins_dir.is_dir():
            plugins_config_dict = {}

            for config_file in plugins_dir.glob("*.json"):
                # 跳过 config_schema.json 等非插件配置文件
                if config_file.name == "config_schema.json":
                    continue

                try:
                    plugin_id = config_file.stem
                    with config_file.open(encoding="utf-8") as f:
                        config_data = json.load(f)

                    plugins_config_dict[plugin_id] = PluginInstanceConfig.model_validate(config_data)
                    logger.debug(f"Loaded plugin config: {plugin_id}")
                except Exception as e:
                    logger.warning(f"Failed to load plugin config {config_file}: {e}")

            if plugins_config_dict:
                self.plugins_config = PluginsConfig(
                    plugins=plugins_config_dict,
                    max_plugins=50,
                    auto_discovery=True,
                    enabled=True,
                )
                logger.info(f"Loaded {len(plugins_config_dict)} plugins from {plugins_dir}")
                return

        # 默认配置（无插件）
        logger.info("No plugin configs found, using defaults")
        self.plugins_config = PluginsConfig()

    async def _save_plugins_config(self):
        """保存插件配置到 .dawei/plugins/{plugin_id}.json"""
        if self.plugins_config is None:
            raise RuntimeError("No plugins config to save")

        plugins_dir = self.workspace_path / ".dawei" / "plugins"
        plugins_dir.mkdir(parents=True, exist_ok=True)

        # 为每个插件保存独立的配置文件
        saved_count = 0
        for plugin_id, config in self.plugins_config.plugins.items():
            config_file = plugins_dir / f"{plugin_id}.json"
            try:
                with config_file.open("w", encoding="utf-8") as f:
                    json.dump(config.model_dump(), f, indent=2, ensure_ascii=False)
                saved_count += 1
                logger.debug(f"Saved plugin config: {plugin_id}")
            except Exception as e:
                logger.exception(f"Failed to save plugin config {plugin_id}: {e}")

        logger.info(f"Saved {saved_count} plugin configs to {plugins_dir}")
        """初始化MCP工具管理器（现在从 WorkspaceContext 获取）

        ⭐ 改动：不再创建，直接使用 WorkspaceContext 中的
        """
        # MCP 工具管理器已经在 WorkspaceContext 中初始化
        # 通过 @property mcp_tool_manager 自动获取
        logger.debug("MCP tool manager provided by WorkspaceContext")

    async def _initialize_tools(self):
        """初始化工具管理器（现在从 WorkspaceContext 获取）

        ⭐ 改动：不再创建，直接使用 WorkspaceContext 中的
        """
        # 工具管理器已经在 WorkspaceContext 中初始化
        # 通过 @property tool_manager 自动获取
        logger.debug("Tool manager provided by WorkspaceContext")

        # 🔧 初始化Skills工具 - 三级加载机制
        from pathlib import Path

        from dawei.tools.custom_tools.skills_tool import create_skills_tools

        def find_skills_roots() -> list[Path]:
            """查找所有可能包含skills的根目录
            返回两个级别的根目录列表（workspace和global user）

            新的路径结构：.dawei/skills/
            """
            roots = []
            ws_path = Path(self.absolute_path)

            # 获取当前mode（用于mode-specific skills）
            current_mode = None
            try:
                if hasattr(self, "mode") and self.mode:
                    current_mode = self.mode
                elif self.workspace_info and hasattr(self.workspace_info, "user_ui_context"):
                    current_mode = self.workspace_info.user_ui_context.current_mode
            except (AttributeError, TypeError) as mode_error:
                # mode 获取失败是预期的，使用 None 作为默认值
                logger.debug(f"Could not determine current mode: {mode_error}")
            except Exception as e:
                # 未预期的错误应该记录
                logger.warning(f"Unexpected error getting current mode: {e}", exc_info=True)

            logger.debug(f"Current mode for skills: {current_mode}")

            # ===== Level 1: UserWorkspace级别 =====
            # 1.1 {workspace}/.dawei/skills/
            ws_dawei_configs = ws_path / ".dawei"
            ws_skills_dir = ws_dawei_configs / "skills"
            if ws_skills_dir.exists() and any(ws_skills_dir.iterdir()):
                logger.info("[Level 1: Workspace] Found .dawei/skills in workspace")
                roots.append(ws_path)

            # 1.2 {workspace}/.dawei/skills-{mode}/
            if current_mode:
                ws_mode_skills = ws_dawei_configs / f"skills-{current_mode}"
                if ws_mode_skills.exists() and any(ws_mode_skills.iterdir()):
                    logger.info(
                        f"[Level 1: Workspace] Found .dawei/skills-{current_mode} in workspace",
                    )
                    roots.append(ws_path)

            # ===== Level 2: Global User级别 =====
            # 2.1 {DAWEI_HOME}/skills/
            dawei_home = get_dawei_home()
            global_dawei_configs = dawei_home 
            global_skills_dir = global_dawei_configs / "skills"
            if global_skills_dir.exists() and any(global_skills_dir.iterdir()):
                logger.info("[Level 2: Global User] Found .dawei/skills in DAWEI_HOME")
                roots.append(dawei_home)

            # 2.2 {DAWEI_HOME}/skills-{mode}/
            if current_mode:
                global_mode_skills = global_dawei_configs / f"skills-{current_mode}"
                if global_mode_skills.exists() and any(global_mode_skills.iterdir()):
                    logger.info(
                        f"[Level 2: Global User] Found .dawei/skills-{current_mode} in DAWEI_HOME",
                    )
                    roots.append(dawei_home)

            logger.info(f"Skills discovery: found {len(roots)} root(s) with skills")
            return roots

        # 查找所有skills根目录
        skills_roots = find_skills_roots()

        # 创建skills工具 - 传入所有找到的根目录
        self._skills_tools = create_skills_tools(
            skills_roots=skills_roots,  # 所有包含.dawei的根目录
            current_mode=None,  # mode已经在查找时处理
        )

        logger.info(
            f"✓ Created {len(self._skills_tools)} skills tools from {len(skills_roots)} root(s)",
        )

        # 记录内置提供者信息
        providers_info = self.tool_manager.get_builtin_providers_info()
        logger.info("Builtin providers info:")
        for provider_name, info in providers_info.items():
            logger.info(f"  {provider_name}: {info['count']} tools - {info['description']}")

        # 记录工具覆盖信息
        override_info = self.tool_manager.get_all_override_info()
        if override_info:
            logger.info(f"Found {len(override_info)} overridden tools")
            for info in override_info[:3]:  # 只记录前3个
                logger.info(
                    f"  - {info['tool_name']}: {info['active_source']} overrides other sources",
                )

        # 初始化允许的工具名称
        await self._update_allowed_tools()

    async def _update_allowed_tools(self):
        """更新允许的工具列表 - 由 ToolManager 统一管理"""
        if self.tool_manager:
            # 从 ToolManager 获取最新工具列表
            all_tools = self.tool_manager.load_tools()
            # 应用工作区过滤
            allowed_tool_names = self._get_filtered_tool_names(all_tools)
            logger.info(f"Allowed tools updated: {len(allowed_tool_names)} out of {len(all_tools)}")
        else:
            logger.warning("ToolManager not initialized, cannot update allowed tools")

    # 对话管理方法
    async def new_conversation(
        self,
        title: str = "新对话",
        agent_mode: str = "orchestrator",
    ) -> Conversation:
        """创建新对话并设置为当前对话

        Args:
            title: 对话标题
            agent_mode: 代理模式

        Returns:
            Conversation: 新创建的对话

        """
        # 保存当前对话到历史（如果有消息）
        if self.current_conversation and self.current_conversation.message_count > 0:
            await self.save_current_conversation()

        # 创建新对话
        current_llm_config = self.llm_manager.get_current_config_name() if self.llm_manager else "glm"
        self.current_conversation = create_conversation(
            title=title,
            agent_mode=agent_mode,
            llm_model=current_llm_config or "glm",
        )

        logger.info(f"Created new conversation: {title}")
        return self.current_conversation

    async def save_current_conversation(self) -> bool:
        """保存当前对话到历史 (使用持久化管理器)

        Returns:
            bool: 保存是否成功

        Raises:
            ConversationPersistenceError: 当对话持久化失败时
            PersistenceError: 当持久化管理器不可用时

        """
        logger.info("[SAVE_CONVERSATION] Starting save for conversation")

        if not self.current_conversation:
            raise ConversationPersistenceError(
                "current_conversation is None",
                conversation_id="unknown",
            )

        if not self.conversation_history_manager:
            raise ConversationPersistenceError(
                "conversation_history_manager is None",
                conversation_id="unknown",
            )

        logger.info(
            f"[SAVE_CONVERSATION] Conversation details: id={self.current_conversation.id}, message_count={self.current_conversation.message_count}",
        )

        # 首先尝试使用持久化管理器保存
        if self.persistence_manager:
            # 将对话转换为字典格式
            conversation_dict = self._conversation_to_dict(self.current_conversation)

            success = await self.persistence_manager.save_conversation(
                self.current_conversation.id,
                conversation_dict,
            )

            if success:
                logger.info(
                    f"[SAVE_CONVERSATION] Successfully saved conversation via persistence manager: {self.current_conversation.id}",
                )
                return True
            logger.warning(
                "[SAVE_CONVERSATION] Persistence manager save failed, falling back to conversation_history_manager",
            )

        # 回退到对话历史管理器
        success = await self.conversation_history_manager.save_by_id(
            self.current_conversation.id,
            self.current_conversation,
        )

        if success:
            logger.info(
                f"[SAVE_CONVERSATION] Successfully saved conversation via history manager: {self.current_conversation.id}",
            )
        else:
            logger.error(
                f"[SAVE_CONVERSATION] Failed to save conversation: {self.current_conversation.id}",
            )
            # 发送持久化失败告警
            await self._alert_persistence_failure(
                "conversation",
                f"Failed to save conversation {self.current_conversation.id}",
                conversation_id=self.current_conversation.id,
            )

        return success

    def _conversation_to_dict(self, conversation: Conversation) -> dict[str, Any]:
        """将对话对象转换为字典格式"""
        # 处理时间戳 - 确保是字符串格式
        created_at = conversation.created_at
        if isinstance(created_at, datetime):
            created_at = created_at.isoformat()
        elif created_at is None:
            created_at = datetime.now(UTC).isoformat()

        updated_at = conversation.updated_at
        if isinstance(updated_at, datetime):
            updated_at = updated_at.isoformat()
        elif updated_at is None:
            updated_at = datetime.now(UTC).isoformat()

        # 正确序列化消息 - 使用 to_dict() 方法确保 datetime 正确转换
        messages_data = []
        for msg in conversation.messages:
            # 使用 to_dict() 方法，这是最可靠的序列化方式
            # to_dict() 会调用 to_openai_format()，正确处理 datetime
            if hasattr(msg, "to_dict") and callable(msg.to_dict):
                msg_dict = msg.to_dict()
            # 回退到 model_dump/dict
            elif hasattr(msg, "model_dump"):
                msg_dict = msg.model_dump(exclude_none=True)
            elif hasattr(msg, "dict"):
                msg_dict = msg.dict(exclude_none=True)
            else:
                msg_dict = {}

            # 确保 content 字段是字符串格式(处理OpenAI格式的content对象)
            if "content" in msg_dict and isinstance(msg_dict["content"], dict):
                # OpenAI格式: {"type": "text", "text": "..."}
                if msg_dict["content"].get("type") == "text":
                    msg_dict["content"] = msg_dict["content"].get("text", "")
                else:
                    # 其他类型,转为JSON字符串
                    import json

                    msg_dict["content"] = json.dumps(msg_dict["content"])

            messages_data.append(msg_dict)

        return {
            "id": conversation.id,
            "title": conversation.title,
            "agent_mode": conversation.agent_mode,
            "llm_model": conversation.llm_model,
            "created_at": created_at,
            "updated_at": updated_at,
            "messages": messages_data,
            "message_count": conversation.message_count,
        }

    async def load_conversation(self, conversation_id: str) -> bool:
        """加载指定对话作为当前对话

        Args:
            conversation_id: 对话ID

        Returns:
            bool: 加载是否成功

        Raises:
            ConversationPersistenceError: 当对话历史管理器不可用时
            ConversationPersistenceError: 当对话加载失败时

        """
        if not self.conversation_history_manager:
            raise ConversationPersistenceError(
                "conversation_history_manager is None",
                conversation_id=conversation_id,
            )

        # 先保存当前对话
        if self.current_conversation and self.current_conversation.message_count > 0:
            await self.save_current_conversation()

        # 加载指定对话
        conversation = await self.conversation_history_manager.get_by_id(conversation_id)
        if conversation:
            self.current_conversation = conversation
            logger.info(f"Loaded conversation: {conversation_id}")
            return True
        raise ConversationPersistenceError(
            f"Conversation not found: {conversation_id}",
            conversation_id=conversation_id,
        )

    async def delete_conversation(self, conversation_id: str) -> bool:
        """删除指定对话

        Args:
            conversation_id: 对话ID

        Returns:
            bool: 删除是否成功

        Raises:
            ConversationPersistenceError: 当对话历史管理器不可用时
            ConversationPersistenceError: 当对话删除失败时

        """
        if not self.conversation_history_manager:
            raise ConversationPersistenceError(
                "conversation_history_manager is None",
                conversation_id=conversation_id,
            )

        success = await self.conversation_history_manager.delete_by_id(conversation_id)
        if success:
            # 如果删除的是当前对话，创建新对话
            if self.current_conversation and self.current_conversation.id == conversation_id:
                current_llm_config = self.llm_manager.get_current_config_name() if self.llm_manager else "glm"
                self.current_conversation = create_conversation(
                    title="新对话",
                    agent_mode="orchestrator",  # 使用orchestrator作为默认模式
                    llm_model=current_llm_config or "glm",
                )
            logger.info(f"Deleted conversation: {conversation_id}")
        else:
            raise ConversationPersistenceError(
                f"Failed to delete conversation: {conversation_id}",
                conversation_id=conversation_id,
            )

        return success

    async def get_conversation_list(self) -> list[Conversation]:
        """获取对话历史列表

        Returns:
            List[Conversation]: 对话列表

        Raises:
            ConversationPersistenceError: 当对话历史管理器不可用时

        """
        if not self.conversation_history_manager:
            raise ConversationPersistenceError(
                "conversation_history_manager is None",
                conversation_id="unknown",
            )

        return await self.conversation_history_manager.list_all()

    async def search_conversations(
        self,
        query: str,
        search_in_content: bool = False,
    ) -> list[Conversation]:
        """搜索对话

        Args:
            query: 搜索关键词
            search_in_content: 是否在消息内容中搜索

        Returns:
            List[Conversation]: 匹配的对话列表

        Raises:
            ConversationPersistenceError: 当对话历史管理器不可用时

        """
        if not self.conversation_history_manager:
            raise ConversationPersistenceError(
                "conversation_history_manager is None",
                conversation_id="unknown",
            )

        return await self.conversation_history_manager.search_conversations(
            query,
            search_in_content,
        )

    async def restore(self, conversation_id: str | None = None) -> bool:
        """根据 conversation_id 加载或者新建 current_conversation

        Args:
            conversation_id: 对话ID，如果为 None 则创建新对话

        Returns:
            bool: 操作是否成功

        Raises:
            ConversationPersistenceError: 当对话加载失败时
            WorkspaceInfoPersistenceError: 当工作区信息不存在时
            PersistenceError: 当其他持久化错误发生时

        """
        if conversation_id:
            # 尝试加载指定ID的对话
            success = await self.load_conversation(conversation_id)
            if success:
                # 更新 user_ui_context 中的 conversation_id
                if self.workspace_info and self.workspace_info.user_ui_context:
                    self.workspace_info.user_ui_context.conversation_id = conversation_id
                self.logger.info(f"Successfully restored conversation: {conversation_id}")
                return True
            self.logger.warning(
                f"Failed to load conversation: {conversation_id}, creating new conversation",
            )

        # 如果没有提供 conversation_id 或加载失败，创建新对话
        current_llm_config = self.llm_manager.get_current_config_name() if self.llm_manager else "glm"
        self.current_conversation = create_conversation(
            title="新对话",
            agent_mode="orchestrator",  # 默认使用orchestrator模式
            llm_model=current_llm_config or "glm",
        )

        # 更新 user_ui_context 中的 conversation_id
        if self.workspace_info and self.workspace_info.user_ui_context:
            self.workspace_info.user_ui_context.conversation_id = self.current_conversation.id

        self.logger.info(f"Created new conversation: {self.current_conversation.id}")
        return True

    # 配置管理方法 - 委托给 LLMProvider
    def get_current_llm_config(self) -> LLMConfig | None:
        """获取当前LLM配置"""
        if not self.llm_manager:
            return None
        provider_config = self.llm_manager.get_current_config()
        return provider_config.config if provider_config else None

    def set_current_llm_config(self, config_id: str) -> bool:
        """设置当前LLM配置"""
        if not self.llm_manager:
            logger.error("LLMProvider not initialized")
            return False

        success = self.llm_manager.set_current_config(config_id)

        # 更新当前对话的LLM模型
        if success and self.current_conversation:
            self.current_conversation.llm_model = config_id

        return success

    def get_all_llm_configs(self) -> dict[str, LLMConfig]:
        """获取所有LLM配置"""
        if not self.llm_manager:
            return {}

        all_configs = self.llm_manager.get_all_configs()
        return {name: config.config for name, config in all_configs.items()}

    def get_llm_config(self, config_name: str) -> LLMConfig | None:
        """获取指定名称的LLM配置"""
        if not self.llm_manager:
            return None

        provider_config = self.llm_manager.get_config(config_name)
        return provider_config.config if provider_config else None

    def get_mode_llm_config(self, mode: str) -> LLMConfig | None:
        """获取模式特定的LLM配置"""
        if not self.llm_manager:
            return None

        provider_config = self.llm_manager.get_mode_config(mode)
        return provider_config.config if provider_config else None

    def set_mode_llm_config(self, mode: str, config_name: str) -> bool:
        """设置模式特定的LLM配置"""
        if not self.llm_manager:
            logger.error("LLMProvider not initialized")
            return False

        return self.llm_manager.set_mode_config(mode, config_name)

    def get_workspace_info(self) -> WorkspaceInfo | None:
        """获取工作区信息"""
        return self.workspace_info

    async def update_workspace_info(self, **kwargs) -> bool:
        """更新工作区信息

        Args:
            **kwargs: 要更新的字段

        Returns:
            bool: 更新是否成功

        """
        if not self.workspace_info:
            return False

        for key, value in kwargs.items():
            if hasattr(self.workspace_info, key):
                setattr(self.workspace_info, key, value)

        await self._save_workspace_info()
        logger.info("Workspace info updated successfully.")
        return True

    @property
    def allowed_tools(self) -> list[dict[str, Any]]:
        """获取允许的工具列表 - 由 ToolManager 统一管理"""
        if self.tool_manager:
            # 从 ToolManager 获取最新数据并应用工作区过滤
            all_tools = self.tool_manager.load_tools()
            allowed_tool_names = self._get_filtered_tool_names(all_tools)
            tools = [tool for tool in all_tools if tool["name"] in allowed_tool_names]

            # 🔧 添加skills工具
            if self._skills_tools:
                for skill_tool in self._skills_tools:
                    tools.append(
                        {
                            "name": skill_tool.name,
                            "description": skill_tool.description,
                            "original_tool": skill_tool,  # ToolExecutor会使用这个字段
                            "category": "skills",
                            "enabled": True,
                        },
                    )

            return tools
        return []

    def _get_filtered_tool_names(self, tools: list[dict[str, Any]]) -> set[str]:
        """根据工作区设置过滤工具名称 - 使用 ToolManager 的统一方法"""
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
        """启用工具 - 由 ToolManager 统一管理"""
        if self.tool_manager:
            success = self.tool_manager.enable_tool(tool_name)
            if success:
                logger.info(f"Tool '{tool_name}' enabled successfully")
            return success
        return False

    def disable_tool(self, tool_name: str) -> bool:
        """禁用工具 - 由 ToolManager 统一管理"""
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

        """
        # 添加诊断日志
        logger.debug(f"get_mode_available_tools called for mode: {mode}")
        logger.debug(f"tool_manager is None: {self.tool_manager is None}")
        logger.debug(f"mode_manager is None: {self.mode_manager is None}")
        logger.debug(f"UserWorkspace initialized: {self._initialized}")
        logger.debug(f"UserWorkspace loaded: {self._loaded}")

        # 检查初始化状态
        if not self._initialized:
            logger.warning(
                f"UserWorkspace not initialized when get_mode_available_tools called for mode: {mode}",
            )
            # 尝试同步初始化关键组件
            try:
                if self.tool_manager is None:
                    logger.info("Attempting to initialize tool_manager synchronously")
                    from dawei.tools.tool_manager import ToolManager

                    self.tool_manager = ToolManager(workspace_path=self.absolute_path)
                    logger.info(
                        f"ToolManager created synchronously: {self.tool_manager is not None}",
                    )
            except Exception:
                logger.exception("Failed to initialize tool_manager synchronously: ")

        # 获取所有工具
        if self.tool_manager is None:
            logger.error("tool_manager is None, returning empty tools list")
            return {
                "tools": [],
                "mode": mode,
                "total_count": 0,
                "mode_filtered_count": 0,
                "final_count": 0,
                "workspace_settings_applied": False,
                "error": "tool_manager not initialized",
            }

        all_tools = self.tool_manager.load_tools()
        logger.debug(f"Loaded {len(all_tools)} tools from tool_manager")

        # 获取模式配置
        mode_info = self.mode_manager.get_mode_info(mode)
        logger.debug(f"Mode info for {mode}: {mode_info}")

        # 根据模式过滤工具
        mode_filtered_tools = self._filter_tools_by_mode(all_tools, mode_info)
        logger.debug(f"Mode filtered tools count: {len(mode_filtered_tools)}")

        # 应用工作区设置过滤
        allowed_tool_names = self._get_filtered_tool_names(mode_filtered_tools)
        final_tools = [tool for tool in mode_filtered_tools if tool["name"] in allowed_tool_names]
        logger.debug(f"Final tools count: {len(final_tools)}")

        # 返回过滤后的工具字典
        return {
            "tools": final_tools,
            "mode": mode,
            "total_count": len(all_tools),
            "mode_filtered_count": len(mode_filtered_tools),
            "final_count": len(final_tools),
            "workspace_settings_applied": True,
        }

    def _filter_tools_by_mode(
        self,
        tools: list[dict[str, Any]],
        mode_info: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """根据模式配置过滤工具

        Args:
            tools: 所有工具列表
            mode_info: 模式信息

        Returns:
            List[Dict[str, Any]]: 过滤后的工具列表

        Raises:
            ValueError: 当工具管理器不可用时
            AttributeError: 当模式信息格式不正确时

        """
        if not mode_info:
            logger.debug("No mode_info provided, returning all tools")
            return tools

        # 获取模式配置中的工具偏好和约束
        getattr(mode_info, "tool_preferences", {})
        getattr(mode_info, "constraints", [])
        groups = getattr(mode_info, "groups", [])
        filtered_tools = []

        # 添加诊断日志
        logger.debug(f"Filtering tools by mode - groups: {groups}")
        logger.debug(f"tool_manager is None: {self.tool_manager is None}")

        if self.tool_manager is None:
            raise ValueError("tool_manager is None, cannot get_available_tools_with_groups")

        mode_tools = self.tool_manager.get_available_tools_with_groups(groups)
        logger.debug(f"Mode tools from get_available_tools_with_groups: {mode_tools}")

        for tool in tools:
            tool_name = tool.get("name", "")
            if tool_name in mode_tools:
                filtered_tools.append(tool)

        logger.debug(f"Filtered {len(tools)} tools to {len(filtered_tools)} for mode")
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
        """重新加载工具配置 - 由 ToolManager 统一管理"""
        if self.tool_manager:
            # 重新加载所有配置
            self.tool_manager.reload_configs()

            # 记录重新加载后的统计信息
            stats = self.tool_manager.get_tool_statistics()
            logger.info(
                f"Tool configurations reloaded: {stats['total_tools']} total, {stats['overridden_tools']} overridden",
            )

            # 注意：这里不能使用 await，因为这是同步方法
            # 调用者需要在异步上下文中处理 _update_allowed_tools()
        logger.info("Tool configurations reloaded")

    def get_tool_sources(self, tool_name: str) -> dict[str, bool]:
        """获取工具配置来源信息"""
        if self.tool_manager:
            return self.tool_manager.get_tool_sources(tool_name)
        return {}

    # MCP 管理方法 - 委托给 MCPToolManager
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

    def is_path_allowed(self, path: str) -> bool:
        """检查路径是否允许访问"""
        # SUPER MODE: Allow all paths
        if is_super_mode_enabled():
            log_security_bypass("is_path_allowed", f"path={path}")
            return True

        # 如果路径已经是绝对路径，直接解析；否则与 workspace_path 拼接
        input_path = Path(path)
        abs_path = input_path.resolve() if input_path.is_absolute() else (Path(self.workspace_path) / input_path).resolve()

        logger.debug(
            f"is_path_allowed: input='{path}', workspace='{self.workspace_path}', resolved='{abs_path}'",
        )

        try:
            relative = abs_path.relative_to(self.workspace_path)
            logger.debug(f"is_path_allowed: path is within workspace, relative path='{relative}'")
            return True
        except ValueError:
            logger.warning(
                f"is_path_allowed: path '{abs_path}' is not within workspace '{self.workspace_path}'",
            )
            if self.workspace_settings:
                allowed = self.workspace_settings.always_allow_read_only_outside_workspace
                logger.debug(f"is_path_allowed: always_allow_read_only_outside_workspace={allowed}")
                return allowed
            return False

    def ensure_path_in_workspace(self, path: str) -> str:
        """确保路径在工作区内"""
        path = path.strip(".").strip()
        # 如果路径已经是绝对路径，直接解析；否则与 workspace_path 拼接
        input_path = Path(path)
        abs_path = input_path.resolve() if input_path.is_absolute() else (Path(self.workspace_path) / input_path).resolve()
        return str(abs_path)

    def create_task_context(self, cwd: str | None = None) -> TaskContext:
        """创建任务上下文"""
        if cwd is None:
            cwd = str(self.workspace_path)

        if not self.is_path_allowed(cwd):
            cwd = str(self.workspace_path)

        current_llm_config = self.llm_manager.get_current_config_name() if self.llm_manager else None
        return TaskContext(
            user_id="cli_user",  # 默认用户ID
            session_id=str(uuid.uuid4()),  # 生成新的会话ID
            message_id=str(uuid.uuid4()),  # 生成新的消息ID
            workspace_path=str(self.workspace_path),
            metadata={
                "environment": os.environ.copy(),
                "variables": {
                    "workspace_path": str(self.workspace_path),
                    "workspace_uuid": self.uuid,
                    "llm_config": current_llm_config,
                },
            },
            task_files=[],
            task_images=[],
        )

    # 生命周期管理方法
    async def cleanup(self) -> bool:
        """清理工作区资源（使用 WorkspaceService）

        ⭐ 改动：释放对 WorkspaceContext 的引用，而不是直接停止共享资源

        Returns:
            bool: 清理是否成功

        """
        if not self._initialized:
            return True

        logger.info(f"Cleaning up workspace: {self.uuid}")

        try:
            # 停止自动保存任务
            await self._stop_auto_save_conversation()

            # 保存当前对话
            if self.current_conversation and self.current_conversation.message_count > 0:
                await self.save_current_conversation()

            # 🔧 修复内存泄漏：清理 TaskGraph 的事件处理器
            if self.task_graph:
                try:
                    self.task_graph.cleanup()
                    logger.info(f"  ✓ Cleaned up TaskGraph event handlers")
                except Exception as e:
                    logger.warning(f"  ⚠️ Failed to cleanup TaskGraph handlers: {e}")

            # ⭐ 核心改动：释放对 WorkspaceContext 的引用（不停止共享资源）
            if self._context:
                ref_count_before = self._context.ref_count
                await self._context.release()
                ref_count_after = self._context.ref_count  # 在设为 None 之前获取
                logger.info(f"  ✓ Released WorkspaceContext (refs: {ref_count_before} → {ref_count_after})")
                self._context = None

            self._initialized = False
            self._loaded = False
            logger.info(f"✓ Workspace cleanup completed successfully: {self.uuid}")
            return True

        except Exception as e:
            logger.error(f"Error cleaning up workspace: {e}", exc_info=True)
            return False

    async def reload(self) -> bool:
        """重新加载工作区

        Returns:
            bool: 重新加载是否成功

        """
        logger.info("Reloading workspace...")

        # 先清理（会自动清理 TaskGraph 事件处理器）
        await self.cleanup()

        # 重新初始化（会创建新的 TaskGraph 并注册新的事件处理器）
        success = await self.initialize()
        if success:
            logger.info("Workspace reloaded successfully")
        else:
            logger.error("Failed to reload workspace")

        return success

    def is_initialized(self) -> bool:
        """检查工作区是否已初始化"""
        return self._initialized

    def is_loaded(self) -> bool:
        """检查工作区是否已加载"""
        return self._loaded

    # 序列化方法
    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        # 获取 LLM 配置信息
        current_llm_config = self.llm_manager.get_current_config_name() if self.llm_manager else None
        llm_configs = {}
        if self.llm_manager:
            all_configs = self.llm_manager.get_all_configs()
            llm_configs = {name: config.config.__dict__ for name, config in all_configs.items()}

        return {
            "uuid": self.uuid,
            "absolute_path": self.absolute_path,
            "workspace_info": self.workspace_info.to_dict() if self.workspace_info else None,
            "current_llm_config": current_llm_config,
            "llm_configs": llm_configs,
            "mcp_configs": self.mcp_tool_manager.to_dict() if self.mcp_tool_manager else {},
            "workspace_settings": (self.workspace_settings.__dict__ if self.workspace_settings else None),
            "mode_llm_configs": self.llm_manager.get_mode_configs() if self.llm_manager else {},
            "current_conversation": (
                {
                    "id": self.current_conversation.id,
                    "title": self.current_conversation.title,
                    "message_count": self.current_conversation.message_count,
                }
                if self.current_conversation
                else None
            ),
            "available_tools_count": (len(self.tool_manager.load_tools()) if self.tool_manager else 0),
            "allowed_tools_count": (len(self._get_filtered_tool_names(self.tool_manager.load_tools())) if self.tool_manager else 0),
            "initialized": self._initialized,
            "loaded": self._loaded,
        }

    def __str__(self) -> str:
        """字符串表示"""
        workspace_name = self.workspace_info.display_name if self.workspace_info else "Unknown"
        return f"UserWorkspace(name={workspace_name}, path={self.absolute_path})"

    def __repr__(self) -> str:
        """详细字符串表示"""
        return f"UserWorkspace(uuid={self.uuid}, name={self.workspace_info.display_name if self.workspace_info else 'Unknown'}, path={self.absolute_path}, initialized={self._initialized}, loaded={self._loaded})"

    def check_duplicate_tool_call(self) -> bool:
        """检查当前对话中是否存在重复的工具调用，避免无限循环

        检查 current_conversation 中最近3次工具调用消息，如果是同一工具并且参数也一样，
        说明是无效重复。此时应该 abort task。

        Returns:
            bool: 如果检测到重复工具调用返回 True，否则返回 False

        """
        # 检查是否有 current_conversation 和消息
        if not self.current_conversation or not self.current_conversation.messages:
            return False

        # 获取最近的消息
        messages = self.current_conversation.messages

        # 收集最近的工具调用
        recent_tool_calls = []

        # 从最新消息开始向前查找工具调用
        for i in range(len(messages) - 1, -1, -1):
            message = messages[i]

            # 如果是 AI 消息并且有工具调用
            from dawei.entity.lm_messages import AssistantMessage, ToolCall

            if isinstance(message, AssistantMessage) and hasattr(message, "tool_calls") and message.tool_calls:
                for tool_call in message.tool_calls:
                    if isinstance(tool_call, ToolCall):
                        recent_tool_calls.append(
                            {
                                "name": tool_call.function.name,
                                "parameters": tool_call.function.arguments,
                                "tool_call_id": tool_call.tool_call_id,
                                "message_index": i,
                            },
                        )

            # 如果已经找到3个工具调用，停止搜索
            if len(recent_tool_calls) >= 3:
                break

        # 如果工具调用少于3个，不进行重复检查
        if len(recent_tool_calls) < 3:
            return False

        # 检查最近3个工具调用是否是同一工具并且参数相同
        # 注意：recent_tool_calls 是按时间倒序排列的，所以最近的是第一个
        latest_call = recent_tool_calls[0]
        second_call = recent_tool_calls[1]
        third_call = recent_tool_calls[2]

        # 检查工具名称是否相同
        if latest_call["name"] == second_call["name"] == third_call["name"]:
            # 检查参数是否相同
            if latest_call["parameters"] == second_call["parameters"] == third_call["parameters"]:
                return True

        return False

    async def _on_persist_task_graph(self, event: Any) -> None:
        """处理任务图持久化事件

        当 TaskGraph 发生变化时，此方法被调用以触发保存

        Args:
            event: 持久化事件，包含 task_graph_id

        """
        try:
            # 提取事件数据
            if hasattr(event, "data") and hasattr(event.data, "get_event_data"):
                data = event.data.get_event_data()
            elif hasattr(event, "data"):
                data = event.data if isinstance(event.data, dict) else {}
            else:
                data = {}

            task_graph_id = data.get("task_graph_id")

            if not task_graph_id:
                logger.warning("Persist task graph event missing task_graph_id")
                return

            # 验证 TaskGraph 存在
            if not self.task_graph or self.task_graph.task_node_id != task_graph_id:
                logger.warning(f"TaskGraph {task_graph_id} not found in workspace")
                return

            # 调用现有的 save_task_graph 方法
            success = await self.save_task_graph(self.task_graph)

            if success:
                logger.info(f"Task graph {task_graph_id} persisted successfully")
            else:
                logger.warning(f"Task graph {task_graph_id} persistence returned False")

        except Exception as e:
            logger.error(f"Error persisting task graph: {e}", exc_info=True)
            # 不重新抛出异常，避免中断事件处理

    async def save_task_graph(self, task_graph) -> bool:
        """保存任务图到文件 (使用持久化管理器)

        Args:
            task_graph: 任务图实例

        Returns:
            bool: 保存是否成功

        """
        try:
            # 准备任务图数据
            all_tasks = await task_graph.get_all_tasks()

            # all_tasks 是 List[TaskNode],需要转换为字典
            nodes_dict = {}
            for task in all_tasks:
                # 🔥 修复：使用 task_node_id 而不是 task_id，且 to_dict() 不是异步方法
                task_id = task.task_node_id
                nodes_dict[task_id] = task.to_dict()

            task_data = {
                "task_graph_id": task_graph.task_node_id,
                "timestamp": datetime.now(UTC).isoformat(),
                "nodes": nodes_dict,
                "total_tasks": len(all_tasks),
            }

            # 首先尝试使用持久化管理器保存
            if self.persistence_manager:
                success = await self.persistence_manager.save_task_graph(
                    task_graph.task_node_id,
                    task_data,
                )

                if success:
                    logger.info(
                        f"Task graph saved via persistence manager: {task_graph.task_node_id}",
                    )

                    # 根据配置决定是否保存旧格式

                    return True
                logger.warning(
                    "Persistence manager save failed for task graph",
                )

        except Exception as e:
            logger.error(f"Failed to save task graph: {e}", exc_info=True)
            # 发送持久化失败告警
            await self._alert_persistence_failure(
                "task_graph",
                f"Failed to save task graph: {e!s}",
                task_graph_id=task_graph.task_node_id,
            )
            raise TaskGraphPersistenceError(
                f"Failed to save task graph: {e}",
                task_graph_id=task_graph.task_node_id,
            )

    async def load_task_graph(self) -> Any | None:
        """从文件恢复任务图

        Returns:
            任务图实例或None

        """
        try:
            if not self.tasks_file.exists():
                logger.info("No task graph file found, creating empty task graph")
                return None

            with Path(self.tasks_file).open(encoding="utf-8") as f:
                task_data = json.load(f)

            logger.info(f"Task graph loaded from {self.tasks_file}")

            # 这里返回任务图数据，而不是TaskGraph实例
            # 因为TaskGraph的创建需要event_bus参数
            return task_data

        except Exception:
            logger.exception("Failed to load task graph: ")
            return None

    async def create_or_restore_task_graph(self):
        """创建或恢复任务图
        Returns:
            TaskGraph: 任务图实例
        """
        from dawei.task_graph.task_graph import TaskGraph

        # 尝试恢复任务图
        task_graph_data = await self.load_task_graph()

        if task_graph_data:
            # 创建新的TaskGraph实例
            task_graph = TaskGraph(
                task_id=task_graph_data["task_graph_id"],
                event_bus=None,  # 不再使用 workspace 的 event_bus
            )

            # 恢复节点数据
            from dawei.task_graph.task_node import TaskNode
            from dawei.task_graph.task_node_data import TaskData

            # 先创建所有节点
            nodes = {}
            for task_id, node_data in task_graph_data["nodes"].items():
                # 创建TaskData
                task_data_obj = TaskData.from_dict(node_data["data"])

                # 创建TaskNode
                task_node = TaskNode.create_child(task_node_id=task_id, description=task_data_obj.description, mode=task_data_obj.mode, parent_id=node_data["parent_id"]) if node_data.get("parent_id") else TaskNode.create_root(task_node_id=task_id, description=task_data_obj.description, mode=task_data_obj.mode)

                nodes[task_id] = task_node

            # 创建根节点
            root_task_id = None
            for task_id, node_data in task_graph_data["nodes"].items():
                if not node_data.get("parent_id"):
                    root_task_id = task_id
                    break

            if root_task_id and root_task_id in nodes:
                root_task = nodes[root_task_id]
                await task_graph.create_root_task(root_task.data)

                # 更新子节点关系
                for task_id, node_data in task_graph_data["nodes"].items():
                    if node_data.get("parent_id"):
                        for child_id in node_data["child_ids"]:
                            if child_id in task_graph_data["nodes"]:
                                await task_graph.create_subtask(
                                    task_id,
                                    TaskData.from_dict(task_graph_data["nodes"][child_id]["data"]),
                                )

            logger.info(f"Task graph restored with {len(task_graph_data['nodes'])} nodes")
            return task_graph

        # 创建空的任务图
        logger.info("Creating empty task graph")
        # 🔴 修复：TaskGraph 不再使用 UserWorkspace 的 event_bus
        return TaskGraph(task_id="default", event_bus=None)

    # ==================== 持久化失败告警机制 ====================

    async def _alert_persistence_failure(self, resource_type: str, error_message: str, **kwargs):
        """发送持久化失败告警

        Args:
            resource_type: 资源类型 (workspace_info, conversation, task_graph, checkpoint)
            error_message: 错误信息
            **kwargs: 额外的上下文信息 (conversation_id, task_graph_id, checkpoint_id等)

        """
        try:
            # 构建告警数据
            alert_data = {
                "alert_type": "persistence_failure",
                "resource_type": resource_type,
                "error_message": error_message,
                "timestamp": datetime.now(UTC).isoformat(),
                "workspace_path": self.absolute_path,
                "workspace_id": self.workspace_info.id if self.workspace_info else self.uuid,
                **kwargs,
            }

            # 1. 记录到错误日志
            logger.error(
                f"[PERSISTENCE_FAILURE] {resource_type}: {error_message}",
                extra={"alert_data": alert_data},
            )

            # 🔴 修复：UserWorkspace 不再使用 event_bus,所以不发送事件
            # 如果需要发送事件，应该使用 Agent 的 event_bus
            # if self.event_bus:
            #     try:
            #         await self.event_bus.emit("persistence_failure", alert_data)
            #     except Exception as e:
            #         logger.warning(f"Failed to emit persistence_failure event: {e}")

            # 3. 保存到持久化失败日志文件
            await self._log_persistence_failure(alert_data)

            # 4. 如果有WebSocket连接,发送实时通知 (可选)
            # 这需要访问WebSocket服务器,暂时跳过

        except Exception as e:
            logger.error(f"Failed to send persistence failure alert: {e}", exc_info=True)

    async def _log_persistence_failure(self, alert_data: dict[str, Any]):
        """将持久化失败记录到日志文件

        Args:
            alert_data: 告警数据

        """
        try:
            # 创建持久化失败日志目录
            failure_log_dir = self.workspace_path / ".dawei" / "persistence_failures"
            failure_log_dir.mkdir(parents=True, exist_ok=True)

            # 生成日志文件名
            timestamp = datetime.now(UTC).strftime("%Y%m%d")
            log_file = failure_log_dir / f"failures_{timestamp}.jsonl"

            # 追加写入日志 (JSONL格式)
            with Path(log_file, "a").open(encoding="utf-8") as f:
                f.write(json.dumps(alert_data, ensure_ascii=False) + "\n")

            logger.debug(f"Persistence failure logged to {log_file}")

        except Exception as e:
            logger.warning(f"Failed to log persistence failure to file: {e}")

    async def get_persistence_failures(self, limit: int = 100) -> list[dict[str, Any]]:
        """获取持久化失败记录

        Args:
            limit: 最多返回的失败记录数

        Returns:
            失败记录列表,按时间倒序

        Raises:
            PersistenceError: 当读取持久化失败文件失败时
            FileNotFoundError: 当失败日志目录不存在时

        """
        failure_log_dir = self.workspace_path / ".dawei" / "persistence_failures"

        if not failure_log_dir.exists():
            return []

        # 读取所有失败日志文件
        failures = []
        for log_file in sorted(failure_log_dir.glob("failures_*.jsonl"), reverse=True):
            with Path(log_file).open(encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            failure = json.loads(line)
                            failures.append(failure)
                            if len(failures) >= limit:
                                break
                        except json.JSONDecodeError:
                            continue

            if len(failures) >= limit:
                break

        return failures

    def clear_persistence_failures(self) -> bool:
        """清除持久化失败日志

        Returns:
            是否清除成功

        Raises:
            PersistenceError: 当清除持久化失败日志失败时
            OSError: 当文件系统操作失败时

        """
        failure_log_dir = self.workspace_path / ".dawei" / "persistence_failures"

        if failure_log_dir.exists():
            import shutil

            shutil.rmtree(failure_log_dir)
            logger.info("Cleared persistence failure logs")

        return True

    # ==================== 对话自动保存机制 ====================

    async def _start_auto_save_conversation(self):
        """启动对话自动保存任务"""
        if not self._auto_save_enabled:
            logger.info("Auto-save is disabled")
            return

        if self._auto_save_task is not None:
            logger.warning("Auto-save task is already running")
            return

        logger.info(f"Starting auto-save task (interval: {self._auto_save_interval}s)")
        self._auto_save_task = asyncio.create_task(self._auto_save_conversation_loop())
        logger.info("Auto-save task started")

    async def _stop_auto_save_conversation(self):
        """停止对话自动保存任务"""
        if self._auto_save_task is None:
            return

        logger.info("Stopping auto-save task...")

        # 取消任务
        self._auto_save_task.cancel()

        try:
            await self._auto_save_task
        except asyncio.CancelledError:
            logger.info("Auto-save task cancelled")

        self._auto_save_task = None
        logger.info("Auto-save task stopped")

    async def _auto_save_conversation_loop(self):
        """自动保存对话循环"""
        while self._initialized:
            await asyncio.sleep(self._auto_save_interval)

            # 检查是否需要保存
            if self.current_conversation and self._should_auto_save_conversation():
                logger.debug("Auto-saving conversation...")
                success = await self.save_current_conversation()

                if success:
                    self._last_message_count = self.current_conversation.message_count
                    logger.debug(
                        f"Conversation auto-saved ({self.current_conversation.message_count} messages)",
                    )
                else:
                    logger.warning("Conversation auto-save failed")

        logger.info("Auto-save loop completed")

    def _should_auto_save_conversation(self) -> bool:
        """判断是否应该自动保存对话"""
        if not self.current_conversation:
            return False

        # 检查消息数量是否增加
        current_count = self.current_conversation.message_count
        if current_count > self._last_message_count:
            return True

        # 检查是否有未保存的更改
        # (可以根据需要添加更多检查条件)

        return False

    async def set_auto_save_interval(self, interval_seconds: int):
        """设置自动保存间隔

        Args:
            interval_seconds: 保存间隔(秒)

        """
        if interval_seconds < 5:
            logger.warning("Auto-save interval too short, using minimum 5 seconds")
            interval_seconds = 5

        old_interval = self._auto_save_interval
        self._auto_save_interval = interval_seconds
        logger.info(f"Auto-save interval changed: {old_interval}s -> {interval_seconds}s")

        # 重启自动保存任务
        if self._auto_save_task is not None:
            await self._stop_auto_save_conversation()
            await self._start_auto_save_conversation()

    def enable_auto_save(self):
        """启用自动保存"""
        if not self._auto_save_enabled:
            self._auto_save_enabled = True
            logger.info("Auto-save enabled")

    def disable_auto_save(self):
        """禁用自动保存"""
        if self._auto_save_enabled:
            self._auto_save_enabled = False
            logger.info("Auto-save disabled")

    # ==================== 持久化重试机制 ====================

    async def _save_with_retry(self, save_func, resource_type: str, *args, **kwargs) -> bool:
        """带重试的持久化保存

        Args:
            save_func: 保存函数
            resource_type: 资源类型(用于日志)
            *args: 传递给保存函数的位置参数
            **kwargs: 传递给保存函数的关键字参数

        Returns:
            bool: 是否保存成功

        """
        last_exception = None

        for attempt in range(self._max_retry_attempts):
            try:
                # 尝试保存
                result = await save_func(*args, **kwargs)

                if result:
                    if attempt > 0:
                        logger.info(f"{resource_type} saved successfully after {attempt} retries")
                    return True
                # 保存失败但没抛出异常
                last_exception = Exception("Save function returned False")
                logger.warning(
                    f"{resource_type} save attempt {attempt + 1}/{self._max_retry_attempts} failed",
                )

            except Exception as e:
                last_exception = e
                logger.warning(
                    f"{resource_type} save attempt {attempt + 1}/{self._max_retry_attempts} failed: {e}",
                )

            # 如果不是最后一次尝试,等待后重试
            if attempt < self._max_retry_attempts - 1:
                delay = self._calculate_retry_delay(attempt)
                logger.info(f"Retrying {resource_type} save in {delay:.1f} seconds...")
                await asyncio.sleep(delay)

        # 所有重试都失败了
        logger.error(
            f"{resource_type} save failed after {self._max_retry_attempts} attempts: {last_exception}",
        )

        # 发送持久化失败告警
        await self._alert_persistence_failure(
            resource_type,
            f"Failed after {self._max_retry_attempts} retries: {last_exception!s}",
        )

        return False

    def _calculate_retry_delay(self, attempt: int) -> float:
        """计算重试延迟(指数退避)

        Args:
            attempt: 当前尝试次数(从0开始)

        Returns:
            float: 延迟秒数

        """
        # 指数退避: delay = base_delay * (multiplier ^ attempt)
        delay = self._retry_base_delay * (self._retry_backoff_multiplier**attempt)

        # 限制最大延迟
        return min(delay, self._retry_max_delay)

    async def save_workspace_info_with_retry(self) -> bool:
        """带重试的 Workspace 信息保存

        Returns:
            bool: 是否保存成功

        """
        return await self._save_with_retry(self._save_workspace_info, "workspace_info")

    async def save_conversation_with_retry(self) -> bool:
        """带重试的对话保存

        Returns:
            bool: 是否保存成功

        """
        return await self._save_with_retry(self.save_current_conversation, "conversation")

    async def save_task_graph_with_retry(self, task_graph) -> bool:
        """带重试的任务图保存

        Args:
            task_graph: 任务图实例

        Returns:
            bool: 是否保存成功

        """
        return await self._save_with_retry(self.save_task_graph, "task_graph", task_graph)

    # ==================== UI 上下文自动保存 ====================

    async def update_ui_context_auto(
        self,
        open_files: list[str] | None = None,
        current_file: str | None = None,
        current_selected_content: str | None = None,
        current_mode: str | None = None,
        conversation_id: str | None = None,
    ) -> bool:
        """自动更新并保存 UI 上下文

        Args:
            open_files: 打开的文件列表
            current_file: 当前文件
            current_selected_content: 当前选中内容
            current_mode: 当前模式
            conversation_id: 当前对话ID

        Returns:
            bool: 是否更新保存成功

        """
        if not self.workspace_info or not self.workspace_info.user_ui_context:
            logger.warning("Cannot update UI context: workspace_info or user_ui_context is None")
            return False

        # 更新 UI 上下文

        context = self.workspace_info.user_ui_context

        if open_files is not None:
            context.open_files = open_files
            self._ui_context_dirty = True

        if current_file is not None:
            context.current_file = current_file
            self._ui_context_dirty = True

        if current_selected_content is not None:
            context.current_selected_content = current_selected_content
            self._ui_context_dirty = True

        if current_mode is not None:
            context.current_mode = current_mode
            self._ui_context_dirty = True

        if conversation_id is not None:
            context.conversation_id = conversation_id
            self._ui_context_dirty = True

        # 如果有更新,自动保存
        if self._ui_context_dirty:
            return await self.save_workspace_info_with_retry()

        return True

    async def on_file_opened(self, file_path: str):
        """文件打开时自动保存 UI 上下文

        Args:
            file_path: 打开的文件路径

        """
        if not self.workspace_info or not self.workspace_info.user_ui_context:
            return

        context = self.workspace_info.user_ui_context

        # 添加到打开文件列表(如果不存在)
        if file_path not in context.open_files:
            context.open_files.append(file_path)

        # 设置为当前文件
        context.current_file = file_path

        # 自动保存
        await self.update_ui_context_auto(open_files=context.open_files, current_file=file_path)

    async def on_file_closed(self, file_path: str):
        """文件关闭时自动保存 UI 上下文

        Args:
            file_path: 关闭的文件路径

        """
        if not self.workspace_info or not self.workspace_info.user_ui_context:
            return

        context = self.workspace_info.user_ui_context

        # 从打开文件列表移除
        if file_path in context.open_files:
            context.open_files.remove(file_path)

        # 如果关闭的是当前文件,清除当前文件
        if context.current_file == file_path:
            context.current_file = context.open_files[-1] if context.open_files else None

        # 自动保存
        await self.update_ui_context_auto(
            open_files=context.open_files,
            current_file=context.current_file,
        )

    async def on_conversation_changed(self, conversation_id: str):
        """对话切换时自动保存 UI 上下文

        Args:
            conversation_id: 新的对话ID

        """
        await self.update_ui_context_auto(conversation_id=conversation_id)

    async def on_mode_changed(self, mode: str):
        """模式切换时自动保存 UI 上下文

        Args:
            mode: 新的模式

        """
        await self.update_ui_context_auto(current_mode=mode)


# 便捷函数
async def create_workspace(workspace_path: str) -> UserWorkspace:
    """创建并初始化工作区的便捷函数

    Args:
        workspace_path: 工作区路径

    Returns:
        UserWorkspace: 初始化后的工作区实例

    """
    workspace = UserWorkspace(workspace_path)
    await workspace.initialize()
    return workspace


def load_workspace(workspace_path: str) -> UserWorkspace:
    """加载工作区的便捷函数（同步版本，仅创建实例）

    Args:
        workspace_path: 工作区路径

    Returns:
        UserWorkspace: 工作区实例

    """
    return UserWorkspace(workspace_path)
