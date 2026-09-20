# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Patch 应用器。

将 DiffOp 列表应用到一个 python-docx Document 对象上，生成修改后的 docx 文件。
关键挑战：格式保留。
"""

from __future__ import annotations

import logging
from collections import Counter

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Emu, Pt

from .ast import (
    Paragraph,
    ParagraphStyle,
    Run,
    RunStyle,
    Table,
    TableCell,
    TableRow,
)
from .differ import DiffOp, DiffType, RunDiffOp
from .serializer import DocxSerializer

logger = logging.getLogger(__name__)

# OOXML 对齐值
_ALIGNMENT_OOXML: dict[str, str] = {
    "left": "left",
    "center": "center",
    "right": "right",
    "justify": "both",
}


class DocxPatcher:
    """将 DiffOp 列表应用到 python-docx Document 对象。"""

    def apply(self, doc: Document, ops: list[DiffOp]) -> list[str]:
        """应用 DiffOp 列表到文档。

        Args:
            doc: python-docx Document 对象（会被修改）
            ops: DiffOp 列表

        Returns:
            操作结果列表

        Raises:
            ValueError: 位置超出范围
        """
        results: list[str] = []
        sorted_ops = sorted(ops, key=lambda op: op.position)

        offset = 0  # DELETE 导致的位置偏移
        for op in sorted_ops:
            actual_pos = op.position + offset
            try:
                match op.type:
                    case DiffType.INSERT:
                        self._insert_node(doc, actual_pos, op.node)
                        results.append(f"✓ 插入段落 [{actual_pos}]")
                        offset += 1
                    case DiffType.DELETE:
                        self._delete_node(doc, actual_pos)
                        results.append(f"✓ 删除段落 [{actual_pos}]")
                        offset -= 1
                    case DiffType.REPLACE:
                        self._replace_text(doc, actual_pos, op.old_text, op.new_text)
                        results.append(f"✓ 替换段落 [{actual_pos}]")
                    case DiffType.MODIFY_STYLE:
                        self._modify_style(doc, actual_pos, op.new_style)
                        results.append(f"✓ 修改样式 段落 [{actual_pos}]")
                    case DiffType.MODIFY_RUNS:
                        self._modify_runs(doc, actual_pos, op.run_diffs)
                        results.append(f"✓ 修改内容 段落 [{actual_pos}]")
            except Exception as e:
                results.append(f"✗ 段落 [{actual_pos}] 操作失败: {e}")
                logger.warning("Patch op failed at position %d: %s", actual_pos, e)

        return results

    # ------------------------------------------------------------------
    # INSERT
    # ------------------------------------------------------------------

    def _insert_node(self, doc: Document, position: int, node: Paragraph | Table | None) -> None:
        """在 position 位置插入新节点。"""
        if node is None:
            raise ValueError("INSERT 操作缺少 node")

        body = doc.element.body

        serializer = DocxSerializer()
        if isinstance(node, Paragraph):
            elem = serializer._create_paragraph_element(node, doc)
        elif isinstance(node, Table):
            elem = serializer._create_table_element(node, doc)
        else:
            raise ValueError(f"不支持的节点类型: {type(node)}")

        if position < len(body):
            body.insert(position, elem)
        else:
            body.append(elem)

    # ------------------------------------------------------------------
    # DELETE
    # ------------------------------------------------------------------

    @staticmethod
    def _delete_node(doc: Document, position: int) -> None:
        """删除 position 位置的节点。"""
        body = doc.element.body
        if position < 0 or position >= len(body):
            raise ValueError(f"Position {position} out of range [0, {len(body) - 1}]")
        body.remove(body[position])

    # ------------------------------------------------------------------
    # REPLACE
    # ------------------------------------------------------------------

    def _replace_text(
        self,
        doc: Document,
        position: int,
        old_text: str | None,
        new_text: str | None,
    ) -> None:
        """替换段落文本，尽量保留格式。"""
        if new_text is None:
            raise ValueError("REPLACE 操作缺少 new_text")

        body = doc.element.body
        if position < 0 or position >= len(body):
            raise ValueError(f"Position {position} out of range [0, {len(body) - 1}]")

        para_elem = body[position]
        tag = para_elem.tag.split("}")[-1] if "}" in para_elem.tag else para_elem.tag
        if tag != "p":
            raise ValueError(f"Position {position} 不是段落元素")

        # 获取现有 runs 的格式
        existing_runs = self._extract_runs_from_element(para_elem)

        if not existing_runs:
            # 空段落，直接创建新 run
            r = OxmlElement("w:r")
            t = OxmlElement("w:t")
            t.text = new_text
            t.set(qn("xml:space"), "preserve")
            r.append(t)
            # 清空现有内容
            for child in list(para_elem):
                tag_c = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if tag_c != "pPr":
                    para_elem.remove(child)
            para_elem.append(r)
            return

        # 解析新文本中的 Markdown 格式标记
        new_runs = parse_markdown_runs(new_text)

        if len(new_runs) == 1 and not new_runs[0].style.bold and not new_runs[0].style.italic:
            # 新文本无格式标记 — 使用"多数格式"策略
            merged_style = _merge_run_styles(existing_runs)
            self._replace_paragraph_runs(para_elem, new_text, merged_style)
        else:
            # 新文本有格式标记 — 按标记拆分 Run
            self._replace_paragraph_with_runs(para_elem, new_runs)

    def _replace_paragraph_runs(self, para_elem, text: str, style: RunStyle) -> None:
        """用单个 run 替换段落所有内容。"""
        # 清空现有 run 内容
        for child in list(para_elem):
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if tag != "pPr":
                para_elem.remove(child)

        r = OxmlElement("w:r")
        self._apply_run_style_to_element(r, style)
        t = OxmlElement("w:t")
        t.text = text
        t.set(qn("xml:space"), "preserve")
        r.append(t)
        para_elem.append(r)

    def _replace_paragraph_with_runs(self, para_elem, runs: list[Run]) -> None:
        """用多个 run 替换段落内容。"""
        # 清空现有 run 内容
        for child in list(para_elem):
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if tag != "pPr":
                para_elem.remove(child)

        serializer = DocxSerializer()
        for run in runs:
            elem = serializer._create_run_element(run)
            para_elem.append(elem)

    # ------------------------------------------------------------------
    # MODIFY_STYLE
    # ------------------------------------------------------------------

    @staticmethod
    def _modify_style(doc: Document, position: int, new_style: ParagraphStyle | None) -> None:
        """修改段落级样式。"""
        if new_style is None:
            raise ValueError("MODIFY_STYLE 操作缺少 new_style")

        body = doc.element.body
        if position < 0 or position >= len(body):
            raise ValueError(f"Position {position} out of range [0, {len(body) - 1}]")

        para_elem = body[position]
        pPr = para_elem.find(qn("w:pPr"))
        if pPr is None:
            pPr = OxmlElement("w:pPr")
            para_elem.insert(0, pPr)

        # 样式名
        pStyle = pPr.find(qn("w:pStyle"))
        if pStyle is not None:
            pStyle.set(qn("w:val"), new_style.style_name)
        else:
            pStyle = OxmlElement("w:pStyle")
            pStyle.set(qn("w:val"), new_style.style_name)
            pPr.insert(0, pStyle)

        # 对齐
        if new_style.alignment:
            jc = pPr.find(qn("w:jc"))
            if jc is None:
                jc = OxmlElement("w:jc")
                pPr.append(jc)
            jc.set(qn("w:val"), _ALIGNMENT_OOXML.get(new_style.alignment, new_style.alignment))

        # 缩进
        if new_style.indent_left_pt is not None or new_style.indent_first_line_pt is not None:
            ind = pPr.find(qn("w:ind"))
            if ind is None:
                ind = OxmlElement("w:ind")
                pPr.append(ind)
            if new_style.indent_left_pt is not None:
                ind.set(qn("w:left"), str(int(Pt(new_style.indent_left_pt))))
            if new_style.indent_first_line_pt is not None and new_style.indent_first_line_pt >= 0:
                ind.set(qn("w:firstLine"), str(int(Pt(new_style.indent_first_line_pt))))
            elif new_style.indent_first_line_pt is not None and new_style.indent_first_line_pt < 0:
                ind.set(qn("w:hanging"), str(int(Pt(-new_style.indent_first_line_pt))))

        # 间距
        if new_style.spacing_before_pt is not None or new_style.spacing_after_pt is not None:
            spacing = pPr.find(qn("w:spacing"))
            if spacing is None:
                spacing = OxmlElement("w:spacing")
                pPr.append(spacing)
            if new_style.spacing_before_pt is not None:
                spacing.set(qn("w:before"), str(int(Pt(new_style.spacing_before_pt))))
            if new_style.spacing_after_pt is not None:
                spacing.set(qn("w:after"), str(int(Pt(new_style.spacing_after_pt))))

        # 行距
        if new_style.line_spacing is not None:
            spacing = pPr.find(qn("w:spacing"))
            if spacing is None:
                spacing = OxmlElement("w:spacing")
                pPr.append(spacing)
            spacing.set(qn("w:line"), str(int(new_style.line_spacing * 240)))
            spacing.set(qn("w:lineRule"), "auto")

    # ------------------------------------------------------------------
    # MODIFY_RUNS
    # ------------------------------------------------------------------

    @staticmethod
    def _modify_runs(doc: Document, position: int, run_diffs: list[RunDiffOp] | None) -> None:
        """对段落的 runs 列表应用增量修改。"""
        if not run_diffs:
            return

        body = doc.element.body
        if position < 0 or position >= len(body):
            raise ValueError(f"Position {position} out of range [0, {len(body) - 1}]")

        para_elem = body[position]

        # 收集所有 w:r 元素
        r_elems = para_elem.findall(qn("w:r"))
        # 也收集 w:hyperlink 中的 w:r
        for hl in para_elem.findall(qn("w:hyperlink")):
            r_elems.extend(hl.findall(qn("w:r")))

        # 反向遍历，避免位置偏移
        serializer = DocxSerializer()
        for rd in sorted(run_diffs, key=lambda x: x.position, reverse=True):
            pos = rd.position
            if pos < 0 or pos >= len(r_elems):
                continue

            match rd.type:
                case "insert":
                    if rd.run is None:
                        continue
                    new_elem = serializer._create_run_element(rd.run)
                    if pos < len(r_elems):
                        r_elems[pos].addnext(new_elem)
                        r_elems.insert(pos, new_elem)
                    else:
                        para_elem.append(new_elem)
                        r_elems.append(new_elem)
                case "delete":
                    r_elem = r_elems[pos]
                    parent = r_elem.getparent()
                    if parent is not None:
                        parent.remove(r_elem)
                    r_elems.pop(pos)
                case "modify":
                    if rd.run is None:
                        continue
                    r_elem = r_elems[pos]
                    # 替换文本
                    t_elem = r_elem.find(qn("w:t"))
                    if t_elem is None:
                        t_elem = OxmlElement("w:t")
                        t_elem.set(qn("xml:space"), "preserve")
                        r_elem.append(t_elem)
                    t_elem.text = rd.run.text
                    # 应用格式
                    _apply_run_style_to_element(r_elem, rd.run.style)

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_runs_from_element(para_elem) -> list[RunStyle]:
        """从段落 XML 元素中提取 Run 格式列表。"""
        from .parser import DocxParser

        styles: list[RunStyle] = []
        for r_elem in para_elem.findall(qn("w:r")):
            style = DocxParser._parse_run_style(r_elem)
            styles.append(style)
        for hl in para_elem.findall(qn("w:hyperlink")):
            for r_elem in hl.findall(qn("w:r")):
                style = DocxParser._parse_run_style(r_elem)
                styles.append(style)
        return styles

    @staticmethod
    def _apply_run_style_to_element(r_elem, style: RunStyle) -> None:
        """将 RunStyle 应用到 w:r XML 元素。"""
        _apply_run_style_to_element(r_elem, style)


# ------------------------------------------------------------------
# 模块级辅助函数
# ------------------------------------------------------------------


def _apply_run_style_to_element(r_elem, style: RunStyle) -> None:
    """将 RunStyle 应用到 w:r XML 元素。"""
    rPr = r_elem.find(qn("w:rPr"))
    if rPr is None:
        rPr = OxmlElement("w:rPr")
        r_elem.insert(0, rPr)

    if style.bold:
        rPr.append(OxmlElement("w:b"))
    if style.italic:
        rPr.append(OxmlElement("w:i"))
    if style.underline:
        u = OxmlElement("w:u")
        u.set(qn("w:val"), "single")
        rPr.append(u)
    if style.strikethrough:
        rPr.append(OxmlElement("w:strike"))
    if style.superscript:
        rPr.append(OxmlElement("w:superscript"))
    if style.subscript:
        rPr.append(OxmlElement("w:subscript"))

    if style.font_name:
        rFonts = OxmlElement("w:rFonts")
        rFonts.set(qn("w:ascii"), style.font_name)
        rFonts.set(qn("w:hAnsi"), style.font_name)
        rFonts.set(qn("w:eastAsia"), style.font_name)
        rPr.append(rFonts)

    if style.font_size_pt is not None:
        sz = OxmlElement("w:sz")
        sz.set(qn("w:val"), str(int(style.font_size_pt * 2)))
        rPr.append(sz)

    if style.color_rgb:
        color = OxmlElement("w:color")
        color.set(qn("w:val"), style.color_rgb)
        rPr.append(color)

    if style.highlight:
        highlight = OxmlElement("w:highlight")
        highlight.set(qn("w:val"), style.highlight)
        rPr.append(highlight)


def _merge_run_styles(runs: list[RunStyle]) -> RunStyle:
    """将多个 Run 的格式合并为一个"代表格式"（多数投票）。"""
    if not runs:
        return RunStyle()

    total = len(runs)
    bold_count = sum(1 for r in runs if r.bold)
    italic_count = sum(1 for r in runs if r.italic)
    underline_count = sum(1 for r in runs if r.underline)

    font_names = [r.font_name for r in runs if r.font_name]
    font_sizes = [r.font_size_pt for r in runs if r.font_size_pt]
    colors = [r.color_rgb for r in runs if r.color_rgb]

    return RunStyle(
        bold=bold_count > total / 2,
        italic=italic_count > total / 2,
        underline=underline_count > total / 2,
        font_name=_most_common(font_names),
        font_size_pt=_most_common(font_sizes),
        color_rgb=_most_common(colors),
    )


def _most_common(items: list) -> str | int | None:
    """返回列表中最常见的元素。"""
    if not items:
        return None
    counter = Counter(items)
    return counter.most_common(1)[0][0]


def parse_markdown_runs(text: str) -> list[Run]:
    """将带 Markdown 格式标记的文本解析为 Run 列表。

    支持: **bold**, *italic*, ~~strikethrough~~, _underline_, `code`
    """
    import re

    runs: list[Run] = []
    # 正则匹配 Markdown 行内格式
    pattern = re.compile(
        r"(\*\*(.+?)\*\*)"  # **bold**
        r"|(\*(.+?)\*)"  # *italic*
        r"|(~~(.+?)~~)"  # ~~strikethrough~~
        r"|(_(.+?)_)"  # _underline_
        r"|(`(.+?)`)"  # `code`
        r"|([^*_~`]+)",  # 普通文本
    )

    for m in pattern.finditer(text):
        if m.group(2):  # **bold**
            runs.append(Run(text=m.group(2), style=RunStyle(bold=True)))
        elif m.group(4):  # *italic*
            runs.append(Run(text=m.group(4), style=RunStyle(italic=True)))
        elif m.group(6):  # ~~strikethrough~~
            runs.append(Run(text=m.group(6), style=RunStyle(strikethrough=True)))
        elif m.group(8):  # _underline_
            runs.append(Run(text=m.group(8), style=RunStyle(underline=True)))
        elif m.group(10):  # `code`
            runs.append(Run(text=m.group(10), style=RunStyle(font_name="Courier New")))
        elif m.group(11):  # 普通文本
            runs.append(Run(text=m.group(11), style=RunStyle()))

    if not runs and text:
        runs.append(Run(text=text, style=RunStyle()))

    return runs
