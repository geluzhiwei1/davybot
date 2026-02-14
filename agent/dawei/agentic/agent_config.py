# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""扁平化配置系统
简化的配置管理，移除嵌套结构
"""

import json
import os
import time
from enum import StrEnum
from typing import Any, Optional

# ============================================================================
# Agent 模式枚举
# ============================================================================


class AgentMode(StrEnum):
    """Agent 工作模式

    支持PDCA循环的完整模式系统
    """

    ORCHESTRATOR = "orchestrator"  # 智能协调者模式 - 跨领域PDCA协调
    PLAN = "plan"  # 规划阶段 - 只读模式：仅分析，不修改文件
    DO = "do"  # 执行阶段 - 执行具体任务
    CHECK = "check"  # 检查阶段 - 验证结果
    ACT = "act"  # 行动阶段 - 改进措施
    BUILD = "build"  # 完整模式：可执行所有操作


class Config:
    """简化的扁平化配置系统

    所有配置项都在同一层级，没有嵌套结构
    """

    def __init__(self, config_dict: dict[str, Any] | None = None):
        # 默认配置
        # Agent 模式配置（支持PDCA循环）
        self.mode = AgentMode.ORCHESTRATOR  # 默认 Orchestrator 模式
        self.plan_mode_confirm_required = True  # Plan 模式下执行危险操作需确认

        # 重试配置
        self.max_retries = 3
        self.retry_delay = 1.0
        self.retry_backoff_factor = 2.0
        self.max_delay = 60.0
        self.jitter = True
        self.retryable_errors = [
            "network_error",
            "api_error",
            "timeout_error",
            "rate_limit_error",
            "context_window_error",
        ]
        self.backoff_strategy = "exponential"

        # 检查点配置
        self.checkpoint_interval = 300  # 5分钟
        self.max_checkpoints = 10
        self.enable_checkpoint_compression = True
        self.auto_create_enabled = True
        self.min_interval_minutes = 5
        self.max_checkpoints_per_task = 50
        self.validation_enabled = True
        self.storage_type = "file"
        self.storage_path = "checkpoints"

        # 上下文配置
        self.max_context_tokens = 100000
        self.context_compression_strategy = "hybrid"
        self.compression_threshold = 0.8
        self.max_messages = 1000
        self.enable_ttl = True
        self.default_ttl = 3600  # 1 hour
        self.enable_auto_compression = True

        # 超时配置
        self.tool_execution_timeout = 60
        self.task_execution_timeout = 3600  # 1小时

        # 日志配置
        self.log_level = "INFO"
        self.enable_performance_logging = True
        self.enable_telemetry = True

        # 任务执行配置
        # Mode 切换应该由 LLM 通过 switch_mode 工具显式控制
        # 不应该基于关键词自动检测，因为：
        # 1. LLM 更有能力判断何时需要切换 mode
        # 2. 工具调用应该由 LLM 根据任务需要决定
        # 3. 关键词匹配不可靠，会误判任务意图
        self.enable_auto_mode_switch = False
        self.enable_skills = True
        self.enable_mcp = True
        self.auto_approve_tools = True
        self.max_concurrent_subtasks = 3

        # 配置元数据
        self._config_version = "1.0.0"
        self._last_modified = time.time()

        # 从字典更新配置
        if config_dict:
            self.update_from_dict(config_dict)

        # 应用环境变量覆盖
        self.apply_env_overrides()

    def update_from_dict(self, config_dict: dict[str, Any]):
        """从字典更新配置

        Args:
            config_dict: 配置字典

        """
        # 定义预期的配置项集合
        expected_configs = {
            "mode",
            "plan_mode_confirm_required",
            "max_retries",
            "retry_delay",
            "retry_backoff_factor",
            "max_delay",
            "jitter",
            "retryable_errors",
            "backoff_strategy",
            "checkpoint_interval",
            "max_checkpoints",
            "enable_checkpoint_compression",
            "auto_create_enabled",
            "min_interval_minutes",
            "max_checkpoints_per_task",
            "validation_enabled",
            "storage_type",
            "storage_path",
            "max_context_tokens",
            "context_compression_strategy",
            "compression_threshold",
            "max_messages",
            "enable_ttl",
            "default_ttl",
            "enable_auto_compression",
            "tool_execution_timeout",
            "task_execution_timeout",
            "log_level",
            "enable_performance_logging",
            "enable_telemetry",
            "enable_auto_mode_switch",
            "enable_skills",
            "enable_mcp",
            "auto_approve_tools",
            "max_concurrent_subtasks",
        }

        # 只更新预期的配置项
        for key, value in config_dict.items():
            if hasattr(self, key) and key in expected_configs:
                # 特殊处理枚举类型
                if key == "mode" and isinstance(value, str):
                    value = AgentMode(value.lower())
                setattr(self, key, value)

        self._last_modified = time.time()

    def apply_env_overrides(self, prefix: str = "AGENT_"):
        """应用环境变量覆盖

        Args:
            prefix: 环境变量前缀

        """
        # 定义布尔类型配置项
        boolean_configs = {
            "jitter",
            "enable_checkpoint_compression",
            "auto_create_enabled",
            "validation_enabled",
            "enable_ttl",
            "enable_auto_compression",
            "enable_performance_logging",
            "enable_telemetry",
            "enable_auto_mode_switch",
            "enable_skills",
            "enable_mcp",
            "auto_approve_tools",
            "plan_mode_confirm_required",
        }

        # 定义整数类型配置项
        integer_configs = {
            "max_retries",
            "checkpoint_interval",
            "max_checkpoints",
            "min_interval_minutes",
            "max_checkpoints_per_task",
            "max_context_tokens",
            "max_messages",
            "default_ttl",
            "tool_execution_timeout",
            "task_execution_timeout",
            "max_concurrent_subtasks",
        }

        # 定义浮点数类型配置项
        float_configs = {
            "retry_delay",
            "retry_backoff_factor",
            "max_delay",
            "compression_threshold",
        }

        # 环境变量到配置属性映射
        env_mappings = {
            f"{prefix}MODE": "mode",
            f"{prefix}PLAN_MODE_CONFIRM_REQUIRED": "plan_mode_confirm_required",
            f"{prefix}MAX_RETRIES": "max_retries",
            f"{prefix}RETRY_DELAY": "retry_delay",
            f"{prefix}RETRY_BACKOFF_FACTOR": "retry_backoff_factor",
            f"{prefix}MAX_DELAY": "max_delay",
            f"{prefix}JITTER": "jitter",
            f"{prefix}BACKOFF_STRATEGY": "backoff_strategy",
            f"{prefix}CHECKPOINT_INTERVAL": "checkpoint_interval",
            f"{prefix}MAX_CHECKPOINTS": "max_checkpoints",
            f"{prefix}ENABLE_CHECKPOINT_COMPRESSION": "enable_checkpoint_compression",
            f"{prefix}AUTO_CREATE_ENABLED": "auto_create_enabled",
            f"{prefix}MIN_INTERVAL_MINUTES": "min_interval_minutes",
            f"{prefix}MAX_CHECKPOINTS_PER_TASK": "max_checkpoints_per_task",
            f"{prefix}VALIDATION_ENABLED": "validation_enabled",
            f"{prefix}STORAGE_TYPE": "storage_type",
            f"{prefix}STORAGE_PATH": "storage_path",
            f"{prefix}MAX_CONTEXT_TOKENS": "max_context_tokens",
            f"{prefix}CONTEXT_COMPRESSION_STRATEGY": "context_compression_strategy",
            f"{prefix}COMPRESSION_THRESHOLD": "compression_threshold",
            f"{prefix}MAX_MESSAGES": "max_messages",
            f"{prefix}ENABLE_TTL": "enable_ttl",
            f"{prefix}DEFAULT_TTL": "default_ttl",
            f"{prefix}ENABLE_AUTO_COMPRESSION": "enable_auto_compression",
            f"{prefix}TOOL_EXECUTION_TIMEOUT": "tool_execution_timeout",
            f"{prefix}TASK_EXECUTION_TIMEOUT": "task_execution_timeout",
            f"{prefix}LOG_LEVEL": "log_level",
            f"{prefix}ENABLE_PERFORMANCE_LOGGING": "enable_performance_logging",
            f"{prefix}ENABLE_TELEMETRY": "enable_telemetry",
            f"{prefix}ENABLE_AUTO_MODE_SWITCH": "enable_auto_mode_switch",
            f"{prefix}ENABLE_SKILLS": "enable_skills",
            f"{prefix}ENABLE_MCP": "enable_mcp",
            f"{prefix}AUTO_APPROVE_TOOLS": "auto_approve_tools",
            f"{prefix}MAX_CONCURRENT_SUBTASKS": "max_concurrent_subtasks",
        }

        for env_var, attr_name in env_mappings.items():
            if env_var not in os.environ:
                continue

            value = os.environ[env_var]

            # 类型转换
            if attr_name == "mode":
                value = AgentMode(value.lower())
            elif attr_name in boolean_configs:
                value = value.lower() in {"true", "1", "yes", "on"}
            elif attr_name in integer_configs:
                value = int(value)
            elif attr_name in float_configs:
                value = float(value)
            elif attr_name == "retryable_errors":
                value = value.split(",")
            else:
                # 保持字符串类型，不做转换
                pass

            setattr(self, attr_name, value)

        self._last_modified = time.time()

    def to_dict(self) -> dict[str, Any]:
        """转换为字典

        Returns:
            配置字典

        """
        result = {}
        for attr in dir(self):
            if not attr.startswith("_"):
                value = getattr(self, attr)
                if not callable(value):
                    result[attr] = value

        return result

    def save_to_file(self, file_path: str) -> bool:
        """保存配置到文件

        Args:
            file_path: 文件路径

        Returns:
            是否成功保存

        """
        try:
            # 确保目录存在
            from pathlib import Path

            parent_dir = Path(file_path).parent
            if parent_dir != Path():
                parent_dir.mkdir(parents=True, exist_ok=True)

            with file_path.open("w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

            return True
        except Exception as e:
            print(f"Failed to save config to {file_path}: {e}")
            return False

    @classmethod
    def load_from_file(cls, file_path: str) -> Optional["Config"]:
        """从文件加载配置

        Args:
            file_path: 文件路径

        Returns:
            配置实例或None

        """
        try:
            from pathlib import Path

            if not Path(file_path).exists():
                return None

            with Path(file_path).open(encoding="utf-8") as f:
                config_dict = json.load(f)

            return cls(config_dict)
        except Exception as e:
            print(f"Failed to load config from {file_path}: {e}")
            return None

    def validate(self) -> dict[str, list[str]]:
        """验证配置有效性

        Returns:
            错误字典，键为配置类别，值为错误消息列表

        """
        errors = {}

        # 验证各个配置组
        errors.update(self._validate_retry_config())
        errors.update(self._validate_checkpoint_config())
        errors.update(self._validate_context_config())
        errors.update(self._validate_timeout_config())
        errors.update(self._validate_logging_config())
        errors.update(self._validate_task_execution_config())

        return errors

    def _validate_retry_config(self) -> dict[str, list[str]]:
        """验证重试配置"""
        errors = []
        if self.max_retries < 0:
            errors.append("max_retries must be >= 0")
        if self.retry_delay < 0:
            errors.append("retry_delay must be >= 0")
        if self.retry_backoff_factor <= 1:
            errors.append("retry_backoff_factor must be > 1")
        if self.max_delay < self.retry_delay:
            errors.append("max_delay must be >= retry_delay")
        return {"retry": errors} if errors else {}

    def _validate_checkpoint_config(self) -> dict[str, list[str]]:
        """验证检查点配置"""
        errors = []
        if self.checkpoint_interval < 10:
            errors.append("checkpoint_interval must be >= 10 seconds")
        if self.max_checkpoints < 1:
            errors.append("max_checkpoints must be >= 1")
        if self.min_interval_minutes < 1:
            errors.append("min_interval_minutes must be >= 1")
        if self.max_checkpoints_per_task < 1:
            errors.append("max_checkpoints_per_task must be >= 1")
        return {"checkpoint": errors} if errors else {}

    def _validate_context_config(self) -> dict[str, list[str]]:
        """验证上下文配置"""
        errors = []
        if self.max_context_tokens < 1000:
            errors.append("max_context_tokens must be >= 1000")

        valid_strategies = {"hybrid", "recent", "summary", "importance"}
        if self.context_compression_strategy not in valid_strategies:
            errors.append(f"context_compression_strategy must be one of {valid_strategies}")

        if not 0 < self.compression_threshold <= 1:
            errors.append("compression_threshold must be between 0 and 1")
        if self.max_messages < 10:
            errors.append("max_messages must be >= 10")
        if self.default_ttl < 0:
            errors.append("default_ttl must be >= 0")

        return {"context": errors} if errors else {}

    def _validate_timeout_config(self) -> dict[str, list[str]]:
        """验证超时配置"""
        errors = []
        if self.tool_execution_timeout < 1:
            errors.append("tool_execution_timeout must be >= 1 second")
        if self.task_execution_timeout < 1:
            errors.append("task_execution_timeout must be >= 1 second")
        return {"timeout": errors} if errors else {}

    def _validate_logging_config(self) -> dict[str, list[str]]:
        """验证日志配置"""
        errors = []
        valid_log_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if self.log_level not in valid_log_levels:
            errors.append(f"log_level must be one of {valid_log_levels}")
        return {"logging": errors} if errors else {}

    def _validate_task_execution_config(self) -> dict[str, list[str]]:
        """验证任务执行配置"""
        errors = []
        if self.max_concurrent_subtasks < 1:
            errors.append("max_concurrent_subtasks must be >= 1")
        return {"task_execution": errors} if errors else {}

    def merge_with(self, other: "Config") -> "Config":
        """与另一个配置合并，other的值会覆盖当前值

        Args:
            other: 另一个配置实例

        Returns:
            合并后的配置实例

        """
        import copy

        # 深拷贝当前配置
        merged = copy.deepcopy(self)

        # 定义预期的配置项集合（与update_from_dict保持一致）
        expected_configs = {
            "mode",
            "plan_mode_confirm_required",
            "max_retries",
            "retry_delay",
            "retry_backoff_factor",
            "max_delay",
            "jitter",
            "retryable_errors",
            "backoff_strategy",
            "checkpoint_interval",
            "max_checkpoints",
            "enable_checkpoint_compression",
            "auto_create_enabled",
            "min_interval_minutes",
            "max_checkpoints_per_task",
            "validation_enabled",
            "storage_type",
            "storage_path",
            "max_context_tokens",
            "context_compression_strategy",
            "compression_threshold",
            "max_messages",
            "enable_ttl",
            "default_ttl",
            "enable_auto_compression",
            "tool_execution_timeout",
            "task_execution_timeout",
            "log_level",
            "enable_performance_logging",
            "enable_telemetry",
            "enable_auto_mode_switch",
            "enable_skills",
            "enable_mcp",
            "auto_approve_tools",
            "max_concurrent_subtasks",
            "_config_version",
            "_last_modified",
        }

        # 更新属性，只更新预期的配置项
        for attr in dir(other):
            if not attr.startswith("_") and not callable(getattr(other, attr)) and attr in expected_configs and hasattr(merged, attr):
                # 特殊处理枚举类型
                value = AgentMode(getattr(other, attr).lower()) if attr == "mode" and isinstance(getattr(other, attr), str) else getattr(other, attr)
                setattr(merged, attr, value)

        # 更新元数据
        merged._last_modified = time.time()

        return merged


# ============================================================================
# 配置工厂函数
# ============================================================================


def create_default_config() -> Config:
    """创建默认配置

    Returns:
        默认配置实例

    """
    return Config()


def create_config_from_dict(config_dict: dict[str, Any]) -> Config:
    """从字典创建配置

    Args:
        config_dict: 配置字典

    Returns:
        配置实例

    """
    return Config(config_dict)


def create_config_from_file(file_path: str) -> Config | None:
    """从文件创建配置

    Args:
        file_path: 文件路径

    Returns:
        配置实例或None

    """
    return Config.load_from_file(file_path)


def create_config_with_env_overrides(
    base_config: Config | None = None,
    prefix: str = "AGENT_",
) -> Config:
    """创建带有环境变量覆盖的配置

    Args:
        base_config: 基础配置（可选）
        prefix: 环境变量前缀

    Returns:
        配置实例

    """
    config = base_config or create_default_config()
    config.apply_env_overrides(prefix)
    return config


def merge_configs(*configs: Config) -> Config:
    """合并多个配置，后面的配置会覆盖前面的配置

    Args:
        configs: 配置实例列表

    Returns:
        合并后的配置实例

    """
    if not configs:
        return create_default_config()

    result = configs[0]
    for config in configs[1:]:
        result = result.merge_with(config)

    return result
