# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Workspace数据模型

定义工作区的核心数据结构
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

from dawei.entity.system_info import (
    SystemEnvironments,
    UserUIContext,
    UserUIEnvironments,
)

logger = logging.getLogger(__name__)


@dataclass
class WorkspaceInfo:
    """工作区基本信息"""

    id: str
    name: str
    display_name: str
    description: str
    created_at: datetime
    is_active: bool = True
    files_list: list[str] = field(default_factory=list)
    system_environments: SystemEnvironments = field(
        default_factory=SystemEnvironments,
    )  # 系统后端环境如os,python,内存等
    user_ui_environments: UserUIEnvironments = field(
        default_factory=UserUIEnvironments,
    )  # 用户前端静态环境信息如浏览器操作系统语言时区等
    user_ui_context: UserUIContext = field(
        default_factory=UserUIContext,
    )  # 用户前端动态上下文信息如打开的文件当前文件选中内容当前模式等

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkspaceInfo":
        """从字典创建工作区信息"""
        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00")) if created_at.endswith("Z") else datetime.fromisoformat(created_at)
        elif created_at is None:
            created_at = datetime.now(timezone.utc)

        # 处理系统环境信息
        system_env_data = data.get("system_environments", {})
        system_environments = SystemEnvironments.from_dict(system_env_data) if isinstance(system_env_data, dict) else SystemEnvironments()

        # 处理用户UI环境信息（静态）
        user_ui_env_data = data.get("user_ui_environments", {})
        user_ui_environments = UserUIEnvironments.from_dict(user_ui_env_data) if isinstance(user_ui_env_data, dict) else UserUIEnvironments()

        # 处理用户UI上下文信息（动态）
        user_ui_context_data = data.get("user_ui_context", {})
        user_ui_context = UserUIContext.from_dict(user_ui_context_data) if isinstance(user_ui_context_data, dict) else UserUIContext()

        return cls(
            id=data.get("id", str(uuid.uuid4())),
            name=data.get("name", ""),
            display_name=data.get("display_name", data.get("name", "")),
            description=data.get("description", ""),
            created_at=created_at,
            is_active=data.get("is_active", True),
            files_list=data.get("files_list", []),
            system_environments=system_environments,
            user_ui_environments=user_ui_environments,
            user_ui_context=user_ui_context,
        )

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "created_at": self.created_at.isoformat(),
            "is_active": self.is_active,
            "files_list": self.files_list,
            "system_environments": self.system_environments.to_dict(),
            "user_ui_environments": self.user_ui_environments.to_dict(),
            "user_ui_context": self.user_ui_context.to_dict(),
        }


@dataclass
class WorkspaceSettings:
    """工作区设置类"""

    auto_approval_enabled: bool = True
    always_allow_read_only: bool = True
    always_allow_read_only_outside_workspace: bool = False
    always_allow_write: bool = True
    always_allow_write_outside_workspace: bool = False
    always_allow_write_protected: bool = False
    write_delay_ms: int = 1000
    always_allow_browser: bool = True
    always_approve_resubmit: bool = True
    request_delay_seconds: int = 10
    always_allow_mcp: bool = True
    always_allow_mode_switch: bool = True
    always_allow_subtasks: bool = True
    always_allow_execute: bool = True
    always_allow_followup_questions: bool = True
    followup_auto_approve_timeout_ms: int = 60000
    always_allow_update_todo_list: bool = True
    allowed_commands: list[str] = field(default_factory=list)
    denied_commands: list[str] = field(default_factory=list)
    max_concurrent_file_reads: int = 5
    max_workspace_files: int = 200
    max_read_file_line: int = -1
    max_image_file_size: int = 5
    max_total_image_size: int = 20
    terminal_output_line_limit: int = 500
    terminal_output_character_limit: int = 50000

    @classmethod
    def from_dict(cls, config_dict: dict[str, Any]) -> "WorkspaceSettings":
        """从字典创建工作区设置"""
        return cls(
            auto_approval_enabled=config_dict.get("autoApprovalEnabled", True),
            always_allow_read_only=config_dict.get("alwaysAllowReadOnly", True),
            always_allow_read_only_outside_workspace=config_dict.get(
                "alwaysAllowReadOnlyOutsideWorkspace",
                False,
            ),
            always_allow_write=config_dict.get("alwaysAllowWrite", True),
            always_allow_write_outside_workspace=config_dict.get(
                "alwaysAllowWriteOutsideWorkspace",
                False,
            ),
            always_allow_write_protected=config_dict.get("alwaysAllowWriteProtected", False),
            write_delay_ms=config_dict.get("writeDelayMs", 1000),
            always_allow_browser=config_dict.get("browserToolEnabled", True),
            always_approve_resubmit=config_dict.get("alwaysApproveResubmit", True),
            request_delay_seconds=config_dict.get("requestDelaySeconds", 10),
            always_allow_mcp=config_dict.get("mcpEnabled", True),
            always_allow_mode_switch=config_dict.get("alwaysAllowModeSwitch", True),
            always_allow_subtasks=config_dict.get("alwaysAllowSubtasks", True),
            always_allow_execute=config_dict.get("alwaysAllowExecute", True),
            always_allow_followup_questions=config_dict.get("alwaysAllowFollowupQuestions", True),
            followup_auto_approve_timeout_ms=config_dict.get("followupAutoApproveTimeoutMs", 60000),
            always_allow_update_todo_list=config_dict.get("alwaysAllowUpdateTodoList", True),
            allowed_commands=config_dict.get("allowedCommands", []),
            denied_commands=config_dict.get("deniedCommands", []),
            max_concurrent_file_reads=config_dict.get("maxConcurrentFileReads", 5),
            max_workspace_files=config_dict.get("maxWorkspaceFiles", 200),
            max_read_file_line=config_dict.get("maxReadFileLine", -1),
            max_image_file_size=config_dict.get("maxImageFileSize", 5),
            max_total_image_size=config_dict.get("maxTotalImageSize", 20),
            terminal_output_line_limit=config_dict.get("terminalOutputLineLimit", 500),
            terminal_output_character_limit=config_dict.get("terminalOutputCharacterLimit", 50000),
        )


# ============================================================================
# Workspace Configuration Models (Pydantic)
# ============================================================================


class AgentConfig(BaseModel):
    """Agent 执行配置"""

    mode: Literal["orchestrator", "plan", "do", "check", "act"] = "orchestrator"
    plan_mode_confirm_required: bool = True
    enable_auto_mode_switch: bool = False
    auto_approve_tools: bool = True
    max_concurrent_subtasks: int = 3


class MemoryConfig(BaseModel):
    """内存系统配置"""

    enabled: bool = True
    virtual_page_size: int = 2000
    max_active_pages: int = 5
    default_energy: float = 1.0
    energy_decay_rate: float = 0.1
    min_energy_threshold: float = 0.2


class CheckpointConfig(BaseModel):
    """检查点配置"""

    checkpoint_interval: int = 300
    max_checkpoints: int = 10
    enable_compression: bool = True
    auto_create_enabled: bool = True
    min_interval_minutes: int = 5
    max_checkpoints_per_task: int = 50
    validation_enabled: bool = True


class CompressionConfig(BaseModel):
    """对话压缩配置"""

    enabled: bool = False
    preserve_recent: int = 20
    max_tokens: int = 100000
    compression_threshold: float = 0.5
    aggressive_threshold: float = 0.9
    page_size: int = 20
    max_active_pages: int = 5
    memory_integration_enabled: bool = True
    auto_extract_memories: bool = True
    auto_store_memories: bool = True


class SkillsConfig(BaseModel):
    """Skills 配置"""

    enabled: bool = True
    auto_discovery: bool = True


class ToolsConfig(BaseModel):
    """工具配置"""

    builtin_tools_enabled: bool = True
    system_tools_enabled: bool = True
    user_tools_enabled: bool = True
    workspace_tools_enabled: bool = True
    default_timeout: int = 60
    max_concurrent_executions: int = 3


class LoggingConfig(BaseModel):
    """日志配置"""

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    dir: str = "~/.dawei/logs"
    max_file_size: int = 10
    backup_count: int = 5
    console_output: bool = True
    file_output: bool = True
    enable_performance_logging: bool = True
    sanitize_sensitive_data: bool = True


class MonitoringConfig(BaseModel):
    """监控配置"""

    prometheus_enabled: bool = True
    prometheus_port: int = 9090


class AnalyticsConfig(BaseModel):
    """分析配置"""

    enabled: bool = True
    retention_days: int = 90
    sampling_rate: float = 1.0
    anonymize_enabled: bool = True




class PluginInstanceConfig(BaseModel):
    """单个插件实例的配置（动态结构）"""

    enabled: bool = True
    activated: bool = False
    settings: dict[str, Any] = Field(default_factory=dict)
    version: str | None = None
    install_path: str | None = None


class PluginsConfig(BaseModel):
    """插件配置（第二层：动态配置）

    插件配置特点：
    - 动态结构：插件ID和配置项都是运行时确定的
    - 独立存储：保存在 .dawei/plugins/{plugin_id}.json
    - 灵活扩展：每个插件可以有自己独特的配置字段
    """

    plugins: dict[str, PluginInstanceConfig] = Field(default_factory=dict)
    max_plugins: int = 50
    auto_discovery: bool = True
    enabled: bool = True

    def get_plugin_config(self, plugin_id: str) -> PluginInstanceConfig | None:
        """获取指定插件的配置

        Args:
            plugin_id: 插件ID

        Returns:
            插件配置如果不存在则返回 None
        """
        return self.plugins.get(plugin_id)

    def set_plugin_config(self, plugin_id: str, config: PluginInstanceConfig) -> None:
        """设置插件配置

        Args:
            plugin_id: 插件ID
            config: 插件配置
        """
        self.plugins[plugin_id] = config

    def enable_plugin(self, plugin_id: str) -> None:
        """启用插件"""
        if plugin_id in self.plugins:
            self.plugins[plugin_id].enabled = True

    def disable_plugin(self, plugin_id: str) -> None:
        """禁用插件"""
        if plugin_id in self.plugins:
            self.plugins[plugin_id].enabled = False


class WorkspaceConfig(BaseModel):
    """工作区统一配置模型（第一层：系统配置）

    使用 Pydantic 进行类型验证和序列化
    包含所有配置节：agent, memory, skills, tools 等
    """

    agent: AgentConfig = Field(default_factory=AgentConfig)
    checkpoint: CheckpointConfig = Field(default_factory=CheckpointConfig)
    compression: CompressionConfig = Field(default_factory=CompressionConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    skills: SkillsConfig = Field(default_factory=SkillsConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)
    analytics: AnalyticsConfig = Field(default_factory=AnalyticsConfig)
    # ✨ 新增：插件配置（第二层：动态配置）
    plugins: PluginsConfig = Field(default_factory=PluginsConfig)

    @classmethod
    def from_dict(cls, config_dict: dict[str, Any] | None) -> "WorkspaceConfig":
        """从字典创建配置合并默认值

        Args:
            config_dict: 配置字典如果为 None 则使用默认值

        Returns:
            WorkspaceConfig 实例
        """
        if config_dict is None:
            return cls()

        # 创建默认配置
        default_config = cls()

        # 更新提供的配置节
        update_data = {}
        for key in cls.model_fields:
            if key in config_dict and isinstance(config_dict[key], dict):
                # 合并配置节（保留默认值只更新提供的字段）
                default_section = getattr(default_config, key).model_dump()
                update_data[key] = {**default_section, **config_dict[key]}

        # 特殊处理：插件配置从独立文件加载
        # 插件配置保存在 .dawei/plugins/{plugin_id}.json
        # 在这里不处理 plugins由 UserWorkspace 单独管理

        return cls(**update_data)

    def model_dump_custom(self) -> dict[str, Any]:
        """转换为字典（自定义序列化）

        Returns:
            配置字典格式与 config.json 兼容
        """
        return {
            "agent": self.agent.model_dump(),
            "checkpoint": self.checkpoint.model_dump(),
            "compression": self.compression.model_dump(),
            "memory": self.memory.model_dump(),
            "skills": self.skills.model_dump(),
            "tools": self.tools.model_dump(),
            "logging": self.logging.model_dump(),
            "monitoring": self.monitoring.model_dump(),
            "analytics": self.analytics.model_dump(),
            "plugins": self.plugins.model_dump(),  # ✨ 新增：插件配置
        }
