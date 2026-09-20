"""BrowserExecutor 富文本注入 —— 测试即规格(rich_text 规范消费)。"""

from __future__ import annotations

import pytest

from dawei.tools.browser.browser_executor import BrowserPublishExecutor, StepOutcome

RICH_RECIPE = {
    "compose_url": "https://mp.weixin.qq.com/",
    "domains": ["mp.weixin.qq.com"],
    "publish": {
        "selectors": {
            "compose_box": {"primary": ".ProseMirror >> nth=1"},
            "save_draft_button": {"primary": 'button:has-text("保存")'},
            "success_indicator": {"method": "api_check"},
        },
        "rich_text": {
            "enabled": True,
            "content_format": "html_inline_style",
            "dialect": "wechat_section",
            "inject_method": "clipboard_paste",
            "style": {
                "heading_style": "font-weight: bold;",
                "paragraph_style": "line-height: 1.75;",
            },
        },
    },
}

PLAIN_RECIPE = {
    "compose_url": "https://creator.xiaohongshu.com/publish/publish",
    "domains": ["creator.xiaohongshu.com"],
    "publish": {
        "selectors": {
            "compose_box": {"primary": "#post-textarea"},
            "save_draft_button": {"primary": 'button:has-text("存草稿")'},
            "success_indicator": {"method": "api_check"},
        },
    },
}

LOGIN_RECIPE = {
    "compose_url": "https://baijiahao.baidu.com/builder/rc/edit?type=news",
    "domains": ["baijiahao.baidu.com"],
    "publish": {
        "selectors": {
            "compose_box": {"primary": "body.news-editor-pc"},
            "save_draft_button": {"primary": 'button:has-text("存草稿")'},
            "success_indicator": {"method": "api_check"},
        },
        "login_check": {
            "indicator": ".client_pages_edit_components_titleInput",
            "absent_indicator": 'button:has-text("注册百家号")',
            "wait_timeout_ms": 1500,
        },
    },
}

MD_BODY = "# 标题\n\n正文**加粗**"


class FakeLocator:
    def __init__(self, sel: str):
        self.sel = sel
        self.filled: str | None = None
        self.clicked = 0
        self.focused = 0

    async def count(self) -> int:
        return 1

    async def fill(self, text: str) -> None:
        self.filled = text

    async def element_handle(self):
        return self

    async def click(self) -> None:
        self.clicked += 1

    async def focus(self) -> None:
        self.focused += 1

    async def inner_text(self) -> str:
        return "已注入内容"


class FakeKeyboard:
    def __init__(self):
        self.pressed: list[str] = []

    async def press(self, key: str) -> None:
        self.pressed.append(key)


class FakeContext:
    def __init__(self):
        self.granted: list[list[str]] = []

    async def grant_permissions(self, perms) -> None:
        self.granted.append(list(perms))


class FakePage:
    """最小 Page 桩:evaluate 可编程返回(模拟剪贴板/execCommand 成败)。"""

    def __init__(self, *, evaluate_result=True, clipboard_ok=True):
        self.locators: dict[str, FakeLocator] = {}
        self.evaluated: list[tuple[str, object]] = []
        self._evaluate_result = evaluate_result
        self._clipboard_ok = clipboard_ok
        self.url = "about:blank"
        self.keyboard = FakeKeyboard()
        self.context = FakeContext()

    def locator(self, sel: str) -> FakeLocator:
        if sel not in self.locators:
            self.locators[sel] = FakeLocator(sel)
        return self.locators[sel]

    @property
    def frames(self):
        return [self]

    async def goto(self, url) -> None:
        self.url = url

    async def wait_for_load_state(self, _state) -> None:
        pass

    async def evaluate(self, script, arg=None):
        self.evaluated.append((script, arg))
        if "navigator.clipboard" in script and not self._clipboard_ok:
            raise RuntimeError("clipboard denied")
        return self._evaluate_result

    async def screenshot(self, path=None):
        return path


class SlowRenderPage(FakePage):
    """SPA 冷启模拟:指定选择器前 misses 次 count()=0(未渲染),之后 1。"""

    def __init__(self, late_selector: str, misses: int = 2):
        super().__init__()
        self._late = late_selector
        self._misses_left = misses

    def locator(self, sel: str) -> FakeLocator:
        if sel not in self.locators:
            if sel == self._late:
                self.locators[sel] = LateLocator(sel, self)
            else:
                self.locators[sel] = FakeLocator(sel)
        return self.locators[sel]


class LateLocator(FakeLocator):
    def __init__(self, sel: str, owner: SlowRenderPage):
        super().__init__(sel)
        self._owner = owner

    async def count(self) -> int:
        if self._owner._misses_left > 0:
            self._owner._misses_left -= 1
            return 0
        return 1


class NeverLocator(FakeLocator):
    """恒不出现(登录页负向标记在已登录页不在场)。"""

    async def count(self) -> int:
        return 0


async def _run(recipe: dict, page: FakePage) -> BrowserPublishExecutor:
    ex = BrowserPublishExecutor(recipe, confirm_callback=None)
    await ex.execute(page, title="t", body=MD_BODY, mode="draft_box")
    return ex


@pytest.mark.unit
class TestRichInject:
    async def test_clipboard_paste_pipeline(self):
        """clipboard_paste 主管线:方言 HTML 进剪贴板 → Ctrl+V(真机唯一样式全保留路径)。"""
        page = FakePage()
        ex = await _run(RICH_RECIPE, page)
        writes = [(s, a) for s, a in page.evaluated if "navigator.clipboard" in s]
        assert len(writes) == 1
        html = writes[0][1][0]
        assert "font-size: 24px" in html          # h1 → section + 字号(微信方言)
        assert "<section" in html
        assert "<h1" not in html
        assert "<strong>加粗</strong>" in html
        assert page.keyboard.pressed == ["Control+V"]
        assert page.context.granted
        assert "clipboard-write" in page.context.granted[0]
        assert page.locators[".ProseMirror >> nth=1"].filled is None  # 不走纯文本 fill
        assert ex.trace[-1].outcome == StepOutcome.OK

    async def test_clipboard_failure_falls_back_to_insert_html(self):
        """剪贴板被拒 → 兜底 execCommand insertHTML(内容降级但管线不断)。"""
        page = FakePage(clipboard_ok=False)
        ex = await _run(RICH_RECIPE, page)
        assert any("insertHTML" in s for s, _ in page.evaluated)
        fill = [s for s in ex.trace if s.step == "fill_compose"][0]
        assert fill.outcome == StepOutcome.OK
        assert fill.detail.get("inject") == "insert_html"  # 实际走的兜底管线落 trace

    async def test_rich_disabled_fills_plain_text(self):
        page = FakePage()
        ex = await _run(PLAIN_RECIPE, page)
        assert page.evaluated == [] or all("insertHTML" not in s and "clipboard" not in s
                                           for s, _ in page.evaluated)
        assert page.locators["#post-textarea"].filled == MD_BODY
        assert ex.trace[-1].outcome == StepOutcome.OK

    async def test_inject_failure_degrades_to_selector_stale(self):
        """剪贴板与 insertHTML 均未落地 → 无 LLM 时走 stale 阶梯,原因落 trace。"""
        page = FakePage(clipboard_ok=False, evaluate_result=False)
        ex = await _run(RICH_RECIPE, page)
        fill = [s for s in ex.trace if s.step == "fill_compose"][0]
        assert fill.outcome == StepOutcome.SELECTOR_STALE
        assert fill.detail.get("inject_error")  # 失败原因落 trace(真机远程排查)
        assert ex.trace[-1].step == "fill_compose"  # SELECTOR_STALE 早退

    async def test_trace_records_rich_flag_and_diag(self):
        page = FakePage()
        ex_rich = await _run(RICH_RECIPE, page)
        fill = [s for s in ex_rich.trace if s.step == "fill_compose"][0]
        assert fill.detail.get("rich") is True
        assert fill.detail.get("url") == "https://mp.weixin.qq.com/"  # goto 后的诊断快照

        page2 = FakePage()
        ex_plain = await _run(PLAIN_RECIPE, page2)
        fill2 = [s for s in ex_plain.trace if s.step == "fill_compose"][0]
        assert fill2.detail.get("rich") is False

    async def test_injection_js_is_owner_document_aware(self):
        """iframe 编辑器(百家号 UEditor):selection/range/execCommand 必须在
        el.ownerDocument 上执行 —— 主页面 window/document 跨文档 selectNodeContents
        抛 WrongDocumentError,注入管线整段失败(真机 2026-08-30)。
        """
        page = FakePage(clipboard_ok=False)  # 直接走 insert_html 兜底
        await _run(RICH_RECIPE, page)
        insert_js = [s for s, _ in page.evaluated if "insertHTML" in s]
        assert insert_js, "insert_html 管线未执行"
        js = insert_js[0]
        assert "el.ownerDocument" in js
        assert "doc.defaultView.getSelection()" in js
        assert "doc.createRange()" in js
        assert "doc.execCommand" in js
        assert "window.getSelection" not in js and "document.execCommand" not in js

        page2 = FakePage()  # clipboard 管线的全选段同样 ownerDocument 化
        await _run(RICH_RECIPE, page2)
        selall_js = [s for s, _ in page2.evaluated
                     if "selectNodeContents" in s and "clipboard" not in s]
        assert selall_js, "clipboard 全选段未执行"
        assert "el.ownerDocument" in selall_js[0]
        assert "doc.defaultView.getSelection()" in selall_js[0]
        assert "window.getSelection" not in selall_js[0]

    async def test_login_check_waits_for_spa_render(self):
        """login_check 等待窗口:SPA 冷启 indicator 迟到(前 2 次探测 0)仍判已登录,
        不再立即误报 login_required 死信(真机百家号 2026-08-30 复现)。"""
        page = SlowRenderPage(".client_pages_edit_components_titleInput", misses=2)
        page.locators['button:has-text("注册百家号")'] = NeverLocator("absent")
        ex = BrowserPublishExecutor(LOGIN_RECIPE, confirm_callback=None)
        await ex.execute(page, title="t", body=MD_BODY, mode="draft_box")
        lc = [s for s in ex.trace if s.step == "login_check"][0]
        assert lc.outcome == StepOutcome.OK
        assert lc.detail.get("logged_in") is True

    async def test_login_check_timeout_reports_login_required(self):
        """等待窗口耗尽仍无 indicator → login_required(不可重试,死信回人工)。"""
        page = FakePage()
        page.locators[".client_pages_edit_components_titleInput"] = NeverLocator("x")
        page.locators['button:has-text("注册百家号")'] = NeverLocator("absent")
        ex = BrowserPublishExecutor(LOGIN_RECIPE, confirm_callback=None)
        out = await ex.execute(page, title="t", body=MD_BODY, mode="draft_box")
        assert out["outcome"] == "login_required"
        assert ex.trace[1].step == "login_check"  # navigate 之后立即早退
