# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Comprehensive tests for agent foundational components.

Tests the building blocks that Agent depends on:
  - Tools (read, edit, command) — direct invocation, no LLM
  - ToolManager — discovery, registration, tool groups
  - SkillManager — discovery, loading, matching
  - MemoryGraph — add, query, search, temporal, stats
  - Knowledge stores — SQLiteVec + FTS (hybrid retrieval)
  - EmbeddingManager — cosine similarity, model info
  - WorkspaceConfig — load, merge, defaults
  - MCPConfig — loading, merging, override

Usage:
    cd agent
    uv run python -m pytest tests/test_agent_all.py -v            # all
    uv run python -m pytest tests/test_agent_all.py -v -m unit    # unit only
    uv run python -m pytest tests/test_agent_all.py::TestReadFileTool -v
"""

import asyncio
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.unit


# ============================================================================
# Helpers — minimal context objects for tools
# ============================================================================


@dataclass
class _FakeUserWorkspace:
    """Minimal stand-in for the user_workspace attribute tools expect."""
    path: Path


@dataclass
class _ReadContext:
    """Context for read_tools (uses user_workspace.path)."""
    user_workspace: _FakeUserWorkspace


@dataclass
class _EditContext:
    """Context for edit_tools (uses cwd)."""
    cwd: str


# ============================================================================
# Test: Read Tools
# ============================================================================


class TestReadFileTool:
    """Test ReadFileTool — reading files within workspace."""

    def test_read_text_file(self, test_workspace_with_files: Path):
        from dawei.tools.custom_tools.read_tools import ReadFileTool

        tool = ReadFileTool()
        ctx = _ReadContext(user_workspace=_FakeUserWorkspace(path=test_workspace_with_files))
        result = tool.run(context=ctx, file_path="hello.txt")
        assert "Hello, World!" in result

    def test_read_file_with_line_range(self, test_workspace_with_files: Path):
        from dawei.tools.custom_tools.read_tools import ReadFileTool

        tool = ReadFileTool()
        ctx = _ReadContext(user_workspace=_FakeUserWorkspace(path=test_workspace_with_files))
        result = tool.run(context=ctx, file_path="src/main.py", start_line=1, end_line=2)
        assert "def main" in result

    def test_read_nonexistent_file_returns_error(self, test_workspace: Path):
        from dawei.tools.custom_tools.read_tools import ReadFileTool

        tool = ReadFileTool()
        ctx = _ReadContext(user_workspace=_FakeUserWorkspace(path=test_workspace))
        result = tool.run(context=ctx, file_path="no_such_file.txt")
        assert "error" in result.lower() or "not found" in result.lower() or "failed" in result.lower()

    def test_read_file_rejects_traversal(self, test_workspace: Path):
        """Paths with '..' should be rejected."""
        from dawei.tools.custom_tools.read_tools import ReadFileTool

        tool = ReadFileTool()
        ctx = _ReadContext(user_workspace=_FakeUserWorkspace(path=test_workspace))
        result = tool.run(context=ctx, file_path="../../../etc/passwd")
        assert "error" in result.lower() or "denied" in result.lower() or "not allowed" in result.lower() or "failed" in result.lower()


class TestListFilesTool:
    """Test ListFilesTool — listing directories."""

    def test_list_root(self, test_workspace_with_files: Path):
        from dawei.tools.custom_tools.read_tools import ListFilesTool

        tool = ListFilesTool()
        ctx = _ReadContext(user_workspace=_FakeUserWorkspace(path=test_workspace_with_files))
        result = tool.run(context=ctx, path=".")
        assert "hello.txt" in result
        assert "data.json" in result
        assert "src/" in result

    def test_list_subdirectory(self, test_workspace_with_files: Path):
        from dawei.tools.custom_tools.read_tools import ListFilesTool

        tool = ListFilesTool()
        ctx = _ReadContext(user_workspace=_FakeUserWorkspace(path=test_workspace_with_files))
        result = tool.run(context=ctx, path="src")
        assert "main.py" in result

    def test_list_recursive(self, test_workspace_with_files: Path):
        from dawei.tools.custom_tools.read_tools import ListFilesTool

        tool = ListFilesTool()
        ctx = _ReadContext(user_workspace=_FakeUserWorkspace(path=test_workspace_with_files))
        result = tool.run(context=ctx, path=".", recursive=True)
        assert "main.py" in result
        assert "hello.txt" in result

    def test_list_excludes_dawei_dir(self, test_workspace: Path):
        """The .dawei directory should be excluded from listing."""
        from dawei.tools.custom_tools.read_tools import ListFilesTool

        tool = ListFilesTool()
        ctx = _ReadContext(user_workspace=_FakeUserWorkspace(path=test_workspace))
        result = tool.run(context=ctx, path=".")
        assert ".dawei" not in result


# ============================================================================
# Test: Edit Tools
# ============================================================================


class TestWriteToFileTool:
    """Test WriteToFileTool — creating/overwriting files."""

    def test_write_new_file(self, test_workspace: Path):
        from dawei.tools.custom_tools.edit_tools import WriteToFileTool

        tool = WriteToFileTool()
        ctx = _EditContext(cwd=str(test_workspace))
        result = tool.run(context=ctx, path="new_file.txt", content="written by test")
        assert "success" in result.lower() or "wrote" in result.lower() or "written" in result.lower()

        content = (test_workspace / "new_file.txt").read_text(encoding="utf-8")
        assert "written by test" in content

    def test_write_creates_parent_dirs(self, test_workspace: Path):
        from dawei.tools.custom_tools.edit_tools import WriteToFileTool

        tool = WriteToFileTool()
        ctx = _EditContext(cwd=str(test_workspace))
        result = tool.run(context=ctx, path="deep/nested/dir/file.txt", content="deep")
        assert (test_workspace / "deep" / "nested" / "dir" / "file.txt").exists()

    def test_overwrite_existing_file(self, test_workspace_with_files: Path):
        from dawei.tools.custom_tools.edit_tools import WriteToFileTool

        tool = WriteToFileTool()
        ctx = _EditContext(cwd=str(test_workspace_with_files))
        tool.run(context=ctx, path="hello.txt", content="overwritten")
        content = (test_workspace_with_files / "hello.txt").read_text(encoding="utf-8")
        assert content.strip() == "overwritten"


class TestInsertContentTool:
    """Test InsertContentTool — inserting lines into files."""

    def test_insert_at_line(self, test_workspace: Path):
        from dawei.tools.custom_tools.edit_tools import InsertContentTool

        # Create a file with known content
        f = test_workspace / "lines.txt"
        f.write_text("line1\nline2\nline3\n", encoding="utf-8")

        tool = InsertContentTool()
        ctx = _EditContext(cwd=str(test_workspace))
        result = tool.run(context=ctx, path="lines.txt", line=2, content="INSERTED")
        assert "success" in result.lower() or "inserted" in result.lower()

        lines = f.read_text(encoding="utf-8").splitlines()
        assert "INSERTED" in lines

    def test_insert_at_line_0_appends(self, test_workspace: Path):
        from dawei.tools.custom_tools.edit_tools import InsertContentTool

        f = test_workspace / "append.txt"
        f.write_text("existing\n", encoding="utf-8")

        tool = InsertContentTool()
        ctx = _EditContext(cwd=str(test_workspace))
        tool.run(context=ctx, path="append.txt", line=0, content="APPENDED")

        content = f.read_text(encoding="utf-8")
        assert "APPENDED" in content

    def test_insert_creates_file_if_missing(self, test_workspace: Path):
        from dawei.tools.custom_tools.edit_tools import InsertContentTool

        tool = InsertContentTool()
        ctx = _EditContext(cwd=str(test_workspace))
        tool.run(context=ctx, path="created.txt", line=1, content="brand new")

        assert (test_workspace / "created.txt").exists()
        assert "brand new" in (test_workspace / "created.txt").read_text(encoding="utf-8")


# ============================================================================
# Test: Command Tools
# ============================================================================


class TestExecuteCommandTool:
    """Test ExecuteCommandTool — running shell commands."""

    def test_run_echo(self, test_workspace: Path):
        from dawei.tools.custom_tools.command_tools import ExecuteCommandTool

        tool = ExecuteCommandTool()
        result = tool.run(command="echo hello_agent", timeout=10)
        result_data = json.loads(result)
        assert result_data["exit_code"] == 0
        assert "hello_agent" in result_data["stdout"]

    def test_run_pwd(self, test_workspace: Path):
        from dawei.tools.custom_tools.command_tools import ExecuteCommandTool

        tool = ExecuteCommandTool()
        result = tool.run(command="pwd", timeout=10)
        result_data = json.loads(result)
        assert result_data["exit_code"] == 0

    def test_command_timeout(self, test_workspace: Path):
        from dawei.tools.custom_tools.command_tools import ExecuteCommandTool

        tool = ExecuteCommandTool()
        result = tool.run(command="sleep 30", timeout=1)
        # The safe_tool_operation decorator catches TimeoutExpired and returns a fallback string
        assert "error" in result.lower() or "timeout" in result.lower() or "timed out" in result.lower()

    def test_reject_dangerous_command(self, test_workspace: Path):
        from dawei.tools.custom_tools.command_tools import ExecuteCommandTool, _check_dangerous_command

        blocked = _check_dangerous_command("rm -rf /")
        assert blocked is not None

        blocked = _check_dangerous_command("sudo rm /etc/passwd")
        assert blocked is not None

        safe = _check_dangerous_command("ls -la")
        assert safe is None


class TestShellCommandTool:
    """Test ShellCommandTool — running whitelisted shell commands."""

    def test_run_ls(self, test_workspace_with_files: Path):
        from dawei.tools.custom_tools.command_tools import ShellCommandTool

        tool = ShellCommandTool()
        result = tool.run(command="ls", args=[str(test_workspace_with_files)])
        result_data = json.loads(result)
        assert result_data["exit_code"] == 0
        assert "hello.txt" in result_data["stdout"]


# ============================================================================
# Test: ToolManager
# ============================================================================


class TestToolManager:
    """Test ToolManager — tool discovery and registration."""

    def test_discover_builtin_tools(self, test_workspace: Path):
        from dawei.tools.tool_manager import ToolManager

        tm = ToolManager(workspace_root=str(test_workspace))
        configs = tm.get_all_tool_configs()
        tool_names = set(configs.keys())
        # Core builtin tools should always be present
        assert "read_file" in tool_names
        assert "list_files" in tool_names
        assert "write_text_file" in tool_names
        assert "execute_command" in tool_names

    def test_get_tool_config_by_name(self, test_workspace: Path):
        from dawei.tools.tool_manager import ToolManager

        tm = ToolManager(workspace_root=str(test_workspace))
        config = tm.get_tool_config("read_file")
        assert config is not None
        assert config.name == "read_file"

    def test_get_nonexistent_tool(self, test_workspace: Path):
        from dawei.tools.tool_manager import ToolManager

        tm = ToolManager(workspace_root=str(test_workspace))
        config = tm.get_tool_config("nonexistent_tool_xyz")
        assert config is None

    def test_tool_groups(self, test_workspace: Path):
        from dawei.tools.tool_manager import ToolManager

        tm = ToolManager(workspace_root=str(test_workspace))
        groups = tm.get_tool_groups()
        assert "read" in groups
        assert "edit" in groups
        assert "command" in groups
        assert "workflow" in groups


# ============================================================================
# Test: SkillManager
# ============================================================================


class TestSkillManager:
    """Test SkillManager — skill discovery and loading."""

    def test_discover_skills_empty_dir(self, tmp_path: Path):
        """Only our empty tmp_path root — no skills from DAWEI_HOME or ~/.roo."""
        from dawei.tools.skill_manager import SkillManager

        sm = SkillManager(skills_roots=[tmp_path], current_mode="orchestrator")
        sm.discover_skills()
        # Filter to only skills from our tmp_path (exclude DAWEI_HOME / ~/.roo skills)
        our_skills = [s for s in sm.get_all_skills() if str(s.path).startswith(str(tmp_path))]
        assert len(our_skills) == 0

    def test_discover_skills_with_skill_md(self, tmp_path: Path):
        """Discover a SKILL.md in .dawei/skills/."""
        from dawei.tools.skill_manager import SkillManager

        # Create a skill directory with SKILL.md
        skill_dir = tmp_path / ".dawei" / "skills" / "test-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: test-skill\ndescription: A test skill\n---\n# Test Skill\nContent here.\n",
            encoding="utf-8",
        )

        sm = SkillManager(skills_roots=[tmp_path], current_mode="orchestrator")
        sm.discover_skills()
        skills = sm.get_all_skills()
        assert len(skills) >= 1
        names = [s.name for s in skills]
        assert "test-skill" in names

    def test_get_skill_content(self, tmp_path: Path):
        """Load skill content lazily."""
        from dawei.tools.skill_manager import SkillManager

        skill_dir = tmp_path / ".dawei" / "skills" / "my-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: Another test skill\n---\n# My Skill\nDetailed content.\n",
            encoding="utf-8",
        )

        sm = SkillManager(skills_roots=[tmp_path], current_mode="orchestrator")
        sm.discover_skills()
        content = sm.get_skill_content("my-skill")
        assert content is not None
        assert "Detailed content" in content

    def test_get_skill_summary(self, tmp_path: Path):
        """Summary string includes skill names."""
        from dawei.tools.skill_manager import SkillManager

        skill_dir = tmp_path / ".dawei" / "skills" / "summary-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: summary-skill\ndescription: For summary test\n---\n# Summary\nContent.\n",
            encoding="utf-8",
        )

        sm = SkillManager(skills_roots=[tmp_path], current_mode="orchestrator")
        sm.discover_skills()
        summary = sm.get_skills_summary()
        assert "summary-skill" in summary

    def test_skill_resources(self, tmp_path: Path):
        """Skills can list their resource files."""
        from dawei.tools.skill_manager import SkillManager

        skill_dir = tmp_path / ".dawei" / "skills" / "res-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: res-skill\ndescription: Has resources\n---\n# Res\nContent.\n",
            encoding="utf-8",
        )
        (skill_dir / "data.yaml").write_text("key: value\n", encoding="utf-8")
        (skill_dir / "template.j2").write_text("Hello {{ name }}\n", encoding="utf-8")

        sm = SkillManager(skills_roots=[tmp_path], current_mode="orchestrator")
        sm.discover_skills()
        resources = sm.get_skill_resources("res-skill")
        # Keys are file stems (no extension)
        resource_names = set(resources.keys())
        assert "data" in resource_names
        assert "template" in resource_names


# ============================================================================
# Test: MemoryGraph
# ============================================================================


class TestMemoryGraph:
    """Test MemoryGraph — add, query, search, temporal operations."""

    @pytest.mark.asyncio
    async def test_add_and_get_memory(self, tmp_path: Path):
        from dawei.memory.memory_graph import MemoryGraph, MemoryEntry, MemoryType

        db_path = str(tmp_path / "memory.db")
        mg = MemoryGraph(db_path)

        entry = MemoryEntry(
            id="mem-1",
            subject="User",
            predicate="prefers",
            object="Python",
            valid_start=datetime.now(timezone.utc),
            memory_type=MemoryType.PREFERENCE,
        )
        mid = await mg.add_memory(entry)
        assert mid == "mem-1"

        retrieved = await mg.get_memory("mem-1")
        assert retrieved is not None
        assert retrieved.subject == "User"
        assert retrieved.object == "Python"

    @pytest.mark.asyncio
    async def test_query_temporal(self, tmp_path: Path):
        from dawei.memory.memory_graph import MemoryGraph, MemoryEntry, MemoryType

        db_path = str(tmp_path / "memory.db")
        mg = MemoryGraph(db_path)

        now = datetime.now(timezone.utc)
        for i, obj in enumerate(["Python", "Rust", "Go"]):
            entry = MemoryEntry(
                id=f"lang-{i}",
                subject="User",
                predicate="knows",
                object=obj,
                valid_start=now,
                memory_type=MemoryType.FACT,
            )
            await mg.add_memory(entry)

        results = await mg.query_temporal(subject="User", predicate="knows")
        assert len(results) == 3
        objects = {r.object for r in results}
        assert objects == {"Python", "Rust", "Go"}

    @pytest.mark.asyncio
    async def test_query_by_type(self, tmp_path: Path):
        from dawei.memory.memory_graph import MemoryGraph, MemoryEntry, MemoryType

        db_path = str(tmp_path / "memory.db")
        mg = MemoryGraph(db_path)

        now = datetime.now(timezone.utc)
        await mg.add_memory(MemoryEntry(
            id="fact-1", subject="Project", predicate="uses", object="FastAPI",
            valid_start=now, memory_type=MemoryType.FACT,
        ))
        await mg.add_memory(MemoryEntry(
            id="pref-1", subject="User", predicate="prefers", object="dark mode",
            valid_start=now, memory_type=MemoryType.PREFERENCE,
        ))

        facts = await mg.query_temporal(memory_type=MemoryType.FACT)
        prefs = await mg.query_temporal(memory_type=MemoryType.PREFERENCE)
        assert len(facts) == 1
        assert len(prefs) == 1
        assert facts[0].object == "FastAPI"

    @pytest.mark.asyncio
    async def test_update_memory(self, tmp_path: Path):
        from dawei.memory.memory_graph import MemoryGraph, MemoryEntry, MemoryType

        db_path = str(tmp_path / "memory.db")
        mg = MemoryGraph(db_path)

        now = datetime.now(timezone.utc)
        await mg.add_memory(MemoryEntry(
            id="upd-1", subject="User", predicate="editor", object="vim",
            valid_start=now, memory_type=MemoryType.PREFERENCE,
        ))

        ok = await mg.update_memory("upd-1", object="emacs", confidence=0.99)
        assert ok

        updated = await mg.get_memory("upd-1")
        assert updated.object == "emacs"
        assert updated.confidence == 0.99

    @pytest.mark.asyncio
    async def test_delete_memory(self, tmp_path: Path):
        from dawei.memory.memory_graph import MemoryGraph, MemoryEntry, MemoryType

        db_path = str(tmp_path / "memory.db")
        mg = MemoryGraph(db_path)

        now = datetime.now(timezone.utc)
        await mg.add_memory(MemoryEntry(
            id="del-1", subject="X", predicate="is", object="gone",
            valid_start=now,
        ))
        assert await mg.get_memory("del-1") is not None

        ok = await mg.delete_memory("del-1")
        assert ok
        assert await mg.get_memory("del-1") is None

    @pytest.mark.asyncio
    async def test_search_memories(self, tmp_path: Path):
        from dawei.memory.memory_graph import MemoryGraph, MemoryEntry

        db_path = str(tmp_path / "memory.db")
        mg = MemoryGraph(db_path)

        now = datetime.now(timezone.utc)
        await mg.add_memory(MemoryEntry(
            id="s-1", subject="Project", predicate="language", object="Python programming",
            valid_start=now, keywords=["python", "backend"],
        ))
        await mg.add_memory(MemoryEntry(
            id="s-2", subject="User", predicate="hobby", object="photography",
            valid_start=now, keywords=["camera", "art"],
        ))

        results = await mg.search_memories("Python")
        assert len(results) >= 1
        assert any(r.id == "s-1" for r in results)

    @pytest.mark.asyncio
    async def test_get_stats(self, tmp_path: Path):
        from dawei.memory.memory_graph import MemoryGraph, MemoryEntry, MemoryType

        db_path = str(tmp_path / "memory.db")
        mg = MemoryGraph(db_path)

        now = datetime.now(timezone.utc)
        await mg.add_memory(MemoryEntry(
            id="stat-1", subject="A", predicate="b", object="c",
            valid_start=now, memory_type=MemoryType.FACT,
        ))
        await mg.add_memory(MemoryEntry(
            id="stat-2", subject="D", predicate="e", object="f",
            valid_start=now, memory_type=MemoryType.PREFERENCE,
        ))

        stats = await mg.get_stats()
        assert stats.total == 2
        assert "fact" in stats.by_type
        assert "preference" in stats.by_type

    @pytest.mark.asyncio
    async def test_energy_decay_and_boost(self, tmp_path: Path):
        """Energy decays on retrieval, can be boosted."""
        from dawei.memory.memory_graph import MemoryEntry, MemoryType

        now = datetime.now(timezone.utc)
        entry = MemoryEntry(
            id="energy-1", subject="X", predicate="y", object="z",
            valid_start=now, energy=1.0,
        )
        entry.decay_energy(0.9)
        assert entry.energy == pytest.approx(0.9)

        entry.boost_energy(0.3)
        assert entry.energy == pytest.approx(1.0)  # capped at 1.0


# ============================================================================
# Test: Knowledge Stores
# ============================================================================


class TestSQLiteFTSStore:
    """Test SQLiteFTSStore — full-text search."""

    @pytest.mark.asyncio
    async def test_add_and_search(self, tmp_path: Path):
        from dawei.knowledge.fulltext.sqlite_fts_store import SQLiteFTSStore
        from dawei.knowledge.models import DocumentChunk

        db_path = str(tmp_path / "fts.db")
        store = SQLiteFTSStore(db_path)
        await store.initialize()

        chunks = [
            DocumentChunk(id="c1", document_id="d1", chunk_index=0, content="Python is a programming language"),
            DocumentChunk(id="c2", document_id="d1", chunk_index=1, content="Rust is a systems programming language"),
            DocumentChunk(id="c3", document_id="d2", chunk_index=0, content="JavaScript runs in the browser"),
        ]
        await store.add_documents(chunks)

        results = await store.search("programming language", top_k=2)
        assert len(results) >= 1
        # Results are (chunk_id, score) tuples
        chunk_ids = [r[0] for r in results]
        assert "c1" in chunk_ids

    @pytest.mark.asyncio
    async def test_count_and_clear(self, tmp_path: Path):
        from dawei.knowledge.fulltext.sqlite_fts_store import SQLiteFTSStore
        from dawei.knowledge.models import DocumentChunk

        db_path = str(tmp_path / "fts2.db")
        store = SQLiteFTSStore(db_path)
        await store.initialize()

        await store.add_documents([
            DocumentChunk(id="x1", document_id="d1", chunk_index=0, content="hello world"),
        ])
        assert await store.count() == 1

        await store.clear()
        assert await store.count() == 0

    @pytest.mark.asyncio
    async def test_delete_document(self, tmp_path: Path):
        from dawei.knowledge.fulltext.sqlite_fts_store import SQLiteFTSStore
        from dawei.knowledge.models import DocumentChunk

        db_path = str(tmp_path / "fts3.db")
        store = SQLiteFTSStore(db_path)
        await store.initialize()

        await store.add_documents([
            DocumentChunk(id="y1", document_id="doc-a", chunk_index=0, content="alpha"),
            DocumentChunk(id="y2", document_id="doc-b", chunk_index=0, content="beta"),
        ])
        deleted = await store.delete_document("doc-a")
        assert deleted >= 1
        assert await store.count() == 1


class TestSQLiteVecStore:
    """Test SQLiteVecVectorStore — vector similarity search."""

    @pytest.mark.asyncio
    async def test_add_and_search(self, tmp_path: Path):
        from dawei.knowledge.vector.sqlite_vec_store import SQLiteVecVectorStore
        from dawei.knowledge.models import VectorDocument

        db_path = str(tmp_path / "vec.db")
        dim = 4
        store = SQLiteVecVectorStore(db_path, dimension=dim)
        await store.initialize()

        docs = [
            VectorDocument(id="v1", embedding=[1.0, 0.0, 0.0, 0.0], content="document one"),
            VectorDocument(id="v2", embedding=[0.0, 1.0, 0.0, 0.0], content="document two"),
            VectorDocument(id="v3", embedding=[0.9, 0.1, 0.0, 0.0], content="document three"),
        ]
        await store.add(docs)

        # Query with vector close to v1 and v3
        results = await store.search(query_embedding=[1.0, 0.0, 0.0, 0.0], top_k=2)
        assert len(results) >= 1
        result_ids = [r.id for r in results]
        assert "v1" in result_ids

    @pytest.mark.asyncio
    async def test_count_and_delete(self, tmp_path: Path):
        from dawei.knowledge.vector.sqlite_vec_store import SQLiteVecVectorStore
        from dawei.knowledge.models import VectorDocument

        db_path = str(tmp_path / "vec2.db")
        store = SQLiteVecVectorStore(db_path, dimension=4)
        await store.initialize()

        await store.add([
            VectorDocument(id="d1", embedding=[1.0, 0.0, 0.0, 0.0], content="doc1"),
            VectorDocument(id="d2", embedding=[0.0, 1.0, 0.0, 0.0], content="doc2"),
        ])
        assert await store.count() == 2

        deleted = await store.delete(["d1"])
        assert deleted >= 1
        assert await store.count() == 1


# ============================================================================
# Test: EmbeddingManager (unit — no API calls)
# ============================================================================


class TestEmbeddingManager:
    """Test EmbeddingManager — metadata and similarity (no API calls)."""

    def test_cosine_similarity_identical(self):
        from dawei.knowledge.embeddings.manager import EmbeddingManager

        vec = (1.0, 0.0, 0.0)
        sim = EmbeddingManager.cosine_similarity(vec, vec)
        assert sim == pytest.approx(1.0, abs=1e-6)

    def test_cosine_similarity_orthogonal(self):
        from dawei.knowledge.embeddings.manager import EmbeddingManager

        sim = EmbeddingManager.cosine_similarity((1.0, 0.0), (0.0, 1.0))
        assert sim == pytest.approx(0.0, abs=1e-6)

    def test_cosine_similarity_opposite(self):
        from dawei.knowledge.embeddings.manager import EmbeddingManager

        sim = EmbeddingManager.cosine_similarity((1.0, 0.0), (-1.0, 0.0))
        assert sim == pytest.approx(-1.0, abs=1e-6)

    def test_get_model_info(self):
        from dawei.knowledge.embeddings.manager import EmbeddingManager

        mgr = EmbeddingManager()
        info = mgr.get_model_info()
        assert info is not None
        assert info.dimension > 0

    def test_dimension_property(self):
        from dawei.knowledge.embeddings.manager import EmbeddingManager

        mgr = EmbeddingManager()
        assert mgr.dimension > 0

    def test_euclidean_distance(self):
        from dawei.knowledge.embeddings.manager import EmbeddingManager

        dist = EmbeddingManager.euclidean_distance([0, 0], [3, 4])
        assert dist == pytest.approx(5.0, abs=1e-6)

    def test_dot_product(self):
        from dawei.knowledge.embeddings.manager import EmbeddingManager

        dp = EmbeddingManager.dot_product([1, 2, 3], [4, 5, 6])
        assert dp == pytest.approx(32.0, abs=1e-6)


# ============================================================================
# Test: WorkspaceConfig / WorkspaceSettings
# ============================================================================


class TestWorkspaceConfig:
    """Test workspace configuration loading and defaults."""

    def test_default_config(self):
        from dawei.workspace.models import WorkspaceConfig

        config = WorkspaceConfig()
        assert config.agent.mode == "orchestrator"
        assert config.agent.auto_approve_tools is True
        assert config.memory.enabled is True
        assert config.skills.enabled is True
        assert config.tools.builtin_tools_enabled is True

    def test_config_from_dict(self):
        from dawei.workspace.models import WorkspaceConfig

        data = {
            "agent": {"auto_approve_tools": False, "max_concurrent_subtasks": 1},
            "memory": {"enabled": False},
            "skills": {"enabled": False, "auto_discovery": False},
        }
        config = WorkspaceConfig.from_dict(data)
        assert config.agent.auto_approve_tools is False
        assert config.agent.max_concurrent_subtasks == 1
        assert config.memory.enabled is False
        assert config.skills.enabled is False
        # Defaults preserved for unspecified fields
        assert config.tools.builtin_tools_enabled is True

    def test_config_from_none(self):
        from dawei.workspace.models import WorkspaceConfig

        config = WorkspaceConfig.from_dict(None)
        assert config.agent.mode == "orchestrator"

    def test_config_round_trip(self):
        from dawei.workspace.models import WorkspaceConfig

        config = WorkspaceConfig()
        dumped = config.model_dump_custom()
        restored = WorkspaceConfig.from_dict(dumped)
        assert restored.agent.mode == config.agent.mode
        assert restored.memory.enabled == config.memory.enabled

    def test_workspace_settings_defaults(self):
        from dawei.workspace.models import WorkspaceSettings

        settings = WorkspaceSettings()
        assert settings.auto_approval_enabled is True
        assert settings.always_allow_read_only is True
        assert settings.always_allow_execute is True
        assert settings.terminal_output_line_limit == 500

    def test_workspace_settings_from_dict(self):
        from dawei.workspace.models import WorkspaceSettings

        # The from_dict accepts camelCase keys (frontend format)
        data = {
            "autoApprovalEnabled": False,
            "alwaysAllowExecute": False,
            "deniedTools": ["dangerous_tool"],
        }
        settings = WorkspaceSettings.from_dict(data)
        assert settings.auto_approval_enabled is False
        assert settings.always_allow_execute is False
        assert "dangerous_tool" in settings.denied_tools


class TestWorkspaceInfo:
    """Test WorkspaceInfo data model."""

    def test_from_dict(self):
        from dawei.workspace.models import WorkspaceInfo

        data = {
            "id": "ws-123",
            "name": "my-ws",
            "display_name": "My Workspace",
            "description": "Test",
            "created_at": "2025-01-01T00:00:00Z",
        }
        info = WorkspaceInfo.from_dict(data)
        assert info.id == "ws-123"
        assert info.name == "my-ws"

    def test_to_dict_round_trip(self):
        from dawei.workspace.models import WorkspaceInfo

        data = {
            "id": "ws-rt",
            "name": "roundtrip",
            "display_name": "RT",
            "description": "RT test",
            "created_at": "2025-06-01T00:00:00Z",
        }
        info = WorkspaceInfo.from_dict(data)
        dumped = info.to_dict()
        restored = WorkspaceInfo.from_dict(dumped)
        assert restored.id == info.id
        assert restored.name == info.name


# ============================================================================
# Test: MCPConfig
# ============================================================================


class TestMCPConfig:
    """Test MCP config loading and merging."""

    def test_mcp_config_from_dict(self):
        from dawei.tools.mcp_tool_manager import MCPConfig

        data = {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
            "alwaysAllow": ["read_file", "write_file"],
            "timeout": 60,
        }
        config = MCPConfig.from_dict("test-server", data, source_level="workspace")
        assert config.server_name == "test-server"
        assert config.command == "npx"
        assert config.args == ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
        assert config.timeout == 60
        assert config.source_level == "workspace"

    def test_mcp_config_to_dict(self):
        from dawei.tools.mcp_tool_manager import MCPConfig

        config = MCPConfig(
            server_name="s1",
            command="node",
            args=["server.js"],
            timeout=120,
        )
        d = config.to_dict()
        assert d["server_name"] == "s1"
        assert d["command"] == "node"

    def test_mcp_config_merge_workspace_overrides_user(self):
        from dawei.tools.mcp_tool_manager import MCPConfig

        user = MCPConfig(server_name="x", command="node", args=["a"], timeout=60, source_level="user")
        workspace = MCPConfig(server_name="x", command="node", args=["b"], timeout=120, source_level="workspace")

        merged = user.merge_with(workspace)
        assert merged.source_level == "workspace"
        assert merged.args == ["b"]  # workspace wins
        assert merged.timeout == 120

    def test_mcp_config_loader_no_files(self, tmp_path: Path):
        """MCPConfigLoader returns empty dict when no config files exist."""
        from dawei.tools.mcp_tool_manager import MCPConfigLoader

        loader = MCPConfigLoader()
        # User configs from ~/.dawei/configs/mcp.json — just check it doesn't crash
        user_configs = loader.load_user_mcp_configs()
        assert isinstance(user_configs, dict)

        workspace_configs = loader.load_workspace_mcp_configs(str(tmp_path))
        assert isinstance(workspace_configs, dict)


# ============================================================================
# Test: PluginsConfig
# ============================================================================


class TestPluginsConfig:
    """Test plugin configuration management."""

    def test_default_empty(self):
        from dawei.workspace.models import PluginsConfig

        pc = PluginsConfig()
        assert len(pc.plugins) == 0

    def test_enable_disable_plugin(self):
        from dawei.workspace.models import PluginsConfig, PluginInstanceConfig

        pc = PluginsConfig()
        pc.plugins["my-plugin"] = PluginInstanceConfig(enabled=False, activated=False)

        pc.enable_plugin("my-plugin")
        assert pc.plugins["my-plugin"].enabled is True

        pc.disable_plugin("my-plugin")
        assert pc.plugins["my-plugin"].enabled is False

    def test_get_set_plugin_config(self):
        from dawei.workspace.models import PluginsConfig, PluginInstanceConfig

        pc = PluginsConfig()
        assert pc.get_plugin_config("nonexistent") is None

        cfg = PluginInstanceConfig(enabled=True, version="1.0.0")
        pc.set_plugin_config("new-plugin", cfg)
        retrieved = pc.get_plugin_config("new-plugin")
        assert retrieved.version == "1.0.0"
