"""TrendingScraper —— 连接器 trending 段驱动的热点页抓取(PRD §11.3 B4 引擎轨)。

connector.yml 契约(_schema/selectors.schema.json):
  trending: {url, container, topic, category?, pagination: none|scroll|click}

策略:
  - 域名白名单(recipe.domains)校验 trending.url —— 不在白名单拒绝导航
  - 登录判定用页面特征:goto 后 URL 跳到登录域(login/passport/signin/sso)→ login_required;
    容器 0 项且 recipe.login_check.indicator 未命中 → login_required;否则 selector_stale
  - pagination: none=首页即止;scroll=N 轮滚动合并去重;click=P0 首页(schema 无 next 选择器)
  - topic 为 <a> 时取 href 为条目 url(相对路径按页面基址绝对化)
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urljoin, urlparse

LOGIN_URL_MARKERS = ("login", "passport", "signin", "sso")


def _host(url: str) -> str:
    return urlparse(url).hostname or ""


def _host_allowed(host: str, whitelist: list[str]) -> bool:
    """精确域名或其子域(s.weibo.com ⊂ weibo.com;trending 页常在子域)。"""
    return any(host == d or host.endswith("." + d) for d in whitelist)


async def scrape_trending(
    platform: str,
    *,
    recipe: dict[str, Any] | None = None,
    page=None,
    max_items: int = 50,
    scroll_rounds: int = 3,
    headless: bool = True,
) -> dict[str, Any]:
    """抓取平台热点榜 → {ok, items, outcome};失败 {ok: False, outcome, error}。

    page 注入时零浏览器依赖(单测);缺省用 RealBrowserSession(平台登录态 profile)。
    """
    if recipe is None:
        from dawei.social.browser_track import load_recipe

        recipe = load_recipe(platform)
    if not recipe:
        return {"ok": False, "outcome": "recipe_missing", "items": [],
                "error": f"未找到 {platform} 的连接器包"}

    trending = recipe.get("trending") or {}
    url = str(trending.get("url") or "").strip()
    container = str(trending.get("container") or "").strip()
    topic = str(trending.get("topic") or "").strip()
    category_sel = str(trending.get("category") or "").strip()
    pagination = str(trending.get("pagination") or "none").strip()
    if not url or not container or not topic:
        return {"ok": False, "outcome": "recipe_missing", "items": [],
                "error": f"{platform} 连接器 trending 段不完整(url/container/topic)"}

    domains = [str(d) for d in (recipe.get("domains") or [])]
    if domains and not _host_allowed(_host(url), domains):
        return {"ok": False, "outcome": "recipe_missing", "items": [],
                "error": f"trending.url 域名 {_host(url)} 不在 domains 白名单"}

    owned_session = page is None
    if owned_session:
        from dawei.tools.browser.real_session import RealBrowserSession

        session = RealBrowserSession(platform, headless=headless)
        page = (await session.start()).page  # start() 返回 session 自身;Playwright Page 在 .page
    try:
        items = await _extract(page, url=url, container=container, topic=topic,
                               category_sel=category_sel, pagination=pagination,
                               max_items=max_items, scroll_rounds=scroll_rounds)
        if items:
            return {"ok": True, "outcome": "ok", "items": items[:max_items]}
        # 0 项:登录墙 or 选择器过期 —— 按页面特征分辨
        if _looks_login_page(page.url) or not await _indicator_present(page, recipe):
            return {"ok": False, "outcome": "login_required", "items": [],
                    "error": f"{platform} 热点页需要登录态(先 /browser-track/login 扫码)"}
        return {"ok": False, "outcome": "selector_stale", "items": [],
                "error": f"容器 {container} 命中 0 项(平台改版?)", }
    except Exception as e:  # 导航失败/浏览器崩溃
        return {"ok": False, "outcome": "selector_stale", "items": [], "error": str(e)[:200]}
    finally:
        if owned_session:
            try:
                await session.close()
            except Exception:
                pass


def _looks_login_page(url: str) -> bool:
    host_path = (urlparse(url).hostname or "") + (urlparse(url).path or "")
    return any(m in host_path.lower() for m in LOGIN_URL_MARKERS)


async def _indicator_present(page, recipe: dict) -> bool:
    """recipe.publish.login_check.indicator 在当前页命中 → 视为已登录上下文。"""
    sel = str(((recipe.get("publish") or {}).get("login_check") or {}).get("indicator") or "")
    if not sel:
        return False
    try:
        first = sel.partition(",")[0].strip()
        return await page.locator(first).count() > 0
    except Exception:
        return False


async def _extract(page, *, url: str, container: str, topic: str, category_sel: str,
                   pagination: str, max_items: int, scroll_rounds: int) -> list[dict]:
    await page.goto(url)
    wait = getattr(page, "wait_for_load_state", None)
    if wait:
        await wait("domcontentloaded")

    seen: dict[str, dict] = {}
    rounds = [0] if pagination != "scroll" else list(range(max(1, scroll_rounds)))
    for r in rounds:
        await _collect_batch(page, container=container, topic=topic,
                             category_sel=category_sel, base_url=url, seen=seen, max_items=max_items)
        if len(seen) >= max_items:
            break
        if pagination == "scroll" and r < rounds[-1]:
            mouse = getattr(page, "mouse", None)
            if mouse is None:
                break  # 打桩页无 mouse:首轮即止
            await mouse.wheel(0, 2000)
            import asyncio as _aio

            await _aio.sleep(1.2)
    return list(seen.values())


async def _collect_batch(page, *, container: str, topic: str, category_sel: str,
                         base_url: str, seen: dict, max_items: int) -> None:
    """当前视口内收集一批条目(标题去重合并;URL 跳过取 href)。"""
    loc = page.locator(container)
    try:
        count = await loc.count()
    except Exception:
        return
    for i in range(min(count, max_items * 2)):
        try:
            row = loc.nth(i)
            title_loc = row.locator(topic)
            n = await title_loc.count()
            if n == 0:
                continue
            el = title_loc.first if n > 1 else title_loc
            title = (await el.inner_text()).strip()
            if not title or title in seen:
                continue
            item: dict[str, Any] = {"title": title}
            href = await _safe_attr(el, "href")
            if href:
                item["url"] = href if href.startswith("http") else urljoin(base_url, href)
            if category_sel:
                cat_loc = row.locator(category_sel)
                if await cat_loc.count() > 0:
                    item["category"] = (await cat_loc.first.inner_text()).strip()
            seen[title] = item
            if len(seen) >= max_items:
                return
        except Exception:
            continue


async def _safe_attr(el, attr: str) -> str | None:
    try:
        v = await el.get_attribute(attr)
        return str(v) if v else None
    except Exception:
        return None


__all__ = ["scrape_trending"]
