# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""A5 — Skill system (backend core).

Workspace-scoped skill CRUD against the live server: list → create → read content
→ delete. Skills are written under {workspace}/.dawei/skills/, so each test uses
the temp workspace fixture.
"""

import uuid

import httpx
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

SKILL_CONTENT = """---
name: it-skill
description: integration test skill
---
# IT Skill
This skill exists only for the integration test suite.
"""


@pytest.mark.asyncio
async def test_skills_list(client: httpx.AsyncClient, workspace):
    """A5.1 — GET /api/skills/list returns a skills inventory (workspace-scoped)."""
    r = await client.get("/api/skills/list", params={"workspace_id": workspace["id"]})
    assert r.status_code == 200, r.text
    body = r.json()
    # Tolerate either {skills:[...]} or a bare list
    skills = body.get("skills") if isinstance(body, dict) else body
    assert isinstance(skills, list)


@pytest.mark.asyncio
async def test_skills_list_without_workspace_id_is_400(client: httpx.AsyncClient):
    """A5 regression — missing workspace_id returns 400, not a 500.

    Guards the fix for the old _auto_detect_workspace_id fallback that called the
    non-existent WorkspaceManager.get_active_workspace and crashed with 500.
    """
    r = await client.get("/api/skills/list")
    assert r.status_code == 400, f"expected 400 for missing workspace_id, got {r.status_code}: {r.text}"


@pytest.mark.asyncio
async def test_skill_create_read_delete(client: httpx.AsyncClient, workspace):
    """A5.2 — create a workspace skill, read its content, then delete it."""
    ws_id = workspace["id"]
    name = f"it-skill-{uuid.uuid4().hex[:6]}"

    # Create
    create = await client.post(
        "/api/skills/skill",
        params={"workspace_id": ws_id},
        json={"name": name, "description": "it", "content": SKILL_CONTENT, "scope": "workspace"},
    )
    assert create.status_code in (200, 201), create.text
    assert create.json().get("success", True)

    try:
        # Read content
        content = await client.get(
            f"/api/skills/skill/{name}/content", params={"workspace_id": ws_id}
        )
        assert content.status_code == 200, content.text
        body = content.json()
        text = body.get("content") if isinstance(body, dict) else str(body)
        assert "IT Skill" in text, f"skill content mismatch: {body}"
    finally:
        # Delete
        dele = await client.delete(f"/api/skills/skill/{name}", params={"workspace_id": ws_id})
        assert dele.status_code in (200, 204), dele.text

    # Gone: re-fetching content should 404
    again = await client.get(f"/api/skills/skill/{name}/content", params={"workspace_id": ws_id})
    assert again.status_code in (404, 422, 400), again.text
