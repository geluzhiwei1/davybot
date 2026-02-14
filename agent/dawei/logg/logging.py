# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""统一日志记录模块

提供日志记录功能，所有文件日志统一保存在 DAWEI_HOME/logs 目录下
"""

import asyncio
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

# 共享的 UTF-8 流（避免重复创建文件描述符）
_shared_utf8_stream = None


class UTF8StreamHandler(logging.StreamHandler):
    """自定义 StreamHandler，强制使用 UTF-8 编码写入控制台

    适用于 Windows 控制台编码为 GBK 的情况。

    关键改进：使用共享的 UTF-8 流，避免多次调用 os.dup() 导致文件描述符混乱。
    """

    def __init__(self):
        super().__init__()
        self._setup_utf8_stream()

    def _setup_utf8_stream(self):
        """设置 UTF-8 输出流"""
        global _shared_utf8_stream

        if sys.platform == "win32":
            # Windows: 使用共享的 UTF-8 流（避免重复 dup）
            if _shared_utf8_stream is None:
                import io

                # 安全地获取 stderr 的底层 buffer
                # 某些情况下 stderr 可能是 BufferedWriter，没有 buffer 属性
                try:
                    # 尝试获取原始 buffer
                    if hasattr(sys.stderr, "buffer"):
                        base_stream = sys.stderr.buffer
                    else:
                        # 如果 stderr 没有 buffer 属性，直接使用 stderr
                        base_stream = sys.stderr
                except (AttributeError, OSError):
                    # 如果获取失败，使用 stderr 本身
                    base_stream = sys.stderr

                # 创建一个直接写入 stderr 的 UTF-8 文本流
                _shared_utf8_stream = io.TextIOWrapper(
                    base_stream,
                    encoding="utf-8",
                    errors="replace",
                    line_buffering=True,
                )
            self.stream = _shared_utf8_stream
        else:
            # 非 Windows: 使用 stderr
            self.stream = sys.stderr

    def emit(self, record):
        """写入日志记录，强制使用 UTF-8 编码"""
        try:
            msg = self.format(record)
            # 确保 msg 是字符串类型（处理可能的 bytes）
            if isinstance(msg, bytes):
                msg = msg.decode("utf-8", errors="replace")
            # 统一使用字符串写入（流已经是 UTF-8 编码的文本流）
            self.stream.write(msg + "\n")
            self.flush()
        except Exception:
            self.handleError(record)


def _get_utf8_stream():
    """获取支持 UTF-8 的输出流（保持向后兼容）

    注意：此函数现在返回 sys.stderr，实际 UTF-8 处理由 UTF8StreamHandler 完成
    """
    return sys.stderr


class AgenticLogger:
    """Agentic 模块专用日志记录器"""

    def __init__(self, name: str, level: str = "INFO"):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(getattr(logging, level.upper()))

        # 避免重复添加处理器
        if not self.logger.handlers:
            self._setup_handlers()

    def _setup_handlers(self):
        """设置日志处理器"""
        # 控制台处理器（使用 UTF-8 流）
        console_handler = UTF8StreamHandler()
        console_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"),
        )
        self.logger.addHandler(console_handler)

        # 防止日志传播到父 logger（避免重复处理和编码问题）
        self.logger.propagate = False

        # 文件处理器（使用统一的 DAWEI_HOME/logs 路径）
        try:
            from dawei.config.logging_config import get_log_dir

            log_dir = get_log_dir() / "agentic"
            log_dir.mkdir(parents=True, exist_ok=True)

            file_handler = RotatingFileHandler(
                str(log_dir / "agentic.log"),
                maxBytes=10 * 1024 * 1024,  # 10MB
                backupCount=5,
                encoding="utf-8",  # 明确指定 UTF-8 编码
            )
            file_handler.setFormatter(
                logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"),
            )
            self.logger.addHandler(file_handler)
        except Exception as e:
            # 如果无法创建文件日志，仅使用控制台输出
            self.logger.warning(f"Failed to setup file logging: {e}")

    def debug(self, message: str, **kwargs):
        """记录调试信息"""
        self._log(logging.DEBUG, message, **kwargs)

    def info(self, message: str, **kwargs):
        """记录信息"""
        self._log(logging.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs):
        """记录警告"""
        self._log(logging.WARNING, message, **kwargs)

    def error(self, message: str, **kwargs):
        """记录错误"""
        self._log(logging.ERROR, message, **kwargs)

    def critical(self, message: str, **kwargs):
        """记录严重错误"""
        self._log(logging.CRITICAL, message, **kwargs)

    def exception(self, message: str, **kwargs):
        """记录异常（包含堆栈跟踪）"""
        self._log(logging.ERROR, message, exc_info=True, **kwargs)

    def _log(self, level: int, message: str, **kwargs):
        """内部日志记录方法"""
        extra = kwargs.pop("extra", {})
        exc_info = kwargs.pop("exc_info", False)

        # 添加上下文信息
        if kwargs:
            extra.update(kwargs)

        self.logger.log(level, message, extra=extra, exc_info=exc_info)


# 全局日志记录器缓存
_loggers: dict[str, AgenticLogger] = {}


def get_logger(name: str, level: str | None = None) -> AgenticLogger:
    """获取日志记录器实例

    Args:
        name: 日志记录器名称
        level: 日志级别（可选）

    Returns:
        日志记录器实例

    """
    if name not in _loggers:
        log_level = level or os.environ.get("AGENT_LOG_LEVEL", "INFO")
        _loggers[name] = AgenticLogger(name, log_level)

    return _loggers[name]


def set_log_level(level: str):
    """设置全局日志级别

    Args:
        level: 日志级别

    """
    log_level = getattr(logging, level.upper())
    for logger in _loggers.values():
        logger.logger.setLevel(log_level)


# 性能日志装饰器
def log_performance(func_name: str | None = None):
    """性能日志装饰器

    Args:
        func_name: 函数名称（可选）

    """

    def decorator(func):
        import functools
        import time

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            name = func_name or f"{func.__module__}.{func.__name__}"
            logger = get_logger(name)

            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start_time
                # logger.info(f"Function completed",
                #            function=name,
                #            duration=duration,
                #            success=True)
                return result
            except Exception as e:
                duration = time.time() - start_time
                logger.exception(
                    "Function failed",
                    function=name,
                    duration=duration,
                    success=False,
                    error=str(e),
                )
                raise

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            name = func_name or f"{func.__module__}.{func.__name__}"
            logger = get_logger(name)

            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                # logger.info(f"Function completed",
                #            function=name,
                #            duration=duration,
                #            success=True)
                return result
            except Exception as e:
                duration = time.time() - start_time
                logger.exception(
                    "Function failed",
                    function=name,
                    duration=duration,
                    success=False,
                    error=str(e),
                )
                raise

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return decorator


# 错误日志装饰器
def log_errors(func_name: str | None = None):
    """错误日志装饰器

    Args:
        func_name: 函数名称（可选）

    """

    def decorator(func):
        import functools

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            name = func_name or f"{func.__module__}.{func.__name__}"
            logger = get_logger(name)

            try:
                return await func(*args, **kwargs)
            except Exception as e:
                logger.exception(
                    "Function raised exception",
                    function=name,
                    error_type=type(e).__name__,
                    error=str(e),
                )
                raise

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            name = func_name or f"{func.__module__}.{func.__name__}"
            logger = get_logger(name)

            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.exception(
                    "Function raised exception",
                    function=name,
                    error_type=type(e).__name__,
                    error=str(e),
                )
                raise

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return decorator


def clear_logging_context():
    """清除日志上下文。
    注意：此函数已弃用，请使用 dawei.core.context 的相应功能代替。
    为了向后兼容，此函数仍然可用。
    """
    # 由于 contextvars 有默认值，不需要显式清除
