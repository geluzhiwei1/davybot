# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""dawei/runtime.py 单测 (多模式统一方案 §4-1)

覆盖:
1. 四模式能力矩阵 (mode → deployment_class + capabilities)
2. DAWEI_DEPLOYMENT_MODE 兼容回退 (saas→saas, local/非法→desktop)
3. 矛盾 env → validate_environment() fail-fast
4. 非法 DAWEI_RUNTIME_MODE → ValueError
5. GET /api/runtime-info 端点 + 旧 deployment-mode 兼容包装
6. provider_factory._deployment_mode 委托 (上游变量优先)
"""

import pytest

pytestmark = pytest.mark.unit


def _clear_mode_env(monkeypatch):
    monkeypatch.delenv("DAWEI_RUNTIME_MODE", raising=False)
    monkeypatch.delenv("DAWEI_DEPLOYMENT_MODE", raising=False)
    monkeypatch.delenv("WORKSPACE_STORE_BACKEND", raising=False)
    monkeypatch.delenv("MARKET_API_URL", raising=False)
    monkeypatch.delenv("DAWEI_SERVER_PASSWORD", raising=False)


# ================================================================
# 1. 四模式能力矩阵
# ================================================================


class TestModeMatrix:
    """四模式 × deployment_class × capabilities"""

    @pytest.mark.parametrize(
        ("mode", "expected_class", "expected_caps"),
        [
            ("saas", "saas", {"auth", "sandbox", "market", "relay"}),
            ("desktop", "local", {"auth", "sandbox", "local-mcp", "market", "relay"}),
            ("server", "local", {"relay"}),  # market 配置判定 (server 自包含: 默认不连市场)
            ("tui", "local", set()),
        ],
    )
    def test_mode_matrix(self, monkeypatch, mode, expected_class, expected_caps):
        _clear_mode_env(monkeypatch)
        monkeypatch.setenv("DAWEI_RUNTIME_MODE", mode)

        from dawei.runtime import deployment_class, get_capabilities, runtime_mode

        assert runtime_mode() == mode
        assert deployment_class() == expected_class
        assert set(get_capabilities()) == expected_caps

    def test_server_mode_market_config_driven(self, monkeypatch):
        """server 自包含: 显式设 MARKET_API_URL 才注册 market capability"""
        _clear_mode_env(monkeypatch)
        monkeypatch.setenv("DAWEI_RUNTIME_MODE", "server")
        monkeypatch.setenv("MARKET_API_URL", "https://market.example.com")

        from dawei.runtime import get_capabilities

        assert "market" in get_capabilities()

    def test_workspace_store_s3_capability(self, monkeypatch):
        """WORKSPACE_STORE_BACKEND=rustfs → workspace-store-s3 capability"""
        _clear_mode_env(monkeypatch)
        monkeypatch.setenv("DAWEI_RUNTIME_MODE", "saas")
        monkeypatch.setenv("WORKSPACE_STORE_BACKEND", "rustfs")

        from dawei.runtime import get_capabilities

        assert "workspace-store-s3" in get_capabilities()

    def test_workspace_store_local_no_s3_capability(self, monkeypatch):
        _clear_mode_env(monkeypatch)
        monkeypatch.setenv("DAWEI_RUNTIME_MODE", "saas")
        monkeypatch.setenv("WORKSPACE_STORE_BACKEND", "local")

        from dawei.runtime import get_capabilities

        assert "workspace-store-s3" not in get_capabilities()


# ================================================================
# 2. 兼容回退 (DAWEI_DEPLOYMENT_MODE)
# ================================================================


class TestLegacyFallback:
    def test_legacy_saas(self, monkeypatch):
        _clear_mode_env(monkeypatch)
        monkeypatch.setenv("DAWEI_DEPLOYMENT_MODE", "saas")

        from dawei.runtime import deployment_class, runtime_mode

        assert runtime_mode() == "saas"
        assert deployment_class() == "saas"

    def test_legacy_local_maps_desktop(self, monkeypatch):
        _clear_mode_env(monkeypatch)
        monkeypatch.setenv("DAWEI_DEPLOYMENT_MODE", "local")

        from dawei.runtime import deployment_class, runtime_mode

        assert runtime_mode() == "desktop"
        assert deployment_class() == "local"

    def test_unset_defaults_desktop(self, monkeypatch):
        _clear_mode_env(monkeypatch)

        from dawei.runtime import deployment_class, runtime_mode

        assert runtime_mode() == "desktop"
        assert deployment_class() == "local"

    def test_legacy_invalid_maps_desktop(self, monkeypatch):
        """非法 DAWEI_DEPLOYMENT_MODE 历史行为按 local → desktop (class=local)"""
        _clear_mode_env(monkeypatch)
        monkeypatch.setenv("DAWEI_DEPLOYMENT_MODE", "cloud-ish")

        from dawei.runtime import deployment_class, runtime_mode

        assert runtime_mode() == "desktop"
        assert deployment_class() == "local"


# ================================================================
# 3/4. fail-fast 校验
# ================================================================


class TestFailFast:
    def test_conflicting_env_raises(self, monkeypatch):
        """RUNTIME_MODE=saas + DEPLOYMENT_MODE=local → boot 拒启"""
        _clear_mode_env(monkeypatch)
        monkeypatch.setenv("DAWEI_RUNTIME_MODE", "saas")
        monkeypatch.setenv("DAWEI_DEPLOYMENT_MODE", "local")

        from dawei.runtime import validate_environment

        with pytest.raises(RuntimeError, match="矛盾"):
            validate_environment()

    def test_conflicting_env_raises_reverse(self, monkeypatch):
        """RUNTIME_MODE=desktop + DEPLOYMENT_MODE=saas → boot 拒启"""
        _clear_mode_env(monkeypatch)
        monkeypatch.setenv("DAWEI_RUNTIME_MODE", "desktop")
        monkeypatch.setenv("DAWEI_DEPLOYMENT_MODE", "saas")

        from dawei.runtime import validate_environment

        with pytest.raises(RuntimeError, match="矛盾"):
            validate_environment()

    def test_consistent_env_passes(self, monkeypatch):
        """RUNTIME_MODE=server + DEPLOYMENT_MODE=local → 一致, 放行"""
        _clear_mode_env(monkeypatch)
        monkeypatch.setenv("DAWEI_RUNTIME_MODE", "server")
        monkeypatch.setenv("DAWEI_DEPLOYMENT_MODE", "local")

        from dawei.runtime import validate_environment

        info = validate_environment()
        assert info["mode"] == "server"
        assert info["deployment_class"] == "local"

    def test_invalid_runtime_mode_raises(self, monkeypatch):
        _clear_mode_env(monkeypatch)
        monkeypatch.setenv("DAWEI_RUNTIME_MODE", "cloud")

        from dawei.runtime import runtime_mode

        with pytest.raises(ValueError, match="DAWEI_RUNTIME_MODE"):
            runtime_mode()


# ================================================================
# 5. API 端点
# ================================================================


class TestRuntimeApi:
    @pytest.fixture
    def client(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from dawei.api import runtime_api

        app = FastAPI()
        app.include_router(runtime_api.router)
        return TestClient(app)

    def test_runtime_info_endpoint(self, client, monkeypatch):
        _clear_mode_env(monkeypatch)
        monkeypatch.setenv("DAWEI_RUNTIME_MODE", "desktop")

        resp = client.get("/api/runtime-info")
        assert resp.status_code == 200
        data = resp.json()
        assert data["mode"] == "desktop"
        assert data["deployment_class"] == "local"
        assert "sandbox" in data["capabilities"]
        assert "local-mcp" in data["capabilities"]

    def test_runtime_info_server_mode_no_sandbox(self, client, monkeypatch):
        """server 模式无 sandbox capability (多模式统一方案 §3)"""
        _clear_mode_env(monkeypatch)
        monkeypatch.setenv("DAWEI_RUNTIME_MODE", "server")

        data = client.get("/api/runtime-info").json()
        assert data["mode"] == "server"
        assert "sandbox" not in data["capabilities"]

    def test_legacy_deployment_mode_endpoint(self, monkeypatch):
        """旧端点是 deployment_class 的薄包装 (老前端不破坏)"""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from dawei.api import sandbox_system

        app = FastAPI()
        app.include_router(sandbox_system.router)
        client = TestClient(app)

        _clear_mode_env(monkeypatch)
        monkeypatch.setenv("DAWEI_RUNTIME_MODE", "desktop")
        assert client.get("/api/system/deployment-mode").json()["mode"] == "local"

        monkeypatch.setenv("DAWEI_RUNTIME_MODE", "saas")
        assert client.get("/api/system/deployment-mode").json()["mode"] == "saas"


# ================================================================
# 5.5 server/tui 无沙箱守卫 (多模式统一方案 §3 唯一缺口收口)
# ================================================================


class TestNoSandboxModes:
    @pytest.mark.parametrize("mode", ["server", "tui"])
    def test_mode_without_sandbox_rejects_provider(self, monkeypatch, mode):
        """server/tui 模式对任何 provider 创建显式报错, 不留隐式后门"""
        _clear_mode_env(monkeypatch)
        monkeypatch.setenv("DAWEI_RUNTIME_MODE", mode)

        from dawei.core.exceptions import SandboxError
        from dawei.sandbox.base import ProviderType
        from dawei.sandbox.provider_factory import create_provider

        with pytest.raises(SandboxError, match="未配置沙箱"):
            create_provider(ProviderType.DOCKER)


# ================================================================
# 6. provider_factory 委托
# ================================================================


class TestFactoryDelegation:
    def test_upstream_variable_wins(self, monkeypatch):
        """RUNTIME_MODE (上游) 优先于 DEPLOYMENT_MODE"""
        _clear_mode_env(monkeypatch)
        monkeypatch.setenv("DAWEI_RUNTIME_MODE", "saas")
        monkeypatch.setenv("DAWEI_DEPLOYMENT_MODE", "local")

        # 注: 此组合 validate_environment 会拒启, 但读取点本身以上游为准
        from dawei.sandbox.provider_factory import _deployment_mode

        assert _deployment_mode() == "saas"

    def test_runtime_mode_only(self, monkeypatch):
        _clear_mode_env(monkeypatch)
        monkeypatch.setenv("DAWEI_RUNTIME_MODE", "desktop")

        from dawei.sandbox.provider_factory import _deployment_mode

        assert _deployment_mode() == "local"


# ================================================================
# 7. 产物盖戳 (多模式统一方案 §L1: dawei/_mode_ + boot 比对拒启)
# ================================================================


class TestModeStamp:
    def test_stamp_missing_returns_none(self, tmp_path):
        """源码开发运行无戳 → None (不限制)"""
        from dawei.runtime import read_mode_stamp

        assert read_mode_stamp(tmp_path / "_mode_") is None

    def test_stamp_parses_comma_list_with_comments(self, tmp_path):
        stamp = tmp_path / "_mode_"
        stamp.write_text("# artifact stamp\nsaas, server\n", encoding="utf-8")

        from dawei.runtime import read_mode_stamp

        assert read_mode_stamp(stamp) == ["saas", "server"]

    def test_stamp_empty_file_treated_as_no_stamp(self, tmp_path):
        """空清单视为无戳 (容错, 不因空文件拒启所有模式)"""
        stamp = tmp_path / "_mode_"
        stamp.write_text("# only comments\n", encoding="utf-8")

        from dawei.runtime import read_mode_stamp

        assert read_mode_stamp(stamp) is None

    def test_boot_rejects_mode_outside_stamp(self, monkeypatch):
        """saas 盖戳的产物以 server 模式启动 → 拒启 (防隔离守卫被绕过)"""
        _clear_mode_env(monkeypatch)
        monkeypatch.setenv("DAWEI_RUNTIME_MODE", "server")
        monkeypatch.setattr("dawei.runtime.read_mode_stamp", lambda: ["saas"])

        from dawei.runtime import validate_environment

        with pytest.raises(RuntimeError, match="构建盖戳"):
            validate_environment()

    def test_boot_allows_mode_in_stamp(self, monkeypatch):
        _clear_mode_env(monkeypatch)
        monkeypatch.setenv("DAWEI_RUNTIME_MODE", "saas")
        monkeypatch.setattr("dawei.runtime.read_mode_stamp", lambda: ["saas"])

        from dawei.runtime import validate_environment

        info = validate_environment()
        assert info["mode"] == "saas"

    def test_boot_multi_mode_stamp(self, monkeypatch):
        """共享二进制多模式戳 (server,saas) — 任一允许模式可启"""
        _clear_mode_env(monkeypatch)
        monkeypatch.setattr("dawei.runtime.read_mode_stamp", lambda: ["server", "saas"])

        from dawei.runtime import validate_environment

        for mode in ("server", "saas"):
            monkeypatch.setenv("DAWEI_RUNTIME_MODE", mode)
            assert validate_environment()["mode"] == mode

    def test_source_tree_has_no_stamp(self):
        """仓库源码树必须无戳 (build-binary.py 构建后清理) — 否则开发运行被误限"""
        from pathlib import Path

        import dawei.runtime as rt

        assert (Path(rt.__file__).parent / rt.MODE_STAMP_FILENAME).exists() is False


# ================================================================
# 8. server 自包含身份 (auth cap / local-user / 可选访问密码)
# ================================================================


def _make_request(headers: dict[str, str] | None = None):
    """构造最小 starlette Request (auth.py 依赖注入函数直接消费)"""
    from starlette.requests import Request as StarletteRequest

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "query_string": b"",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
    }
    return StarletteRequest(scope)


class TestLocalUserAuth:
    """无 auth capability (server/tui) → 固定 local-user + DAWEI_SERVER_PASSWORD 可选校验"""

    def test_server_mode_no_password_passes_through(self, monkeypatch):
        """未设密码 → 直接放行, 固定身份 local-user"""
        _clear_mode_env(monkeypatch)
        monkeypatch.setenv("DAWEI_RUNTIME_MODE", "server")

        import asyncio

        from dawei.api.auth import get_authenticated_user_id

        assert asyncio.run(get_authenticated_user_id(_make_request())) == "local-user"

    def test_server_mode_password_missing_rejected(self, monkeypatch):
        _clear_mode_env(monkeypatch)
        monkeypatch.setenv("DAWEI_RUNTIME_MODE", "server")
        monkeypatch.setenv("DAWEI_SERVER_PASSWORD", "s3cret")

        import asyncio

        from fastapi import HTTPException

        from dawei.api.auth import get_authenticated_user_id

        with pytest.raises(HTTPException) as ei:
            asyncio.run(get_authenticated_user_id(_make_request()))
        assert ei.value.status_code == 401

    def test_server_mode_password_wrong_rejected(self, monkeypatch):
        _clear_mode_env(monkeypatch)
        monkeypatch.setenv("DAWEI_RUNTIME_MODE", "server")
        monkeypatch.setenv("DAWEI_SERVER_PASSWORD", "s3cret")

        import asyncio

        from fastapi import HTTPException

        from dawei.api.auth import get_authenticated_user_id

        with pytest.raises(HTTPException) as ei:
            asyncio.run(get_authenticated_user_id(_make_request({"Authorization": "Bearer wrong"})))
        assert ei.value.status_code == 401

    def test_server_mode_password_ok_returns_local_user(self, monkeypatch):
        _clear_mode_env(monkeypatch)
        monkeypatch.setenv("DAWEI_RUNTIME_MODE", "server")
        monkeypatch.setenv("DAWEI_SERVER_PASSWORD", "s3cret")

        import asyncio

        from dawei.api.auth import get_authenticated_user_id

        req = _make_request({"Authorization": "Bearer s3cret"})
        assert asyncio.run(get_authenticated_user_id(req)) == "local-user"

    def test_server_mode_tenant_personal(self, monkeypatch):
        """自包含模式无租户概念 → personal"""
        _clear_mode_env(monkeypatch)
        monkeypatch.setenv("DAWEI_RUNTIME_MODE", "server")

        import asyncio

        from dawei.api.auth import get_authenticated_tenant_id

        assert asyncio.run(get_authenticated_tenant_id(_make_request())) == "personal"

    def test_desktop_mode_still_requires_auth(self, monkeypatch):
        """有 auth capability 的模式行为不变: 无认证信息 → 401"""
        _clear_mode_env(monkeypatch)
        monkeypatch.setenv("DAWEI_RUNTIME_MODE", "desktop")

        import asyncio

        from fastapi import HTTPException

        from dawei.api.auth import get_authenticated_user_id

        with pytest.raises(HTTPException) as ei:
            asyncio.run(get_authenticated_user_id(_make_request()))
        assert ei.value.status_code == 401


# =============================================================================
# 9. AccessPasswordMiddleware — server 自包含访问密码门 (单点 ASGI 收口)
# =============================================================================


def _gate_app() -> "FastAPI":
    from fastapi import FastAPI, WebSocket

    from dawei.api.access_gate import AccessPasswordMiddleware

    app = FastAPI()
    app.add_middleware(AccessPasswordMiddleware)

    @app.get("/api/ping")
    async def _ping():  # type: ignore[misc]
        return {"ok": True}

    @app.get("/api/runtime-info")
    async def _runtime_info():  # type: ignore[misc]
        return {"mode": "server"}

    @app.get("/healthz")
    async def _healthz():  # type: ignore[misc]
        return {"ok": True}

    @app.websocket("/ws")
    async def _ws(websocket: WebSocket):  # type: ignore[misc]
        await websocket.accept()
        await websocket.send_text("hello")
        await websocket.close()

    return app


class TestAccessPasswordMiddleware:
    def test_server_mode_password_set_blocks_without_token(self, monkeypatch):
        _clear_mode_env(monkeypatch)
        monkeypatch.setenv("DAWEI_RUNTIME_MODE", "server")
        monkeypatch.setenv("DAWEI_SERVER_PASSWORD", "s3cret")

        from fastapi.testclient import TestClient

        with TestClient(_gate_app()) as client:
            assert client.get("/api/ping").status_code == 401
            assert client.get("/api/ping", headers={"Authorization": "Bearer wrong"}).status_code == 401
            assert client.get("/api/ping", headers={"Authorization": "Bearer s3cret"}).status_code == 200

    def test_runtime_info_exempt_and_non_api_paths_open(self, monkeypatch):
        _clear_mode_env(monkeypatch)
        monkeypatch.setenv("DAWEI_RUNTIME_MODE", "server")
        monkeypatch.setenv("DAWEI_SERVER_PASSWORD", "s3cret")

        from fastapi.testclient import TestClient

        with TestClient(_gate_app()) as client:
            assert client.get("/api/runtime-info").status_code == 200
            assert client.get("/healthz").status_code == 200

    def test_no_password_set_gate_inactive(self, monkeypatch):
        _clear_mode_env(monkeypatch)
        monkeypatch.setenv("DAWEI_RUNTIME_MODE", "server")
        monkeypatch.delenv("DAWEI_SERVER_PASSWORD", raising=False)

        from fastapi.testclient import TestClient

        with TestClient(_gate_app()) as client:
            assert client.get("/api/ping").status_code == 200

    def test_auth_capability_mode_gate_inactive(self, monkeypatch):
        """saas/desktop (有 auth cap) 设了密码也不启用简单密码门 — 走 JWT 体系"""
        _clear_mode_env(monkeypatch)
        monkeypatch.setenv("DAWEI_RUNTIME_MODE", "desktop")
        monkeypatch.setenv("DAWEI_SERVER_PASSWORD", "s3cret")

        from fastapi.testclient import TestClient

        with TestClient(_gate_app()) as client:
            assert client.get("/api/ping").status_code == 200

    def test_websocket_token_query_param(self, monkeypatch):
        """浏览器 WS 无法自定义 header → ?token= 查询参数"""
        _clear_mode_env(monkeypatch)
        monkeypatch.setenv("DAWEI_RUNTIME_MODE", "server")
        monkeypatch.setenv("DAWEI_SERVER_PASSWORD", "s3cret")

        from starlette.testclient import TestClient
        from starlette.websockets import WebSocketDisconnect

        with TestClient(_gate_app()) as client:
            with pytest.raises(WebSocketDisconnect):
                with client.websocket_connect("/ws"):
                    pass
            with client.websocket_connect("/ws?token=s3cret") as ws:
                assert ws.receive_text() == "hello"
