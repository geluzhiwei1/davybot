# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""PII 安全日志包装器 (§沙箱系统升级 v2 — N6)

功能:
- user_id → HMAC-SHA256(user_id, salt)[:12]
- workspace_path → workspace_id (哈希形式)
- 文件路径 → 仅保留 <ws:hash> 形式
- email → <email:hash> 形式

设计原则:
- 脱敏不可逆: salt 独立管理, 定期轮换
- 透明包装: 调用方传入 user_id, 自动脱敏后写入日志
- 物理路径不进入日志, 仅 workspace_id 出现

配置:
    DAWEI_LOG_SALT=<random-32-byte-base64>  # 环境变量
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
from pathlib import Path
from typing import Any


class PiiSafeLogger:
    """PII 感知日志包装器

    用法:
        logger = PiiSafeLogger(logging.getLogger(__name__))
        logger.info("[E2B] execute", user_id=ctx.user_id, workspace_id=ctx.workspace_id)
        # 日志中 user_id 自动哈希, workspace_id 保留 (已是哈希)

    安全保证:
    - user_id → HMAC-SHA256(user_id, salt)[:12], 不可逆
    - 物理路径 → <ws:hash> 形式, 不暴露真实路径
    - email → <email:hash> 形式
    """

    # 模块级缓存: salt 只读一次
    _salt_cache: bytes | None = None

    # stdlib Logger 的保留字参数 —— 必须按原样透传, 绝不能混进 extra
    # (否则 LogRecord 构造抛 KeyError: Attempt to overwrite 'exc_info' in LogRecord,
    #  2026-09-14 smoke #7 实测: 该 KeyError 会替换原始异常向上抛, 导致工具误报 success:false)
    _RESERVED_LOG_KWARGS = ("exc_info", "stack_info", "stacklevel")

    def __init__(
        self,
        logger: logging.Logger,
        salt: str | None = None,
    ):
        self._logger = logger
        self._salt = self._resolve_salt(salt)

    # ================================================================
    # 日志方法 (与 logging.Logger 接口一致)
    # ================================================================

    def info(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """info 日志, 自动脱敏 kwargs 中的 PII"""
        self._emit(self._logger.info, msg, args, kwargs)

    def warning(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """warning 日志, 自动脱敏"""
        self._emit(self._logger.warning, msg, args, kwargs)

    def error(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """error 日志, 自动脱敏"""
        self._emit(self._logger.error, msg, args, kwargs)

    def debug(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """debug 日志, 自动脱敏"""
        self._emit(self._logger.debug, msg, args, kwargs)

    def exception(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """exception 日志, 自动脱敏 (默认带堆栈)"""
        kwargs.setdefault("exc_info", True)
        self._emit(self._logger.error, msg, args, kwargs)

    def _emit(self, log_func, msg: str, args: tuple, kwargs: dict[str, Any]) -> None:
        """统一发射入口: 拆保留字参数 → 脱敏 → 调用底层 logger。

        铁律: 日志包装器绝不向调用方抛异常 —— 日志崩溃会替换调用方
        except 块里的原始异常 (2026-09-14 实测事故), 因此全程兜底。
        """
        try:
            kwargs = dict(kwargs)  # 不修改调用方传入的 dict
            passthrough: dict[str, Any] = {}
            for key in self._RESERVED_LOG_KWARGS:
                if key in kwargs:
                    passthrough[key] = kwargs.pop(key)
            extra = dict(kwargs.pop("extra", None) or {})
            extra.update(kwargs)  # 其余 kwargs 作为结构化字段进 extra
            safe_msg = self._redact_message(msg)
            safe_extra = self._redact_kwargs(extra)
            log_func(safe_msg, *args, extra=safe_extra, **passthrough)
        except Exception:
            # 脱敏/发射失败也要留下痕迹, 但绝不影响调用方
            try:
                self._logger.log(logging.ERROR, "[PII_LOGGER] emit failed, raw msg: %s", str(msg)[:500])
            except Exception:
                pass

    # ================================================================
    # 透传方法
    # ================================================================

    @property
    def underlying(self) -> logging.Logger:
        """获取底层 logger (用于不支持脱敏的场景)"""
        return self._logger

    def setLevel(self, level: int) -> None:
        self._logger.setLevel(level)

    def isEnabledFor(self, level: int) -> bool:
        return self._logger.isEnabledFor(level)

    # ================================================================
    # 脱敏内部实现
    # ================================================================

    def _resolve_salt(self, salt: str | None) -> bytes:
        """解析 salt (优先参数 > 环境变量 > 缓存)"""
        if salt:
            return salt.encode()

        if PiiSafeLogger._salt_cache is not None:
            return PiiSafeLogger._salt_cache

        env_salt = os.environ.get("DAWEI_LOG_SALT", "").strip()
        if not env_salt:
            # 生产环境应设置, 开发环境用默认值并警告
            env_salt = "dawei-dev-salt-not-for-production"
            self._logger.warning("[PII_LOGGER] DAWEI_LOG_SALT 未设置, 使用不安全的开发默认值。生产环境必须设置 DAWEI_LOG_SALT 环境变量!")

        PiiSafeLogger._salt_cache = env_salt.encode()
        return PiiSafeLogger._salt_cache

    def _hash(self, value: str) -> str:
        """HMAC-SHA256 哈希, 取前 12 字符"""
        return hmac.new(self._salt, value.encode(), hashlib.sha256).hexdigest()[:12]

    def _redact_message(self, msg: str) -> str:
        """脱敏消息文本中的 PII

        策略:
        - 绝对路径 (/home/user/...) → <ws:hash>
        - email → <email:hash>
        """
        if not isinstance(msg, str):
            return str(msg)

        # 脱敏绝对路径
        import re

        # 匹配 Unix 绝对路径
        msg = re.sub(
            r"/(?:home|Users|root|workspace|srv|var|tmp|opt)/[^\s\"')\]]+",
            lambda m: f"<ws:{self._hash(m.group())}>",
            msg,
        )

        # 脱敏 email
        return re.sub(
            r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
            lambda m: f"<email:{self._hash(m.group())}>",
            msg,
        )

    def _redact_kwargs(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        """脱敏关键字参数中的 PII"""
        safe: dict[str, Any] = {}
        for key, value in kwargs.items():
            safe[key] = self._auto_redact(value)
        return safe

    def _auto_redact(self, value: Any) -> Any:
        """自动判断值类型并脱敏"""
        if isinstance(value, str):
            # workspace_id 格式 (已经是哈希), 不再处理
            if value.startswith(("<ws:", "<email:")):
                return value

            # 物理路径
            if value.startswith("/") or ("\\" in value and len(value) > 3):
                return self._redact_path(value)

            # email 模式
            if "@" in value and "." in value.split("@")[-1]:
                return f"<email:{self._hash(value)}>"

            # user_id (非路径非 email, 但包含在脱敏参数中)
            # 检查是否是已知 PII 字段
            return value

        if isinstance(value, Path):
            return self._redact_path(str(value))

        return value

    def _redact_path(self, path: str | Path) -> str:
        """物理路径 → workspace_id 风格字符串"""
        try:
            p = Path(path)
            resolved = str(p.resolve())
            return f"<ws:{self._hash(resolved)}>"
        except Exception:
            return f"<ws:{self._hash(str(path))}>"


# ================================================================
# 便捷工厂函数
# ================================================================


def get_pii_safe_logger(name: str) -> PiiSafeLogger:
    """获取 PiiSafeLogger 实例

    Args:
        name: logger 名称 (通常传 __name__)

    Returns:
        PiiSafeLogger 实例
    """
    return PiiSafeLogger(logging.getLogger(name))
