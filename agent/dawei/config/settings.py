# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""应用配置管理模块
使用pydantic和python-dotenv实现配置加载和验证
"""

import os
from pathlib import Path
from typing import Any

from pydantic import ConfigDict, Field, field_validator
from pydantic_settings import BaseSettings


def get_workspaces_root() -> str:
    """从环境变量获取DAWEI_HOME，默认值为 ~/.dawei
    此函数需要在load_dotenv()之后调用

    Returns:
        str: 工作区根目录的绝对路径

    """
    # 从环境变量获取，如果不存在则使用默认值 ~/.dawei
    workspaces_root = os.environ.get("DAWEI_HOME", "~/.dawei")
    # 展开波浪号并转换为绝对路径
    return str(Path(workspaces_root).expanduser().resolve())


class DatabaseConfig(BaseSettings):
    """数据库配置 - 使用 SQLite"""

    model_config = ConfigDict(
        env_prefix="DB_",
        env_file=[".env", "services/agent-api/.env"],
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
    )

    # SQLite 配置
    url: str = Field(default="sqlite:///./data/dawei.db")
    path: str = Field(default="./data/dawei.db")

    # 连接池配置（SQLite 不需要，但保留接口兼容性）
    echo: bool = Field(default=False)
    pool_size: int = Field(default=1)  # SQLite 单连接
    max_overflow: int = Field(default=0)


class RedisConfig(BaseSettings):
    """Redis配置"""

    model_config = ConfigDict(
        env_prefix="REDIS_",
        env_file=[".env", "services/agent-api/.env"],
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
    )

    url: str = Field(default="redis://localhost:6379/0")
    host: str = Field(default="localhost")
    port: int = Field(default=6379)
    password: str | None = Field(default=None)
    db: int = Field(default=0)
    max_connections: int = Field(default=10)


class SecurityConfig(BaseSettings):
    """安全配置"""

    model_config = ConfigDict(
        env_file=[".env", "services/agent-api/.env"],
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
    )

    jwt_secret: str = Field(default="your_jwt_secret_here_change_in_production")
    jwt_algorithm: str = Field(default="HS256")
    jwt_expire_minutes: int = Field(default=30)
    encryption_key: str = Field(default="your_32_character_encryption_key_here")


class FileStorageConfig(BaseSettings):
    """文件存储配置"""

    model_config = ConfigDict(
        env_file=[".env", "services/agent-api/.env"],
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
    )

    upload_dir: str = Field(default="./uploads")
    max_file_size: int = Field(default=10485760)  # 10MB
    allowed_file_types: list[str] = Field(default=["pdf", "doc", "docx", "txt"])

    @field_validator("allowed_file_types", mode="before")
    @classmethod
    def parse_file_types(cls, v):
        if isinstance(v, str):
            return [ext.strip() for ext in v.split(",")]
        return v


class ExternalServiceConfig(BaseSettings):
    """外部服务配置"""

    model_config = ConfigDict(
        env_file=[".env", "services/agent-api/.env"],
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
    )

    # Generic external API configuration
    external_api_key: str = Field(default="")
    external_api_url: str = Field(default="")
    timeout: int = Field(default=30)


class MonitoringConfig(BaseSettings):
    """监控配置"""

    model_config = ConfigDict(
        env_file=[".env", "services/agent-api/.env"],
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
    )

    prometheus_enabled: bool = Field(default=True)
    prometheus_port: int = Field(default=9090)
    grafana_port: int = Field(default=3000)
    log_level: str = Field(default="INFO")


class EmailConfig(BaseSettings):
    """邮件配置（可选）"""

    model_config = ConfigDict(
        env_prefix="SMTP_",
        env_file=[".env", "services/agent-api/.env"],
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
    )

    host: str = Field(default="smtp.gmail.com")
    port: int = Field(default=587)
    user: str = Field(default="")
    password: str = Field(default="")
    use_tls: bool = Field(default=True)


class RateLimitConfig(BaseSettings):
    """限流配置"""

    model_config = ConfigDict(
        env_prefix="RATE_LIMIT_",
        env_file=[".env", "services/agent-api/.env"],
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
    )

    enabled: bool = Field(default=True)
    requests: int = Field(default=100)
    window: int = Field(default=60)


class CompressionConfig(BaseSettings):
    """对话压缩配置"""

    model_config = ConfigDict(
        env_prefix="COMPRESSION_",
        env_file=[".env", "services/agent-api/.env"],
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
    )

    # 启用开关
    enabled: bool = Field(default=False)

    # 压缩策略配置
    preserve_recent: int = Field(default=20, description="保留最近的消息数量")
    max_tokens: int = Field(default=100000, description="最大token数限制")
    compression_threshold: float = Field(default=0.5, description="开始压缩的阈值（0-1）")
    aggressive_threshold: float = Field(default=0.9, description="激进压缩的阈值（0-1）")

    # 分页配置
    page_size: int = Field(default=20, description="每页消息数量")
    max_active_pages: int = Field(default=5, description="最大活动页面数")

    # 记忆集成配置
    memory_integration_enabled: bool = Field(default=True, description="是否启用记忆集成")
    auto_extract_memories: bool = Field(default=True, description="是否自动提取记忆")
    auto_store_memories: bool = Field(default=True, description="是否自动存储记忆")

    @field_validator("enabled", "compression_threshold", "aggressive_threshold", mode="before")
    @classmethod
    def parse_bool(cls, v):
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes", "on")
        return v

    @field_validator("compression_threshold", "aggressive_threshold", mode="before")
    @classmethod
    def validate_threshold(cls, v):
        if isinstance(v, str):
            v = float(v)
        if not 0 <= v <= 1:
            raise ValueError("Threshold must be between 0 and 1")
        return v

    @field_validator(
        "preserve_recent",
        "max_tokens",
        "page_size",
        "max_active_pages",
        mode="before",
    )
    @classmethod
    def parse_int(cls, v):
        if isinstance(v, str):
            return int(v)
        return v


# ============================================================================
# LLM API Configuration
# ============================================================================


class LLMProviderConfig(BaseSettings):
    """LLM提供商配置"""

    model_config = ConfigDict(
        env_prefix="LLM_",
        env_file=[".env", "services/agent-api/.env"],
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
    )

    # 默认模型
    default_model: str = Field(default="deepseek/deepseek-chat")

    # OpenAI 配置
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_base_url: str = Field(default="https://api.openai.com/v1")

    # DeepSeek 配置
    deepseek_api_key: str = Field(default="", alias="DEEPSEEK_API_KEY")
    deepseek_base_url: str = Field(default="https://api.deepseek.com/v1")

    # Ollama 配置
    ollama_base_url: str = Field(default="http://localhost:11434")
    ollama_api_key: str = Field(default="ollama")

    # 通用配置
    timeout: int = Field(default=300)
    max_retries: int = Field(default=3)
    retry_delay: float = Field(default=1.0)


class CircuitBreakerConfig(BaseSettings):
    """熔断器配置"""

    model_config = ConfigDict(
        env_prefix="CIRCUIT_BREAKER_",
        env_file=[".env", "services/agent-api/.env"],
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
    )

    failure_threshold: int = Field(default=5)
    success_threshold: int = Field(default=2)
    timeout: float = Field(default=60.0)
    window_size: int = Field(default=100)
    max_retries: int = Field(default=5)
    base_delay: float = Field(default=1.0)
    max_delay: float = Field(default=60.0)
    jitter: bool = Field(default=True)
    jitter_factor: float = Field(default=0.25)


class RateLimiterConfig(BaseSettings):
    """限流器配置"""

    model_config = ConfigDict(
        env_prefix="RATE_LIMITER_",
        env_file=[".env", "services/agent-api/.env"],
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
    )

    initial_rate: float = Field(default=5.0)
    min_rate: float = Field(default=0.5)
    max_rate: float = Field(default=50.0)
    burst_capacity: int = Field(default=20)
    scale_up_factor: float = Field(default=1.2)
    scale_down_factor: float = Field(default=0.7)
    scale_up_threshold: int = Field(default=10)
    scale_down_threshold: int = Field(default=3)
    strategy: str = Field(default="sliding_window")


class RequestQueueConfig(BaseSettings):
    """请求队列配置"""

    model_config = ConfigDict(
        env_prefix="REQUEST_QUEUE_",
        env_file=[".env", "services/agent-api/.env"],
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
    )

    max_concurrent: int = Field(default=5)
    max_queue_size: int = Field(default=1000)
    default_timeout: float = Field(default=300.0)


# ============================================================================
# Agent Configuration
# ============================================================================


class AgentRetryConfig(BaseSettings):
    """Agent重试配置"""

    model_config = ConfigDict(
        env_prefix="AGENT_RETRY_",
        env_file=[".env", "services/agent-api/.env"],
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
    )

    max_retries: int = Field(default=3)
    retry_delay: float = Field(default=1.0)
    retry_backoff_factor: float = Field(default=2.0)
    max_delay: float = Field(default=60.0)
    jitter: bool = Field(default=True)
    retryable_errors: list[str] = Field(
        default=["LLMTimeoutError", "LLMConnectionError", "APIError", "LLMRateLimitError"],
    )
    backoff_strategy: str = Field(default="exponential")


class AgentCheckpointConfig(BaseSettings):
    """Agent检查点配置"""

    model_config = ConfigDict(
        env_prefix="AGENT_CHECKPOINT_",
        env_file=[".env", "services/agent-api/.env"],
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
    )

    checkpoint_interval: int = Field(default=300)
    max_checkpoints: int = Field(default=10)
    enable_compression: bool = Field(default=True)
    auto_create_enabled: bool = Field(default=True)
    min_interval_minutes: int = Field(default=5)
    max_checkpoints_per_task: int = Field(default=50)
    validation_enabled: bool = Field(default=True)
    storage_type: str = Field(default="file")
    storage_path: str = Field(default="checkpoints")


class AgentTimeoutConfig(BaseSettings):
    """Agent超时配置"""

    model_config = ConfigDict(
        env_prefix="AGENT_TIMEOUT_",
        env_file=[".env", "services/agent-api/.env"],
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
    )

    tool_execution_timeout: int = Field(default=60)
    request_timeout: int = Field(default=180)


class AgentExecutionConfig(BaseSettings):
    """Agent执行配置"""

    model_config = ConfigDict(
        env_prefix="AGENT_",
        env_file=[".env", "services/agent-api/.env"],
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
    )

    mode: str = Field(default="orchestrator")
    plan_mode_confirm_required: bool = Field(default=True)
    enable_auto_mode_switch: bool = Field(default=False)
    enable_skills: bool = Field(default=True)
    enable_mcp: bool = Field(default=True)
    auto_approve_tools: bool = Field(default=True)
    max_concurrent_subtasks: int = Field(default=3)
    # 缓存配置
    mode_cache_ttl: int = Field(default=300)  # 模式配置缓存TTL（秒）


# ============================================================================
# Memory Configuration
# ============================================================================


class MemoryConfig(BaseSettings):
    """记忆系统配置"""

    model_config = ConfigDict(
        env_prefix="MEMORY_",
        env_file=[".env", "services/agent-api/.env"],
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
    )

    enabled: bool = Field(default=False)
    db_path: str = Field(default=".dawei/memory.db")
    virtual_page_size: int = Field(default=2000)
    max_active_pages: int = Field(default=5)
    default_energy: float = Field(default=1.0)
    energy_decay_rate: float = Field(default=0.1)
    min_energy_threshold: float = Field(default=0.2)


# ============================================================================
# Skills Configuration
# ============================================================================


class SkillsConfig(BaseSettings):
    """技能系统配置"""

    model_config = ConfigDict(
        env_prefix="SKILLS_",
        env_file=[".env", "services/agent-api/.env"],
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
    )

    enabled: bool = Field(default=True)
    auto_discovery: bool = Field(default=True)

    # 技能优先级目录
    project_mode_skills_dir: str = Field(default=".dawei/skills-{mode}")
    global_mode_skills_dir: str = Field(default="~/.dawei/skills-{mode}")
    project_generic_skills_dir: str = Field(default=".dawei/skills")
    global_generic_skills_dir: str = Field(default="~/.dawei/skills")

    @field_validator("enabled", "auto_discovery", mode="before")
    @classmethod
    def parse_bool(cls, v):
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes", "on")
        return v


# ============================================================================
# Tool Configuration
# ============================================================================


class ToolConfig(BaseSettings):
    """工具系统配置"""

    model_config = ConfigDict(
        env_prefix="TOOL_",
        env_file=[".env", "services/agent-api/.env"],
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
    )

    # 始终可用的工具
    always_available_tools: list[str] = Field(
        default_factory=lambda: [
            "ask_followup_question",
            "attempt_completion",
            "switch_mode",
            "run_slash_command",
            "timer",
        ],
    )

    # 工具组配置
    builtin_tools_enabled: bool = Field(default=True)
    system_tools_enabled: bool = Field(default=True)
    user_tools_enabled: bool = Field(default=True)
    workspace_tools_enabled: bool = Field(default=True)

    # 工具执行配置
    default_timeout: int = Field(default=60)
    max_concurrent_executions: int = Field(default=3)


# ============================================================================
# Analytics Configuration
# ============================================================================


class AnalyticsConfig(BaseSettings):
    """分析配置"""

    model_config = ConfigDict(
        env_prefix="ANALYTICS_",
        env_file=[".env", "services/agent-api/.env"],
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
    )

    enabled: bool = Field(default=True)
    storage_path: str = Field(default="analytics_data")
    retention_days: int = Field(default=90)
    batch_size: int = Field(default=100)
    flush_interval: int = Field(default=300)
    sampling_rate: float = Field(default=1.0)

    # 匿名化配置
    anonymize_enabled: bool = Field(default=True)
    anonymize_hash_user_ids: bool = Field(default=True)
    anonymize_sanitize_errors: bool = Field(default=True)

    # 允许的事件
    allowed_events: list[str] = Field(
        default_factory=lambda: [
            "session_start",
            "session_end",
            "feature_use",
            "error",
            "performance",
        ],
    )

    # 每日限制
    daily_limit_events_per_session: int = Field(default=1000)
    daily_limit_max_payload_size_mb: int = Field(default=10)


# ============================================================================
# Storage Configuration
# ============================================================================


class StorageConfig(BaseSettings):
    """存储配置"""

    model_config = ConfigDict(
        env_prefix="STORAGE_",
        env_file=[".env", "services/agent-api/.env"],
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
    )

    storage_type: str = Field(default="LOCAL_FILESYSTEM")
    root_dir: str = Field(default=".")
    create_if_missing: bool = Field(default=True)


# ============================================================================
# Logging Configuration
# ============================================================================


class LoggingConfig(BaseSettings):
    """日志配置"""

    model_config = ConfigDict(
        env_prefix="LOG_",
        env_file=[".env", "services/agent-api/.env"],
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
    )

    level: str = Field(default="INFO")
    enable_performance_logging: bool = Field(default=True)
    enable_telemetry: bool = Field(default=True)
    log_file: str = Field(default="logs/dawei.log")
    max_file_size_mb: int = Field(default=10)
    backup_count: int = Field(default=5)
    console_output: bool = Field(default=True)


class AppConfig(BaseSettings):
    """应用主配置"""

    model_config = ConfigDict(
        env_file=[".env", "services/agent-api/.env"],
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
    )

    # 基础配置
    name: str = Field(default="dawei-agent")
    version: str = Field(default="1.0.0")
    environment: str = Field(default="development")
    debug: bool = Field(default=True)

    # 服务器配置
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8465)
    reload: bool = Field(default=True)

    # CORS配置
    cors_origins: list[str] = Field(default=["*"])

    # 工作目录配置
    # workspaces_root 直接从环境变量获取，默认为 ~/.dawei
    workspaces_root: str = Field(default_factory=get_workspaces_root)

    def __init__(self, **data):
        """初始化配置"""
        super().__init__(**data)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v

    @field_validator("debug", mode="before")
    @classmethod
    def parse_debug(cls, v):
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes", "on")
        return v

    @field_validator("reload", mode="before")
    @classmethod
    def parse_reload(cls, v):
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes", "on")
        return v


class Settings(BaseSettings):
    """主配置类，整合所有配置模块"""

    model_config = ConfigDict(
        env_file=[".env", "services/agent-api/.env"],  # 尝试多个环境文件
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",  # 允许额外的字段
    )

    # 应用配置
    app: AppConfig = Field(default_factory=AppConfig)

    # 基础设施配置
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    file_storage: FileStorageConfig = Field(default_factory=FileStorageConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)

    # 服务配置
    external_service: ExternalServiceConfig = Field(default_factory=ExternalServiceConfig)
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)
    email: EmailConfig = Field(default_factory=EmailConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    analytics: AnalyticsConfig = Field(default_factory=AnalyticsConfig)

    # API控制配置
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig)

    # LLM配置
    llm: LLMProviderConfig = Field(default_factory=LLMProviderConfig)
    circuit_breaker: CircuitBreakerConfig = Field(default_factory=CircuitBreakerConfig)
    rate_limiter: RateLimiterConfig = Field(default_factory=RateLimiterConfig)
    request_queue: RequestQueueConfig = Field(default_factory=RequestQueueConfig)

    # Agent配置
    agent_retry: AgentRetryConfig = Field(default_factory=AgentRetryConfig)
    agent_checkpoint: AgentCheckpointConfig = Field(default_factory=AgentCheckpointConfig)
    agent_timeout: AgentTimeoutConfig = Field(default_factory=AgentTimeoutConfig)
    agent_execution: AgentExecutionConfig = Field(default_factory=AgentExecutionConfig)

    # 功能配置
    compression: CompressionConfig = Field(default_factory=CompressionConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    skills: SkillsConfig = Field(default_factory=SkillsConfig)
    tool: ToolConfig = Field(default_factory=ToolConfig)

    @classmethod
    def load_from_env(cls, env_file: str = ".env") -> "Settings":
        """从环境文件加载配置

        Args:
            env_file: 环境文件路径，默认为.env

        Returns:
            Settings: 配置实例

        """
        return cls(_env_file=env_file)

    def get_database_url(self) -> str:
        """获取数据库连接URL (SQLite)"""
        return self.database.url

    def get_redis_url(self) -> str:
        """获取完整的Redis连接URL"""
        if self.redis.url and self.redis.url != f"redis://{self.redis.host}:{self.redis.port}/{self.redis.db}":
            return self.redis.url

        auth_part = f":{self.redis.password}@" if self.redis.password else ""
        return f"redis://{auth_part}{self.redis.host}:{self.redis.port}/{self.redis.db}"

    def is_development(self) -> bool:
        """判断是否为开发环境"""
        return self.app.environment.lower() in ("development", "dev")

    def is_production(self) -> bool:
        """判断是否为生产环境"""
        return self.app.environment.lower() in ("production", "prod")

    def is_staging(self) -> bool:
        """判断是否为测试环境"""
        return self.app.environment.lower() in ("staging", "stage")

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        result = {}
        for field_name in self.__fields__:
            value = getattr(self, field_name)
            if hasattr(value, "to_dict"):
                result[field_name] = value.to_dict()
            elif hasattr(value, "__dict__"):
                result[field_name] = {k: v for k, v in value.__dict__.items() if not k.startswith("_")}
            else:
                result[field_name] = value
        return result


# 全局配置实例
_settings: Settings | None = None


def get_settings(env_file: str = ".env") -> Settings:
    """获取全局配置实例

    Args:
        env_file: 环境文件路径

    Returns:
        Settings: 配置实例

    """
    global _settings

    if _settings is None:
        _settings = Settings.load_from_env(env_file)

    return _settings


def reload_settings(env_file: str = ".env") -> Settings:
    """重新加载配置

    Args:
        env_file: 环境文件路径

    Returns:
        Settings: 新的配置实例

    """
    global _settings
    _settings = None
    return get_settings(env_file)


# 便捷函数
def get_database_url() -> str:
    """获取数据库连接URL"""
    return get_settings().get_database_url()


def get_redis_url() -> str:
    """获取Redis连接URL"""
    return get_settings().get_redis_url()


def is_development() -> bool:
    """判断是否为开发环境"""
    return get_settings().is_development()


def is_production() -> bool:
    """判断是否为生产环境"""
    return get_settings().is_production()


def is_staging() -> bool:
    """判断是否为测试环境"""
    return get_settings().is_staging()
