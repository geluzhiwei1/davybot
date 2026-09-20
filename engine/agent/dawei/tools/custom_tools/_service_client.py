# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Authenticated HTTP client for multi-tenant business service tools.

Used by the kb-searcher / sanctions native tools. Reads the **current user's
JWT** from `local_context` (set per-request by the chat handler from
`user_message.metadata["auth_token"]`) and injects it as `Authorization: Bearer`
on every call. The JWT therefore never enters the LLM context, and each user's
request is isolated (multi-tenant).

Errors are raised as categorized exceptions so tools can surface friendly
messages (auth → re-login; server/network → retry-later) instead of leaking
raw HTTP noise.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from dawei.core import local_context


class ServiceError(Exception):
    """Base error for business service calls."""


class ServiceAuthError(ServiceError):
    """401/403 — token missing/expired or insufficient permission."""


class ServiceUnavailableError(ServiceError):
    """5xx / 429 / network / timeout — transient, retry later."""


class AuthenticatedServiceClient:
    """HTTP client that transparently injects the per-user JWT."""

    def __init__(self, base_url: str, *, timeout: float = 30.0, service_name: str = "service"):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.service_name = service_name

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        token = local_context.get_auth_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    async def get(self, path: str, *, params: dict | None = None, timeout: float | None = None) -> Any:
        return await self._request("GET", path, params=params, timeout=timeout)

    async def post(
        self,
        path: str,
        *,
        json_body: dict | None = None,
        params: dict | None = None,
        timeout: float | None = None,
    ) -> Any:
        return await self._request("POST", path, params=params, json_body=json_body, timeout=timeout)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json_body: dict | None = None,
        timeout: float | None = None,
    ) -> Any:
        if not self.base_url:
            raise ServiceUnavailableError(
                f"{self.service_name} 未配置（BUSINESS_*_API_URL 为空，业务服务集成默认关闭）"
            )
        url = f"{self.base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=timeout or self.timeout) as client:
                resp = await client.request(
                    method,
                    url,
                    params=params,
                    json=json_body if json_body is not None else None,
                    headers=self._headers(),
                )
        except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as e:
            raise ServiceUnavailableError(f"{self.service_name} 不可达：{type(e).__name__}") from e
        except httpx.HTTPError as e:
            raise ServiceUnavailableError(f"{self.service_name} 请求失败：{type(e).__name__}") from e

        status = resp.status_code
        if status in (401, 403):
            raise ServiceAuthError(f"{self.service_name} 认证失败（token 缺失/过期或无权限）")
        if status == 429:
            raise ServiceUnavailableError(f"{self.service_name} 请求过于频繁，请稍后重试")
        if status >= 500:
            raise ServiceUnavailableError(f"{self.service_name} 服务端错误 {status}")

        if status >= 400:
            # Other 4xx (bad params etc.) — surface a concise message.
            detail = (resp.text or "")[:300]
            return {"_error": f"HTTP {status}", "detail": detail}

        try:
            return resp.json()
        except ValueError:
            return {"_error": "non-JSON response", "detail": (resp.text or "")[:300]}


# ── Service base URLs (env-required; E1: no cloud default — unset = integration off,
#    each client fails fast with a clear message on first use) ──
# kb-searcher: API mounted at {base}/api/v1/legal/*
KB_SEARCHER_BASE_URL = os.environ.get(
    "BUSINESS_KB_SEARCHER_API_URL",
    "",
).rstrip("/")
# sanctions: API mounted at {base}/api/v1/*
SANCTIONS_BASE_URL = os.environ.get(
    "BUSINESS_SANCTIONS_API_URL",
    "",
).rstrip("/")
# normflow: API mounted at {base}/* (gateway rewrites /nnflow/api -> /api/v1)
NORMFLOW_BASE_URL = os.environ.get(
    "BUSINESS_NORFLOW_API_URL",
    "",
).rstrip("/")
# market-flow: API mounted at {base}/api/v1/* (nginx /marketflow/ → backend, no rewrite)
MARKET_BASE_URL = os.environ.get(
    "BUSINESS_MARKET_API_URL",
    "",
).rstrip("/")
# research-flow (gelu): API mounted at {base}/api/v1/* (科研审稿控制面, group "research")
RESEARCH_BASE_URL = os.environ.get(
    "BUSINESS_RESEARCHFLOW_API_URL",
    "",
).rstrip("/")

# Shared client instances (stateless — JWT read per-request from local_context).
kb_searcher_client = AuthenticatedServiceClient(KB_SEARCHER_BASE_URL, service_name="kb-searcher")
sanctions_client = AuthenticatedServiceClient(SANCTIONS_BASE_URL, service_name="sanctions")
normflow_client = AuthenticatedServiceClient(NORMFLOW_BASE_URL, service_name="normflow")
market_client = AuthenticatedServiceClient(MARKET_BASE_URL, service_name="market-flow")
research_client = AuthenticatedServiceClient(RESEARCH_BASE_URL, service_name="research-flow")
