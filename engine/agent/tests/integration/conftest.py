# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Integration test fixtures — Part A (backend core).

All tests here hit a **real running dawei server** (no mocking). Configure via:

    INTEGRATION_TARGET   HTTP base URL of the server  (default http://localhost:8431)
    INTEGRATION_TOKEN    Optional Bearer token (dev is usually auth-free)
    DAWEI_TEST_LLM       Set to "1" to enable LLM/embedding-dependent tests
                         (agent runs, KB search). Skipped otherwise — NOT mocked.
    DAWEI_TEST_PREFIX    Prefix for created test workspaces (default "it-")

Run:
    cd engine/agent
    uv run dawei server start --port 8431 --host 127.0.0.1
    uv run pytest tests/integration -v

If the server is unreachable, every module self-skips (no red).
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
import pytest

# ── Configuration ────────────────────────────────────────────────────
BASE_URL = os.environ.get("INTEGRATION_TARGET", "http://localhost:8010").rstrip("/")
WS_BASE_URL = BASE_URL.replace("http://", "ws://").replace("https://", "wss://")
TEST_PREFIX = os.environ.get("DAWEI_TEST_PREFIX", "it-")
LLM_ENABLED = os.environ.get("DAWEI_TEST_LLM", "") == "1"
_AUTH_HEADERS = (
    {"Authorization": f"Bearer {os.environ['INTEGRATION_TOKEN']}"}
    if os.environ.get("INTEGRATION_TOKEN")
    else {}
)


# ── Server reachability (session-scoped, evaluated once) ────────────
def _server_reachable() -> bool:
    """Probe several read-only endpoints; True if any answers 2xx/4xx (not connect-refused)."""
    probes = ["/api/workspaces/list", "/api/system/info", "/api/knowledge/bases"]
    for path in probes:
        try:
            r = httpx.get(f"{BASE_URL}{path}", headers=_AUTH_HEADERS, timeout=3.0)
            if r.status_code < 500:
                return True
        except Exception:
            continue
    return False


_SERVER_UP: bool | None = None


def server_is_up() -> bool:
    global _SERVER_UP
    if _SERVER_UP is None:
        _SERVER_UP = _server_reachable()
        if not _SERVER_UP:
            print(f"\n[integration] Server not reachable at {BASE_URL} — skipping live tests")
    return _SERVER_UP


skip_if_no_server = pytest.mark.skipif(not server_is_up(), reason=f"no server at {BASE_URL}")
skip_if_no_llm = pytest.mark.skipif(
    not (server_is_up() and LLM_ENABLED),
    reason="set DAWEI_TEST_LLM=1 with a running model backend to exercise LLM/embedding paths",
)


@pytest.fixture(autouse=True)
def _skip_when_server_down():
    """Auto-skip every integration test if the live server is unreachable."""
    if not server_is_up():
        pytest.skip(f"no server at {BASE_URL}")


# ── HTTP client ──────────────────────────────────────────────────────
@pytest.fixture
async def client():
    """Async HTTP client bound to the live server, with optional auth."""
    async with httpx.AsyncClient(base_url=BASE_URL, headers=_AUTH_HEADERS, timeout=30.0) as c:
        yield c


# ── Workspace factory (real API create + guaranteed cleanup) ─────────
@pytest.fixture
async def workspace(client: httpx.AsyncClient) -> dict[str, Any]:
    """Create a temporary workspace via the real API; delete it after the test.

    Uses POST /api/workspaces/create-temp (no on-disk path required).
    Returns the created workspace dict (contains id/name/display_name/lifecycle).
    """
    display = f"{TEST_PREFIX}{uuid.uuid4().hex[:8]}"
    resp = await client.post("/api/workspaces/create-temp", json={"display_name": display})
    assert resp.status_code == 201, f"create-temp failed: {resp.status_code} {resp.text}"
    body = resp.json()
    ws = body.get("workspace", body)
    ws_id = ws["id"]
    try:
        yield ws
    finally:
        try:
            await client.delete(f"/api/workspaces/{ws_id}")
        except Exception:
            pass


@pytest.fixture
async def cleanup_leaked_workspaces(client: httpx.AsyncClient):
    """Best-effort: remove any leftover workspaces from a previous aborted run."""
    yield
    try:
        resp = await client.get("/api/workspaces/list")
        for ws in resp.json().get("workspaces", []):
            if str(ws.get("name", "")).startswith(TEST_PREFIX) or str(ws.get("id", "")).startswith(TEST_PREFIX):
                await client.delete(f"/api/workspaces/{ws['id']}")
    except Exception:
        pass


# ── LLM / embedding gate ─────────────────────────────────────────────
@pytest.fixture
def require_llm():
    """Skip the test when no model backend is opted in."""
    if not (server_is_up() and LLM_ENABLED):
        pytest.skip("DAWEI_TEST_LLM not set — LLM/embedding path not exercised")


# ── WebSocket helper (lazy import — websockets is an optional dev dep) ─
class WSRecorder:
    """Minimal async context around a WebSocket that collects typed messages."""

    def __init__(self, url: str):
        self.url = url
        self._ws = None
        self.messages: list[dict] = []
        self._task: asyncio.Task | None = None

    async def __aenter__(self):
        try:
            import websockets  # type: ignore
        except ImportError as e:  # pragma: no cover
            pytest.skip(f"websockets not installed: {e}")
        self._ws = await websockets.connect(self.url, max_size=2**22, open_timeout=10)
        self._task = asyncio.create_task(self._pump())
        return self

    async def __aexit__(self, *exc):
        if self._task:
            self._task.cancel()
        if self._ws:
            await self._ws.close()
        return False

    async def _pump(self):
        try:
            async for raw in self._ws:
                import json as _json
                try:
                    self.messages.append(_json.loads(raw))
                except Exception:
                    pass
        except Exception:
            pass

    async def send(self, payload: dict):
        import json as _json
        await self._ws.send(_json.dumps(payload))

    def wait_for(self, predicate, timeout: float = 60.0) -> dict | None:
        """Block (sync) until a message matches predicate or timeout."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            for m in self.messages:
                try:
                    if predicate(m):
                        return m
                except Exception:
                    continue
            time.sleep(0.1)
        return None


@pytest.fixture
async def ws(workspace: dict):
    """Opened WebSocket to the test workspace. Requires `require_llm` flow upstream."""
    async with WSRecorder(f"{WS_BASE_URL}/ws?workspace_id={workspace['id']}") as rec:
        yield rec
