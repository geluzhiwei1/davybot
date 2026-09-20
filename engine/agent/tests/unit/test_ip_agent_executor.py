"""
Unit tests for IP agent executor prompt builders.

Tests cover:
  - All 9 registered prompt builders return non-empty strings
  - Country-specific application prompts contain format references
  - Prompt builders accept required and optional params
  - Registry completeness — every IP module has a builder
"""

import pytest

pytestmark = pytest.mark.unit


class TestAgentExecutorRegistry:
    """Tests for _MODULE_PROMPT_BUILDERS registry completeness."""

    def test_registry_has_9_modules(self):
        from dawei.workspace.ip_agent_executor import _MODULE_PROMPT_BUILDERS
        assert len(_MODULE_PROMPT_BUILDERS) == 9

    def test_all_ip_modules_registered(self):
        from dawei.workspace.ip_agent_executor import _MODULE_PROMPT_BUILDERS
        expected = {
            "ip-idea-vault", "ip-disclosure", "ip-draft",
            "ip-application", "ip-filing", "ip-oa-reply",
            "ip-reverse-detection", "ip-portfolio", "ip-trademark",
        }
        assert set(_MODULE_PROMPT_BUILDERS.keys()) == expected

    def test_all_builders_are_callable(self):
        from dawei.workspace.ip_agent_executor import _MODULE_PROMPT_BUILDERS
        for module, builder in _MODULE_PROMPT_BUILDERS.items():
            assert callable(builder), f"{module} builder is not callable"


class TestPromptBuilders:
    """Tests for individual prompt builder outputs."""

    def test_ip_draft_returns_non_empty(self):
        from dawei.workspace.ip_agent_executor import _MODULE_PROMPT_BUILDERS
        builder = _MODULE_PROMPT_BUILDERS["ip-draft"]
        result = builder({"description": "A method for ML"})
        assert isinstance(result, str)
        assert len(result) > 0

    def test_ip_idea_vault_returns_non_empty(self):
        from dawei.workspace.ip_agent_executor import _MODULE_PROMPT_BUILDERS
        builder = _MODULE_PROMPT_BUILDERS["ip-idea-vault"]
        result = builder({"description": "New caching algorithm"})
        assert isinstance(result, str)
        assert len(result) > 0

    def test_ip_disclosure_returns_non_empty(self):
        from dawei.workspace.ip_agent_executor import _MODULE_PROMPT_BUILDERS
        builder = _MODULE_PROMPT_BUILDERS["ip-disclosure"]
        result = builder({"description": "Neural network optimization"})
        assert isinstance(result, str)
        assert len(result) > 0

    def test_ip_application_cn_has_cnipa_reference(self):
        from dawei.workspace.ip_agent_executor import _MODULE_PROMPT_BUILDERS
        builder = _MODULE_PROMPT_BUILDERS["ip-application"]
        result = builder({
            "targetCountry": "CN",
            "description": "Data processing method",
            "applicantName": "Test Corp",
        })
        assert "CNIPA" in result or "中国" in result or "CN" in result

    def test_ip_application_us_has_uspto_reference(self):
        from dawei.workspace.ip_agent_executor import _MODULE_PROMPT_BUILDERS
        builder = _MODULE_PROMPT_BUILDERS["ip-application"]
        result = builder({
            "targetCountry": "US",
            "description": "Data processing method",
        })
        assert "USPTO" in result or "美国" in result or "US" in result

    def test_ip_application_pct_has_wipo_reference(self):
        from dawei.workspace.ip_agent_executor import _MODULE_PROMPT_BUILDERS
        builder = _MODULE_PROMPT_BUILDERS["ip-application"]
        result = builder({
            "targetCountry": "PCT",
            "description": "International filing",
        })
        assert "PCT" in result or "WIPO" in result

    def test_ip_application_default_country(self):
        from dawei.workspace.ip_agent_executor import _MODULE_PROMPT_BUILDERS
        builder = _MODULE_PROMPT_BUILDERS["ip-application"]
        # No targetCountry — should default gracefully
        result = builder({"description": "Generic patent"})
        assert isinstance(result, str)
        assert len(result) > 0

    def test_ip_filing_returns_non_empty(self):
        from dawei.workspace.ip_agent_executor import _MODULE_PROMPT_BUILDERS
        builder = _MODULE_PROMPT_BUILDERS["ip-filing"]
        result = builder({"description": "Filing route analysis"})
        assert isinstance(result, str)
        assert len(result) > 0

    def test_ip_oa_reply_returns_non_empty(self):
        from dawei.workspace.ip_agent_executor import _MODULE_PROMPT_BUILDERS
        builder = _MODULE_PROMPT_BUILDERS["ip-oa-reply"]
        result = builder({"description": "OA response for rejection"})
        assert isinstance(result, str)
        assert len(result) > 0

    def test_ip_reverse_detection_returns_non_empty(self):
        from dawei.workspace.ip_agent_executor import _MODULE_PROMPT_BUILDERS
        builder = _MODULE_PROMPT_BUILDERS["ip-reverse-detection"]
        result = builder({"description": "Infringement detection"})
        assert isinstance(result, str)
        assert len(result) > 0

    def test_ip_portfolio_returns_non_empty(self):
        from dawei.workspace.ip_agent_executor import _MODULE_PROMPT_BUILDERS
        builder = _MODULE_PROMPT_BUILDERS["ip-portfolio"]
        result = builder({"description": "Portfolio analysis"})
        assert isinstance(result, str)
        assert len(result) > 0

    def test_ip_trademark_returns_non_empty(self):
        from dawei.workspace.ip_agent_executor import _MODULE_PROMPT_BUILDERS
        builder = _MODULE_PROMPT_BUILDERS["ip-trademark"]
        result = builder({"description": "Trademark registration"})
        assert isinstance(result, str)
        assert len(result) > 0

    def test_empty_params_returns_non_empty(self):
        """Builders should handle empty params gracefully."""
        from dawei.workspace.ip_agent_executor import _MODULE_PROMPT_BUILDERS
        for module, builder in _MODULE_PROMPT_BUILDERS.items():
            result = builder({})
            assert isinstance(result, str), f"{module} returned non-string"
            assert len(result) > 0, f"{module} returned empty string"
