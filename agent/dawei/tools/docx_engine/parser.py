# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""docx → DocxAST 解析器。

遍历 python-docx Document 的 body 元素，保留原始顺序（段落和表格交替出现），
将 OOXML 结构映射为 DocxAST 数据模型。
"""

from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.shared import Emu, Pt

from .ast import (
    DocxAST,
    DocxMetadata,
    Paragraph,
    ParagraphStyle,
    Run,
    RunStyle,
    Table,
    TableCell,
    TableRow,
)

_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


class DocxParser:
    """将 docx 文件解析为 DocxAST。"""

    def parse(self, file_path: str | Path) -> DocxAST:
        """将 docx 文件解析为 DocxAST。

        Args:
            file_path: docx 文件路径

        Returns:
            DocxAST 结构化表示

        Raises:
            FileNotFoundError: 文件不存在
            ValueError: 文件不是有效的 docx
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {path}")
        if path.suffix.lower() not in (".docx",):
            raise ValueError(f"不支持的文件格式: {path.suffix}，仅支持 .docx")

        doc = Document(str(path))
        ast = DocxAST(metadata=self._parse_metadata(doc))

        index = 0
        for element in doc.element.body:
            tag = element.tag.split("}")[-1] if "}" in element.tag else element.tag

            if tag == "p":
                para = self._parse_paragraph(element, index)
                ast.nodes.append(para)
                index += 1
            elif tag == "tbl":
                table = self._parse_table(element, index)
                ast.nodes.append(table)
                index += 1
            # 忽略 sdt (Structured Document Tag) 等其他元素

        return ast

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    def _parse_metadata(self, doc: Document) -> DocxMetadata:
        meta = DocxMetadata()
        try:
            core = doc.core_properties
            meta.author = core.author or None
            meta.title = core.title or None
            if core.created:
                meta.created = core.created.isoformat()
            if core.modified:
                meta.modified = core.modified.isoformat()
        except Exception:
            pass
        return meta

    # ------------------------------------------------------------------
    # Paragraph
    # ------------------------------------------------------------------

    def _parse_paragraph(self, p_elem, index: int) -> Paragraph:
        style = self._parse_paragraph_style(p_elem)
        runs = self._parse_runs(p_elem)
        return Paragraph(index=index, style=style, runs=runs)

    def _parse_paragraph_style(self, p_elem) -> ParagraphStyle:
        ps = ParagraphStyle()

        pPr = p_elem.find(qn("w:pPr"))
        if pPr is None:
            return ps

        # 样式名
        pStyle = pPr.find(qn("w:pStyle"))
        if pStyle is not None:
            ps.style_name = pStyle.get(qn("w:val"), "Normal")

        # 对齐
        jc = pPr.find(qn("w:jc"))
        if jc is not None:
            ps.alignment = jc.get(qn("w:val"))

        # 缩进
        ind = pPr.find(qn("w:ind"))
        if ind is not None:
            left = ind.get(qn("w:left"))
            if left:
                ps.indent_left_pt = Emu(int(left)).pt
            first_line = ind.get(qn("w:firstLine"))
            if first_line:
                ps.indent_first_line_pt = Emu(int(first_line)).pt
            hanging = ind.get(qn("w:hanging"))
            if hanging and ps.indent_first_line_pt is None:
                ps.indent_first_line_pt = -Emu(int(hanging)).pt

        # 间距
        spacing = pPr.find(qn("w:spacing"))
        if spacing is not None:
            before = spacing.get(qn("w:before"))
            if before:
                ps.spacing_before_pt = Emu(int(before)).pt
            after = spacing.get(qn("w:after"))
            if after:
                ps.spacing_after_pt = Emu(int(after)).pt
            line = spacing.get(qn("w:line"))
            if line:
                rule = spacing.get(qn("w:lineRule"), "auto")
                if rule == "auto":
                    ps.line_spacing = int(line) / 240.0
                else:
                    ps.line_spacing = Emu(int(line)).pt

        # 编号
        numPr = pPr.find(qn("w:numPr"))
        if numPr is not None:
            numId = numPr.find(qn("w:numId"))
            if numId is not None:
                ps.numbering_id = numId.get(qn("w:val"))
            ilvl = numPr.find(qn("w:ilvl"))
            if ilvl is not None:
                ps.numbering_level = int(ilvl.get(qn("w:val"), "0"))

        return ps

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def _parse_runs(self, p_elem) -> list[Run]:
        runs: list[Run] = []

        # 处理超链接 (w:hyperlink)
        for hyperlink in p_elem.findall(qn("w:hyperlink")):
            self._parse_runs_from_element(hyperlink, runs, hyperlink)

        # 处理普通 run
        self._parse_runs_from_element(p_elem, runs)

        return runs

    def _parse_runs_from_element(self, parent, runs: list[Run], hyperlink_elem=None) -> None:
        """从父元素中解析所有 w:r 并追加到 runs 列表。"""
        hyperlink_url = None
        if hyperlink_elem is not None:
            rid = hyperlink_elem.get(qn(f"{{{_REL_NS}}}id"))
            if rid:
                try:
                    from docx.opc.constants import RELATIONSHIP_TYPE as RT

                    doc_part = hyperlink_elem.getparent()
                    while doc_part is not None and not hasattr(doc_part, "part"):
                        doc_part = doc_part.getparent()
                    if doc_part and hasattr(doc_part, "part"):
                        rel = doc_part.part.rels.get(rid)
                        if rel:
                            hyperlink_url = rel.target_ref
                except Exception:
                    pass

        for r_elem in parent.findall(qn("w:r")):
            text = self._extract_run_text(r_elem)
            style = self._parse_run_style(r_elem)
            if hyperlink_url:
                style.hyperlink_url = hyperlink_url
            # 保留空 run（可能有格式意义）
            if text or style.bold or style.italic or style.underline or style.strikethrough:
                runs.append(Run(text=text, style=style))

    @staticmethod
    def _extract_run_text(r_elem) -> str:
        """从 w:r 元素中提取文本内容。"""
        parts: list[str] = []
        for t_elem in r_elem.findall(qn("w:t")):
            if t_elem.text:
                parts.append(t_elem.text)
        return "".join(parts)

    @staticmethod
    def _parse_run_style(r_elem) -> RunStyle:
        """从 w:r 元素中解析 Run 格式。"""
        rs = RunStyle()
        rPr = r_elem.find(qn("w:rPr"))
        if rPr is None:
            return rs

        if rPr.find(qn("w:b")) is not None:
            rs.bold = True
        if rPr.find(qn("w:i")) is not None:
            rs.italic = True
        if rPr.find(qn("w:u")) is not None:
            rs.underline = True
        if rPr.find(qn("w:strike")) is not None:
            rs.strikethrough = True
        if rPr.find(qn("w:superscript")) is not None:
            rs.superscript = True
        if rPr.find(qn("w:subscript")) is not None:
            rs.subscript = True

        # 字体
        rFonts = rPr.find(qn("w:rFonts"))
        if rFonts is not None:
            ascii_font = rFonts.get(qn("w:ascii"))
            if ascii_font:
                rs.font_name = ascii_font

        # 字号 (OOXML 使用半磅)
        sz = rPr.find(qn("w:sz"))
        if sz is not None:
            val = sz.get(qn("w:val"))
            if val:
                rs.font_size_pt = int(val) / 2

        # 颜色
        color = rPr.find(qn("w:color"))
        if color is not None:
            val = color.get(qn("w:val"))
            if val and val != "auto":
                rs.color_rgb = val

        # 高亮
        highlight = rPr.find(qn("w:highlight"))
        if highlight is not None:
            val = highlight.get(qn("w:val"))
            if val:
                rs.highlight = val

        return rs

    # ------------------------------------------------------------------
    # Table
    # ------------------------------------------------------------------

    def _parse_table(self, tbl_elem, index: int) -> Table:
        rows: list[TableRow] = []
        for tr_elem in tbl_elem.findall(qn("w:tr")):
            cells = self._parse_table_row(tr_elem)
            rows.append(TableRow(cells=cells))
        return Table(index=index, rows=rows)

    def _parse_table_row(self, tr_elem) -> list[TableCell]:
        cells: list[TableCell] = []
        for tc_elem in tr_elem.findall(qn("w:tc")):
            cell = self._parse_table_cell(tc_elem)
            cells.append(cell)
        return cells

    def _parse_table_cell(self, tc_elem) -> TableCell:
        paragraphs: list[Paragraph] = []
        for cell_index, p_elem in enumerate(tc_elem.findall(qn("w:p"))):
            para = self._parse_paragraph(p_elem, cell_index)
            paragraphs.append(para)

        # 合并单元格信息
        merge_h = 1
        merge_v = 1
        tcPr = tc_elem.find(qn("w:tcPr"))
        if tcPr is not None:
            gridSpan = tcPr.find(qn("w:gridSpan"))
            if gridSpan is not None:
                merge_h = int(gridSpan.get(qn("w:val"), "1"))
            vMerge = tcPr.find(qn("w:vMerge"))
            if vMerge is not None:
                # w:val="restart" 表示垂直合并的开始
                val = vMerge.get(qn("w:val"))
                if val != "restart":
                    merge_v = 0  # 续合并，不计入

        return TableCell(paragraphs=paragraphs, merge_horizontal=merge_h, merge_vertical=merge_v)
