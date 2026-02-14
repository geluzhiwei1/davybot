# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""错误处理器

专门处理WebSocket通信中的各种错误情况，提供错误分类、统计和恢复机制。
"""

import asyncio
import contextlib
import logging
import traceback
from collections.abc import Callable
from datetime import datetime, timezone, timedelta
from enum import StrEnum
from typing import Any

from dawei.websocket.protocol import (
    BaseWebSocketMessage,
    ErrorMessage,
    MessageType,
    WarningMessage,
)

from .base import StatefulMessageHandler

logger = logging.getLogger(__name__)


class ErrorSeverity(StrEnum):
    """错误严重程度"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(StrEnum):
    """错误类别"""

    CONNECTION = "connection"
    MESSAGE = "message"
    VALIDATION = "validation"
    PROCESSING = "processing"
    SYSTEM = "system"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    RATE_LIMIT = "rate_limit"


class ErrorInfo:
    """错误信息"""

    def __init__(
        self,
        code: str,
        message: str,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        category: ErrorCategory = ErrorCategory.SYSTEM,
        details: dict[str, Any] | None = None,
        recoverable: bool = True,
        session_id: str | None = None,
        timestamp: datetime | None = None,
    ):
        self.code = code
        self.message = message
        self.severity = severity
        self.category = category
        self.details = details or {}
        self.recoverable = recoverable
        self.session_id = session_id
        self.timestamp = timestamp or datetime.now(timezone.utc)
        self.stack_trace = traceback.format_exc()

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
            "category": self.category,
            "details": self.details,
            "recoverable": self.recoverable,
            "session_id": self.session_id,
            "timestamp": self.timestamp.isoformat(),
            "stack_trace": self.stack_trace,
        }


class ErrorHandler(StatefulMessageHandler):
    """错误处理器"""

    async def handle(
        self,
        _session_id: str,
        _message: BaseWebSocketMessage,
    ) -> BaseWebSocketMessage | None:
        """处理消息的具体实现

        Args:
            session_id: 会话ID
            message: 接收到的消息

        Returns:
            可选的响应消息

        """
        # ErrorHandler不处理直接消息，只处理通过其他方法调用的错误
        return None

    def __init__(self, max_error_history: int = 1000, cleanup_interval: int = 3600):
        super().__init__()
        self.max_error_history = max_error_history
        self.cleanup_interval = cleanup_interval
        self.error_history: list[ErrorInfo] = []
        self.error_stats: dict[str, dict[str, Any]] = {}
        self.error_callbacks: dict[str, list[Callable]] = {}
        self.recovery_strategies: dict[str, Callable] = {}
        self._cleanup_task: asyncio.Task | None = None

    def get_supported_types(self) -> list[str]:
        """获取支持的消息类型"""
        return [MessageType.ERROR, MessageType.WARNING]

    async def on_initialize(self):
        """初始化时的回调"""
        await super().on_initialize()

        # 启动清理任务
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

        # 初始化错误统计
        await self.set_state("initialized", True)
        await self.set_state("error_count", 0)
        await self.set_state("last_error_time", None)

        # 注册默认恢复策略
        self._register_default_recovery_strategies()

        logger.info("错误处理器已初始化")

    async def process_message(
        self,
        session_id: str,
        message: BaseWebSocketMessage,
    ) -> BaseWebSocketMessage | None:
        """处理错误消息

        Args:
            session_id: 会话ID
            message: 错误消息

        Returns:
            可选的响应消息

        """
        if isinstance(message, ErrorMessage):
            return await self._handle_error_message(session_id, message)
        if isinstance(message, WarningMessage):
            return await self._handle_warning_message(session_id, message)
        logger.warning(f"收到非错误/警告消息类型: {type(message)}")
        return None

    async def _handle_error_message(
        self,
        session_id: str,
        message: ErrorMessage,
    ) -> BaseWebSocketMessage | None:
        """处理错误消息

        Args:
            session_id: 会话ID
            message: 错误消息

        Returns:
            可选的响应消息

        """
        # 创建错误信息
        try:
            timestamp = datetime.fromisoformat(message.timestamp)
        except (ValueError, TypeError, AttributeError):
            timestamp = datetime.now(timezone.utc)
            logger.warning(
                f"Invalid timestamp format in error message: {message.timestamp}, using current time",
            )

        error_info = ErrorInfo(
            code=message.code,
            message=message.message,
            details=message.details,
            recoverable=message.recoverable,
            session_id=session_id,
            timestamp=timestamp,
        )

        # 分类错误
        error_info.category = self._categorize_error(message.code)
        error_info.severity = self._determine_severity(message.code, error_info.category)

        # 记录错误
        await self._record_error(error_info)

        # 尝试恢复
        if error_info.recoverable:
            recovery_result = await self._attempt_recovery(error_info)
            if recovery_result:
                return recovery_result

        # 发送错误确认
        return ErrorMessage(
            session_id=session_id,
            code="ERROR_RECEIVED",
            message=f"错误已收到并记录: {message.code}",
            details={
                "original_code": message.code,
                "category": error_info.category,
                "severity": error_info.severity,
            },
            recoverable=True,
        )

    async def _handle_warning_message(
        self,
        session_id: str,
        message: WarningMessage,
    ) -> BaseWebSocketMessage | None:
        """处理警告消息

        Args:
            session_id: 会话ID
            message: 警告消息

        Returns:
            可选的响应消息

        """
        # 创建错误信息（低严重程度）
        try:
            timestamp = datetime.fromisoformat(message.timestamp)
        except (ValueError, TypeError, AttributeError):
            timestamp = datetime.now(timezone.utc)
            logger.warning(
                f"Invalid timestamp format in warning message: {message.timestamp}, using current time",
            )

        error_info = ErrorInfo(
            code=message.code,
            message=message.message,
            severity=ErrorSeverity.LOW,
            category=ErrorCategory.SYSTEM,
            details=message.details,
            recoverable=True,
            session_id=session_id,
            timestamp=timestamp,
        )

        # 记录警告
        await self._record_error(error_info)

        # 发送警告确认
        return WarningMessage(
            session_id=session_id,
            code="WARNING_RECEIVED",
            message=f"警告已收到并记录: {message.code}",
            details={"original_code": message.code, "severity": error_info.severity},
        )

    def _categorize_error(self, error_code: str) -> ErrorCategory:
        """根据错误代码分类错误

        Args:
            error_code: 错误代码

        Returns:
            错误类别

        """
        # 连接错误
        if error_code.startswith("CONNECTION_") or error_code in [
            "WEBSOCKET_ERROR",
            "TIMEOUT",
        ]:
            return ErrorCategory.CONNECTION

        # 消息错误
        if error_code.startswith("MESSAGE_") or error_code in [
            "INVALID_JSON",
            "UNKNOWN_MESSAGE_TYPE",
        ]:
            return ErrorCategory.MESSAGE

        # 验证错误
        if error_code.startswith("VALIDATION_") or error_code in [
            "INVALID_FORMAT",
            "MISSING_FIELD",
        ]:
            return ErrorCategory.VALIDATION

        # 处理错误
        if error_code.startswith("PROCESSING_") or error_code in [
            "HANDLER_ERROR",
            "TASK_FAILED",
        ]:
            return ErrorCategory.PROCESSING

        # 认证错误
        if error_code.startswith("AUTH_") or error_code in [
            "UNAUTHORIZED",
            "FORBIDDEN",
        ]:
            return ErrorCategory.AUTHENTICATION

        # 授权错误
        if error_code.startswith("PERMISSION_") or error_code in ["ACCESS_DENIED"]:
            return ErrorCategory.AUTHORIZATION

        # 限流错误
        if error_code.startswith("RATE_") or error_code in ["TOO_MANY_REQUESTS"]:
            return ErrorCategory.RATE_LIMIT

        # 默认为系统错误
        return ErrorCategory.SYSTEM

    def _determine_severity(self, error_code: str, category: ErrorCategory) -> ErrorSeverity:
        """确定错误严重程度

        Args:
            error_code: 错误代码
            category: 错误类别

        Returns:
            错误严重程度

        """
        # 关键错误
        if error_code in ["CRITICAL_ERROR", "SYSTEM_FAILURE", "DATABASE_ERROR"]:
            return ErrorSeverity.CRITICAL

        # 高严重程度错误
        if category in [
            ErrorCategory.SYSTEM,
            ErrorCategory.AUTHENTICATION,
        ] or error_code in [
            "CONNECTION_LOST",
            "HANDLER_ERROR",
            "PROCESSING_ERROR",
        ]:
            return ErrorSeverity.HIGH

        # 低严重程度错误
        if category in [
            ErrorCategory.VALIDATION,
            ErrorCategory.RATE_LIMIT,
        ] or error_code in [
            "INVALID_FORMAT",
            "TOO_MANY_REQUESTS",
        ]:
            return ErrorSeverity.LOW

        # 默认为中等严重程度
        return ErrorSeverity.MEDIUM

    async def _record_error(self, error_info: ErrorInfo):
        """记录错误

        Args:
            error_info: 错误信息

        """
        # 添加到历史记录
        self.error_history.append(error_info)

        # 限制历史记录大小
        if len(self.error_history) > self.max_error_history:
            self.error_history = self.error_history[-self.max_error_history :]

        # 更新统计
        error_key = f"{error_info.category}_{error_info.code}"
        if error_key not in self.error_stats:
            self.error_stats[error_key] = {
                "count": 0,
                "first_occurrence": error_info.timestamp,
                "last_occurrence": error_info.timestamp,
                "severity": error_info.severity,
                "category": error_info.category,
            }

        self.error_stats[error_key]["count"] += 1
        self.error_stats[error_key]["last_occurrence"] = error_info.timestamp

        # 更新处理器状态
        error_count = await self.get_state("error_count", 0) + 1
        await self.set_state("error_count", error_count)
        await self.set_state("last_error_time", error_info.timestamp)

        # 记录日志
        log_level = {
            ErrorSeverity.LOW: logging.INFO,
            ErrorSeverity.MEDIUM: logging.WARNING,
            ErrorSeverity.HIGH: logging.ERROR,
            ErrorSeverity.CRITICAL: logging.CRITICAL,
        }.get(error_info.severity, logging.WARNING)

        logger.log(
            log_level,
            f"错误记录 [{error_info.severity}] {error_info.category}:{error_info.code} - {error_info.message}",
        )

        # 调用错误回调
        await self._call_error_callbacks(error_info)

    async def _attempt_recovery(self, error_info: ErrorInfo) -> BaseWebSocketMessage | None:
        """尝试错误恢复

        Args:
            error_info: 错误信息

        Returns:
            恢复结果消息

        """
        # 检查是否有恢复策略
        if error_info.code in self.recovery_strategies:
            try:
                recovery_func = self.recovery_strategies[error_info.code]
                result = await recovery_func(error_info)

                if result:
                    logger.info(f"错误恢复成功: {error_info.code}")
                    return result
                logger.debug(f"恢复策略 {error_info.code} 返回空结果")

            except (
                RuntimeError,
                ValueError,
                TypeError,
                AttributeError,
                KeyError,
                asyncio.CancelledError,
            ) as e:
                logger.exception("错误恢复失败: {error_info.code} - ")
                # 创建错误恢复失败的错误记录
                recovery_error = ErrorInfo(
                    code=f"RECOVERY_FAILED_{error_info.code}",
                    message=f"恢复策略执行失败: {e}",
                    severity=ErrorSeverity.HIGH,
                    category=ErrorCategory.PROCESSING,
                    details={"original_error_code": error_info.code, "error": str(e)},
                    recoverable=False,
                    session_id=error_info.session_id,
                    timestamp=datetime.now(timezone.utc),
                )
                await self._record_error(recovery_error)
                # Intentional tolerance: User-provided recovery strategies may fail; we record but don't crash

        # 检查类别级别的恢复策略
        category_key = f"category_{error_info.category}"
        if category_key in self.recovery_strategies:
            try:
                recovery_func = self.recovery_strategies[category_key]
                result = await recovery_func(error_info)

                if result:
                    logger.info(f"类别错误恢复成功: {error_info.category}")
                    return result
                logger.debug(f"类别恢复策略 {error_info.category} 返回空结果")

            except (
                RuntimeError,
                ValueError,
                TypeError,
                AttributeError,
                KeyError,
                asyncio.CancelledError,
            ) as e:
                logger.exception("类别错误恢复失败: {error_info.category} - ")
                # 创建类别恢复失败的错误记录
                recovery_error = ErrorInfo(
                    code=f"CATEGORY_RECOVERY_FAILED_{error_info.category}",
                    message=f"类别恢复策略执行失败: {e}",
                    severity=ErrorSeverity.HIGH,
                    category=ErrorCategory.PROCESSING,
                    details={
                        "original_error_category": error_info.category,
                        "error": str(e),
                    },
                    recoverable=False,
                    session_id=error_info.session_id,
                    timestamp=datetime.now(timezone.utc),
                )
                await self._record_error(recovery_error)
                # Intentional tolerance: Category-level recovery strategies may fail; we record but don't crash

        return None

    async def _call_error_callbacks(self, error_info: ErrorInfo):
        """调用错误回调

        Args:
            error_info: 错误信息

        """
        # 调用通用错误回调
        for callback in self.error_callbacks.get("*", []):
            try:
                await callback(error_info)
                logger.debug(f"通用错误回调执行成功: {callback.__name__}")
            except (
                RuntimeError,
                ValueError,
                TypeError,
                AttributeError,
                KeyError,
                asyncio.CancelledError,
            ) as e:
                logger.exception("通用错误回调执行失败: {callback.__name__} - ")
                # 记录回调失败错误
                callback_error = ErrorInfo(
                    code="CALLBACK_EXECUTION_FAILED",
                    message=f"通用错误回调执行失败: {e}",
                    severity=ErrorSeverity.MEDIUM,
                    category=ErrorCategory.PROCESSING,
                    details={"callback": callback.__name__, "error": str(e)},
                    recoverable=False,
                    session_id=error_info.session_id,
                    timestamp=datetime.now(timezone.utc),
                )
                await self._record_error(callback_error)
                # Intentional tolerance: User callbacks may fail; we record but continue processing other callbacks

        # 调用特定错误回调
        for callback in self.error_callbacks.get(error_info.code, []):
            try:
                await callback(error_info)
                logger.debug(f"特定错误回调执行成功: {error_info.code} - {callback.__name__}")
            except (
                RuntimeError,
                ValueError,
                TypeError,
                AttributeError,
                KeyError,
                asyncio.CancelledError,
            ) as e:
                logger.exception("特定错误回调执行失败: {error_info.code} - {callback.__name__} - ")
                # 记录回调失败错误
                callback_error = ErrorInfo(
                    code=f"CALLBACK_EXECUTION_FAILED_{error_info.code}",
                    message=f"特定错误回调执行失败: {e}",
                    severity=ErrorSeverity.MEDIUM,
                    category=ErrorCategory.PROCESSING,
                    details={
                        "error_code": error_info.code,
                        "callback": callback.__name__,
                        "error": str(e),
                    },
                    recoverable=False,
                    session_id=error_info.session_id,
                    timestamp=datetime.now(timezone.utc),
                )
                await self._record_error(callback_error)
                # Intentional tolerance: User callbacks may fail; we record but continue processing other callbacks

        # 调用类别错误回调
        for callback in self.error_callbacks.get(f"category_{error_info.category}", []):
            try:
                await callback(error_info)
                logger.debug(f"类别错误回调执行成功: {error_info.category} - {callback.__name__}")
            except (
                RuntimeError,
                ValueError,
                TypeError,
                AttributeError,
                KeyError,
                asyncio.CancelledError,
            ) as e:
                logger.exception(
                    f"类别错误回调执行失败: {error_info.category} - {callback.__name__} - {e}",
                )
                # 记录回调失败错误
                callback_error = ErrorInfo(
                    code=f"CATEGORY_CALLBACK_EXECUTION_FAILED_{error_info.category}",
                    message=f"类别错误回调执行失败: {e}",
                    severity=ErrorSeverity.MEDIUM,
                    category=ErrorCategory.PROCESSING,
                    details={
                        "error_category": error_info.category,
                        "callback": callback.__name__,
                        "error": str(e),
                    },
                    recoverable=False,
                    session_id=error_info.session_id,
                    timestamp=datetime.now(timezone.utc),
                )
                await self._record_error(callback_error)
                # Intentional tolerance: User callbacks may fail; we record but continue processing other callbacks

    def _register_default_recovery_strategies(self):
        """注册默认恢复策略"""
        # 连接错误恢复
        self.recovery_strategies["CONNECTION_LOST"] = self._recover_connection_lost
        self.recovery_strategies["TIMEOUT"] = self._recover_timeout

        # 消息错误恢复
        self.recovery_strategies["INVALID_JSON"] = self._recover_invalid_json
        self.recovery_strategies["UNKNOWN_MESSAGE_TYPE"] = self._recover_unknown_message_type

        # 类别级别恢复
        self.recovery_strategies["category_connection"] = self._recover_connection_errors
        self.recovery_strategies["category_validation"] = self._recover_validation_errors

    async def _recover_connection_lost(
        self,
        error_info: ErrorInfo,
    ) -> BaseWebSocketMessage | None:
        """恢复连接丢失错误"""
        # 这里可以实现重连逻辑
        return ErrorMessage(
            session_id=error_info.session_id,
            code="RECOVERY_ATTEMPT",
            message="正在尝试恢复连接...",
            recoverable=True,
        )

    async def _recover_timeout(self, error_info: ErrorInfo) -> BaseWebSocketMessage | None:
        """恢复超时错误"""
        # 这里可以实现重试逻辑
        return ErrorMessage(
            session_id=error_info.session_id,
            code="RECOVERY_ATTEMPT",
            message="正在重试超时操作...",
            recoverable=True,
        )

    async def _recover_invalid_json(self, error_info: ErrorInfo) -> BaseWebSocketMessage | None:
        """恢复无效JSON错误"""
        return ErrorMessage(
            session_id=error_info.session_id,
            code="RECOVERY_ATTEMPT",
            message="请检查消息格式，确保发送有效的JSON数据",
            recoverable=True,
        )

    async def _recover_unknown_message_type(
        self,
        error_info: ErrorInfo,
    ) -> BaseWebSocketMessage | None:
        """恢复未知消息类型错误"""
        return ErrorMessage(
            session_id=error_info.session_id,
            code="RECOVERY_ATTEMPT",
            message="请检查消息类型，确保发送支持的消息类型",
            recoverable=True,
        )

    async def _recover_connection_errors(
        self,
        error_info: ErrorInfo,
    ) -> BaseWebSocketMessage | None:
        """恢复连接错误"""
        return ErrorMessage(
            session_id=error_info.session_id,
            code="RECOVERY_ATTEMPT",
            message="正在处理连接问题...",
            recoverable=True,
        )

    async def _recover_validation_errors(
        self,
        error_info: ErrorInfo,
    ) -> BaseWebSocketMessage | None:
        """恢复验证错误"""
        return ErrorMessage(
            session_id=error_info.session_id,
            code="RECOVERY_ATTEMPT",
            message="请检查消息格式和内容...",
            recoverable=True,
        )

    async def _cleanup_loop(self):
        """清理循环"""
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval)
                await self._cleanup_old_errors()
            except asyncio.CancelledError:
                # Task was cancelled during shutdown - expected behavior
                break
            except Exception:
                # Intentional tolerance: Background cleanup should never crash the error handler
                # This is a non-critical maintenance task that must always keep running
                logger.exception("清理错误历史时出错: ")

    async def _cleanup_old_errors(self, max_age_hours: int = 24):
        """清理旧错误记录

        Args:
            max_age_hours: 最大保留时间（小时）

        """
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)

        # 清理错误历史
        self.error_history = [error for error in self.error_history if error.timestamp > cutoff_time]

        # 清理错误统计
        for key, stats in list(self.error_stats.items()):
            if stats["last_occurrence"] < cutoff_time:
                del self.error_stats[key]

        logger.info(f"已清理 {max_age_hours} 小时前的错误记录")

    def add_error_callback(self, error_code: str, callback: Callable):
        """添加错误回调

        Args:
            error_code: 错误代码，使用"*"表示所有错误
            callback: 回调函数

        """
        # 输入验证
        if not isinstance(error_code, str):
            raise ValueError("error_code must be a string")

        if error_code not in ["*"] and not error_code.strip():
            raise ValueError("error_code cannot be empty (except for '*')")

        if not callable(callback):
            raise ValueError("callback must be a callable function")

        # 验证回调函数参数
        import inspect

        try:
            sig = inspect.signature(callback)
            params = list(sig.parameters.values())
            if len(params) != 1 or not isinstance(params[0].annotation, type(ErrorInfo)):
                raise ValueError("callback must accept exactly one ErrorInfo parameter")
        except (ValueError, TypeError) as e:
            # Signature validation failed (e.g., built-in functions, C extensions)
            # We allow registration but log a warning for debugging
            logger.warning(f"Callback signature validation failed for {callback.__name__}: {e}")
            # Intentional tolerance: Some callable types (builtins, C extensions) can't be inspected;
            # we allow registration but may fail at call time

        if error_code not in self.error_callbacks:
            self.error_callbacks[error_code] = []

        # 检查是否已存在相同的回调
        existing_callbacks = self.error_callbacks[error_code]
        if callback in existing_callbacks:
            logger.warning(f"Callback already exists for error_code: {error_code}")
            return

        self.error_callbacks[error_code].append(callback)
        logger.info(f"已添加错误回调: {error_code}, 回调类型: {type(callback).__name__}")

    def remove_error_callback(self, error_code: str, callback: Callable):
        """移除错误回调

        Args:
            error_code: 错误代码
            callback: 回调函数

        """
        if error_code in self.error_callbacks and callback in self.error_callbacks[error_code]:
            self.error_callbacks[error_code].remove(callback)
            logger.info(f"已移除错误回调: {error_code}")

    def add_recovery_strategy(self, error_code: str, strategy: Callable):
        """添加恢复策略

        Args:
            error_code: 错误代码
            strategy: 恢复策略函数

        """
        self.recovery_strategies[error_code] = strategy
        logger.info(f"已添加恢复策略: {error_code}")

    def remove_recovery_strategy(self, error_code: str):
        """移除恢复策略

        Args:
            error_code: 错误代码

        """
        if error_code in self.recovery_strategies:
            del self.recovery_strategies[error_code]
            logger.info(f"已移除恢复策略: {error_code}")

    async def get_error_stats(self) -> dict[str, Any]:
        """获取错误统计

        Returns:
            错误统计信息

        """
        try:
            total_errors = await self.get_state("error_count", 0)
            last_error_time = await self.get_state("last_error_time")

            # 计算错误分类统计
            error_breakdown = {}
            try:
                error_breakdown = {category.value: sum(stats["count"] for stats in self.error_stats.values() if stats.get("category") == category) for category in ErrorCategory}
            except (KeyError, ValueError, TypeError, AttributeError):
                # Data structure inconsistencies - return empty breakdown
                logger.exception("计算错误分类统计失败: ")
                error_breakdown = {}
                # Defensive: Handle data structure inconsistencies in error_stats

            return {
                "total_errors": total_errors,
                "last_error_time": last_error_time.isoformat() if last_error_time else None,
                "error_types": len(self.error_stats),
                "recent_errors": len(self.error_history),
                "error_breakdown": error_breakdown,
                "recovery_strategies_count": len(self.recovery_strategies),
                "error_callbacks_count": sum(len(callbacks) for callbacks in self.error_callbacks.values()),
            }

        except (KeyError, ValueError, TypeError, AttributeError, RuntimeError) as e:
            # Stats retrieval partially failed - return degraded response
            logger.exception("获取错误统计失败: ")
            # 返回基本的错误统计结构，即使某些数据获取失败
            return {
                "total_errors": 0,
                "last_error_time": None,
                "error_types": 0,
                "recent_errors": 0,
                "error_breakdown": {},
                "recovery_strategies_count": len(self.recovery_strategies),
                "error_callbacks_count": sum(len(callbacks) for callbacks in self.error_callbacks.values()),
                "error": f"获取统计失败: {e!s}",
            }
            # Defensive: Return degraded stats on partial failures - stats endpoint should never crash

    async def cleanup(self):
        """清理资源"""
        # 取消清理任务
        if self._cleanup_task:
            self._cleanup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._cleanup_task

        # 清理状态
        await self.clear_state()

        # 调用父类清理
        await super().cleanup()

        logger.info("错误处理器已清理")
