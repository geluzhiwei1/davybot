# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Shared async utilities for custom tools."""

import asyncio
import concurrent.futures


def run_async(coro):
    """Run async coroutine from sync context, handling existing event loops.

    If called from within a running event loop, spawns a new thread
    to avoid blocking. Otherwise uses asyncio.run directly.

    Args:
        coro: Coroutine to execute

    Returns:
        The coroutine's return value

    """
    try:
        asyncio.get_running_loop()
        # Already inside a running event loop — run in a separate thread
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result()
    except RuntimeError:
        # No running event loop — safe to use asyncio.run
        return asyncio.run(coro)
