# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""统一日志配置管理模块

提供日志记录的配置选项和默认设置，所有日志统一保存在 DAWEI_HOME/logs 目录下。
"""

import os
from datetime import UTC, datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ConfigDict, Field, field_validator
from pydantic_settings import BaseSettings


def get_dawei_home() -> Path:
    """获取 DAWEI_HOME 路径

    Returns:
        Path: DAWEI_HOME 目录的绝对路径（默认 ~/.dawei）

    """
    dawei_home = os.environ.get("DAWEI_HOME", "~/.dawei")
    return Path(dawei_home).expanduser().resolve()


def get_log_dir() -> Path:
    """获取日志目录路径

    Returns:
        Path: 日志目录的绝对路径（DAWEI_HOME/logs）

    """
    return get_dawei_home() / "logs"


class LoggingConfig(BaseSettings):
    """统一日志配置类

    所有日志文件统一保存在 DAWEI_HOME/logs 目录下
    """

    model_config = ConfigDict(
        env_prefix="LOG_",
        env_file=[".env", "services/agent-api/.env"],
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
    )

    # 基础配置
    level: str = Field(default="WARNING", alias="log_level")
    format: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        alias="log_format",
    )
    date_format: str = Field(default="%Y-%m-%d %H:%M:%S")

    # 文件配置 - 使用 DAWEI_HOME/logs
    dir: str = Field(default_factory=lambda: str(get_log_dir()), alias="log_dir")
    max_file_size: int = Field(default=10 * 1024 * 1024, alias="max_file_size")  # 10MB
    backup_count: int = Field(default=5)
    file_encoding: str = Field(default="utf-8")

    # LLM日志特定配置 - 使用 DAWEI_HOME/logs/llm
    llm_dir: str = Field(default_factory=lambda: str(get_log_dir() / "llm"), alias="llm_log_dir")
    llm_file_extension: str = Field(default=".json")
    max_llm_files: int = Field(default=100)
    cleanup_interval_hours: int = Field(default=24)

    # 控制台输出配置
    console_output: bool = Field(default=True)
    console_level: str = Field(default="DEBUG")

    # 文件输出配置
    file_output: bool = Field(default=True)
    file_level: str = Field(default="DEBUG")

    # 结构化日志配置
    structured_logging: bool = Field(default=True)
    include_traceback: bool = Field(default=True)

    # 性能监控配置
    enable_performance_logging: bool = Field(default=True)
    slow_query_threshold_ms: float = Field(default=1000.0)

    # 安全配置
    sanitize_sensitive_data: bool = Field(default=True)
    sensitive_fields: list[str] = Field(default_factory=lambda: ["api_key", "password", "secret", "credential"])

    def __init__(self, **data):
        """初始化日志配置

        自动设置日志目录为 DAWEI_HOME/logs
        """
        # 调用父类初始化（default_factory 会自动设置路径）
        super().__init__(**data)

        # 确保路径是绝对路径
        if not Path(self.dir).is_absolute():
            self.dir = str(Path(self.dir).absolute())
        if not Path(self.llm_dir).is_absolute():
            self.llm_dir = str(Path(self.llm_dir).absolute())

        # 确保日志目录存在
        Path(self.dir).mkdir(parents=True, exist_ok=True)
        Path(self.llm_dir).mkdir(parents=True, exist_ok=True)

        # 打印路径信息用于调试
        dawei_home = get_dawei_home()
        print(f"[LoggingConfig] DAWEI_HOME: {dawei_home}")
        print(f"[LoggingConfig] Log directory: {self.dir}")
        print(f"[LoggingConfig] LLM log directory: {self.llm_dir}")

    @field_validator("sensitive_fields", mode="before")
    @classmethod
    def parse_sensitive_fields(cls, v, info):
        """解析敏感字段列表"""
        if isinstance(v, str):
            if v.strip() == "":
                return []
            return [field.strip() for field in v.split(",")]
        return v

    @field_validator(
        "console_output",
        "file_output",
        "structured_logging",
        "enable_performance_logging",
        "sanitize_sensitive_data",
        mode="before",
    )
    @classmethod
    def parse_bool_fields(cls, v):
        """解析布尔值字段"""
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes", "on")
        return v

    @field_validator(
        "max_file_size",
        "backup_count",
        "max_llm_files",
        "cleanup_interval_hours",
        "slow_query_threshold_ms",
        mode="before",
    )
    @classmethod
    def parse_numeric_fields(cls, v):
        """解析数值字段"""
        if isinstance(v, str):
            try:
                return float(v) if "." in v else int(v)
            except ValueError:
                return v
        return v

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        result = {}
        for field_name in self.model_fields:
            value = getattr(self, field_name)
            result[field_name] = value
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LoggingConfig":
        """从字典创建配置"""
        return cls(**data)

    # 为了向后兼容，保留旧的属性名
    @property
    def log_level(self) -> str:
        return self.level

    @property
    def log_format(self) -> str:
        return self.format

    @property
    def log_dir(self) -> str:
        return self.dir

    @property
    def llm_log_dir(self) -> str:
        return self.llm_dir


# 默认配置实例
default_config = LoggingConfig()


def get_config(config: LoggingConfig | None = None) -> LoggingConfig:
    """获取日志配置"""
    if config is None:
        return LoggingConfig()
    return config


def create_llm_filename(model_name: str, timestamp: str | None = None) -> str:
    """创建LLM日志文件名"""
    if timestamp is None:
        from datetime import datetime

        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")

    # 清理模型名称，移除不安全字符
    safe_model_name = "".join(c for c in model_name if c.isalnum() or c in ("-", "_"))

    return f"{safe_model_name}_{timestamp}.json"


def get_llm_log_path(model_name: str, config: LoggingConfig | None = None) -> str:
    """获取LLM日志文件路径"""
    cfg = get_config(config)
    filename = create_llm_filename(model_name)
    return str(Path(cfg.llm_dir) / filename)


def get_tool_log_path() -> str:
    """获取工具调用日志文件路径"""
    log_dir = get_log_dir()
    return str(log_dir / "tool_calls.log")


def get_tui_log_path(workspace_path: Path | None = None) -> str:
    """获取TUI日志文件路径

    Args:
        workspace_path: 工作区路径，如果提供则使用工作区日志，否则使用 DAWEI_HOME

    Returns:
        str: TUI日志文件路径

    """
    if workspace_path:
        # 使用工作区级别的日志
        log_dir = Path(workspace_path) / ".dawei" / "logs"
    else:
        # 使用 DAWEI_HOME 级别的日志
        log_dir = get_log_dir() / "tui"

    log_dir.mkdir(parents=True, exist_ok=True)
    return str(log_dir / "tui.log")


def get_tui_error_log_path(workspace_path: Path | None = None) -> str:
    """获取TUI错误日志文件路径

    Args:
        workspace_path: 工作区路径，如果提供则使用工作区日志，否则使用 DAWEI_HOME

    Returns:
        str: TUI错误日志文件路径

    """
    if workspace_path:
        # 使用工作区级别的日志
        log_dir = Path(workspace_path) / ".dawei" / "logs"
    else:
        # 使用 DAWEI_HOME 级别的日志
        log_dir = get_log_dir() / "tui"

    log_dir.mkdir(parents=True, exist_ok=True)
    return str(log_dir / "tui_errors.log")
