"""值班 Agent 定时器 —— 测试即规格(先测后码)。PRD §6.10(值班 Agent 按品牌策略定时执行)。

规格:
  DS-1 set(enabled) 启动后台循环:按 interval 反复执行值班任务
  DS-2 set(enabled=False) 停止:不再执行
  DS-3 单轮异常不杀循环(下轮照常)
  DS-4 status() 列出各品牌调度配置
  DS-5 router:POST /api/social/duty-schedule 启停;interval 非法 422
  DS-6 循环调用 runner 时透传 tenant_id/draft_count(不丢参);status 回显 draft_count
"""

from __future__ import annotations

import asyncio

import pytest


@pytest.mark.unit
class TestDutyScheduler:
    async def test_ds1_interval_runs(self):
        from dawei_biz.bridges.social.duty_schedule import DutyScheduler

        ran = []

        def run(brand, *, tenant_id="default", draft_count=0):
            ran.append(brand)

        sch = DutyScheduler(runner=run)
        sch.set("b1", interval_minutes=0.01 / 60, enabled=True)  # ~0.01s
        await asyncio.sleep(0.15)
        await sch.stop_all()
        assert ran.count("b1") >= 2  # 循环执行多轮

    async def test_ds2_disable_stops(self):
        from dawei_biz.bridges.social.duty_schedule import DutyScheduler

        ran = []

        def run(brand, *, tenant_id="default", draft_count=0):
            ran.append(brand)

        sch = DutyScheduler(runner=run)
        sch.set("b1", interval_minutes=0.01 / 60, enabled=True)
        await asyncio.sleep(0.06)
        sch.set("b1", interval_minutes=0.01 / 60, enabled=False)
        after = len(ran)
        await asyncio.sleep(0.1)
        assert len(ran) == after  # 停止后不再执行

    async def test_ds3_runner_exception_does_not_kill_loop(self):
        from dawei_biz.bridges.social.duty_schedule import DutyScheduler

        state = {"n": 0}

        def runner(brand, *, tenant_id="default", draft_count=0):
            state["n"] += 1
            if state["n"] == 1:
                raise RuntimeError("llm down")

        sch = DutyScheduler(runner=runner)
        sch.set("b1", interval_minutes=0.01 / 60, enabled=True)
        await asyncio.sleep(0.12)
        await sch.stop_all()
        assert state["n"] >= 2  # 首轮炸了,循环仍在

    async def test_ds4_status_lists_schedules(self):
        from dawei_biz.bridges.social.duty_schedule import DutyScheduler

        sch = DutyScheduler(runner=lambda _brand, *, tenant_id="default", draft_count=0: None)
        sch.set("b1", interval_minutes=30, enabled=True)
        sch.set("b2", interval_minutes=60, enabled=False)
        st = {s["brand_id"]: s for s in sch.status()}
        assert st["b1"]["enabled"] is True
        assert st["b1"]["interval_minutes"] == 30
        assert st["b2"]["enabled"] is False
        await sch.stop_all()

    async def test_ds6_loop_passes_tenant_and_draft_count(self):
        from dawei_biz.bridges.social.duty_schedule import DutyScheduler

        seen = []

        def runner(brand, *, tenant_id, draft_count):
            seen.append((brand, tenant_id, draft_count))

        sch = DutyScheduler(runner=runner)
        sch.set("b1", interval_minutes=0.01 / 60, enabled=True,
                tenant_id="t-42", draft_count=2)
        await asyncio.sleep(0.08)
        await sch.stop_all()
        assert seen and all(s == ("b1", "t-42", 2) for s in seen)  # 参数全程透传不丢
        assert sch.status()[0]["draft_count"] == 2  # status 回显


@pytest.mark.unit
class TestDutyScheduleRoute:
    def _client(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from dawei_biz.bridges.social import router as social_router
        from dawei_biz.bridges.social.duty_schedule import shared_scheduler

        app = FastAPI()
        app.include_router(social_router.router)
        with TestClient(app) as c:
            yield c, shared_scheduler()

    def test_ds5_route_start_stop_and_validation(self):
        import asyncio

        for c, sch in self._client():
            r1 = c.post("/api/social/duty-schedule",
                        json={"brand_id": "b1", "interval_minutes": 30, "enabled": True})
            assert r1.status_code == 200
            assert r1.json()["ok"] is True
            r2 = c.post("/api/social/duty-schedule",
                        json={"brand_id": "b1", "interval_minutes": 0, "enabled": False})
            assert r2.status_code == 422  # interval 非法
            r3 = c.post("/api/social/duty-schedule",
                        json={"brand_id": "b1", "interval_minutes": 30, "enabled": False})
            assert r3.status_code == 200
            asyncio.new_event_loop().run_until_complete(sch.stop_all())
