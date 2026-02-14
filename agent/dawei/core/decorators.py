# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""统一错误处理装饰器模块
提供简化的错误处理装饰器，用于替代代码中的try块
"""

import asyncio
import functools
import logging
import time
from collections.abc import Callable
from typing import Any

from .error_handler import get_error_handler
from .errors import ErrorCategory, ErrorContext, ErrorSeverity, RecoveryStrategy


class SafeOperationConfig:
    """安全操作配置类"""

    def __init__(
        self,
        component: str,
        operation: str | None = None,
        category: ErrorCategory | None = None,
        severity: ErrorSeverity | None = None,
        recovery_strategy: RecoveryStrategy | None = None,
        fallback_value: Any = None,
        log_errors: bool = True,
        log_level: str = "ERROR",
        retry_count: int = 0,
        retry_delay: float = 1.0,
        catch_exceptions: list[type[Exception]] | None = None,
        ignore_exceptions: list[type[Exception]] | None = None,
    ):
        self.component = component
        self.operation = operation
        self.category = category
        self.severity = severity
        self.recovery_strategy = recovery_strategy
        self.fallback_value = fallback_value
        self.log_errors = log_errors
        self.log_level = log_level
        self.retry_count = retry_count
        self.retry_delay = retry_delay
        self.catch_exceptions = catch_exceptions
        self.ignore_exceptions = ignore_exceptions or []


def safe_operation(
    component: str,
    operation: str | None = None,
    category: ErrorCategory | None = None,
    severity: ErrorSeverity | None = None,
    recovery_strategy: RecoveryStrategy | None = None,
    fallback_value: Any = None,
    log_errors: bool = True,
    log_level: str = "ERROR",
    retry_count: int = 0,
    retry_delay: float = 1.0,
    catch_exceptions: list[type[Exception]] | None = None,
    ignore_exceptions: list[type[Exception]] | None = None,
) -> Callable:
    """安全操作装饰器，用于替代简单的try块

    Args:
        component: 组件名称
        operation: 操作名称，默认为函数名
        category: 错误分类
        severity: 错误严重程度
        recovery_strategy: 恢复策略
        fallback_value: 异常时的默认返回值
        log_errors: 是否记录错误日志
        log_level: 日志级别
        retry_count: 重试次数
        retry_delay: 重试延迟（秒）
        catch_exceptions: 要捕获的异常类型列表，None表示捕获所有异常
        ignore_exceptions: 要忽略的异常类型列表

    Returns:
        装饰后的函数

    """
    config = SafeOperationConfig(
        component=component,
        operation=operation,
        category=category,
        severity=severity,
        recovery_strategy=recovery_strategy,
        fallback_value=fallback_value,
        log_errors=log_errors,
        log_level=log_level,
        retry_count=retry_count,
        retry_delay=retry_delay,
        catch_exceptions=catch_exceptions,
        ignore_exceptions=ignore_exceptions,
    )

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            return await _execute_with_error_handling_async(func, args, kwargs, config)

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs) -> Any:
            return _execute_with_error_handling_sync(func, args, kwargs, config)

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return decorator


async def _execute_with_error_handling_async(
    func: Callable,
    args: tuple,
    kwargs: dict[str, Any],
    config: SafeOperationConfig,
) -> Any:
    logger = logging.getLogger(__name__)
    operation_name = config.operation or func.__name__

    def should_catch_exception(exception: Exception) -> bool:
        """判断是否应该捕获该异常"""
        for ignore_type in config.ignore_exceptions:
            if isinstance(exception, ignore_type):
                return False
        if config.catch_exceptions is None:
            return True
        return any(isinstance(exception, catch_type) for catch_type in config.catch_exceptions)

    last_exception = None
    for attempt in range(config.retry_count + 1):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            if not should_catch_exception(e):
                raise

            if config.log_errors:
                log_message = f"Error in {config.component}.{operation_name}: {e.__class__.__name__}: {e!s}"
                getattr(logger, config.log_level.lower())(log_message)

            error_context = ErrorContext(
                component=config.component,
                operation=operation_name,
                args=args,
                kwargs=kwargs,
            )
            error_handler = get_error_handler()
            classified_error = error_handler.classify_error(e, error_context)

            if config.category:
                classified_error.category = config.category
            if config.severity:
                classified_error.severity = config.severity
            if config.recovery_strategy:
                classified_error.recovery_strategy = config.recovery_strategy

            last_exception = e
            if attempt < config.retry_count:
                if config.log_errors:
                    logger.warning(
                        f"Retrying {config.component}.{operation_name} after {config.retry_delay}s (attempt {attempt + 1}/{config.retry_count})",
                    )
                await asyncio.sleep(config.retry_delay)

    if last_exception:
        # 如果有fallback值，返回它；否则重新抛出异常
        if config.fallback_value is not None:
            return config.fallback_value
        raise last_exception
    return config.fallback_value


def _execute_with_error_handling_sync(
    func: Callable,
    args: tuple,
    kwargs: dict[str, Any],
    config: SafeOperationConfig,
) -> Any:
    logger = logging.getLogger(__name__)
    operation_name = config.operation or func.__name__

    def should_catch_exception(exception: Exception) -> bool:
        """判断是否应该捕获该异常"""
        for ignore_type in config.ignore_exceptions:
            if isinstance(exception, ignore_type):
                return False
        if config.catch_exceptions is None:
            return True
        return any(isinstance(exception, catch_type) for catch_type in config.catch_exceptions)

    last_exception = None
    for attempt in range(config.retry_count + 1):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if not should_catch_exception(e):
                raise

            if config.log_errors:
                log_message = f"Error in {config.component}.{operation_name}: {e.__class__.__name__}: {e!s}"
                getattr(logger, config.log_level.lower())(log_message)

            error_context = ErrorContext(
                component=config.component,
                operation=operation_name,
                args=args,
                kwargs=kwargs,
            )
            error_handler = get_error_handler()
            classified_error = error_handler.classify_error(e, error_context)

            if config.category:
                classified_error.category = config.category
            if config.severity:
                classified_error.severity = config.severity
            if config.recovery_strategy:
                classified_error.recovery_strategy = config.recovery_strategy

            last_exception = e
            if attempt < config.retry_count:
                if config.log_errors:
                    logger.warning(
                        f"Retrying {config.component}.{operation_name} after {config.retry_delay}s (attempt {attempt + 1}/{config.retry_count})",
                    )
                time.sleep(config.retry_delay)

    if last_exception:
        # 如果有fallback值，返回它；否则重新抛出异常
        if config.fallback_value is not None:
            return config.fallback_value
        raise last_exception
    return config.fallback_value


def _execute_with_error_handling(
    func: Callable,
    args: tuple,
    kwargs: dict[str, Any],
    config: SafeOperationConfig,
    is_async: bool = False,
) -> Any:
    """统一的错误处理执行函数

    Args:
        func: 要执行的函数
        args: 位置参数
        kwargs: 关键字参数
        config: 错误处理配置
        is_async: 是否为异步函数

    Returns:
        函数执行结果或fallback值

    """
    if is_async:
        return _execute_with_error_handling_async(func, args, kwargs, config)
    return _execute_with_error_handling_sync(func, args, kwargs, config)


# 便捷装饰器函数
def safe_tool_operation(
    tool_name: str,
    fallback_value: Any = None,
    log_errors: bool = True,
) -> Callable:
    """工具操作的安全装饰器

    Args:
        tool_name: 工具名称
        fallback_value: 异常时的默认返回值
        log_errors: 是否记录错误日志

    Returns:
        装饰后的函数

    """
    return safe_operation(
        component="tools",
        operation=tool_name,
        category=ErrorCategory.BUSINESS,
        severity=ErrorSeverity.MEDIUM,
        recovery_strategy=RecoveryStrategy.FALLBACK,
        fallback_value=fallback_value,
        log_errors=log_errors,
    )


def safe_system_operation(
    operation: str,
    fallback_value: Any = None,
    log_errors: bool = True,
) -> Callable:
    """系统操作的安全装饰器

    Args:
        operation: 操作名称
        fallback_value: 异常时的默认返回值
        log_errors: 是否记录错误日志

    Returns:
        装饰后的函数

    """
    return safe_operation(
        component="system",
        operation=operation,
        category=ErrorCategory.SYSTEM,
        severity=ErrorSeverity.HIGH,
        recovery_strategy=RecoveryStrategy.RETRY,
        fallback_value=fallback_value,
        log_errors=log_errors,
        retry_count=2,
    )


def safe_integration_operation(
    service: str,
    fallback_value: Any = None,
    log_errors: bool = True,
) -> Callable:
    """集成操作的安全装饰器

    Args:
        service: 服务名称
        fallback_value: 异常时的默认返回值
        log_errors: 是否记录错误日志

    Returns:
        装饰后的函数

    """
    return safe_operation(
        component="integration",
        operation=service,
        category=ErrorCategory.INTEGRATION,
        severity=ErrorSeverity.HIGH,
        recovery_strategy=RecoveryStrategy.RETRY,
        fallback_value=fallback_value,
        log_errors=log_errors,
        retry_count=3,
    )


def safe_user_operation(
    operation: str,
    fallback_value: Any = None,
    log_errors: bool = True,
) -> Callable:
    """用户操作的安全装饰器

    Args:
        operation: 操作名称
        fallback_value: 异常时的默认返回值
        log_errors: 是否记录错误日志

    Returns:
        装饰后的函数

    """
    return safe_operation(
        component="user",
        operation=operation,
        category=ErrorCategory.USER,
        severity=ErrorSeverity.LOW,
        recovery_strategy=RecoveryStrategy.NONE,
        fallback_value=fallback_value,
        log_errors=log_errors,
    )


# 批量装饰器应用工具
class TryBlockAnalyzer:
    """Try块分析器，用于识别可以替换的try块模式"""

    @staticmethod
    def analyze_file_for_try_blocks(file_path: str) -> dict[str, list[dict[str, Any]]]:
        """分析文件中的try块模式

        Args:
            file_path: 文件路径

        Returns:
            分析结果，包含不同类型的try块模式

        """
        import ast
        from pathlib import Path

        if not Path(file_path).exists():
            return {}

        with Path(file_path).open(encoding="utf-8") as f:
            content = f.read()

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return {"syntax_errors": [{"line": 0, "message": "Invalid syntax"}]}

        patterns = {
            "simple_logging": [],  # 简单日志记录模式
            "fallback_return": [],  # 返回默认值模式
            "resource_cleanup": [],  # 资源清理模式
            "complex_handling": [],  # 复杂处理模式
            "nested_try": [],  # 嵌套try块
        }

        class TryBlockVisitor(ast.NodeVisitor):
            def visit_Try(self, node):
                # 分析try块模式
                pattern_info = {
                    "line": node.lineno,
                    "handlers": len(node.handlers),
                    "has_else": bool(node.orelse),
                    "has_finally": bool(node.finalbody),
                }

                # 检查是否为简单日志记录模式
                if len(node.handlers) == 1 and isinstance(node.handlers[0].type, ast.Name) and node.handlers[0].type.id == "Exception" and len(node.handlers[0].body) == 1 and isinstance(node.handlers[0].body[0], ast.Expr) and isinstance(node.handlers[0].body[0].value, ast.Call):
                    patterns["simple_logging"].append(pattern_info)

                # 检查是否为返回默认值模式
                elif len(node.handlers) == 1 and any(isinstance(stmt, ast.Return) and isinstance(stmt.value, (ast.Constant, ast.NameConstant)) for stmt in node.handlers[0].body):
                    patterns["fallback_return"].append(pattern_info)

                # 检查是否为资源清理模式
                elif node.finalbody:
                    patterns["resource_cleanup"].append(pattern_info)

                # 检查是否为复杂处理模式
                elif len(node.handlers) > 1 or len(node.handlers[0].body) > 2:
                    patterns["complex_handling"].append(pattern_info)

                # 检查嵌套try块
                for child in ast.walk(node):
                    if isinstance(child, ast.Try) and child != node:
                        patterns["nested_try"].append(pattern_info)
                        break

                self.generic_visit(node)

        visitor = TryBlockVisitor()
        visitor.visit(tree)

        return patterns

    @staticmethod
    def suggest_decorator_for_pattern(pattern_type: str, context: dict[str, Any]) -> str | None:
        """为特定模式建议合适的装饰器

        Args:
            pattern_type: 模式类型
            context: 上下文信息

        Returns:
            建议的装饰器名称

        """
        suggestions = {
            "simple_logging": "safe_operation",
            "fallback_return": "safe_operation",
            "resource_cleanup": "safe_operation",  # 需要特殊处理
            "complex_handling": None,  # 保持原有try块
            "nested_try": None,  # 保持原有try块
        }

        return suggestions.get(pattern_type)
