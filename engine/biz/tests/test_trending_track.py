"""TrendingCollectClient —— 采集轨闭环(claim → 抓取 → 回报)测试即规格。"""

from __future__ import annotations

import pytest

from dawei_biz.bridges.social.trending_track import TrendingCollectClient, collectable_platforms


def _task(tid="t1", platform="weibo"):
    return {"id": tid, "source_id": "s1", "tenant_id": "t-a", "platform": platform}


@pytest.mark.unit
class TestCollectablePlatforms:
    def test_ttc1_only_trending_browser_connectors(self):
        platforms = collectable_platforms()
        assert "weibo" in platforms
        assert "zhihu" in platforms
        assert "bilibili" not in platforms      # capability.trending = none
        assert "wechat_mp" not in platforms     # trending 段为空串占位


@pytest.mark.unit
class TestPollLoop:
    async def test_ttc2_claim_scrape_report_roundtrip(self):
        claimed_args, reported = [], []

        def claim(platforms, limit=3):
            claimed_args.append((list(platforms), limit))
            return [_task()]

        def report(task_id, payload):
            reported.append((task_id, payload))

        async def scrape(task, *, headless=True):
            return {"ok": True, "items": [{"title": "微博热点"}, {"title": "热搜2", "url": "https://wb/2"}]}

        c = TrendingCollectClient(tenant_id="t-a", platforms=["weibo"], claim=claim, report=report, scrape=scrape)
        out = await c.poll_once()
        assert out == {"claimed": 1, "reported": 1}
        assert claimed_args[0][0] == ["weibo"]
        tid, payload = reported[0]
        assert tid == "t1"
        assert payload["ok"] is True
        assert payload["items"][0] == {"platform": "weibo", "title": "微博热点"}

    async def test_ttc3_control_plane_unreachable_not_raise(self):
        def boom(platforms, limit=3):
            raise RuntimeError("network down")

        c = TrendingCollectClient(claim=boom, report=lambda *_a, **_k: None, scrape=None)
        out = await c.poll_once()
        assert out.get("error") == "control_plane_unreachable"

    async def test_ttc4_outcome_error_class_mapping(self):
        reported = []

        async def scrape(task, *, headless=True):
            return {"ok": False, "outcome": "login_required", "error": "需登录"}

        c = TrendingCollectClient(
            claim=lambda _p, _limit=3: [_task()],
            report=lambda _tid, p: reported.append(p), scrape=scrape)
        await c.poll_once()
        assert reported[0]["error_class"] == "LOGIN_REQUIRED"
        assert reported[0]["items"] == []

    async def test_ttc5_executor_crash_classified(self):
        reported = []

        def scrape(task, *, headless=True):
            raise RuntimeError("chrome crashed")

        c = TrendingCollectClient(
            claim=lambda _p, _limit=3: [_task()],
            report=lambda _tid, p: reported.append(p), scrape=scrape)
        await c.poll_once()
        assert reported[0]["error_class"] == "EXECUTOR_ERROR"

    async def test_ttc6_single_failure_not_block_batch(self):
        reported = []

        async def scrape(task, *, headless=True):
            if task["id"] == "bad":
                raise RuntimeError("boom")
            return {"ok": True, "items": [{"title": "ok"}]}

        c = TrendingCollectClient(
            claim=lambda _p, _limit=3: [_task("bad"), _task("good")],
            report=lambda tid, p: reported.append((tid, p)), scrape=scrape)
        out = await c.poll_once()
        assert out == {"claimed": 2, "reported": 2}
        assert [ok for _, p in reported for ok in [p["ok"]]] == [False, True]

    async def test_ttc7_report_failure_swallowed(self):
        def report(tid, payload):
            raise RuntimeError("control plane gone")

        async def scrape(task, *, headless=True):
            return {"ok": True, "items": []}

        c = TrendingCollectClient(claim=lambda _p, _limit=3: [_task()], report=report, scrape=scrape)
        out = await c.poll_once()
        assert out == {"claimed": 1, "reported": 0}

    async def test_ttc8_start_stop_idempotent(self):
        c = TrendingCollectClient(platforms=["weibo"], poll_interval=3600,
                                  claim=lambda _p, _limit=3: [], report=lambda *_a, **_k: None, scrape=None)
        assert c.start() is True
        assert c.start() is False  # 已在跑
        await c.stop()
        assert c.start() is True   # 停后可再启


@pytest.mark.unit
class TestAuthHeaders:
    def test_ttc9_default_claim_auth_priority(self, monkeypatch):
        """X-Api-Key 优先于 Bearer;两者皆空回落纯 X-Tenant-Id。"""
        import httpx

        from dawei_biz.bridges.social import trending_track as tt

        captured = {}

        def fake_post(url, json=None, headers=None, timeout=None):
            captured["url"], captured["json"], captured["headers"] = url, json, headers

            class R:
                def raise_for_status(self):
                    pass

                def json(self):
                    return {"tasks": []}
            return R()

        monkeypatch.setenv("SOCIAL_API_KEY", "sk-1")
        monkeypatch.setenv("SOCIAL_CONTROL_URL", "http://control.test")  # E1 后须显式基址
        monkeypatch.setattr(httpx, "post", fake_post)
        tt.default_collect_claim(["weibo"], tenant_id="t-a", token="jwt-x")
        assert captured["headers"]["X-Api-Key"] == "sk-1"
        assert "Authorization" not in captured["headers"]
        assert captured["json"] == {"platforms": ["weibo"], "limit": 3}
        assert captured["url"].endswith("/api/v1/trending/collect/claim")

        monkeypatch.setenv("SOCIAL_API_KEY", "", )
        monkeypatch.setenv("SOCIAL_AUTH_TOKEN", "env-jwt")
        tt.default_collect_claim(["weibo"], tenant_id="t-a")
        assert captured["headers"].get("Authorization") == "Bearer env-jwt"
