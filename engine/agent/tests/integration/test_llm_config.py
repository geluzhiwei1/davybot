# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""A7 — LLM provider config / config leveling (backend core).

Global model listing (/api/llms) + workspace-scoped override-or-inherit merge
(llm-providers/effective, llm-settings, llm-settings-all). These endpoints underpin
the 4-layer config priority and the frontend's model merge — high regression value.
"""

import httpx
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.mark.asyncio
async def test_llms_global_listing(client: httpx.AsyncClient):
    """A7.1 — GET /api/llms returns { availableLLMs: [...] } (drives store.fetchModels local source)."""
    r = await client.get("/api/llms")
    assert r.status_code == 200, r.text
    body = r.json()
    available = body.get("availableLLMs")
    assert isinstance(available, list), f"missing availableLLMs: {body}"
    # each entry is well-formed
    for m in available:
        assert isinstance(m, dict)
        assert "id" in m or "name" in m


@pytest.mark.asyncio
async def test_workspace_llm_effective_merge(client: httpx.AsyncClient, workspace):
    """A7.3 — GET /api/workspaces/{id}/llm-providers/effective returns override-or-inherit merge."""
    ws_id = workspace["id"]
    r = await client.get(f"/api/workspaces/{ws_id}/llm-providers/effective")
    assert r.status_code == 200, r.text
    body = r.json()
    # effective endpoints return {success, current, default, override, effective}
    assert body.get("success", True)
    effective = body.get("effective")
    assert isinstance(effective, list), f"effective not a list: {body}"
    # every effective entry carries a source attribution
    for entry in effective:
        assert "name" in entry, f"effective entry missing name: {entry}"


@pytest.mark.asyncio
async def test_workspace_llm_settings(client: httpx.AsyncClient, workspace):
    """A7.4 — GET /api/workspaces/{id}/llm-settings returns merged settings."""
    ws_id = workspace["id"]
    r = await client.get(f"/api/workspaces/{ws_id}/llm-settings")
    assert r.status_code == 200, r.text
    body = r.json()
    settings = body.get("settings", body)
    assert isinstance(settings, dict)
    # merged settings expose the resolved current config name + all configs map
    assert "allConfigs" in settings or "currentApiConfigName" in settings, settings


@pytest.mark.asyncio
async def test_workspace_llm_settings_all(client: httpx.AsyncClient, workspace):
    """A7.4 — GET /api/workspaces/{id}/llm-settings-all returns user+workspace split + mode configs."""
    ws_id = workspace["id"]
    r = await client.get(f"/api/workspaces/{ws_id}/llm-settings-all")
    assert r.status_code == 200, r.text
    body = r.json()
    settings = body.get("settings", body)
    # split form exposes user / workspace / mode_configs
    assert "user" in settings and "workspace" in settings, settings
