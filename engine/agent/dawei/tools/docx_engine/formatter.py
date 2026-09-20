# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""AST → LLM 友好文本格式化器。

将 DocxAST 转换为带锚点的结构化文本，供 LLM 阅读和编辑。
格式: [序号] (样式名) 文本内容
"""

from __future__ import annotations

from .ast import DocxAST, Paragraph, Run, RunStyle, Table


class DocxASTFormatter:
    """将 AST 格式化为 LLM 可读的带锚点文本。"""

    def format(
        self,
        ast: DocxAST,
        detail: str = "run",
        start_paragraph: int | None = None,
        end_paragraph: int | None = None,
    ) -> str:
        """格式化 DocxAST 为带锚点的文本。

        Args:
            ast: DocxAST 结构化表示
            detail: 详细级别
                - "paragraph": 仅段落文本和样式
                - "run": 包含行内格式标记 (**bold** *italic*)
                - "full": 完整信息，包含所有格式属性
            start_paragraph: 起始段落序号（0-based），None 则从开头
            end_paragraph: 结束段落序号（0-based），None 则到末尾

        Returns:
            带锚点的结构化文本
        """
        lines: list[str] = []
        for node in ast.nodes:
            if isinstance(node, Paragraph):
                idx = node.index
                if start_paragraph is not None and idx < start_paragraph:
                    continue
                if end_paragraph is not None and idx > end_paragraph:
                    continue
                lines.append(self._format_paragraph(node, detail))
            elif isinstance(node, Table):
                idx = node.index
                if start_paragraph is not None and idx < start_paragraph:
                    continue
                if end_paragraph is not None and idx > end_paragraph:
                    continue
                lines.append(self._format_table(node, detail))
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Paragraph
    # ------------------------------------------------------------------

    def _format_paragraph(self, para: Paragraph, detail: str) -> str:
        anchor = f"[{para.index}] ({para.style.style_name})"
        if para.is_empty:
            return f"{anchor} "

        if detail == "paragraph":
            return f"{anchor} {para.text}"
        if detail == "run":
            text = self._format_runs_inline(para.runs)
            return f"{anchor} {text}"
        # full
        text = self._format_runs_full(para.runs)
        return f"{anchor} {text}"

    # ------------------------------------------------------------------
    # Run inline formatting (detail="run")
    # ------------------------------------------------------------------

    @staticmethod
    def _format_runs_inline(runs: list[Run]) -> str:
        """将 Run 列表格式化为带 Markdown 行内标记的文本。"""
        parts: list[str] = []
        for run in runs:
            text = run.text
            if not text:
                continue
            s = run.style
            # Markdown 格式标记
            if s.strikethrough:
                text = f"~~{text}~~"
            if s.italic:
                text = f"*{text}*"
            elif s.underline:
                text = f"_{text}_"
            if s.bold:
                text = f"**{text}**"
            if s.hyperlink_url:
                text = f"[{text}]({s.hyperlink_url})"
            parts.append(text)
        return "".join(parts)

    # ------------------------------------------------------------------
    # Run full formatting (detail="full")
    # ------------------------------------------------------------------

    @staticmethod
    def _format_runs_full(runs: list[Run]) -> str:
        """将 Run 列表格式化为包含完整格式属性的文本。"""
        parts: list[str] = []
        for run in runs:
            text = run.text
            if not text:
                continue
            s = run.style
            attrs: list[str] = []
            if s.bold:
                attrs.append("bold")
            if s.italic:
                attrs.append("italic")
            if s.underline:
                attrs.append("underline")
            if s.strikethrough:
                attrs.append("strike")
            if s.font_name:
                attrs.append(f"font={s.font_name}")
            if s.font_size_pt:
                attrs.append(f"size={s.font_size_pt}pt")
            if s.color_rgb:
                attrs.append(f"color={s.color_rgb}")
            if s.highlight:
                attrs.append(f"hl={s.highlight}")
            if s.superscript:
                attrs.append("super")
            if s.subscript:
                attrs.append("sub")
            if s.hyperlink_url:
                attrs.append(f"url={s.hyperlink_url}")

            if attrs:
                parts.append(f"<{'|'.join(attrs)}>{text}")
            else:
                parts.append(text)
        return "".join(parts)

    # ------------------------------------------------------------------
    # Table
    # ------------------------------------------------------------------

    def _format_table(self, table: Table, detail: str) -> str:
        lines: list[str] = [f"[{table.index}] (Table)"]

        if not table.rows:
            return lines[0]

        # 计算列数
        max_cols = max(len(row.cells) for row in table.rows)

        # 表头
        header_cells = table.rows[0].cells if table.rows else []
        header = "| " + " | ".join(self._format_cell_text(c, detail) for c in header_cells) + " |"
        lines.append(header)

        # 分隔线
        lines.append("| " + " | ".join(["------"] * max_cols) + " |")

        # 数据行
        for row in table.rows[1:]:
            row_text = "| " + " | ".join(self._format_cell_text(c, detail) for c in row.cells) + " |"
            lines.append(row_text)

        return "\n".join(lines)

    def _format_cell_text(self, cell, detail: str) -> str:
        """格式化表格单元格文本。"""
        if not cell.paragraphs:
            return ""
        # 合并所有段落文本
        parts: list[str] = []
        for para in cell.paragraphs:
            if para.is_empty:
                continue
            if detail in ("paragraph",):
                parts.append(para.text)
            elif detail == "run":
                parts.append(self._format_runs_inline(para.runs))
            else:
                parts.append(self._format_runs_full(para.runs))
        return " ".join(parts)
