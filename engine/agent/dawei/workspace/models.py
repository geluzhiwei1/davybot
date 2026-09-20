# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Workspace数据模型

定义工作区的核心数据结构
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Dict, List, Literal

from pydantic import BaseModel, Field, field_validator

from dawei.core.datetime_compat import UTC
from dawei.entity.system_info import (
    SystemEnvironments,
    UserUIContext,
    UserUIEnvironments,
)
from dawei.config.settings import KnowledgeConfig

logger = logging.getLogger(__name__)


# ============================================================================
# Workspace Type Enums
# ============================================================================


class WorkspaceCategory(StrEnum):
    """工作区大类（对应前端的侧边栏分组）"""

    GENERAL = "general"         # 通用工作区
    AI_TASK = "ai_task"         # AI 任务（简单/定时任务）
    IP = "ip"                   # 知识产权
    COMPLIANCE = "compliance"   # 合规管理
    LAW_FIRM = "law_firm"       # 律所运营（预留，nn-flow 使用）
    SYSTEM = "system"           # 系统


class WorkspaceType(StrEnum):
    """工作区精确类型 —— 唯一权威来源"""

    # ── 通用工作区 ──
    USER = "user"               # 用户手动创建的持久工作区

    # ── AI 任务 ──
    SIMPLE_TASK = "simple_task"         # 简单任务（一次性）
    SCHEDULED_TASK = "scheduled_task"   # 定时任务（周期性）
    DEEP_RESEARCH = "deep-research"     # 深度调研（每个调研任务 = 一个独立工作区）

    # ── 知识产权 (IP) ──
    IP_IDEA_VAULT = "ip-idea-vault"             # M1: 创意保险箱
    IP_DISCLOSURE = "ip-disclosure"             # M2: 发明披露
    IP_DRAFT = "ip-draft"                       # M3: 专利撰写
    IP_APPLICATION = "ip-application"           # M4b: 专利申请
    IP_FILING = "ip-filing"                     # M4: 申请管理
    IP_OA_REPLY = "ip-oa-reply"                 # M5: OA 答复
    IP_REVERSE_DETECTION = "ip-reverse-detection" # M6: 反向侵权检测
    IP_PORTFOLIO = "ip-portfolio"               # M7: 资产组合仪表盘
    IP_TRADEMARK = "ip-trademark"               # M8: 商标注册

    # ── 合规管理 ──
    COMPLIANCE_PROJECT = "compliance"   # 合规项目（由合规模板初始化）

    # ── 团队/系统（预留） ──
    TEAM = "team"
    SYSTEM = "system"

    # ── 辅助属性 ──

    @property
    def category(self) -> "WorkspaceCategory":
        """推断工作区所属大类"""
        if self.value.startswith("ip-"):
            return WorkspaceCategory.IP
        if self.value == "compliance":
            return WorkspaceCategory.COMPLIANCE
        if self.value in ("simple_task", "scheduled_task", "deep-research"):
            return WorkspaceCategory.AI_TASK
        if self.value == "user":
            return WorkspaceCategory.GENERAL
        if self.value == "team":
            return WorkspaceCategory.LAW_FIRM
        if self.value == "system":
            return WorkspaceCategory.SYSTEM
        return WorkspaceCategory.GENERAL

    @property
    def is_temporary(self) -> bool:
        """是否临时工作区"""
        return self.value in ("simple_task", "scheduled_task") or self.value.startswith("ip-")

    @property
    def is_ip(self) -> bool:
        """是否为 IP 工作区"""
        return self.value.startswith("ip-")


# IP 子模块 slug 列表（由枚举自动生成，无需硬编码）
IP_MODULE_TYPES: tuple[str, ...] = tuple(
    t.value for t in WorkspaceType if t.value.startswith("ip-")
)


class WorkspaceLifecycle(StrEnum):
    """工作区生命周期"""

    PERSISTENT = "persistent"    # 永久，手动删除
    TEMPORARY = "temporary"      # 临时，可自动清理
    ARCHIVED = "archived"        # 归档


@dataclass
class WorkspaceInfo:
    """工作区基本信息"""

    id: str
    name: str
    display_name: str
    description: str
    created_at: datetime
    owner_user_id: str = "default_user"  # 多租户：工作区归属用户 ID
    is_active: bool = True
    files_list: List[str] = field(default_factory=list)
    system_environments: SystemEnvironments = field(
        default_factory=SystemEnvironments,
    )  # 系统后端环境如os,python,内存等
    user_ui_environments: UserUIEnvironments = field(
        default_factory=UserUIEnvironments,
    )  # 用户前端静态环境信息如浏览器操作系统语言时区等
    user_ui_context: UserUIContext = field(
        default_factory=UserUIContext,
    )  # 用户前端动态上下文信息如打开的文件当前文件选中内容当前模式等

    # 统一工作区类型字段
    workspace_type: str = WorkspaceType.USER.value
    lifecycle: str = WorkspaceLifecycle.PERSISTENT.value
    source_task_id: str | None = None
    source_task_type: str | None = None
    last_accessed_at: datetime | None = None
    # 业务模块标识（如 research-review）：创建时由前端固化传入。
    # mode 收紧策略（core.WORKSPACE_MODULE_AGENTS）按它把工作区可见
    # modes 收敛为本模块相关 agent/mode，而非全部已装团队的并集。
    biz_module: str | None = None

    @property
    def workspace_category(self) -> str:
        """从 workspace_type 推导大类（不持久化）"""
        try:
            wt = WorkspaceType(self.workspace_type)
            return wt.category.value
        except ValueError:
            return WorkspaceCategory.GENERAL.value

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkspaceInfo":
        """从字典创建工作区信息"""
        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00")) if created_at.endswith("Z") else datetime.fromisoformat(created_at)
        elif created_at is None:
            created_at = datetime.now(UTC)

        last_accessed_at = data.get("last_accessed_at")
        if isinstance(last_accessed_at, str):
            last_accessed_at = datetime.fromisoformat(last_accessed_at.replace("Z", "+00:00")) if last_accessed_at.endswith("Z") else datetime.fromisoformat(last_accessed_at)
        elif last_accessed_at is not None and not isinstance(last_accessed_at, datetime):
            last_accessed_at = None

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
            workspace_type=data.get("workspace_type", WorkspaceType.USER.value),
            lifecycle=data.get("lifecycle", WorkspaceLifecycle.PERSISTENT.value),
            source_task_id=data.get("source_task_id"),
            source_task_type=data.get("source_task_type"),
            last_accessed_at=last_accessed_at,
            biz_module=data.get("biz_module"),
        )

    def to_dict(self) -> Dict[str, Any]:
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
            "workspace_type": self.workspace_type,
            "lifecycle": self.lifecycle,
            "source_task_id": self.source_task_id,
            "source_task_type": self.source_task_type,
            "last_accessed_at": self.last_accessed_at.isoformat() if self.last_accessed_at else None,
            "biz_module": self.biz_module,
            # workspace_category 不持久化，由 API 响应层计算
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
    allowed_tools: List[str] = field(default_factory=list)
    denied_tools: List[str] = field(default_factory=list)
    allowed_commands: List[str] = field(default_factory=list)
    denied_commands: List[str] = field(default_factory=list)
    max_concurrent_file_reads: int = 5
    max_workspace_files: int = 200
    max_read_file_line: int = -1
    max_image_file_size: int = 5
    max_total_image_size: int = 20
    terminal_output_line_limit: int = 500
    terminal_output_character_limit: int = 50000
    # 代理配置
    http_proxy: str = ""
    https_proxy: str = ""
    no_proxy: str = ""

    # 安全配置（工作区级）
    security: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        from dataclasses import asdict

        return asdict(self)

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> "WorkspaceSettings":
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
            allowed_tools=config_dict.get("allowedTools", []),
            denied_tools=config_dict.get("deniedTools", []),
            max_concurrent_file_reads=config_dict.get("maxConcurrentFileReads", 5),
            max_workspace_files=config_dict.get("maxWorkspaceFiles", 200),
            max_read_file_line=config_dict.get("maxReadFileLine", -1),
            max_image_file_size=config_dict.get("maxImageFileSize", 5),
            max_total_image_size=config_dict.get("maxTotalImageSize", 20),
            terminal_output_line_limit=config_dict.get("terminalOutputLineLimit", 500),
            terminal_output_character_limit=config_dict.get("terminalOutputCharacterLimit", 50000),
            http_proxy=config_dict.get("httpProxy", ""),
            https_proxy=config_dict.get("httpsProxy", ""),
            no_proxy=config_dict.get("noProxy", ""),
            security=config_dict.get("security", {}),
        )


# ============================================================================
# Workspace Metadata Model (Pydantic)
# ============================================================================


class WorkspaceMetadata(BaseModel):
    """工作区元信息 — 各类型共享的标准化可选字段

    不持久化为独立文件，存在于 workspace.json 的 metadata / ip_metadata 字段中。
    """

    # ── IP 专有 ──
    phase: str | None = Field(default=None, description="idle/plan/do/check/act/completed/error")
    score: float | None = None
    task_type: str | None = None
    parent_workspace_id: str | None = None
    inherited_files: list[str] | None = None
    alerts: list[dict[str, Any]] | None = None

    # ── 合规专有 ──
    compliance_template: str | None = None
    compliance_form_data: dict[str, Any] | None = None

    # ── 通用扩展点 ──
    extra: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_ip_meta(cls, ip_meta: dict[str, Any] | None) -> "WorkspaceMetadata":
        """从 ip_metadata 字典构建标准化元信息"""
        if not ip_meta:
            return cls()
        return cls(
            phase=ip_meta.get("phase"),
            score=ip_meta.get("score"),
            task_type=ip_meta.get("task_type"),
            parent_workspace_id=ip_meta.get("parent_workspace_id"),
            inherited_files=ip_meta.get("inherited_files"),
            alerts=ip_meta.get("alerts"),
            extra=ip_meta.get("extra", ip_meta.get("metadata", {})),
        )

    @classmethod
    def from_compliance_meta(cls, meta: dict[str, Any] | None) -> "WorkspaceMetadata":
        """从合规模板元数据构建标准化元信息"""
        if not meta:
            return cls()
        return cls(
            compliance_template=meta.get("compliance_template"),
            compliance_form_data=meta.get("compliance_form_data"),
            extra=meta.get("extra", {}),
        )


# ============================================================================
# Workspace Configuration Models (Pydantic)
# ============================================================================


class AgentConfig(BaseModel):
    """Agent 执行配置"""

    mode: str = "orchestrator"
    plan_mode_confirm_required: bool = True
    enable_auto_mode_switch: bool = False
    auto_approve_tools: bool = True
    max_concurrent_subtasks: int = 3

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        """验证模式是否有效"""
        from dawei.mode import get_valid_modes

        valid_modes = get_valid_modes()
        if v not in valid_modes:
            raise ValueError(f"Invalid mode '{v}'. Must be one of: {valid_modes}")
        return v


class MemoryConfig(BaseModel):
    """内存系统配置"""

    enabled: bool = True
    # Independent read/write switches (Codex-inspired: debug, import-only, etc.)
    read_enabled: bool = True  # False = skip memory injection into context
    write_enabled: bool = True  # False = skip extraction/consolidation/gardener
    virtual_page_size: int = 2000
    max_active_pages: int = 5
    default_energy: float = 1.0
    # 对齐 MemoryGardener 运行时默认（0.95），桥接后不改变既有衰减行为
    energy_decay_rate: float = 0.95
    min_energy_threshold: float = 0.2
    consolidation_enabled: bool = False  # LLM consolidation 默认关（仅 decay+archive，零 LLM 成本）


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
    # 对齐 AsyncTaskManagerConfig 运行时默认（10），桥接时不改变既有并发行为
    max_concurrent_executions: int = 10


class LoggingConfig(BaseModel):
    """日志配置"""

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    dir: str = "~/.normnomos/logs"
    max_file_size: int = 10
    backup_count: int = 5
    console_output: bool = True
    file_output: bool = True
    enable_performance_logging: bool = True
    sanitize_sensitive_data: bool = True


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
    settings: Dict[str, Any] = Field(default_factory=dict)
    version: str | None = None
    install_path: str | None = None


class PluginsConfig(BaseModel):
    """插件配置（第二层：动态配置）

    插件配置特点：
    - 动态结构：插件ID和配置项都是运行时确定的
    - 独立存储：保存在 .dawei/plugins/{plugin_id}.json
    - 灵活扩展：每个插件可以有自己独特的配置字段
    """

    plugins: Dict[str, PluginInstanceConfig] = Field(default_factory=dict)

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
    knowledge: KnowledgeConfig = Field(default_factory=KnowledgeConfig)
    skills: SkillsConfig = Field(default_factory=SkillsConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    analytics: AnalyticsConfig = Field(default_factory=AnalyticsConfig)
    # ✨ 新增：插件配置（第二层：动态配置）
    plugins: PluginsConfig = Field(default_factory=PluginsConfig)

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any] | None) -> "WorkspaceConfig":
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

    def model_dump_custom(self) -> Dict[str, Any]:
        """转换为字典（自定义序列化）

        Returns:
            配置字典格式与 config.json 兼容
        """
        return {
            "agent": self.agent.model_dump(),
            "checkpoint": self.checkpoint.model_dump(),
            "compression": self.compression.model_dump(),
            "memory": self.memory.model_dump(),
            "knowledge": self.knowledge.model_dump(),
            "skills": self.skills.model_dump(),
            "tools": self.tools.model_dump(),
            "logging": self.logging.model_dump(),
            "analytics": self.analytics.model_dump(),
            "plugins": self.plugins.model_dump(),  # ✨ 新增：插件配置
        }
