# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""A4 — Tool / slash-command system (backend core).

GET /api/tools/commands lists builtin+system commands; /reload re-scans disk;
/execute runs a command. We assert listing + reload (non-destructive) and that
/execute is wired (a bogus command returns a controlled error, never a 500).
"""

import httpx
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.mark.asyncio
async def test_tools_list_commands(client: httpx.AsyncClient, workspace):
    """A4.1 — GET /api/tools/commands returns a command inventory."""
    r = await client.get("/api/tools/commands", params={"workspace": workspace["id"]})
    assert r.status_code == 200, r.text
    body = r.json()
    # Shape: { commands: [...], total: N } (or similar envelope)
    commands = body.get("commands") if isinstance(body, dict) else body
    assert commands is not None, f"unexpected commands shape: {body}"
    total = body.get("total") if isinstance(body, dict) else len(commands)
    assert total == len(commands)


@pytest.mark.asyncio
async def test_tools_reload(client: httpx.AsyncClient, workspace):
    """A4.3 — POST /api/tools/commands/reload succeeds and reports a count."""
    r = await client.post("/api/tools/commands/reload", params={"workspace": workspace["id"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("success") is True
    assert isinstance(body.get("total"), int)


@pytest.mark.asyncio
async def test_tools_execute_bogus_command_is_controlled(client: httpx.AsyncClient, workspace):
    """A4.2 (wiring) — executing a non-existent command must NOT crash the server (no 5xx)."""
    r = await client.post(
        "/api/tools/commands/execute",
        params={"command": "/__definitely_not_a_command__", "workspace": workspace["id"]},
    )
    assert r.status_code < 500, f"execute crashed server: {r.status_code} {r.text}"
