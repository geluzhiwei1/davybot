"""
Unit tests for workspace type system — enum completeness, category derivation, and model integrity.

Tests cover:
  - WorkspaceType: 16 values, category/is_temporary/is_ip properties
  - WorkspaceCategory: 6 values, correct mapping from type
  - WorkspaceLifecycle: 3 values, no duplicate in models/ip.py
  - IP_MODULE_TYPES: auto-generated from enum, correct count
  - WorkspaceInfo.workspace_category: computed property (not persisted)
  - WorkspaceMetadata: from_ip_meta / from_compliance_meta factory methods
"""

import pytest

from dawei.workspace.models import (
    IP_MODULE_TYPES,
    WorkspaceCategory,
    WorkspaceInfo,
    WorkspaceLifecycle,
    WorkspaceMetadata,
    WorkspaceType,
)

pytestmark = pytest.mark.unit


# ============================================================================
# WorkspaceType — 枚举完整性
# ============================================================================


class TestWorkspaceTypeCompleteness:
    """验证 WorkspaceType 枚举包含所有 16 种类型。"""

    EXPECTED_COUNT = 16

    def test_total_count(self):
        """WorkspaceType 应有 16 个值。"""
        values = list(WorkspaceType)
        assert len(values) == self.EXPECTED_COUNT, (
            f"Expected {self.EXPECTED_COUNT} types, got {len(values)}"
        )

    def test_all_values_are_str(self):
        """所有 WorkspaceType 值都应是字符串。"""
        for t in WorkspaceType:
            assert isinstance(t.value, str), f"{t.name} value is not str"

    def test_no_empty_values(self):
        """没有 WorkspaceType 值应为空。"""
        for t in WorkspaceType:
            assert t.value, f"{t.name} has empty value"

    def test_type_values_unique(self):
        """所有 WorkspaceType 值应唯一。"""
        seen = set()
        for t in WorkspaceType:
            assert t.value not in seen, f"Duplicate value: {t.value}"
            seen.add(t.value)


# ============================================================================
# WorkspaceCategory — 6 大类 & 映射正确性
# ============================================================================


class TestWorkspaceCategoryMapping:
    """验证每个 WorkspaceType 映射到正确的 WorkspaceCategory。"""

    # ── 通用工作区 ──
    def test_user_is_general(self):
        assert WorkspaceType.USER.category == WorkspaceCategory.GENERAL

    # ── AI 任务 ──
    def test_simple_task_is_ai_task(self):
        assert WorkspaceType.SIMPLE_TASK.category == WorkspaceCategory.AI_TASK

    def test_scheduled_task_is_ai_task(self):
        assert WorkspaceType.SCHEDULED_TASK.category == WorkspaceCategory.AI_TASK

    def test_deep_research_is_ai_task(self):
        """Task-as-Workspace：深度调研任务归类 AI 任务（独立持久工作区）。"""
        assert WorkspaceType.DEEP_RESEARCH.category == WorkspaceCategory.AI_TASK
        assert WorkspaceType.DEEP_RESEARCH.is_temporary is False

    # ── IP 模块 (全部 9 个) ──
    def test_all_ip_types_are_ip_category(self):
        ip_types = [t for t in WorkspaceType if t.is_ip]
        assert len(ip_types) == 9, f"Expected 9 IP types, got {len(ip_types)}"
        for t in ip_types:
            assert t.category == WorkspaceCategory.IP, (
                f"{t.value} should be IP category, got {t.category}"
            )

    def test_specific_ip_mappings(self):
        """逐个 IP 子类型验证 category 映射。"""
        mapping = {
            WorkspaceType.IP_IDEA_VAULT: WorkspaceCategory.IP,
            WorkspaceType.IP_DISCLOSURE: WorkspaceCategory.IP,
            WorkspaceType.IP_DRAFT: WorkspaceCategory.IP,
            WorkspaceType.IP_APPLICATION: WorkspaceCategory.IP,
            WorkspaceType.IP_FILING: WorkspaceCategory.IP,
            WorkspaceType.IP_OA_REPLY: WorkspaceCategory.IP,
            WorkspaceType.IP_REVERSE_DETECTION: WorkspaceCategory.IP,
            WorkspaceType.IP_PORTFOLIO: WorkspaceCategory.IP,
            WorkspaceType.IP_TRADEMARK: WorkspaceCategory.IP,
        }
        assert len(mapping) == 9
        for wtype, expected_cat in mapping.items():
            assert wtype.category == expected_cat, (
                f"{wtype.value} -> expected {expected_cat}, got {wtype.category}"
            )

    # ── 合规管理 ──
    def test_compliance_is_compliance(self):
        assert WorkspaceType.COMPLIANCE_PROJECT.category == WorkspaceCategory.COMPLIANCE

    # ── 团队/系统 ──
    def test_team_is_law_firm(self):
        assert WorkspaceType.TEAM.category == WorkspaceCategory.LAW_FIRM

    def test_system_is_system(self):
        assert WorkspaceType.SYSTEM.category == WorkspaceCategory.SYSTEM


# ============================================================================
# WorkspaceType — is_ip / is_temporary 属性
# ============================================================================


class TestWorkspaceTypeProperties:
    """验证 is_ip 和 is_temporary 属性。"""

    def test_ip_types_return_true_for_is_ip(self):
        ip_types = [t for t in WorkspaceType if t.value.startswith("ip-")]
        for t in ip_types:
            assert t.is_ip is True, f"{t.value} should be ip"

    def test_non_ip_types_return_false_for_is_ip(self):
        non_ip = [t for t in WorkspaceType if not t.value.startswith("ip-")]
        for t in non_ip:
            assert t.is_ip is False, f"{t.value} should NOT be ip"

    def test_ip_types_are_temporary(self):
        ip_types = [t for t in WorkspaceType if t.value.startswith("ip-")]
        for t in ip_types:
            assert t.is_temporary is True, f"{t.value} should be temporary"

    def test_task_types_are_temporary(self):
        assert WorkspaceType.SIMPLE_TASK.is_temporary is True
        assert WorkspaceType.SCHEDULED_TASK.is_temporary is True

    def test_persistent_types_are_not_temporary(self):
        assert WorkspaceType.USER.is_temporary is False
        assert WorkspaceType.COMPLIANCE_PROJECT.is_temporary is False
        assert WorkspaceType.TEAM.is_temporary is False
        assert WorkspaceType.SYSTEM.is_temporary is False


# ============================================================================
# IP_MODULE_TYPES — 从枚举自动生成
# ============================================================================


class TestIPModuleTypes:
    """验证 IP_MODULE_TYPES 从 WorkspaceType 自动生成。"""

    def test_count_matches_enum(self):
        ip_from_enum = [t for t in WorkspaceType if t.value.startswith("ip-")]
        assert len(IP_MODULE_TYPES) == len(ip_from_enum), (
            f"IP_MODULE_TYPES count {len(IP_MODULE_TYPES)} != enum count {len(ip_from_enum)}"
        )

    def test_all_start_with_ip_prefix(self):
        for slug in IP_MODULE_TYPES:
            assert slug.startswith("ip-"), f"'{slug}' does not start with 'ip-'"

    def test_all_have_corresponding_enum_value(self):
        """IP_MODULE_TYPES 中的每个值都应对应 WorkspaceType 中的枚举值。"""
        enum_values = {t.value for t in WorkspaceType}
        for slug in IP_MODULE_TYPES:
            assert slug in enum_values, f"'{slug}' not found in WorkspaceType values"

    def test_no_duplicate_slugs(self):
        assert len(IP_MODULE_TYPES) == len(set(IP_MODULE_TYPES)), (
            "IP_MODULE_TYPES contains duplicates"
        )


# ============================================================================
# WorkspaceLifecycle — 无重复定义
# ============================================================================


class TestWorkspaceLifecycle:
    """验证 WorkspaceLifecycle 枚举及其唯一性。"""

    def test_three_values(self):
        values = [lc.value for lc in WorkspaceLifecycle]
        assert set(values) == {"persistent", "temporary", "archived"}

    def test_not_defined_in_models_ip(self):
        """WorkspaceLifecycle 不应在 dawei.models.ip 中有重复定义。"""
        from dawei.models import ip as ip_models

        assert not hasattr(ip_models, "WorkspaceLifecycle"), (
            "WorkspaceLifecycle should NOT be defined in dawei.models.ip — "
            "canonical definition is in dawei.workspace.models"
        )

    def test_all_production_imports_from_canonical(self):
        """验证关键生产代码从 canonical 路径导入。

        ip_workspace_service（原第三条腿）已随 6b 拆库迁至 davybot-biz
        （dawei_biz.services.ip_workspace_service，仍从 canonical 导入）；
        核心测试不得依赖 biz —— 该断言腿移除，核心侧覆盖 crud/twm 两处。
        """
        from dawei.api.workspaces.crud import (
            WorkspaceLifecycle as crud_lc,
        )
        from dawei.workspace.temp_workspace_manager import (
            WorkspaceLifecycle as tm_lc,
        )

        assert crud_lc is WorkspaceLifecycle
        assert tm_lc is WorkspaceLifecycle


# ============================================================================
# WorkspaceCategory — 枚举完整性
# ============================================================================


class TestWorkspaceCategoryCompleteness:
    """验证 WorkspaceCategory 枚举。"""

    EXPECTED = {
        "general",
        "ai_task",
        "ip",
        "compliance",
        "law_firm",
        "system",
    }

    def test_six_values(self):
        values = {c.value for c in WorkspaceCategory}
        assert values == self.EXPECTED, f"Expected {self.EXPECTED}, got {values}"

    def test_every_type_maps_to_valid_category(self):
        """每个 WorkspaceType 必须映射到有效的 WorkspaceCategory。"""
        valid = set(WorkspaceCategory)
        for t in WorkspaceType:
            assert t.category in valid, (
                f"{t.value} maps to unknown category {t.category}"
            )


# ============================================================================
# WorkspaceMetadata — Pydantic 模型
# ============================================================================


class TestWorkspaceMetadata:
    """验证 WorkspaceMetadata pydantic 模型。"""

    def test_default_constructor(self):
        m = WorkspaceMetadata()
        assert m.phase is None
        assert m.score is None
        assert m.task_type is None
        assert m.parent_workspace_id is None
        assert m.inherited_files is None
        assert m.alerts is None
        assert m.compliance_template is None
        assert m.compliance_form_data is None
        assert m.extra == {}

    def test_ip_fields(self):
        m = WorkspaceMetadata(
            phase="plan",
            score=0.95,
            task_type="evaluate",
            parent_workspace_id="ws-001",
            inherited_files=["draft.md"],
        )
        assert m.phase == "plan"
        assert m.score == 0.95
        assert m.task_type == "evaluate"
        assert m.parent_workspace_id == "ws-001"
        assert m.inherited_files == ["draft.md"]

    def test_alerts_field(self):
        m = WorkspaceMetadata(
            alerts=[{"level": "warning", "message": "deadline approaching"}]
        )
        assert len(m.alerts) == 1
        assert m.alerts[0]["level"] == "warning"

    def test_from_ip_meta_full(self):
        m = WorkspaceMetadata.from_ip_meta({
            "phase": "do",
            "score": 0.8,
            "task_type": "generate_draft",
            "parent_workspace_id": "ws-parent",
            "inherited_files": ["a.txt", "b.txt"],
            "alerts": [{"level": "info"}],
            "extra": {"custom_key": "custom_val"},
        })
        assert m.phase == "do"
        assert m.score == 0.8
        assert m.task_type == "generate_draft"
        assert m.parent_workspace_id == "ws-parent"
        assert m.inherited_files == ["a.txt", "b.txt"]
        assert m.alerts == [{"level": "info"}]
        assert m.extra == {"custom_key": "custom_val"}

    def test_from_ip_meta_empty(self):
        m = WorkspaceMetadata.from_ip_meta(None)
        assert m.phase is None
        assert m.extra == {}

    def test_from_ip_meta_partial(self):
        m = WorkspaceMetadata.from_ip_meta({"phase": "act"})
        assert m.phase == "act"
        assert m.score is None
        assert m.task_type is None

    def test_from_compliance_meta_full(self):
        m = WorkspaceMetadata.from_compliance_meta({
            "compliance_template": "sanctions_check",
            "compliance_form_data": {"country": "US", "entity_count": 5},
            "extra": {"risk_level": "high"},
        })
        assert m.compliance_template == "sanctions_check"
        assert m.compliance_form_data == {"country": "US", "entity_count": 5}
        assert m.extra == {"risk_level": "high"}

    def test_from_compliance_meta_empty(self):
        m = WorkspaceMetadata.from_compliance_meta(None)
        assert m.compliance_template is None
        assert m.compliance_form_data is None
        assert m.extra == {}

    def test_extra_dict_default(self):
        """extra 默认应为空 dict，不是 None。"""
        m = WorkspaceMetadata()
        assert isinstance(m.extra, dict)
        assert m.extra == {}
