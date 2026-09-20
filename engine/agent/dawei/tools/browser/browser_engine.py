"""BrowserEngine —— 会话池/互斥/TTL/验证码协同(PRD §11.4)。阶段 2 实现(纯 asyncio)。

并发模型:
  - 全局并发上限(默认 2)用 Event 计数门(有空位时 set)
  - 平台互斥用 per-platform asyncio.Lock(同平台同时仅一个任务)
  - 空闲 TTL 由 sweep() 回收(busy 会话绝不清)

使用场景(重要):
  - SessionPool/CaptchaGate 为"同事件循环内多任务共享会话"的 asyncio 形态,
    适用于单进程内并发复用 Chrome 会话的高级场景(当前主要为测试所引用)。
  - 生产社媒浏览器轨(dawei.social.browser_track)采用"每任务独立短会话 +
    线程卸载执行"模型:每个 claim 在工作线程里开全新事件循环跑
    RealBrowserSession,asyncio 原生锁跨不了循环,因此生产路径使用本模块的
    线程安全变体 ExecutionLimiter(threading 语义,同平台互斥 + 全局并发上限),
    验证码人机协同直接走 HumanGate(browser_track 层)。
  - 执行端为本机桌面 sidecar / light-app 壳;SaaS 云端引擎不执行本模块。
"""

from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass, field

_STALE_AFTER_S = 3600.0  # 会话健康判定:超过 1h 无活动视为僵死


class SessionState:
    IDLE = "idle"
    BUSY = "busy"
    CAPTCHA = "captcha"
    CLOSED = "closed"


@dataclass
class PooledSession:
    platform: str
    state: str = SessionState.IDLE
    last_active: float = field(default_factory=time.monotonic)


class SessionPool:
    def __init__(self, max_concurrent: int = 2, ttl_seconds: float = 600.0):
        self.max_concurrent = max_concurrent
        self.ttl_seconds = ttl_seconds
        self._sessions: dict[str, PooledSession] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._slot_free = asyncio.Event()
        self._slot_free.set()  # 初始有空位

    def _busy_count(self) -> int:
        return sum(1 for s in self._sessions.values() if s.state == SessionState.BUSY)

    async def acquire(self, platform: str) -> PooledSession:
        lock = self._locks.setdefault(platform, asyncio.Lock())
        await lock.acquire()  # BE-2 平台互斥(可能等待)
        try:
            while self._busy_count() >= self.max_concurrent:
                await self._slot_free.wait()  # BE-1 并发上限
            s = self._sessions.get(platform)
            if s is None:
                s = PooledSession(platform=platform)
                self._sessions[platform] = s
            s.state = SessionState.BUSY
            s.last_active = time.monotonic()
            if self._busy_count() >= self.max_concurrent:
                self._slot_free.clear()
            return s
        except Exception:
            lock.release()
            raise

    def release(self, platform: str) -> None:
        s = self._sessions.get(platform)
        if s is not None:
            s.state = SessionState.IDLE
            s.last_active = time.monotonic()
        self._slot_free.set()  # 唤醒等待者
        lock = self._locks.get(platform)
        if lock is not None and lock.locked():
            lock.release()

    def sweep(self, now: float | None = None) -> list[str]:
        now = time.monotonic() if now is None else now
        closed = [
            p
            for p, s in self._sessions.items()
            if s.state == SessionState.IDLE and (now - s.last_active) > self.ttl_seconds
        ]
        for p in closed:
            self._sessions.pop(p, None)
        return closed


class CaptchaGate:
    """验证码人机协同:notify → 用户本机解决 → solve() 放行;超时判失败。

    attach_human_gate 后,notify 会把待办登记进人工关卡(HumanGate,社媒浏览器轨
    的 HTTP 可见待办表),桌面端经 POST /api/social/browser-track/captcha/{id}/solve
    放行 → 自动 solve();未接线时保持原最小语义。
    """

    def __init__(self, timeout_seconds: float = 600.0):
        self.timeout_seconds = timeout_seconds
        self._solved = asyncio.Event()
        self._human_gate = None  # 可选:社媒人工关卡(social 层注入,tools 层不依赖)

    def attach_human_gate(self, gate) -> None:
        """接入人工关卡(dawei.social.browser_track.HumanGate)。"""
        self._human_gate = gate

    def notify(self, platform: str) -> None:
        self.platform = platform
        gate = self._human_gate
        if gate is None:
            return  # 未接线(非社媒场景):保持最小语义,由调用方自行处理
        task = asyncio.ensure_future(gate.wait_captcha(platform, timeout=self.timeout_seconds))
        task.add_done_callback(
            lambda f: self.solve() if (not f.exception() and f.result()) else None)

    def solve(self) -> None:
        self._solved.set()

    async def wait_for_solve(self) -> bool:
        try:
            await asyncio.wait_for(self._solved.wait(), timeout=self.timeout_seconds)
            return True
        except TimeoutError:
            return False


def session_is_healthy(s: PooledSession, now: float) -> bool:
    return (now - s.last_active) <= _STALE_AFTER_S


class ExecutionLimiter:
    """线程安全执行限流器 —— 生产社媒浏览器轨使用(语义同 SessionPool,跨线程/跨事件循环)。

    背景:BrowserTrackClient/TrendingCollectClient 把每个任务经 asyncio.to_thread
    卸载到工作线程并在其中运行全新事件循环,asyncio.Lock 无法跨循环,故此处用
    threading 原语实现同平台互斥(BE-2)+ 全局并发上限(BE-1):
      - acquire(platform) 阻塞直至拿到该平台锁与全局空位,超时抛 TimeoutError
      - acquire_nowait(platform) 立即返回 bool(用于"忙则快速上报"路径)
      - release(platform) 必须在 finally 中调用
    全局并发上限默认 2(与 SessionPool/PRD §11.4 一致):同机 Chrome 实例数受控,
    避免桌面端资源耗尽与平台风控放大。
    """

    def __init__(self, max_concurrent: int = 2, *, acquire_timeout_s: float = 330.0):
        self.max_concurrent = max_concurrent
        self.acquire_timeout_s = acquire_timeout_s  # 略大于单任务硬超时(300s),保证长任务排队可行
        self._global = threading.BoundedSemaphore(max_concurrent)
        self._platform_locks: dict[str, threading.Lock] = {}
        self._held_platforms: set[str] = set()
        self._guard = threading.Lock()

    def _platform_lock(self, platform: str) -> threading.Lock:
        with self._guard:
            lock = self._platform_locks.get(platform)
            if lock is None:
                lock = threading.Lock()
                self._platform_locks[platform] = lock
            return lock

    def acquire(self, platform: str) -> None:
        """阻塞获取(先平台互斥,后全局并发);超时抛 TimeoutError。"""
        plock = self._platform_lock(platform)
        deadline = time.monotonic() + self.acquire_timeout_s
        if not plock.acquire(timeout=self.acquire_timeout_s):
            raise TimeoutError(f"platform {platform} busy: another task holds the platform lock")
        try:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not self._global.acquire(timeout=remaining):
                raise TimeoutError(f"global concurrency limit ({self.max_concurrent}) reached")
            with self._guard:
                self._held_platforms.add(platform)
        except Exception:
            plock.release()
            raise

    def acquire_nowait(self, platform: str) -> bool:
        """非阻塞获取;拿不到立即返回 False(调用方可快速上报 executor_busy)。"""
        plock = self._platform_lock(platform)
        if not plock.acquire(blocking=False):
            return False
        if not self._global.acquire(blocking=False):
            plock.release()
            return False
        with self._guard:
            self._held_platforms.add(platform)
        return True

    def release(self, platform: str) -> None:
        with self._guard:
            self._held_platforms.discard(platform)
        try:
            self._global.release()
        except ValueError:
            pass  # 防御性:重复 release 不致命
        lock = self._platform_locks.get(platform)
        if lock is not None:
            try:
                lock.release()
            except RuntimeError:
                pass  # 防御性:未持锁时 release 忽略

    def held_platforms(self) -> list[str]:
        with self._guard:
            return sorted(self._held_platforms)


# 生产单例:桌面 sidecar / light-app Python 兼容路径的浏览器轨共用
_PROD_LIMITER: ExecutionLimiter | None = None
_PROD_LIMITER_GUARD = threading.Lock()


def get_execution_limiter() -> ExecutionLimiter:
    """进程级单例(BE-1/BE-2 生产形态)。"""
    global _PROD_LIMITER
    with _PROD_LIMITER_GUARD:
        if _PROD_LIMITER is None:
            _PROD_LIMITER = ExecutionLimiter()
        return _PROD_LIMITER


__all__ = [
    "SessionPool", "CaptchaGate", "PooledSession", "SessionState", "session_is_healthy",
    "ExecutionLimiter", "get_execution_limiter",
]
