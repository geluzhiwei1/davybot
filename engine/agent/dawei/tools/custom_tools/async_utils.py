# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Shared async utilities for custom tools."""

import asyncio
import concurrent.futures
import contextvars

# 主事件循环引用（bug#5 修复）：MCP 长连接的 owner task 与 session 绑定在
# 主 loop 上；同步工具在 worker 线程里必须把协程投递回主 loop 执行，
# 而不是各自新建临时 loop（旧 run_async 临时 loop 退出即杀死连接 task）。
_MAIN_LOOP: asyncio.AbstractEventLoop | None = None


def set_main_loop(loop: asyncio.AbstractEventLoop | None) -> None:
    """注册主事件循环（server 启动时调用一次）。"""
    global _MAIN_LOOP
    _MAIN_LOOP = loop


def get_main_loop() -> asyncio.AbstractEventLoop | None:
    """返回已注册的主事件循环（未注册时为 None）。"""
    return _MAIN_LOOP


def run_on_main_loop(coro, timeout: float = 120):
    """在主事件循环上执行协程，供 worker 线程中的同步工具调用。

    与 run_async 的区别：协程调度到主 loop（长连接 session/owner task 所在
    的 loop），并以 timeout 有界阻塞调用线程（超时抛 TimeoutError，绝不
    无限等待）；当前线程就是主 loop 线程时直接报错（FAST FAIL）——同步
    工具应先经 tool_executor 的 to_thread 卸载到 worker 线程。

    Args:
        coro: 待执行的协程
        timeout: 最长等待秒数

    Returns:
        协程的返回值

    Raises:
        TimeoutError: 超过 timeout 未完成
        RuntimeError: 未注册主 loop，或从主 loop 线程内调用（会死锁）
    """
    loop = _MAIN_LOOP
    if loop is None or loop.is_closed():
        raise RuntimeError(
            "run_on_main_loop: main loop not registered (server not started?)"
        )
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None
    if running is loop:
        raise RuntimeError(
            "run_on_main_loop called from the main loop thread — "
            "sync tools must be offloaded via asyncio.to_thread (tool_executor)"
        )
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout)


def run_async(coro):
    """Run async coroutine from sync context, handling existing event loops.

    If called from within a running event loop, spawns a new thread
    to avoid blocking. Otherwise uses asyncio.run directly.

    The current contextvars are propagated into the worker thread — a bare new
    thread starts with an empty context, which would otherwise drop per-request
    state such as the user JWT in ``local_context`` (multi-tenant business tools).

    Args:
        coro: Coroutine to execute

    Returns:
        The coroutine's return value

    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # No running event loop — safe to use asyncio.run (inherits current context)
        return asyncio.run(coro)

    # Already inside a running event loop — run in a separate thread, but copy
    # the current contextvars so the coroutine sees per-request state (auth_token,
    # session_id, ...). A plain new thread would lose them.
    ctx = contextvars.copy_context()

    def _worker():
        loop = asyncio.new_event_loop()
        try:
            return ctx.run(loop.run_until_complete, coro)
        finally:
            loop.close()

    with concurrent.futures.ThreadPoolExecutor() as pool:
        future = pool.submit(_worker)
        return future.result()
