# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Unit tests for the unified security policy model + merge helpers (Phase 1).

Merge semantics: override-or-inherit. The user level supplies defaults; the
workspace freely overrides any field in either direction (no "tighten-only").
"""

import pytest

from dawei.core.effective_policy import (
    EffectiveSecurityPolicy,
    TOOL_RISK_LEVELS,
    WorkspaceSecurityOverride,
    get_tool_risk,
    merge_override,
    merge_override_list,
    risk_at_least,
)
from pydantic import ValidationError
from dawei.core.security_manager import security_manager


# ---------------- merge helpers ----------------


class TestMergeOverride:
    def test_workspace_value_wins(self):
        assert merge_override(True, False) is False
        assert merge_override(30, 120) == 120  # workspace may raise a ceiling
        assert merge_override("docker", "podman") == "podman"

    def test_none_inherits_user_default(self):
        assert merge_override(True, None) is True
        assert merge_override(30, None) == 30

    def test_workspace_can_loosen(self):
        # explicitly: no monotonic clamping — a workspace may turn shell on
        # even if the user default is off.
        assert merge_override(False, True) is True


class TestMergeOverrideList:
    def test_workspace_list_replaces(self):
        assert merge_override_list(["ls", "cat"], ["git"]) == ["git"]

    def test_empty_workspace_list_replaces(self):
        # an explicitly-set empty list is authoritative, not "inherit"
        assert merge_override_list(["ls", "cat"], []) == []

    def test_none_inherits_user_list(self):
        # order is preserved (override-or-inherit does not sort)
        assert merge_override_list(["ls", "cat"], None) == ["ls", "cat"]

    def test_none_user_default(self):
        assert merge_override_list(None, ["git"]) == ["git"]
        assert merge_override_list(None, None) == []


# ---------------- typed effective policy ----------------


class TestEffectiveSecurityPolicy:
    def test_from_merged_dict_roundtrip(self):
        merged = {
            "enable_command_whitelist": True,
            "use_system_command_whitelist": False,
            "allowed_commands": ["ls", "cat"],
            "denied_commands": ["rm"],
            "allow_shell_commands": True,
            "allow_background_commands": False,
            "allow_pipe_commands": False,
            "command_execution_timeout": 10,
            "enable_sandbox": True,
            "container_runtime": "docker",
            "drop_all_capabilities": True,
            "no_new_privileges": False,
            "sandbox_disable_network": True,
        }
        p = EffectiveSecurityPolicy.from_merged_dict(merged)
        assert p.command.enable_command_whitelist is True
        assert p.command.allowed_commands == ["ls", "cat"]
        assert p.command.command_execution_timeout == 10
        assert p.sandbox.enable_sandbox is True
        assert p.sandbox.container_runtime == "docker"
        assert p.sandbox.no_new_privileges is False

    def test_defaults_when_empty(self):
        p = EffectiveSecurityPolicy.from_merged_dict({})
        assert p.command.enable_command_whitelist is True
        assert p.command.command_execution_timeout == 30
        assert p.sandbox.enable_sandbox is False
        assert p.sandbox.container_runtime == "auto"


class TestWorkspaceSecurityOverride:
    """Schema validation for the workspace PUT body (override-or-inherit:
    validates type/enum/range, drops unknown keys, does NOT reject loosening)."""

    def test_valid_camelcase_and_drops_unknown(self):
        o = WorkspaceSecurityOverride.model_validate(
            {
                "enableCommandWhitelist": True,
                "commandExecutionTimeout": 120,
                "customAllowedCommands": ["ls", "git"],
                "containerRuntime": "docker",
                "bogusUnknownKey": 123,
            }
        )
        d = o.model_dump(exclude_none=True, by_alias=True)
        assert "enableCommandWhitelist" in d
        assert "bogusUnknownKey" not in d
        assert d["commandExecutionTimeout"] == 120

    def test_empty_means_all_inherit(self):
        assert WorkspaceSecurityOverride.model_validate({}).model_dump(
            exclude_none=True, by_alias=True
        ) == {}

    def test_rejects_bad_enum(self):
        with pytest.raises(ValidationError):
            WorkspaceSecurityOverride.model_validate({"containerRuntime": "kubernetes"})

    def test_rejects_out_of_range(self):
        for bad in (0, -5, 99999):
            with pytest.raises(ValidationError):
                WorkspaceSecurityOverride.model_validate({"commandExecutionTimeout": bad})

    def test_rejects_non_bool_like_string(self):
        # Pydantic lax mode coerces bool-like strings ('yes'/'no'/'true'); a
        # non-bool-like value must still be rejected.
        with pytest.raises(ValidationError):
            WorkspaceSecurityOverride.model_validate({"allowShellCommands": "maybe"})
        with pytest.raises(ValidationError):
            WorkspaceSecurityOverride.model_validate({"allowShellCommands": 123})


@pytest.fixture(scope="module", autouse=True)
def _load_security_manager():
    """Ensure the singleton is loaded before assertions read it."""
    security_manager.load()


class TestSecurityManagerPolicy:
    def test_get_policy_consistent_with_get_settings(self):
        settings = security_manager.get_settings()
        policy = security_manager.get_policy()
        # command domain parity
        assert policy.command.enable_command_whitelist == settings.get("enable_command_whitelist")
        assert policy.command.command_execution_timeout == settings.get("command_execution_timeout", 30)
        assert policy.command.allowed_commands == list(settings.get("allowed_commands", []))
        # sandbox domain parity
        assert policy.sandbox.enable_sandbox == settings.get("enable_sandbox")
        assert policy.sandbox.container_runtime == settings.get("container_runtime", "auto")

    def test_get_policy_is_typed(self):
        policy = security_manager.get_policy()
        assert isinstance(policy, EffectiveSecurityPolicy)
        assert isinstance(policy.command.allowed_commands, list)


class TestToolRiskMatrix:
    """P2.1 — tool risk classification + tool policy merge (override-or-inherit)."""

    def test_known_risks(self):
        assert get_tool_risk("execute_command") == "critical"
        assert get_tool_risk("use_mcp_tool") == "critical"
        assert get_tool_risk("write_text_file") == "high"
        assert get_tool_risk("list_files") == "low"

    def test_unknown_defaults_medium(self):
        assert get_tool_risk("does_not_exist") == "medium"

    def test_risk_at_least(self):
        assert risk_at_least("critical", "high") is True
        assert risk_at_least("low", "high") is False
        assert risk_at_least("high", "high") is True

    def test_override_schema_accepts_tool_fields(self):
        o = WorkspaceSecurityOverride.model_validate(
            {"customDeniedTools": ["execute_command"], "requireApprovalRisk": "high"}
        )
        d = o.model_dump(exclude_none=True, by_alias=True)
        assert d["customDeniedTools"] == ["execute_command"]
        assert d["requireApprovalRisk"] == "high"

    def test_override_rejects_bad_risk_enum(self):
        with pytest.raises(ValidationError):
            WorkspaceSecurityOverride.model_validate({"requireApprovalRisk": "bogus"})

    def test_tool_policy_inherits_user_baseline(self):
        from dawei.workspace.user_security_settings import UserSecuritySettings

        security_manager._user_settings = UserSecuritySettings(
            base_denied_tools=["execute_command"], require_approval_risk="high"
        )
        security_manager._workspace_security = {}
        security_manager._merged = None
        tp = security_manager.get_policy().tools
        assert tp.denied_tools == ["execute_command"]
        assert tp.require_approval_risk == "high"

    def test_tool_policy_workspace_replaces_deny(self):
        from dawei.workspace.user_security_settings import UserSecuritySettings

        security_manager._user_settings = UserSecuritySettings(
            base_denied_tools=["execute_command"]
        )
        security_manager._workspace_security = {"customDeniedTools": ["write_text_file"]}
        security_manager._merged = None
        # override-or-inherit: workspace list replaces the user list
        assert security_manager.get_policy().tools.denied_tools == ["write_text_file"]


class TestMCPPolicy:
    """P3 域6 — MCP server allow/deny policy (override-or-inherit)."""

    def test_inherits_user_deny(self):
        from dawei.workspace.user_security_settings import UserSecuritySettings

        security_manager._user_settings = UserSecuritySettings(
            base_denied_mcp_servers=["evil-mcp"]
        )
        security_manager._workspace_security = {}
        security_manager._merged = None
        mp = security_manager.get_policy().mcp
        assert mp.denied_mcp_servers == ["evil-mcp"]
        assert mp.allowed_mcp_servers == []  # empty = all allowed

    def test_workspace_replaces_deny(self):
        from dawei.workspace.user_security_settings import UserSecuritySettings

        security_manager._user_settings = UserSecuritySettings(
            base_denied_mcp_servers=["evil-mcp"]
        )
        security_manager._workspace_security = {"customDeniedMcpServers": ["other"]}
        security_manager._merged = None
        assert security_manager.get_policy().mcp.denied_mcp_servers == ["other"]

    def test_override_schema_accepts_mcp_fields(self):
        o = WorkspaceSecurityOverride.model_validate(
            {"customDeniedMcpServers": ["x"], "customAllowedMcpServers": ["y"]}
        )
        d = o.model_dump(exclude_none=True, by_alias=True)
        assert d["customDeniedMcpServers"] == ["x"]
        assert d["customAllowedMcpServers"] == ["y"]


class TestAutonomyPolicy:
    """P3 域9 — autonomous / scheduled execution (override-or-inherit)."""

    def test_defaults(self):
        from dawei.workspace.user_security_settings import UserSecuritySettings

        security_manager._user_settings = UserSecuritySettings()
        security_manager._workspace_security = {}
        security_manager._merged = None
        au = security_manager.get_policy().autonomy
        assert au.allow_scheduled_tasks is True
        assert au.allow_cron is False
        assert au.max_subtask_depth == 5

    def test_workspace_overrides(self):
        from dawei.workspace.user_security_settings import UserSecuritySettings

        security_manager._user_settings = UserSecuritySettings(allow_scheduled_tasks=False)
        security_manager._workspace_security = {
            "allowScheduledTasks": True,
            "maxSubtaskDepth": 10,
        }
        security_manager._merged = None
        au = security_manager.get_policy().autonomy
        assert au.allow_scheduled_tasks is True
        assert au.max_subtask_depth == 10

    def test_override_schema_range_check(self):
        o = WorkspaceSecurityOverride.model_validate(
            {"allowCron": True, "maxSubtaskDepth": 8}
        )
        d = o.model_dump(exclude_none=True, by_alias=True)
        assert d["allowCron"] is True
        assert d["maxSubtaskDepth"] == 8
        with pytest.raises(ValidationError):
            WorkspaceSecurityOverride.model_validate({"maxSubtaskDepth": 999})


class TestRateLimitPolicy:
    """P3 域11 — tool rate limiting (override-or-inherit, 0 = unlimited)."""

    def test_default_unlimited(self):
        from dawei.core.tool_rate_limiter import ToolRateLimiter
        from dawei.workspace.user_security_settings import UserSecuritySettings

        security_manager._user_settings = UserSecuritySettings()
        security_manager._workspace_security = {}
        security_manager._merged = None
        assert security_manager.get_policy().rate_limit.tool_calls_per_minute == 0
        rl = ToolRateLimiter()
        assert all(rl.check_and_consume("tool") for _ in range(50))

    def test_enforces_cap(self):
        from dawei.core.tool_rate_limiter import ToolRateLimiter
        from dawei.workspace.user_security_settings import UserSecuritySettings

        security_manager._user_settings = UserSecuritySettings(
            tool_calls_per_minute=3
        )
        security_manager._merged = None
        rl = ToolRateLimiter()
        assert all(rl.check_and_consume("tool") for _ in range(3))
        assert rl.check_and_consume("tool") is False  # 4th blocked

    def test_override_schema(self):
        o = WorkspaceSecurityOverride.model_validate({"toolCallsPerMinute": 100})
        assert o.model_dump(exclude_none=True, by_alias=True)["toolCallsPerMinute"] == 100
        with pytest.raises(ValidationError):
            WorkspaceSecurityOverride.model_validate({"toolCallsPerMinute": -1})


class TestFilesystemPolicy:
    """P3 域4 — filesystem blocked_paths (override-or-inherit, central gate)."""

    def test_inherits_user_blocked(self):
        from dawei.workspace.user_security_settings import UserSecuritySettings

        security_manager._user_settings = UserSecuritySettings(
            base_blocked_paths=["/secret", "/etc/ssh"]
        )
        security_manager._workspace_security = {}
        security_manager._merged = None
        bp = security_manager.get_policy().filesystem.blocked_paths
        assert "/secret" in bp and "/etc/ssh" in bp

    def test_workspace_replaces_blocked(self):
        from dawei.workspace.user_security_settings import UserSecuritySettings

        security_manager._user_settings = UserSecuritySettings(
            base_blocked_paths=["/secret"]
        )
        security_manager._workspace_security = {"customBlockedPaths": ["/override"]}
        security_manager._merged = None
        assert security_manager.get_policy().filesystem.blocked_paths == ["/override"]

    def test_is_path_allowed_blocks(self, tmp_path):
        import os

        from dawei.workspace.user_security_settings import UserSecuritySettings
        from dawei.workspace.user_workspace import UserWorkspace

        secret = str(tmp_path / "secret")
        security_manager._user_settings = UserSecuritySettings(base_blocked_paths=[secret])
        security_manager._workspace_security = {}
        security_manager._merged = None
        ws = UserWorkspace(str(tmp_path))
        # blocked prefix → denied
        assert ws.is_path_allowed(os.path.join(secret, "key.txt")) is False
        # non-blocked workspace file → allowed
        assert ws.is_path_allowed(str(tmp_path / "normal.txt")) is True

    def test_override_schema(self):
        o = WorkspaceSecurityOverride.model_validate({"customBlockedPaths": ["/x", "/y"]})
        assert o.model_dump(exclude_none=True, by_alias=True)["customBlockedPaths"] == ["/x", "/y"]
