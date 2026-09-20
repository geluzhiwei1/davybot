"""markdown_rich_text —— 测试即规格(connector rich_text 规范驱动的 md→HTML)。"""

from __future__ import annotations

import pytest

from dawei.tools.browser.markdown_rich_text import (
    markdown_to_rich_html,
    rich_enabled,
    rich_spec,
)

WECHAT_SPEC = {
    "enabled": True,
    "content_format": "html_inline_style",
    "style": {
        "heading_style": "margin: 1.2em 0 0.6em; font-weight: bold;",
        "paragraph_style": "margin: 0.8em 0; line-height: 1.75;",
        "image_style": "max-width: 100%;",
        "blockquote_style": "border-left: 4px solid #07c160;",
        "list_style": "padding-left: 2em;",
    },
}

ZHIHU_SPEC = {"enabled": True, "content_format": "html_semantic"}

WECHAT_DIALECT_SPEC = {
    "enabled": True,
    "content_format": "html_inline_style",
    "dialect": "wechat_section",
    "style": {
        "heading_style": "margin: 1.2em 0 0.6em; font-weight: bold;",
        "paragraph_style": "margin: 0.8em 0; line-height: 1.75;",
        "blockquote_style": "border-left: 4px solid #07c160;",
        "list_style": "padding-left: 2em;",
    },
}


@pytest.mark.unit
class TestInlineStyle:
    def test_heading_gets_style(self):
        html = markdown_to_rich_html("# 标题", WECHAT_SPEC)
        assert '<h1 style="margin: 1.2em 0 0.6em; font-weight: bold;">标题</h1>' in html

    def test_paragraph_style_and_inline_marks(self):
        html = markdown_to_rich_html("正文**加粗**与*斜体*", WECHAT_SPEC)
        assert '<p style="margin: 0.8em 0; line-height: 1.75;">' in html
        assert "<strong>加粗</strong>" in html
        assert "<em>斜体</em>" in html

    def test_blockquote_and_list_styled(self):
        html = markdown_to_rich_html("> 引用\n\n- 项一\n- 项二", WECHAT_SPEC)
        assert '<blockquote style="border-left: 4px solid #07c160;">' in html
        assert '<ul style="padding-left: 2em;">' in html
        assert "<li>项一</li>" in html

    def test_image_gets_style_and_keeps_src(self):
        html = markdown_to_rich_html("![alt](https://cdn.example.com/a.png)", WECHAT_SPEC)
        # markdown2 把独立图片包进 <p>(合规输出);样式与属性都要在
        assert '<img src="https://cdn.example.com/a.png" alt="alt" style="max-width: 100%;"' in html
        assert 'src="https://cdn.example.com/a.png"' in html
        assert 'alt="alt"' in html

    def test_partial_style_map_only_styles_provided_tags(self):
        spec = {"content_format": "html_inline_style", "style": {"heading_style": "font-weight: bold;"}}
        html = markdown_to_rich_html("# 标题\n\n正文", spec)
        assert '<h1 style="font-weight: bold;">' in html
        assert "<p>" in html
        assert "<p " not in html

    def test_style_overrides_existing_attr(self):
        """注入 style 覆盖而非叠加(源文来自 markdown2,正常无 style;防御性)"""
        html = markdown_to_rich_html("# t", WECHAT_SPEC)
        assert html.count("style=") == 1


@pytest.mark.unit
class TestSemanticPassthrough:
    def test_html_semantic_no_style_attrs(self):
        html = markdown_to_rich_html("# 标题\n\n正文", ZHIHU_SPEC)
        assert "style=" not in html
        assert "<h1>标题</h1>" in html

    def test_default_spec_is_semantic(self):
        html = markdown_to_rich_html("# 标题", None)
        assert "style=" not in html

    def test_unknown_format_falls_back_semantic(self):
        html = markdown_to_rich_html("# t", {"content_format": "bbcode"})
        assert "style=" not in html


@pytest.mark.unit
class TestSafetyAndEdges:
    def test_raw_html_escaped(self):
        """safe_mode=escape:源文裸 HTML 不落编辑器(防 <script> 注入)"""
        html = markdown_to_rich_html("<script>alert(1)</script>", WECHAT_SPEC)
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_link_href_entity_escaped(self):
        html = markdown_to_rich_html("[点这](https://a.com/?x=1&y=2)", WECHAT_SPEC)
        assert 'href="https://a.com/?x=1&amp;y=2"' in html

    def test_fenced_code_not_markdown_processed(self):
        md = "```\n**不是粗体**\n```"
        html = markdown_to_rich_html(md, WECHAT_SPEC)
        assert "**不是粗体**" in html
        assert "<strong>" not in html

    def test_crlf_input(self):
        html = markdown_to_rich_html("# 标题\r\n\r\n正文\r\n", WECHAT_SPEC)
        assert "标题" in html
        assert "正文" in html

    def test_empty_input(self):
        assert markdown_to_rich_html("", WECHAT_SPEC) == ""


@pytest.mark.unit
class TestWechatSectionDialect:
    """真机结论(2026-08-28):公众号 PM paste 管线认 section+style;
    标准 h2/p 会被剥成纯文本 —— 方言改写决定内容存活。"""

    def test_paragraph_maps_to_section(self):
        html = markdown_to_rich_html("正文", WECHAT_DIALECT_SPEC)
        assert '<section style="margin: 0.8em 0; line-height: 1.75;">正文</section>' in html
        assert "<p" not in html

    def test_heading_maps_to_section_with_font_size(self):
        html = markdown_to_rich_html("## 标题", WECHAT_DIALECT_SPEC)
        assert "font-size: 22px" in html
        assert "<h2" not in html

    def test_blockquote_maps_to_section_keeps_border(self):
        html = markdown_to_rich_html("> 引用", WECHAT_DIALECT_SPEC)
        assert "border-left: 4px solid #07c160" in html
        assert "<blockquote" not in html

    def test_lists_stay_lists_with_style(self):
        html = markdown_to_rich_html("- 项", WECHAT_DIALECT_SPEC)
        assert '<ul style="padding-left: 2em;">' in html
        assert "<li>项</li>" in html

    def test_inline_marks_survive(self):
        html = markdown_to_rich_html("**粗** *斜*", WECHAT_DIALECT_SPEC)
        assert "<strong>粗</strong>" in html
        assert "<em>斜</em>" in html

    def test_no_dialect_keeps_standard_tags(self):
        html = markdown_to_rich_html("# t\n\np", WECHAT_SPEC)  # WECHAT_SPEC 无 dialect
        assert "<h1" in html
        assert "<p" in html
        assert "<section" not in html


@pytest.mark.unit
class TestSpecHelpers:
    def test_rich_spec_from_recipe(self):
        recipe = {"publish": {"rich_text": {"enabled": True}}}
        assert rich_spec(recipe) == {"enabled": True}
        assert rich_spec({}) == {}

    def test_rich_enabled_gate(self):
        assert rich_enabled({"enabled": True, "content_format": "html_inline_style"}) is True
        assert rich_enabled({"enabled": True, "content_format": "bbcode"}) is False
        assert rich_enabled({"enabled": False, "content_format": "html_inline_style"}) is False
        assert rich_enabled({}) is False
