# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

from dataclasses import dataclass, field
from typing import Any

# 敏感环境变量键名模式
SENSITIVE_ENV_PATTERNS = [
    'key', 'secret', 'token', 'password', 'pwd',
    'api', 'auth', 'credential', 'private',
]


@dataclass
class SystemEnvironments:
    """系统后端环境信息，如操作系统、Python版本、内存等

    隐私保护:
    - environment_variables 默认为空字典
    - 需要明确启用才会收集环境变量
    - 敏感变量会被自动过滤
    """

    os_name: str = ""
    os_version: str = ""
    python_version: str = ""
    cpu_count: int = 0
    memory_total: int = 0  # MB
    memory_available: int = 0  # MB
    disk_total: int = 0  # MB
    disk_available: int = 0  # MB
    environment_variables: dict[str, str] = field(default_factory=dict)

    def to_dict(self, include_env_vars: bool = False) -> dict[str, Any]:
        """转换为字典

        Args:
            include_env_vars: 是否包含环境变量 (默认 False 以保护隐私)

        Returns:
            字典格式的系统信息
        """
        result = {
            "os_name": self.os_name,
            "os_version": self.os_version,
            "python_version": self.python_version,
            "cpu_count": self.cpu_count,
            "memory_total": self.memory_total,
            "memory_available": self.memory_available,
            "disk_total": self.disk_total,
            "disk_available": self.disk_available,
        }

        # 仅在明确请求时包含环境变量
        if include_env_vars:
            result["environment_variables"] = self._sanitize_env_vars(self.environment_variables)

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SystemEnvironments":
        """从字典创建系统环境信息"""
        return cls(
            os_name=data.get("os_name", ""),
            os_version=data.get("os_version", ""),
            python_version=data.get("python_version", ""),
            cpu_count=data.get("cpu_count", 0),
            memory_total=data.get("memory_total", 0),
            memory_available=data.get("memory_available", 0),
            disk_total=data.get("disk_total", 0),
            disk_available=data.get("disk_available", 0),
            environment_variables=data.get("environment_variables", {}),
        )

    def _sanitize_env_vars(self, env_vars: dict[str, str]) -> dict[str, str]:
        """过滤敏感环境变量

        Args:
            env_vars: 原始环境变量字典

        Returns:
            过滤后的环境变量字典
        """
        if not env_vars:
            return {}

        sanitized = {}
        for key, value in env_vars.items():
            key_lower = key.lower()

            # 检查是否包含敏感关键词
            is_sensitive = any(
                pattern in key_lower
                for pattern in SENSITIVE_ENV_PATTERNS
            )

            if is_sensitive:
                # 敏感变量，完全跳过或使用占位符
                sanitized[key] = "[REDACTED]"
            else:
                # 非敏感变量，截断过长的值
                sanitized[key] = value[:100] if len(str(value)) > 100 else value

        return sanitized

    def get_safe_for_analytics(self) -> dict[str, Any]:
        """获取安全的分析数据 (隐私保护版本)

        这是用于分析数据收集的推荐方法。
        自动排除环境变量和其他敏感信息。

        Returns:
            安全的系统信息字典
        """
        return self.to_dict(include_env_vars=False)


@dataclass
class UserUIEnvironments:
    """用户前端静态环境信息，如浏览器、操作系统、语言、时区等

    隐私保护:
    - 这些信息通常不包含敏感数据
    - 时区信息可用于本地化功能
    - 语言偏好用于国际化
    """

    browser_name: str = ""
    browser_version: str = ""
    user_os: str = ""
    user_language: str = ""
    timezone: str = ""
    screen_resolution: str = ""

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "browser_name": self.browser_name,
            "browser_version": self.browser_version,
            "user_os": self.user_os,
            "user_language": self.user_language,
            "timezone": self.timezone,
            "screen_resolution": self.screen_resolution,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UserUIEnvironments":
        """从字典创建用户UI环境信息"""
        return cls(
            browser_name=data.get("browser_name", ""),
            browser_version=data.get("browser_version", ""),
            user_os=data.get("user_os", ""),
            user_language=data.get("user_language", ""),
            timezone=data.get("timezone", ""),
            screen_resolution=data.get("screen_resolution", ""),
        )

    def get_safe_for_analytics(self) -> dict[str, Any]:
        """获取安全的分析数据

        对于 UI 环境信息，所有字段通常都是安全的。
        仅用于与其他系统信息类保持接口一致。

        Returns:
            完整的 UI 环境信息字典
        """
        return self.to_dict()


@dataclass
class UserUIContext:
    """用户前端动态上下文信息，如打开的文件、当前文件、选中内容、当前模式等

    隐私保护:
    - current_selected_content 可能包含敏感数据，需要过滤
    - 文件路径可能包含用户信息，需要匿名化
    - user_preferences 可能包含个人设置，需要谨慎处理
    """

    open_files: list[str] = field(default_factory=list)
    active_applications: list[str] = field(default_factory=list)
    user_preferences: dict[str, Any] = field(default_factory=dict)
    current_file: str | None = None
    current_selected_content: str | None = None
    current_mode: str | None = None
    current_llm_id: str | None = None
    conversation_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "open_files": self.open_files,
            "active_applications": self.active_applications,
            "user_preferences": self.user_preferences,
            "current_file": self.current_file,
            "current_selected_content": self.current_selected_content,
            "current_mode": self.current_mode,
            "current_llm_id": self.current_llm_id,
            "conversation_id": self.conversation_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UserUIContext":
        """从字典创建用户UI上下文信息"""
        return cls(
            open_files=data.get("open_files", []),
            active_applications=data.get("active_applications", []),
            user_preferences=data.get("user_preferences", {}),
            current_file=data.get("current_file"),
            current_selected_content=data.get("current_selected_content"),
            current_mode=data.get("current_mode"),
            current_llm_id=data.get("current_llm_id"),
            conversation_id=data.get("conversation_id"),
        )

    def get_safe_for_analytics(self) -> dict[str, Any]:
        """获取安全的分析数据 (隐私保护版本)

        排除或匿名化敏感的上下文信息:
        - current_selected_content: 完全排除 (可能包含敏感数据)
        - open_files: 仅保留数量，不保留路径
        - current_file: 仅保留文件名，不保留完整路径

        Returns:
            安全的上下文信息字典
        """
        return {
            "open_files_count": len(self.open_files),
            "active_applications_count": len(self.active_applications),
            "current_mode": self.current_mode,
            "current_llm_id": self.current_llm_id,
            # 文件路径匿名化 - 仅保留文件名
            "current_file": self._anonymize_path(self.current_file) if self.current_file else None,
            # 完全排除选中的内容 (可能包含敏感数据)
            # "current_selected_content": None,
        }

    def _anonymize_path(self, file_path: str | None) -> str | None:
        """匿名化文件路径

        Args:
            file_path: 完整文件路径

        Returns:
            仅包含文件名的路径
        """
        if not file_path:
            return None

        # 提取文件名 (保留扩展名)
        import os
        filename = os.path.basename(file_path)

        # 如果文件名过长，进一步简化
        if len(filename) > 50:
            # 保留扩展名
            ext = os.path.splitext(filename)[1]
            return f"[FILE]{ext}" if ext else "[FILE]"

        # 如果看起来像哈希（包含多个点和数字/字母混合），进一步简化
        if '.' in filename[:10] and any(c.isdigit() for c in filename[:10]):
            ext = os.path.splitext(filename)[1]
            return f"[FILE]{ext}" if ext else "[FILE]"

        return filename
