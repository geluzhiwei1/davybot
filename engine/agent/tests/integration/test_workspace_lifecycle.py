# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""A1 — Workspace lifecycle (backend core).

Exercises the real workspace CRUD API end-to-end against a live server:
create → list → info → update → config/effective → delete.

Pairs with the existing test_workspace_api.py (which covers filtering of
pre-seeded entries); here we drive the full create→delete cycle.
"""

import uuid

import httpx
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

from tests.integration.conftest import TEST_PREFIX  # noqa: E402


@pytest.mark.asyncio
async def test_workspace_create_list_delete(client: httpx.AsyncClient, workspace):
    """A1.1/A1.3 — create via API, appears in list, gone after delete."""
    ws = workspace
    ws_id = ws["id"]
    assert ws_id, "created workspace has no id"

    # Appears in list
    listing = (await client.get("/api/workspaces/list")).json()
    ids = [w["id"] for w in listing.get("workspaces", [])]
    assert ws_id in ids, "created workspace missing from /list"

    # Delete is handled by the fixture teardown — verify deletion explicitly
    del_resp = await client.delete(f"/api/workspaces/{ws_id}")
    assert del_resp.status_code in (200, 204), del_resp.text

    listing2 = (await client.get("/api/workspaces/list")).json()
    assert ws_id not in [w["id"] for w in listing2.get("workspaces", [])], (
        "workspace still present after delete"
    )
    # Mark as deleted so the fixture's own teardown is a no-op
    ws["_deleted"] = True


@pytest.mark.asyncio
async def test_workspace_info_and_update(client: httpx.AsyncClient, workspace):
    """A1.2 — GET /{id}/info then PUT /{id} to rename."""
    ws_id = workspace["id"]

    info_resp = await client.get(f"/api/workspaces/{ws_id}/info")
    assert info_resp.status_code == 200, info_resp.text
    info = info_resp.json()
    info_ws = info.get("workspace", info)
    assert info_ws.get("id") == ws_id, f"info id mismatch: {info}"

    new_name = f"{TEST_PREFIX}renamed-{uuid.uuid4().hex[:6]}"
    upd = await client.put(f"/api/workspaces/{ws_id}", json={"display_name": new_name})
    assert upd.status_code == 200, upd.text
    # Re-read to confirm persistence (response wrapped in {success, workspace:{...}})
    info2 = (await client.get(f"/api/workspaces/{ws_id}/info")).json()
    info2_ws = info2.get("workspace", info2)
    assert info2_ws.get("id") == ws_id
    assert info2_ws.get("display_name") == new_name or info2_ws.get("name") == new_name, (
        f"rename did not persist: {info2_ws}"
    )


@pytest.mark.asyncio
async def test_workspace_config_shape(client: httpx.AsyncClient, workspace):
    """A1.4 — /config returns the leveled config envelope."""
    ws_id = workspace["id"]
    cfg = await client.get(f"/api/workspaces/{ws_id}/config")
    assert cfg.status_code == 200, cfg.text
    body = cfg.json()
    # config endpoint returns {success, config:{...}} or the config directly
    config = body.get("config", body)
    assert isinstance(config, dict)


@pytest.mark.asyncio
@pytest.mark.parametrize("eff", ["skills-tools", "memory", "knowledge"])
async def test_workspace_effective_endpoints(client: httpx.AsyncClient, workspace, eff):
    """A1.4 — override-or-inherit effective endpoints are reachable and shaped."""
    ws_id = workspace["id"]
    resp = await client.get(f"/api/workspaces/{ws_id}/{eff}/effective")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # effective endpoints return {success, default, override, effective}
    assert "effective" in body, f"{eff}/effective missing 'effective' key: {body}"
