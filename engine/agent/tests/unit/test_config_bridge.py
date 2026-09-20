# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""配置桥接测试。

验证 ``workspace_config_to_agent_dict`` 把 ``WorkspaceConfig``（config.json）正确映射为
``Config`` 可接受的扁平 dict（含命名错位修正、mode 枚举健壮性），以及优先级
``AGENT_* env > 调用方 dict > workspace config.json > 默认``。
"""

import json
import os
from types import SimpleNamespace

import pytest

from dawei.core.utils.config_utils import (
    validate_and_create_config,
    workspace_config_to_agent_dict,
)
from dawei.workspace.models import WorkspaceConfig


@pytest.fixture(autouse=True)
def _isolate_agent_env(monkeypatch):
    """清除真实环境里的 AGENT_* 变量，防止污染配置测试。"""
    for k in list(os.environ):
        if k.startswith("AGENT_"):
            monkeypatch.delenv(k, raising=False)


class TestWorkspaceConfigToAgentDict:
    def test_default_config_is_safe(self):
        d = workspace_config_to_agent_dict(WorkspaceConfig())
        assert isinstance(d, dict)
        assert d["enable_skills"] is True
        assert d["plan_mode_confirm_required"] is True
        assert d["mode"] == "orchestrator"

    def test_name_mismatches_translated(self):
        cfg = WorkspaceConfig()
        cfg.skills.enabled = False
        cfg.tools.default_timeout = 42
        cfg.compression.max_tokens = 12345
        cfg.logging.level = "DEBUG"
        d = workspace_config_to_agent_dict(cfg)
        assert d["enable_skills"] is False  # skills.enabled → enable_skills
        assert d["tool_execution_timeout"] == 42  # tools.default_timeout → tool_execution_timeout
        assert d["max_context_tokens"] == 12345  # compression.max_tokens → max_context_tokens
        assert d["log_level"] == "DEBUG"  # logging.level → log_level

    def test_agent_section_fields(self):
        cfg = WorkspaceConfig()
        cfg.agent.enable_auto_mode_switch = True
        cfg.agent.max_concurrent_subtasks = 7
        d = workspace_config_to_agent_dict(cfg)
        assert d["enable_auto_mode_switch"] is True
        assert d["max_concurrent_subtasks"] == 7

    def test_checkpoint_and_compression(self):
        cfg = WorkspaceConfig()
        cfg.checkpoint.checkpoint_interval = 99
        cfg.checkpoint.enable_compression = False
        cfg.compression.compression_threshold = 0.77
        d = workspace_config_to_agent_dict(cfg)
        assert d["checkpoint_interval"] == 99
        assert d["enable_checkpoint_compression"] is False  # enable_compression → ...
        assert d["compression_threshold"] == 0.77

    def test_non_agent_mode_is_skipped_not_raised(self):
        """PDCA 子模式（非 AgentMode）不应崩溃，mode 键被跳过，其余字段正常。"""
        fake = SimpleNamespace(
            agent=SimpleNamespace(
                mode="plan",  # 非 AgentMode（orchestrator/pdca）
                plan_mode_confirm_required=True,
                enable_auto_mode_switch=False,
                auto_approve_tools=True,
                max_concurrent_subtasks=3,
            ),
            skills=SimpleNamespace(enabled=True),
            checkpoint=SimpleNamespace(
                checkpoint_interval=300, max_checkpoints=10, enable_compression=True,
                auto_create_enabled=True, min_interval_minutes=5,
                max_checkpoints_per_task=50, validation_enabled=True,
            ),
            compression=SimpleNamespace(compression_threshold=0.5, max_tokens=100000),
            logging=SimpleNamespace(level="INFO", enable_performance_logging=True),
            tools=SimpleNamespace(default_timeout=60),
        )
        d = workspace_config_to_agent_dict(fake)
        assert "mode" not in d  # 跳过
        assert d["plan_mode_confirm_required"] is True

    def test_malformed_object_returns_empty(self):
        assert workspace_config_to_agent_dict(object()) == {}


class TestBridgePrecedence:
    def test_workspace_config_flows_into_config(self):
        cfg = WorkspaceConfig()
        cfg.agent.max_concurrent_subtasks = 9
        c = validate_and_create_config(workspace_config_to_agent_dict(cfg))
        assert c.max_concurrent_subtasks == 9
        assert c.enable_skills is True

    def test_env_overrides_workspace(self, monkeypatch):
        """AGENT_* env 必须胜过 workspace config（保护现有 env 部署）。"""
        cfg = WorkspaceConfig()
        cfg.skills.enabled = True  # workspace 说开
        monkeypatch.setenv("AGENT_ENABLE_SKILLS", "false")  # env 说关
        c = validate_and_create_config(workspace_config_to_agent_dict(cfg))
        assert c.enable_skills is False  # env 胜

    def test_caller_dict_overrides_workspace(self):
        """工厂里 {**base, **caller}：调用方键覆盖 workspace。"""
        cfg = WorkspaceConfig()
        cfg.agent.max_concurrent_subtasks = 9
        merged = {**workspace_config_to_agent_dict(cfg), "max_concurrent_subtasks": 2}
        c = validate_and_create_config(merged)
        assert c.max_concurrent_subtasks == 2


class TestReconciledDefaults:
    """默认值对齐运行时，桥接不改变既有行为。"""

    def test_memory_decay_default_matches_gardener(self):
        # 0.95 对齐 MemoryGardener 运行时默认（原 0.1 会造成 9.5x 衰减回归）
        assert WorkspaceConfig().memory.energy_decay_rate == 0.95

    def test_tools_concurrent_default_matches_task_manager(self):
        # 10 对齐 AsyncTaskManagerConfig 运行时默认（原 3 会降低并发）
        assert WorkspaceConfig().tools.max_concurrent_executions == 10


class TestSkillsGating:
    """config.skills.enabled → tool_manager_wrapper._init_skill_manager 门控（Phase 2.2）。"""

    def test_disabled_skills_skips_discovery(self, tmp_path):
        """skills.enabled=false → _init_skill_manager 直接置 skill_manager=None，不发现 skills。"""
        from dawei.workspace.tool_manager_wrapper import WorkspaceToolManager

        cfg_dir = tmp_path / ".dawei"
        cfg_dir.mkdir()
        (cfg_dir / "config.json").write_text(
            json.dumps({"skills": {"enabled": False}}), encoding="utf-8"
        )

        wtm = WorkspaceToolManager(workspace_root=tmp_path)
        wtm._init_skill_manager()  # 同步方法；disabled 分支在构造 SkillManager 前返回

        assert wtm.skill_manager is None  # 门控生效：跳过 discover_skills
        # _create_skills_tools 在 skill_manager=None 时返回空
        assert wtm._create_skills_tools() == []
