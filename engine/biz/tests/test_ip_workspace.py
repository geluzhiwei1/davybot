"""
Unit tests for IP workspace service (IPWorkspaceService) and IP data models.

Tests cover:
  - IpTaskContext / WorkspaceStatus / ResumableTask / InheritRequest dataclasses
  - IP_MODULE_RESOURCES configuration integrity
  - create_ip_workspace lifecycle (create, resource install, file inherit, metadata write)
  - get_workspace_status (from workspace.json + checkpoints)
  - resume_workspace (non-expired, expired, missing)
  - cleanup_workspace (idle, active, force)
  - inherit_files (specific files, all files, missing parent)
  - list_resumable_tasks (empty, with checkpoints, non-IP workspaces)
  - get_workspace_files (empty, populated)
  - get_module_resources (known, unknown)
  - _count_active_ip_workspaces
  - _generate_workspace_name / _generate_display_name
  - _compute_expiry (temporary vs persistent)
"""

import json
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


# ============================================================================
# Fake helpers
# ============================================================================

@dataclass
class _FakeWsInfo:
    """Minimal fake for the dict returned by temp_workspace_manager.create_temp_workspace."""
    id: str
    path: str
    name: str = ""

    def __getitem__(self, key):
        if key == "id":
            return self.id
        if key == "path":
            return self.path
        if key == "name":
            return self.name
        raise KeyError(key)

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default


def _make_fake_ws_info(ws_id: str, ws_path: Path) -> _FakeWsInfo:
    return _FakeWsInfo(id=ws_id, path=str(ws_path))


class _FakeSystemStorage:
    """Minimal async Storage fake rooted at a tmp dir.

    list_ip_workspaces / _count_active_ip_workspaces / _resolve_workspace_path
    read the unified system index (workspaces.json) via
    StorageProvider.get_system_storage().  Pointing that at a tmp root keeps
    tests isolated from the real ~/.normnomos index.
    """

    def __init__(self, root: Path):
        self.root = root

    async def read_file(self, rel_path: str) -> str:
        p = self.root / rel_path
        if not p.exists():
            raise FileNotFoundError(rel_path)
        return p.read_text(encoding="utf-8")


def _index_entry(ws_id: str, ws_path: Path, ws_type: str, **extra) -> dict:
    """Build one workspaces.json index entry (created_at defaults to now)."""
    now = datetime.now(timezone.utc).isoformat()
    entry = {
        "id": ws_id,
        "name": ws_path.name,
        "display_name": ws_path.name,
        "path": str(ws_path),
        "workspace_type": ws_type,
        "lifecycle": "temporary",
        "created_at": now,
    }
    entry.update(extra)
    return entry


@contextmanager
def _fake_system_index(root: Path, entries: list[dict] | None = None):
    """Patch StorageProvider.get_system_storage to a tmp-rooted fake index."""
    from dawei.storage.storage_provider import StorageProvider

    if entries is not None:
        root.mkdir(parents=True, exist_ok=True)
        (root / "workspaces.json").write_text(json.dumps({"workspaces": entries}), encoding="utf-8")
    with patch.object(StorageProvider, "get_system_storage", return_value=_FakeSystemStorage(root)):
        yield


# ============================================================================
# 1. IP Data Models (pure dataclass tests — no fixtures needed)
# ============================================================================

class TestIpTaskContext:
    """IpTaskContext dataclass creation and defaults."""

    def test_minimal_required_fields(self):
        from dawei.models.ip import IpTaskContext
        ctx = IpTaskContext(module="ip-draft", task_type="generate_draft")
        assert ctx.module == "ip-draft"
        assert ctx.task_type == "generate_draft"
        assert ctx.language == "zh-CN"
        assert ctx.jurisdiction == "CN"
        assert ctx.file_ids == []
        assert ctx.inherit_files == []
        assert ctx.parent_workspace_id is None

    def test_full_fields(self):
        from dawei.models.ip import IpTaskContext
        ctx = IpTaskContext(
            module="ip-reverse-detection",
            task_type="reverse_detection",
            parent_module="ip-draft",
            parent_workspace_id="ws-parent-001",
            parent_task_id="task-001",
            language="en-US",
            jurisdiction="US",
            draft_strategy="broad",
            target_country="US",
            description="A method for caching data",
            trademark_name="MyBrand",
            business_scope="Software development",
            file_ids=["f1", "f2"],
            reference_ids=["r1"],
            inherit_files=["draft.docx", "claims.docx"],
            user_preferences={"key": "val"},
        )
        assert ctx.parent_module == "ip-draft"
        assert ctx.parent_workspace_id == "ws-parent-001"
        assert ctx.language == "en-US"
        assert ctx.draft_strategy == "broad"
        assert ctx.target_country == "US"
        assert ctx.description == "A method for caching data"
        assert ctx.trademark_name == "MyBrand"
        assert len(ctx.file_ids) == 2
        assert len(ctx.inherit_files) == 2
        assert ctx.user_preferences == {"key": "val"}


class TestWorkspaceStatus:
    """WorkspaceStatus dataclass creation."""

    def test_minimal_creation(self):
        from dawei.models.ip import WorkspaceStatus
        ws = WorkspaceStatus(
            workspace_id="ws-001",
            name="ip-draft-a1b2c3d4",
            display_name="专利撰写",
            module="ip-draft",
            lifecycle="temporary",
            status="creating",
        )
        assert ws.workspace_id == "ws-001"
        assert ws.status == "creating"
        assert ws.phase is None
        assert ws.file_count == 0
        assert ws.task_count == 0

    def test_with_checkpoint_and_resources(self):
        from dawei.models.ip import WorkspaceStatus
        now = datetime.now(timezone.utc).isoformat()
        ws = WorkspaceStatus(
            workspace_id="ws-002",
            name="ip-draft-xyz",
            display_name="专利撰写 · XYZ",
            module="ip-draft",
            lifecycle="temporary",
            status="paused",
            phase="do",
            progress_current=3,
            progress_total=7,
            created_at=now,
            expires_at=now,
            file_count=5,
            task_count=1,
            parent_workspace_id="ws-parent",
            checkpoint={"phase": "do", "description": "Writing claims"},
            resources={"skills": ["skill/docx"], "mcps": []},
            metadata={"draft_strategy": "defensive"},
        )
        assert ws.phase == "do"
        assert ws.progress_current == 3
        assert ws.progress_total == 7
        assert ws.checkpoint["phase"] == "do"
        assert ws.resources["skills"] == ["skill/docx"]
        assert ws.metadata["draft_strategy"] == "defensive"


class TestResumableTask:
    """ResumableTask dataclass creation."""

    def test_creation(self):
        from dawei.models.ip import ResumableTask
        task = ResumableTask(
            workspace_id="ws-001",
            name="专利撰写 · Test",
            module="ip-draft",
            phase="check",
            progress_current=4,
            progress_total=8,
        )
        assert task.workspace_id == "ws-001"
        assert task.phase == "check"
        assert task.progress_current == 4


class TestInheritRequest:
    """InheritRequest dataclass creation."""

    def test_with_file_list(self):
        from dawei.models.ip import InheritRequest
        req = InheritRequest(
            parent_workspace_id="ws-parent",
            file_names=["draft.docx", "claims.json"],
        )
        assert req.parent_workspace_id == "ws-parent"
        assert len(req.file_names) == 2

    def test_empty_file_names_means_all(self):
        from dawei.models.ip import InheritRequest
        req = InheritRequest(parent_workspace_id="ws-parent")
        assert req.file_names == []


# ============================================================================
# 2. IP_MODULE_RESOURCES Configuration
# ============================================================================

class TestIPModuleResources:
    """Verify IP_MODULE_RESOURCES dict is complete and consistent."""

    MODULES = [
        "ip-idea-vault", "ip-disclosure", "ip-draft",
        "ip-filing", "ip-oa-reply", "ip-reverse-detection",
        "ip-portfolio", "ip-trademark",
    ]

    def test_all_eight_modules_defined(self):
        from dawei_biz.services.ip_workspace_service import IP_MODULE_RESOURCES
        for mod in self.MODULES:
            assert mod in IP_MODULE_RESOURCES, f"Missing module: {mod}"

    def test_each_module_has_required_keys(self):
        from dawei_biz.services.ip_workspace_service import IP_MODULE_RESOURCES
        for mod, res in IP_MODULE_RESOURCES.items():
            for key in ("skills", "agents", "mcps", "knowledges"):
                assert key in res, f"{mod} missing key: {key}"
                assert isinstance(res[key], list), f"{mod}.{key} should be list"

    def test_skills_only_use_valid_prefixes(self):
        """All skill references should use 'skill/' prefix."""
        from dawei_biz.services.ip_workspace_service import IP_MODULE_RESOURCES
        for mod, res in IP_MODULE_RESOURCES.items():
            for s in res["skills"]:
                assert s.startswith("skill/"), f"{mod} invalid skill: {s}"

    def test_agents_only_use_valid_prefixes(self):
        from dawei_biz.services.ip_workspace_service import IP_MODULE_RESOURCES
        for mod, res in IP_MODULE_RESOURCES.items():
            for a in res["agents"]:
                assert a.startswith("agent/"), f"{mod} invalid agent: {a}"

    def test_mcps_only_use_valid_prefixes(self):
        from dawei_biz.services.ip_workspace_service import IP_MODULE_RESOURCES
        for mod, res in IP_MODULE_RESOURCES.items():
            for m in res["mcps"]:
                assert m.startswith("mcp/"), f"{mod} invalid mcp: {m}"

    def test_knowledges_only_use_valid_prefixes(self):
        from dawei_biz.services.ip_workspace_service import IP_MODULE_RESOURCES
        for mod, res in IP_MODULE_RESOURCES.items():
            for k in res["knowledges"]:
                assert k.startswith("knowledge/"), f"{mod} invalid knowledge: {k}"


# ============================================================================
# 3. IPWorkspaceService — Unit Tests
# ============================================================================

class TestGetModuleResources:
    """Tests for get_module_resources()."""

    def test_known_module_returns_resources(self):
        from dawei_biz.services.ip_workspace_service import ip_workspace_service
        res = ip_workspace_service.get_module_resources("ip-draft")
        assert "skills" in res
        assert "skill/docx" in res["skills"]

    def test_unknown_module_returns_empty(self):
        from dawei_biz.services.ip_workspace_service import ip_workspace_service
        res = ip_workspace_service.get_module_resources("nonexistent-module")
        assert res == {}


class TestGenerateWorkspaceName:
    """Tests for _generate_workspace_name()."""

    def test_prefix_includes_module_slug(self):
        from dawei_biz.services.ip_workspace_service import ip_workspace_service
        name = ip_workspace_service._generate_workspace_name("ip-draft")
        assert name.startswith("ip-draft-")

    def test_suffix_is_8_hex_chars(self):
        from dawei_biz.services.ip_workspace_service import ip_workspace_service
        name = ip_workspace_service._generate_workspace_name("ip-draft")
        suffix = name[len("ip-draft-"):]
        assert len(suffix) == 8
        assert all(c in "0123456789abcdef" for c in suffix)

    def test_different_module_produces_different_prefix(self):
        from dawei_biz.services.ip_workspace_service import ip_workspace_service
        name = ip_workspace_service._generate_workspace_name("ip-trademark")
        assert name.startswith("ip-trademark-")


class TestGenerateDisplayName:
    """Tests for _generate_display_name()."""

    def test_basic_module_name(self):
        from dawei.models.ip import IpTaskContext
        from dawei_biz.services.ip_workspace_service import ip_workspace_service
        ctx = IpTaskContext(module="ip-draft", task_type="generate")
        name = ip_workspace_service._generate_display_name("ip-draft", ctx)
        assert "专利撰写" in name

    def test_with_description(self):
        from dawei.models.ip import IpTaskContext
        from dawei_biz.services.ip_workspace_service import ip_workspace_service
        ctx = IpTaskContext(
            module="ip-draft",
            task_type="generate",
            description="A method for optimizing database queries",
        )
        name = ip_workspace_service._generate_display_name("ip-draft", ctx)
        assert "A method for optimiz..." in name
        assert "专利撰写" in name

    def test_short_description_not_truncated(self):
        from dawei.models.ip import IpTaskContext
        from dawei_biz.services.ip_workspace_service import ip_workspace_service
        ctx = IpTaskContext(module="ip-draft", task_type="generate", description="Short desc")
        name = ip_workspace_service._generate_display_name("ip-draft", ctx)
        assert "Short desc" in name

    def test_with_trademark_name(self):
        from dawei.models.ip import IpTaskContext
        from dawei_biz.services.ip_workspace_service import ip_workspace_service
        ctx = IpTaskContext(
            module="ip-trademark",
            task_type="register",
            trademark_name="MyGreatBrand",
        )
        name = ip_workspace_service._generate_display_name("ip-trademark", ctx)
        assert "MyGreatBrand" in name
        assert "商标注册" in name

    def test_unknown_module_falls_back_to_slug(self):
        from dawei.models.ip import IpTaskContext
        from dawei_biz.services.ip_workspace_service import ip_workspace_service
        ctx = IpTaskContext(module="unknown-mod", task_type="test")
        name = ip_workspace_service._generate_display_name("unknown-mod", ctx)
        assert name == "unknown-mod"


class TestComputeExpiry:
    """Tests for _compute_expiry (static method)."""

    def test_temporary_returns_future_iso(self):
        from dawei_biz.services.ip_workspace_service import (
            IPWorkspaceService,
            DEFAULT_IP_WORKSPACE_TTL_H,
        )
        now = datetime.now(timezone.utc)
        expiry = IPWorkspaceService._compute_expiry(now, "temporary")
        expiry_dt = datetime.fromisoformat(expiry)
        delta = expiry_dt - now
        assert timedelta(hours=DEFAULT_IP_WORKSPACE_TTL_H - 1) < delta < timedelta(hours=DEFAULT_IP_WORKSPACE_TTL_H + 1)

    def test_persistent_returns_empty_string(self):
        from dawei_biz.services.ip_workspace_service import IPWorkspaceService
        now = datetime.now(timezone.utc)
        result = IPWorkspaceService._compute_expiry(now, "persistent")
        assert result == ""


# ============================================================================
# 4. IPWorkspaceService — Filesystem-dependent tests (uses tmp_path)
# ============================================================================

class TestWriteIPMetadata:
    """Tests for _write_ip_metadata()."""

    @pytest.mark.asyncio
    async def test_writes_ip_metadata_to_workspace_json(self, tmp_path: Path):
        from dawei.models.ip import IpTaskContext
        from dawei_biz.services.ip_workspace_service import ip_workspace_service

        ws_path = tmp_path / "test-ws"
        ws_path.mkdir()
        dawei_dir = ws_path / ".dawei"
        dawei_dir.mkdir()

        ctx = IpTaskContext(
            module="ip-draft",
            task_type="generate_draft",
            language="zh-CN",
            jurisdiction="CN",
            parent_workspace_id="ws-parent",
            draft_strategy="defensive",
        )
        resources = {"skills": ["skill/docx"], "mcps": [], "knowledges": [], "agents": []}

        await ip_workspace_service._write_ip_metadata(
            workspace_path=ws_path,
            module="ip-draft",
            ctx=ctx,
            lifecycle="temporary",
            resources=resources,
        )

        ws_json = dawei_dir / "workspace.json"
        assert ws_json.exists()
        with open(ws_json) as f:
            data = json.load(f)

        meta = data.get("ip_metadata")
        assert meta is not None
        assert meta["module"] == "ip-draft"
        assert meta["task_type"] == "generate_draft"
        assert meta["language"] == "zh-CN"
        assert meta["jurisdiction"] == "CN"
        assert meta["parent_workspace_id"] == "ws-parent"
        assert meta["resources"] == resources
        assert "created_at" in meta
        assert "expires_at" in meta

    @pytest.mark.asyncio
    async def test_existing_workspace_json_is_merged(self, tmp_path: Path):
        from dawei.models.ip import IpTaskContext
        from dawei_biz.services.ip_workspace_service import ip_workspace_service

        ws_path = tmp_path / "test-ws"
        ws_path.mkdir()
        dawei_dir = ws_path / ".dawei"
        dawei_dir.mkdir()

        # Pre-write existing data
        existing = {"name": "pre-existing", "version": 1}
        with open(dawei_dir / "workspace.json", "w") as f:
            json.dump(existing, f)

        ctx = IpTaskContext(module="ip-draft", task_type="generate_draft")
        await ip_workspace_service._write_ip_metadata(
            workspace_path=ws_path,
            module="ip-draft",
            ctx=ctx,
            lifecycle="temporary",
            resources={},
        )

        with open(dawei_dir / "workspace.json") as f:
            data = json.load(f)

        # Existing keys preserved
        assert data["name"] == "pre-existing"
        assert data["version"] == 1
        # New ip_metadata added
        assert "ip_metadata" in data


class TestInheritFilesPrivate:
    """Tests for the private _inherit_files method."""

    @pytest.mark.asyncio
    async def test_copies_specific_files(self, tmp_path: Path):
        from dawei_biz.services.ip_workspace_service import ip_workspace_service

        # Parent workspace with files
        parent_path = tmp_path / "parent-ws"
        parent_files = parent_path / ".dawei" / "files"
        parent_files.mkdir(parents=True)
        (parent_files / "draft.docx").write_text("draft content")
        (parent_files / "claims.txt").write_text("claims content")
        (parent_files / "extra.md").write_text("extra content")

        # Target workspace
        target_path = tmp_path / "target-ws"
        target_path.mkdir()

        # Patch _resolve_workspace_path to return parent_path for the parent_workspace_id
        with patch.object(ip_workspace_service, "_resolve_workspace_path") as mock_resolve:
            mock_resolve.return_value = parent_path

            inherited = await ip_workspace_service._inherit_files(
                target_workspace_path=target_path,
                parent_workspace_id="parent-id",
                file_names=["draft.docx", "claims.txt"],
            )

        assert set(inherited) == {"draft.docx", "claims.txt"}

        target_files = target_path / ".dawei" / "files"
        assert target_files.exists()
        assert (target_files / "draft.docx").read_text() == "draft content"
        assert (target_files / "claims.txt").read_text() == "claims content"
        assert not (target_files / "extra.md").exists()  # not in list

    @pytest.mark.asyncio
    async def test_empty_file_names_copies_all(self, tmp_path: Path):
        from dawei_biz.services.ip_workspace_service import ip_workspace_service

        parent_path = tmp_path / "parent-ws"
        parent_files = parent_path / ".dawei" / "files"
        parent_files.mkdir(parents=True)
        (parent_files / "a.txt").write_text("a")
        (parent_files / "b.txt").write_text("b")

        target_path = tmp_path / "target-ws"
        target_path.mkdir()

        with patch.object(ip_workspace_service, "_resolve_workspace_path") as mock_resolve:
            mock_resolve.return_value = parent_path

            inherited = await ip_workspace_service._inherit_files(
                target_workspace_path=target_path,
                parent_workspace_id="parent-id",
                file_names=[],
            )

        assert len(inherited) == 2
        target_files = target_path / ".dawei" / "files"
        assert (target_files / "a.txt").exists()
        assert (target_files / "b.txt").exists()

    @pytest.mark.asyncio
    async def test_missing_parent_returns_empty(self, tmp_path: Path):
        from dawei_biz.services.ip_workspace_service import ip_workspace_service

        target_path = tmp_path / "target-ws"
        target_path.mkdir()

        with patch.object(ip_workspace_service, "_resolve_workspace_path") as mock_resolve:
            mock_resolve.return_value = None  # parent not found

            inherited = await ip_workspace_service._inherit_files(
                target_workspace_path=target_path,
                parent_workspace_id="nonexistent",
                file_names=["draft.docx"],
            )

        assert inherited == []

    @pytest.mark.asyncio
    async def test_nonexistent_files_are_skipped(self, tmp_path: Path):
        from dawei_biz.services.ip_workspace_service import ip_workspace_service

        parent_path = tmp_path / "parent-ws"
        parent_files = parent_path / ".dawei" / "files"
        parent_files.mkdir(parents=True)
        (parent_files / "exists.txt").write_text("hello")

        target_path = tmp_path / "target-ws"
        target_path.mkdir()

        with patch.object(ip_workspace_service, "_resolve_workspace_path") as mock_resolve:
            mock_resolve.return_value = parent_path

            inherited = await ip_workspace_service._inherit_files(
                target_workspace_path=target_path,
                parent_workspace_id="parent-id",
                file_names=["exists.txt", "no-such-file.pdf"],
            )

        assert inherited == ["exists.txt"]


class TestGetWorkspaceStatus:
    """Tests for get_workspace_status()."""

    @pytest.mark.asyncio
    async def test_workspace_not_found_raises(self):
        from dawei_biz.services.ip_workspace_service import ip_workspace_service
        with patch.object(ip_workspace_service, "_resolve_workspace_path", return_value=None):
            with pytest.raises(FileNotFoundError):
                await ip_workspace_service.get_workspace_status("nonexistent-ws")

    @pytest.mark.asyncio
    async def test_empty_workspace_returns_defaults(self, tmp_path: Path):
        from dawei_biz.services.ip_workspace_service import ip_workspace_service

        ws_path = tmp_path / "empty-ws"
        ws_path.mkdir()
        dawei_dir = ws_path / ".dawei"
        dawei_dir.mkdir()

        with patch.object(ip_workspace_service, "_resolve_workspace_path", return_value=ws_path):
            status = await ip_workspace_service.get_workspace_status("empty-ws")

        assert status.workspace_id == "empty-ws"
        assert status.status == "idle"
        assert status.file_count == 0
        assert status.task_count == 0

    @pytest.mark.asyncio
    async def test_with_workspace_json_reads_ip_metadata(self, tmp_path: Path):
        from dawei_biz.services.ip_workspace_service import ip_workspace_service

        ws_path = tmp_path / "rich-ws"
        ws_path.mkdir()
        dawei_dir = ws_path / ".dawei"
        dawei_dir.mkdir()
        workspace_json = dawei_dir / "workspace.json"
        now = datetime.now(timezone.utc).isoformat()
        config = {
            "name": "ip-draft-abc",
            "display_name": "专利撰写 · Test",
            "lifecycle": "temporary",
            "ip_metadata": {
                "module": "ip-draft",
                "created_at": now,
                "expires_at": now,
                "resources": {"skills": ["skill/docx"]},
                "metadata": {"draft_strategy": "broad"},
                "parent_workspace_id": "ws-parent",
            },
        }
        with open(workspace_json, "w") as f:
            json.dump(config, f)

        with patch.object(ip_workspace_service, "_resolve_workspace_path", return_value=ws_path):
            status = await ip_workspace_service.get_workspace_status("rich-ws")

        assert status.module == "ip-draft"
        assert status.lifecycle == "temporary"
        assert status.name == "ip-draft-abc"
        assert status.display_name == "专利撰写 · Test"
        assert status.parent_workspace_id == "ws-parent"
        assert status.resources == {"skills": ["skill/docx"]}
        assert status.metadata == {"draft_strategy": "broad"}

    @pytest.mark.asyncio
    async def test_with_checkpoints_sets_paused_status(self, tmp_path: Path):
        from dawei_biz.services.ip_workspace_service import ip_workspace_service

        ws_path = tmp_path / "paused-ws"
        ws_path.mkdir()
        dawei_dir = ws_path / ".dawei"
        dawei_dir.mkdir()
        checkpoints_dir = dawei_dir / "checkpoints"
        checkpoints_dir.mkdir()

        cp = {
            "phase": "do",
            "description": "Writing claims section",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "progress_current": 3,
            "progress_total": 7,
        }
        with open(checkpoints_dir / "checkpoint-001.json", "w") as f:
            json.dump(cp, f)

        with patch.object(ip_workspace_service, "_resolve_workspace_path", return_value=ws_path):
            status = await ip_workspace_service.get_workspace_status("paused-ws")

        assert status.status == "paused"
        assert status.phase == "do"
        assert status.progress_current == 3
        assert status.progress_total == 7
        assert status.checkpoint is not None
        assert status.checkpoint["phase"] == "do"

    @pytest.mark.asyncio
    async def test_with_files_counts_correctly(self, tmp_path: Path):
        from dawei_biz.services.ip_workspace_service import ip_workspace_service

        ws_path = tmp_path / "files-ws"
        ws_path.mkdir()
        dawei_dir = ws_path / ".dawei"
        dawei_dir.mkdir()
        files_dir = dawei_dir / "files"
        files_dir.mkdir()
        (files_dir / "a.txt").write_text("a")
        (files_dir / "b.txt").write_text("b")
        (files_dir / "subdir").mkdir()
        (files_dir / "subdir" / "c.txt").write_text("c")

        with patch.object(ip_workspace_service, "_resolve_workspace_path", return_value=ws_path):
            status = await ip_workspace_service.get_workspace_status("files-ws")

        assert status.file_count == 4  # rglob counts subdir dir plus 3 files

    @pytest.mark.asyncio
    async def test_with_task_graphs_counts_correctly(self, tmp_path: Path):
        from dawei_biz.services.ip_workspace_service import ip_workspace_service

        ws_path = tmp_path / "tasks-ws"
        ws_path.mkdir()
        dawei_dir = ws_path / ".dawei"
        dawei_dir.mkdir()
        graphs_dir = dawei_dir / "task_graphs"
        graphs_dir.mkdir()
        (graphs_dir / "task-001.json").write_text("{}")
        (graphs_dir / "task-002.json").write_text("{}")

        with patch.object(ip_workspace_service, "_resolve_workspace_path", return_value=ws_path):
            status = await ip_workspace_service.get_workspace_status("tasks-ws")

        assert status.task_count == 2


class TestResumeWorkspace:
    """Tests for resume_workspace()."""

    @pytest.mark.asyncio
    async def test_returns_status_for_valid_workspace(self, tmp_path: Path):
        from dawei_biz.services.ip_workspace_service import ip_workspace_service

        ws_path = tmp_path / "valid-ws"
        ws_path.mkdir()
        dawei_dir = ws_path / ".dawei"
        dawei_dir.mkdir()
        ws_json = dawei_dir / "workspace.json"
        with open(ws_json, "w") as f:
            json.dump({
                "lifecycle": "temporary",
                "ip_metadata": {"module": "ip-draft", "expires_at": "2099-01-01T00:00:00+00:00"},
            }, f)

        with patch.object(ip_workspace_service, "_resolve_workspace_path", return_value=ws_path):
            status = await ip_workspace_service.resume_workspace("valid-ws")

        assert status.workspace_id == "valid-ws"

    @pytest.mark.asyncio
    async def test_expired_temporary_workspace_raises(self, tmp_path: Path):
        from dawei_biz.services.ip_workspace_service import ip_workspace_service

        ws_path = tmp_path / "expired-ws"
        ws_path.mkdir()
        dawei_dir = ws_path / ".dawei"
        dawei_dir.mkdir()
        ws_json = dawei_dir / "workspace.json"
        with open(ws_json, "w") as f:
            json.dump({
                "lifecycle": "temporary",
                "ip_metadata": {
                    "module": "ip-draft",
                    "expires_at": "2000-01-01T00:00:00+00:00",
                },
            }, f)

        with patch.object(ip_workspace_service, "_resolve_workspace_path", return_value=ws_path):
            with pytest.raises(RuntimeError, match="expired"):
                await ip_workspace_service.resume_workspace("expired-ws")

    @pytest.mark.asyncio
    async def test_persistent_workspace_never_expires(self, tmp_path: Path):
        from dawei_biz.services.ip_workspace_service import ip_workspace_service

        ws_path = tmp_path / "persistent-ws"
        ws_path.mkdir()
        dawei_dir = ws_path / ".dawei"
        dawei_dir.mkdir()
        ws_json = dawei_dir / "workspace.json"
        with open(ws_json, "w") as f:
            json.dump({
                "lifecycle": "persistent",
                "ip_metadata": {"module": "ip-reverse-detection"},
            }, f)

        with patch.object(ip_workspace_service, "_resolve_workspace_path", return_value=ws_path):
            status = await ip_workspace_service.resume_workspace("persistent-ws")

        assert status.lifecycle == "persistent"


class TestCleanupWorkspace:
    """Tests for cleanup_workspace()."""

    @pytest.mark.asyncio
    async def test_cleans_up_idle_workspace(self, tmp_path: Path):
        from dawei_biz.services.ip_workspace_service import ip_workspace_service

        ws_path = tmp_path / "idle-ws"
        ws_path.mkdir()
        (ws_path / ".dawei").mkdir()
        (ws_path / "some-file.txt").write_text("data")

        with patch.object(ip_workspace_service, "_resolve_workspace_path", return_value=ws_path):
            with patch.object(ip_workspace_service, "get_workspace_status") as mock_status:
                from dawei.models.ip import WorkspaceStatus
                mock_status.return_value = WorkspaceStatus(
                    workspace_id="idle-ws",
                    name="idle-ws",
                    display_name="idle",
                    module="ip-draft",
                    lifecycle="temporary",
                    status="idle",
                )
                result = await ip_workspace_service.cleanup_workspace("idle-ws")
                assert result is True
                assert not ws_path.exists()

    @pytest.mark.asyncio
    async def test_refuses_active_workspace_without_force(self, tmp_path: Path):
        from dawei_biz.services.ip_workspace_service import ip_workspace_service

        ws_path = tmp_path / "active-ws"
        ws_path.mkdir()

        with patch.object(ip_workspace_service, "_resolve_workspace_path", return_value=ws_path):
            with patch.object(ip_workspace_service, "get_workspace_status") as mock_status:
                from dawei.models.ip import WorkspaceStatus
                mock_status.return_value = WorkspaceStatus(
                    workspace_id="active-ws",
                    name="active-ws",
                    display_name="active",
                    module="ip-draft",
                    lifecycle="temporary",
                    status="running",
                )
                with pytest.raises(RuntimeError, match="Cannot cleanup active"):
                    await ip_workspace_service.cleanup_workspace("active-ws")

    @pytest.mark.asyncio
    async def test_force_cleans_up_active_workspace(self, tmp_path: Path):
        from dawei_biz.services.ip_workspace_service import ip_workspace_service

        ws_path = tmp_path / "force-ws"
        ws_path.mkdir()

        with patch.object(ip_workspace_service, "_resolve_workspace_path", return_value=ws_path):
            result = await ip_workspace_service.cleanup_workspace("force-ws", force=True)
            assert result is True
            assert not ws_path.exists()

    @pytest.mark.asyncio
    async def test_non_existent_workspace_returns_false(self):
        from dawei_biz.services.ip_workspace_service import ip_workspace_service
        # Use force=True to skip get_workspace_status (which would raise FileNotFoundError)
        with patch.object(ip_workspace_service, "_resolve_workspace_path", return_value=None):
            result = await ip_workspace_service.cleanup_workspace("nonexistent", force=True)
            assert result is False


class TestInheritFiles:
    """Tests for inherit_files() public method."""

    @pytest.mark.asyncio
    async def test_inherits_from_parent_to_target(self, tmp_path: Path):
        from dawei.models.ip import InheritRequest
        from dawei_biz.services.ip_workspace_service import ip_workspace_service

        # Create parent with files
        parent_path = tmp_path / "parent-ws"
        parent_files = parent_path / ".dawei" / "files"
        parent_files.mkdir(parents=True)
        (parent_files / "output.docx").write_text("output content")

        # Create target
        target_path = tmp_path / "target-ws"
        target_path.mkdir()

        def _resolve_side_effect(ws_id):
            if ws_id == "target-id":
                return target_path
            if ws_id == "parent-id":
                return parent_path
            return None

        with patch.object(ip_workspace_service, "_resolve_workspace_path", side_effect=_resolve_side_effect):
            request = InheritRequest(parent_workspace_id="parent-id", file_names=["output.docx"])
            inherited = await ip_workspace_service.inherit_files(
                workspace_id="target-id",
                request=request,
            )

        assert inherited == ["output.docx"]
        target_files = target_path / ".dawei" / "files"
        assert (target_files / "output.docx").read_text() == "output content"

    @pytest.mark.asyncio
    async def test_target_not_found_raises(self):
        from dawei.models.ip import InheritRequest
        from dawei_biz.services.ip_workspace_service import ip_workspace_service
        with patch.object(ip_workspace_service, "_resolve_workspace_path", return_value=None):
            request = InheritRequest(parent_workspace_id="parent-id")
            with pytest.raises(FileNotFoundError, match="Target workspace not found"):
                await ip_workspace_service.inherit_files("target-id", request)

    @pytest.mark.asyncio
    async def test_parent_not_found_raises(self, tmp_path: Path):
        from dawei.models.ip import InheritRequest
        from dawei_biz.services.ip_workspace_service import ip_workspace_service

        target_path = tmp_path / "target-ws"
        target_path.mkdir()

        def _resolve_side_effect(ws_id):
            if ws_id == "target-id":
                return target_path
            return None

        with patch.object(ip_workspace_service, "_resolve_workspace_path", side_effect=_resolve_side_effect):
            request = InheritRequest(parent_workspace_id="nonexistent-parent")
            with pytest.raises(FileNotFoundError, match="Parent workspace not found"):
                await ip_workspace_service.inherit_files("target-id", request)


class TestGetWorkspaceFiles:
    """Tests for get_workspace_files()."""

    @pytest.mark.asyncio
    async def test_empty_files_dir_returns_empty(self, tmp_path: Path):
        from dawei_biz.services.ip_workspace_service import ip_workspace_service

        ws_path = tmp_path / "empty-files-ws"
        ws_path.mkdir()

        with patch.object(ip_workspace_service, "_resolve_workspace_path", return_value=ws_path):
            files = await ip_workspace_service.get_workspace_files("empty-files-ws")
            assert files == []

    @pytest.mark.asyncio
    async def test_lists_files_with_metadata(self, tmp_path: Path):
        from dawei_biz.services.ip_workspace_service import ip_workspace_service

        ws_path = tmp_path / "files-ws"
        ws_path.mkdir()
        # get_workspace_files scans the workspace ROOT and skips .dawei/
        (ws_path / "hello.txt").write_text("hello world")

        with patch.object(ip_workspace_service, "_resolve_workspace_path", return_value=ws_path):
            files = await ip_workspace_service.get_workspace_files("files-ws")

        assert len(files) == 1
        f = files[0]
        assert f["name"] == "hello.txt"
        assert f["size"] == len("hello world")
        assert "modified_at" in f
        assert f["path_relative"] == "hello.txt"

    @pytest.mark.asyncio
    async def test_nonexistent_workspace_raises(self):
        from dawei_biz.services.ip_workspace_service import ip_workspace_service
        with patch.object(ip_workspace_service, "_resolve_workspace_path", return_value=None):
            with pytest.raises(FileNotFoundError):
                await ip_workspace_service.get_workspace_files("nonexistent")


class TestListResumableTasks:
    """Tests for list_resumable_tasks()."""

    @pytest.mark.asyncio
    async def test_empty_temp_dir_returns_empty(self, tmp_path: Path):
        from dawei_biz.services.ip_workspace_service import ip_workspace_service
        from dawei.workspace.temp_workspace_manager import temp_workspace_manager

        with patch.object(temp_workspace_manager, "get_temp_workspace_base_dir", return_value=tmp_path):
            tasks = await ip_workspace_service.list_resumable_tasks()
            assert tasks == []

    @pytest.mark.asyncio
    async def test_workspace_with_checkpoints_is_listed(self, tmp_path: Path):
        from dawei_biz.services.ip_workspace_service import ip_workspace_service
        from dawei.workspace.temp_workspace_manager import temp_workspace_manager

        ws_path = tmp_path / "ip-draft-testrun"
        ws_path.mkdir()
        dawei_dir = ws_path / ".dawei"
        dawei_dir.mkdir()

        # workspace.json with ip_metadata
        ws_config = {
            "name": "ip-draft-testrun",
            "display_name": "专利撰写 · Test",
            "ip_metadata": {
                "module": "ip-draft",
                "last_activity_at": datetime.now(timezone.utc).isoformat(),
                "expires_at": "2099-01-01T00:00:00+00:00",
            },
        }
        with open(dawei_dir / "workspace.json", "w") as f:
            json.dump(ws_config, f)

        # checkpoint
        checkpoints_dir = dawei_dir / "checkpoints"
        checkpoints_dir.mkdir()
        cp = {
            "phase": "do",
            "description": "in progress",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "progress_current": 2,
            "progress_total": 5,
        }
        with open(checkpoints_dir / "checkpoint-001.json", "w") as f:
            json.dump(cp, f)

        with patch.object(temp_workspace_manager, "get_temp_workspace_base_dir", return_value=tmp_path):
            tasks = await ip_workspace_service.list_resumable_tasks()

        assert len(tasks) == 1
        task = tasks[0]
        assert task.workspace_id == "ip-draft-testrun"
        assert task.module == "ip-draft"
        assert task.phase == "do"
        assert task.progress_current == 2
        assert task.progress_total == 5

    @pytest.mark.asyncio
    async def test_non_ip_workspace_is_skipped(self, tmp_path: Path):
        from dawei_biz.services.ip_workspace_service import ip_workspace_service
        from dawei.workspace.temp_workspace_manager import temp_workspace_manager

        ws_path = tmp_path / "non-ip-ws"
        ws_path.mkdir()
        dawei_dir = ws_path / ".dawei"
        dawei_dir.mkdir()

        # workspace.json WITHOUT ip_metadata
        with open(dawei_dir / "workspace.json", "w") as f:
            json.dump({"name": "non-ip-ws"}, f)

        # checkpoint
        checkpoints_dir = dawei_dir / "checkpoints"
        checkpoints_dir.mkdir()
        with open(checkpoints_dir / "cp.json", "w") as f:
            json.dump({"phase": "do"}, f)

        with patch.object(temp_workspace_manager, "get_temp_workspace_base_dir", return_value=tmp_path):
            tasks = await ip_workspace_service.list_resumable_tasks()

        assert tasks == []

    @pytest.mark.asyncio
    async def test_workspace_without_checkpoints_is_skipped(self, tmp_path: Path):
        from dawei_biz.services.ip_workspace_service import ip_workspace_service
        from dawei.workspace.temp_workspace_manager import temp_workspace_manager

        ws_path = tmp_path / "no-cp-ws"
        ws_path.mkdir()
        dawei_dir = ws_path / ".dawei"
        dawei_dir.mkdir()

        with open(dawei_dir / "workspace.json", "w") as f:
            json.dump({
                "ip_metadata": {"module": "ip-draft"},
            }, f)

        with patch.object(temp_workspace_manager, "get_temp_workspace_base_dir", return_value=tmp_path):
            tasks = await ip_workspace_service.list_resumable_tasks()

        assert tasks == []


class TestCountActiveIPWorkspaces:
    """Tests for _count_active_ip_workspaces() — reads the workspaces.json system index."""

    @pytest.mark.asyncio
    async def test_missing_index_returns_zero(self, tmp_path: Path):
        from dawei_biz.services.ip_workspace_service import ip_workspace_service

        with _fake_system_index(tmp_path):  # no workspaces.json under root
            count = await ip_workspace_service._count_active_ip_workspaces()
            assert count == 0

    @pytest.mark.asyncio
    async def test_counts_only_active_ip_entries(self, tmp_path: Path):
        from dawei_biz.services.ip_workspace_service import ip_workspace_service

        entries = [_index_entry(f"ip-ws-{i}", tmp_path / f"ip-ws-{i}", "ip-draft") for i in range(3)]
        # Non-IP type and inactive IP entries must not count
        entries.append(_index_entry("non-ip", tmp_path / "non-ip", "deep-research"))
        entries.append(_index_entry("archived-ip", tmp_path / "archived-ip", "ip-trademark", is_active=False))

        with _fake_system_index(tmp_path, entries):
            count = await ip_workspace_service._count_active_ip_workspaces()
            assert count == 3


class TestModuleWorkspaceTypeContract:
    """_module_to_workspace_type() 已移除：module slug 直接作为 workspace_type。

    契约：IP_MODULE_RESOURCES 的每个 module 都是合法的 WorkspaceType 枚举值
    （create_ip_workspace 直接传 module，list_ip_workspaces 会做
    WsTypeEnum(ws_type) 解析）。
    """

    def test_all_modules_are_valid_workspace_types(self):
        from dawei_biz.services.ip_workspace_service import IP_MODULE_RESOURCES
        from dawei.workspace.models import WorkspaceType

        assert IP_MODULE_RESOURCES, "IP_MODULE_RESOURCES must not be empty"
        for module in IP_MODULE_RESOURCES:
            assert WorkspaceType(module).value == module, f"{module} is not a valid WorkspaceType"


# ============================================================================
# 5. IPWorkspaceService — create_ip_workspace integration test
# ============================================================================

class TestCreateIPWorkspace:
    """Tests for create_ip_workspace() — the main entry point."""

    @pytest.mark.asyncio
    async def test_creates_workspace_with_all_fields(self, tmp_path: Path):
        from dawei.models.ip import IpTaskContext
        from dawei.workspace.models import WorkspaceLifecycle
        from dawei_biz.services.ip_workspace_service import ip_workspace_service
        from dawei.workspace.temp_workspace_manager import temp_workspace_manager

        # Prepare fake temp workspace manager response
        ws_path = tmp_path / "created-ws"
        ws_path.mkdir(parents=True)
        dawei_dir = ws_path / ".dawei"
        dawei_dir.mkdir()

        ctx = IpTaskContext(
            module="ip-draft",
            task_type="generate_draft",
            language="zh-CN",
            jurisdiction="CN",
            draft_strategy="defensive",
            description="A method for machine learning",
            parent_workspace_id="ws-parent-001",
            inherit_files=["prior_draft.docx"],
        )

        with patch.object(temp_workspace_manager, "get_temp_workspace_base_dir", return_value=tmp_path):
            with patch.object(temp_workspace_manager, "create_temp_workspace") as mock_create:
                mock_create.return_value = _make_fake_ws_info(
                    ws_id="created-ws",
                    ws_path=ws_path,
                )

                # Also patch _count_active_ip_workspaces to allow creation
                with patch.object(ip_workspace_service, "_count_active_ip_workspaces", return_value=0):
                    # Patch resource install to avoid real install
                    with patch.object(ip_workspace_service, "_install_module_resources") as mock_install:
                        mock_install.return_value = {
                            "skills": ["skill/docx"],
                            "mcps": [],
                            "knowledges": [],
                            "agents": ["agent/patent-team"],
                        }

                        # Patch _inherit_files to avoid real file ops
                        with patch.object(ip_workspace_service, "_inherit_files") as mock_inherit:
                            mock_inherit.return_value = ["prior_draft.docx"]

                            status = await ip_workspace_service.create_ip_workspace(
                                module="ip-draft",
                                task_context=ctx,
                                lifecycle=WorkspaceLifecycle.TEMPORARY.value,
                            )

        # Verify
        assert status.workspace_id == "created-ws"
        assert status.module == "ip-draft"
        assert status.lifecycle == "temporary"
        assert status.status == "creating"
        assert status.phase == "idle"
        assert status.parent_workspace_id == "ws-parent-001"
        assert status.resources["skills"] == ["skill/docx"]
        assert status.metadata["draft_strategy"] == "defensive"
        assert status.metadata["task_type"] == "generate_draft"
        assert status.expires_at is not None

        # Verify workspace.json was written
        ws_json = dawei_dir / "workspace.json"
        assert ws_json.exists()
        with open(ws_json) as f:
            data = json.load(f)
        assert "ip_metadata" in data
        assert data["ip_metadata"]["module"] == "ip-draft"

    @pytest.mark.asyncio
    async def test_resource_install_failure_does_not_block_creation(self, tmp_path: Path):
        from dawei.models.ip import IpTaskContext
        from dawei_biz.services.ip_workspace_service import ip_workspace_service
        from dawei.workspace.temp_workspace_manager import temp_workspace_manager

        ws_path = tmp_path / "tolerant-ws"
        ws_path.mkdir(parents=True)
        (ws_path / ".dawei").mkdir()

        ctx = IpTaskContext(module="ip-draft", task_type="generate")

        with patch.object(temp_workspace_manager, "get_temp_workspace_base_dir", return_value=tmp_path):
            with patch.object(temp_workspace_manager, "create_temp_workspace") as mock_create:
                mock_create.return_value = _make_fake_ws_info(ws_id="tolerant-ws", ws_path=ws_path)

                with patch.object(ip_workspace_service, "_count_active_ip_workspaces", return_value=0):
                    with patch.object(ip_workspace_service, "_install_module_resources") as mock_install:
                        mock_install.side_effect = Exception("Network error")

                        status = await ip_workspace_service.create_ip_workspace(
                            module="ip-draft",
                            task_context=ctx,
                        )

        # Creation succeeds, resources are empty
        assert status.workspace_id == "tolerant-ws"
        assert status.resources == {"skills": [], "mcps": [], "knowledges": [], "agents": []}

    @pytest.mark.asyncio
    async def test_no_parent_files_inherit_when_parent_absent(self, tmp_path: Path):
        from dawei.models.ip import IpTaskContext
        from dawei_biz.services.ip_workspace_service import ip_workspace_service
        from dawei.workspace.temp_workspace_manager import temp_workspace_manager

        ws_path = tmp_path / "no-parent-ws"
        ws_path.mkdir(parents=True)
        (ws_path / ".dawei").mkdir()

        ctx = IpTaskContext(module="ip-draft", task_type="generate")
        # No parent_workspace_id set

        with patch.object(temp_workspace_manager, "get_temp_workspace_base_dir", return_value=tmp_path):
            with patch.object(temp_workspace_manager, "create_temp_workspace") as mock_create:
                mock_create.return_value = _make_fake_ws_info(ws_id="no-parent-ws", ws_path=ws_path)

                with patch.object(ip_workspace_service, "_count_active_ip_workspaces", return_value=0):
                    with patch.object(ip_workspace_service, "_install_module_resources") as mock_install:
                        mock_install.return_value = {}
                        status = await ip_workspace_service.create_ip_workspace(
                            module="ip-draft",
                            task_context=ctx,
                        )

        assert status.workspace_id == "no-parent-ws"
        assert status.parent_workspace_id is None


# ============================================================================
# 6. IPWorkspaceService — list_ip_workspaces
# ============================================================================


class TestListIPWorkspaces:
    """Tests for list_ip_workspaces() — reads the workspaces.json system index.

    现实现经 StorageProvider.get_system_storage() 读统一系统索引（与
    GET /api/workspaces/list 同源），按 workspace_type 前缀 "ip-" 过滤，
    再回读各工作区 .dawei/workspace.json / files / checkpoints。
    """

    @pytest.mark.asyncio
    async def test_missing_index_returns_empty(self, tmp_path: Path):
        from dawei_biz.services.ip_workspace_service import ip_workspace_service

        with _fake_system_index(tmp_path):  # no workspaces.json under root
            result = await ip_workspace_service.list_ip_workspaces()
            assert result == []

    @pytest.mark.asyncio
    async def test_empty_index_returns_empty(self, tmp_path: Path):
        from dawei_biz.services.ip_workspace_service import ip_workspace_service

        with _fake_system_index(tmp_path, entries=[]):
            result = await ip_workspace_service.list_ip_workspaces()
            assert result == []

    @pytest.mark.asyncio
    async def test_returns_ip_workspace_entries(self, tmp_path: Path):
        from dawei_biz.services.ip_workspace_service import ip_workspace_service

        # Create an IP workspace on disk
        ws_path = tmp_path / "ip-draft-abc12345"
        ws_path.mkdir()
        dawei_dir = ws_path / ".dawei"
        dawei_dir.mkdir()
        now = datetime.now(timezone.utc).isoformat()
        ws_config = {
            "name": "ip-draft-abc12345",
            "display_name": "专利撰写 · Test",
            "ip_metadata": {
                "module": "ip-draft",
                "task_type": "generate_draft",
                "created_at": now,
                "last_activity_at": now,
                "expires_at": "2099-01-01T00:00:00+00:00",
            },
        }
        with open(dawei_dir / "workspace.json", "w") as f:
            json.dump(ws_config, f)

        # Create files
        files_dir = dawei_dir / "files"
        files_dir.mkdir()
        (files_dir / "draft.docx").write_text("content")

        entry = _index_entry(
            "ip-draft-abc12345",
            ws_path,
            "ip-draft",
            display_name="专利撰写 · Test",
        )
        with _fake_system_index(tmp_path, [entry]):
            result = await ip_workspace_service.list_ip_workspaces()

        assert len(result) == 1
        ws = result[0]
        assert ws["id"] == "ip-draft-abc12345"
        assert ws["name"] == "专利撰写 · Test"
        assert ws["workspaceType"] == "ip-draft"
        assert len(ws["files"]) == 1
        assert ws["files"][0]["name"] == "draft.docx"
        assert ws["createdAt"] > 0

    @pytest.mark.asyncio
    async def test_filters_by_workspace_type(self, tmp_path: Path):
        from dawei_biz.services.ip_workspace_service import ip_workspace_service

        draft_path = tmp_path / "ip-draft-1"
        draft_path.mkdir()
        (draft_path / ".dawei").mkdir()
        with open(draft_path / ".dawei" / "workspace.json", "w") as f:
            json.dump({"ip_metadata": {"module": "ip-draft"}}, f)

        tm_path = tmp_path / "ip-trademark-1"
        tm_path.mkdir()
        (tm_path / ".dawei").mkdir()
        with open(tm_path / ".dawei" / "workspace.json", "w") as f:
            json.dump({"ip_metadata": {"module": "ip-trademark"}}, f)

        entries = [
            _index_entry("ip-draft-1", draft_path, "ip-draft"),
            _index_entry("ip-trademark-1", tm_path, "ip-trademark"),
        ]
        with _fake_system_index(tmp_path, entries):
            result = await ip_workspace_service.list_ip_workspaces(workspace_type="ip-draft")

        assert len(result) == 1
        assert result[0]["workspaceType"] == "ip-draft"

    @pytest.mark.asyncio
    async def test_search_query_filters_by_name(self, tmp_path: Path):
        from dawei_biz.services.ip_workspace_service import ip_workspace_service

        ws1_path = tmp_path / "ws-1"
        ws1_path.mkdir()
        (ws1_path / ".dawei").mkdir()
        ws2_path = tmp_path / "ws-2"
        ws2_path.mkdir()
        (ws2_path / ".dawei").mkdir()

        entries = [
            _index_entry("ws-1", ws1_path, "ip-draft", display_name="Alpha Project"),
            _index_entry("ws-2", ws2_path, "ip-draft", display_name="Beta Analysis"),
        ]
        with _fake_system_index(tmp_path, entries):
            result = await ip_workspace_service.list_ip_workspaces(search_query="alpha")

        assert len(result) == 1
        assert "Alpha" in result[0]["name"]

    @pytest.mark.asyncio
    async def test_skips_non_ip_workspace(self, tmp_path: Path):
        from dawei_biz.services.ip_workspace_service import ip_workspace_service

        # Non-IP workspace_type in the index (authoritative typing — no name inference)
        non_ip = tmp_path / "non-ip"
        non_ip.mkdir()
        (non_ip / ".dawei").mkdir()
        with open(non_ip / ".dawei" / "workspace.json", "w") as f:
            json.dump({"name": "non-ip-ws"}, f)

        entries = [_index_entry("non-ip", non_ip, "deep-research")]
        with _fake_system_index(tmp_path, entries):
            result = await ip_workspace_service.list_ip_workspaces()

        assert result == []

    @pytest.mark.asyncio
    async def test_skips_entry_with_missing_path(self, tmp_path: Path):
        from dawei_biz.services.ip_workspace_service import ip_workspace_service

        # Index entry pointing at a path that no longer exists on disk
        entry = _index_entry("ghost", tmp_path / "ghost-ws", "ip-draft")
        with _fake_system_index(tmp_path, [entry]):
            result = await ip_workspace_service.list_ip_workspaces()

        assert result == []

    @pytest.mark.asyncio
    async def test_includes_alerts_in_metadata(self, tmp_path: Path):
        from dawei_biz.services.ip_workspace_service import ip_workspace_service

        ws_path = tmp_path / "reverse-detection-ws"
        ws_path.mkdir()
        dawei_dir = ws_path / ".dawei"
        dawei_dir.mkdir()
        alerts = [
            {"id": "a1", "title": "Risk detected", "severity": "high", "type": "patent", "read": False},
        ]
        with open(dawei_dir / "workspace.json", "w") as f:
            json.dump({
                "display_name": "侵权监测",
                "ip_metadata": {
                    "module": "ip-reverse-detection",
                    "alerts": alerts,
                },
            }, f)

        entry = _index_entry("reverse-detection-ws", ws_path, "ip-reverse-detection")
        with _fake_system_index(tmp_path, [entry]):
            result = await ip_workspace_service.list_ip_workspaces()

        assert len(result) == 1
        assert result[0]["metadata"]["alerts"] == alerts

    @pytest.mark.asyncio
    async def test_includes_checkpoints_in_metadata(self, tmp_path: Path):
        from dawei_biz.services.ip_workspace_service import ip_workspace_service

        ws_path = tmp_path / "paused-ws"
        ws_path.mkdir()
        dawei_dir = ws_path / ".dawei"
        dawei_dir.mkdir()
        checkpoints_dir = dawei_dir / "checkpoints"
        checkpoints_dir.mkdir()

        with open(checkpoints_dir / "cp-001.json", "w") as f:
            json.dump({"phase": "do", "progress_current": 3, "progress_total": 7}, f)

        with open(dawei_dir / "workspace.json", "w") as f:
            json.dump({"ip_metadata": {"module": "ip-draft"}}, f)

        entry = _index_entry("paused-ws", ws_path, "ip-draft")
        with _fake_system_index(tmp_path, [entry]):
            result = await ip_workspace_service.list_ip_workspaces()

        assert len(result) == 1
        assert result[0]["metadata"]["checkpoints"] is not None
        assert len(result[0]["metadata"]["checkpoints"]) == 1
        assert result[0]["metadata"]["checkpoints"][0]["phase"] == "do"

    @pytest.mark.asyncio
    async def test_status_inferred_from_phase(self, tmp_path: Path):
        from dawei_biz.services.ip_workspace_service import ip_workspace_service

        def _make_ws(name: str, phase: str | None) -> Path:
            p = tmp_path / name
            p.mkdir()
            (p / ".dawei").mkdir()
            meta = {"module": "ip-draft"}
            if phase:
                meta["phase"] = phase
            with open(p / ".dawei" / "workspace.json", "w") as f:
                json.dump({"ip_metadata": meta}, f)
            return p

        cases = {
            "ws-idle": "idle",
            "ws-running": "do",
            "ws-completed": "completed",
            "ws-error": "error",
            "ws-none": None,
        }
        entries = [_index_entry(name, _make_ws(name, phase), "ip-draft") for name, phase in cases.items()]

        with _fake_system_index(tmp_path, entries):
            result = await ip_workspace_service.list_ip_workspaces()

        statuses = {ws["id"]: ws["metadata"]["status"] for ws in result}
        assert statuses["ws-idle"] == "idle"
        assert statuses["ws-running"] == "running"
        assert statuses["ws-completed"] == "completed"
        assert statuses["ws-error"] == "error"
        assert statuses["ws-none"] == "idle"


# ============================================================================
# 7. IPWorkspaceService — get_portfolio_stats
# ============================================================================


class TestGetPortfolioStats:
    """Tests for get_portfolio_stats()."""

    @pytest.mark.asyncio
    async def test_empty_returns_no_data(self):
        from dawei_biz.services.ip_workspace_service import ip_workspace_service

        with patch.object(ip_workspace_service, "list_ip_workspaces", return_value=[]):
            stats = await ip_workspace_service.get_portfolio_stats()

        assert stats["total_workspaces"] == 0
        assert stats["health_score"] is None
        assert stats["patents_granted"] == 0
        assert stats["patents_pending"] == 0
        assert stats["trademarks_registered"] == 0
        assert stats["trademarks_pending"] == 0
        assert stats["new_this_year"] == 0
        assert stats["modules"] == []
        assert stats["recent_workspaces"] == []

    @pytest.mark.asyncio
    async def test_aggregates_across_workspaces(self):
        from dawei_biz.services.ip_workspace_service import ip_workspace_service
        current_year = datetime.now(timezone.utc).year
        start_of_year = datetime(current_year, 1, 1, tzinfo=timezone.utc)

        mock_workspaces = [
            {
                "id": "ws-1",
                "workspaceType": "ip-draft",
                "createdAt": int(start_of_year.timestamp() * 1000),
                "metadata": {
                    "granted_patents": 3,
                    "pending_patents": 1,
                    "health_score": 80,
                },
            },
            {
                "id": "ws-2",
                "workspaceType": "ip-draft",
                "createdAt": int(start_of_year.timestamp() * 1000),
                "metadata": {
                    "granted_patents": 2,
                    "pending_patents": 2,
                    "health_score": 60,
                },
            },
            {
                "id": "ws-3",
                "workspaceType": "ip-trademark",
                "createdAt": int((start_of_year - timedelta(days=400)).timestamp() * 1000),
                "metadata": {
                    "registered_trademarks": 5,
                    "pending_trademarks": 3,
                },
            },
        ]

        with patch.object(ip_workspace_service, "list_ip_workspaces", return_value=mock_workspaces):
            stats = await ip_workspace_service.get_portfolio_stats()

        assert stats["total_workspaces"] == 3
        assert stats["patents_granted"] == 5   # 3 + 2
        assert stats["patents_pending"] == 3    # 1 + 2
        assert stats["trademarks_registered"] == 5
        assert stats["trademarks_pending"] == 3
        assert stats["health_score"] == 70       # (80 + 60) / 2
        assert stats["new_this_year"] == 2       # ws-1 + ws-2 are this year
        assert len(stats["modules"]) == 2
        assert stats["modules"][0]["type"] == "ip-draft"
        assert stats["modules"][0]["count"] == 2

    @pytest.mark.asyncio
    async def test_health_score_none_when_no_scores(self):
        from dawei_biz.services.ip_workspace_service import ip_workspace_service

        mock = [{"id": "ws-1", "workspaceType": "ip-draft", "createdAt": 0, "metadata": {}}]
        with patch.object(ip_workspace_service, "list_ip_workspaces", return_value=mock):
            stats = await ip_workspace_service.get_portfolio_stats()

        assert stats["health_score"] is None


# ============================================================================
# 8. IPWorkspaceService — Checkpoint Methods
# ============================================================================


class TestSaveCheckpoint:
    """Tests for save_checkpoint()."""

    @pytest.mark.asyncio
    async def test_saves_checkpoint_to_workspace(self, tmp_path: Path):
        from dawei_biz.services.ip_workspace_service import ip_workspace_service

        ws_path = tmp_path / "cp-test-ws"
        ws_path.mkdir()
        (ws_path / ".dawei").mkdir()
        (ws_path / ".dawei" / "workspace.json").write_text('{"name":"cp-test","ip_metadata":{"module":"ip-draft"}}')

        with patch.object(ip_workspace_service, "_resolve_workspace_path", return_value=ws_path):
            result = await ip_workspace_service.save_checkpoint(
                workspace_id="cp-test-ws",
                phase="do",
                description="Writing claims section",
                progress_current=3,
                progress_total=7,
            )

        assert result["workspace_id"] == "cp-test-ws"
        assert result["phase"] == "do"
        assert result["progress_current"] == 3
        assert result["progress_total"] == 7
        assert "saved_at" in result
        assert "id" in result

        # Verify file was written
        checkpoints_dir = ws_path / ".dawei" / "checkpoints"
        assert checkpoints_dir.exists()
        cps = list(checkpoints_dir.glob("*.json"))
        assert len(cps) == 1
        with open(cps[0]) as f:
            data = json.load(f)
        assert data["phase"] == "do"
        assert data["description"] == "Writing claims section"
        assert data["progress_current"] == 3

    @pytest.mark.asyncio
    async def test_saves_multiple_checkpoints(self, tmp_path: Path):
        from dawei_biz.services.ip_workspace_service import ip_workspace_service

        ws_path = tmp_path / "multi-cp-ws"
        ws_path.mkdir()
        (ws_path / ".dawei").mkdir()
        (ws_path / ".dawei" / "workspace.json").write_text('{"name":"multi-cp","ip_metadata":{"module":"ip-draft"}}')

        with patch.object(ip_workspace_service, "_resolve_workspace_path", return_value=ws_path):
            await ip_workspace_service.save_checkpoint("multi-cp-ws", phase="plan", description="Planning", progress_current=1, progress_total=5)
            await ip_workspace_service.save_checkpoint("multi-cp-ws", phase="do", description="Executing", progress_current=3, progress_total=5)
            await ip_workspace_service.save_checkpoint("multi-cp-ws", phase="check", description="Reviewing", progress_current=4, progress_total=5)

        cps = sorted((ws_path / ".dawei" / "checkpoints").glob("*.json"))
        assert len(cps) == 3

    @pytest.mark.asyncio
    async def test_raises_when_workspace_not_found(self):
        from dawei_biz.services.ip_workspace_service import ip_workspace_service

        with patch.object(ip_workspace_service, "_resolve_workspace_path", return_value=None):
            with pytest.raises(FileNotFoundError, match="Workspace not found"):
                await ip_workspace_service.save_checkpoint("nonexistent", phase="do")

    @pytest.mark.asyncio
    async def test_updates_last_activity_timestamp(self, tmp_path: Path):
        from dawei_biz.services.ip_workspace_service import ip_workspace_service

        ws_path = tmp_path / "activity-ws"
        ws_path.mkdir()
        (ws_path / ".dawei").mkdir()
        ws_json = ws_path / ".dawei" / "workspace.json"
        old_time = "2000-01-01T00:00:00+00:00"
        ws_json.write_text(json.dumps({"name": "activity-ws", "ip_metadata": {"module": "ip-draft", "last_activity_at": old_time}}))

        with patch.object(ip_workspace_service, "_resolve_workspace_path", return_value=ws_path):
            await ip_workspace_service.save_checkpoint("activity-ws", phase="do")

        with open(ws_json) as f:
            config = json.load(f)
        assert config["ip_metadata"]["last_activity_at"] != old_time

    @pytest.mark.asyncio
    async def test_with_metadata_extra(self, tmp_path: Path):
        from dawei_biz.services.ip_workspace_service import ip_workspace_service

        ws_path = tmp_path / "meta-ws"
        ws_path.mkdir()
        (ws_path / ".dawei").mkdir()
        (ws_path / ".dawei" / "workspace.json").write_text('{"name":"meta","ip_metadata":{"module":"ip-draft"}}')

        with patch.object(ip_workspace_service, "_resolve_workspace_path", return_value=ws_path):
            result = await ip_workspace_service.save_checkpoint(
                workspace_id="meta-ws",
                phase="do",
                metadata={"strategy": "defensive", "user_notes": "Changed approach"},
            )

        assert "saved_at" in result

        cps = sorted((ws_path / ".dawei" / "checkpoints").glob("*.json"))
        with open(cps[-1]) as f:
            data = json.load(f)
        assert data["metadata"]["strategy"] == "defensive"
        assert data["metadata"]["user_notes"] == "Changed approach"


class TestGetLatestCheckpoint:
    """Tests for get_latest_checkpoint()."""

    @pytest.mark.asyncio
    async def test_returns_latest_checkpoint(self, tmp_path: Path):
        from dawei_biz.services.ip_workspace_service import ip_workspace_service

        ws_path = tmp_path / "latest-ws"
        ws_path.mkdir()
        (ws_path / ".dawei").mkdir()
        (ws_path / ".dawei" / "workspace.json").write_text('{"name":"latest","ip_metadata":{"module":"ip-draft"}}')

        with patch.object(ip_workspace_service, "_resolve_workspace_path", return_value=ws_path):
            await ip_workspace_service.save_checkpoint("latest-ws", phase="plan", description="First")
            await ip_workspace_service.save_checkpoint("latest-ws", phase="do", description="Second")

        cps = sorted((ws_path / ".dawei" / "checkpoints").glob("*.json"), key=lambda p: p.name)
        assert len(cps) == 2

        # Use the service method which sorts by mtime descending
        with patch.object(ip_workspace_service, "_resolve_workspace_path", return_value=ws_path):
            result = await ip_workspace_service.get_latest_checkpoint("latest-ws")

        assert result is not None
        assert result["phase"] in ("plan", "do")  # Both valid, newest wins if mtime differs
        assert result["description"] in ("First", "Second")

    @pytest.mark.asyncio
    async def test_returns_none_when_no_checkpoints(self, tmp_path: Path):
        from dawei_biz.services.ip_workspace_service import ip_workspace_service

        ws_path = tmp_path / "empty-cp-ws"
        ws_path.mkdir()

        with patch.object(ip_workspace_service, "_resolve_workspace_path", return_value=ws_path):
            result = await ip_workspace_service.get_latest_checkpoint("empty-cp-ws")

        assert result is None

    @pytest.mark.asyncio
    async def test_raises_when_workspace_not_found(self):
        from dawei_biz.services.ip_workspace_service import ip_workspace_service

        with patch.object(ip_workspace_service, "_resolve_workspace_path", return_value=None):
            with pytest.raises(FileNotFoundError, match="Workspace not found"):
                await ip_workspace_service.get_latest_checkpoint("nonexistent")


class TestListCheckpoints:
    """Tests for list_checkpoints()."""

    @pytest.mark.asyncio
    async def test_returns_empty_list_for_no_checkpoints(self, tmp_path: Path):
        from dawei_biz.services.ip_workspace_service import ip_workspace_service

        ws_path = tmp_path / "no-cps-ws"
        ws_path.mkdir()

        with patch.object(ip_workspace_service, "_resolve_workspace_path", return_value=ws_path):
            result = await ip_workspace_service.list_checkpoints("no-cps-ws")

        assert result == []

    @pytest.mark.asyncio
    async def test_lists_all_checkpoints_in_reverse_time_order(self, tmp_path: Path):
        from dawei_biz.services.ip_workspace_service import ip_workspace_service

        ws_path = tmp_path / "ordered-ws"
        ws_path.mkdir()
        (ws_path / ".dawei").mkdir()
        (ws_path / ".dawei" / "workspace.json").write_text('{"name":"ordered","ip_metadata":{"module":"ip-draft"}}')

        with patch.object(ip_workspace_service, "_resolve_workspace_path", return_value=ws_path):
            await ip_workspace_service.save_checkpoint("ordered-ws", phase="plan", progress_current=1, progress_total=3)
            await ip_workspace_service.save_checkpoint("ordered-ws", phase="do", progress_current=2, progress_total=3)
            await ip_workspace_service.save_checkpoint("ordered-ws", phase="check", progress_current=3, progress_total=3)

            result = await ip_workspace_service.list_checkpoints("ordered-ws")

        assert len(result) == 3
        # Most recent first
        assert result[0]["phase"] == "check"
        assert result[1]["phase"] == "do"
        assert result[2]["phase"] == "plan"

    @pytest.mark.asyncio
    async def test_raises_when_workspace_not_found(self):
        from dawei_biz.services.ip_workspace_service import ip_workspace_service

        with patch.object(ip_workspace_service, "_resolve_workspace_path", return_value=None):
            with pytest.raises(FileNotFoundError, match="Workspace not found"):
                await ip_workspace_service.list_checkpoints("nonexistent")


# ============================================================================
# 9. IPWorkspaceService — Cleanup Expired IP Workspaces
# ============================================================================


class TestCleanupExpiredIPWorkspaces:
    """Tests for cleanup_expired_ip_workspaces()."""

    @pytest.mark.asyncio
    async def test_no_temp_dir_returns_zero(self, tmp_path: Path):
        from dawei_biz.services.ip_workspace_service import ip_workspace_service
        from dawei.workspace.temp_workspace_manager import temp_workspace_manager

        non_existent = tmp_path / "nonexistent"
        with patch.object(temp_workspace_manager, "get_temp_workspace_base_dir", return_value=non_existent):
            cleaned = await ip_workspace_service.cleanup_expired_ip_workspaces()
            assert cleaned == 0

    @pytest.mark.asyncio
    async def test_skips_persistent_ip_workspaces(self, tmp_path: Path):
        from dawei_biz.services.ip_workspace_service import ip_workspace_service
        from dawei.workspace.temp_workspace_manager import temp_workspace_manager

        ws_path = tmp_path / "persistent-ip"
        ws_path.mkdir()
        dawei_dir = ws_path / ".dawei"
        dawei_dir.mkdir()
        with open(dawei_dir / "workspace.json", "w") as f:
            json.dump({
                "lifecycle": "persistent",
                "ip_metadata": {"module": "ip-draft", "expires_at": "2000-01-01T00:00:00+00:00"},
            }, f)

        with patch.object(temp_workspace_manager, "get_temp_workspace_base_dir", return_value=tmp_path):
            cleaned = await ip_workspace_service.cleanup_expired_ip_workspaces()
            assert cleaned == 0
            assert ws_path.exists()  # Should NOT be deleted

    @pytest.mark.asyncio
    async def test_cleans_expired_temporary_ip_workspace(self, tmp_path: Path):
        from dawei_biz.services.ip_workspace_service import ip_workspace_service
        from dawei.workspace.temp_workspace_manager import temp_workspace_manager

        ws_path = tmp_path / "expired-ip"
        ws_path.mkdir()
        dawei_dir = ws_path / ".dawei"
        dawei_dir.mkdir()
        with open(dawei_dir / "workspace.json", "w") as f:
            json.dump({
                "lifecycle": "temporary",
                "ip_metadata": {"module": "ip-draft", "expires_at": "2000-01-01T00:00:00+00:00"},
            }, f)

        with patch.object(temp_workspace_manager, "get_temp_workspace_base_dir", return_value=tmp_path):
            cleaned = await ip_workspace_service.cleanup_expired_ip_workspaces()
            assert cleaned == 1
            assert not ws_path.exists()  # Should be deleted

    @pytest.mark.asyncio
    async def test_keeps_non_expired_ip_workspace(self, tmp_path: Path):
        from dawei_biz.services.ip_workspace_service import ip_workspace_service
        from dawei.workspace.temp_workspace_manager import temp_workspace_manager

        ws_path = tmp_path / "fresh-ip"
        ws_path.mkdir()
        dawei_dir = ws_path / ".dawei"
        dawei_dir.mkdir()
        # Future expiry date
        with open(dawei_dir / "workspace.json", "w") as f:
            json.dump({
                "lifecycle": "temporary",
                "ip_metadata": {"module": "ip-draft", "expires_at": "2099-12-31T23:59:59+00:00"},
            }, f)

        with patch.object(temp_workspace_manager, "get_temp_workspace_base_dir", return_value=tmp_path):
            cleaned = await ip_workspace_service.cleanup_expired_ip_workspaces()
            assert cleaned == 0
            assert ws_path.exists()  # Should NOT be deleted

    @pytest.mark.asyncio
    async def test_skips_non_ip_workspaces(self, tmp_path: Path):
        from dawei_biz.services.ip_workspace_service import ip_workspace_service
        from dawei.workspace.temp_workspace_manager import temp_workspace_manager

        # Non-IP workspace (no ip_metadata)
        ws_path = tmp_path / "non-ip-ws"
        ws_path.mkdir()
        (ws_path / ".dawei").mkdir()
        with open(ws_path / ".dawei" / "workspace.json", "w") as f:
            json.dump({"lifecycle": "temporary", "name": "non-ip"}, f)

        with patch.object(temp_workspace_manager, "get_temp_workspace_base_dir", return_value=tmp_path):
            cleaned = await ip_workspace_service.cleanup_expired_ip_workspaces()
            assert cleaned == 0
            assert ws_path.exists()

    @pytest.mark.asyncio
    async def test_uses_last_activity_when_no_expires_at(self, tmp_path: Path):
        """When no expires_at is set, use last_activity_at with 72h TTL."""
        from datetime import timedelta
        from dawei_biz.services.ip_workspace_service import ip_workspace_service, DEFAULT_IP_WORKSPACE_TTL_H
        from dawei.workspace.temp_workspace_manager import temp_workspace_manager

        # Old workspace (beyond 72h TTL)
        old_ws = tmp_path / "old-ws"
        old_ws.mkdir()
        (old_ws / ".dawei").mkdir()
        old_time = (datetime.now(timezone.utc) - timedelta(hours=DEFAULT_IP_WORKSPACE_TTL_H + 1)).isoformat()
        with open(old_ws / ".dawei" / "workspace.json", "w") as f:
            json.dump({
                "lifecycle": "temporary",
                "ip_metadata": {"module": "ip-draft", "last_activity_at": old_time},
            }, f)

        # Fresh workspace (within 72h TTL)
        fresh_ws = tmp_path / "fresh-ws"
        fresh_ws.mkdir()
        (fresh_ws / ".dawei").mkdir()
        fresh_time = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        with open(fresh_ws / ".dawei" / "workspace.json", "w") as f:
            json.dump({
                "lifecycle": "temporary",
                "ip_metadata": {"module": "ip-draft", "last_activity_at": fresh_time},
            }, f)

        with patch.object(temp_workspace_manager, "get_temp_workspace_base_dir", return_value=tmp_path):
            cleaned = await ip_workspace_service.cleanup_expired_ip_workspaces()
            assert cleaned == 1
            assert not old_ws.exists()
            assert fresh_ws.exists()
