# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""工作区专家可见范围（mode scoping）单元测试。

覆盖 /api/workspaces/{id}/resources 的 4 层判定（_resolve_mode_scope）：
  A) .dawei/agents/ 已装 → 各 agent modes 并集
  A′) 模块身份（biz_module 或 name marker，见 _resolve_module_key）且已登记
      WORKSPACE_MODULE_AGENTS → 并集收敛为本模块映射 agents 的 modes（可用
      WORKSPACE_MODULE_MODES 二级收紧到单 mode；映射 agent 未装 → 空集，
      不回退全量泄漏其他模块；MarketingAgent/SocialAgent 伞工作区同享）
  B) 仅 team.json（半成品）→ 空集（仅框架，不回退全量）
  C) name/display_name marker → 模块已识别但团队未装 → 空集（仅框架；
     §8 兜底移除后业务模式经 market 安装进入，安装后走 A）
  D) 无模块标识 → None（全量，旧行为）

运行: uv run python -m pytest tests/test_mode_scoping.py -v
"""

import json
from datetime import UTC, datetime, timezone

import pytest
import yaml

from dawei.api.workspaces.core import (
    FRAMEWORK_MODE_SLUGS,
    WORKSPACE_MODULE_AGENTS,
    WORKSPACE_MODULE_MODES,
    _load_agent_modes_map,
    _module_agents_for,
    _module_teams_for_workspace,
    _resolve_mode_scope,
    _resolve_module_key,
)

pytestmark = pytest.mark.unit


# ── _module_teams_for_workspace：name marker 前缀匹配 ──────────────


def test_module_teams_exact_marker():
    assert _module_teams_for_workspace("MarketingAgent 工作区") == ["market-team"]


def test_module_teams_exact_marker_with_suffix():
    # startswith 匹配：name 可能带后缀
    assert _module_teams_for_workspace("MarketingAgent 工作区-2") == ["market-team"]


def test_module_teams_prefix_marker_deep_research():
    # 深度调研工作区 name = "{slug}-{id[:8]}"
    assert _module_teams_for_workspace("product-survey-48e8c4ae") == ["product-survey-team"]
    assert _module_teams_for_workspace("industry-research-ab12cd34") == ["industry-research-team"]


def test_module_teams_multi_team_module():
    # 一个模块可绑多个 team（social = social-team + social-tools）
    assert _module_teams_for_workspace("SocialAgent 工作区") == ["social-team", "social-tools"]


def test_module_teams_no_match():
    assert _module_teams_for_workspace("临时聊天") == []
    assert _module_teams_for_workspace("") == []


def test_module_teams_display_topic_not_confused():
    # 用户主题 display_name（如"product 页跳转验证"）不以 marker 开头 → 不误命中
    assert _module_teams_for_workspace("product 页跳转验证") == []


# ── _load_agent_modes_map：.dawei/agents/*/modes.yaml ──────────────


def _write_agent(ws, agent: str, slugs: list[str]):
    agent_dir = ws / ".dawei" / "agents" / agent
    agent_dir.mkdir(parents=True, exist_ok=True)
    modes = {"customModes": [{"slug": s, "name": s} for s in slugs]}
    (agent_dir / "modes.yaml").write_text(yaml.dump(modes), encoding="utf-8")


def test_load_agent_modes_map(tmp_path):
    _write_agent(tmp_path, "patent-team", ["patent-engineer", "oa-replier"])
    _write_agent(tmp_path, "paper-team", ["paper-orchestrator"])
    amap = _load_agent_modes_map(tmp_path / ".dawei")
    assert amap == {
        "patent-team": ["patent-engineer", "oa-replier"],
        "paper-team": ["paper-orchestrator"],
    }


def test_load_agent_modes_map_empty(tmp_path):
    assert _load_agent_modes_map(tmp_path / ".dawei") == {}


# ── _resolve_mode_scope：4 层判定 ──────────────────────────────────


def test_scope_tier_a_installed_agents_union(tmp_path):
    _write_agent(tmp_path, "patent-team", ["patent-engineer", "oa-replier"])
    _write_agent(tmp_path, "paper-team", ["paper-orchestrator"])
    scope = _resolve_mode_scope(tmp_path / ".dawei", "whatever")
    assert scope == {"patent-engineer", "oa-replier", "paper-orchestrator"}


def test_scope_tier_b_team_json_only_empty_scope(tmp_path):
    # 半成品（team.json 已写、agents 未装）→ 空集，绝不回退全量泄漏其他模块
    dawei = tmp_path / ".dawei"
    dawei.mkdir()
    (dawei / "team.json").write_text(json.dumps({"team_id": "ip-disclosure"}), encoding="utf-8")
    assert _resolve_mode_scope(dawei, "ip-disclosure") == set()


def test_scope_tier_c_name_marker_framework_only(tmp_path):
    # §8 兜底移除：模块已识别（name marker）但团队未 market 安装 → 仅框架（空集）
    scope = _resolve_mode_scope(tmp_path / ".dawei", "product-survey-48e8c4ae")
    assert scope == set()


def test_scope_tier_c_display_name_fallback(tmp_path):
    # name 无标记时回退 display_name 判定模块；未安装同样仅框架
    scope = _resolve_mode_scope(tmp_path / ".dawei", "", "SocialAgent 工作区")
    assert scope == set()


def test_scope_tier_a_module_workspace_with_installed_agents(tmp_path):
    # 模块工作区 market 安装团队后走 tier A：返回已装 agents 的并集
    # （social 模块 = social + social-tools 两个 agent 目录）
    _write_agent(tmp_path, "social", ["soc-content-drafter", "soc-trend-spotter"])
    _write_agent(tmp_path, "social-tools", ["soc-publisher"])
    scope = _resolve_mode_scope(tmp_path / ".dawei", "SocialAgent 工作区")
    assert scope == {"soc-content-drafter", "soc-trend-spotter", "soc-publisher"}


def test_scope_tier_d_no_identity_full_list(tmp_path):
    # 无任何模块标识（临时聊天等）→ None = 不限定（旧行为）
    assert _resolve_mode_scope(tmp_path / ".dawei", "temp-4185516e", "随便聊聊") is None


def test_scope_tier_a_beats_team_json(tmp_path):
    # agents 已装时优先于 team.json（A 优先于 B）
    _write_agent(tmp_path, "gelu-experts", ["integrity-expert"])
    dawei = tmp_path / ".dawei"
    (dawei / "team.json").write_text("{}", encoding="utf-8")
    assert _resolve_mode_scope(dawei, "") == {"integrity-expert"}


def test_framework_mode_slugs_stable():
    assert {"orchestrator", "pdca", "plan", "do", "check", "act"} == FRAMEWORK_MODE_SLUGS


# ── _load_agent_modes_map：aliases 并入已退役（mode-工具解耦 D2）──


def _write_agent_modes(ws, agent: str, modes: list[dict]):
    """写 .dawei/agents/<agent>/modes.yaml，modes 项可含残留 aliases。"""
    agent_dir = ws / ".dawei" / "agents" / agent
    agent_dir.mkdir(parents=True, exist_ok=True)
    payload = {"customModes": [{"slug": m["slug"], "name": m["slug"], "aliases": m.get("aliases", [])} for m in modes]}
    (agent_dir / "modes.yaml").write_text(yaml.dump(payload), encoding="utf-8")


def test_load_agent_modes_map_aliases_retired(tmp_path):
    """mode-工具解耦 D2：include_aliases 参数已删除 —— 即便 yaml 残留
    aliases 也只返回纯 canonical slug（前端一律用正名；历史 alias expertId
    经 scripts/migrate_mode_decoupling.py 归一）。"""
    import inspect

    assert "include_aliases" not in inspect.signature(_load_agent_modes_map).parameters
    _write_agent_modes(
        tmp_path,
        "review-team",
        [
            {"slug": "gelu-review-orchestrator", "aliases": ["review-orchestrator"]},
            {"slug": "gelu-review-planner"},
        ],
    )
    amap = _load_agent_modes_map(tmp_path / ".dawei")
    assert amap == {"review-team": ["gelu-review-orchestrator", "gelu-review-planner"]}


# ── tier A′：biz_module 模块收紧（WORKSPACE_MODULE_AGENTS/MODES）────


def _write_gelu_research_team(ws):
    """模拟 team/gelu-research 整团队安装（4 agents × 各自 modes）。"""
    _write_agent(ws, "review-team", ["gelu-review-orchestrator", "gelu-review-planner"])
    _write_agent(ws, "paper-team", ["gelu-paper-orchestrator"])
    _write_agent(ws, "lens-team", ["gelu-lens-orchestrator"])
    _write_agent(ws, "gelu-experts", ["gelu-data-analysis-expert", "gelu-writing-expert"])


def test_scope_module_review_only_review_team(tmp_path):
    # 综述写作工具页（biz_module=research-review）：只看 review-team 的 modes，
    # 不泄漏同工作区已装的其他 3 个 agent（原 tier A 并集会暴露全部 6 个）
    _write_gelu_research_team(tmp_path)
    scope = _resolve_mode_scope(tmp_path / ".dawei", "whatever", biz_module="research-review")
    assert scope == {"gelu-review-orchestrator", "gelu-review-planner"}


def test_scope_module_original_only_paper_team(tmp_path):
    # 原创论文工具页（biz_module=research-original）→ 仅 paper-team
    _write_gelu_research_team(tmp_path)
    scope = _resolve_mode_scope(tmp_path / ".dawei", "", biz_module="research-original")
    assert scope == {"gelu-paper-orchestrator"}


def test_scope_module_single_expert_mode_subset(tmp_path):
    # 单专家工具页（biz_module=research-analysis）：WORKSPACE_MODULE_MODES
    # 二级收紧 → gelu-experts 7 专家中只暴露 gelu-data-analysis-expert 一个
    _write_gelu_research_team(tmp_path)
    scope = _resolve_mode_scope(tmp_path / ".dawei", "", biz_module="research-analysis")
    assert scope == {"gelu-data-analysis-expert"}


def test_scope_module_mapped_agent_missing_framework_only(tmp_path):
    # 映射的 agent 未装（research-review 需要 review-team，但只装了
    # gelu-experts）→ 空集（仅框架），不回退全量并集泄漏其他模块
    _write_agent(tmp_path, "gelu-experts", ["gelu-writing-expert"])
    assert _resolve_mode_scope(tmp_path / ".dawei", "", biz_module="research-review") == set()


def test_scope_unregistered_biz_module_keeps_union(tmp_path):
    # 未登记的 biz_module 不收紧（走原 tier A 并集，向后兼容存量/新模块）
    _write_gelu_research_team(tmp_path)
    scope = _resolve_mode_scope(tmp_path / ".dawei", "", biz_module="some-future-module")
    assert scope == {
        "gelu-review-orchestrator",
        "gelu-review-planner",
        "gelu-paper-orchestrator",
        "gelu-lens-orchestrator",
        "gelu-data-analysis-expert",
        "gelu-writing-expert",
    }


def test_scope_module_agents_partial_install_uses_installed(tmp_path):
    # 团队只装了一部分（缺 lens-team）：模块收敛只看已装映射 agents 的并集
    _write_agent(tmp_path, "review-team", ["gelu-review-orchestrator"])
    _write_agent(tmp_path, "gelu-experts", ["gelu-writing-expert"])
    scope = _resolve_mode_scope(tmp_path / ".dawei", "", biz_module="research-review")
    assert scope == {"gelu-review-orchestrator"}


# ── 收紧映射表自身一致性（防漂移）──────────────────────────────────


def test_module_modes_keys_registered_in_module_agents():
    # WORKSPACE_MODULE_MODES 的每个 biz_module 必须已登记 WORKSPACE_MODULE_AGENTS
    # 且映射非空（否则二级收紧永远命中不了）
    for biz_module in WORKSPACE_MODULE_MODES:
        assert biz_module in WORKSPACE_MODULE_AGENTS, f"{biz_module} missing in WORKSPACE_MODULE_AGENTS"
        assert WORKSPACE_MODULE_AGENTS[biz_module], f"{biz_module} maps to empty agent list"


def test_module_agents_for_lookup():
    assert _module_agents_for("research-review") == ["review-team"]
    assert _module_agents_for("") == []
    assert _module_agents_for("unknown-module") == []


# ── name marker 模块收紧（MarketingAgent/SocialAgent 伞工作区）─────
# 伞工作区无工具页（不固话 biz_module），身份靠 name marker 识别；团队经
# market 资源页装进工作区后，同工作区误装的其他模块团队 modes 不外泄。


def test_resolve_module_key_biz_module_priority():
    # biz_module 优先于 name marker；marker 命中返回 marker 本身；无身份为空
    assert _resolve_module_key("research-review", "MarketingAgent 工作区") == "research-review"
    assert _resolve_module_key("", "SocialAgent 工作区") == "SocialAgent 工作区"
    assert _resolve_module_key("", "SocialAgent 工作区-2") == "SocialAgent 工作区"  # startswith
    assert _resolve_module_key("", "", "MarketingAgent 工作区") == "MarketingAgent 工作区"  # display 兜底
    assert _resolve_module_key("", "temp-4185516e", "随便聊聊") == ""


def test_scope_market_workspace_excludes_foreign_agents(tmp_path):
    # MarketingAgent 工作区装了 market 编队 + 外来团队（marketing-tools /
    # gelu-experts）→ 只见 mkt-*，不泄漏 mt-*/gelu-*
    _write_agent(tmp_path, "market", ["mkt-orchestrator", "mkt-radar-scout"])
    _write_agent(tmp_path, "marketing-tools", ["mt-brand-strategist"])
    _write_agent(tmp_path, "gelu-experts", ["gelu-writing-expert"])
    scope = _resolve_mode_scope(tmp_path / ".dawei", "MarketingAgent 工作区")
    assert scope == {"mkt-orchestrator", "mkt-radar-scout"}


def test_scope_social_workspace_two_agent_dirs(tmp_path):
    # SocialAgent 工作区 = social + social-tools 两编队并集；外来 agent 不外泄
    _write_agent(tmp_path, "social", ["soc-orchestrator", "soc-trending-scout"])
    _write_agent(tmp_path, "social-tools", ["soc-content-drafter", "soc-publisher"])
    _write_agent(tmp_path, "market", ["mkt-orchestrator"])
    scope = _resolve_mode_scope(tmp_path / ".dawei", "SocialAgent 工作区-2")
    assert scope == {"soc-orchestrator", "soc-trending-scout", "soc-content-drafter", "soc-publisher"}


def test_scope_marker_module_fleet_missing_framework_only(tmp_path):
    # 模块编队未装、只装了外来团队 → 空集（仅框架），不回退全量泄漏
    _write_agent(tmp_path, "gelu-experts", ["gelu-writing-expert"])
    assert _resolve_mode_scope(tmp_path / ".dawei", "MarketingAgent 工作区") == set()


def test_scope_marker_unregistered_team_unchanged(tmp_path):
    # 未登记收紧映射的 marker 模块（product-survey-）装团队后走原 tier A 并集
    _write_agent(tmp_path, "product-survey-team", ["ps-survey-orchestrator"])
    _write_agent(tmp_path, "gelu-experts", ["gelu-writing-expert"])
    scope = _resolve_mode_scope(tmp_path / ".dawei", "product-survey-48e8c4ae")
    assert scope == {"ps-survey-orchestrator", "gelu-writing-expert"}


# ── WorkspaceInfo biz_module 持久化往返 ────────────────────────────


def test_workspace_info_biz_module_roundtrip():
    from dawei.workspace.models import WorkspaceInfo

    ws = WorkspaceInfo(
        id="w1",
        name="n",
        display_name="d",
        description="",
        created_at=datetime.now(UTC),
        biz_module="research-review",
    )
    d = ws.to_dict()
    assert d["biz_module"] == "research-review"
    assert WorkspaceInfo.from_dict(d).biz_module == "research-review"
    # 存量工作区无 biz_module → None（旧数据加载不受影响）
    legacy = WorkspaceInfo.from_dict({**d, "biz_module": None})
    assert legacy.biz_module is None
