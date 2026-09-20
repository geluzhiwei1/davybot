"""浏览器轨闭环 —— 测试即规格(先测后码)。PRD §11.2(双轨制)/§3.2 原则 3/§6.10。

规格:
  HG-1 人工确认关卡:request 入 pending 表;resolve(True) 放行
  HG-2 resolve(False) → 终止(不发布)
  HG-3 超时 → 终止
  HG-4 验证码请求(captcha kind)同机制;solve 即 resolve
  HG-5 未知 request_id 的 resolve 返回 False
  BTC-1 poll_once:claim(POST {platform,limit})→ 执行 → 回报(ok + result_url)
  BTC-2 确认默认人工:confirm_callback 走关卡,无人放行 → aborted_by_human 回报(ok=False)
  BTC-3 错误分类映射:selector_stale→SELECTOR_STALE / aborted_by_human→ABORTED_BY_HUMAN /
       verify_failed→VERIFY_FAILED(§11.2 差异点 4)
  BTC-4 控制面不可达:poll_once 不抛异常(循环韧性)
  BTC-5 单任务失败不阻断批次
  BTC-6 auto_confirm 显式开启:跳过本地人工关卡(confirm_callback=None 直达执行)
  DT-1 值班成稿链(L3 自动成稿+人工批准):热点→选题→成稿→落盘 draft 工件;
       单稿失败不阻断批次
  CG-1 CaptchaGate.notify 经 notifier 钩子进入人工关卡(替换 stub)
"""

from __future__ import annotations

import asyncio

import pytest

from dawei.social.browser_track import BrowserTrackClient, HumanGate
from dawei.tools.browser.browser_engine import CaptchaGate


def _task(tid="bt-1", platform="mockweb", mode="draft_box"):
    return {"id": tid, "schedule_id": "s-1", "content_id": "c-1", "platform": platform,
            "title": "新品测评", "body": "正文…", "mode": mode}


# ── 人工关卡 ────────────────────────────────────────────────

@pytest.mark.unit
class TestHumanGate:
    async def test_hg1_confirm_resolved_true(self):
        gate = HumanGate()
        fut = asyncio.ensure_future(gate.wait_confirm("bt-1", "mockweb", timeout=2.0))
        await asyncio.sleep(0.01)
        pend = gate.pending()
        assert len(pend) == 1
        assert pend[0]["kind"] == "confirm"
        assert pend[0]["task_id"] == "bt-1"
        assert gate.resolve(pend[0]["request_id"], True)
        assert await fut is True

    async def test_hg2_confirm_resolved_false(self):
        gate = HumanGate()
        fut = asyncio.ensure_future(gate.wait_confirm("bt-1", "mockweb", timeout=2.0))
        await asyncio.sleep(0.01)
        rid = gate.pending()[0]["request_id"]
        gate.resolve(rid, False)
        assert await fut is False

    async def test_hg3_confirm_timeout(self):
        gate = HumanGate()
        assert await gate.wait_confirm("bt-1", "mockweb", timeout=0.05) is False
        assert gate.pending() == []  # 超时后清出待办

    async def test_hg4_captcha_kind(self):
        gate = HumanGate()
        fut = asyncio.ensure_future(gate.wait_captcha("mockweb", timeout=2.0))
        await asyncio.sleep(0.01)
        pend = gate.pending()
        assert pend[0]["kind"] == "captcha"
        assert pend[0]["platform"] == "mockweb"
        gate.resolve(pend[0]["request_id"], True)
        assert await fut is True

    def test_hg5_unknown_request_id(self):
        gate = HumanGate()
        assert gate.resolve("nope", True) is False


# ── 闭环客户端 ───────────────────────────────────────────────

@pytest.mark.unit
class TestBrowserTrackClient:
    def _client(self, *, claim, report, run, gate=None):
        return BrowserTrackClient(
            tenant_id="t1", platforms=["mockweb"],
            claim=claim, report=report, run=run, gate=gate,
        )

    async def test_btc1_claim_run_report(self):
        claims, reports = [], []

        async def claim(platform, limit=5):
            claims.append((platform, limit))
            return [_task()]

        async def run(task, *, confirm_callback, headless=True):
            return {"ok": True, "post_url": "https://mockweb/p/1", "outcome": "ok"}

        client = self._client(claim=claim, report=reports.append, run=run)
        out = await client.poll_once()
        assert claims == [("mockweb", 5)]  # POST claim 契约参数
        assert out == {"mockweb": {"claimed": 1, "reported": 1}}
        assert len(reports) == 1
        assert reports[0]["task_id"] == "bt-1"
        assert reports[0]["ok"] is True
        assert reports[0]["result_url"] == "https://mockweb/p/1"

    async def test_btc2_human_confirm_default_not_auto(self):
        """无人放行 → 执行器收到 confirm=False → aborted,回报失败(原则 3)。"""
        reports = []

        async def claim(platform, limit=5):
            return [_task()]

        async def run(task, *, confirm_callback, headless=True):
            confirmed = confirm_callback("shot.png")  # 关卡未放行必须返回 False
            return {"ok": confirmed, "outcome": "ok" if confirmed else "aborted_by_human"}

        gate = HumanGate(confirm_timeout=0.05)
        client = self._client(claim=claim, report=reports.append, run=run, gate=gate)
        await client.poll_once()
        assert reports[0]["ok"] is False
        assert reports[0]["result_detail"]["error_class"] == "ABORTED_BY_HUMAN"

    async def test_btc3_error_class_mapping(self):
        seen = {}

        async def claim(platform, limit=5):
            return [_task(tid=f"bt-{i}") for i in range(3)]

        outcomes = iter(["selector_stale", "aborted_by_human", "verify_failed"])

        async def run(task, *, confirm_callback, headless=True):
            return {"ok": False, "outcome": next(outcomes)}

        async def report(payload):
            seen[payload["task_id"]] = payload

        client = self._client(claim=claim, report=report, run=run, gate=HumanGate(confirm_timeout=0.01))
        await client.poll_once()
        classes = {p["result_detail"]["error_class"] for p in seen.values()}
        assert classes == {"SELECTOR_STALE", "ABORTED_BY_HUMAN", "VERIFY_FAILED"}
        assert all(p["ok"] is False for p in seen.values())

    async def test_btc4_control_plane_unreachable_no_raise(self):
        async def claim(platform, limit=5):
            raise ConnectionError("control plane down")

        async def report(payload):
            raise AssertionError("不应走到回报")

        client = self._client(claim=claim, report=report, run=None)
        out = await client.poll_once()  # 不抛异常
        assert out["mockweb"]["claimed"] == 0

    async def test_btc5_single_failure_does_not_break_batch(self):
        done = []

        async def claim(platform, limit=5):
            return [_task(tid="bt-1"), _task(tid="bt-2")]

        async def run(task, *, confirm_callback, headless=True):
            if task["id"] == "bt-1":
                raise RuntimeError("chrome crash")
            done.append(task["id"])
            return {"ok": True, "post_url": "u", "outcome": "ok"}

        reports = []

        async def report(payload):
            reports.append(payload)

        client = self._client(claim=claim, report=report, run=run)
        out = await client.poll_once()
        assert done == ["bt-2"]
        assert out["mockweb"]["reported"] == 2  # 失败任务同样回报(错误分类)
        assert any(p["ok"] is False for p in reports)

    async def test_btc6_auto_confirm_skips_gate(self):
        """BTC-6 auto_confirm=True:执行器收到 confirm_callback=None + auto_confirm=True,
        不进入人工关卡(无人放行也不超时死等),回报成功。默认关(btc2 覆盖)。"""
        reports = []
        seen = {}

        async def claim(platform, limit=5):
            return [_task()]

        async def run(task, *, confirm_callback, headless=True, auto_confirm=False):
            seen["confirm_callback"] = confirm_callback
            seen["auto_confirm"] = auto_confirm
            return {"ok": True, "post_url": "https://mockweb/p/6", "outcome": "ok"}

        gate = HumanGate(confirm_timeout=0.05)  # 若误入关卡:超时 → ok=False,测试即失败
        client = BrowserTrackClient(
            tenant_id="t1", platforms=["mockweb"],
            claim=claim, report=reports.append, run=run, gate=gate,
            auto_confirm=True,
        )
        await client.poll_once()
        assert seen["confirm_callback"] is None
        assert seen["auto_confirm"] is True
        assert gate.pending() == []  # 关卡从未被触碰
        assert reports[0]["ok"] is True
        assert reports[0]["result_url"] == "https://mockweb/p/6"


# ── 值班成稿链 ───────────────────────────────────────────────

@pytest.mark.unit
class TestDutyDraftChain:
    def test_dt1_duty_produces_draft_artifacts(self):
        from dawei.social.duty_orchestrator import run_duty_pipeline

        items = [{"platform": "weibo", "title": "行业新规", "content_hash": "h1"}]
        llm_calls = []

        def llm_call(system, user):
            llm_calls.append(system[:20])
            if len(llm_calls) == 1:  # 选题
                return ('```json\n{"ideas": [{"title": "新规解读", "angle": "合规视角",'
                        ' "reasoning": "高相关", "relevance_score": 0.9,'
                        ' "timeliness": "rising", "trending_item_ids": ["h1"]}]}\n```')
            return '```json\n{"title": "新规解读", "variants": {"xiaohongshu": {"text": "笔记"}}}\n```'

        pushed = []
        out = run_duty_pipeline(
            items, {"industry": "legal"}, llm_call=llm_call,
            brand_id="b1", tenant_id="t1", push=lambda p, tenant_id: pushed.append(p),  # noqa: ARG005
        )
        assert out["created_ideas"] == 1
        assert out["created_drafts"] == 1
        assert len(pushed) == 1
        p = pushed[0]
        assert p["brand_id"] == "b1"
        assert p["body"]["variants"]["xiaohongshu"]["text"] == "笔记"
        assert p["source_ref"]["origin"] == "agent_session"  # 落盘协议复用

    def test_dt1_draft_failure_does_not_break_batch(self):
        from dawei.social.duty_orchestrator import run_duty_pipeline

        items = [{"platform": "weibo", "title": "热点A", "content_hash": "h1"}]
        ideas = ('```json\n{"ideas": ['
                 '{"title": "T1", "angle": "a", "reasoning": "r", "relevance_score": 0.9, "timeliness": "peak"},'
                 '{"title": "T2", "angle": "a", "reasoning": "r", "relevance_score": 0.9, "timeliness": "peak"}'
                 ']}\n```')
        state = {"n": 0}

        def llm_call(system, user):
            state["n"] += 1
            if state["n"] == 1:
                return ideas
            if state["n"] == 2:
                raise RuntimeError("llm down")
            return '```json\n{"title": "T2", "variants": {"weibo": {"text": "稿"}}}\n```'

        pushed = []
        out = run_duty_pipeline(
            items, {}, llm_call=llm_call,
            brand_id="b1", tenant_id="t1", push=lambda p, tenant_id: pushed.append(p),  # noqa: ARG005
            max_drafts=2,
        )
        assert out["created_ideas"] == 2
        assert out["created_drafts"] == 1  # 第 1 稿失败,第 2 稿照常
        assert len(pushed) == 1


# ── CaptchaGate 接线 ────────────────────────────────────────

@pytest.mark.unit
class TestCaptchaWiring:
    async def test_cg1_notify_files_human_request(self):
        gate = HumanGate()
        captcha = CaptchaGate(timeout_seconds=2.0)
        captcha.attach_human_gate(gate)
        fut = asyncio.ensure_future(captcha.wait_for_solve())
        captcha.notify("xiaohongshu")  # 触发通知 → 人工关卡出现 captcha 待办
        await asyncio.sleep(0.01)
        pend = gate.pending()
        assert any(p["kind"] == "captcha" and p["platform"] == "xiaohongshu" for p in pend)
        gate.resolve(pend[0]["request_id"], True)  # 桌面端 HTTP solve
        assert await fut is True


# ── sidecar 路由 HTTP 面 ────────────────────────────────────

@pytest.mark.unit
class TestBrowserTrackRoutes:
    def _client(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from dawei.social import router as social_router

        app = FastAPI()
        app.include_router(social_router.router)
        return TestClient(app)

    @staticmethod
    def _file_pending(kind, **kw):
        import asyncio

        from dawei.social.browser_track import shared_human_gate

        async def _file():
            return shared_human_gate()._file(kind, **kw)

        return asyncio.new_event_loop().run_until_complete(_file())

    def test_rt1_pending_and_confirm_flow(self):
        client = self._client()
        rid = self._file_pending("confirm", task_id="bt-x", platform="mockweb")

        r = client.get("/api/social/browser-track/pending")
        assert r.status_code == 200
        assert any(p["request_id"] == rid for p in r.json()["items"])

        r2 = client.post(f"/api/social/browser-track/confirm/{rid}", json={"approved": True})
        assert r2.status_code == 200
        assert r2.json()["resolved"] is True

        r3 = client.post(f"/api/social/browser-track/confirm/{rid}", json={"approved": True})
        assert r3.status_code == 404  # 已解决(移除)

    def test_rt2_captcha_solve_endpoint(self):
        client = self._client()
        rid = self._file_pending("captcha", platform="douyin")
        r = client.post(f"/api/social/browser-track/captcha/{rid}/solve")
        assert r.status_code == 200
        assert r.json()["solved"] is True

    def test_rt3_start_stop(self):
        client = self._client()
        r1 = client.post("/api/social/browser-track/start",
                         json={"platforms": ["mockweb"], "poll_seconds": 30})
        assert r1.status_code == 200
        assert r1.json()["platforms"] == ["mockweb"]
        r2 = client.post("/api/social/browser-track/stop")
        assert r2.status_code == 200
        assert r2.json()["stopped"] is True


# ── sidecar 路由 HTTP 面 ────────────────────────────────────

@pytest.mark.unit
class TestBrowserTrackRoutes:
    def _client(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from dawei.social import router as social_router

        app = FastAPI()
        app.include_router(social_router.router)
        return TestClient(app)

    def test_rt1_pending_and_confirm_flow(self):
        import threading

        client = self._client()
        from dawei.social.browser_track import shared_human_gate

        gate = shared_human_gate()

        # 异步上下文造一条 confirm 待办(sidecar 事件循环外模拟执行侧)
        import asyncio

        async def _file():
            return gate._file("confirm", task_id="bt-x", platform="mockweb")

        rid = asyncio.new_event_loop().run_until_complete(_file())
        r = client.get("/api/social/browser-track/pending")
        assert r.status_code == 200
        assert any(p["request_id"] == rid for p in r.json()["items"])

        r2 = client.post(f"/api/social/browser-track/confirm/{rid}", json={"approved": True})
        assert r2.status_code == 200 and r2.json()["resolved"] is True

        r3 = client.post(f"/api/social/browser-track/confirm/{rid}", json={"approved": True})
        assert r3.status_code == 404  # 已解决(移除)

    def test_rt2_captcha_solve_endpoint(self):
        client = self._client()
        import asyncio

        from dawei.social.browser_track import shared_human_gate

        gate = shared_human_gate()

        async def _file():
            return gate._file("captcha", platform="douyin")

        rid = asyncio.new_event_loop().run_until_complete(_file())
        r = client.post(f"/api/social/browser-track/captcha/{rid}/solve")
        assert r.status_code == 200 and r.json()["solved"] is True

    def test_rt3_start_stop_idempotent(self):
        client = self._client()
        r1 = client.post("/api/social/browser-track/start",
                         json={"platforms": ["mockweb"], "poll_seconds": 30})
        assert r1.status_code == 200
        assert r1.json()["platforms"] == ["mockweb"]
        r2 = client.post("/api/social/browser-track/stop")
        assert r2.status_code == 200 and r2.json()["stopped"] is True
