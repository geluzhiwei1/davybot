# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""修订追踪（Track Changes）。

通过 python-docx 的 oxml 层直接操作 OOXML，在 docx 中写入 Word 原生修订标记。
生成的 docx 在 Word/WPS 中打开时会显示标准的修订痕迹。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from .ast import (
    DocxAST,
    Paragraph,
    Run,
    RunStyle,
)
from .differ import DiffOp, DiffType
from .parser import DocxParser

logger = logging.getLogger(__name__)

_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


class RevisionManager:
    """在 python-docx Document 中生成 Word 原生修订标记。"""

    def __init__(self, author: str = "Dawei"):
        self.author = author
        self._revision_id = 0

    def _next_id(self) -> str:
        """递增修订 ID。"""
        self._revision_id += 1
        return str(self._revision_id)

    @staticmethod
    def _current_datetime() -> str:
        """ISO 8601 时间戳。"""
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _scan_max_revision_id(self, doc: Document) -> None:
        """扫描文档中已有的最大修订 ID，避免冲突。"""
        max_id = 0
        for elem in doc.element.iter():
            if "}" in elem.tag:
                tag = elem.tag.split("}")[-1]
            else:
                tag = elem.tag
            if tag in ("ins", "del", "rPrChange", "pPrChange", "sectPrChange", "tblPrChange", "trPrChange", "tcPrChange"):
                rid = elem.get(qn("w:id"))
                if rid:
                    try:
                        max_id = max(max_id, int(rid))
                    except ValueError:
                        pass
        self._revision_id = max_id

    # ------------------------------------------------------------------
    # 启用修订模式
    # ------------------------------------------------------------------

    @staticmethod
    def enable_track_changes(doc: Document) -> None:
        """在文档设置中启用修订追踪。"""
        settings = doc.settings.element
        # 检查是否已启用
        existing = settings.find(qn("w:trackRevisions"))
        if existing is None:
            track_revisions = OxmlElement("w:trackRevisions")
            settings.append(track_revisions)

    # ------------------------------------------------------------------
    # 标记插入
    # ------------------------------------------------------------------

    def mark_insertion(self, parent_elem, runs: list[Run]) -> None:
        """在父元素中插入带修订标记的 runs。"""
        ins = OxmlElement("w:ins")
        ins.set(qn("w:id"), self._next_id())
        ins.set(qn("w:author"), self.author)
        ins.set(qn("w:date"), self._current_datetime())

        for run in runs:
            r = self._create_revision_run(run)
            ins.append(r)

        parent_elem.append(ins)

    # ------------------------------------------------------------------
    # 标记删除
    # ------------------------------------------------------------------

    def mark_deletion(self, parent_elem, runs: list[Run]) -> None:
        """标记 runs 为删除。"""
        del_elem = OxmlElement("w:del")
        del_elem.set(qn("w:id"), self._next_id())
        del_elem.set(qn("w:author"), self.author)
        del_elem.set(qn("w:date"), self._current_datetime())

        for run in runs:
            r = OxmlElement("w:r")
            # 保留原始格式
            self._apply_run_format(r, run.style)
            del_text = OxmlElement("w:delText")
            del_text.text = run.text
            del_text.set(qn("xml:space"), "preserve")
            r.append(del_text)
            del_elem.append(r)

        parent_elem.append(del_elem)

    # ------------------------------------------------------------------
    # 标记格式变更
    # ------------------------------------------------------------------

    def mark_run_format_change(self, run_elem, old_style: RunStyle) -> None:
        """在 Run 中记录格式变更（旧格式作为修订记录）。"""
        rPr = run_elem.find(qn("w:rPr"))
        if rPr is None:
            rPr = OxmlElement("w:rPr")
            run_elem.insert(0, rPr)

        rPrChange = OxmlElement("w:rPrChange")
        rPrChange.set(qn("w:id"), self._next_id())
        rPrChange.set(qn("w:author"), self.author)
        rPrChange.set(qn("w:date"), self._current_datetime())

        old_rPr = OxmlElement("w:rPr")
        if not old_style.bold:
            pass  # 旧格式无加粗
        if old_style.font_name:
            rFonts = OxmlElement("w:rFonts")
            rFonts.set(qn("w:ascii"), old_style.font_name)
            rFonts.set(qn("w:hAnsi"), old_style.font_name)
            old_rPr.append(rFonts)
        if old_style.font_size_pt:
            sz = OxmlElement("w:sz")
            sz.set(qn("w:val"), str(int(old_style.font_size_pt * 2)))
            old_rPr.append(sz)

        rPrChange.append(old_rPr)
        rPr.append(rPrChange)

    # ------------------------------------------------------------------
    # 标记段落属性变更
    # ------------------------------------------------------------------

    def mark_paragraph_property_change(self, para_elem, old_style_name: str) -> None:
        """记录段落样式变更。"""
        pPr = para_elem.find(qn("w:pPr"))
        if pPr is None:
            return

        pPrChange = OxmlElement("w:pPrChange")
        pPrChange.set(qn("w:id"), self._next_id())
        pPrChange.set(qn("w:author"), self.author)
        pPrChange.set(qn("w:date"), self._current_datetime())

        old_pPr = OxmlElement("w:pPr")
        pStyle = OxmlElement("w:pStyle")
        pStyle.set(qn("w:val"), old_style_name)
        old_pPr.append(pStyle)

        pPrChange.append(old_pPr)
        pPr.append(pPrChange)

    # ------------------------------------------------------------------
    # 与 DiffOp 集成
    # ------------------------------------------------------------------

    def apply_revisions(
        self,
        doc: Document,
        ops: list[DiffOp],
        ast: DocxAST,
    ) -> None:
        """将 DiffOp 转换为 Word 修订标记。"""
        self._scan_max_revision_id(doc)
        self.enable_track_changes(doc)
        body = doc.element.body

        offset = 0
        for op in ops:
            actual_pos = op.position + offset

            match op.type:
                case DiffType.INSERT:
                    if op.node and isinstance(op.node, Paragraph):
                        ref_elem = body[actual_pos] if actual_pos < len(body) else None
                        p = OxmlElement("w:p")
                        # 设置段落样式
                        pPr = OxmlElement("w:pPr")
                        pStyle = OxmlElement("w:pStyle")
                        pStyle.set(qn("w:val"), op.node.style.style_name)
                        pPr.append(pStyle)
                        p.append(pPr)
                        # 插入内容
                        self.mark_insertion(p, op.node.runs)
                        if ref_elem is not None:
                            ref_elem.addprevious(p)
                        else:
                            body.append(p)
                        offset += 1

                case DiffType.DELETE:
                    if actual_pos < len(body):
                        para = body[actual_pos]
                        runs = self._extract_runs_from_para(para)
                        if runs:
                            self.mark_deletion(para, runs)
                        offset -= 1

                case DiffType.MODIFY_RUNS:
                    if actual_pos < len(body) and op.run_diffs:
                        para = body[actual_pos]
                        self._apply_run_revisions(para, op.run_diffs)

                case DiffType.MODIFY_STYLE:
                    if actual_pos < len(body) and op.old_style:
                        para = body[actual_pos]
                        self.mark_paragraph_property_change(para, op.old_style.style_name)
                        # 同时应用新样式
                        pPr = para.find(qn("w:pPr"))
                        if pPr is not None and op.new_style:
                            pStyle = pPr.find(qn("w:pStyle"))
                            if pStyle is not None:
                                pStyle.set(qn("w:val"), op.new_style.style_name)

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    def _create_revision_run(self, run: Run):
        """创建带格式的修订 run 元素。"""
        r = OxmlElement("w:r")
        self._apply_run_format(r, run.style)
        t = OxmlElement("w:t")
        t.text = run.text
        t.set(qn("xml:space"), "preserve")
        r.append(t)
        return r

    @staticmethod
    def _apply_run_format(r_elem, style: RunStyle) -> None:
        """将 RunStyle 应用到 w:r XML 元素。"""
        if style.bold or style.italic or style.underline or style.strikethrough or style.font_name or style.font_size_pt or style.color_rgb:
            rPr = OxmlElement("w:rPr")
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
            if style.font_name:
                rFonts = OxmlElement("w:rFonts")
                rFonts.set(qn("w:ascii"), style.font_name)
                rFonts.set(qn("w:hAnsi"), style.font_name)
                rPr.append(rFonts)
            if style.font_size_pt:
                sz = OxmlElement("w:sz")
                sz.set(qn("w:val"), str(int(style.font_size_pt * 2)))
                rPr.append(sz)
            if style.color_rgb:
                color = OxmlElement("w:color")
                color.set(qn("w:val"), style.color_rgb)
                rPr.append(color)
            r_elem.append(rPr)

    @staticmethod
    def _extract_runs_from_para(para_elem) -> list[Run]:
        """从段落 XML 元素中提取 Run 列表。"""
        runs: list[Run] = []
        for r_elem in para_elem.findall(qn("w:r")):
            parts: list[str] = []
            for t_elem in r_elem.findall(qn("w:t")):
                if t_elem.text:
                    parts.append(t_elem.text)
            text = "".join(parts)
            style = DocxParser._parse_run_style(r_elem)
            if text:
                runs.append(Run(text=text, style=style))
        return runs

    def _apply_run_revisions(self, para_elem, run_diffs) -> None:
        """对段落应用 Run 级修订标记。"""
        for rd in run_diffs:
            if rd.type == "insert" and rd.run:
                self.mark_insertion(para_elem, [rd.run])
            elif rd.type == "delete" and rd.old_run:
                self.mark_deletion(para_elem, [rd.old_run])
            elif rd.type == "modify" and rd.old_run and rd.run:
                # 删除旧内容，插入新内容
                self.mark_deletion(para_elem, [rd.old_run])
                self.mark_insertion(para_elem, [rd.run])
