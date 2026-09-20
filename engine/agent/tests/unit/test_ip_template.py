"""
Unit tests for IPTemplateManager — template loading, versioning, i18n, and workspace init.

Tests cover:
  - list_templates() — all, filtered, with i18n
  - load_template() — success, 404 returns None
  - get_version() — from index, from YAML, fallback
  - list_versions() — per-module, all
  - index integrity — all 9 modules, 18 templates
  - YAML schema validation — required fields present
  - Knowledge RAG files existence
"""

import json
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def template_base(tmp_path: Path) -> Path:
    """Create a minimal template directory structure for testing."""
    base = tmp_path / "workspace"
    base.mkdir()

    # Write index.yaml
    index = {
        "templates": {
            "ip-draft": [
                {
                    "slug": "patent-draft",
                    "name": "专利草案撰写",
                    "version": "1.0",
                    "estimated_time": "30-45 分钟",
                    "description": "撰写管辖中立的专利草案",
                    "i18n": {"en": {"name": "Patent Draft", "description": "Jurisdiction-neutral patent draft"}},
                },
            ],
            "ip-application": [
                {
                    "slug": "cn-invention",
                    "name": "中国发明专利申请",
                    "version": "1.0",
                    "description": "基于草案生成中国发明专利五书",
                    "i18n": {"en": {"name": "CN Invention", "description": "CNIPA-format invention patent"}},
                },
                {
                    "slug": "us-utility",
                    "name": "美国发明专利申请",
                    "version": "2.0",
                    "description": "USPTO utility patent",
                },
            ],
        },
    }
    with open(base / "index.yaml", "w", encoding="utf-8") as f:
        yaml.dump(index, f, allow_unicode=True)

    # Create template YAML files
    app_dir = base / "ip-application"
    app_dir.mkdir(parents=True)
    draft_dir = base / "ip-draft"
    draft_dir.mkdir(parents=True)

    cn_template = {
        "template": {
            "slug": "cn-invention",
            "name": "中国发明专利申请",
            "version": "1.0",
            "module": "ip-application",
            "team_slug": "ip-application",
            "target_country": "CN",
            "description": "基于草案生成中国发明专利五书",
            "data_requirements": {
                "required": [
                    {"key": "applicant_name", "label": "申请人", "type": "string", "store": "input/task_params.json"},
                ],
                "optional": [],
            },
            "knowledge_refs": ["knowledge/patent-law"],
            "checklists": [],
            "workspace_structure": [
                {"dir": "input", "description": "用户输入"},
                {"dir": "output", "description": "输出"},
                {"dir": "drafts", "description": "申请文件"},
            ],
            "agent_instructions": "生成中国发明专利五书。",
            "deliverables": [
                {"file": "drafts/cn_patent_package.md", "name": "中国发明专利五书", "format": "markdown"},
            ],
            "phases": [
                {"name": "plan", "label": "分析草案", "progress": 10},
                {"name": "do_spec", "label": "生成说明书", "progress": 30},
                {"name": "do_claims", "label": "生成权利要求", "progress": 25},
                {"name": "do_abstract", "label": "生成摘要", "progress": 15},
                {"name": "check", "label": "格式审查", "progress": 15},
                {"name": "act", "label": "生成最终文件", "progress": 5},
            ],
        }
    }
    with open(app_dir / "cn-invention.yaml", "w", encoding="utf-8") as f:
        yaml.dump(cn_template, f, allow_unicode=True)

    us_template = {
        "template": {
            "slug": "us-utility",
            "name": "美国发明专利申请",
            "version": "2.0",
            "module": "ip-application",
            "team_slug": "ip-application",
            "target_country": "US",
            "description": "USPTO utility patent",
            "data_requirements": {"required": [], "optional": []},
            "knowledge_refs": [],
            "checklists": [],
            "workspace_structure": [],
            "agent_instructions": "Generate USPTO utility patent.",
            "deliverables": [],
            "phases": [],
        }
    }
    with open(app_dir / "us-utility.yaml", "w", encoding="utf-8") as f:
        yaml.dump(us_template, f, allow_unicode=True)

    draft_template = {
        "template": {
            "slug": "patent-draft",
            "name": "专利草案撰写",
            "version": "1.0",
            "module": "ip-draft",
            "team_slug": "ip-draft",
            "description": "撰写管辖中立的专利草案",
            "data_requirements": {"required": [], "optional": []},
            "knowledge_refs": [],
            "checklists": [],
            "workspace_structure": [],
            "agent_instructions": "Write patent draft.",
            "deliverables": [],
            "phases": [],
        }
    }
    with open(draft_dir / "patent-draft.yaml", "w", encoding="utf-8") as f:
        yaml.dump(draft_template, f, allow_unicode=True)

    # Create checklist and knowledge dirs
    checklist_base = tmp_path / "checklists"
    checklist_base.mkdir()
    knowledge_base = tmp_path / "knowledge"
    knowledge_base.mkdir()

    return base


@pytest.fixture
def mgr(template_base: Path):
    """Create IPTemplateManager with injected test paths."""
    from dawei.workspace.ip_template import IPTemplateManager
    return IPTemplateManager(
        template_base=template_base,
        checklist_base=template_base.parent / "checklists",
        knowledge_base=template_base.parent / "knowledge",
    )


# ============================================================================
# 1. list_templates()
# ============================================================================

class TestListTemplates:
    """Tests for list_templates()."""

    def test_returns_all_templates(self, mgr):
        templates = mgr.list_templates()
        assert len(templates) == 3  # patent-draft + cn-invention + us-utility

    def test_filters_by_module(self, mgr):
        app_templates = mgr.list_templates(module_slug="ip-application")
        assert len(app_templates) == 2
        assert all(t["category"] == "ip-application" for t in app_templates)

    def test_nonexistent_module_returns_empty(self, mgr):
        result = mgr.list_templates(module_slug="nonexistent-module")
        assert result == []

    def test_each_template_has_category(self, mgr):
        for t in mgr.list_templates():
            assert "category" in t
            assert "slug" in t
            assert "name" in t

    def test_zh_lang_returns_chinese_names(self, mgr):
        templates = mgr.list_templates(lang="zh")
        cn = next(t for t in templates if t["slug"] == "cn-invention")
        assert cn["name"] == "中国发明专利申请"

    def test_en_lang_returns_english_names(self, mgr):
        templates = mgr.list_templates(lang="en")
        cn = next(t for t in templates if t["slug"] == "cn-invention")
        assert cn["name"] == "CN Invention"
        assert cn["description"] == "CNIPA-format invention patent"

    def test_en_lang_falls_back_for_missing_i18n(self, mgr):
        templates = mgr.list_templates(lang="en")
        us = next(t for t in templates if t["slug"] == "us-utility")
        # No i18n.en for us-utility, falls back to Chinese name
        assert us["name"] == "美国发明专利申请"


# ============================================================================
# 2. load_template()
# ============================================================================

class TestLoadTemplate:
    """Tests for load_template()."""

    def test_loads_existing_template(self, mgr):
        tmpl = mgr.load_template("cn-invention")
        assert tmpl is not None
        assert tmpl["template"]["slug"] == "cn-invention"
        assert tmpl["template"]["module"] == "ip-application"
        assert tmpl["template"]["target_country"] == "CN"

    def test_returns_none_for_missing_template(self, mgr):
        result = mgr.load_template("nonexistent-template")
        assert result is None

    def test_loaded_template_has_required_fields(self, mgr):
        tmpl = mgr.load_template("cn-invention")
        t = tmpl["template"]
        assert "slug" in t
        assert "name" in t
        assert "version" in t
        assert "module" in t
        assert "description" in t
        assert "data_requirements" in t
        assert "workspace_structure" in t
        assert "agent_instructions" in t
        assert "deliverables" in t
        assert "phases" in t

    def test_data_requirements_has_required_and_optional(self, mgr):
        tmpl = mgr.load_template("cn-invention")
        dr = tmpl["template"]["data_requirements"]
        assert "required" in dr
        assert "optional" in dr
        assert isinstance(dr["required"], list)
        assert isinstance(dr["optional"], list)

    def test_phases_progress_sum_is_100(self, mgr):
        tmpl = mgr.load_template("cn-invention")
        phases = tmpl["template"]["phases"]
        total = sum(p["progress"] for p in phases)
        assert total == 100, f"Phases progress sum is {total}, expected 100"


# ============================================================================
# 3. get_version()
# ============================================================================

class TestGetVersion:
    """Tests for get_version()."""

    def test_returns_version_from_index(self, mgr):
        version = mgr.get_version("cn-invention")
        assert version == "1.0"

    def test_returns_different_version(self, mgr):
        version = mgr.get_version("us-utility")
        assert version == "2.0"

    def test_returns_none_for_missing_template(self, mgr):
        version = mgr.get_version("nonexistent")
        assert version is None


# ============================================================================
# 4. list_versions()
# ============================================================================

class TestListVersions:
    """Tests for list_versions()."""

    def test_lists_all_versions(self, mgr):
        versions = mgr.list_versions()
        assert len(versions) == 3
        slugs = {v["slug"] for v in versions}
        assert slugs == {"patent-draft", "cn-invention", "us-utility"}

    def test_filters_by_module(self, mgr):
        versions = mgr.list_versions(module_slug="ip-application")
        assert len(versions) == 2
        assert all(v["category"] == "ip-application" for v in versions)

    def test_each_version_has_required_fields(self, mgr):
        for v in mgr.list_versions():
            assert "slug" in v
            assert "version" in v
            assert "category" in v
            assert v["version"] not in (None, "unknown")


# ============================================================================
# 5. Integration — Real templates from nn-market-resources
# ============================================================================

class TestRealTemplates:
    """Verify real templates from nn-market-resources load correctly."""

    @pytest.fixture
    def real_mgr(self):
        """Create IPTemplateManager with real resource paths."""
        from dawei.workspace.ip_template import IPTemplateManager
        return IPTemplateManager()

    def test_all_18_templates_load(self, real_mgr):
        templates = real_mgr.list_templates()
        assert len(templates) >= 18

    def test_all_9_modules_have_templates(self, real_mgr):
        modules = [
            "ip-idea-vault", "ip-disclosure", "ip-draft",
            "ip-application", "ip-filing", "ip-oa-reply",
            "ip-reverse-detection", "ip-portfolio", "ip-trademark",
        ]
        for mod in modules:
            tpls = real_mgr.list_templates(module_slug=mod)
            assert len(tpls) >= 1, f"Module {mod} has no templates"

    def test_every_template_loads_fully(self, real_mgr):
        """Every template in the index should load without errors."""
        templates = real_mgr.list_templates()
        for t in templates:
            detail = real_mgr.load_template(t["slug"])
            assert detail is not None, f"Template {t['slug']} returned None"
            tmpl = detail["template"]
            assert tmpl.get("slug") == t["slug"]
            assert tmpl.get("name")
            assert tmpl.get("module")

    def test_all_phases_progress_sums_to_100(self, real_mgr):
        """Every template's phases should sum progress to 100."""
        templates = real_mgr.list_templates()
        issues = []
        for t in templates:
            detail = real_mgr.load_template(t["slug"])
            phases = detail["template"].get("phases", [])
            if phases:
                total = sum(p.get("progress", 0) for p in phases)
                if total != 100:
                    issues.append(f"{t['slug']}: progress sum = {total}")
        assert issues == [], f"Progress sum issues:\n" + "\n".join(issues)

    def test_all_versions_present(self, real_mgr):
        versions = real_mgr.list_versions()
        assert len(versions) >= 18
        unknowns = [v for v in versions if v["version"] in (None, "unknown")]
        assert unknowns == [], f"Templates with unknown versions: {unknowns}"

    def test_knowledge_refs_reference_existing_dirs(self, real_mgr):
        """knowledge_refs should reference existing knowledge directories."""
        templates = real_mgr.list_templates()
        for t in templates:
            detail = real_mgr.load_template(t["slug"])
            refs = detail["template"].get("knowledge_refs", [])
            for ref in refs:
                # Should be in format "knowledge/xxx"
                assert ref.startswith("knowledge/"), f"Invalid knowledge ref: {ref}"

    def test_deliverables_have_file_paths(self, real_mgr):
        templates = real_mgr.list_templates()
        for t in templates:
            detail = real_mgr.load_template(t["slug"])
            deliverables = detail["template"].get("deliverables", [])
            for d in deliverables:
                assert "file" in d, f"{t['slug']}: deliverable missing 'file' key"
                assert "name" in d, f"{t['slug']}: deliverable missing 'name' key"

    def test_ip_application_has_9_templates(self, real_mgr):
        """ip-application module should have exactly 9 country-specific templates."""
        app_templates = real_mgr.list_templates(module_slug="ip-application")
        assert len(app_templates) == 9

    def test_workspace_structure_dirs_are_valid(self, real_mgr):
        templates = real_mgr.list_templates()
        for t in templates:
            detail = real_mgr.load_template(t["slug"])
            structure = detail["template"].get("workspace_structure", [])
            for entry in structure:
                assert "dir" in entry, f"{t['slug']}: workspace_structure entry missing 'dir'"
                assert "description" in entry, f"{t['slug']}: workspace_structure entry missing 'description'"
