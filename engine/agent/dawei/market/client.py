# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Self-contained HTTP client for the normnomos agent market API.

同名异物消歧：本模块是「资源市场」（装 skill/agent/mcp/knowledge/team）；
与 davybot-biz 的 market_tools.py（「市场情报」，BUSINESS_MARKET_API_URL →
market-flow 营销数据 API）无任何关系。

Talks directly to the nn-user-system ``agent_market`` service
(no default base — requires ``MARKET_API_URL`` or an explicit ``base_url=``).

Auth: caller-provided JWT only (same ``JWT_SECRET`` as nn-user-system).
No service-account login — the user's page-login token is forwarded as-is.

Contract (verified against prod):
- ``GET  /v1/market/resources?type=&page=&page_size=&search=`` -> {items,total,...}
- ``GET  /v1/market/resources/{id:path}``                       -> resource detail
- ``GET  /v1/market/resources/{id:path}/archive``               -> zip bytes (source dir)
- ``GET  /v1/market/agents/teams/hierarchy``                    -> {teams:[...]}

Resource ``id`` format is inconsistent across types (skills/agents use
``{org}/{slug}``, mcp/knowledge use ``{type}/{slug}``, team agents use
``{org}/{team}/{mode}``), so callers should ``resolve`` rather than construct ids.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from .models import CliExecutionError

logger = logging.getLogger(__name__)


class MarketClient:
    """Thin HTTP client for the agent market API. Token-only auth."""

    DEFAULT_BASE = ""  # E1: 无云端缺省 —— market 为可选集成，须显式 MARKET_API_URL/base_url

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.base = (base_url or os.getenv("MARKET_API_URL") or self.DEFAULT_BASE).rstrip("/")
        if not self.base:
            raise CliExecutionError(
                "config", 0,
                "MarketClient requires a base URL — set MARKET_API_URL "
                "to enable market integration (no cloud default).",
            )
        self._token = token or os.getenv("MARKET_API_TOKEN")
        if not self._token:
            raise CliExecutionError(
                "auth", 0,
                "MarketClient requires a token (user JWT). "
                "Pass token= or set MARKET_API_TOKEN.",
            )
        self._timeout = timeout
        self._http = httpx.Client(timeout=timeout, follow_redirects=True)

    # ── auth ──────────────────────────────────────────────────────────────

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """Issue a request under ``/v1/market``."""
        url = f"{self.base}/v1/market{path}"
        resp = self._http.request(method, url, headers=self._headers(), **kwargs)
        if resp.status_code == 401:
            raise CliExecutionError(
                path, 401, "market auth failed (token rejected/expired)"
            )
        if resp.status_code == 404:
            raise CliExecutionError(path, 404, resp.text[:200])
        if resp.status_code >= 400:
            raise CliExecutionError(path, resp.status_code, resp.text[:300])
        return resp

    # ── resource queries ──────────────────────────────────────────────────

    def list(
        self,
        resource_type: str | None = None,
        search: str | None = None,
        page: int = 1,
        page_size: int = 100,
    ) -> list[dict[str, Any]]:
        page_size = max(1, min(page_size, 100))
        params: dict[str, Any] = {"page": page, "page_size": page_size}
        if resource_type:
            params["type"] = resource_type
        if search:
            params["search"] = search
        data = self._request("GET", "/resources", params=params).json()
        return data.get("items", []) if isinstance(data, dict) else []

    def get(self, resource_id: str) -> dict[str, Any]:
        return self._request("GET", f"/resources/{quote(resource_id, safe='')}").json()

    def _list_all(self, resource_type: str, max_items: int = 500) -> list[dict[str, Any]]:
        """Page through every resource of a type."""
        items: list[dict[str, Any]] = []
        page = 1
        while len(items) < max_items:
            batch = self.list(resource_type=resource_type, page=page, page_size=100)
            if not batch:
                break
            items.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        return items

    def resolve(self, resource_type: str, slug: str) -> str | None:
        """Map a ``{type, slug}`` reference to the market resource id.

        【2026-09-14 收紧】精确匹配优先（slug / id 全等）；宽松回退（id 任意段 /
        name）仅在**唯一**命中时采用 —— 旧实现返回第一个命中, 同名资源跨团队时
        会静默装错包。多个不同 id 命中 → ValueError（歧义, FAST FAIL）。
        """
        slug = (slug or "").strip()
        if not slug:
            return None
        items = self._list_all(resource_type)

        # 1) 精确: slug 全等
        for item in items:
            if item.get("slug") == slug:
                return item.get("id") or ""
        # 2) 精确: id 全等
        for item in items:
            if item.get("id") == slug:
                return slug

        # 3) 宽松回退: id 任意段 / name —— 唯一命中才返回
        hits: set[str] = set()
        for item in items:
            rid = item.get("id") or ""
            candidates = {item.get("slug"), item.get("name"), *rid.split("/")}
            if slug in candidates and rid:
                hits.add(rid)
        if len(hits) == 1:
            return hits.pop()
        if len(hits) > 1:
            # 【2026-09-14 修复】多命中 ≠ 必然歧义: market 的 agent 资源按 mode
            # 粒度索引 (id = agent/{org}/{team}/{mode}, slug 字段为空), 团队级
            # 引用 (如 "review-team") 必然命中该团队全部 mode id —— 而任一 mode
            # 的 /archive 都返回整个团队源目录 (install_agents 依赖此语义),
            # 属**同一来源**而非歧义。仅当命中跨多个不同父目录(不同团队/来源,
            # 会装错包)时才 FAST FAIL。取 sorted 首个保证确定性。
            parents = {rid.rsplit("/", 1)[0] for rid in hits}
            if len(parents) == 1:
                return sorted(hits)[0]
            raise ValueError(
                f"ambiguous market reference: {resource_type}/{slug} -> {sorted(hits)}"
            )
        return None

    def download_zip(self, resource_id: str, dest_dir: str | Path) -> Path:
        """Download a resource's source directory as a zip via ``/archive``
        and write it to ``dest_dir``. Returns the zip path.

        Works for skills/agents/templates (and returns the whole team dir for
        a team agent). MCP has no useful archive — read ``get().extra_metadata``
        instead.
        """
        resp = self._request("GET", f"/resources/{quote(resource_id, safe='')}/archive")
        dest = Path(dest_dir)
        dest.mkdir(parents=True, exist_ok=True)
        zip_path = dest / f"{resource_id.replace('/', '_')}.zip"
        zip_path.write_bytes(resp.content)
        return zip_path

    def can_access(self, resource_ids: list[str]) -> dict[str, list[str]]:
        """Batch access pre-check via ``POST /resources/can-access``.

        Returns ``{"accessible": [...], "denied": [...]}`` — denied ids fail
        the team-scope/module visibility check and must not be installed.
        """
        resp = self._request("POST", "/resources/can-access", json=list(resource_ids))
        data = resp.json()
        return {
            "accessible": data.get("accessible", []),
            "denied": data.get("denied", []),
        }

    def team_hierarchy(self) -> list[dict[str, Any]]:
        """Return the flat list of teams from ``/agents/teams/hierarchy``."""
        data = self._request("GET", "/agents/teams/hierarchy").json()
        return data.get("teams", []) if isinstance(data, dict) else []
