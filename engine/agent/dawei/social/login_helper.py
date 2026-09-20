"""登录窗口辅助 —— 浏览器轨手动登录入口(扫码/输密码由用户完成)。

使用场景(重要):仅本机执行端 —— 桌面 dawei sidecar / light-app 壳。
SaaS 云引擎不启动本模块(登录是"人在本机 Chrome 里扫码"的动作,云端无从执行;
router 对 /browser-track/login* 在 saas 模式 403 FAST FAIL)。

用法:
    uv run python -m dawei.social.login_helper bilibili

以平台专属 profile 启动 headful Chrome(detached,脚本退出后浏览器留存),
打开该平台 compose 页;未登录会被平台引导到登录页,用户手动完成后登录态
持久化在 DAWEI_HOME/browser-profiles/{platform}/,供浏览器轨自动化复用。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from dawei.social.browser_track import load_recipe
from dawei.tools.browser.real_session import _free_port, find_chrome, kill_profile_chrome


def profile_dir(platform: str) -> str:
    base = Path.home() / ".normnomos" / "browser-profiles" / platform
    base.mkdir(parents=True, exist_ok=True)
    return str(base)


def open_login(platform: str) -> int:
    """启动 headful Chrome(平台 profile + CDP),返回调试端口。"""
    chrome = find_chrome()
    if not chrome:
        raise SystemExit("未找到 Chrome(请安装或设置路径)")
    udd = profile_dir(platform)
    kill_profile_chrome(udd)  # 回收该 profile 的孤儿 Chrome(profile 被占是最高频故障)
    port = _free_port()

    recipe = load_recipe(platform) or {}
    url = (recipe.get("publish") or {}).get("compose_url") or "https://www.bilibili.com"

    # detached 参数平台相关:Windows 用 creationflags(常量仅 Windows 存在);
    # POSIX 用 start_new_session(setsid 脱离会话),脚本退出后浏览器均独立存活。
    if sys.platform == "win32":
        popen_kwargs = {
            "creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
        }
    else:
        popen_kwargs = {"start_new_session": True}

    proc = subprocess.Popen(  # noqa: S603 detached:浏览器独立存活
        [chrome, f"--user-data-dir={udd}", f"--remote-debugging-port={port}",
         "--no-first-run", "--no-default-browser-check", url],
        **popen_kwargs,
    )
    print(f"[login-helper] platform={platform} pid={proc.pid} cdp=127.0.0.1:{port}")
    print(f"[login-helper] profile={udd}")
    print(f"[login-helper] url={url}")
    (Path(udd) / ".cdp-port").write_text(str(port), encoding="utf-8")  # verify 模式回读
    print("[login-helper] 请在打开的 Chrome 中完成登录(扫码/密码);登录态自动持久化。")
    return port


def verify_login(platform: str) -> bool:
    """判定平台登录态(自举:优先复用登录窗 CDP,失败则自起无头会话)。

    判定走 recipe 的 login_check(indicator + absent_indicator,与执行器同语义);
    未配置 login_check 的平台回退 URL 启发式(passport/login)+ compose 元素探测。
    """
    import asyncio
    from pathlib import Path

    from dawei.social.browser_track import load_recipe

    recipe = load_recipe(platform) or {}
    url = (recipe.get("publish") or {}).get("compose_url") or ""
    port_file = Path(profile_dir(platform)) / ".cdp-port"
    port = port_file.read_text(encoding="utf-8").strip() if port_file.is_file() else ""

    async def _check_via(port_or_session) -> tuple[bool, str]:
        from playwright.async_api import async_playwright

        if isinstance(port_or_session, str):
            pw = await async_playwright().start()
            browser = await pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port_or_session}")
        else:
            pw = None
            browser = None
            session = port_or_session
            page = session.page
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)
            return await _judge(page)
        page = browser.contexts[0].pages[0] if browser.contexts and browser.contexts[0].pages                 else await browser.new_context().new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000)
        try:
            return await _judge(page)
        finally:
            await browser.close()
            if pw:
                await pw.stop()

    async def _judge(page) -> tuple[bool, str]:
        lc = (recipe.get("publish") or {}).get("login_check") or recipe.get("login_check") or {}
        if lc.get("indicator"):
            # 与 BrowserPublishExecutor 同语义:indicator 命中且 absent 未命中
            from dawei.tools.browser.browser_executor import BrowserPublishExecutor

            ex = BrowserPublishExecutor(recipe)
            ok_loc = await ex._find(page, lc["indicator"])
            bad_loc = await ex._find(page, lc["absent_indicator"]) \
                if lc.get("absent_indicator") else None
            logged = bool(ok_loc) and not bad_loc
            why = "login_check 命中" if logged else "login_check 未命中/负向标记在场"
            return logged, f"{page.url} ({why})"
        final = page.url
        # 回退:登录页特征(passport/login)→ 未登录;compose 元素在场 → 已登录
        logged = "passport" not in final and "login" not in final
        detail = final
        for sel in (".bre-title-input textarea", ".ql-editor", "[contenteditable='true']"):
            try:
                if await page.locator(sel).count() > 0:
                    detail = f"{final} (compose 元素命中: {sel})"
                    break
            except Exception:
                continue
        return logged, detail

    async def _run() -> tuple[bool, str]:
        if port:
            try:
                return await _check_via(port)
            except Exception:
                pass  # 登录窗已关/CDP 失联 → 自起会话
        from dawei.tools.browser.real_session import RealBrowserSession

        async with RealBrowserSession(platform, headless=True) as session:
            return await _check_via(session)

    ok, detail = asyncio.run(_run())
    print(f"[login-helper] logged_in={ok} final={detail}")
    return ok


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--verify":
        sys.exit(0 if verify_login(sys.argv[2]) else 1)
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    open_login(sys.argv[1])
