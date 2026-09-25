"""桥接层 —— 本地引擎 → social-control 控制面(httpx)。

端点:POST /api/v1/contents(落盘)/ POST /api/v1/governance/rule-check(发布前预检)。
基址:环境变量 SOCIAL_CONTROL_URL(无云端缺省,E1;本地控制面设 http://localhost:8030)。
鉴权:prod 控制面 SC_AUTH_DEV=false,须 Bearer JWT —— 显式入参 auth_token(桌面 UI 透传
登录态)优先,回落环境变量 SOCIAL_AUTH_TOKEN / SOCIAL_API_KEY(由启动方注入,不落盘);
本地 auth_dev 控制面仅 X-Tenant-Id 即可。
"""

from __future__ import annotations

import os
from typing import Any

DEFAULT_BASE = ""  # E1: 无云端缺省 —— 须显式 SOCIAL_CONTROL_URL


def _base() -> str:
    base = os.getenv("SOCIAL_CONTROL_URL", DEFAULT_BASE).rstrip("/")
    if not base:
        raise RuntimeError(
            "SOCIAL_CONTROL_URL 未设置：social 控制面集成默认关闭（显式配置后启用）"
        )
    return base


def _headers(tenant_id: str, auth_token: str | None = None) -> dict[str, str]:
    """优先级与 browser_track._auth_headers 一致:X-Api-Key(服务账号)> Bearer(桌面登录用户)。"""
    h = {"X-Tenant-Id": tenant_id, "Content-Type": "application/json"}
    key = os.getenv("SOCIAL_API_KEY", "")
    token = auth_token or os.getenv("SOCIAL_AUTH_TOKEN", "")
    if key:
        h["X-Api-Key"] = key
    elif token:
        h["Authorization"] = f"Bearer {token}"
    return h


def push_artifact(payload: dict[str, Any], *, tenant_id: str, base_url: str | None = None) -> dict[str, Any]:
    """内容载荷落盘控制面 → 返回创建的 content。"""
    import httpx

    base = (base_url or _base()).rstrip("/")
    resp = httpx.post(f"{base}/api/v1/contents", json=payload, headers=_headers(tenant_id), timeout=15.0)
    resp.raise_for_status()
    return resp.json()


def precheck_rules(text: str, *, tenant_id: str, base_url: str | None = None,
                   auth_token: str | None = None) -> dict[str, Any]:
    """发布前本地预检(调用控制面规则引擎,编辑器侧实时标注同源)。"""
    import httpx

    base = (base_url or _base()).rstrip("/")
    resp = httpx.post(
        f"{base}/api/v1/governance/rule-check",
        json={"text": text}, headers=_headers(tenant_id, auth_token), timeout=15.0,
    )
    resp.raise_for_status()
    return resp.json()


def get_content(content_id: str, *, tenant_id: str, base_url: str | None = None,
                auth_token: str | None = None) -> dict[str, Any]:
    """读取单条内容工件(social_read_draft 工具数据源;A-M1 编辑器会话)。"""
    import httpx

    base = (base_url or _base()).rstrip("/")
    resp = httpx.get(f"{base}/api/v1/contents/{content_id}",
                     headers=_headers(tenant_id, auth_token), timeout=15.0)
    resp.raise_for_status()
    return resp.json()


__all__ = ["push_artifact", "precheck_rules", "get_content", "DEFAULT_BASE"]


def fetch_trending(*, tenant_id: str, base_url: str | None = None, auth_token: str | None = None) -> list[dict[str, Any]]:
    """拉取控制面当日热点(值班任务输入)。"""
    import httpx

    base = (base_url or _base()).rstrip("/")
    resp = httpx.get(f"{base}/api/v1/trending/items",
                     headers=_headers(tenant_id, auth_token), timeout=15.0)
    resp.raise_for_status()
    return resp.json().get("items", [])


def post_idea(idea: dict[str, Any], *, brand_id: str, tenant_id: str,
              base_url: str | None = None, auth_token: str | None = None) -> dict[str, Any]:
    """选题卡入库(值班 Agent 产出 → 控制面)。"""
    import httpx

    base = (base_url or _base()).rstrip("/")
    payload = {"brand_id": brand_id, **{k: idea[k] for k in (
        "title", "angle", "reasoning", "relevance_score", "timeliness", "trending_item_ids") if k in idea}}
    resp = httpx.post(f"{base}/api/v1/trending/ideas", json=payload,
                      headers=_headers(tenant_id, auth_token), timeout=15.0)
    resp.raise_for_status()
    return resp.json()
