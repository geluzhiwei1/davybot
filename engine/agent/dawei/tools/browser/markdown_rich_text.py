"""markdown → 平台富文本 HTML(connector publish.rich_text 规范驱动)。

分层:markdown2(safe_mode=escape,源文裸 HTML 转义防注入)产出语义 HTML;
按 content_format 决定终态:
- html_inline_style:块级标签注入 rich_text.style 样式表
- html_semantic:语义标签直通(知乎/B 站编辑器)

dialect(可选)叠加方言改写:
- wechat_section:块级元素映射为微信编辑器方言(段落/标题/引用全用 <section
  + style>,标题附 font-size)。真机结论(2026-08-28):公众号 2026 ProseMirror
  的 paste 管线认 section+style / strong/em / ul-ol-li;标准 h2/p 会被剥成
  纯文本 leaf 节点 —— 方言决定内容能不能活,注入方式见 executor clipboard_paste。

style 表来自 connector.yml(市场热更),本模块不内置任何平台样式。
"""

from __future__ import annotations

from html import escape
from html.parser import HTMLParser

SUPPORTED_FORMATS = ("html_inline_style", "html_semantic")
SUPPORTED_DIALECTS = ("", "wechat_section")

# connector.yml publish.rich_text.style 键 → 受益块级标签
_STYLE_TARGETS = {
    "heading_style": ("h1", "h2", "h3", "h4", "h5", "h6"),
    "paragraph_style": ("p",),
    "image_style": ("img",),
    "blockquote_style": ("blockquote",),
    "list_style": ("ul", "ol"),
}

# wechat_section 方言:标题 → section + heading_style + 字号(px)
_HEADING_FONT_SIZE = {"h1": "24px", "h2": "22px", "h3": "20px", "h4": "18px", "h5": "16px", "h6": "16px"}
# 方言块级映射:语义标签 → (方言标签, 样式键)
_DIALECT_BLOCKS = {
    **dict.fromkeys(_HEADING_FONT_SIZE, ("section", "heading_style")),
    "p": ("section", "paragraph_style"),
    "blockquote": ("section", "blockquote_style"),
    "ul": ("ul", "list_style"),
    "ol": ("ol", "list_style"),
}

_VOID = {"img", "br", "hr", "input", "meta", "link"}


class _RichHTMLRewriter(HTMLParser):
    """语义 HTML → 平台方言 HTML:按 style_map 给目标标签补 style,按 dialect
    改写块级标签(微信公众号 section 方言);其余节点原样透传。"""

    def __init__(self, style_map: dict[str, str], dialect: str = ""):
        super().__init__(convert_charrefs=True)
        self._map = style_map
        self._dialect = dialect
        self._out: list[str] = []

    def _rewrite(self, tag: str) -> tuple[str, str]:
        """(标签, 附加样式)——方言块级映射 + heading 字号。"""
        if self._dialect != "wechat_section" or tag not in _DIALECT_BLOCKS:
            return tag, ""
        new_tag, _style_key = _DIALECT_BLOCKS[tag]
        extra = f"font-size: {_HEADING_FONT_SIZE[tag]};" if tag in _HEADING_FONT_SIZE else ""
        return new_tag, (f"{self._map.get(tag, '')} {extra}").strip()

    def _start(self, tag: str, attrs, self_closing: bool) -> None:
        pairs = [(k, v) for k, v in attrs if k != "style"]
        new_tag, dialect_style = self._rewrite(tag)
        style = dialect_style or self._map.get(tag)
        if style:
            pairs.append(("style", style))
        rendered = " ".join(k if v is None else f'{k}="{escape(v, quote=True)}"' for k, v in pairs)
        suffix = " />" if self_closing and new_tag in _VOID else ">"
        self._out.append(f"<{new_tag}{' ' + rendered if rendered else ''}{suffix}")

    def handle_starttag(self, tag, attrs):
        self._start(tag, attrs, self_closing=False)

    def handle_startendtag(self, tag, attrs):
        self._start(tag, attrs, self_closing=True)

    def handle_endtag(self, tag):
        if tag in _VOID:
            return
        if self._dialect == "wechat_section" and tag in _DIALECT_BLOCKS:
            self._out.append(f"</{_DIALECT_BLOCKS[tag][0]}>")
        else:
            self._out.append(f"</{tag}>")

    def handle_data(self, data):
        self._out.append(escape(data, quote=False))

    def result(self) -> str:
        return "".join(self._out)


# 兼容旧名(外部如有引用)
_StyleInjector = _RichHTMLRewriter


def _style_map(spec: dict) -> dict[str, str]:
    style = spec.get("style") if isinstance(spec.get("style"), dict) else {}
    out: dict[str, str] = {}
    for key, tags in _STYLE_TARGETS.items():
        s = str(style.get(key) or "").strip()
        if s:
            for tag in tags:
                out[tag] = s
    return out


def rich_spec(recipe: dict) -> dict:
    """recipe(=connector.yml 全量)→ publish.rich_text 节(缺省空 dict)。"""
    publish = recipe.get("publish") if isinstance(recipe.get("publish"), dict) else {}
    spec = publish.get("rich_text")
    return spec if isinstance(spec, dict) else {}


def rich_enabled(spec: dict) -> bool:
    """是否走富文本注入(enabled 且格式在支持列表)。"""
    return bool(isinstance(spec, dict) and spec.get("enabled")
                and spec.get("content_format") in SUPPORTED_FORMATS)


def markdown_to_rich_html(md: str, spec: dict | None = None) -> str:
    """md 源文本 → 平台 HTML。

    spec 为 connector publish.rich_text 节;html_inline_style 注入 style 表
    (dialect=wechat_section 时块级映射为微信 section 方言),
    其余(html_semantic/缺省)语义直通。裸 HTML 一律转义(编辑器注入安全)。
    """
    import markdown2  # 延迟导入:非富文本路径零开销

    if not (md or "").strip():
        return ""
    semantic = markdown2.markdown(md, safe_mode="escape",
                                  extras=["fenced-code-blocks"])
    if not isinstance(spec, dict) or spec.get("content_format") != "html_inline_style":
        return semantic.strip()
    dialect = str(spec.get("dialect") or "")
    rewriter = _RichHTMLRewriter(_style_map(spec), dialect)
    rewriter.feed(semantic)
    rewriter.close()
    return rewriter.result().strip()


__all__ = ["SUPPORTED_FORMATS", "SUPPORTED_DIALECTS", "markdown_to_rich_html",
           "rich_spec", "rich_enabled"]
