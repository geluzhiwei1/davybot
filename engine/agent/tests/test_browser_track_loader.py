"""connector.yml 单文件格式 —— 加载与执行器接线(新格式)。"""

from __future__ import annotations

import pytest

from dawei.social.browser_track import load_recipe
from dawei.tools.browser.browser_executor import BrowserPublishExecutor


@pytest.mark.unit
class TestSingleFileFormat:
    def test_load_recipe_new_format(self):
        r = load_recipe("mockweb")
        assert r is not None
        assert r["platform"] == "mockweb"
        assert r["capability"]["publish"] == "browser"
        assert r["capability"]["publish_modes"] == ["draft_box"]
        assert r["domains"] == ["127.0.0.1"]
        assert r["publish"]["compose_url"].startswith("http://127.0.0.1:8123")
        assert r["publish"]["selectors"]["compose_box"]["primary"] == "div#editor"

    def test_wechat_mp_draft_box_capability(self):
        r = load_recipe("wechat_mp")
        assert r["capability"]["publish_modes"] == ["draft_box"]  # 公众号一律草稿箱
        assert "mp.weixin.qq.com" in r["domains"]
        assert r["publish"]["selectors"]["compose_box"]["primary"].startswith(".ProseMirror")  # v0.2.4:2026 版公众号编辑器

    def test_xiaohongshu_constraints(self):
        r = load_recipe("xiaohongshu")
        assert r["constraints"]["char_limit"] == 1000
        assert r["constraints"]["max_files"] == 18
        assert r["capability"]["trending"] == "browser"
        assert r["trending"]["url"]  # 热点采集组已并入

    async def test_executor_with_new_format(self):
        from tests.test_browser_executor_real import FakePage, ALL

        recipe = load_recipe("mockweb")
        page = FakePage(
            {"input#title", "div#editor", "button#save-draft", "button#publish"},
            on_click_url="http://127.0.0.1:8123/success?mode=draft",
        )
        ex = BrowserPublishExecutor(recipe, confirm_callback=lambda s: True)
        r = await ex.execute(page, title="T", body="B", mode="draft_box")
        assert r["ok"] is True
        assert ("fill", "div#editor", "B") in page.actions
