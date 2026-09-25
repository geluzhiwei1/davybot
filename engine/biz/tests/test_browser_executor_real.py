"""BrowserPublishExecutor 真机版 —— FakePage 打桩测试(Playwright API 子集)。"""

from __future__ import annotations

import pytest

from dawei_biz.bridges.social.browser_track import load_recipe
from dawei.tools.browser.browser_executor import BrowserPublishExecutor

RECIPE = {
    "compose_url": "https://creator.example.com/publish",
    "compose_domain_whitelist": ["creator.example.com"],
    "selectors": {
        "title_input": {"primary": "input.title"},
        "compose_box": {"primary": "div.editor", "fallback": "textarea.body"},
        "save_draft_button": {"primary": "button.save-draft"},
        "publish_button": {"primary": "button.pub"},
        "success_indicator": {"method": "url_change", "pattern": "/success"},
    },
}


class FakeLocator:
    def __init__(self, page: "FakePage", sel: str):
        self.page, self.sel = page, sel

    async def inner_text(self) -> str:
        return self.page.body_text

    async def count(self) -> int:
        return 1 if self.sel in self.page.elements else 0

    async def fill(self, text: str) -> None:
        self.page.actions.append(("fill", self.sel, text))

    async def click(self) -> None:
        self.page.actions.append(("click", self.sel))
        if self.page.on_click_url is not None:
            self.page.url = self.page.on_click_url

    async def set_input_files(self, paths) -> None:
        self.page.actions.append(("upload", self.sel, list(paths)))


class FakePage:
    def __init__(self, elements: set[str], *, url="about:blank", on_click_url=None, body_text=""):
        self.elements, self.url, self.on_click_url = elements, url, on_click_url
        self.body_text = body_text
        self.actions: list = []

    def locator(self, sel: str) -> FakeLocator:
        return FakeLocator(self, sel)

    async def goto(self, url: str) -> None:
        self.url = url
        self.actions.append(("goto", url))

    async def screenshot(self, path: str = None) -> None:
        self.actions.append(("screenshot", path))


ALL = {"input.title", "div.editor", "button.save-draft", "button.pub"}


@pytest.mark.unit
class TestLoginCheck:
    """登录态检查:indicator 未命中或 absent_indicator 命中 → login_required 早退。"""

    LC_RECIPE = {**RECIPE, "login_check": {
        "indicator": ".account_box",        # 单选择器(FakePage 精确匹配;逗号列表是 Playwright 原生语义)
        "absent_indicator": "#login_qrcode_area",
    }}

    async def test_logged_in_proceeds(self):
        page = FakePage(ALL | {".account_box"}, on_click_url="https://creator.example.com/publish/success")
        ex = BrowserPublishExecutor(self.LC_RECIPE, confirm_callback=lambda s: True)
        r = await ex.execute(page, title="t", body="b")
        assert r["ok"] is True
        assert r["trace"][0].step == "navigate"
        assert r["trace"][1].step == "login_check"

    async def test_not_logged_in_early_exit(self):
        """indicator 不在页面上 → login_required,不做 compose 填充。"""
        page = FakePage(ALL)  # 无任何登录标记
        ex = BrowserPublishExecutor(self.LC_RECIPE, confirm_callback=lambda s: True)
        r = await ex.execute(page, title="t", body="b")
        assert r["ok"] is False and r["outcome"] == "login_required"
        assert not any(a[0] == "fill" for a in page.actions)

    async def test_absent_indicator_vetoes(self):
        """indicator 命中但登录页标记存在(负向否决)→ login_required。"""
        page = FakePage(ALL | {".account_box", "#login_qrcode_area"})
        ex = BrowserPublishExecutor(self.LC_RECIPE, confirm_callback=lambda s: True)
        r = await ex.execute(page, title="t", body="b")
        assert r["ok"] is False and r["outcome"] == "login_required"
        assert r["trace"][-1].detail == {"logged_in": False}

    async def test_no_login_check_config_keeps_behavior(self):
        """未配置 login_check 的平台(如既有 XHS recipe)行为不变。"""
        page = FakePage(ALL, on_click_url="https://creator.example.com/publish/success")
        ex = BrowserPublishExecutor(RECIPE, confirm_callback=lambda s: True)
        r = await ex.execute(page, title="t", body="b")
        assert r["ok"] is True
        assert [t.step for t in r["trace"]][0] == "navigate"


@pytest.mark.unit
class TestComposeEntry:
    """编辑器入口两跳:compose_url 在平台首页时先点入口按钮再点菜单项(如公众号)。"""

    ENTRY_RECIPE = {
        **RECIPE,
        "compose_url": "https://mp.example.com/",
        "compose_domain_whitelist": ["mp.example.com"],
        "login_check": {"indicator": ".account_box"},
        "selectors": {
            **RECIPE["selectors"],
            "compose_button": {"primary": "button.new-creation", "wait_after_click_ms": 0},
            "compose_menu": {"primary": "a.appmsg", "wait_after_click_ms": 0},
        },
    }

    async def test_two_hop_entry_reaches_editor(self):
        page = FakePage({"button.new-creation", "a.appmsg", ".account_box"} | ALL,
                        on_click_url="https://mp.example.com/publish/success")
        ex = BrowserPublishExecutor(self.ENTRY_RECIPE, confirm_callback=lambda s: True)
        r = await ex.execute(page, title="t", body="b")
        assert r["ok"] is True
        clicks = [a for a in page.actions if a[0] == "click"]
        assert ("click", "button.new-creation") in clicks
        assert ("click", "a.appmsg") in clicks
        steps = [t.step for t in r["trace"]]
        assert steps[:4] == ["navigate", "login_check", "compose_button", "compose_menu"]

    async def test_entry_missing_fails_early(self):
        """入口按钮配置了但页面上没有 → selector_stale,不进入填充。"""
        page = FakePage({".account_box"} | ALL)  # 无 button.new-creation
        ex = BrowserPublishExecutor(self.ENTRY_RECIPE, confirm_callback=lambda s: True)
        r = await ex.execute(page, title="t", body="b")
        assert r["ok"] is False and r["outcome"] == "selector_stale"
        assert not any(a[0] == "fill" for a in page.actions)

    async def test_direct_link_platform_unchanged(self):
        """未配置入口组的直链平台(B 站式)trace 不含 compose_button。"""
        page = FakePage(ALL, on_click_url="https://creator.example.com/publish/success")
        ex = BrowserPublishExecutor(RECIPE, confirm_callback=lambda s: True)
        r = await ex.execute(page, title="t", body="b")
        assert r["ok"] is True
        assert "compose_button" not in [t.step for t in r["trace"]]


@pytest.mark.unit
class TestRealExecutor:
    async def test_happy_draft_box(self):
        page = FakePage(ALL, on_click_url="https://creator.example.com/publish/success?x=1")
        ex = BrowserPublishExecutor(RECIPE, confirm_callback=lambda shot: True)
        r = await ex.execute(page, title="标题", body="正文", mode="draft_box")
        assert r["ok"] is True
        assert r["post_url"].endswith("/success?x=1")
        kinds = [a[0] for a in page.actions]
        assert kinds == ["goto", "fill", "fill", "screenshot", "click"]
        assert page.actions[1] == ("fill", "input.title", "标题")
        assert page.actions[2] == ("fill", "div.editor", "正文")
        assert page.actions[4] == ("click", "button.save-draft")  # draft_box 语义
        steps = [t.step for t in r["trace"]]
        assert steps == ["navigate", "fill_compose", "screenshot", "confirm_draft_box", "verify_success"]

    async def test_fallback_selector_used(self):
        page = FakePage({"textarea.body", "button.pub"}, on_click_url="https://creator.example.com/publish/success")
        ex = BrowserPublishExecutor(RECIPE, confirm_callback=lambda s: True)
        r = await ex.execute(page, title="t", body="b", mode="direct")
        assert r["ok"] is True
        assert ("fill", "textarea.body", "b") in page.actions
        assert ("click", "button.pub") in page.actions

    async def test_both_selectors_missing_stale(self):
        page = FakePage({"button.pub"})
        ex = BrowserPublishExecutor(RECIPE, confirm_callback=lambda s: True)
        r = await ex.execute(page, title="t", body="b")
        assert r["ok"] is False and r["outcome"] == "selector_stale"
        assert not any(a[0] == "click" for a in page.actions)  # 未点任何按钮

    async def test_human_abort(self):
        page = FakePage(ALL)
        ex = BrowserPublishExecutor(RECIPE, confirm_callback=lambda s: False)  # 拒绝
        r = await ex.execute(page, title="t", body="b")
        assert r["ok"] is False and r["outcome"] == "aborted_by_human"
        assert not any(a[0] == "click" for a in page.actions)

    async def test_success_indicator_unmatched(self):
        """BX-3:点击后指示器未命中 → 不信成功"""
        page = FakePage(ALL, on_click_url="https://creator.example.com/publish")  # 未变成功页
        ex = BrowserPublishExecutor(RECIPE, confirm_callback=lambda s: True)
        r = await ex.execute(page, title="t", body="b")
        assert r["ok"] is False and r["outcome"] == "verify_failed"

    async def test_whitelist_blocks_foreign_compose(self):
        recipe = dict(RECIPE, compose_url="https://evil.com/publish")
        page = FakePage(ALL)
        ex = BrowserPublishExecutor(recipe)
        r = await ex.execute(page, title="t", body="b")
        assert r["ok"] is False and page.actions == []  # 连导航都不发生
