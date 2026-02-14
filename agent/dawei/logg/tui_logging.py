# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""TUI 日志配置模块

提供 TUI 专用的日志配置功能。

Logging Strategy:
    ---------------
    This module implements the Phase 2 full logging configuration for TUI:

    1. Clear Previous Handlers:
       - Removes all existing handlers from root logger
       - Replaces Phase 1 early logging (from __main__.py)

    2. Console Handler (UTF-8):
       - UTF8StreamHandler for proper multi-language support
       - SensitiveInfoFilter to redact API keys, passwords, etc.
       - Compact format for terminal display
       - Max message length: 500 chars (truncated)

    3. File Handlers (Rotating):
       - Main log: All levels (DEBUG/INFO/WARNING/ERROR/CRITICAL)
         Location: workspace/.dawei/logs/tui.log
         OR: DAWEI_HOME/logs/tui/tui.log (if no workspace)
         Format: Rich with session/message context
         Max size: 10MB per file, 5 backups

       - Error log: ERROR and above only
         Location: Same as main log (tui_errors.log)
         Format: Rich with full exception traceback
         Max size: 10MB per file, 5 backups

    4. Context Tracking:
       - ContextFilter adds session_id and message_id to all log records
       - Enables tracing logs through the TUI session lifecycle

    5. Global Exception Handling:
       - sys.excepthook for all uncaught exceptions in main thread
       - threading.excepthook for exceptions in threads
       - asyncio exception handler for unhandled async exceptions
       - Captures ALL exception types (Exception, BaseException subclasses)

    File Path Priority:
    ------------------
    1. If workspace_path provided: workspace/.dawei/logs/
    2. If no workspace: DAWEI_HOME/logs/tui/

    This allows workspace-specific logs during development,
    with fallback to centralized logs for workspaceless sessions.
"""

import asyncio
import logging
import sys
import threading
import traceback
from pathlib import Path
from typing import Any

from dawei.config.logging_config import get_tui_error_log_path, get_tui_log_path

from .logger import ContextFilter, UTF8StreamHandler
from .sanitize_logs import SensitiveInfoFilter

# Store original hooks for cleanup
_original_excepthook: Any | None = None
_original_threading_excepthook: Any | None = None
_exception_logger: logging.Logger | None = None


class GlobalExceptionHandler:
    """全局异常处理器，捕获所有类型的异常

    捕获范围：
    1. 主线程中未捕获的异常 (sys.excepthook)
    2. 子线程中的异常 (threading.excepthook)
    3. 异步上下文中的异常 (asyncio exception handler)
    4. 所有 BaseException 子类（包括 SystemExit, KeyboardInterrupt, GeneratorExit）

    Exception Types Captured:
    ------------------------
    - Exception and all subclasses (TypeError, ValueError, etc.)
    - SystemExit - sys.exit() 调用
    - KeyboardInterrupt - Ctrl+C 中断
    - GeneratorExit - 生成器关闭
    - BaseException - 所有其他自定义异常基类
    """

    def __init__(self, logger: logging.Logger):
        """初始化全局异常处理器

        Args:
            logger: 用于记录异常的 logger
        """
        global _exception_logger
        _exception_logger = logger
        self.logger = logger

    def _format_exception_info(
        self,
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_tb: Any,
        context: str = "Main Thread",
    ) -> str:
        """格式化异常信息，包含完整的异常链

        处理异常链 (__cause__ 和 __context__)，提供完整的异常上下文。

        Args:
            exc_type: 异常类型
            exc_value: 异常实例
            exc_tb: 异常追踪对象
            context: 异常发生上下文描述

        Returns:
            格式化后的异常信息字符串
        """
        lines = []
        lines.append(f"\n{'=' * 60}")
        lines.append(f"UNCAUGHT EXCEPTION in {context}")
        lines.append(f"{'=' * 60}")
        lines.append(f"Exception Type: {exc_type.__name__}")
        lines.append(f"Exception Module: {exc_type.__module__}")

        # 添加异常消息
        if exc_value:
            lines.append(f"Exception Message: {exc_value!s}")

        # 检查是否是 BaseException 的特殊子类
        if exc_type in (SystemExit, KeyboardInterrupt, GeneratorExit):
            lines.append(f"NOTE: This is a special {exc_type.__name__} signal")

        # 处理异常链 (__cause__ - 显式异常链)
        if exc_value and hasattr(exc_value, "__cause__") and exc_value.__cause__:
            lines.append("\n--- Exception Chain (Cause) ---")
            cause = exc_value.__cause__
            lines.append(f"Caused by: {type(cause).__name__}: {cause!s}")

        # 处理异常上下文 (__context__ - 隐式异常链)
        if exc_value and hasattr(exc_value, "__context__") and exc_value.__context__:
            hasattr(exc_value, "__cause__") and exc_value.__cause__ is not None
            if exc_value.__context__ is not exc_value.__cause__:
                lines.append("\n--- Exception Context ---")
                ctx = exc_value.__context__
                lines.append(f"Context: {type(ctx).__name__}: {ctx!s}")

        # 添加抑制信息 (__suppress_context__)
        if exc_value and hasattr(exc_value, "__suppress_context__") and exc_value.__suppress_context__:
            lines.append("\nNOTE: Exception context is suppressed (explicit __cause__ exists)")

        lines.append("\n--- Full Traceback ---")

        # 获取完整的格式化追踪
        tb_lines = traceback.format_exception(exc_type, exc_value, exc_tb)
        lines.extend(tb_lines)

        # 如果有异常链，也添加其追踪
        if exc_value and hasattr(exc_value, "__cause__") and exc_value.__cause__:
            lines.append("\n--- Cause Traceback ---")
            cause_tb_lines = traceback.format_exception(
                type(exc_value.__cause__),
                exc_value.__cause__,
                exc_value.__cause__.__traceback__,
            )
            lines.extend(cause_tb_lines)

        lines.append(f"{'=' * 60}\n")

        return "\n".join(lines)

    def handle_exception(
        self,
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_tb: Any,
        context: str = "Main Thread",
    ) -> None:
        """处理并记录异常

        Args:
            exc_type: 异常类型
            exc_value: 异常实例
            exc_tb: 异常追踪对象
            context: 异常发生上下文
        """
        try:
            # 构建上下文信息（不包含完整堆栈，避免被 SensitiveInfoFilter 截断）
            context_lines = [
                f"\n{'=' * 60}",
                f"UNCAUGHT EXCEPTION in {context}",
                f"{'=' * 60}",
            ]
            context_lines.append(f"Exception Type: {exc_type.__name__}")
            context_lines.append(f"Exception Module: {exc_type.__module__}")

            # 添加异常消息
            if exc_value:
                context_lines.append(f"Exception Message: {exc_value!s}")

            # 检查是否是 BaseException 的特殊子类
            if exc_type in (SystemExit, KeyboardInterrupt, GeneratorExit):
                context_lines.append(f"NOTE: This is a special {exc_type.__name__} signal")

            # 处理异常链 (__cause__ - 显式异常链)
            if exc_value and hasattr(exc_value, "__cause__") and exc_value.__cause__:
                context_lines.append("\n--- Exception Chain (Cause) ---")
                cause = exc_value.__cause__
                context_lines.append(f"Caused by: {type(cause).__name__}: {cause!s}")

            # 处理异常上下文 (__context__ - 隐式异常链)
            if exc_value and hasattr(exc_value, "__context__") and exc_value.__context__:
                hasattr(exc_value, "__cause__") and exc_value.__cause__ is not None
                if exc_value.__context__ is not exc_value.__cause__:
                    context_lines.append("\n--- Exception Context ---")
                    ctx = exc_value.__context__
                    context_lines.append(f"Context: {type(ctx).__name__}: {ctx!s}")

            # 添加抑制信息 (__suppress_context__)
            if exc_value and hasattr(exc_value, "__suppress_context__") and exc_value.__suppress_context__:
                context_lines.append("\nNOTE: Exception context is suppressed (explicit __cause__ exists)")

            context_message = "\n".join(context_lines)

            # 根据异常类型决定日志级别
            # SystemExit 和 KeyboardInterrupt 通常不是错误
            if exc_type in (KeyboardInterrupt,):
                self.logger.info(context_message, exc_info=(exc_type, exc_value, exc_tb))
            elif exc_type == SystemExit:
                # 检查退出码
                exit_code = exc_value.code if exc_value is not None else 0
                if exit_code == 0:
                    self.logger.info(
                        f"{context_message}\nExit Code: {exit_code}",
                        exc_info=(exc_type, exc_value, exc_tb),
                    )
                else:
                    self.logger.error(
                        f"{context_message}\nExit Code: {exit_code}",
                        exc_info=(exc_type, exc_value, exc_tb),
                    )
            else:
                # 其他所有异常都记录为 ERROR
                # 使用 exc_info 参数让 logging 系统处理堆栈跟踪
                self.logger.error(context_message, exc_info=(exc_type, exc_value, exc_tb))

        except Exception as e:
            # 如果异常处理器本身出错，使用最基本的输出
            print(f"ERROR IN EXCEPTION HANDLER: {e}", file=sys.stderr)
            print(f"Original exception: {exc_type.__name__}: {exc_value}", file=sys.stderr)

    def install_hooks(self) -> None:
        """安装全局异常处理钩子

        此方法会替换 sys.excepthook 和 threading.excepthook，
        并设置 asyncio 的异常处理器。
        """
        global _original_excepthook, _original_threading_excepthook

        # 1. 安装主线程异常钩子
        _original_excepthook = sys.excepthook
        sys.excepthook = self._main_excepthook
        self.logger.info("✓ Installed global exception handler (sys.excepthook)")

        # 2. 安装线程异常钩子 (Python 3.8+)
        if hasattr(threading, "excepthook"):
            _original_threading_excepthook = threading.excepthook
            threading.excepthook = self._threading_excepthook
            self.logger.info("✓ Installed threading exception handler (threading.excepthook)")

        # 3. 设置 asyncio 异常处理器
        try:
            loop = asyncio.get_event_loop()
            loop.set_exception_handler(self._async_exception_handler)
            self.logger.info("✓ Installed asyncio exception handler")
        except RuntimeError:
            # 没有运行的事件循环，稍后会在 TUI app 中设置
            self.logger.debug("No event loop running yet, asyncio handler will be set later")

    def uninstall_hooks(self) -> None:
        """卸载全局异常处理钩子，恢复原始行为

        通常在程序退出时调用，避免干扰其他异常处理机制。
        """
        global _original_excepthook, _original_threading_excepthook

        if _original_excepthook is not None:
            sys.excepthook = _original_excepthook
            _original_excepthook = None
            self.logger.info("✓ Uninstalled global exception handler")

        if _original_threading_excepthook is not None and hasattr(threading, "excepthook"):
            threading.excepthook = _original_threading_excepthook
            _original_threading_excepthook = None
            self.logger.info("✓ Uninstalled threading exception handler")

    def _main_excepthook(self, exc_type: type[BaseException], exc_value: BaseException, exc_tb: Any) -> None:
        """主线程异常钩子

        替换 sys.excepthook，捕获主线程中所有未处理的异常。

        Args:
            exc_type: 异常类型
            exc_value: 异常实例
            exc_tb: 异常追踪对象
        """
        self.handle_exception(exc_type, exc_value, exc_tb, context="Main Thread")

        # 调用原始钩子（如果有）
        global _original_excepthook
        if _original_excepthook is not None:
            _original_excepthook(exc_type, exc_value, exc_tb)

    def _threading_excepthook(self, args: threading.ExceptHookArgs) -> None:
        """线程异常钩子 (Python 3.8+)

        捕获子线程中未处理的异常。

        Args:
            args: threading.ExceptHookArgs 包含异常信息
        """
        exc_type = args.exc_type
        exc_value = args.exc_value
        exc_tb = args.exc_traceback
        thread = args.thread

        thread_name = thread.name if thread else "Unknown Thread"
        thread_id = thread.ident if thread else "Unknown ID"

        context = f"Thread '{thread_name}' (ID: {thread_id})"
        self.handle_exception(exc_type, exc_value, exc_tb, context=context)

        # 调用原始钩子（如果有）
        global _original_threading_excepthook
        if _original_threading_excepthook is not None:
            _original_threading_excepthook(args)

    def _async_exception_handler(self, _loop: asyncio.AbstractEventLoop, context: dict[str, Any]) -> None:
        """异步异常处理器

        处理 asyncio 中未捕获的异常。

        Args:
            loop: 事件循环
            context: 异常上下文字典
        """
        exception = context.get("exception")
        message = context.get("message", "Unknown asyncio exception")
        source_traceback = context.get("source_traceback")
        handle = context.get("handle")
        future = context.get("future")

        # 构建详细的上下文信息
        context_lines = [f"\n{'=' * 60}", "ASYNCIO UNHANDLED EXCEPTION", f"{'=' * 60}"]
        context_lines.append(f"Message: {message}")

        if handle:
            context_lines.append(f"Callback: {handle._callback}")

        if future:
            context_lines.append(f"Future: {future}")

        if source_traceback:
            context_lines.append("\n--- Source Traceback ---")
            context_lines.extend(source_traceback.format())

        if exception:
            exc_type = type(exception)
            exc_tb = exception.__traceback__

            # 复用我们的异常格式化方法
            exception_info = self._format_exception_info(exc_type, exception, exc_tb, "Asyncio Task")
            context_lines.append(exception_info)
        else:
            context_lines.append(f"{'=' * 60}\n")

        self.logger.error("\n".join(context_lines))


class ErrorFormatter(logging.Formatter):
    """Custom formatter that properly handles exception tracebacks.

    The standard Python logging Formatter has problematic behavior:
    1. It applies the format string (which may include %(exc_text)s)
    2. THEN it checks if record.exc_text exists and appends it AGAIN!

    Solution:
    - Store the formatted traceback
    - Clear BOTH exc_info and exc_text before calling parent
    - Use a marker that gets replaced with the actual traceback
    - Restore values after formatting to avoid side effects
    """

    # Use a unique marker that won't appear in normal log messages
    TRACEBACK_MARKER = "__TRACEBACK_PLACEHOLDER__"

    def format(self, record: logging.LogRecord) -> str:
        # Store the traceback and original values
        traceback_text = None
        original_exc_info = record.exc_info
        original_exc_text = record.exc_text

        if record.exc_info:
            traceback_text = self.formatException(record.exc_info)

        # CRITICAL: Clear BOTH exc_info AND exc_text BEFORE calling parent
        # to prevent parent from appending the traceback
        record.exc_info = None
        record.exc_text = ""

        # Call parent's format() - nothing appended since exc_info is None and exc_text is empty
        formatted = super().format(record)

        # Restore original values after formatting (to avoid mutating the record)
        record.exc_info = original_exc_info
        record.exc_text = original_exc_text

        # Manually insert the traceback in the right place
        if traceback_text:
            # The format string has "====== Exception Trace ======\n" followed by %(exc_text)s
            # Since exc_text was empty, this becomes "====== Exception Trace ======\n\n"
            # Replace this with the actual traceback
            formatted = formatted.replace(
                "====== Exception Trace ======\n\n============================",
                f"====== Exception Trace ======\n{traceback_text}\n============================",
            )

        return formatted


def setup_tui_logging(
    workspace_path: Path,
    verbose: bool = False,
    log_to_file: bool = True,
    max_file_size: int = 10 * 1024 * 1024,  # 10 MB
    backup_count: int = 5,
    enable_global_exception_handler: bool = True,
) -> logging.Logger:
    """配置 TUI 完整日志系统（Phase 2）

    这是 TUI 日志配置的第二阶段，在 workspace 初始化后调用。
    此函数会完全替换 Phase 1 的早期日志配置（来自 __main__.py）。

    Args:
        workspace_path: 工作区路径（用于确定日志文件位置）
        verbose: 是否启用 DEBUG 级别（默认 INFO）
        log_to_file: 是否启用文件日志（默认 True）
        max_file_size: 单个日志文件最大大小（字节，默认 10MB）
        backup_count: 保留的日志备份文件数量（默认 5）
        enable_global_exception_handler: 是否启用全局异常处理器（默认 True）

    Returns:
        配置好的 root logger

    Raises:
        OSError: 如果无法创建日志目录（会被捕获并继续使用控制台日志）

    Phase 2 Configuration:
        --------------------
        1. 清除所有现有的 handlers（移除 Phase 1 配置）
        2. 添加 UTF-8 控制台处理器（带敏感信息过滤）
        3. 添加文件日志处理器（如果 log_to_file=True）
           - 主日志文件：所有级别
           - 错误日志文件：仅 ERROR 及以上
        4. 添加上下文追踪（session_id, message_id）
        5. 安装全局异常处理器（如果 enable_global_exception_handler=True）
           - 捕获主线程未处理异常 (sys.excepthook)
           - 捕获子线程异常 (threading.excepthook)
           - 捕获异步异常 (asyncio exception handler)
           - 捕获所有 BaseException 子类

    File Path Selection:
        ------------------
        - 如果 workspace_path 存在且可写：workspace/.dawei/logs/
        - 否则：DAWEI_HOME/logs/tui/（集中式日志）

    Examples:
        >>> from pathlib import Path
        >>> from dawei.logg.tui_logging import setup_tui_logging
        >>>
        >>> # 基本使用（包含全局异常处理器）
        >>> setup_tui_logging(Path("./my-workspace"))
        >>>
        >>> # 启用详细日志
        >>> setup_tui_logging(Path("./my-workspace"), verbose=True)
        >>>
        >>> # 禁用全局异常处理器
        >>> setup_tui_logging(Path("./my-workspace"), enable_global_exception_handler=False)

    """
    # 获取 root logger
    root_logger = logging.getLogger()
    root_logger.handlers.clear()  # 清除现有处理器

    # 设置日志级别
    level = logging.DEBUG if verbose else logging.INFO
    root_logger.setLevel(level)

    # 1. 控制台处理器（UTF-8 + 敏感信息过滤）
    console_handler = UTF8StreamHandler()
    console_handler.setLevel(level)
    console_formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(console_formatter)

    # 添加敏感信息过滤器到控制台
    sensitive_filter = SensitiveInfoFilter(max_length=500)
    console_handler.addFilter(sensitive_filter)

    root_logger.addHandler(console_handler)

    # 2. 文件日志处理器（如果启用）
    if log_to_file:
        try:
            # 使用统一的日志路径配置
            main_log_file = get_tui_log_path(workspace_path)
            error_log_file = get_tui_error_log_path(workspace_path)

            # 使用 RotatingFileHandler 进行日志轮转
            from logging.handlers import RotatingFileHandler

            # 主日志文件（所有级别）
            file_handler = RotatingFileHandler(
                filename=str(main_log_file),
                maxBytes=max_file_size,
                backupCount=backup_count,
                encoding="utf-8",
            )
            file_handler.setLevel(level)

            # 文件日志格式（包含上下文信息）
            file_formatter = logging.Formatter(
                "%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - [session:%(session_id)s] - [message:%(message_id)s] - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            file_handler.setFormatter(file_formatter)

            # 添加上下文过滤器
            context_filter = ContextFilter()
            file_handler.addFilter(context_filter)

            # 添加敏感信息过滤器
            file_sensitive_filter = SensitiveInfoFilter(max_length=1000)
            file_handler.addFilter(file_sensitive_filter)

            root_logger.addHandler(file_handler)

            # 3. 错误日志文件（仅 ERROR 及以上）
            error_handler = RotatingFileHandler(
                filename=str(error_log_file),
                maxBytes=max_file_size,
                backupCount=backup_count,
                encoding="utf-8",
            )
            error_handler.setLevel(logging.ERROR)

            # 错误日志格式（包含完整堆栈）- 使用自定义 ErrorFormatter
            error_formatter = ErrorFormatter(
                "%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - [session:%(session_id)s] - [message:%(message_id)s] - %(message)s\n====== Exception Trace ======\n%(exc_text)s\n============================",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            error_handler.setFormatter(error_formatter)

            # 添加上下文过滤器
            error_handler.addFilter(context_filter)
            # 添加敏感信息过滤器（使用更大的限制以保留完整堆栈跟踪）
            # 错误日志需要完整的堆栈跟踪，所以不限制长度
            error_sensitive_filter = SensitiveInfoFilter(max_length=1000000)
            error_handler.addFilter(error_sensitive_filter)

            root_logger.addHandler(error_handler)

        except (OSError, PermissionError) as e:
            # 如果无法创建日志文件，仅输出到控制台
            root_logger.warning(f"Failed to setup file logging: {e}")

    # 5. 安装全局异常处理器（捕获所有类型的异常）
    if enable_global_exception_handler:
        try:
            exception_handler = GlobalExceptionHandler(root_logger)
            exception_handler.install_hooks()
            root_logger.info("✓ Global exception handler installed - ALL exception types will be logged")
            root_logger.info("  - Capturing: sys.excepthook (main thread)")
            root_logger.info("  - Capturing: threading.excepthook (child threads)")
            root_logger.info("  - Capturing: asyncio exception handler (async tasks)")
            root_logger.info("  - Capturing: All BaseException subclasses")
        except Exception as e:
            # 如果异常处理器安装失败，记录警告但继续
            root_logger.warning(f"Failed to install global exception handler: {e}")

    return root_logger


def get_tui_logger(name: str) -> logging.Logger:
    """获取 TUI 模块的专用 logger

    Args:
        name: 模块名称（通常使用 __name__）

    Returns:
        Logger 实例

    Examples:
        >>> from dawei.logg.tui_logging import get_tui_logger
        >>> logger = get_tui_logger(__name__)
        >>> logger.info("TUI started")
    """
    return logging.getLogger(name)


class TUILoggingContext:
    """TUI 日志上下文管理器

    用于临时设置日志上下文（session_id、message_id）。

    Examples:
        >>> with TUILoggingContext(session_id="session-123", message_id="msg-456"):
        ...     logger.info("This log will have session and message IDs")
    """

    def __init__(
        self,
        session_id: str | None = None,
        message_id: str | None = None,
        user_id: str | None = None,
    ):
        from dawei.core.local_context import set_local_context

        self.session_id = session_id
        self.message_id = message_id
        self.user_id = user_id
        self._set_context = set_local_context

    def __enter__(self):
        if self.session_id or self.message_id or self.user_id:
            self._set_context(
                user_id=self.user_id,
                session_id=self.session_id,
                message_id=self.message_id,
            )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # 清除上下文（恢复默认值）
        if self.session_id or self.message_id or self.user_id:
            self._set_context(
                user_id=None,
                session_id=None,
                message_id=None,
            )
        return False


def log_exception(
    logger: logging.Logger,
    exception: Exception,
    message: str = "An error occurred",
    level: int = logging.ERROR,
) -> None:
    """记录异常日志（包含完整堆栈）

    Args:
        logger: Logger 实例
        exception: 异常对象
        message: 附加消息
        level: 日志级别（默认 ERROR）

    Examples:
        >>> try:
        ...     risky_operation()
        ... except Exception as e:
        ...     log_exception(logger, e, "Failed to process message")
    """
    logger.log(
        level,
        f"{message}: {type(exception).__name__}: {exception!s}",
        exc_info=exception,
    )


# 便捷导出
__all__ = [
    "setup_tui_logging",
    "get_tui_logger",
    "TUILoggingContext",
    "log_exception",
    "GlobalExceptionHandler",  # 全局异常处理器
]
