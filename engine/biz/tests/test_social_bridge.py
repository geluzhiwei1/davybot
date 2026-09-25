"""社媒 bridge —— 测试即规格(本地引擎 → social-control 控制面桥接)。

  B1 基址解析:SOCIAL_CONTROL_URL 覆盖 / 尾斜杠清理 / 无云端缺省(E1,未配置即报错)
  B2 鉴权头优先级:X-Api-Key(服务账号)> Bearer(显式 token > SOCIAL_AUTH_TOKEN)
  B3 端点形状:push_artifact / precheck_rules / get_content / fetch_trending / post_idea
  B4 post_idea 载荷白名单投影 + fetch_trending items 缺失回落 []
  B5 非 2xx → raise_for_status 上抛(调用方翻译 401/502)
"""

from __future__ import annotations

import httpx
import pytest

from dawei_biz.bridges.social import bridge


class _FakeResp:
    def __init__(self, payload=None, status=200):
        self._payload = payload if payload is not None else {}
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"{self.status_code}",
                request=httpx.Request("POST", "x"),
                response=httpx.Response(self.status_code),
            )

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("SOCIAL_CONTROL_URL", raising=False)
    monkeypatch.delenv("SOCIAL_API_KEY", raising=False)
    monkeypatch.delenv("SOCIAL_AUTH_TOKEN", raising=False)
    yield


def _patch_http(monkeypatch, method: str, resp: _FakeResp) -> dict:
    """替换 httpx.post/get(bridge 函数体内 import httpx 后按名调用)。"""
    captured: dict = {}

    def fake(url, *, json=None, headers=None, timeout=None):
        captured.update({"url": url, "json": json, "headers": headers, "timeout": timeout})
        return resp

    monkeypatch.setattr(httpx, method, fake)
    return captured


@pytest.mark.unit
class TestBase:
    def test_b1_no_cloud_default(self):
        assert bridge.DEFAULT_BASE == ""
        with pytest.raises(RuntimeError):
            bridge._base()

    def test_b1_env_override_and_trailing_slash(self, monkeypatch):
        monkeypatch.setenv("SOCIAL_CONTROL_URL", "http://localhost:8030///")
        assert bridge._base() == "http://localhost:8030"


@pytest.mark.unit
class TestHeaders:
    def test_b2_tenant_always_no_auth(self):
        h = bridge._headers("t-1")
        assert h["X-Tenant-Id"] == "t-1"
        assert h["Content-Type"] == "application/json"
        assert "Authorization" not in h
        assert "X-Api-Key" not in h

    def test_b2_explicit_token_wins_over_env(self, monkeypatch):
        monkeypatch.setenv("SOCIAL_AUTH_TOKEN", "env-tok")
        assert bridge._headers("t-1", "explicit-tok")["Authorization"] == "Bearer explicit-tok"

    def test_b2_env_token_fallback(self, monkeypatch):
        monkeypatch.setenv("SOCIAL_AUTH_TOKEN", "env-tok")
        assert bridge._headers("t-1")["Authorization"] == "Bearer env-tok"

    def test_b2_api_key_beats_bearer(self, monkeypatch):
        """服务账号 X-Api-Key 优先级最高(与 browser_track._auth_headers 一致)。"""
        monkeypatch.setenv("SOCIAL_AUTH_TOKEN", "env-tok")
        monkeypatch.setenv("SOCIAL_API_KEY", "svc-key")
        h = bridge._headers("t-1", "explicit-tok")
        assert h["X-Api-Key"] == "svc-key"
        assert "Authorization" not in h


@pytest.mark.unit
class TestEndpoints:
    @pytest.fixture(autouse=True)
    def _base_env(self, monkeypatch):
        """E1 后无云端缺省: 端点用例显式注入控制面基址(httpx 已被 mock, 不实际外呼)。"""
        monkeypatch.setenv("SOCIAL_CONTROL_URL", "http://control.test")

    def test_b3_push_artifact(self, monkeypatch):
        cap = _patch_http(monkeypatch, "post", _FakeResp({"id": "c-1", "status": "draft"}))
        out = bridge.push_artifact({"title": "T"}, tenant_id="t-9",
                                   base_url="http://localhost:8030/")
        assert out["id"] == "c-1"
        assert cap["url"] == "http://localhost:8030/api/v1/contents"
        assert cap["json"] == {"title": "T"}
        assert cap["headers"]["X-Tenant-Id"] == "t-9"
        assert cap["timeout"] == 15.0

    def test_b3_precheck_rules(self, monkeypatch):
        cap = _patch_http(monkeypatch, "post", _FakeResp({"passed": False, "violations": []}))
        out = bridge.precheck_rules("最佳", tenant_id="t-1", auth_token="jwt")
        assert out["passed"] is False
        assert cap["url"].endswith("/api/v1/governance/rule-check")
        assert cap["json"] == {"text": "最佳"}
        assert cap["headers"]["Authorization"] == "Bearer jwt"

    def test_b3_get_content(self, monkeypatch):
        cap = _patch_http(monkeypatch, "get", _FakeResp({"id": "c-9"}))
        out = bridge.get_content("c-9", tenant_id="t-1")
        assert out["id"] == "c-9"
        assert cap["url"].endswith("/api/v1/contents/c-9")

    def test_b3_fetch_trending_items(self, monkeypatch):
        _patch_http(monkeypatch, "get", _FakeResp({"items": [{"platform": "weibo"}]}))
        out = bridge.fetch_trending(tenant_id="t-1")
        assert out == [{"platform": "weibo"}]

    def test_b4_fetch_trending_missing_items_returns_empty(self, monkeypatch):
        _patch_http(monkeypatch, "get", _FakeResp({"unexpected": 1}))
        assert bridge.fetch_trending(tenant_id="t-1") == []

    def test_b4_post_idea_whitelist_projection(self, monkeypatch):
        cap = _patch_http(monkeypatch, "post", _FakeResp({"id": "i-1"}))
        idea = {
            "title": "选题", "angle": "角度", "reasoning": "理由",
            "relevance_score": 0.9, "timeliness": 0.8, "trending_item_ids": ["t-1"],
            "draft": "白名单外字段不得入库", "internal": True,
        }
        out = bridge.post_idea(idea, brand_id="b-1", tenant_id="t-1")
        assert out["id"] == "i-1"
        assert cap["json"] == {
            "brand_id": "b-1", "title": "选题", "angle": "角度", "reasoning": "理由",
            "relevance_score": 0.9, "timeliness": 0.8, "trending_item_ids": ["t-1"],
        }

    def test_b5_non_2xx_raises(self, monkeypatch):
        _patch_http(monkeypatch, "get", _FakeResp(status=401))
        with pytest.raises(httpx.HTTPStatusError):
            bridge.get_content("c-1", tenant_id="t-1")
