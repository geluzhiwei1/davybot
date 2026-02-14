# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""通用工具函数
提供各种辅助功能
"""

import asyncio
import contextlib
import time
import uuid
from collections.abc import Callable
from functools import wraps
from typing import Any

from dawei.core.decorators import safe_system_operation


def generate_task_id() -> str:
    """生成任务ID

    Returns:
        任务ID

    """
    return str(uuid.uuid4())


def generate_timestamp() -> float:
    """生成当前时间戳

    Returns:
        时间戳

    """
    return time.time()


@safe_system_operation("run_with_timeout", fallback_value=None)
async def run_with_timeout(coro, timeout: float, default: Any = None) -> Any:
    """带超时的协程执行

    Args:
        coro: 协程对象
        timeout: 超时时间（秒）
        default: 超时时的默认返回值

    Returns:
        协程结果或默认值

    """
    return await asyncio.wait_for(coro, timeout=timeout)


def retry_async(
    max_retries: int = 3,
    delay: float = 1.0,
    backoff_factor: float = 2.0,
    exceptions: tuple = (Exception,),
):
    """异步重试装饰器

    Args:
        max_retries: 最大重试次数
        delay: 初始延迟时间
        backoff_factor: 退避因子
        exceptions: 需要重试的异常类型

    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            current_delay = delay

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff_factor
                    else:
                        raise

            # 这里不应该到达，但为了类型检查
            raise last_exception

        return wrapper

    return decorator


def debounce(delay: float = 0.1):
    """防抖装饰器

    Args:
        delay: 延迟时间（秒）

    """

    def decorator(func):
        last_called = [0.0]
        task = [None]

        @wraps(func)
        async def wrapper(*args, **kwargs):
            current_time = time.time()

            # 取消之前的任务
            if task[0] and not task[0].done():
                task[0].cancel()

            # 计算延迟时间
            wait_time = max(0, delay - (current_time - last_called[0]))

            # 创建新任务
            async def debounced_call():
                if wait_time > 0:
                    await asyncio.sleep(wait_time)
                return await func(*args, **kwargs)

            task[0] = asyncio.create_task(debounced_call())
            last_called[0] = current_time

            return await task[0]

        return wrapper

    return decorator


def throttle(calls_per_second: float):
    """限流装饰器

    Args:
        calls_per_second: 每秒调用次数

    """

    def decorator(func):
        min_interval = 1.0 / calls_per_second
        last_called = [0.0]

        @wraps(func)
        async def wrapper(*args, **kwargs):
            current_time = time.time()
            elapsed = current_time - last_called[0]

            if elapsed < min_interval:
                await asyncio.sleep(min_interval - elapsed)

            last_called[0] = time.time()
            return await func(*args, **kwargs)

        return wrapper

    return decorator


class AsyncEventEmitter:
    """简单的事件发射器"""

    def __init__(self):
        self._listeners: dict[str, list[Callable]] = {}

    def on(self, event: str, listener: Callable):
        """添加事件监听器

        Args:
            event: 事件名称
            listener: 监听器函数

        """
        if event not in self._listeners:
            self._listeners[event] = []
        self._listeners[event].append(listener)

    def off(self, event: str, listener: Callable):
        """移除事件监听器

        Args:
            event: 事件名称
            listener: 监听器函数

        """
        if event in self._listeners:
            with contextlib.suppress(ValueError):
                self._listeners[event].remove(listener)

    async def emit(self, event: str, *args, **kwargs):
        """发射事件

        Args:
            event: 事件名称
            args: 位置参数
            kwargs: 关键字参数

        """
        if event in self._listeners:
            tasks = []
            for listener in self._listeners[event]:
                if asyncio.iscoroutinefunction(listener):
                    tasks.append(listener(*args, **kwargs))
                else:
                    listener(*args, **kwargs)

            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)


class AsyncCache:
    """简单的异步缓存"""

    def __init__(self, ttl: float = 300.0):
        """初始化缓存

        Args:
            ttl: 生存时间（秒）

        """
        self._cache: dict[str, Any] = {}
        self._timestamps: dict[str, float] = {}
        self._ttl = ttl

    def get(self, key: str) -> Any | None:
        """获取缓存值

        Args:
            key: 缓存键

        Returns:
            缓存值或None

        """
        if key not in self._cache:
            return None

        # 检查是否过期
        if time.time() - self._timestamps[key] > self._ttl:
            self.delete(key)
            return None

        return self._cache[key]

    def set(self, key: str, value: Any):
        """设置缓存值

        Args:
            key: 缓存键
            value: 缓存值

        """
        self._cache[key] = value
        self._timestamps[key] = time.time()

    def delete(self, key: str):
        """删除缓存值

        Args:
            key: 缓存键

        """
        self._cache.pop(key, None)
        self._timestamps.pop(key, None)

    def clear(self):
        """清空缓存"""
        self._cache.clear()
        self._timestamps.clear()

    def cleanup(self):
        """清理过期缓存"""
        current_time = time.time()
        expired_keys = [key for key, timestamp in self._timestamps.items() if current_time - timestamp > self._ttl]

        for key in expired_keys:
            self.delete(key)


@safe_system_operation("safe_json_loads", fallback_value=None)
def safe_json_loads(json_str: str, default: Any = None) -> Any:
    """安全的JSON解析

    Args:
        json_str: JSON字符串
        default: 默认值

    Returns:
        解析结果或默认值

    """
    import json

    return json.loads(json_str)


@safe_system_operation("safe_json_dumps", fallback_value="{}")
def safe_json_dumps(obj: Any, default: str = "{}") -> str:
    """安全的JSON序列化

    Args:
        obj: 要序列化的对象
        default: 默认值

    Returns:
        JSON字符串或默认值

    """
    import json

    return json.dumps(obj, ensure_ascii=False)


def merge_dicts(*dicts: dict[str, Any]) -> dict[str, Any]:
    """合并多个字典

    Args:
        dicts: 字典列表

    Returns:
        合并后的字典

    """
    result = {}
    for d in dicts:
        if d:
            result.update(d)
    return result


def flatten_dict(d: dict[str, Any], parent_key: str = "", sep: str = ".") -> dict[str, Any]:
    """扁平化字典

    Args:
        d: 嵌套字典
        parent_key: 父键名
        sep: 分隔符

    Returns:
        扁平化后的字典

    """
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


def unflatten_dict(d: dict[str, Any], sep: str = ".") -> dict[str, Any]:
    """反扁平化字典

    Args:
        d: 扁平化字典
        sep: 分隔符

    Returns:
        嵌套字典

    """
    result = {}
    for k, v in d.items():
        parts = k.split(sep)
        current = result
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
        current[parts[-1]] = v
    return result


async def gather_with_concurrency(coros, max_concurrency: int = 10) -> list[Any]:
    """并发执行协程，限制并发数

    Args:
        coros: 协程列表
        max_concurrency: 最大并发数

    Returns:
        结果列表

    """
    semaphore = asyncio.Semaphore(max_concurrency)

    async def limited_coro(coro):
        async with semaphore:
            return await coro

    return await asyncio.gather(*(limited_coro(coro) for coro in coros))


def format_bytes(bytes_count: int) -> str:
    """格式化字节数

    Args:
        bytes_count: 字节数

    Returns:
        格式化后的字符串

    """
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes_count < 1024.0:
            return f"{bytes_count:.2f} {unit}"
        bytes_count /= 1024.0
    return f"{bytes_count:.2f} PB"


def format_duration(seconds: float) -> str:
    """格式化时长

    Args:
        seconds: 秒数

    Returns:
        格式化后的字符串

    """
    if seconds < 60:
        return f"{seconds:.2f}s"
    if seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.2f}m"
    hours = seconds / 3600
    return f"{hours:.2f}h"
