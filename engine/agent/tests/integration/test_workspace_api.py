"""
Integration tests for unified workspace API — creation → list → filter correctness.

Tests cover:
  - GET /api/workspaces/list — list all, filter by workspace_type, filter by workspace_category
  - GET /api/ip/workspace/list — IP-specific endpoint reads from unified index
  - workspace_category is a computed field (derived from workspace_type, not persisted)
  - WorkspaceLifecycle enum in responses

Run against running server:
    cd agent && uv run dawei server start --port 8010
    uv run pytest tests/integration/test_workspace_api.py -v -s

Note: These tests manipulate ~/.normnomos/workspaces.json directly and restore it.
"""

import json
import os
import time
from pathlib import Path

import httpx
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

BASE_URL = "http://localhost:8010"

# ── Direct storage manipulation (no API dependency for setup/teardown) ──

DAWEI_HOME = Path(os.environ.get("DAWEI_HOME", Path.home() / ".normnomos"))
WORKSPACES_JSON = DAWEI_HOME / "workspaces.json"


def _read_index() -> dict:
    """Read the current workspaces.json index."""
    if WORKSPACES_JSON.exists():
        return json.loads(WORKSPACES_JSON.read_text(encoding="utf-8"))
    return {"workspaces": [], "last_updated": None, "collections": []}


def _write_index(data: dict) -> None:
    """Write the workspaces.json index."""
    WORKSPACES_JSON.parent.mkdir(parents=True, exist_ok=True)
    WORKSPACES_JSON.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture(scope="module")
def saved_index():
    """Save original index before tests, restore after."""
    original = _read_index()
    yield
    # Restore original
    _write_index(original)


@pytest.fixture(scope="module")
def seed_workspaces(saved_index, tmp_path_factory):
    """Seed workspaces.json with test entries of various types.
    Creates real temp directories so the IP endpoint can validate paths."""
    now = time.time()
    tmp_root = tmp_path_factory.mktemp("ws-integration")

    def _make_ws(ws_id: str, ws_type: str, lifecycle: str, name: str, created_offset: int, access_offset: int) -> dict:
        ws_dir = tmp_root / ws_id
        ws_dir.mkdir(parents=True)
        dawei_dir = ws_dir / ".dawei"
        dawei_dir.mkdir()
        (dawei_dir / "workspace.json").write_text(json.dumps({
            "id": ws_id,
            "name": ws_id,
            "display_name": name,
            "workspace_type": ws_type,
            "lifecycle": lifecycle,
        }), encoding="utf-8")
        (dawei_dir / "files").mkdir(exist_ok=True)
        return {
            "id": ws_id,
            "name": ws_id,
            "path": str(ws_dir),
            "display_name": name,
            "workspace_type": ws_type,
            "lifecycle": lifecycle,
            "is_active": True,
            "created_at": now - created_offset,
            "last_accessed_at": now - access_offset,
        }

    entries = [
        _make_ws("test-user-ws", "user", "persistent", "我的通用工作区", 10000, 100),
        _make_ws("test-ip-idea", "ip-idea-vault", "temporary", "测试创意保险箱", 5000, 200),
        _make_ws("test-ip-draft", "ip-draft", "temporary", "测试专利撰写", 4000, 300),
        _make_ws("test-compliance-ws", "compliance", "persistent", "制裁合规项目", 3000, 400),
        _make_ws("test-simple-task", "simple_task", "temporary", "一次性任务", 2000, 500),
        _make_ws("test-portfolio", "ip-portfolio", "temporary", "资产管理", 1000, 600),
    ]
    _write_index({"workspaces": entries, "last_updated": None})
    yield entries


# ============================================================================
# Test: List all workspaces
# ============================================================================


class TestListAllWorkspaces:
    """GET /api/workspaces/list — returns all workspaces."""

    async def test_returns_all_seeded_workspaces(self, seed_workspaces):
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=httpx.Timeout(10)) as client:
            resp = await client.get("/api/workspaces/list")
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert data["total"] == len(seed_workspaces)
            assert len(data["workspaces"]) == len(seed_workspaces)

    async def test_each_workspace_has_workspace_category(self, seed_workspaces):
        """Every returned workspace must have the computed workspace_category field."""
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=httpx.Timeout(10)) as client:
            resp = await client.get("/api/workspaces/list")
            data = resp.json()
            for ws in data["workspaces"]:
                assert "workspace_category" in ws, (
                    f"workspace {ws['id']} missing workspace_category"
                )
                assert ws["workspace_category"] is not None

    async def test_category_not_in_raw_storage(self, seed_workspaces):
        """workspace_category must NOT exist in the raw workspaces.json — it's computed."""
        raw = _read_index()
        for ws in raw["workspaces"]:
            assert "workspace_category" not in ws, (
                f"workspace {ws['id']} has workspace_category in storage — should be computed only"
            )


# ============================================================================
# Test: Filter by workspace_type
# ============================================================================


class TestFilterByWorkspaceType:
    """GET /api/workspaces/list?workspace_type=..."""

    async def test_filter_user_type(self, seed_workspaces):
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=httpx.Timeout(10)) as client:
            resp = await client.get("/api/workspaces/list", params={"workspace_type": "user"})
            data = resp.json()
            assert data["total"] == 1
            assert data["workspaces"][0]["workspace_type"] == "user"
            assert data["workspaces"][0]["workspace_category"] == "general"

    async def test_filter_ip_idea_vault(self, seed_workspaces):
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=httpx.Timeout(10)) as client:
            resp = await client.get(
                "/api/workspaces/list", params={"workspace_type": "ip-idea-vault"}
            )
            data = resp.json()
            assert data["total"] == 1
            assert data["workspaces"][0]["workspace_type"] == "ip-idea-vault"
            assert data["workspaces"][0]["workspace_category"] == "ip"

    async def test_filter_compliance_type(self, seed_workspaces):
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=httpx.Timeout(10)) as client:
            resp = await client.get(
                "/api/workspaces/list", params={"workspace_type": "compliance"}
            )
            data = resp.json()
            assert data["total"] == 1
            assert data["workspaces"][0]["workspace_type"] == "compliance"
            assert data["workspaces"][0]["workspace_category"] == "compliance"

    async def test_filter_nonexistent_type(self, seed_workspaces):
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=httpx.Timeout(10)) as client:
            resp = await client.get(
                "/api/workspaces/list", params={"workspace_type": "nonexistent"}
            )
            data = resp.json()
            assert data["total"] == 0


# ============================================================================
# Test: Filter by workspace_category (computed, not persisted)
# ============================================================================


class TestFilterByWorkspaceCategory:
    """GET /api/workspaces/list?workspace_category=..."""

    async def test_filter_ip_category(self, seed_workspaces):
        """Filtering by ip category should return all ip-* types (3 seeded: idea, draft, portfolio)."""
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=httpx.Timeout(10)) as client:
            resp = await client.get(
                "/api/workspaces/list", params={"workspace_category": "ip"}
            )
            data = resp.json()
            assert data["total"] == 3, f"Expected 3 IP workspaces, got {data['total']}"
            for ws in data["workspaces"]:
                assert ws["workspace_type"].startswith("ip-"), (
                    f"Non-IP type in ip category filter: {ws['workspace_type']}"
                )
                assert ws["workspace_category"] == "ip"

    async def test_filter_general_category(self, seed_workspaces):
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=httpx.Timeout(10)) as client:
            resp = await client.get(
                "/api/workspaces/list", params={"workspace_category": "general"}
            )
            data = resp.json()
            assert data["total"] == 1
            assert data["workspaces"][0]["workspace_type"] == "user"

    async def test_filter_compliance_category(self, seed_workspaces):
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=httpx.Timeout(10)) as client:
            resp = await client.get(
                "/api/workspaces/list", params={"workspace_category": "compliance"}
            )
            data = resp.json()
            assert data["total"] == 1
            assert data["workspaces"][0]["workspace_type"] == "compliance"

    async def test_filter_ai_task_category(self, seed_workspaces):
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=httpx.Timeout(10)) as client:
            resp = await client.get(
                "/api/workspaces/list", params={"workspace_category": "ai_task"}
            )
            data = resp.json()
            assert data["total"] == 1
            assert data["workspaces"][0]["workspace_type"] == "simple_task"


# ============================================================================
# Test: IP-specific endpoint uses unified index
# ============================================================================


class TestIPEndpointUsesUnifiedIndex:
    """GET /api/ip/workspace/list — reads from unified index, NOT from temp_workspaces/."""

    async def test_returns_ip_workspaces(self, seed_workspaces):
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=httpx.Timeout(10)) as client:
            resp = await client.get("/api/ip/workspace/list")
            assert resp.status_code == 200
            data = resp.json()
            items = data.get("items", [])
            # All 3 seeded IP workspaces should appear
            assert len(items) == 3, f"Expected 3 IP workspaces, got {len(items)}"

    async def test_ip_items_have_workspace_category(self, seed_workspaces):
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=httpx.Timeout(10)) as client:
            resp = await client.get("/api/ip/workspace/list")
            data = resp.json()
            for item in data.get("items", []):
                assert "workspace_category" in item, (
                    f"IP item missing workspace_category: {item.get('id')}"
                )
                assert item["workspace_category"] == "ip"

    async def test_ip_filter_by_type(self, seed_workspaces):
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=httpx.Timeout(10)) as client:
            resp = await client.get(
                "/api/ip/workspace/list", params={"workspace_type": "ip-draft"}
            )
            data = resp.json()
            items = data.get("items", [])
            assert len(items) == 1
            assert items[0]["name"] == "测试专利撰写"  # IP endpoint returns display_name as name
            assert items[0]["workspaceType"] == "ip-draft"


# ============================================================================
# Test: Lifecycle filtering
# ============================================================================


class TestLifecycleFiltering:
    """GET /api/workspaces/list?lifecycle=..."""

    async def test_filter_temporary(self, seed_workspaces):
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=httpx.Timeout(10)) as client:
            resp = await client.get(
                "/api/workspaces/list", params={"lifecycle": "temporary"}
            )
            data = resp.json()
            # 3 IP + 1 simple_task = 4 temporary
            assert data["total"] == 4
            for ws in data["workspaces"]:
                assert ws["lifecycle"] == "temporary"

    async def test_filter_persistent(self, seed_workspaces):
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=httpx.Timeout(10)) as client:
            resp = await client.get(
                "/api/workspaces/list", params={"lifecycle": "persistent"}
            )
            data = resp.json()
            # user + compliance = 2 persistent
            assert data["total"] == 2
            for ws in data["workspaces"]:
                assert ws["lifecycle"] == "persistent"


# ============================================================================
# Test: Combined filters
# ============================================================================


class TestCombinedFilters:
    """Combine workspace_type + category + lifecycle filters."""

    async def test_ip_category_and_temporary(self, seed_workspaces):
        """All IP workspaces are temporary — intersection should return all 3."""
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=httpx.Timeout(10)) as client:
            resp = await client.get(
                "/api/workspaces/list",
                params={"workspace_category": "ip", "lifecycle": "temporary"},
            )
            data = resp.json()
            assert data["total"] == 3

    async def test_ip_category_and_persistent(self, seed_workspaces):
        """No IP workspace is persistent — intersection should return 0."""
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=httpx.Timeout(10)) as client:
            resp = await client.get(
                "/api/workspaces/list",
                params={"workspace_category": "ip", "lifecycle": "persistent"},
            )
            data = resp.json()
            assert data["total"] == 0
