# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""A8 — MCP servers & scheduled tasks (backend core).

Non-LLM contract paths that round out backend coverage:
  - MCP: list + override-or-inherit effective merge per workspace
  - Scheduled tasks: global list + workspace-scoped create/list/delete round-trip
    (a `delay` task with a far-future trigger never fires, so no LLM is invoked).
The standalone /memory router is not mounted in server_app; memory coverage lives
in test_workspace_lifecycle.py via /api/workspaces/{id}/memory/effective.
"""

import uuid

import httpx
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


# ── MCP ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mcp_servers_list(client: httpx.AsyncClient, workspace):
    """A8.1 — GET /api/workspaces/{id}/mcp-servers returns the server list."""
    ws_id = workspace["id"]
    r = await client.get(f"/api/workspaces/{ws_id}/mcp-servers")
    assert r.status_code == 200, r.text
    body = r.json()
    servers = body.get("servers") if isinstance(body, dict) else body
    assert isinstance(servers, list), f"unexpected mcp-servers shape: {body}"


@pytest.mark.asyncio
async def test_mcp_servers_effective(client: httpx.AsyncClient, workspace):
    """A8.2 — GET .../mcp-servers/effective returns the merged effective set."""
    ws_id = workspace["id"]
    r = await client.get(f"/api/workspaces/{ws_id}/mcp-servers/effective")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("success", True)
    # effective shape carries some iterable of merged servers
    eff = body.get("effective") if isinstance(body, dict) else None
    assert eff is not None, f"effective missing: {body}"


# ── Scheduled tasks ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_global_scheduled_tasks_list(client: httpx.AsyncClient):
    """A8.3 — GET /api/scheduled-tasks returns a paginated global list."""
    r = await client.get("/api/scheduled-tasks")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("success", True) is True
    assert isinstance(body.get("tasks"), list)
    assert isinstance(body.get("total"), int)


@pytest.mark.asyncio
async def test_workspace_scheduled_task_create_list_delete(client: httpx.AsyncClient, workspace):
    """A8.4 — workspace-scoped scheduled-task CRUD; task never fires (far-future delay)."""
    ws_id = workspace["id"]
    base = f"/api/workspaces/{ws_id}/scheduled-tasks"

    # List is reachable
    list_before = await client.get(base)
    assert list_before.status_code == 200, list_before.text

    # Create a delay task far in the future — it will not trigger during the test
    payload = {
        "name": f"it-task-{uuid.uuid4().hex[:6]}",
        "description": "integration test task",
        "schedule_type": "delay",
        "trigger_time": "2099-01-01T00:00:00Z",
        "execution_type": "message",
        "execution_data": {"message": "it-test-noop"},
    }
    create = await client.post(base, json=payload)
    assert create.status_code in (200, 201), create.text
    created = create.json()
    task = created.get("task") if isinstance(created, dict) else created
    task_id = task.get("id") or task.get("task_id")
    assert task_id, f"no task id in create response: {created}"

    try:
        # Appears in workspace list
        listing = (await client.get(base)).json()
        items = listing.get("tasks") if isinstance(listing, dict) else listing
        assert any((t.get("id") == task_id or t.get("task_id") == task_id) for t in items), (
            "created scheduled task not in list"
        )
    finally:
        # Delete
        dele = await client.delete(f"{base}/{task_id}")
        assert dele.status_code in (200, 204), dele.text

    # Gone from list
    listing2 = (await client.get(base)).json()
    items2 = listing2.get("tasks") if isinstance(listing2, dict) else listing2
    assert not any((t.get("id") == task_id or t.get("task_id") == task_id) for t in items2), (
        "scheduled task still present after delete"
    )
