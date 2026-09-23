# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""mode 统一管理重构测试（project/docs/mode统一管理.md §6 Phase 0-2 / §7 验收）

- Phase 0：现状基线（builtin 框架模式、冲突确定性、af3e7ce 静态准入回归）
- Phase 1：ModeConfig v2（kind/priority/can_delegate + FAST FAIL）与 ModeRegistry
- Phase 2（mode-工具解耦后）：准入派生已退役（方案 D3-D5），仅存 INV-0/INV-5 不量子集
- P2（mode-工具解耦方案 D2）：aliases 已退役 —— 无归一路径，残留 yaml 仅告警
"""

import pytest

pytestmark = pytest.mark.unit

from pathlib import Path

import yaml

from dawei.entity.mode import (
    FRAMEWORK_SLUGS,
    KIND_BUSINESS,
    KIND_FRAMEWORK,
    ModeConfig,
    strip_emoji_prefix,
)
from dawei.mode.registry import (
    ModeNotFoundError,
    ModeRegistry,
    ModeSelectionContext,
    get_registry,
    invalidate_registry,
)
from dawei.tools.tool_manager import (
    check_mode_invariants,
)

# --------------------------------------------------------------------------- helpers


def write_workspace_modes(ws_path: Path, modes: list[dict], agent_dir: str = "test-agent") -> Path:
    """模拟 market 安装产物：{ws}/.dawei/agents/{agent}/modes.yaml"""
    agents_dir = ws_path / ".dawei" / "agents" / agent_dir
    agents_dir.mkdir(parents=True, exist_ok=True)
    modes_file = agents_dir / "modes.yaml"
    modes_file.write_text(yaml.safe_dump({"customModes": modes}, allow_unicode=True), encoding="utf-8")
    return modes_file


class StubRegistry:
    """最小 registry 桩（duck-typing derive/断言所需接口）"""

    def __init__(self, modes: list[ModeConfig]):
        self._modes = modes

    def all(self, kind: str | None = None) -> list[ModeConfig]:
        return [m for m in self._modes if kind is None or m.kind == kind]

    def get(self, slug: str) -> ModeConfig:
        for m in self._modes:
            if m.slug == slug:
                return m
        raise KeyError(slug)


@pytest.fixture(autouse=True)
def _clean_registry_singleton():
    """测试间清理 per-workspace 单例，避免串扰"""
    invalidate_registry()
    yield
    invalidate_registry()


# --------------------------------------------------------------------------- Phase 0：基线（As-Is 守护）


class TestPhase0Baseline:
    def test_builtin_framework_modes_present(self):
        """builtin 必须提供 orchestrator/pdca 两个 framework 模式（§4.1）"""
        registry = get_registry(None)
        assert registry.framework_slugs == {"orchestrator", "pdca"}
        for slug in FRAMEWORK_SLUGS:
            mode = registry.get(slug)
            assert mode.kind == KIND_FRAMEWORK

    def test_builtin_pdca_priority_lower_than_orchestrator(self):
        """§4.5：pdca 是最低优先级兜底（priority 语义开始被消费）"""
        registry = get_registry(None)
        assert registry.get("pdca").priority < registry.get("orchestrator").priority

    def test_generic_slug_conflict_structurally_resolved(self, tmp_path):
        """P4 基线（§8 兜底目录移除后）：builtin 只剩 framework×2，业务编队
        经 market 安装进入 workspace 层。mode-工具解耦 D2 后别名归一已删除：
        泛型旧 slug（如 export）不再是任何 mode 的有效引用 → ModeNotFoundError"""
        r0 = get_registry(None)
        assert r0.all(kind=KIND_BUSINESS) == []  # builtin 无业务模式（SSOT = market）
        assert not r0.is_valid("export")  # 别名退役：未安装即无效
        write_workspace_modes(
            tmp_path,
            [{"slug": "ind-export-finisher", "name": "Export Finisher", "aliases": ["export"]}],
        )
        r1 = get_registry(str(tmp_path))
        r2 = ModeRegistry(str(tmp_path))
        # yaml 残留 aliases 被忽略（D2）：两个 registry 实例均只认 canonical slug
        assert r1.is_valid("ind-export-finisher") and r2.is_valid("ind-export-finisher")
        with pytest.raises(ModeNotFoundError):
            r1.get("export")
        with pytest.raises(ModeNotFoundError):
            r2.get("export")

    def test_mode_tool_decoupling_static_tables_retired(self):
        """mode-工具解耦（方案 D3/D5）：静态准入白名单与派生入口必须整体退役"""
        import dawei.tools.tool_manager as tm

        for retired in ("RESTRICTED_GROUPS", "RESTRICTED_GROUP_NAMES", "derive_restricted_groups", "get_restricted_groups"):
            assert not hasattr(tm, retired), f"{retired} 应已删除（mode-工具解耦）"


# --------------------------------------------------------------------------- Phase 1：ModeConfig v2


class TestModeConfigV2:
    def test_parses_v2_fields(self):
        mode = ModeConfig.from_dict(
            {
                "slug": "firm-case-manager",
                "name": "Case Manager",
                "kind": "business",
                "priority": 60,
                "canDelegate": False,
            }
        )
        assert mode.kind == KIND_BUSINESS
        assert mode.priority == 60
        assert mode.can_delegate is False
        assert mode.is_framework is False
        assert "groups" not in mode.to_dict()  # D3：groups 字段退役
        assert "aliases" not in mode.to_dict()  # D2：aliases 字段退役

    def test_residual_yaml_groups_ignored_with_warning(self, caplog):
        """D2：aliases 残留 yaml 仅告警；groups 为 Roo Code 兼容字段，静默忽略（不告警）"""
        import logging

        with caplog.at_level(logging.WARNING):
            mode = ModeConfig.from_dict({"slug": "firm-x", "name": "X", "groups": ["read"], "aliases": ["legacy-x"]})
        assert "groups" not in mode.to_dict()
        assert "aliases" not in mode.to_dict()
        assert sum("deprecated" in r.message for r in caplog.records) == 1

    def test_legacy_yaml_defaults(self):
        """存量 yaml（无 kind/priority）兼容：按 slug 推断 + 保留段默认值（Phase 1 兼容策略）"""
        orch = ModeConfig.from_dict({"slug": "orchestrator", "name": "Orchestrator"})
        assert orch.kind == KIND_FRAMEWORK
        assert orch.priority >= 80
        assert orch.can_delegate is True

        biz = ModeConfig.from_dict({"slug": "soc-trend-spotter", "name": "Trend Spotter"})
        assert biz.kind == KIND_BUSINESS
        assert biz.priority == 50

    def test_can_delegate_parsed_from_yaml(self):
        assert ModeConfig.from_dict({"slug": "pdca", "name": "PDCA", "canDelegate": False}).can_delegate is False

    def test_missing_slug_fails(self):
        with pytest.raises(ValueError, match="missing 'slug'"):
            ModeConfig.from_dict({"name": "No Slug"})

    @pytest.mark.parametrize("bad_slug", ["Bad_Slug", "9abc", "-lead", "a" * 49, "UPPER"])
    def test_invalid_slug_format_fails(self, bad_slug):
        with pytest.raises(ValueError, match="invalid slug"):
            ModeConfig.from_dict({"slug": bad_slug, "name": "X"})

    def test_framework_kind_whitelist_fails(self):
        with pytest.raises(ValueError, match="FRAMEWORK_SLUGS"):
            ModeConfig.from_dict({"slug": "custom-fw", "name": "X", "kind": "framework"})

    def test_invalid_kind_fails(self):
        with pytest.raises(ValueError, match="invalid kind"):
            ModeConfig.from_dict({"slug": "x-mode", "name": "X", "kind": "platform"})

    # ---- 命名规范（§4.8，Phase 1 告警级）

    def test_naming_ok(self):
        mode = ModeConfig.from_dict({"slug": "firm-case-manager", "name": "🪃 Case Manager", "kind": "business", "priority": 60})
        assert mode.validation_issues(known_team_codes={"firm"}) == []

    def test_naming_bad_prefix_flagged(self):
        mode = ModeConfig.from_dict({"slug": "case-manager", "name": "Case Manager"})
        assert any("team_code" in i for i in mode.validation_issues(known_team_codes={"firm", "mkt"}))

    def test_naming_cjk_name_flagged(self):
        mode = ModeConfig.from_dict({"slug": "firm-case-manager", "name": "案件管理员"})
        assert any("CJK" in i for i in mode.validation_issues(known_team_codes={"firm"}))

    def test_naming_long_name_flagged(self):
        mode = ModeConfig.from_dict({"slug": "firm-case-manager", "name": "Extremely Long Long Long Long Name Here"})
        assert any("Title Case" in i for i in mode.validation_issues(known_team_codes={"firm"}))
        assert any("words" in i for i in mode.validation_issues(known_team_codes={"firm"}))

    def test_naming_business_priority_band_flagged(self):
        mode = ModeConfig.from_dict({"slug": "firm-case-manager", "name": "Case Manager", "priority": 90})
        assert any("priority" in i for i in mode.validation_issues(known_team_codes={"firm"}))

    def test_strip_emoji_prefix(self):
        assert strip_emoji_prefix("🪃 Mission Coordinator") == "Mission Coordinator"
        assert strip_emoji_prefix("Plain Name") == "Plain Name"


# --------------------------------------------------------------------------- Phase 1：ModeRegistry


class TestModeRegistry:
    def test_unknown_slug_raises_not_found(self):
        """P8 修复：未知 slug 不再静默合成默认 ModeConfig"""
        registry = get_registry(None)
        with pytest.raises(ModeNotFoundError):
            registry.get("ghost-mode")

    def test_framework_override_protection(self, tmp_path):
        """§4.3：workspace 层不可覆盖 framework slug（builtin 胜出）"""
        write_workspace_modes(
            tmp_path,
            [{"slug": "pdca", "name": "Hijacked", "description": "should not win"}],
        )
        registry = get_registry(str(tmp_path))
        pdca = registry.get("pdca")
        assert pdca.name != "Hijacked"
        assert pdca.kind == KIND_FRAMEWORK  # builtin 框架身份仍在

    def test_workspace_override_business_allowed(self, tmp_path):
        """§4.3：workspace 覆盖 business slug 允许（显式 override）"""
        write_workspace_modes(
            tmp_path,
            [{"slug": "soc-trend-spotter", "name": "Overridden Spotter"}],
        )
        registry = get_registry(str(tmp_path))
        assert registry.get("soc-trend-spotter").name == "Overridden Spotter"

    def test_alias_resolution_retired(self, tmp_path):
        """mode-工具解耦 D2：aliases 归一路径整体删除。

        yaml 残留 aliases 被忽略，旧 slug 一律 ModeNotFoundError（附 available）；
        存量数据经 scripts/migrate_mode_decoupling.py 直接改写。
        """
        write_workspace_modes(
            tmp_path,
            [{"slug": "acme-widget-maker", "name": "Widget Maker", "aliases": ["widget-maker"]}],
        )
        registry = get_registry(str(tmp_path))
        assert not hasattr(registry, "canonical")  # 归一 API 已删除
        with pytest.raises(ModeNotFoundError):
            registry.get("widget-maker")
        assert not registry.is_valid("widget-maker")
        assert registry.get("acme-widget-maker").slug == "acme-widget-maker"

    def test_alias_collision_no_longer_fatal(self, tmp_path):
        """D2：alias 冲突 FAST FAIL 索引已随 _index_aliases 删除 —— 残留别名
        互撞不再阻断 registry 初始化（字段本身被忽略）。"""
        write_workspace_modes(
            tmp_path,
            [
                {"slug": "acme-a", "name": "A", "aliases": ["legacy-name"]},
                {"slug": "acme-b", "name": "B", "aliases": ["legacy-name", "pdca"]},
            ],
        )
        registry = get_registry(str(tmp_path))  # 不抛
        assert registry.is_valid("acme-a") and registry.is_valid("acme-b")

    def test_resolve_chain(self, tmp_path):
        """§4.5 兜底链：explicit > task > mention > orchestrator > pdca"""
        write_workspace_modes(
            tmp_path,
            [
                {"slug": "acme-explicit", "name": "E", "priority": 10},
                {"slug": "acme-task", "name": "T", "priority": 11},
                {"slug": "acme-mention", "name": "M", "priority": 12},
            ],
        )
        registry = get_registry(str(tmp_path))

        assert registry.resolve(ModeSelectionContext(explicit_slug="acme-explicit")) == "acme-explicit"
        assert registry.resolve(ModeSelectionContext(task_mode="acme-task")) == "acme-task"
        assert registry.resolve(ModeSelectionContext(mention_slug="acme-mention")) == "acme-mention"
        # 优先级：explicit 覆盖 task/mention
        assert registry.resolve(ModeSelectionContext(explicit_slug="acme-explicit", task_mode="acme-task", mention_slug="acme-mention")) == "acme-explicit"
        # 全空 → 默认入口 orchestrator（非 pdca）
        assert registry.resolve(ModeSelectionContext()) == "orchestrator"
        # 链上未知 slug → 告警后落到下一级（会话不中断）
        assert registry.resolve(ModeSelectionContext(explicit_slug="ghost", task_mode="acme-task")) == "acme-task"

    def test_singleton_and_invalidate(self, tmp_path):
        """P6 修复：per-workspace 单例；invalidate 后重建（无 300s 陈旧窗口）"""
        r1 = get_registry(str(tmp_path))
        r2 = get_registry(str(tmp_path))
        assert r1 is r2

        write_workspace_modes(tmp_path, [{"slug": "acme-late-install", "name": "Late"}])
        assert not r1.is_valid("acme-late-install")  # 旧实例不可变
        invalidate_registry(str(tmp_path))
        r3 = get_registry(str(tmp_path))
        assert r3 is not r1
        assert r3.is_valid("acme-late-install")

    def test_builtin_registry_engine_invariants_pass(self):
        """真 builtin：engine 级不变量（INV-0/1/2）必须通过"""
        registry = get_registry(None)
        assert check_mode_invariants(registry)["engine"] == []

    def test_all_sorted_by_priority(self):
        registry = get_registry(None)
        priorities = [m.priority for m in registry.all()]
        assert priorities == sorted(priorities, reverse=True)

    def test_naming_violations_surfaced_not_fatal(self):
        """Phase 1：命名违规（如 pdca priority=80 ≠ 0）仅告警，不拒启动"""
        registry = get_registry(None)
        assert isinstance(registry.naming_violations, list)  # builtin 现状即有违规（pdca=80）


# --------------------------------------------------------------------------- Phase 2（解耦后）：不变量子集


class TestModeInvariantsPostDecoupling:
    """mode-工具解耦后 check_mode_invariants 仅存 INV-0（pdca 兜底）/ INV-5（命名告警）"""

    def test_inv0_detects_missing_pdca(self):
        stub = StubRegistry([ModeConfig.from_dict({"slug": "orchestrator", "name": "O", "priority": 95})])
        assert any("INV-0" in v for v in check_mode_invariants(stub)["engine"])

    def test_group_gap_assertion_retired(self):
        """INV-1/INV-4（工具组覆盖/未知组）随 groups 退役——不再构成 engine 违规"""
        stub = StubRegistry(
            [
                ModeConfig.from_dict({"slug": "pdca", "name": "PDCA", "priority": 0}),
                ModeConfig.from_dict({"slug": "firm-x", "name": "X", "priority": 60}),
            ]
        )
        assert check_mode_invariants(stub)["engine"] == []

    def test_builtin_invariants_engine_clean(self):
        registry = get_registry(None)
        from dawei.tools.tool_manager import assert_mode_invariants

        assert assert_mode_invariants(registry) == []

    def test_executor_mode_admission_retired(self):
        """源码级守护（D5）：tool_executor 不再引用任何 mode 组准入符号"""
        import inspect

        from dawei.tools import tool_executor

        src = inspect.getsource(tool_executor)
        assert "get_restricted_groups" not in src
        assert "RESTRICTED_GROUPS" not in src
        assert "_get_allowed_groups_for_mode" not in src


class TestFrameworkModeSlugsDerived:
    def test_core_constant_derived_value_unchanged(self):
        """P11：FRAMEWORK_MODE_SLUGS 改为派生，值保持不变（plan/do/check/act 为
        pdca_extension 运行时相位幽灵 slug，Phase 4 收口）"""
        from dawei.api.workspaces.core import FRAMEWORK_MODE_SLUGS

        assert {"orchestrator", "pdca", "plan", "do", "check", "act"} == FRAMEWORK_MODE_SLUGS


# --------------------------------------------------------------------------- §7 验收 #5：new_task can_delegate 拒绝


class TestNewTaskCanDelegateGuard:
    """验收 #5：can_delegate=false 的模式作为 new_task 目标 → 拒绝（对 LLM 可见）"""

    def _tool(self):
        from dawei.tools.custom_tools import workflow_tools_fixed as wtf

        return wtf.NewTaskTool(task_graph=None, workspace_root=None)

    async def test_non_delegable_mode_rejected(self):
        import json

        # C2 起 deliverable 必填——补齐后才能抵达 can_delegate 闸门（验收 #5 语义不变）
        out = json.loads(await self._tool()._run(mode="orchestrator", message="x", acceptance="验收标准示例", deliverable="交付/测试.md"))
        assert out["status"] == "error"
        assert "can_delegate" in out["message"]
        # 可派目标仍列出供 LLM 修正路由
        assert "orchestrator" not in out["available_modes"]
        assert "pdca" in out["available_modes"]

    async def test_delegable_mode_passes_guard(self):
        import json

        # pdca 可派：越过 can_delegate 防护；无 task_graph 走既有 FAST FAIL 分支
        # （deliverable 必填为 C2 新契约，补齐以真正抵达该分支）
        out = json.loads(await self._tool()._run(mode="pdca", message="x", acceptance="验收标准示例", deliverable="交付/测试.md"))
        blob = json.dumps(out, ensure_ascii=False)
        assert "can_delegate" not in blob
