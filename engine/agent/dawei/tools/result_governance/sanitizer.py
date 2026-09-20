# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""X3 — 工具输出敏感数据过滤器

复用 logg/sanitize_logs.py 的 SensitiveInfoFilter 正则模式，
在快照存储前对 raw_result 进行脱敏。
"""

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# 敏感 key 正则（与 security_auditor.py 一致）
_SENSITIVE_KEY_RE = re.compile(
    r"(password|passwd|secret|token|api[_-]?key|private[_-]?key|authorization|cookie|credential|jwt)",
    re.IGNORECASE,
)
_REDACTED = "***REDACTED***"

# 复用日志脱敏过滤器（延迟初始化避免循环导入）
_sensitive_filter = None


def _get_sensitive_filter():
    global _sensitive_filter
    if _sensitive_filter is None:
        try:
            from dawei.logg.sanitize_logs import SensitiveInfoFilter

            _sensitive_filter = SensitiveInfoFilter()
        except ImportError:
            logger.warning("SensitiveInfoFilter not available, using basic patterns only")
            _sensitive_filter = None
    return _sensitive_filter


# 工具输出专用脱敏：在日志脱敏基础上增加命令输出场景
_EXTRA_PATTERNS: list[tuple[re.Pattern, str]] = [
    # 数据库连接字符串（含密码）
    (re.compile(r"(postgresql|postgres|mysql|redis|mongodb|amqp)://[^\s]+:[^\s@]+@"), r"\1://***:***@"),
    # AWS Access Key ID
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AKIA***REDACTED***"),
    # 私钥头
    (re.compile(r"-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"), "-----BEGIN PRIVATE KEY [REDACTED]-----"),
    # Slack token
    (re.compile(r"xox[baprs]-[0-9a-zA-Z]{10,48}"), "xox***REDACTED***"),
    # GitHub PAT
    (re.compile(r"gh[pousr]_[A-Za-z0-9]{36}"), "ghp_***REDACTED***"),
    # Generic high-entropy secrets in env-like assignments
    (re.compile(r"(SECRET_KEY|JWT_SECRET|ENCRYPTION_KEY)[=:]\s*['\"]?[A-Za-z0-9+/=]{16,}"), r"\1=***REDACTED***"),
]


def _is_sensitive_key(key: str) -> bool:
    """检查 key 名是否匹配敏感模式。"""
    return bool(_SENSITIVE_KEY_RE.search(str(key)))


def sanitize_tool_output(raw: Any) -> Any:
    """对工具输出进行敏感数据脱敏——用于快照存储前。

    策略：
    1. 字符串：正则替换敏感模式
    2. dict：递归脱敏（key 匹配 _SENSITIVE_KEY_RE 的 value 直接替换）
    3. list：递归脱敏每个元素
    4. 其他类型：原样返回
    """
    if raw is None:
        return None

    if isinstance(raw, str):
        result = raw
        # 先用 SensitiveInfoFilter 的模式
        sf = _get_sensitive_filter()
        if sf is not None:
            result = sf.sanitize_string(result)
        # 再用额外的工具输出专用模式
        for pattern, replacement in _EXTRA_PATTERNS:
            result = pattern.sub(replacement, result)
        return result

    if isinstance(raw, dict):
        return {k: (_REDACTED if _is_sensitive_key(k) else sanitize_tool_output(v)) for k, v in raw.items()}

    if isinstance(raw, list):
        return [sanitize_tool_output(item) for item in raw]

    if isinstance(raw, tuple):
        return [sanitize_tool_output(item) for item in raw]

    return raw
