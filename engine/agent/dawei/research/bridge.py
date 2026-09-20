# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only
"""桥接层 —— 本地引擎 → gelu-research-flow 控制面(httpx)。

端点（P4 面）：POST /api/v1/journals/suggest（选刊推荐）/ POST /api/v1/submissions
（台账建行）/ PATCH /api/v1/submissions/{id}（状态机）/ POST …/format-check（格式自检）。
基址：环境变量 RESEARCH_CONTROL_URL（无云端缺省，E1；本地控制面设 http://localhost:8056）。
鉴权：优先级 X-Api-Key（服务账号）> Bearer（显式 auth_token，桌面 UI 透传登录态）
> 环境变量 RESEARCH_AUTH_TOKEN；本地 auth_dev 控制面仅 X-Tenant-Id 即可。
分工：用户会话内工具调用走 _service_client.research_client（每请求注入用户 JWT，
见 research_tools.py）；本桥接为服务账号/无会话通道（值班任务、编队回流等）。
"""

from __future__ import annotations

import os
from typing import Any

DEFAULT_BASE = ""  # E1: 无云端缺省 —— 须显式 RESEARCH_CONTROL_URL


def _base() -> str:
    base = os.getenv("RESEARCH_CONTROL_URL", DEFAULT_BASE).rstrip("/")
    if not base:
        raise RuntimeError(
            "RESEARCH_CONTROL_URL 未设置：research 控制面集成默认关闭（显式配置后启用）"
        )
    return base


def _headers(tenant_id: str, auth_token: str | None = None) -> dict[str, str]:
    """优先级与 social.bridge 一致：X-Api-Key（服务账号）> Bearer（桌面登录用户）。"""
    h = {"X-Tenant-Id": tenant_id, "Content-Type": "application/json"}
    key = os.getenv("RESEARCH_API_KEY", "")
    token = auth_token or os.getenv("RESEARCH_AUTH_TOKEN", "")
    if key:
        h["X-Api-Key"] = key
    elif token:
        h["Authorization"] = f"Bearer {token}"
    return h


def suggest_journals(payload: dict[str, Any], *, tenant_id: str, base_url: str | None = None, auth_token: str | None = None) -> dict[str, Any]:
    """选刊推荐（heuristic-v1 确定性打分，设计 §3.1 场景 C）。"""
    import httpx

    base = (base_url or _base()).rstrip("/")
    resp = httpx.post(f"{base}/api/v1/journals/suggest", json=payload, headers=_headers(tenant_id, auth_token), timeout=15.0)
    resp.raise_for_status()
    return resp.json()


def create_submission(payload: dict[str, Any], *, tenant_id: str, base_url: str | None = None, auth_token: str | None = None) -> dict[str, Any]:
    """投稿台账建行（status=preparing；paper_id 或 manuscript_kb_doc_id 二选一）。"""
    import httpx

    base = (base_url or _base()).rstrip("/")
    resp = httpx.post(f"{base}/api/v1/submissions", json=payload, headers=_headers(tenant_id, auth_token), timeout=15.0)
    resp.raise_for_status()
    return resp.json()


def get_submission(submission_id: str, *, tenant_id: str, base_url: str | None = None, auth_token: str | None = None) -> dict[str, Any]:
    """台账详情（含 journal_name 与 packages；跨租户 404）。"""
    import httpx

    base = (base_url or _base()).rstrip("/")
    resp = httpx.get(f"{base}/api/v1/submissions/{submission_id}", headers=_headers(tenant_id, auth_token), timeout=15.0)
    resp.raise_for_status()
    return resp.json()


def list_submissions(params: dict[str, Any] | None = None, *, tenant_id: str, base_url: str | None = None, auth_token: str | None = None) -> dict[str, Any]:
    """台账列表（可按 status / journal_id 过滤）。"""
    import httpx

    base = (base_url or _base()).rstrip("/")
    resp = httpx.get(f"{base}/api/v1/submissions", params=params or {}, headers=_headers(tenant_id, auth_token), timeout=15.0)
    resp.raise_for_status()
    return resp.json()


def update_submission(submission_id: str, payload: dict[str, Any], *, tenant_id: str, base_url: str | None = None, auth_token: str | None = None) -> dict[str, Any]:
    """台账更新/状态机迁移（非法迁移 409）。"""
    import httpx

    base = (base_url or _base()).rstrip("/")
    resp = httpx.patch(f"{base}/api/v1/submissions/{submission_id}", json=payload, headers=_headers(tenant_id, auth_token), timeout=15.0)
    resp.raise_for_status()
    return resp.json()


def generate_package(submission_id: str, payload: dict[str, Any], *, tenant_id: str, base_url: str | None = None, auth_token: str | None = None) -> dict[str, Any]:
    """包件生成/回流（cover_letter|highlights|manuscript|checklist|reviewer_response，同 kind 覆盖）。"""
    import httpx

    base = (base_url or _base()).rstrip("/")
    resp = httpx.post(f"{base}/api/v1/submissions/{submission_id}/packages/generate", json=payload, headers=_headers(tenant_id, auth_token), timeout=15.0)
    resp.raise_for_status()
    return resp.json()


def format_check(submission_id: str, payload: dict[str, Any], *, tenant_id: str, base_url: str | None = None, auth_token: str | None = None) -> dict[str, Any]:
    """格式自检（逐项命中刊物 requirement；结果落 checklist 包 format_check_json）。"""
    import httpx

    base = (base_url or _base()).rstrip("/")
    resp = httpx.post(f"{base}/api/v1/submissions/{submission_id}/format-check", json=payload, headers=_headers(tenant_id, auth_token), timeout=15.0)
    resp.raise_for_status()
    return resp.json()


__all__ = [
    "DEFAULT_BASE",
    "create_submission",
    "format_check",
    "generate_package",
    "get_submission",
    "list_submissions",
    "suggest_journals",
    "update_submission",
]
