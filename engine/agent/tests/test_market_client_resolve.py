# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""MarketClient.resolve 团队级引用回归测试。

背景（2026-09-14 事故）: market 的 agent 资源按 mode 粒度索引
（id = agent/{org}/{team}/{mode}, slug 字段为空）。团队级引用
（如 team.json 里的 "agent/review-team"）必然命中该团队全部 mode id ——
收紧版 resolve 曾把这当作"歧义"抛 ValueError, 导致 install_agents 整类
失败、工作区半成品（team.json 已写但 .dawei/agents/ 空, Capabilities
tab 只剩 system modes）。修复后: 命中共享同一父目录 = 同一团队源目录
（任一 mode 的 /archive 都返回整个团队目录）→ 归并返回; 跨来源命中
仍 FAST FAIL。

运行: uv run python -m pytest tests/test_market_client_resolve.py -v
"""

import pytest

from dawei.market.client import MarketClient

pytestmark = pytest.mark.unit


def _client_with_items(monkeypatch, items):
    # E1 后无云端缺省: 单测显式注入基址(httpx 未实际外呼,_list_all 已被 mock)
    cli = MarketClient(base_url="http://market.test", token="test-token")
    snapshot = list(items)

    def fake_list_all(resource_type, max_items=500):
        return list(snapshot)

    monkeypatch.setattr(cli, "_list_all", fake_list_all)
    return cli


# 镜像 prod 实测形态: 69 条 agent 条目 slug 全为 None, id 按粒度索引
GELU_AGENTS = [
    {"id": f"agent/gelu-research/review-team/{m}", "name": m, "slug": None}
    for m in ("academic-searcher", "export-publish", "knowledge-synthesis", "review-writing")
] + [
    {"id": f"agent/gelu-research/paper-team/{m}", "name": m, "slug": None}
    for m in ("paper-draft", "peer-review", "citation-verify")
] + [
    {"id": "agent/social-tools/social-tools/social-publisher", "name": "social-publisher", "slug": None},
]


def test_team_level_reference_resolves(monkeypatch):
    """团队级引用命中同团队多个 mode id → 归并返回其中一个（不抛歧义）。"""
    cli = _client_with_items(monkeypatch, GELU_AGENTS)
    rid = cli.resolve("agent", "review-team")
    assert rid is not None
    assert rid.startswith("agent/gelu-research/review-team/")
    # 确定性: 重复调用返回同一结果
    assert cli.resolve("agent", "review-team") == rid


def test_team_level_reference_nested_slug(monkeypatch):
    """org 与 team 同名 (agent/social-tools/social-tools/*) 同样归并。"""
    cli = _client_with_items(monkeypatch, GELU_AGENTS)
    rid = cli.resolve("agent", "social-tools")
    assert rid is not None
    assert rid.startswith("agent/social-tools/social-tools/")


def test_cross_team_ambiguity_still_raises(monkeypatch):
    """命中跨多个不同父目录（不同团队/来源）→ 仍 ValueError（FAST FAIL 保留）。"""
    items = [
        {"id": "agent/org-a/red-team/mode-1", "name": "x", "slug": None},
        {"id": "agent/org-b/red-team/mode-1", "name": "y", "slug": None},
    ]
    cli = _client_with_items(monkeypatch, items)
    with pytest.raises(ValueError, match="ambiguous"):
        cli.resolve("agent", "red-team")


def test_skill_same_slug_two_orgs_still_raises(monkeypatch):
    """收紧的原始目标: 同名 skill 跨 org → 歧义（2 段 id 父目录=org 不同）。"""
    items = [
        {"id": "org-a/docx", "name": "docx", "slug": None},
        {"id": "org-b/docx", "name": "docx", "slug": None},
    ]
    cli = _client_with_items(monkeypatch, items)
    with pytest.raises(ValueError, match="ambiguous"):
        cli.resolve("skill", "docx")


def test_exact_slug_match_unaffected(monkeypatch):
    """第 1 层精确 slug 匹配优先, 不进宽松回退。"""
    items = [{"id": "org-a/docx", "name": "Word 处理", "slug": "docx"}]
    cli = _client_with_items(monkeypatch, items)
    assert cli.resolve("skill", "docx") == "org-a/docx"


def test_mode_level_reference_unique(monkeypatch):
    """mode 级引用唯一命中 → 直接返回该 mode id。"""
    cli = _client_with_items(monkeypatch, GELU_AGENTS)
    assert cli.resolve("agent", "paper-draft") == "agent/gelu-research/paper-team/paper-draft"


def test_no_match_returns_none(monkeypatch):
    cli = _client_with_items(monkeypatch, GELU_AGENTS)
    assert cli.resolve("agent", "does-not-exist") is None
