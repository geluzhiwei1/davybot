# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""resource_installer 单元测试。

覆盖：
  - install_team 分类别容错：skills 失败不得中断 agents/mcps 安装
    （半成品工作区根因回归测试）
  - _merge_agent_modes：modes.yaml customModes 合并进 mode_settings.json

运行: uv run python -m pytest tests/test_resource_installer.py -v
"""

import json

import pytest
import yaml

from dawei.workspace import resource_installer as ri

pytestmark = pytest.mark.unit


# ── install_team：分类别容错 ────────────────────────────────────────


def test_install_team_survives_skill_failure(monkeypatch, tmp_path):
    """skills 安装抛异常时，agents/mcps 仍应安装，失败记录进 results['failed']。"""
    calls: list[str] = []

    def boom_skills(*a, **kw):
        calls.append("skills")
        raise RuntimeError("market down")

    def ok_agents(*a, **kw):
        calls.append("agents")

    def ok_mcps(*a, **kw):
        calls.append("mcps")

    monkeypatch.setattr(ri, "install_skills", boom_skills)
    monkeypatch.setattr(ri, "install_agents", ok_agents)
    monkeypatch.setattr(ri, "install_mcp_servers", ok_mcps)

    results: dict = {}
    ri.install_team(
        workspace_path=tmp_path,
        team_id="ip-disclosure",
        team_meta={
            "skills": ["skill/docx"],
            "agents": ["agent/patent-team"],
            "mcps": ["mcp/paper-search"],
            "knowledges": [],
        },
        results=results,
    )

    assert calls == ["skills", "agents", "mcps"]  # agents/mcps 未被 skills 失败中断
    assert results["failed"] == ["skills"]
    # team.json 已写（install_team 自身职责）
    assert json.loads((tmp_path / ".dawei" / "team.json").read_text(encoding="utf-8"))["slug"] == "ip-disclosure"


def test_install_team_all_categories_fail(monkeypatch, tmp_path):
    """全部类别失败也不抛异常（工作区创建继续），failed 记录全部类别。"""

    def boom(*a, **kw):
        raise RuntimeError("market down")

    monkeypatch.setattr(ri, "install_skills", boom)
    monkeypatch.setattr(ri, "install_agents", boom)
    monkeypatch.setattr(ri, "install_mcp_servers", boom)

    results: dict = {}
    ri.install_team(
        workspace_path=tmp_path,
        team_id="t",
        team_meta={"skills": ["skill/x"], "agents": ["agent/y"], "mcps": ["mcp/z"], "knowledges": []},
        results=results,
    )
    assert sorted(results["failed"]) == ["agents", "mcps", "skills"]


def test_install_team_empty_meta_noop(tmp_path):
    results: dict = {}
    ri.install_team(tmp_path, "t", None, results)  # type: ignore[arg-type]
    assert results == {}


# ── install_agents：单 agent 容错 ──────────────────────────────────


class _FakeMarketClient:
    """resolve/download_zip 可编程假客户端（下载产出含 modes.yaml 的 zip）。"""

    def __init__(self, resolvable: set[str], fail_on: set[str]):
        self.resolvable = resolvable
        self.fail_on = fail_on

    def resolve(self, resource_type, slug):
        if slug in self.fail_on:
            raise ValueError(f"ambiguous market reference: {resource_type}/{slug}")
        return slug if slug in self.resolvable else None

    def download_zip(self, rid, dest_dir):
        import zipfile
        from pathlib import Path

        dest = Path(dest_dir)
        dest.mkdir(parents=True, exist_ok=True)
        zip_path = dest / f"{rid.replace('/', '_')}.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("modes.yaml", yaml.dump({"customModes": [{"slug": f"{rid}-mode", "name": rid}]}))
        return zip_path


def test_install_agents_survives_single_failure(tmp_path):
    """单个 agent 解析失败（如歧义 ValueError）不得中断其余 agent 安装。

    2026-09-14 事故回归: 收紧版 resolve 对团队级引用抛 ValueError, 旧代码
    第一个 agent 失败即整类归零 → 半成品工作区。
    """
    cli = _FakeMarketClient(resolvable={"paper-team", "lens-team"}, fail_on={"review-team"})
    results: dict = {}
    ri.install_agents(
        tmp_path,
        ["agent/review-team", "agent/paper-team", "agent/lens-team"],
        results,
        client=cli,  # type: ignore[arg-type]
    )
    installed = sorted(p.name for p in (tmp_path / ".dawei" / "agents").iterdir())
    assert installed == ["lens-team", "paper-team"]  # review-team 失败不拖累其余
    assert results["agents"] == ["paper-team", "lens-team"]
    assert results["failed"] == ["agent/review-team"]
    # 成功安装的 agent 的 modes 仍被合并进 mode_settings.json
    data = json.loads((tmp_path / ".dawei" / "mode_settings.json").read_text(encoding="utf-8"))
    assert {m["slug"] for m in data["customModes"]} == {"paper-team-mode", "lens-team-mode"}


# ── _merge_agent_modes ────────────────────────────────────────────


def _write_agent(ws, agent: str, slugs: list[str]):
    agent_dir = ws / ".dawei" / "agents" / agent
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "modes.yaml").write_text(yaml.dump({"customModes": [{"slug": s, "name": s} for s in slugs]}), encoding="utf-8")


def test_merge_agent_modes_merges_and_tags_source(tmp_path):
    _write_agent(tmp_path, "patent-team", ["patent-engineer", "oa-replier"])
    settings = tmp_path / ".dawei" / "mode_settings.json"
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text(json.dumps({"customModes": [{"slug": "orchestrator"}], "mcpServers": {}}), encoding="utf-8")

    ri._merge_agent_modes(tmp_path, tmp_path / ".dawei" / "agents")

    data = json.loads(settings.read_text(encoding="utf-8"))
    slugs = {m["slug"]: m for m in data["customModes"]}
    assert set(slugs) == {"orchestrator", "patent-engineer", "oa-replier"}
    # 新合并的 mode 打 source=workspace 标记（resources API 依赖）
    assert slugs["patent-engineer"]["source"] == "workspace"
    assert "source" not in slugs["orchestrator"]  # 原有不改动
    # mcpServers 键保留
    assert "mcpServers" in data


def test_merge_agent_modes_no_duplicate(tmp_path):
    _write_agent(tmp_path, "alpha", ["a1"])
    settings = tmp_path / ".dawei" / "mode_settings.json"
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text(json.dumps({"customModes": [{"slug": "a1", "name": "已存在"}]}), encoding="utf-8")

    ri._merge_agent_modes(tmp_path, tmp_path / ".dawei" / "agents")

    data = json.loads(settings.read_text(encoding="utf-8"))
    assert len(data["customModes"]) == 1  # 已有 slug 不重复合并
    assert data["customModes"][0]["name"] == "已存在"


def test_merge_agent_modes_no_settings_file(tmp_path):
    """mode_settings.json 不存在时自动创建默认结构。"""
    _write_agent(tmp_path, "alpha", ["a1"])
    ri._merge_agent_modes(tmp_path, tmp_path / ".dawei" / "agents")
    data = json.loads((tmp_path / ".dawei" / "mode_settings.json").read_text(encoding="utf-8"))
    assert [m["slug"] for m in data["customModes"]] == ["a1"]
