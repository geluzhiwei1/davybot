"""trending_scraper —— 连接器 trending 段抓取(FakePage 打桩,零浏览器依赖)。"""

from __future__ import annotations

import pytest

from dawei.social.browser_track import load_recipe
from dawei.tools.browser.trending_scraper import scrape_trending

WEIBO_RECIPE = {
    "capability": {"trending": "browser"},
    "domains": ["weibo.com"],
    "trending": {
        "url": "https://s.weibo.com/top/summary",
        "container": "tbody tr",
        "topic": "td a",
        "pagination": "none",
    },
}


class TrendingLocator:
    def __init__(self, page: TrendingPage, sel: str, row: dict | None = None):
        self.page, self.sel, self.row = page, sel, row

    async def count(self) -> int:
        if self.row is not None:  # 行内子查询
            return 1 if self.sel in self.row["elements"] else 0
        if self.sel == self.page.container_sel:
            return len(self.page.rows)
        return 1 if self.sel in self.page.page_elements else 0

    def nth(self, i: int) -> TrendingLocator:
        return TrendingLocator(self.page, self.sel, self.page.rows[i])

    @property
    def first(self) -> TrendingLocator:
        return self

    def locator(self, sel: str) -> TrendingLocator:
        assert self.row is not None, "子查询必须在行定位器上"
        return TrendingLocator(self.page, sel, self.row)

    async def inner_text(self) -> str:
        if self.row is None:
            return ""
        if self.sel == self.page.topic_sel:
            return self.row["title"]
        if self.sel == self.page.category_sel:
            return self.row.get("category", "")
        return ""

    async def get_attribute(self, attr: str) -> str | None:
        if attr == "href" and self.row is not None and self.sel == self.page.topic_sel:
            return self.row.get("href")
        return None


class TrendingPage:
    """Playwright Page 子集:goto + 容器行模型(container/topic/category/href)。

    login_url_after_goto=True 模拟未登录跳登录页:URL 改写 + 容器清空(真实重定向语义)。
    """

    def __init__(self, rows, *, url: str = "", container: str = "tbody tr", topic: str = "td a",
                 category: str = "", login_url_after_goto: bool = False, page_elements=()):
        self.rows = rows
        self.container_sel, self.topic_sel, self.category_sel = container, topic, category
        self.page_elements = set(page_elements)
        self._login_redirect = login_url_after_goto
        self.url = url or "about:blank"

    def locator(self, sel: str) -> TrendingLocator:
        return TrendingLocator(self, sel)

    async def goto(self, url: str) -> None:
        if self._login_redirect:
            self.url = "https://login.weibo.com/sso"
            self.rows = []  # 登录页没有热点容器
        else:
            self.url = url

    async def wait_for_load_state(self, state: str = "domcontentloaded") -> None:
        pass


def _rows(n=3, *, container="tbody tr", hrefs=True, categories=False):
    out = []
    for i in range(n):
        r = {"container": container, "title": f"热点{i}", "elements": ["td a"]}
        if hrefs:
            r["href"] = f"/detail/{i}"
        if categories:
            r["elements"] = ["td a", "span.cat"]
            r["category"] = f"分类{i}"
        out.append(r)
    return out


@pytest.mark.unit
class TestScrapeTrending:
    async def test_tsc1_no_trending_section(self):
        r = await scrape_trending("mockweb", recipe={"capability": {"trending": "none"}})
        assert r["ok"] is False
        assert r["outcome"] == "recipe_missing"

    async def test_tsc2_weibo_real_recipe_extracts(self):
        """真连接器(weibo connector.yml):trending 子域 s.weibo.com 在 domains 白名单内(子域放行)。"""
        recipe = load_recipe("weibo") or WEIBO_RECIPE
        trending = recipe["trending"]
        page = TrendingPage(
            _rows(3, container=trending["container"]),
            container=trending["container"], topic=trending["topic"],
        )
        r = await scrape_trending("weibo", recipe=recipe, page=page)
        assert r["ok"] is True
        assert [i["title"] for i in r["items"]] == ["热点0", "热点1", "热点2"]
        assert r["items"][0]["url"].startswith("https://s.weibo.com/detail/")

    async def test_tsc3_login_redirect_detected(self):
        page = TrendingPage(_rows(3), login_url_after_goto=True)
        r = await scrape_trending("weibo", recipe=WEIBO_RECIPE, page=page)
        assert r["ok"] is False
        assert r["outcome"] == "login_required"

    async def test_tsc4_zero_rows_with_indicator_selector_stale(self):
        """无跳转、login_check indicator 命中(已登录上下文)但容器 0 项 → selector_stale。"""
        recipe = {**WEIBO_RECIPE, "publish": {"login_check": {"indicator": ".account_box"}}}
        page = TrendingPage(_rows(0), page_elements={".account_box"})
        r = await scrape_trending("weibo", recipe=recipe, page=page)
        assert r["ok"] is False
        assert r["outcome"] == "selector_stale"

    async def test_tsc5_zero_rows_without_indicator_login_required(self):
        recipe = {**WEIBO_RECIPE, "publish": {"login_check": {"indicator": ".account_box"}}}
        page = TrendingPage(_rows(0))  # indicator 未命中 → 登录墙
        r = await scrape_trending("weibo", recipe=recipe, page=page)
        assert r["ok"] is False
        assert r["outcome"] == "login_required"

    async def test_tsc6_domain_whitelist_blocks(self):
        bad = {"trending": {**WEIBO_RECIPE["trending"], "url": "https://evil.example.com/hot"}}
        r = await scrape_trending("weibo", recipe={**WEIBO_RECIPE, **bad})
        assert r["ok"] is False
        assert "白名单" in r["error"]

    async def test_tsc7_category_optional(self):
        recipe = {**WEIBO_RECIPE, "trending": {**WEIBO_RECIPE["trending"], "category": "span.cat"}}
        page = TrendingPage(_rows(2, categories=True), category="span.cat")
        r = await scrape_trending("weibo", recipe=recipe, page=page)
        assert r["items"][0].get("category") == "分类0"

    async def test_tsc8_max_items_cap(self):
        page = TrendingPage(_rows(10))
        r = await scrape_trending("weibo", recipe=WEIBO_RECIPE, page=page, max_items=3)
        assert len(r["items"]) == 3

    async def test_tsc9_no_recipe_package(self):
        from unittest.mock import patch

        with patch("dawei.social.browser_track.load_recipe", return_value=None):
            r = await scrape_trending("no-such-platform")
        assert r["ok"] is False
        assert r["outcome"] == "recipe_missing"
