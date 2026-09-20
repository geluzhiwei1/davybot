"""BrowserExecutor —— recipe 驱动执行器策略(PRD §11.2/§11.4)。阶段 2 实现(纯策略)。"""

from __future__ import annotations

import asyncio as _aio
from dataclasses import dataclass, field
from urllib.parse import urlparse

from dawei.tools.browser.markdown_rich_text import markdown_to_rich_html, rich_enabled, rich_spec


async def _async_sleep(sec: float) -> None:
    await _aio.sleep(sec)


class StepOutcome:
    OK = "ok"
    OK_LLM_RECOVERED = "ok_llm_recovered"
    SELECTOR_STALE = "selector_stale"


@dataclass
class TraceStep:
    step: str
    outcome: str
    screenshot_path: str | None = None
    duration_ms: float = 0.0
    detail: dict = field(default_factory=dict)


def url_allowed(url: str, whitelist: list[str]) -> bool:
    """compose 导航白名单:精确域名匹配(hostname,不含端口),子域仿冒不放行。"""
    if not whitelist:
        return False
    host = urlparse(url).hostname or ""
    return bool(host) and host in whitelist


def fallback_ladder(primary_ok: bool, llm_ok: bool) -> str:
    if primary_ok:
        return StepOutcome.OK
    if llm_ok:
        return StepOutcome.OK_LLM_RECOVERED
    return StepOutcome.SELECTOR_STALE


def verify_success(indicator_method: str, indicator_matched: bool) -> bool:
    """BX-3:任何指示方法都要求实际命中 —— 不信点击成功。"""
    return indicator_matched


# 验证码墙识别标记(主页面 DOM 层):国内外主流方案覆盖;recipe 可用
# publish.captcha_selectors 追加平台特有标记(优先于内置列表)。
CAPTCHA_MARKERS: list[str] = [
    "iframe[src*='recaptcha']",
    "iframe[src*='google.com/recaptcha']",
    ".g-recaptcha",
    "#recaptcha",
    "iframe[src*='tcaptcha']",
    "#tcaptcha_iframe",
    ".geetest_holder",
    ".geetest_panel",
    "#nc_1_wrapper",
    ".nc-container",
    "iframe[src*='captcha']",
    "#captcha",
    ".captcha-container",
]


async def detect_captcha(page, extra_selectors: list[str] | None = None) -> str | None:
    """检测页面是否弹出验证码墙;命中返回首个匹配选择器,否则 None。

    判据:标记元素存在(count>0)且可见(is_visible)—— 页面常见的隐藏惰性
    容器(如常驻 #captcha 空 div)不计,降低误报(误报后果:任务误入人工
    验证码队列,人工无码可解点重试,可恢复不丢数据)。只查主页面 DOM
    (验证码 iframe 元素本身在主文档);单标记探测失败(选择器非法/上下文
    受限)不致命,静默跳过。
    """
    for sel in list(extra_selectors or []) + CAPTCHA_MARKERS:
        try:
            loc = page.locator(sel)
            if await loc.count() > 0 and await loc.is_visible():
                return sel
        except Exception:
            continue
    return None


__all__ = [
    "url_allowed", "fallback_ladder", "verify_success", "StepOutcome", "TraceStep",
    "BrowserPublishExecutor", "detect_captcha", "CAPTCHA_MARKERS",
]


class BrowserPublishExecutor:
    """真机执行器:recipe selectors 驱动 Playwright Page(browser-use 会话提供)。

    步骤(PRD §11.2):导航(白名单)→ 填标题 → 注入正文(primary→fallback)
    → 媒体上传(可选)→ 预发截图 → draft_box/direct 确认 → 成功指示器校验。
    """

    def __init__(self, recipe: dict, *, confirm_callback=None, llm_locate=None, captcha_callback=None):
        self.recipe = recipe or {}
        self.confirm_callback = confirm_callback  # 人工确认(默认必须;返回 False 终止)
        # LLM 视觉兜底(§11.4 改进4):async (page, step, primary, fallback) -> selector|None
        # 未注入时兜底关闭(确定性优先;真机调优阶段由 sidecar 注入 browser-use Agent)
        self.llm_locate = llm_locate
        # 验证码人机协同:screenshot_path|None -> bool(True=已解决,继续执行)。
        # 桌面端由 browser_track 注入(HumanGate.wait_captcha 跨线程桥);未注入
        # (云端/壳 auto 路径)时命中验证码即判 captcha_timeout → CAPTCHA_REQUIRED。
        self.captcha_callback = captcha_callback
        self.trace: list[TraceStep] = []
        self._last_fill_error = ""
        self._last_inject_used = ""
        self._last_shot: str | None = None

    def _sel(self, group: str) -> tuple[str, str]:
        groups = self.recipe.get("publish", {}).get("selectors") or self.recipe.get("selectors") or {}
        g = groups.get(group) or {}
        return g.get("primary", ""), g.get("fallback", "")

    async def _find(self, page, primary: str, fallback: str = ""):
        sels = [s for s in (primary, fallback) if s]
        for sel in sels:
            loc = page.locator(sel)
            if await loc.count() > 0:
                return loc
        # iframe 兜底:平台编辑器嵌 frame(如 B 站 york/read-editor)
        frames = getattr(page, "frames", None)
        if frames:
            for fr in list(frames)[1:]:
                for sel in sels:
                    try:
                        loc = fr.locator(sel)
                        if await loc.count() > 0:
                            return loc
                    except Exception:
                        continue
        return None

    @staticmethod
    async def _one(loc):
        """strict 模式防御:多匹配取第一个(平台常见同名编辑器真/假双节点)。"""
        try:
            if await loc.count() > 1:
                return loc.first
        except Exception:
            pass
        return loc

    async def _find_wait(self, page, primary: str, fallback: str = "", timeout_ms: int = 8000):
        """等待元素就绪(SPA/iframe 编辑器加载慢;500ms 轮询)。"""
        import time as _t

        deadline = _t.monotonic() + timeout_ms / 1000
        while True:
            loc = await self._find(page, primary, fallback)
            if loc is not None:
                return loc
            if _t.monotonic() >= deadline:
                return None
            await _async_sleep(0.5)

    async def _handle_captcha(self, page, stage: str) -> dict | None:
        """验证码墙检测关口(stage: navigate|publish)。命中且未解决 → 返回终态结果。

        - captcha_callback 已注入(桌面端):回调阻塞等人机解决;解决后复检一次,
          复检通过继续流程,复检仍命中或回调 False → captcha_timeout。
        - 未注入(云端/壳 auto 路径):立即 captcha_timeout(映射 CAPTCHA_REQUIRED,
          控制面转人工,不盲等)。
        """
        extras = (self.recipe.get("publish") or {}).get("captcha_selectors") \
            or self.recipe.get("captcha_selectors") or []
        marker = await detect_captcha(page, extras)
        if not marker:
            return None
        solved = False
        if self.captcha_callback is not None:
            try:
                solved = bool(self.captcha_callback(self._last_shot))
            except Exception:
                solved = False
        if solved and not await detect_captcha(page, extras):
            self.trace.append(TraceStep(step=f"captcha_{stage}", outcome=StepOutcome.OK,
                                        detail={"marker": marker, "solved": True}))
            return None
        self.trace.append(TraceStep(step=f"captcha_{stage}", outcome=StepOutcome.SELECTOR_STALE,
                                    detail={"marker": marker, "solved": solved}))
        return {"ok": False, "outcome": "captcha_timeout", "trace": self.trace}

    async def execute(self, page, *, title: str, body: str, media_paths: list[str] | None = None,
                      mode: str = "draft_box") -> dict:
        import time as _t

        publish = self.recipe.get("publish") or {}
        compose_url = publish.get("compose_url") or self.recipe.get("compose_url", "")
        whitelist = self.recipe.get("domains") or self.recipe.get("compose_domain_whitelist") or []
        if not compose_url or not url_allowed(compose_url, whitelist):
            self.trace.append(TraceStep(step="navigate", outcome=StepOutcome.SELECTOR_STALE,
                                        detail={"error": "compose_url 未配置或不在白名单"}))
            return {"ok": False, "outcome": StepOutcome.SELECTOR_STALE, "trace": self.trace}

        t0 = _t.monotonic()
        await page.goto(compose_url)
        try:
            await page.wait_for_load_state("domcontentloaded")
        except Exception:
            pass  # CDP 场景个别站点不触发;后续 count 定位自会暴露
        self.trace.append(TraceStep(step="navigate", outcome=StepOutcome.OK, duration_ms=(_t.monotonic() - t0) * 1000))

        # 验证码关口 1:进 compose 即弹码的风控(此时无 shot,回调收 None)
        captcha_result = await self._handle_captcha(page, stage="navigate")
        if captcha_result is not None:
            return captcha_result

        # 登录态检查(§11.2):indicator 命中且 absent_indicator 未命中才算已登录。
        # 未登录早退为 login_required —— 免去注定失败的 compose 定位,错误分类直达
        # 「需人工扫码」(不可重试,死信回人工)。
        # 等待窗口(真机 2026-08-30 百家号复现):SPA 冷启/登录跳转未完成时 indicator
        # 尚未渲染,立即判定会把已登录误报 login_required 死信 —— indicator 走
        # _find_wait(连接器可配 login_check.wait_timeout_ms,缺省 8s),absent 窗口后复判。
        lc = (publish.get("login_check") or self.recipe.get("login_check") or {})
        if lc.get("indicator"):
            lc_timeout = int(lc.get("wait_timeout_ms") or 8000)
            ok_loc = await self._find_wait(page, lc["indicator"], "", timeout_ms=lc_timeout)
            absent_loc = None
            if lc.get("absent_indicator"):
                absent_loc = await self._find(page, lc["absent_indicator"])
            if not ok_loc or absent_loc:
                self.trace.append(TraceStep(step="login_check", outcome=StepOutcome.SELECTOR_STALE,
                                            detail={"logged_in": False}))
                return {"ok": False, "outcome": "login_required", "trace": self.trace}
            self.trace.append(TraceStep(step="login_check", outcome=StepOutcome.OK,
                                        detail={"logged_in": True}))

        # 编辑器入口(可选组):compose_url 落在平台首页的平台(如公众号)需两跳进编辑器
        # ——compose_button(「新的创作」)→ compose_menu(「图文」菜单项)。
        # 直链编辑器的平台(B 站/小红书)不配置即跳过,行为不变。
        for group in ("compose_button", "compose_menu"):
            g = (publish.get("selectors") or self.recipe.get("selectors") or {}).get(group)
            if not g or not g.get("primary"):
                continue
            t0 = _t.monotonic()
            loc = await self._find_wait(page, g.get("primary", ""), g.get("fallback", ""))
            if not loc:
                self.trace.append(TraceStep(step=group, outcome=StepOutcome.SELECTOR_STALE))
                return {"ok": False, "outcome": StepOutcome.SELECTOR_STALE, "trace": self.trace}
            await (await self._one(loc)).click()
            if g.get("wait_after_click_ms"):
                await _async_sleep(g["wait_after_click_ms"] / 1000)
            detail: dict = {}
            # 编辑器开新标签页的平台(如公众号):切到最新页再继续
            try:
                pages = page.context.pages
                if len(pages) > 1 and pages[-1] is not page:
                    page = pages[-1]
                    try:
                        await page.wait_for_load_state("domcontentloaded")
                    except Exception:
                        pass
                    detail["tab_switched"] = True
            except Exception:
                pass  # 无 context 的测试桩/单页平台
            self.trace.append(TraceStep(step=group, outcome=StepOutcome.OK,
                                        duration_ms=(_t.monotonic() - t0) * 1000, detail=detail))

        # 标题(可选组;wait_timeout_ms 连接器热更,新标签 SPA 编辑器渲染慢)
        t_sel = (publish.get("selectors") or self.recipe.get("selectors") or {}).get("title_input") or {}
        if title and t_sel.get("primary"):
            loc = await self._find_wait(page, t_sel.get("primary", ""), t_sel.get("fallback", ""),
                                        timeout_ms=int(t_sel.get("wait_timeout_ms") or 8000))
            if loc:
                await (await self._one(loc)).fill(title)

        # 正文(primary → fallback;富文本平台按 connector rich_text 规范注入 HTML)
        t0 = _t.monotonic()
        c_group = (publish.get("selectors") or self.recipe.get("selectors") or {}).get("compose_box") or {}
        c_primary, c_fallback = c_group.get("primary", ""), c_group.get("fallback", "")
        loc = await self._find_wait(page, c_primary, c_fallback,
                                    timeout_ms=int(c_group.get("wait_timeout_ms") or 8000))
        spec = rich_spec(self.recipe)
        rich = rich_enabled(spec)
        fill_detail: dict = {"rich": rich}
        # 诊断:无论成败都记页面 URL + 编辑器计数(真机远程排查落 trace)
        try:
            fill_detail["url"] = (page.url or "")[:120]
            fill_detail["prosemirror_count"] = await page.evaluate(
                "document.querySelectorAll('.ProseMirror').length")
        except Exception as e:
            fill_detail["diag_error"] = f"{type(e).__name__}: {str(e)[:120]}"
        fill_ok = bool(loc)
        if loc:
            if rich:
                html = markdown_to_rich_html(body, spec)
                # evaluate 参数须为 ElementHandle(Locator 会被序列化成 undefined —— 真机踩坑 2026-08-28)
                element = await (await self._one(loc)).element_handle()
                fill_ok = element is not None and await self._fill_rich(page, element, html)
                fill_detail["inject"] = self._last_inject_used
                if not fill_ok:
                    fill_detail["inject_error"] = self._last_fill_error or "element_handle() returned None"
            else:
                await (await self._one(loc)).fill(body)
        llm_recovered = False
        if not fill_ok:
            llm_recovered = await self._llm_locate_and_fill(page, body, step="compose_box")
        outcome = fallback_ladder(fill_ok, llm_recovered)
        self.trace.append(TraceStep(step="fill_compose", outcome=outcome,
                                    duration_ms=(_t.monotonic() - t0) * 1000, detail=fill_detail))
        if outcome == StepOutcome.SELECTOR_STALE:
            return {"ok": False, "outcome": outcome, "trace": self.trace}

        # 媒体(可选)
        if media_paths:
            m = self.recipe.get("selectors", {}).get("media_upload") or {}
            loc = await self._find(page, m.get("primary", ""))
            if loc:
                await loc.set_input_files(media_paths)
                self.trace.append(TraceStep(step="upload_media", outcome=StepOutcome.OK))

        # 预发截图
        shot = None
        try:
            shot = f"trace-{int(_t.time() * 1000)}.png"
            await page.screenshot(path=shot)
            self.trace.append(TraceStep(step="screenshot", outcome=StepOutcome.OK, screenshot_path=shot))
        except Exception:
            self.trace.append(TraceStep(step="screenshot", outcome=StepOutcome.OK))
        self._last_shot = shot

        # 人工确认关卡(默认必须;PRD 3.2 原则 3)
        if self.confirm_callback is not None and not self.confirm_callback(shot):
            self.trace.append(TraceStep(step="human_confirm", outcome=StepOutcome.OK, detail={"aborted": True}))
            return {"ok": False, "outcome": "aborted_by_human", "trace": self.trace}

        # 确认发布/存草稿
        group = "save_draft_button" if mode == "draft_box" else "publish_button"
        t0 = _t.monotonic()
        p_primary, p_fallback = self._sel(group)
        btn = await self._find_wait(page, p_primary, p_fallback)
        clicked = bool(btn)
        if btn:
            await (await self._one(btn)).click()
        outcome = fallback_ladder(clicked, False)
        wait_ms = ((publish.get("selectors") or self.recipe.get("selectors") or {}).get(group) or {}).get("wait_after_click_ms", 0)
        if wait_ms:
            import asyncio

            await asyncio.sleep(wait_ms / 1000)
        self.trace.append(TraceStep(step=f"confirm_{mode}", outcome=outcome, duration_ms=(_t.monotonic() - t0) * 1000))
        if outcome != StepOutcome.OK:
            return {"ok": False, "outcome": outcome, "trace": self.trace}

        # 验证码关口 2:提交瞬间弹码是平台风控主形态(此时已有预发截图供人工参考)
        captcha_result = await self._handle_captcha(page, stage="publish")
        if captcha_result is not None:
            return captcha_result

        # 成功指示器二次校验(BX-3:不信点击成功)
        ind = (publish.get("selectors") or self.recipe.get("selectors") or {}).get("success_indicator") or {}
        matched = False
        if ind.get("method") == "url_change":
            matched = bool(ind.get("pattern")) and ind["pattern"] in (page.url or "")
        elif ind.get("method") == "element_visible":
            sel = ind.get("pattern", "")
            loc = await self._find(page, sel)
            matched = bool(loc)
        elif ind.get("method") == "text_contains":
            # 平台 toast/文案指示(如 B 站"保存成功");toast 常在 iframe 内 → 跨 frame 查找
            pat = str(ind.get("pattern") or "")
            matched = False
            if pat:
                targets = [page] + list(getattr(page, "frames", None) or [])[1:]
                for t in targets:
                    try:
                        if pat in await t.locator("body").inner_text():
                            matched = True
                            break
                    except Exception:
                        continue
        elif ind.get("method") == "api_check":
            matched = True  # 上层调用方负责平台侧查证
        ok = verify_success(ind.get("method", ""), matched)
        self.trace.append(TraceStep(step="verify_success", outcome=StepOutcome.OK if ok else StepOutcome.SELECTOR_STALE,
                                    detail={"matched": matched}))
        return {"ok": ok, "outcome": StepOutcome.OK if ok else "verify_failed",
                "post_url": page.url if ok else None, "screenshot": shot, "trace": self.trace}

    async def _fill_rich(self, page, element, html: str, plain: str = "") -> bool:
        """富文本注入。按 connector inject_method 选管线(真机结论 2026-08-28):

        - clipboard_paste(公众号等 ProseMirror 平台主选):HTML 写真剪贴板 →
          focus+全选 → Ctrl+V —— 走编辑器 paste 解析管线,section+style /
          strong/em / 列表全保留;execCommand insertHTML 会被 PM schema 剥成
          纯文本 leaf 节点,仅作兜底。
        - innerHTML(默认/兜底):focus → 全选 → execCommand insertHTML →
          失败再 innerHTML 直写 + 合成 input 事件。
        """
        self._last_fill_error = ""
        if self._inject_method() == "clipboard_paste":
            if await self._paste_via_clipboard(page, element, html, plain):
                self._last_inject_used = "clipboard_paste"
                return True
            self._last_fill_error = f"clipboard_paste failed → fallback insertHTML; {self._last_fill_error}"
        ok = await self._insert_html(page, element, html)
        if ok:
            self._last_inject_used = "insert_html"
        return ok

    def _inject_method(self) -> str:
        return str((rich_spec(self.recipe).get("inject_method")) or "innerHTML")

    async def _paste_via_clipboard(self, page, element, html: str, plain: str) -> bool:
        """真剪贴板粘贴:grant permissions → ClipboardItem(text/html) → Ctrl+V。"""
        try:
            await page.context.grant_permissions(["clipboard-read", "clipboard-write"])
            await page.evaluate(
                """async ([html, plain]) => {
                    await navigator.clipboard.write([new ClipboardItem({
                        'text/html': new Blob([html], {type: 'text/html'}),
                        'text/plain': new Blob([plain || html], {type: 'text/plain'}),
                    })]);
                }""",
                [html, plain],
            )
            await element.focus()
            # 全选既有内容,粘贴即整体替换。
            # ownerDocument 感知:iframe 内编辑器(百家号 UEditor 等)的 selection/range
            # 属于 iframe 文档 —— 主页面 window.getSelection() 跨文档 selectNodeContents
            # 抛 WrongDocumentError(真机 2026-08-30 复现);主页面编辑器两文档同一,行为不变。
            await page.evaluate(
                """(el) => {
                    const doc = el.ownerDocument;
                    const sel = doc.defaultView.getSelection();
                    const range = doc.createRange();
                    range.selectNodeContents(el);
                    sel.removeAllRanges(); sel.addRange(range);
                }""", element)
            await page.keyboard.press("Control+V")
            await _async_sleep(1.2)  # paste 解析 + PM 文档更新
            return (await element.inner_text()).strip() != ""
        except Exception as e:
            self._last_fill_error = f"{type(e).__name__}: {str(e)[:150]}"
            return False

    async def _insert_html(self, page, element, html: str) -> bool:
        """兜底管线:focus → 全选 → execCommand insertHTML → innerHTML 直写。

        ownerDocument 感知(同 _paste_via_clipboard):selection/execCommand 在
        元素所属文档上执行 —— iframe 编辑器(百家号 UEditor)与主页面编辑器统一。
        """
        try:
            ok = await page.evaluate(
                """([el, html]) => {
                    el.focus();
                    const doc = el.ownerDocument;
                    const sel = doc.defaultView.getSelection();
                    const range = doc.createRange();
                    range.selectNodeContents(el);
                    sel.removeAllRanges();
                    sel.addRange(range);
                    if (doc.execCommand('insertHTML', false, html)) return true;
                    el.innerHTML = html;
                    el.dispatchEvent(new InputEvent('input',
                        {bubbles: true, inputType: 'insertFromPaste'}));
                    return el.innerHTML.trim().length > 0;
                }""",
                [element, html],
            )
            return bool(ok)
        except Exception as e:
            self._last_fill_error = f"{type(e).__name__}: {str(e)[:200]}"
            return False

    async def _llm_locate_and_fill(self, page, body: str, step: str = "compose_box") -> bool:
        """LLM 视觉兜底(§11.4 改进4):selector 主/备均失后调用一次 LLM 定位。

        llm_locate 未注入(默认)→ 直接失败(SELECTOR_STALE,触发 recipe 更新流程);
        返回 selector 经 count>0 验证后 fill —— 不盲信模型输出。
        """
        if self.llm_locate is None:
            return False
        primary, fallback = self._sel(step)
        selector = None
        try:
            selector = await self.llm_locate(page, step, primary, fallback)
        except Exception:
            return False
        if not selector:
            return False
        loc = page.locator(selector)
        if await loc.count() == 0:
            return False
        await loc.fill(body)
        return True
