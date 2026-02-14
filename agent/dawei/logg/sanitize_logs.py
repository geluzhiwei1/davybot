# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""日志敏感信息过滤模块

提供日志敏感信息过滤功能，用于自动检测并替换日志中的敏感信息：
- API 密钥
- JWT tokens
- 密码
- 数据库连接字符串
- 其他敏感凭证
"""

import logging
import re
from typing import Any


class SensitiveInfoFilter(logging.Filter):
    """日志敏感信息过滤器

    自动检测并替换日志消息中的敏感信息为 ***REDACTED***。

    支持的敏感信息类型：
    - API 密钥（api_key, api-key,apikey 等）
    - Bearer tokens（JWT）
    - 密码（password, passwd, pwd 等）
    - 数据库连接字符串
    - 私钥
    - 密钥（secret, token 等）
    """

    # 敏感信息模式列表
    PATTERNS = [
        # API 密钥（支持 api_key, api-key, api key 等格式）
        (r'(api[ _\-]?key[=:]\s*)[^\s\'"]+', r"\1***REDACTED***", re.IGNORECASE),
        # Bearer tokens
        (r'(bearer\s+)[^\s\'"]+', r"\1***REDACTED***", re.IGNORECASE),
        # 密码
        (r'(password|passwd|pwd)[=:]\s*[^\s\'"]+', r"\1=***REDACTED***", re.IGNORECASE),
        # 数据库连接字符串（简化版）
        (
            r'(mongodb://|mysql://|postgresql://|postgres://)[^\s\'"]+@[^\s\'"]+',
            r"\1***REDACTED***@***REDACTED***",
            re.IGNORECASE,
        ),
        # 私钥标记
        (
            r"(-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----)",
            r"\1***KEY CONTENT REDACTED***",
            re.IGNORECASE,
        ),
        # Secret/token
        (
            r'(secret|token|access[ _\-]?token)[=:]\s*[^\s\'"]+',
            r"\1=***REDACTED***",
            re.IGNORECASE,
        ),
        # Session ID（可选，根据需要启用）
        # (r'(session[ _\-]?id[=:]\s*)[^\s\'"]+', r'\1***REDACTED***', re.IGNORECASE),
        # Authorization headers
        (
            r"(authorization['\"]?\s*:\s*['\"])[^'\"]+",
            r"\1***REDACTED***",
            re.IGNORECASE,
        ),
    ]

    def __init__(self, max_length: int = 1000):
        """初始化过滤器

        Args:
            max_length: 日志消息最大长度，超过则截断（防止超大消息）
        """
        super().__init__()
        self.max_length = max_length
        # 预编译正则表达式以提高性能
        self.compiled_patterns = [(re.compile(pattern, flags), replacement) for pattern, replacement, flags in self.PATTERNS]

    def filter(self, record: logging.LogRecord) -> bool:
        """过滤日志记录，替换敏感信息

        Args:
            record: 日志记录对象

        Returns:
            True（始终允许记录通过）
        """
        # 获取原始消息
        original_msg = record.getMessage()

        # 截断超长消息
        if len(original_msg) > self.max_length:
            original_msg = original_msg[: self.max_length] + "... (truncated)"

        # 应用所有敏感信息模式
        sanitized_msg = original_msg
        for pattern, replacement in self.compiled_patterns:
            sanitized_msg = pattern.sub(replacement, sanitized_msg)

        # 更新日志记录的消息
        record.msg = sanitized_msg
        record.args = ()  # 清空参数，因为已经格式化了

        return True

    def sanitize_string(self, text: str) -> str:
        """直接过滤字符串中的敏感信息（工具方法）

        Args:
            text: 原始文本

        Returns:
            过滤后的文本
        """
        sanitized = text
        for pattern, replacement in self.compiled_patterns:
            sanitized = pattern.sub(replacement, sanitized)
        return sanitized


def sanitize_for_log(message: str, max_length: int = 1000) -> str:
    """便捷函数：过滤日志消息中的敏感信息

    Args:
        message: 原始消息
        max_length: 最大长度（超过则截断）

    Returns:
        过滤后的消息

    Examples:
        >>> log_msg = "API key: sk-1234567890abcdef"
        >>> sanitize_for_log(log_msg)
        'API key: ***REDACTED***'

        >>> log_msg = "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
        >>> sanitize_for_log(log_msg)
        'Bearer ***REDACTED***'
    """
    # 截断超长消息
    if len(message) > max_length:
        message = message[:max_length] + "... (truncated)"

    # 应用所有模式
    filter_instance = SensitiveInfoFilter()
    return filter_instance.sanitize_string(message)


def sanitize_dict(data: dict[str, Any], exclude_keys: list[str] | None = None) -> dict[str, Any]:
    """过滤字典中的敏感信息

    Args:
        data: 原始字典
        exclude_keys: 要排除的键列表（默认包含常见的敏感键）

    Returns:
        过滤后的字典副本

    Examples:
        >>> data = {"api_key": "sk-1234", "user": "alice", "password": "secret"}
        >>> sanitize_dict(data)
        {'api_key': '***REDACTED***', 'user': 'alice', 'password': '***REDACTED***'}
    """
    if exclude_keys is None:
        # 默认排除常见的敏感键
        exclude_keys = [
            "api_key",
            "apikey",
            "api-key",
            "secret",
            "token",
            "access_token",
            "refresh_token",
            "password",
            "passwd",
            "pwd",
            "private_key",
            "private_key",
            "authorization",
            "auth",
        ]

    sanitized = {}
    filter_instance = SensitiveInfoFilter()

    for key, value in data.items():
        # 检查键是否敏感
        key_lower = key.lower()
        if any(exclude_key in key_lower for exclude_key in exclude_keys):
            # 键本身敏感，完全替换
            sanitized[key] = "***REDACTED***"
        elif isinstance(value, str):
            # 字符串值，应用过滤器
            sanitized[key] = filter_instance.sanitize_string(value)
        elif isinstance(value, dict):
            # 递归处理嵌套字典
            sanitized[key] = sanitize_dict(value, exclude_keys)
        else:
            # 其他类型保持不变
            sanitized[key] = value

    return sanitized
