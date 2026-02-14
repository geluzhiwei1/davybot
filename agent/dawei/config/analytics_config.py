# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Analytics Configuration Template
配置模板 - 用于启用和配置用户支持系统
"""

import os

# Analytics 配置
ANALYTICS_CONFIG = {
    # 是否启用 Analytics（后端总开关）
    "enabled": True,
    # 数据存储路径
    "storage_path": "analytics_data",
    # 数据保留天数
    "retention_days": 90,
    # 批量处理配置
    "batch_size": 100,  # 批量写入大小
    "flush_interval": 300,  # 刷新间隔（秒）
    # 匿名化配置
    "anonymize": {
        "enabled": True,
        "hash_user_ids": True,  # 对用户 ID 进行 hash
        "sanitize_errors": True,  # 清理错误消息中的敏感信息
    },
    # 采样率（0-1）
    "sampling_rate": 1.0,  # 1.0 = 收集所有数据
    # 允许的事件类型
    "allowed_events": [
        "session_start",
        "session_end",
        "feature_use",
        "error",
        "performance",
    ],
    # 每日数据量限制（防止滥用）
    "daily_limit": {
        "events_per_session": 1000,
        "max_payload_size_mb": 10,
    },
}

# 反馈系统配置
FEEDBACK_CONFIG = {
    # 是否启用反馈系统
    "enabled": True,
    # 存储路径
    "storage_path": "feedbacks",
    # 自动附件配置
    "auto_attach": {
        "system_info": True,
        "app_logs": True,
        "log_lines": 100,  # 附加最近 N 行日志
        "error_history": True,
        "error_count": 20,  # 附加最近 N 个错误
    },
    # 文件上传限制
    "upload_limits": {
        "max_screenshots": 5,
        "max_file_size_mb": 5,
        "allowed_formats": ["png", "jpg", "jpeg", "gif"],
    },
    # 邮件通知（可选）
    "email_notifications": {
        "enabled": False,
        "smtp_server": "smtp.example.com",
        "smtp_port": 587,
        "smtp_username": "notifications@example.com",
        "recipients": ["admin@example.com"],
    },
}

# 配置同步配置
SYNC_CONFIG = {
    # 是否启用配置同步
    "enabled": True,
    # 同步存储（数据库或文件系统）
    "storage": "database",  # 或 "filesystem"
    # 同步间隔（秒）
    "sync_interval": 300,  # 5 分钟
    # 冲突解决策略
    "conflict_resolution": "latest_timestamp",  # 或 "manual", "local_wins", "remote_wins"
    # 支持同步的配置项
    "syncable_items": [
        "preferences.theme",
        "preferences.language",
        "preferences.fontSize",
        "agentSettings.defaultMode",
        "agentSettings.defaultModel",
        "agentSettings.temperature",
    ],
    # 版本控制
    "versioning": {
        "enabled": True,
        "max_versions": 10,  # 保留最近 N 个版本
    },
}

# 环境信息收集配置
ENVIRONMENT_CONFIG = {
    # 是否启用环境信息收集
    "enabled": True,
    # 收集的硬件信息
    "hardware_info": {
        "cpu": True,
        "memory": True,
        "gpu": False,  # GPU 信息较敏感
        "network": False,  # 网络信息较敏感
    },
    # 收集的软件信息
    "software_info": {
        "os_version": True,
        "app_version": True,
        "dependencies": True,
        "environment_variables": False,  # 环境变量可能包含敏感信息
    },
    # 日志配置
    "logging": {
        "enabled": True,
        "log_path": "logs",
        "log_level": "INFO",
        "max_file_size_mb": 10,
        "max_files": 5,
        "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    },
}

# 隐私和合规配置
PRIVACY_CONFIG = {
    # GDPR 合规
    "gdpr": {
        "enabled": True,
        "require_consent": True,  # 需要明确同意
        "allow_data_export": True,  # 允许用户导出数据
        "allow_data_deletion": True,  # 允许用户删除数据
        "consent_expiry_days": 365,  # 同意有效期（天后需重新确认）
    },
    # 数据加密
    "encryption": {
        "enabled": False,  # 可选启用加密存储
        "algorithm": "AES-256",
        "key_path": ".encryption_key",
    },
    # 数据脱敏规则
    "sanitization": {
        "email_pattern": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
        "ip_pattern": r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}",
        "path_pattern": r"/[^\s]+",  # 文件路径
        "token_pattern": r"sk-[a-zA-Z0-9]{32,}",  # API keys (正则模式，用于脱敏)
        "replacement": "[REDACTED]",
    },
    # Cookie 策略（Web 模式）
    "cookies": {
        "necessary": True,
        "analytics": False,  # 需要同意
        "preferences": True,
    },
}

# 速率限制配置
RATE_LIMIT_CONFIG = {
    # Analytics 速率限制
    "analytics": {
        "enabled": True,
        "max_events_per_minute": 100,
        "max_events_per_hour": 1000,
    },
    # 反馈提交速率限制
    "feedback": {
        "enabled": True,
        "max_submissions_per_hour": 5,
        "max_submissions_per_day": 20,
    },
    # 同步速率限制
    "sync": {
        "enabled": True,
        "max_syncs_per_hour": 12,
    },
}

# 集成配置
INTEGRATION_CONFIG = {
    # 外部服务集成
    "services": {
        # Sentry 集成（错误追踪）
        "sentry": {
            "enabled": False,
        "dsn": os.getenv("SENTRY_DSN", ""),  # 从环境变量加载
            "environment": "production",
            "traces_sample_rate": 0.1,
        },
        # Google Analytics 集成（可选）
        "google_analytics": {
            "enabled": False,
            "tracking_id": os.getenv("GA_TRACKING_ID", ""),  # 从环境变量加载
        },
        # Mixpanel 集成（可选）
        "mixpanel": {
            "enabled": False,
            "token": os.getenv("MIXPANEL_TOKEN", ""),  # 从环境变量加载
        },
    },
    # Webhook 通知
    "webhooks": {
        "enabled": False,
        "urls": [],  # Webhook URLs
        "events": ["feedback_submitted", "error_reported"],
    },
}

# 开发和调试配置
DEBUG_CONFIG = {
    # 调试模式
    "debug_mode": False,
    # 详细日志
    "verbose_logging": False,
    # 本地开发配置
    "development": {
        "use_mock_storage": False,  # 使用内存存储（测试用）
        "disable_rate_limiting": True,  # 禁用速率限制
        "log_all_events": True,  # 记录所有事件到控制台
    },
}

# 完整配置对象
CONFIG = {
    "analytics": ANALYTICS_CONFIG,
    "feedback": FEEDBACK_CONFIG,
    "sync": SYNC_CONFIG,
    "environment": ENVIRONMENT_CONFIG,
    "privacy": PRIVACY_CONFIG,
    "rate_limit": RATE_LIMIT_CONFIG,
    "integration": INTEGRATION_CONFIG,
    "debug": DEBUG_CONFIG,
}


# 配置验证函数
def validate_config(config: dict | None = None) -> bool:
    """验证配置是否有效"""
    if config is None:
        config = CONFIG

    # 验证 Analytics 配置
    if config["analytics"]["enabled"]:
        assert 0 < config["analytics"]["sampling_rate"] <= 1, "Invalid sampling_rate"
        assert config["analytics"]["retention_days"] > 0, "Invalid retention_days"

    # 验证反馈配置
    if config["feedback"]["enabled"]:
        assert config["feedback"]["auto_attach"]["log_lines"] > 0, "Invalid log_lines"

    # 验证同步配置
    if config["sync"]["enabled"]:
        assert config["sync"]["sync_interval"] > 0, "Invalid sync_interval"

    return True


# 获取配置的辅助函数
def get_analytics_config() -> dict:
    """获取 Analytics 配置"""
    return CONFIG["analytics"]


def get_feedback_config() -> dict:
    """获取反馈系统配置"""
    return CONFIG["feedback"]


def get_sync_config() -> dict:
    """获取同步配置"""
    return CONFIG["sync"]


def get_environment_config() -> dict:
    """获取环境信息配置"""
    return CONFIG["environment"]


def get_privacy_config() -> dict:
    """获取隐私配置"""
    return CONFIG["privacy"]


# 示例：覆盖配置（从环境变量）


def load_config_from_env():
    """从环境变量加载配置"""
    # Analytics
    if os.getenv("ANALYTICS_ENABLED"):
        CONFIG["analytics"]["enabled"] = os.getenv("ANALYTICS_ENABLED").lower() == "true"

    # Feedback
    if os.getenv("FEEDBACK_ENABLED"):
        CONFIG["feedback"]["enabled"] = os.getenv("FEEDBACK_ENABLED").lower() == "true"

    # Sync
    if os.getenv("SYNC_ENABLED"):
        CONFIG["sync"]["enabled"] = os.getenv("SYNC_ENABLED").lower() == "true"

    # Sentry
    if os.getenv("SENTRY_DSN"):
        CONFIG["integration"]["services"]["sentry"]["dsn"] = os.getenv("SENTRY_DSN")
        CONFIG["integration"]["services"]["sentry"]["enabled"] = True

    return CONFIG


# 启动时加载环境配置
load_config_from_env()

# 验证配置
try:
    validate_config()
except AssertionError as e:
    print(f"Configuration error: {e}")
    raise
