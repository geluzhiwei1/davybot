"""浏览器轨控制面鉴权 —— 测试即规格(§11.2 桌面端 claim 契约)。

背景:prod(SC_AUTH_DEV=false)下仅 X-Tenant-Id 的 claim 会 401;
默认通道必须携带 X-Api-Key(服务账号)或 Bearer(桌面登录用户)。
"""

from __future__ import annotations

import pytest

from dawei.social.browser_track import (
    OUTCOME_ERROR_CLASS,
    BrowserTrackClient,
    _auth_headers,
    default_claim,
)


@pytest.mark.unit
class TestAuthHeaders:
    def test_bare_tenant_only(self, monkeypatch):
        monkeypatch.delenv("SOCIAL_API_KEY", raising=False)
        monkeypatch.delenv("SOCIAL_AUTH_TOKEN", raising=False)
        h = _auth_headers("t1")
        assert h == {"X-Tenant-Id": "t1"}

    def test_env_token_becomes_bearer(self, monkeypatch):
        monkeypatch.delenv("SOCIAL_API_KEY", raising=False)
        monkeypatch.setenv("SOCIAL_AUTH_TOKEN", "jwt-1")
        assert _auth_headers("t1")["Authorization"] == "Bearer jwt-1"

    def test_api_key_wins_over_token(self, monkeypatch):
        monkeypatch.setenv("SOCIAL_API_KEY", "key-1")
        monkeypatch.setenv("SOCIAL_AUTH_TOKEN", "jwt-1")
        h = _auth_headers("t1")
        assert h["X-Api-Key"] == "key-1"
        assert "Authorization" not in h

    def test_explicit_args_override_env(self, monkeypatch):
        monkeypatch.setenv("SOCIAL_AUTH_TOKEN", "env-token")
        assert _auth_headers("t1", token="arg-token")["Authorization"] == "Bearer arg-token"

    def test_tenant_falls_back_to_env(self, monkeypatch):
        monkeypatch.setenv("SOCIAL_TENANT_ID", "env-t")
        assert _auth_headers("")["X-Tenant-Id"] == "env-t"


@pytest.mark.unit
class TestDefaultChannelAuth:
    def test_claim_sends_bearer(self, monkeypatch):
        """客户端默认通道闭包把 auth_token 传到 httpx 层。"""
        monkeypatch.setenv("SOCIAL_CONTROL_URL", "http://control.test")  # E1 后须显式基址
        captured = {}

        class FakeResp:
            def raise_for_status(self): ...

            def json(self):
                return {"tasks": []}

        def fake_post(url, json=None, headers=None, timeout=None):
            captured["url"], captured["headers"] = url, headers
            return FakeResp()

        monkeypatch.setattr("httpx.post", fake_post)
        client = BrowserTrackClient(tenant_id="t1", platforms=["wechat_mp"],
                                    auth_token="jwt-x")
        client.claim("wechat_mp", 1)
        assert captured["url"].endswith("/api/v1/browser-tasks/claim")
        assert captured["headers"]["Authorization"] == "Bearer jwt-x"
        assert captured["headers"]["X-Tenant-Id"] == "t1"

    def test_login_required_maps_to_error_class(self):
        assert OUTCOME_ERROR_CLASS["login_required"] == "LOGIN_REQUIRED"
