# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""输入验证装饰器和辅助函数

遵循 Fast Fail 原则，在函数入口处进行验证
"""

import functools
from collections.abc import Callable
from inspect import signature
from typing import Any, Union, get_type_hints

from .exceptions import MissingRequiredFieldError, ValidationError

# ==============================================================================
# 验证装饰器
# ==============================================================================


def validate_args(func: Callable) -> Callable:
    """装饰器：验证函数参数

    使用类型提示进行基本验证
    """
    hints = get_type_hints(func)
    sig = signature(func)

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # 绑定参数
        bound_args = sig.bind(*args, **kwargs)
        bound_args.apply_defaults()

        # 验证每个参数
        for name, value in bound_args.arguments.items():
            if name in hints:
                expected_type = hints[name]
                _validate_type(name, value, expected_type)

        return func(*args, **kwargs)

    return wrapper


def validate_strings(*param_names: str) -> Callable:
    """装饰器：验证指定参数为非空字符串

    Usage:
        @validate_strings('task_id', 'workspace_path')
        def some_method(task_id: str, workspace_path: str):
            ...
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            sig = signature(func)
            bound_args = sig.bind(*args, **kwargs)
            bound_args.apply_defaults()

            for param_name in param_names:
                if param_name in bound_args.arguments:
                    value = bound_args.arguments[param_name]
                    if not isinstance(value, str) or not value.strip():
                        raise ValidationError(param_name, value, "must be a non-empty string")

            return func(*args, **kwargs)

        return wrapper

    return decorator


def validate_positive(*param_names: str) -> Callable:
    """装饰器：验证指定参数为正数

    Usage:
        @validate_positive('timeout', 'max_retries')
        def some_method(timeout: int, max_retries: int):
            ...
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            sig = signature(func)
            bound_args = sig.bind(*args, **kwargs)
            bound_args.apply_defaults()

            for param_name in param_names:
                if param_name in bound_args.arguments:
                    value = bound_args.arguments[param_name]
                    if not isinstance(value, (int, float)) or value <= 0:
                        raise ValidationError(param_name, value, "must be a positive number")

            return func(*args, **kwargs)

        return wrapper

    return decorator


def validate_not_none(*param_names: str) -> Callable:
    """装饰器：验证指定参数不为 None

    Usage:
        @validate_not_none('agent', 'workspace')
        def some_method(agent, workspace):
            ...
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            sig = signature(func)
            bound_args = sig.bind(*args, **kwargs)
            bound_args.apply_defaults()

            for param_name in param_names:
                if param_name in bound_args.arguments:
                    value = bound_args.arguments[param_name]
                    if value is None:
                        raise MissingRequiredFieldError(param_name, None, "cannot be None")

            return func(*args, **kwargs)

        return wrapper

    return decorator


def require_fields(*fields: str) -> Callable:
    """装饰器：验证字典或对象包含必需字段

    Usage:
        @require_fields('task_id', 'workspace_id')
        def some_method(data: dict):
            ...
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            sig = signature(func)
            bound_args = sig.bind(*args, **kwargs)
            bound_args.apply_defaults()

            # 获取第一个参数（假设是需要验证的数据）
            if bound_args.arguments:
                first_param = next(iter(bound_args.arguments.values()))
                if isinstance(first_param, dict):
                    for field in fields:
                        if field not in first_param:
                            raise MissingRequiredFieldError(field, None, "missing in data dict")

            return func(*args, **kwargs)

        return wrapper

    return decorator


# ==============================================================================
# 验证辅助函数
# ==============================================================================


def _validate_type(param_name: str, value: Any, expected_type: type) -> None:
    """验证参数类型"""
    if value is None:
        return  # None 由 @validate_not_none 处理

    # 处理 Optional 类型
    if hasattr(expected_type, "__origin__") and expected_type.__origin__ is Union:
        # Optional[X] 等价于 Union[X, None]
        args = expected_type.__args__
        if type(None) in args and value is None:
            return
        # 尝试非 None 类型
        non_none_types = [t for t in args if t is not type(None)]
        if non_none_types:
            expected_type = non_none_types[0]

    # 基本类型检查
    if not isinstance(value, expected_type):
        raise ValidationError(
            param_name,
            value,
            f"expected type {expected_type.__name__}, got {type(value).__name__}",
        )


def require_non_empty_string(value: Any, field_name: str = "value") -> str:
    """要求值为非空字符串

    Args:
        value: 要验证的值
        field_name: 字段名称（用于错误消息）

    Returns:
        验证通过后的字符串值

    Raises:
        ValidationError: 如果值为空或不是字符串

    """
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(field_name, value, "must be a non-empty string")
    return value


def validate_string_not_empty(value: Any, field_name: str = "value") -> str:
    """验证字符串不为空 (validate_string_not_empty 的别名)

    Args:
        value: 要验证的值
        field_name: 字段名称（用于错误消息）

    Returns:
        验证通过后的字符串值

    Raises:
        ValidationError: 如果值为空或不是字符串

    """
    return require_non_empty_string(value, field_name)


def require_positive_number(value: Any, field_name: str = "value") -> float:
    """要求值为正数

    Args:
        value: 要验证的值
        field_name: 字段名称（用于错误消息）

    Returns:
        验证通过后的数值

    Raises:
        ValidationError: 如果值不是正数

    """
    if not isinstance(value, (int, float)) or value <= 0:
        raise ValidationError(field_name, value, "must be a positive number")
    return float(value)


def require_non_negative(value: Any, field_name: str = "value") -> float:
    """要求值为非负数

    Args:
        value: 要验证的值
        field_name: 字段名称（用于错误消息）

    Returns:
        验证通过后的数值

    Raises:
        ValidationError: 如果值是负数

    """
    if not isinstance(value, (int, float)) or value < 0:
        raise ValidationError(field_name, value, "must be non-negative")
    return float(value)


def require_instance(value: Any, expected_type: type, field_name: str = "value") -> Any:
    """要求值是指定类型的实例

    Args:
        value: 要验证的值
        expected_type: 期望的类型
        field_name: 字段名称（用于错误消息）

    Returns:
        验证通过后的值

    Raises:
        ValidationError: 如果值不是指定类型

    """
    if not isinstance(value, expected_type):
        raise ValidationError(field_name, value, f"must be instance of {expected_type.__name__}")
    return value


def require_in_range(
    value: Any,
    min_value: float | None = None,
    max_value: float | None = None,
    field_name: str = "value",
) -> float:
    """要求值在指定范围内

    Args:
        value: 要验证的值
        min_value: 最小值（可选）
        max_value: 最大值（可选）
        field_name: 字段名称（用于错误消息）

    Returns:
        验证通过后的数值

    Raises:
        ValidationError: 如果值不在范围内

    """
    if not isinstance(value, (int, float)):
        raise ValidationError(field_name, value, "must be a number")

    value_float = float(value)

    if min_value is not None and value_float < min_value:
        raise ValidationError(field_name, value, f"must be >= {min_value}")

    if max_value is not None and value_float > max_value:
        raise ValidationError(field_name, value, f"must be <= {max_value}")

    return value_float


def check_condition(
    condition: bool,
    error_message: str,
    field_name: str = "value",
    value: Any = None,
) -> None:
    """检查条件，如果不满足则抛出异常

    Args:
        condition: 要检查的条件
        error_message: 错误消息
        field_name: 字段名称（可选）
        value: 字段值（可选）

    Raises:
        ValidationError: 如果条件不满足

    """
    if not condition:
        raise ValidationError(field_name, value, error_message)


# ==============================================================================
# Early Return 辅助函数
# ==============================================================================


def fail_fast(error: Exception) -> None:
    """Fast Fail：立即抛出异常

    用于在条件检查失败时快速失败

    Args:
        error: 要抛出的异常

    Raises:
        Exception: 传入的异常

    """
    raise error


def assert_not_none(value: Any, field_name: str = "value") -> Any:
    """断言值不为 None

    Args:
        value: 要检查的值
        field_name: 字段名称

    Returns:
        原值（如果不为 None）

    Raises:
        MissingRequiredFieldError: 如果值为 None

    """
    if value is None:
        raise MissingRequiredFieldError(field_name, None, "cannot be None")
    return value


def assert_condition(
    condition: bool,
    error_message: str,
    exception_type: type[Exception] = ValidationError,
    field_name: str = "value",
) -> None:
    """断言条件成立

    Args:
        condition: 要检查的条件
        error_message: 错误消息
        exception_type: 异常类型
        field_name: 字段名称（可选）

    Raises:
        Exception: 如果条件不成立

    """
    if not condition:
        if exception_type is ValidationError:
            raise exception_type(field_name, None, error_message)
        raise exception_type(error_message)


# =============================================================================
# 通用验证辅助函数
# =============================================================================


def validate_dict_key(data: dict, key: str, field_name: str = "data") -> Any:
    """验证字典包含必需的key"""
    if not isinstance(data, dict):
        raise ValidationError(field_name=field_name, value=data, reason=f"must be a dict, got {type(data).__name__}")
    if key not in data:
        raise ValidationError(field_name=field_name, value=data, reason=f"missing required key '{key}'")
    return data[key]


def safe_execute(func):
    """装饰器：安全执行函数，捕获并重新抛出异常"""

    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except (ValidationError, ValueError, TypeError, KeyError, AttributeError):
            raise
        except Exception as e:
            import logging

            logger = logging.getLogger(func.__name__)
            logger.error(f"Unexpected error in {func.__name__}: {e}", exc_info=True)
            raise type(e)(f"Unexpected error in {func.__name__}: {e}") from e

    return wrapper
