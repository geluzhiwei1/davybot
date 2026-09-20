"""值班 Agent 编排 —— 测试即规格。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from dawei.social.duty_orchestrator import run_duty

BRAND = {"name": "消费品牌A", "keywords": ["新品", "行业趋势"]}

ITEMS = [
    {"platform": "weibo", "title": "新规出台", "content_hash": "h1"},
    {"platform": "x", "title": "行业趋势讨论", "content_hash": "h2"},
]

GOOD_REPLY = '''值班分析完成:
```json
{"ideas": [
  {"title": "新规解读", "angle": "品牌视角解读新规", "reasoning": "高度相关",
   "relevance_score": 0.9, "timeliness": "rising", "trending_item_ids": ["h1"]},
  {"title": "", "angle": "缺标题应被丢弃", "reasoning": "x",
   "relevance_score": 0.8, "timeliness": "rising", "trending_item_ids": []},
  {"title": "分数越界", "angle": "a", "reasoning": "r",
   "relevance_score": 1.7, "timeliness": "peak", "trending_item_ids": []},
  {"title": "时效非法", "angle": "a", "reasoning": "r",
   "relevance_score": 0.6, "timeliness": "hot", "trending_item_ids": []}
]}
```'''


@pytest.mark.unit
class TestRunDuty:
    def test_do1_valid_ideas_kept(self):
        ideas = run_duty(ITEMS, BRAND, llm_call=lambda s, u: GOOD_REPLY)
        assert len(ideas) == 1  # 3 条垃圾被闸门拦截
        assert ideas[0]["title"] == "新规解读"
        assert ideas[0]["trending_item_ids"] == ["h1"]

    def test_do1_empty_trending_returns_empty(self):
        assert run_duty([], BRAND, llm_call=lambda s, u: GOOD_REPLY) == []

    def test_do1_unparseable_raises(self):
        with pytest.raises(ValueError):
            run_duty(ITEMS, BRAND, llm_call=lambda s, u: "没有围栏")

    def test_do2_brand_profile_reaches_prompt(self):
        seen: dict = {}

        def fake_llm(system, user):
            seen["user"] = user
            return GOOD_REPLY

        run_duty(ITEMS, BRAND, llm_call=fake_llm)
        assert "消费品牌A" in seen["user"] and "新规出台" in seen["user"]


@pytest.mark.unit
class TestDutyRoute:
    @pytest.fixture
    def client(self, monkeypatch):
        from dawei.social import router as m

        monkeypatch.setattr(m.bridge, "fetch_trending", lambda *, tenant_id, **k: ITEMS)
        monkeypatch.setattr(m.service, "default_llm_call", lambda s, u: GOOD_REPLY)
        posted: list[dict] = []

        def fake_post(idea, *, brand_id, tenant_id, **k):
            posted.append(idea)
            return {"id": f"idea-{len(posted)}", **{k2: idea[k2] for k2 in ("title",)}}

        monkeypatch.setattr(m.bridge, "post_idea", fake_post)
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(m.router)
        return TestClient(app)

    def test_dr1_end_to_end(self, client):
        r = client.post("/api/social/duty", json={"tenant_id": "t1", "brand_id": "b1", "brand_profile": BRAND})
        assert r.status_code == 200
        body = r.json()
        assert body["analyzed"] == 2 and body["created"] == 1
        assert body["ideas"][0]["title"] == "新规解读"

    def test_dr1_single_failure_does_not_block(self, client, monkeypatch):
        from dawei.social import router as m
        calls = {"n": 0}

        def flaky(idea, *, brand_id, tenant_id, **k):
            calls["n"] += 1
            raise RuntimeError("boom")

        monkeypatch.setattr(m.bridge, "post_idea", flaky)
        r = client.post("/api/social/duty", json={"tenant_id": "t1"})
        assert r.status_code == 200 and r.json()["created"] == 0  # 批次不因单条失败 5xx
