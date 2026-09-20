# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""统一异常处理模块

提供装饰器和辅助函数,确保所有异常都:
1. 记录完整的堆栈跟踪 (exc_info=True)
2. 遵循 fast fail 原则
3. 精确捕获异常类型
"""

import asyncio
import functools
import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


def handle_exceptions(
    *exception_types: type[Exception],
    reraise: bool = True,
    default_return: Any = None,
    log_level: str = "error",
    component: str | None = None,
    operation: str | None = None,
):
    """统一异常处理装饰器

    WARNING: Use specific exception types whenever possible.
    Only use bare @handle_exceptions() without exception_types for:
    1. External user callbacks that should never crash the system
    2. Top-level main entry points where all errors must be logged
    3. Rare cases where graceful degradation is absolutely required

    Args:
        exception_types: 要捕获的异常类型,如果未指定则捕获所有 Exception
        reraise: 是否重新抛出异常 (默认 True,遵循 fast fail 原则)
        default_return: 发生异常且不重新抛出时的默认返回值
        log_level: 日志级别 (error, warning, critical)
        component: 组件名称,用于日志上下文
        operation: 操作名称,用于日志上下文

    Examples:
        # GOOD: 捕获特定异常并重新抛出 (默认行为)
        @handle_exceptions(ValueError, TypeError)
        def my_function():
            ...

        # AVOID: 不带异常类型参数会掩盖所有异常 (仅用于用户回调)
        @handle_exceptions()  # BAD unless wrapping user callbacks
        def my_function():
            ...

        # GOOD: 捕获特定异常,不重新抛出 (谨慎使用,可能掩盖问题)
        @handle_exceptions(ValueError, reraise=False, default_return=None)
        def my_function():
            ...

        # GOOD: 捕获所有异常,记录上下文 (用于main入口点)
        @handle_exceptions(component="agent", operation="initialize")
        async def my_async_function():
            ...

    """

    def decorator(func: Callable) -> Callable:
        # 确定异步还是同步函数
        is_async = asyncio.iscoroutinefunction(func)

        # 构建日志上下文
        log_context = {}
        if component:
            log_context["component"] = component
        if operation:
            log_context["operation"] = operation
        if not log_context:
            log_context["function"] = func.__name__

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except exception_types or Exception as e:
                # 使用指定的日志级别
                log_func = getattr(logger, log_level)

                # 记录异常,包含完整堆栈跟踪
                if log_context:
                    log_func(
                        f"Error in {func.__name__}: {e}",
                        exc_info=True,
                        context=log_context,
                    )
                else:
                    log_func(f"Error in {func.__name__}: {e}", exc_info=True)

                if reraise:
                    raise
                return default_return

            except Exception as e:
                # 捕获未预期的异常 (总是记录并重新抛出)
                logger.critical(
                    f"Unexpected error in {func.__name__}: {e}",
                    exc_info=True,
                    context=log_context,
                )
                raise

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except exception_types or Exception as e:
                log_func = getattr(logger, log_level)

                if log_context:
                    log_func(
                        f"Error in {func.__name__}: {e}",
                        exc_info=True,
                        context=log_context,
                    )
                else:
                    log_func(f"Error in {func.__name__}: {e}", exc_info=True)

                if reraise:
                    raise
                return default_return

            except Exception as e:
                logger.critical(
                    f"Unexpected error in {func.__name__}: {e}",
                    exc_info=True,
                    context=log_context,
                )
                raise

        return async_wrapper if is_async else sync_wrapper

    return decorator


def safe_operation(
    default_return: Any = None,
    log_level: str = "warning",
    component: str | None = None,
    operation: str | None = None,
):
    """安全操作装饰器 (别名,用于向后兼容)

    WARNING: This decorator sets reraise=False by default, which may mask errors.
    Only use this for:
    1. User-provided callbacks that should never crash the system
    2. Background cleanup tasks that must continue running
    3. Optional/failure-tolerant operations with clear fallback behavior

    For most code, use @handle_exceptions() with specific types instead.

    注意: 默认 reraise=False,可能掩盖问题,应谨慎使用

    Args:
        default_return: 发生异常时的默认返回值
        log_level: 日志级别 (默认 warning)
        component: 组件名称
        operation: 操作名称

    Examples:
        # GOOD: For user callbacks that shouldn't crash the system
        @safe_operation(default_return={}, component="tool_manager", operation="load_config")
        def load_tools():
            ...

        # AVOID: For critical operations that should fail fast
        @safe_operation(default_return=None)  # BAD - masks errors in critical path
        def process_payment():
            ...

    """
    return handle_exceptions(
        reraise=False,  # 注意: 默认不重新抛出
        default_return=default_return,
        log_level=log_level,
        component=component,
        operation=operation,
    )


def log_and_raise(
    exception_types: type[Exception] | tuple,
    message: str,
    component: str | None = None,
    operation: str | None = None,
):
    """记录并重新抛出异常的辅助函数

    Args:
        exception_types: 异常类型
        message: 错误消息
        component: 组件名称
        operation: 操作名称

    Examples:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            log_and_raise(json.JSONDecodeError, "Invalid JSON", component="config_loader")

    """
    log_context = {}
    if component:
        log_context["component"] = component
    if operation:
        log_context["operation"] = operation

    if log_context:
        logger.error(message, exc_info=True, context=log_context)
    else:
        logger.error(message, exc_info=True)

    raise


def log_exception(
    error: Exception,
    message: str,
    log_level: str = "error",
    component: str | None = None,
    operation: str | None = None,
    reraise: bool = True,
):
    """记录异常的辅助函数

    Args:
        error: 异常对象
        message: 错误消息
        log_level: 日志级别
        component: 组件名称
        operation: 操作名称
        reraise: 是否重新抛出异常

    Examples:
        try:
            ...
        except ValueError as e:
            log_exception(e, "Invalid value", component="agent", reraise=True)

    """
    log_context = {}
    if component:
        log_context["component"] = component
    if operation:
        log_context["operation"] = operation

    log_func = getattr(logger, log_level)

    full_message = f"{message}: {error}"
    if log_context:
        log_func(full_message, exc_info=True, context=log_context)
    else:
        log_func(full_message, exc_info=True)

    if reraise:
        raise


# 兼容性别名
safe_system_operation = safe_operation


# 使用示例
if __name__ == "__main__":
    # 示例 1: 捕获特定异常并重新抛出
    @handle_exceptions(ValueError, TypeError, component="example", operation="parse")
    def parse_data(data: str) -> int:
        return int(data)

    # 示例 2: 捕获所有异常,记录并重新抛出
    @handle_exceptions(component="example", operation="load")
    async def load_config(path: str) -> dict:
        import json

        with Path(path).open() as f:
            return json.load(f)

    # 示例 3: 捕获异常但不重新抛出 (谨慎使用)
    @safe_operation(default_return=[], component="example", operation="list_files")
    def list_files_safe():
        raise FileNotFoundError("Not found")

    # 示例 4: 使用 log_and_raise
    def example_function():
        try:
            raise ValueError("Test error")
        except ValueError:
            log_and_raise(ValueError, "Failed to process", component="example")

    # 测试
    try:
        parse_data("invalid")
    except Exception as e:
        print(f"Caught: {e}")
