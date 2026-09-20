"""BrowserEngine 会话池/验证码门 —— 测试即规格(PRD §11.4)。阶段 1 红态。"""

from __future__ import annotations

import asyncio
import time

import pytest

from dawei.tools.browser.browser_engine import (
    CaptchaGate,
    PooledSession,
    SessionPool,
    SessionState,
    session_is_healthy,
)


@pytest.mark.unit
class TestConcurrency:
    async def test_be1_within_limit(self):
        pool = SessionPool(max_concurrent=2)
        a = await pool.acquire("xiaohongshu")
        b = await pool.acquire("weibo")
        assert a.platform == "xiaohongshu" and b.platform == "weibo"

    async def test_be1_over_limit_waits(self):
        """第 3 个并发获取必须等待,而非超发"""
        pool = SessionPool(max_concurrent=2)
        await pool.acquire("p1")
        await pool.acquire("p2")
        async with asyncio.timeout(0.2):
            task = asyncio.create_task(pool.acquire("p3"))
            await asyncio.sleep(0.05)
            assert not task.done()
        pool.release("p1")
        c = await asyncio.wait_for(task, timeout=0.5)
        assert c.platform == "p3"

    async def test_be2_platform_mutex(self):
        """同平台互斥:第二个任务等待第一个释放"""
        pool = SessionPool(max_concurrent=2)
        s1 = await pool.acquire("xhs")
        assert s1.state == SessionState.BUSY
        async with asyncio.timeout(0.2):
            task = asyncio.create_task(pool.acquire("xhs"))
            await asyncio.sleep(0.05)
            assert not task.done()
        pool.release("xhs")
        s2 = await asyncio.wait_for(task, timeout=0.5)
        assert s2.state == SessionState.BUSY

    async def test_be2_release_allows_reacquire(self):
        pool = SessionPool(max_concurrent=2)
        await pool.acquire("x")
        pool.release("x")
        s = await pool.acquire("x")
        assert s.state == SessionState.BUSY


@pytest.mark.unit
class TestTTL:
    def test_be3_idle_expired_swept(self):
        pool = SessionPool(ttl_seconds=600.0)
        s = await_(pool.acquire("weibo"))
        pool.release("weibo")
        # 快进 601s
        closed = pool.sweep(now=s.last_active + 601)
        assert closed == ["weibo"]

    def test_be3_within_ttl_kept(self):
        pool = SessionPool(ttl_seconds=600.0)
        await_(pool.acquire("weibo"))
        pool.release("weibo")
        closed = pool.sweep(now=time.monotonic() + 100)
        assert closed == []

    def test_be3_busy_session_never_swept(self):
        pool = SessionPool(ttl_seconds=1.0)
        await_(pool.acquire("xhs"))  # 未 release → busy
        closed = pool.sweep(now=time.monotonic() + 999)
        assert closed == []


@pytest.mark.unit
class TestCaptchaGate:
    async def test_be4_solve_within_timeout(self):
        gate = CaptchaGate(timeout_seconds=5)
        gate.notify("xhs")
        t = asyncio.create_task(gate.wait_for_solve())
        await asyncio.sleep(0.05)
        gate.solve()  # 用户在本机解决验证码
        assert await asyncio.wait_for(t, timeout=1) is True

    async def test_be4_timeout_fails(self):
        gate = CaptchaGate(timeout_seconds=0.1)
        gate.notify("xhs")
        assert await gate.wait_for_solve() is False


@pytest.mark.unit
class TestHealth:
    def test_be5_healthy_when_fresh(self):
        s = PooledSession(platform="x")
        assert session_is_healthy(s, now=s.last_active + 10) is True

    def test_be5_unhealthy_when_stale(self):
        """孤儿/僵死会话判定 → 触发重建"""
        s = PooledSession(platform="x")
        assert session_is_healthy(s, now=s.last_active + 10_000) is False


def await_(coro):
    return asyncio.run(coro)
