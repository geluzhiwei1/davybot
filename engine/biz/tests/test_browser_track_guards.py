"""浏览器轨执行端守卫 —— 测试即规格(使用场景 + Gap 修复验证)。

规格:
  SG-1 SaaS FAST FAIL:DAWEI_DEPLOYMENT_MODE=saas 下 /browser-track/start、
      /login、/login/verify 一律 403(云端只编排,本机执行端执行)
  SG-2 SaaS 下观测端点保留:status 200(无副作用)
  SG-3 local 模式行为不变:start 200 + stop 释放锁
  TL-1 TrackLock 获取/读取:锁文件含 pid/holder/tenant_id/platforms
  TL-2 同进程幂等:重复 acquire 放行
  TL-3 他进程持锁(活 pid)→ TrackLockHeldError;router start → 409
  TL-4 陈旧锁(死 pid)自动接管
  TL-5 release 仅删自身锁(他人锁不动);stop 端点释放后可重新 start
  EL-1 同平台互斥:acquire_nowait 第二次 False
  EL-2 全局并发上限:第 3 平台 False;release 后恢复
  EL-3 executor_busy 接线:_run_one 拿不到限流 → RATE_LIMITED 快速回报(不进执行器)
  EL-4 采集轨同限流:TrendingCollectClient 共享限流器语义
  CP-1 detect_captcha 标记命中(内置 + recipe 附加优先)
  CP-2 无回调:命中 → captcha_timeout(→ CAPTCHA_REQUIRED,云端/壳 auto 路径)
  CP-3 回调解决且复检通过 → 放行继续(返回 None)
  CP-4 回调 False / 复检仍命中 → captcha_timeout
  CP-5 _default_run 透传 captcha_callback → run_browser_publish
"""

from __future__ import annotations

import json
import os
import subprocess
import time

import pytest

from dawei_biz.bridges.social.browser_track import (
    OUTCOME_ERROR_CLASS,
    BrowserTrackClient,
    TrackLockHeldError,
    _track_lock_path,
    acquire_track_lock,
    read_track_lock,
    release_track_lock,
)
from dawei.tools.browser.browser_engine import ExecutionLimiter, get_execution_limiter
from dawei.tools.browser.browser_executor import CAPTCHA_MARKERS, BrowserPublishExecutor, detect_captcha


@pytest.fixture
def home(tmp_path, monkeypatch):
    """TrackLock 隔离:DAWEI_HOME 指向临时目录(不污染真实 ~/.normnomos)。"""
    monkeypatch.setenv("DAWEI_HOME", str(tmp_path))
    return tmp_path


def _task(tid="bt-1", platform="mockweb"):
    return {"id": tid, "schedule_id": "s-1", "content_id": "c-1", "platform": platform, "title": "标题", "body": "正文", "mode": "draft_box"}


# ── SG: SaaS 守卫 ──────────────────────────────────────────


@pytest.mark.unit
class TestSaasGuard:
    def _client(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from dawei_biz.bridges.social import router as social_router

        app = FastAPI()
        app.include_router(social_router.router)
        return TestClient(app)

    def test_sg1_saas_rejects_executors(self, home, monkeypatch):
        # .env 的 DAWEI_RUNTIME_MODE=server 是 deployment_class 的上游输入，
        # 删除之以使 DAWEI_DEPLOYMENT_MODE=saas 兼容回落生效（saas→saas）。
        monkeypatch.delenv("DAWEI_RUNTIME_MODE", raising=False)
        monkeypatch.setenv("DAWEI_DEPLOYMENT_MODE", "saas")
        client = self._client()
        r1 = client.post("/api/social/browser-track/start", json={"platforms": ["mockweb"], "poll_seconds": 30})
        assert r1.status_code == 403
        r2 = client.post("/api/social/browser-track/login", json={"platform": "mockweb"})
        assert r2.status_code == 403
        r3 = client.post("/api/social/browser-track/login/verify", json={"platform": "mockweb"})
        assert r3.status_code == 403
        # 守卫生效即未触锁
        assert read_track_lock() is None

    def test_sg2_saas_keeps_readonly_status(self, home, monkeypatch):
        monkeypatch.delenv("DAWEI_RUNTIME_MODE", raising=False)
        monkeypatch.setenv("DAWEI_DEPLOYMENT_MODE", "saas")
        client = self._client()
        r = client.get("/api/social/browser-track/status")
        assert r.status_code == 200
        assert r.json()["track_lock"]["held_by_other_process"] in (True, False)

    def test_sg3_local_mode_unchanged(self, home, monkeypatch):
        monkeypatch.delenv("DAWEI_RUNTIME_MODE", raising=False)
        monkeypatch.setenv("DAWEI_DEPLOYMENT_MODE", "local")
        monkeypatch.setenv("SOCIAL_CONTROL_URL", "http://127.0.0.1:9")  # 不可达 → claim 快速失败
        client = self._client()
        r1 = client.post("/api/social/browser-track/start", json={"platforms": ["mockweb"], "poll_seconds": 60})
        assert r1.status_code == 200
        assert r1.json()["platforms"] == ["mockweb"]
        r2 = client.post("/api/social/browser-track/stop")
        assert r2.status_code == 200
        assert read_track_lock() is None  # stop 已释放


# ── TL: TrackLock 双 claim 防护 ────────────────────────────


@pytest.mark.unit
class TestTrackLock:
    def test_tl1_acquire_and_read(self, home):
        acquire_track_lock(tenant_id="t1", platforms=["mockweb"], holder="dawei-engine")
        lock = read_track_lock()
        assert lock is not None
        assert lock["pid"] == os.getpid()
        assert lock["holder"] == "dawei-engine"
        assert lock["tenant_id"] == "t1"
        assert lock["platforms"] == ["mockweb"]
        assert lock["started_at"] <= time.time()

    def test_tl2_same_process_idempotent(self, home):
        acquire_track_lock(tenant_id="t1")
        acquire_track_lock(tenant_id="t2")  # 不抛
        assert read_track_lock()["tenant_id"] == "t1"  # 首次信息保留

    def test_tl3_other_live_process_holds(self, home):
        proc = subprocess.Popen(["sleep", "30"])
        try:
            _track_lock_path().write_text(json.dumps({"pid": proc.pid, "holder": "davy-light-app", "tenant_id": "t9", "platforms": ["xhs"], "started_at": time.time()}), encoding="utf-8")
            with pytest.raises(TrackLockHeldError) as ei:
                acquire_track_lock()
            assert ei.value.holder["holder"] == "davy-light-app"
            assert read_track_lock()["holder"] == "davy-light-app"  # 未被覆盖
        finally:
            proc.kill()
            proc.wait()

    def test_tl3b_router_409_when_held(self, home):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from dawei_biz.bridges.social import router as social_router

        proc = subprocess.Popen(["sleep", "30"])
        try:
            _track_lock_path().write_text(json.dumps({"pid": proc.pid, "holder": "davy-light-app", "tenant_id": "t9", "platforms": [], "started_at": time.time()}), encoding="utf-8")
            app = FastAPI()
            app.include_router(social_router.router)
            r = TestClient(app).post("/api/social/browser-track/start", json={"platforms": ["mockweb"], "poll_seconds": 30})
            assert r.status_code == 409
            assert "davy-light-app" in r.json()["detail"]
        finally:
            proc.kill()
            proc.wait()

    def test_tl4_stale_lock_takeover(self, home):
        dead_pid = 2**30  # 极不可能存活
        _track_lock_path().write_text(json.dumps({"pid": dead_pid, "holder": "crashed-sidecar", "tenant_id": "t0", "platforms": [], "started_at": 1.0}), encoding="utf-8")
        acquire_track_lock(tenant_id="t1")  # 陈旧锁 → 接管,不抛
        assert read_track_lock()["pid"] == os.getpid()

    def test_tl5_release_only_own_lock(self, home):
        _track_lock_path().write_text(json.dumps({"pid": 2**30, "holder": "other", "tenant_id": "t", "platforms": [], "started_at": 1.0}), encoding="utf-8")
        release_track_lock()  # 他人/陈旧锁不动
        assert read_track_lock() is not None
        acquire_track_lock()
        release_track_lock()
        assert read_track_lock() is None

    def test_tl_router_status_reports_lock(self, home):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from dawei_biz.bridges.social import router as social_router

        app = FastAPI()
        app.include_router(social_router.router)
        acquire_track_lock(holder="dawei-engine")
        r = TestClient(app).get("/api/social/browser-track/status")
        assert r.status_code == 200
        assert r.json()["track_lock"]["held_by_other_process"] is False
        release_track_lock()


# ── EL: ExecutionLimiter(BE-1/BE-2 生产形态)──────────────────


@pytest.mark.unit
class TestExecutionLimiter:
    def test_el1_platform_mutex(self):
        lim = ExecutionLimiter(max_concurrent=2)
        assert lim.acquire_nowait("mockweb") is True
        assert lim.acquire_nowait("mockweb") is False  # BE-2 同平台互斥
        assert lim.held_platforms() == ["mockweb"]
        lim.release("mockweb")
        assert lim.acquire_nowait("mockweb") is True

    def test_el2_global_cap(self):
        lim = ExecutionLimiter(max_concurrent=2)
        assert lim.acquire_nowait("a") is True
        assert lim.acquire_nowait("b") is True
        assert lim.acquire_nowait("c") is False  # BE-1 全局上限
        lim.release("a")
        assert lim.acquire_nowait("c") is True

    def test_el2b_blocking_acquire_timeout(self):
        lim = ExecutionLimiter(max_concurrent=1, acquire_timeout_s=0.05)
        lim.acquire_nowait("a")
        with pytest.raises(TimeoutError):
            lim.acquire("a")

    def test_el3_busy_task_reports_rate_limited(self):
        async def run(task, *, confirm_callback, headless=True):  # pragma: no cover 不应被调
            raise AssertionError("限流拒绝时不得进入执行器")

        async def claim(platform, limit=5):
            return [_task()]

        reports = []
        client = BrowserTrackClient(
            tenant_id="t1",
            platforms=["mockweb"],
            claim=claim,
            report=reports.append,
            run=run,
            limiter=ExecutionLimiter(max_concurrent=1),
        )
        client._limiter.acquire_nowait("mockweb")  # 模拟同平台任务在途
        out = __import__("asyncio").run(client._run_one(_task()))
        assert out["ok"] is False
        assert out["result_detail"]["error_class"] == OUTCOME_ERROR_CLASS["executor_busy"]
        assert out["result_detail"]["outcome"] == "executor_busy"
        client._limiter.release("mockweb")

    def test_el3b_busy_releases_cleanly(self):
        async def run(task, *, confirm_callback, headless=True):
            return {"ok": True, "post_url": "u", "outcome": "ok"}

        async def claim(platform, limit=5):
            return [_task()]

        client = BrowserTrackClient(
            tenant_id="t1",
            platforms=["mockweb"],
            claim=claim,
            report=lambda _p: None,
            run=run,
            limiter=ExecutionLimiter(max_concurrent=1),
        )
        out = __import__("asyncio").run(client._run_one(_task()))
        assert out["ok"] is True
        # 正常路径必须释放(否则后续任务误判 busy)
        assert client._limiter.acquire_nowait("mockweb") is True

    def test_el4_trending_shares_limiter_semantics(self):
        from dawei_biz.bridges.social.trending_track import TrendingCollectClient

        lim = ExecutionLimiter(max_concurrent=1)
        client = TrendingCollectClient(tenant_id="t1", platforms=["mockweb"], limiter=lim)

        async def scrape(task, *, headless=True):
            return {"ok": True, "items": [{"title": "热点"}]}

        client._scrape = scrape
        lim.acquire_nowait("mockweb")  # 发布轨占用同平台
        out = __import__("asyncio").run(client._run_one(_task()))
        assert out["ok"] is False
        assert out["error_class"] == "RATE_LIMITED"
        lim.release("mockweb")
        out2 = __import__("asyncio").run(client._run_one(_task()))
        assert out2["ok"] is True
        assert out2["items"][0]["title"] == "热点"

    def test_el5_singleton_shared(self):
        assert get_execution_limiter() is get_execution_limiter()
        assert get_execution_limiter().max_concurrent == 2


# ── CP: 验证码检测关口 ─────────────────────────────────────


class _FakeLocator:
    def __init__(self, n: int):
        self._n = n

    async def count(self) -> int:
        return self._n

    async def is_visible(self) -> bool:
        return self._n > 0


class FakePage:
    """标记集可变:模拟验证码出现/被解决;is_visible 与 count 同源。"""

    def __init__(self, markers: set[str]):
        self.markers = markers

    def locator(self, sel: str):
        return _FakeLocator(1 if sel in self.markers else 0)


@pytest.mark.unit
class TestCaptchaDetection:
    async def test_cp1_builtin_and_extra_markers(self):
        page = FakePage({"iframe[src*='recaptcha']"})
        assert await detect_captcha(page) == "iframe[src*='recaptcha']"
        assert await detect_captcha(FakePage(set())) is None
        # recipe 附加标记优先
        page2 = FakePage({".my-captcha"})
        assert await detect_captcha(page2, extra_selectors=[".my-captcha"]) == ".my-captcha"
        assert await detect_captcha(FakePage(set()), extra_selectors=[".my-captcha"]) is None
        assert any("geetest" in m for m in CAPTCHA_MARKERS)

    async def test_cp2_no_callback_captcha_timeout(self):
        page = FakePage({"#tcaptcha_iframe"})
        ex = BrowserPublishExecutor({}, captcha_callback=None)
        res = await ex._handle_captcha(page, stage="navigate")
        assert res is not None
        assert res["outcome"] == "captcha_timeout"
        assert ex.trace[-1].step == "captcha_navigate"
        assert ex.trace[-1].detail["solved"] is False

    async def test_cp3_solved_and_cleared_continues(self):
        markers = {"iframe[src*='tcaptcha']"}
        page = FakePage(markers)

        def cb(_shot):
            markers.clear()  # 用户本机解决
            return True

        ex = BrowserPublishExecutor({}, captcha_callback=cb)
        assert await ex._handle_captcha(page, stage="publish") is None
        assert ex.trace[-1].step == "captcha_publish"
        assert ex.trace[-1].outcome == "ok"

    async def test_cp4_callback_false_or_persist_times_out(self):
        # 回调 False
        ex = BrowserPublishExecutor({}, captcha_callback=lambda _s: False)
        res = await ex._handle_captcha(FakePage({"#captcha"}), stage="publish")
        assert res is not None
        assert res["outcome"] == "captcha_timeout"
        # 回调 True 但验证码仍在
        ex2 = BrowserPublishExecutor({}, captcha_callback=lambda _s: True)
        res2 = await ex2._handle_captcha(FakePage({".geetest_panel"}), stage="publish")
        assert res2 is not None
        assert res2["outcome"] == "captcha_timeout"

    async def test_cp5_default_run_forwards_captcha_callback(self, monkeypatch):
        from dawei_biz.bridges.social import browser_track as bt

        seen = {}

        async def fake_rbp(platform, **kw):
            seen.update(kw)
            return {"ok": True}

        monkeypatch.setattr(bt, "run_browser_publish", fake_rbp)
        await bt._default_run(_task(), confirm_callback=lambda _s: True, captcha_callback=lambda _s: True)
        assert seen.get("captcha_callback") is not None
        assert seen.get("auto_confirm") is False
