"""BrowserExecutor 策略 —— 测试即规格(PRD §11.2/§11.4)。阶段 1 红态。"""

from __future__ import annotations

import pytest

from dawei.tools.browser.browser_executor import (
    StepOutcome,
    fallback_ladder,
    url_allowed,
    verify_success,
)

XHS_WHITELIST = ["creator.xiaohongshu.com"]


@pytest.mark.unit
class TestUrlWhitelist:
    def test_bx1_allowed_domain(self):
        assert url_allowed("https://creator.xiaohongshu.com/publish/publish", XHS_WHITELIST) is True

    def test_bx1_blocked_domain(self):
        """防注入导航:白名单外一律拒绝"""
        assert url_allowed("https://evil.example.com/publish", XHS_WHITELIST) is False

    def test_bx1_subdomain_not_bypassed(self):
        """子域仿冒不放行(精确域名匹配,非后缀匹配)"""
        assert url_allowed("https://creator.xiaohongshu.com.evil.com/publish", XHS_WHITELIST) is False

    def test_bx1_empty_whitelist_denies_all(self):
        assert url_allowed("https://creator.xiaohongshu.com/publish", []) is False


@pytest.mark.unit
class TestFallbackLadder:
    def test_bx2_primary_success(self):
        assert fallback_ladder(primary_ok=True, llm_ok=False) == StepOutcome.OK

    def test_bx2_llm_recovers(self):
        assert fallback_ladder(primary_ok=False, llm_ok=True) == StepOutcome.OK_LLM_RECOVERED

    def test_bx2_both_fail_stale(self):
        assert fallback_ladder(primary_ok=False, llm_ok=False) == StepOutcome.SELECTOR_STALE


@pytest.mark.unit
class TestSuccessVerification:
    def test_bx3_matched_verifies(self):
        assert verify_success("url_change", indicator_matched=True) is True

    def test_bx3_not_matched_rejects(self):
        """不信点击成功 —— 指示器未命中即失败"""
        assert verify_success("url_change", indicator_matched=False) is False

    def test_bx3_any_method_requires_match(self):
        assert verify_success("element_visible", indicator_matched=True) is True
        assert verify_success("element_visible", indicator_matched=False) is False
