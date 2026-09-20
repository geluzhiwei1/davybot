# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Tests for Evolution Cycle Manager (Fused Architecture)

测试融合架构后的EvolutionCycleManager：
- TaskGraph创建（root + 4 phase子任务节点）
- Phase → Mode映射（plan→plan, do→do, check→check, act→act）
- TaskGraph状态同步
- 暂停/恢复/中止逻辑
- Metadata状态管理

所有测试mock Agent执行和TaskGraph（不需要真实LLM调用或TaskGraph初始化）。
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dawei.entity.task_types import TaskStatus


# ==================== Fixtures ====================


class FakeWorkspace:
    """Fake UserWorkspace for testing"""

    workspace_id: str = "test-workspace-001"
    workspace_path: str = ""
    workspace_config: dict = {"evolution": {"enabled": True}}
    event_bus = None

    class _FakeTaskContext:
        def __init__(self):
            self.metadata = {}
            self.parent_context = None

        def to_dict(self):
            return {
                "metadata": dict(self.metadata),
                "parent_context": self.parent_context,
            }

    def create_task_context(self):
        return self._FakeTaskContext()


@pytest.fixture
def tmp_workspace(tmp_path):
    """Create a fake workspace with .dawei directory"""
    dawei_dir = tmp_path / ".dawei"
    dawei_dir.mkdir()
    (dawei_dir / "workspace.md").write_text("Goal: improve code quality\nSuccess criteria: tests pass", encoding="utf-8")

    ws = FakeWorkspace()
    ws.workspace_path = str(tmp_path)
    return ws


@pytest.fixture(autouse=True)
def patch_isinstance():
    """Patch isinstance checks in evolution modules to accept FakeWorkspace"""
    _original_isinstance = isinstance

    def _patched_isinstance(obj, classinfo):
        if _original_isinstance(obj, FakeWorkspace) and classinfo is not FakeWorkspace:
            target = classinfo if isinstance(classinfo, tuple) else (classinfo,)
            from dawei.workspace.user_workspace import UserWorkspace

            if UserWorkspace in target:
                return True
        return _original_isinstance(obj, classinfo)

    import builtins

    original = builtins.isinstance
    builtins.isinstance = _patched_isinstance
    yield
    builtins.isinstance = original


@pytest.fixture
def mock_task_graph():
    """Create a mock TaskGraph with basic API"""
    tg = AsyncMock()

    # Root task
    root_node = MagicMock()
    root_node.task_node_id = "evolution-001"
    root_node.status = TaskStatus.RUNNING
    tg.get_root_task = AsyncMock(return_value=root_node)

    # Subtask nodes
    plan_node = MagicMock()
    plan_node.task_node_id = "evolution-001-plan"
    plan_node.mode = "plan"
    plan_node.status = TaskStatus.PENDING
    plan_node.context.metadata = {"evolution_cycle_id": "001", "phase": "plan"}

    do_node = MagicMock()
    do_node.task_node_id = "evolution-001-do"
    do_node.mode = "do"
    do_node.status = TaskStatus.PENDING
    do_node.context.metadata = {"evolution_cycle_id": "001", "phase": "do"}

    check_node = MagicMock()
    check_node.task_node_id = "evolution-001-check"
    check_node.mode = "check"
    check_node.status = TaskStatus.PENDING
    check_node.context.metadata = {"evolution_cycle_id": "001", "phase": "check"}

    act_node = MagicMock()
    act_node.task_node_id = "evolution-001-act"
    act_node.mode = "act"
    act_node.status = TaskStatus.PENDING
    act_node.context.metadata = {"evolution_cycle_id": "001", "phase": "act"}

    tg.get_subtasks = AsyncMock(return_value=[plan_node, do_node, check_node, act_node])
    tg.create_root_task = AsyncMock(return_value=root_node)
    tg.create_subtask = AsyncMock()
    tg.update_task_status = AsyncMock(return_value=True)
    tg.cleanup = AsyncMock()

    return tg


# ==================== PHASE_MODE_MAP Tests ====================


class TestPhaseModeMap:
    """测试Phase → Mode映射"""

    def test_plan_maps_to_plan_mode(self):
        from dawei.evolution.evolution_manager import PHASE_MODE_MAP

        assert PHASE_MODE_MAP["plan"] == "plan"

    def test_do_maps_to_do_mode(self):
        from dawei.evolution.evolution_manager import PHASE_MODE_MAP

        assert PHASE_MODE_MAP["do"] == "do"

    def test_check_maps_to_check_mode(self):
        from dawei.evolution.evolution_manager import PHASE_MODE_MAP

        assert PHASE_MODE_MAP["check"] == "check"

    def test_act_maps_to_act_mode(self):
        from dawei.evolution.evolution_manager import PHASE_MODE_MAP

        assert PHASE_MODE_MAP["act"] == "act"

    def test_all_phases_have_mapping(self):
        from dawei.evolution.evolution_manager import PHASE_MODE_MAP

        for phase in ("plan", "do", "check", "act"):
            assert phase in PHASE_MODE_MAP
            assert PHASE_MODE_MAP[phase] == phase


# ==================== EvolutionPromptBuilder Integration Tests ====================


class TestPromptBuilderIntegration:
    """测试Prompt Builder与mode系统的集成"""

    def test_builder_does_not_set_agent_role(self):
        """融合后builder不应定义agent角色（由内置mode处理）"""
        from dawei.evolution.prompts import EvolutionPromptBuilder

        builder = EvolutionPromptBuilder()
        empty_inputs = {"workspace_md": "", "prev_action": "", "prev_cycle_id": None}

        for phase in ["plan", "do", "check", "act"]:
            result = builder.build(phase, empty_inputs, "001", None)
            assert "strategic planner" not in result
            assert "quality assurance analyst" not in result
            assert "continuous improvement coordinator" not in result
            assert "executor responsible" not in result

    def test_builder_injects_evolution_context(self):
        """builder应注入evolution特有的上下文"""
        from dawei.evolution.prompts import EvolutionPromptBuilder

        builder = EvolutionPromptBuilder()
        inputs = {"workspace_md": "Goal: X", "prev_action": "Prev action", "prev_cycle_id": "000"}

        result = builder.build("plan", inputs, "001", "000")

        assert "Evolution Cycle 001" in result
        assert "Goal: X" in result
        assert "Previous Cycle (000)" in result


# ==================== EvolutionCycleManager Tests ====================


class TestEvolutionCycleManager:
    """EvolutionCycleManager单元测试"""

    def test_invalid_workspace_raises(self):
        """非UserWorkspace应抛出EvolutionError"""
        from dawei.evolution.evolution_manager import EvolutionCycleManager
        from dawei.evolution.exceptions import EvolutionError

        with pytest.raises(EvolutionError, match="workspace must be UserWorkspace"):
            EvolutionCycleManager("not a workspace")

    @pytest.mark.asyncio
    async def test_init_sets_task_graphs_empty(self, tmp_workspace):
        """初始化后_task_graphs应为空"""
        from dawei.evolution.evolution_manager import EvolutionCycleManager

        manager = EvolutionCycleManager(tmp_workspace)
        assert manager._task_graphs == {}

    @pytest.mark.asyncio
    async def test_get_task_graph_returns_none_for_unknown(self, tmp_workspace):
        """未知cycle_id应返回None"""
        from dawei.evolution.evolution_manager import EvolutionCycleManager

        manager = EvolutionCycleManager(tmp_workspace)
        assert manager.get_task_graph("nonexistent") is None

    @pytest.mark.asyncio
    async def test_generate_cycle_id_first(self, tmp_workspace):
        """第一个cycle_id应为001"""
        from dawei.evolution.evolution_manager import EvolutionCycleManager

        manager = EvolutionCycleManager(tmp_workspace)
        cycle_id = await manager._generate_cycle_id()
        assert cycle_id == "001"

    @pytest.mark.asyncio
    async def test_init_metadata_structure(self, tmp_workspace):
        """metadata初始化应包含所有必要字段"""
        from dawei.evolution.evolution_manager import EvolutionCycleManager

        manager = EvolutionCycleManager(tmp_workspace)
        metadata = manager._init_metadata("001", None)

        assert metadata["cycle_id"] == "001"
        assert metadata["status"] == "running"
        assert metadata["current_phase"] is None
        for phase in ("plan", "do", "check", "act"):
            assert phase in metadata["phases"]
            assert metadata["phases"][phase]["status"] == "pending"
        assert metadata["context"]["previous_cycle_id"] is None
        assert metadata["context"]["pause_count"] == 0

    @pytest.mark.asyncio
    async def test_init_metadata_with_prev_cycle(self, tmp_workspace):
        """metadata初始化应包含prev_cycle_id"""
        from dawei.evolution.evolution_manager import EvolutionCycleManager

        manager = EvolutionCycleManager(tmp_workspace)
        metadata = manager._init_metadata("002", "001")

        assert metadata["context"]["previous_cycle_id"] == "001"


# ==================== TaskGraph Creation Tests ====================


class TestTaskGraphCreation:
    """测试TaskGraph骨架创建（mock TaskGraph初始化）"""

    @pytest.mark.asyncio
    @patch("dawei.task_graph.TaskGraph")
    async def test_create_cycle_task_graph_calls_create_root(self, MockTaskGraph, tmp_workspace, mock_task_graph):
        """应调用create_root_task创建root节点"""
        from dawei.evolution.evolution_manager import EvolutionCycleManager

        MockTaskGraph.return_value = mock_task_graph

        manager = EvolutionCycleManager(tmp_workspace)
        await manager._create_cycle_task_graph("001", None)

        # Verify root task created
        mock_task_graph.create_root_task.assert_called_once()
        root_call = mock_task_graph.create_root_task.call_args
        assert root_call[0][0].task_node_id == "evolution-001"
        assert root_call[0][0].mode == "orchestrator"
        assert root_call[0][0].status == TaskStatus.RUNNING

    @pytest.mark.asyncio
    @patch("dawei.task_graph.TaskGraph")
    async def test_create_cycle_task_graph_creates_4_subtasks(self, MockTaskGraph, tmp_workspace, mock_task_graph):
        """应为每个phase创建子任务节点"""
        from dawei.evolution.evolution_manager import EvolutionCycleManager

        MockTaskGraph.return_value = mock_task_graph

        manager = EvolutionCycleManager(tmp_workspace)
        await manager._create_cycle_task_graph("001", None)

        # Should create 4 subtasks (one per phase)
        assert mock_task_graph.create_subtask.call_count == 4

        # Verify each subtask uses the correct mode
        call_args_list = mock_task_graph.create_subtask.call_args_list
        modes = [call.kwargs["task_data"].mode for call in call_args_list]
        assert modes == ["plan", "do", "check", "act"]

    @pytest.mark.asyncio
    @patch("dawei.task_graph.TaskGraph")
    async def test_create_cycle_task_graph_uses_workspace_event_bus(self, MockTaskGraph, tmp_workspace, mock_task_graph):
        """应使用workspace的event_bus创建TaskGraph"""
        from dawei.evolution.evolution_manager import EvolutionCycleManager

        tmp_workspace.event_bus = MagicMock()
        MockTaskGraph.return_value = mock_task_graph

        manager = EvolutionCycleManager(tmp_workspace)
        await manager._create_cycle_task_graph("001", None)

        MockTaskGraph.assert_called_once_with(task_id="evolution-001", event_bus=tmp_workspace.event_bus)

    @pytest.mark.asyncio
    @patch("dawei.task_graph.TaskGraph")
    async def test_create_cycle_task_graph_creates_event_bus_when_missing(self, MockTaskGraph, tmp_workspace, mock_task_graph):
        """workspace无event_bus时应创建SimpleEventBus"""
        from dawei.evolution.evolution_manager import EvolutionCycleManager

        # FakeWorkspace has no event_bus attribute by default
        MockTaskGraph.return_value = mock_task_graph

        manager = EvolutionCycleManager(tmp_workspace)
        await manager._create_cycle_task_graph("001", None)

        MockTaskGraph.assert_called_once()
        call_kwargs = MockTaskGraph.call_args
        # event_bus should be a SimpleEventBus instance (not None)
        assert call_kwargs.kwargs["event_bus"] is not None

    @pytest.mark.asyncio
    @patch("dawei.task_graph.TaskGraph")
    async def test_task_graph_stored_in_manager(self, MockTaskGraph, tmp_workspace, mock_task_graph):
        """_create_cycle_task_graph返回的TaskGraph在start_cycle中会被存储"""
        from dawei.evolution.evolution_manager import EvolutionCycleManager

        MockTaskGraph.return_value = mock_task_graph

        manager = EvolutionCycleManager(tmp_workspace)
        result = await manager._create_cycle_task_graph("001", None)

        # _create_cycle_task_graph returns the TaskGraph
        assert result is mock_task_graph

        # Simulate what start_cycle does: store in _task_graphs
        manager._task_graphs["001"] = result
        assert manager.get_task_graph("001") is mock_task_graph


# ==================== Pause/Resume/Abort Tests ====================


class TestPauseResumeAbort:
    """测试暂停/恢复/中止逻辑

    Note: pause/resume/abort tests operate on metadata directly without going through
    persistence_manager.save_evolution_metadata (which requires ResourceType.EVOLUTION
    to be registered in persistence_manager's dir_map). We mock the persistence layer.
    """

    @pytest.mark.asyncio
    async def test_pause_running_cycle(self, tmp_workspace):
        """暂停running状态的cycle应成功"""
        from dawei.evolution.evolution_manager import EvolutionCycleManager
        from dawei.evolution.exceptions import EvolutionStateError

        manager = EvolutionCycleManager(tmp_workspace)

        # Directly set metadata in storage (bypass persistence_manager)
        await manager.storage.create_cycle_directory("001")
        metadata = manager._init_metadata("001", None)
        metadata["status"] = "running"

        # Mock save/load to avoid ResourceType.EVOLUTION KeyError
        manager.storage.save_metadata = AsyncMock(return_value=True)
        manager.storage.load_metadata = AsyncMock(return_value=metadata)

        await manager.pause_cycle("001")

        assert metadata["status"] == "paused"
        assert metadata["paused_at"] is not None
        assert metadata["context"]["pause_count"] == 1
        # Verify save was called
        manager.storage.save_metadata.assert_called()

    @pytest.mark.asyncio
    async def test_pause_completed_cycle_raises(self, tmp_workspace):
        """暂停completed状态的cycle应抛出EvolutionStateError"""
        from dawei.evolution.evolution_manager import EvolutionCycleManager
        from dawei.evolution.exceptions import EvolutionStateError

        manager = EvolutionCycleManager(tmp_workspace)

        metadata = manager._init_metadata("001", None)
        metadata["status"] = "completed"
        manager.storage.load_metadata = AsyncMock(return_value=metadata)

        with pytest.raises(EvolutionStateError, match="Cannot pause"):
            await manager.pause_cycle("001")

    @pytest.mark.asyncio
    async def test_resume_paused_cycle(self, tmp_workspace):
        """恢复paused状态的cycle应成功"""
        from dawei.evolution.evolution_manager import EvolutionCycleManager

        manager = EvolutionCycleManager(tmp_workspace)

        metadata = manager._init_metadata("001", None)
        metadata["status"] = "paused"
        manager.storage.load_metadata = AsyncMock(return_value=metadata)
        manager.storage.save_metadata = AsyncMock(return_value=True)

        await manager.resume_cycle("001")

        assert metadata["status"] == "running"
        assert metadata["context"]["resume_count"] == 1

    @pytest.mark.asyncio
    async def test_resume_running_cycle_raises(self, tmp_workspace):
        """恢复非paused状态的cycle应抛出EvolutionStateError"""
        from dawei.evolution.evolution_manager import EvolutionCycleManager
        from dawei.evolution.exceptions import EvolutionStateError

        manager = EvolutionCycleManager(tmp_workspace)

        metadata = manager._init_metadata("001", None)
        metadata["status"] = "running"
        manager.storage.load_metadata = AsyncMock(return_value=metadata)

        with pytest.raises(EvolutionStateError, match="Cannot resume"):
            await manager.resume_cycle("001")

    @pytest.mark.asyncio
    async def test_abort_running_cycle(self, tmp_workspace):
        """中止running状态的cycle应设置abort_event"""
        from dawei.evolution.evolution_manager import EvolutionCycleManager

        manager = EvolutionCycleManager(tmp_workspace)

        metadata = manager._init_metadata("001", None)
        metadata["status"] = "running"
        manager.storage.load_metadata = AsyncMock(return_value=metadata)

        await manager.abort_cycle("001", reason="test abort")

        assert manager._abort_event.is_set()

    @pytest.mark.asyncio
    async def test_abort_paused_cycle(self, tmp_workspace):
        """中止paused状态的cycle也应成功"""
        from dawei.evolution.evolution_manager import EvolutionCycleManager

        manager = EvolutionCycleManager(tmp_workspace)

        metadata = manager._init_metadata("001", None)
        metadata["status"] = "paused"
        manager.storage.load_metadata = AsyncMock(return_value=metadata)

        await manager.abort_cycle("001")

        assert manager._abort_event.is_set()

    @pytest.mark.asyncio
    async def test_abort_completed_cycle_raises(self, tmp_workspace):
        """中止completed状态的cycle应抛出EvolutionStateError"""
        from dawei.evolution.evolution_manager import EvolutionCycleManager
        from dawei.evolution.exceptions import EvolutionStateError

        manager = EvolutionCycleManager(tmp_workspace)

        metadata = manager._init_metadata("001", None)
        metadata["status"] = "completed"
        manager.storage.load_metadata = AsyncMock(return_value=metadata)

        with pytest.raises(EvolutionStateError, match="Cannot abort"):
            await manager.abort_cycle("001")
