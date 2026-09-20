# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""DocxAST → docx 序列化器。

将 DocxAST 转换为 python-docx Document 对象并保存为 .docx 文件。
用于 patch 应用后的文档输出。
"""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Emu, Pt

from .ast import (
    DocxAST,
    Paragraph,
    ParagraphStyle,
    Run,
    RunStyle,
    Table,
    TableCell,
    TableRow,
)

# 对齐方式映射
_ALIGNMENT_MAP: dict[str, int] = {
    "left": WD_ALIGN_PARAGRAPH.LEFT,
    "center": WD_ALIGN_PARAGRAPH.CENTER,
    "right": WD_ALIGN_PARAGRAPH.RIGHT,
    "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
}

# OOXML 对齐值
_ALIGNMENT_OOXML: dict[str, str] = {
    "left": "left",
    "center": "center",
    "right": "right",
    "justify": "both",
}


class DocxSerializer:
    """将 DocxAST 序列化为 docx 文件。"""

    def serialize(self, ast: DocxAST, output_path: str | Path) -> None:
        """将 DocxAST 序列化为 docx 文件。

        Args:
            ast: DocxAST 结构化表示
            output_path: 输出文件路径
        """
        doc = Document()
        # 清除默认空段落
        doc.element.body.clear_content()

        for node in ast.nodes:
            if isinstance(node, Paragraph):
                elem = self._create_paragraph_element(node, doc)
                doc.element.body.append(elem)
            elif isinstance(node, Table):
                elem = self._create_table_element(node, doc)
                doc.element.body.append(elem)

        doc.save(str(output_path))

    # ------------------------------------------------------------------
    # Paragraph
    # ------------------------------------------------------------------

    def _create_paragraph_element(self, para: Paragraph, doc: Document):
        """从 AST Paragraph 创建 python-docx 段落 XML 元素。"""
        p = OxmlElement("w:p")

        # 段落属性
        pPr = OxmlElement("w:pPr")
        p.append(pPr)

        # 样式名
        pStyle = OxmlElement("w:pStyle")
        pStyle.set(qn("w:val"), para.style.style_name)
        pPr.append(pStyle)

        # 对齐
        if para.style.alignment and para.style.alignment in _ALIGNMENT_OOXML:
            jc = OxmlElement("w:jc")
            jc.set(qn("w:val"), _ALIGNMENT_OOXML[para.style.alignment])
            pPr.append(jc)

        # 缩进
        indent_attrs: dict[str, str] = {}
        if para.style.indent_left_pt is not None:
            indent_attrs[qn("w:left")] = str(int(Pt(para.style.indent_left_pt)))
        if para.style.indent_first_line_pt is not None:
            if para.style.indent_first_line_pt >= 0:
                indent_attrs[qn("w:firstLine")] = str(int(Pt(para.style.indent_first_line_pt)))
            else:
                indent_attrs[qn("w:hanging")] = str(int(Pt(-para.style.indent_first_line_pt)))
        if indent_attrs:
            ind = OxmlElement("w:ind")
            for k, v in indent_attrs.items():
                ind.set(k, v)
            pPr.append(ind)

        # 间距
        spacing_attrs: dict[str, str] = {}
        if para.style.spacing_before_pt is not None:
            spacing_attrs[qn("w:before")] = str(int(Pt(para.style.spacing_before_pt)))
        if para.style.spacing_after_pt is not None:
            spacing_attrs[qn("w:after")] = str(int(Pt(para.style.spacing_after_pt)))
        if para.style.line_spacing is not None:
            spacing_attrs[qn("w:line")] = str(int(para.style.line_spacing * 240))
            spacing_attrs[qn("w:lineRule")] = "auto"
        if spacing_attrs:
            spacing = OxmlElement("w:spacing")
            for k, v in spacing_attrs.items():
                spacing.set(k, v)
            pPr.append(spacing)

        # 编号
        if para.style.numbering_id is not None:
            numPr = OxmlElement("w:numPr")
            numId = OxmlElement("w:numId")
            numId.set(qn("w:val"), para.style.numbering_id)
            numPr.append(numId)
            ilvl = OxmlElement("w:ilvl")
            ilvl.set(qn("w:val"), str(para.style.numbering_level or 0))
            numPr.append(ilvl)
            pPr.append(numPr)

        # Runs
        for run in para.runs:
            r = self._create_run_element(run)
            p.append(r)

        return p

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def _create_run_element(self, run: Run):
        """从 AST Run 创建 python-docx Run XML 元素。"""
        r = OxmlElement("w:r")
        s = run.style

        # 如果有超链接，需要包裹在 w:hyperlink 中（由调用者处理）
        # 这里只创建 run 元素

        # Run 属性
        rPr = OxmlElement("w:rPr")
        r.append(rPr)

        if s.bold:
            rPr.append(OxmlElement("w:b"))
        if s.italic:
            rPr.append(OxmlElement("w:i"))
        if s.underline:
            u = OxmlElement("w:u")
            u.set(qn("w:val"), "single")
            rPr.append(u)
        if s.strikethrough:
            rPr.append(OxmlElement("w:strike"))
        if s.superscript:
            rPr.append(OxmlElement("w:superscript"))
        if s.subscript:
            rPr.append(OxmlElement("w:subscript"))

        if s.font_name:
            rFonts = OxmlElement("w:rFonts")
            rFonts.set(qn("w:ascii"), s.font_name)
            rFonts.set(qn("w:hAnsi"), s.font_name)
            rFonts.set(qn("w:eastAsia"), s.font_name)
            rPr.append(rFonts)

        if s.font_size_pt is not None:
            sz = OxmlElement("w:sz")
            sz.set(qn("w:val"), str(int(s.font_size_pt * 2)))
            rPr.append(sz)
            szCs = OxmlElement("w:szCs")
            szCs.set(qn("w:val"), str(int(s.font_size_pt * 2)))
            rPr.append(szCs)

        if s.color_rgb:
            color = OxmlElement("w:color")
            color.set(qn("w:val"), s.color_rgb)
            rPr.append(color)

        if s.highlight:
            highlight = OxmlElement("w:highlight")
            highlight.set(qn("w:val"), s.highlight)
            rPr.append(highlight)

        # 文本内容
        t = OxmlElement("w:t")
        t.text = run.text
        t.set(qn("xml:space"), "preserve")
        r.append(t)

        return r

    # ------------------------------------------------------------------
    # Table
    # ------------------------------------------------------------------

    def _create_table_element(self, table: Table, doc: Document):
        """从 AST Table 创建 python-docx 表格 XML 元素。"""
        tbl = OxmlElement("w:tbl")

        # 表格属性
        tblPr = OxmlElement("w:tblPr")
        tbl.append(tblPr)

        # 表格样式
        tblStyle = OxmlElement("w:tblStyle")
        tblStyle.set(qn("w:val"), "TableGrid")
        tblPr.append(tblStyle)

        # 边框
        borders = OxmlElement("w:tblBorders")
        for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
            border = OxmlElement(f"w:{edge}")
            border.set(qn("w:val"), "single")
            border.set(qn("w:sz"), "4")
            border.set(qn("w:space"), "0")
            border.set(qn("w:color"), "000000")
            borders.append(border)
        tblPr.append(borders)

        # 表格宽度 (100%)
        tblW = OxmlElement("w:tblW")
        tblW.set(qn("w:w"), "5000")
        tblW.set(qn("w:type"), "pct")
        tblPr.append(tblW)

        # 行和单元格
        for row in table.rows:
            tr = self._create_table_row_element(row)
            tbl.append(tr)

        return tbl

    def _create_table_row_element(self, row: TableRow):
        """从 AST TableRow 创建表格行 XML 元素。"""
        tr = OxmlElement("w:tr")
        for cell in row.cells:
            tc = self._create_table_cell_element(cell)
            tr.append(tc)
        return tr

    def _create_table_cell_element(self, cell: TableCell):
        """从 AST TableCell 创建表格单元格 XML 元素。"""
        tc = OxmlElement("w:tc")

        # 单元格属性
        tcPr = OxmlElement("w:tcPr")
        if cell.merge_horizontal > 1:
            gridSpan = OxmlElement("w:gridSpan")
            gridSpan.set(qn("w:val"), str(cell.merge_horizontal))
            tcPr.append(gridSpan)
        if cell.merge_vertical == 0:
            vMerge = OxmlElement("w:vMerge")
            tcPr.append(vMerge)
        elif cell.merge_vertical > 1:
            vMerge = OxmlElement("w:vMerge")
            vMerge.set(qn("w:val"), "restart")
            tcPr.append(vMerge)
        tc.append(tcPr)

        for para in cell.paragraphs:
            p = self._create_paragraph_element(para, doc=None)
            tc.append(p)

        return tc
