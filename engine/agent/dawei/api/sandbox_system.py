# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""沙箱系统级 API — 供前端安全设置页面调用

端点清单:
  GET  /api/system/sandbox/providers         — 列出所有 Provider 及可用性
  GET  /api/system/sandbox/capabilities       — 查询指定 Provider 能力
  GET  /api/system/deployment-mode            — 部署模式 (local / saas)
  POST /api/sandbox/test-connection           — 测试指定 Provider 连通性
  GET  /api/sandbox/quota                     — 当前用户配额
  GET  /api/sandbox/network-policy            — 网络策略
  GET  /api/sandbox/session/{workspace_id}    — 工作区沙箱会话状态
"""
import logging
import os
import time
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sandbox-system"])


# ================================================================
# Response Models
# ================================================================


class ProviderHealthItem(BaseModel):
    provider: str
    available: bool
    latency_ms: int | None = None
    error: str | None = None


class ProvidersResponse(BaseModel):
    success: bool
    providers: list[ProviderHealthItem]


class CapabilitiesResponse(BaseModel):
    success: bool
    capabilities: dict[str, Any]


class DeploymentModeResponse(BaseModel):
    mode: str  # "local" | "saas"


class TestConnectionRequest(BaseModel):
    provider: str


class TestConnectionResult(BaseModel):
    ok: bool
    latency_ms: int | None = None
    error: str | None = None


class TestConnectionResponse(BaseModel):
    success: bool
    result: TestConnectionResult


class QuotaDimension(BaseModel):
    used: int
    limit: int


class QuotaUsage(BaseModel):
    sessions: QuotaDimension
    memory_mb: QuotaDimension
    rate_per_min: QuotaDimension


class QuotaResponse(BaseModel):
    success: bool
    quota: QuotaUsage


class NetworkPolicy(BaseModel):
    name: str
    version: int
    default_action: str  # "allow" | "deny"
    allowed_domains: list[str]
    denied_domains: list[str]


class NetworkPolicyResponse(BaseModel):
    success: bool
    policy: NetworkPolicy


class SandboxSessionInfo(BaseModel):
    status: str  # "active" | "idle" | "none"
    provider: str
    created_at: str
    last_active: str
    queue_size: int


class SessionResponse(BaseModel):
    success: bool
    session: SandboxSessionInfo


# ================================================================
# Endpoints
# ================================================================


@router.get("/api/system/sandbox/providers", response_model=ProvidersResponse)
async def list_providers() -> ProvidersResponse:
    """列出当前部署模式可用的沙箱 Provider 及其健康状态

    按模式过滤 (2026-09-19 简化决策, 与 provider_factory 守卫一致):
    - local (PC App): 仅 docker (Podman 兼容) + auto
    - saas:          仅 e2b (CubeSandbox) + auto
    """
    from dawei.sandbox.provider_factory import (
        _auto_detect,
        _check_docker_available,
        _check_e2b_available,
        _deployment_mode,
    )

    items: list[ProviderHealthItem] = []
    mode = _deployment_mode()

    if mode == "saas":
        # E2B / CubeSandbox (saas 专属)
        api_url = os.environ.get("DAWEI_SANDBOX_API_URL", "").strip()
        if api_url:
            t0 = time.monotonic()
            ok = _check_e2b_available(api_url)
            ms = max(1, int((time.monotonic() - t0) * 1000))
            items.append(
                ProviderHealthItem(
                    provider="e2b",
                    available=ok,
                    latency_ms=ms if ok else None,
                    error=None if ok else f"unreachable: {api_url}",
                )
            )
        else:
            items.append(
                ProviderHealthItem(provider="e2b", available=False, error="DAWEI_SANDBOX_API_URL not set")
            )
    else:
        # local (PC App): 仅 Docker/Podman
        t0 = time.monotonic()
        ok = _check_docker_available()
        ms = max(1, int((time.monotonic() - t0) * 1000))
        items.append(
            ProviderHealthItem(
                provider="docker",
                available=ok,
                latency_ms=ms if ok else None,
                error=None if ok else "docker/podman not available (PC App 版仅支持 Docker/Podman)",
            )
        )

    # Auto — 报告 auto-detect 的选择; 检测失败也返回显式错误而非 500
    try:
        auto_choice = _auto_detect()
        items.append(ProviderHealthItem(provider="auto", available=True, error=f"would select: {auto_choice.value}"))
    except Exception as e:  # SandboxError / SandboxSecurityError
        items.append(ProviderHealthItem(provider="auto", available=False, error=str(e)))

    return ProvidersResponse(success=True, providers=items)


@router.get("/api/system/sandbox/capabilities", response_model=CapabilitiesResponse)
async def get_capabilities(
    provider: str = Query(default="auto"),
) -> CapabilitiesResponse:
    """查询指定 Provider 的能力声明"""
    from dawei.sandbox.base import ProviderType, SandboxCapabilities

    caps_map: dict[str, SandboxCapabilities] = {
        "subprocess": SandboxCapabilities(
            isolation_level="none",
            supports_network=True,
            supports_filesystem=True,
            supports_pause=False,
            max_timeout=300,
            cold_start_ms=0,
        ),
        "docker": SandboxCapabilities(
            isolation_level="container",
            supports_network=True,
            supports_filesystem=True,
            supports_pause=True,
            max_timeout=600,
            cold_start_ms=500,
        ),
        "e2b": SandboxCapabilities(
            isolation_level="hardware",
            supports_network=True,
            supports_filesystem=True,
            supports_pause=True,
            max_timeout=1800,
            cold_start_ms=60,
        ),
    }

    if provider == "auto":
        from dawei.sandbox.provider_factory import _auto_detect

        provider = _auto_detect().value

    caps = caps_map.get(provider, caps_map["subprocess"])
    return CapabilitiesResponse(
        success=True,
        capabilities={
            "isolation_level": caps.isolation_level.value if hasattr(caps.isolation_level, "value") else str(caps.isolation_level),
            "max_timeout_s": caps.max_timeout,
            "cold_start_ms": caps.cold_start_ms,
            "supports_network": caps.supports_network,
            "supports_filesystem": caps.supports_filesystem,
            "supports_pause": caps.supports_pause,
        },
    )


@router.get("/api/system/deployment-mode", response_model=DeploymentModeResponse)
async def get_deployment_mode() -> DeploymentModeResponse:
    """部署模式 (兼容端点): deployment_class 的薄包装。

    新消费方请改用 GET /api/runtime-info (mode + capabilities)。
    """
    from dawei.runtime import deployment_class

    return DeploymentModeResponse(mode=deployment_class())


@router.post("/api/sandbox/test-connection", response_model=TestConnectionResponse)
async def test_connection(req: TestConnectionRequest) -> TestConnectionResponse:
    """测试指定 Provider 的连通性"""
    from dawei.sandbox.provider_factory import (
        _auto_detect,
        _check_docker_available,
        _check_e2b_available,
    )

    provider = req.provider.lower().strip()

    # auto: detect which provider would be selected, then test that one
    if provider == "auto":
        t0 = time.monotonic()
        detected = _auto_detect()
        detected_name = detected.value

        # test the detected provider
        if detected_name == "e2b":
            api_url = os.environ.get("DAWEI_SANDBOX_API_URL", "").strip()
            ok = _check_e2b_available(api_url) if api_url else False
            ms = max(1, int((time.monotonic() - t0) * 1000))
            return TestConnectionResponse(
                success=True,
                result=TestConnectionResult(
                    ok=ok, latency_ms=ms,
                    error=None if ok else f"auto→e2b unreachable: {api_url or 'no URL'}",
                ),
            )
        elif detected_name == "docker":
            ok = _check_docker_available()
            ms = max(1, int((time.monotonic() - t0) * 1000))
            return TestConnectionResponse(
                success=True,
                result=TestConnectionResult(
                    ok=ok, latency_ms=ms,
                    error=None if ok else "auto→docker/podman not available",
                ),
            )
        else:
            # subprocess — always available
            ms = max(1, int((time.monotonic() - t0) * 1000))
            return TestConnectionResponse(
                success=True,
                result=TestConnectionResult(ok=True, latency_ms=ms),
            )

    t0 = time.monotonic()

    if provider == "e2b":
        api_url = os.environ.get("DAWEI_SANDBOX_API_URL", "").strip()
        if not api_url:
            return TestConnectionResponse(
                success=True,
                result=TestConnectionResult(ok=False, error="DAWEI_SANDBOX_API_URL not set"),
            )
        ok = _check_e2b_available(api_url)
        ms = max(1, int((time.monotonic() - t0) * 1000))
        return TestConnectionResponse(
            success=True,
            result=TestConnectionResult(
                ok=ok, latency_ms=ms, error=None if ok else f"unreachable: {api_url}"
            ),
        )

    if provider == "docker":
        ok = _check_docker_available()
        ms = max(1, int((time.monotonic() - t0) * 1000))
        return TestConnectionResponse(
            success=True,
            result=TestConnectionResult(
                ok=ok, latency_ms=ms, error=None if ok else "docker/podman not available"
            ),
        )

    if provider == "subprocess":
        ms = max(1, int((time.monotonic() - t0) * 1000))
        return TestConnectionResponse(
            success=True,
            result=TestConnectionResult(ok=True, latency_ms=ms),
        )

    return TestConnectionResponse(
        success=True,
        result=TestConnectionResult(ok=False, error=f"unknown provider: {provider}"),
    )


@router.get("/api/sandbox/quota", response_model=QuotaResponse)
async def get_quota() -> QuotaResponse:
    """返回当前用户沙箱配额（本地部署返回宽松默认值）"""
    return QuotaResponse(
        success=True,
        quota=QuotaUsage(
            sessions=QuotaDimension(used=0, limit=10),
            memory_mb=QuotaDimension(used=0, limit=4096),
            rate_per_min=QuotaDimension(used=0, limit=60),
        ),
    )


@router.get("/api/sandbox/network-policy", response_model=NetworkPolicyResponse)
async def get_network_policy() -> NetworkPolicyResponse:
    """返回网络策略（本地部署返回默认 allow-all）"""
    return NetworkPolicyResponse(
        success=True,
        policy=NetworkPolicy(
            name="default-local",
            version=1,
            default_action="allow",
            allowed_domains=[],
            denied_domains=[],
        ),
    )


@router.get("/api/sandbox/session/{workspace_id}", response_model=SessionResponse)
async def get_session(workspace_id: str) -> SessionResponse:
    """返回指定工作区的沙箱会话状态"""
    # 本地部署下, 沙箱会话是按需创建的, 默认返回 idle
    provider_name = "auto"
    try:
        from dawei.sandbox.sandbox_facade import SandboxFacade

        p = SandboxFacade.get_provider()
        provider_name = p.__class__.__name__.replace("Provider", "").lower()
    except Exception:
        pass

    return SessionResponse(
        success=True,
        session=SandboxSessionInfo(
            status="idle",
            provider=provider_name,
            created_at="",
            last_active="",
            queue_size=0,
        ),
    )
