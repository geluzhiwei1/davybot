# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""DocxAST 数据模型 — docx 文件的结构化中间表示。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

# ---------------------------------------------------------------------------
# Run 级别
# ---------------------------------------------------------------------------


@dataclass
class RunStyle:
    """Run 级别格式（一段内可有多种格式混排）。"""

    bold: bool = False
    italic: bool = False
    underline: bool = False
    strikethrough: bool = False
    font_name: str | None = None
    font_size_pt: int | None = None
    color_rgb: str | None = None
    highlight: str | None = None
    superscript: bool = False
    subscript: bool = False
    hyperlink_url: str | None = None

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, RunStyle):
            return NotImplemented
        return (
            self.bold == other.bold
            and self.italic == other.italic
            and self.underline == other.underline
            and self.strikethrough == other.strikethrough
            and self.font_name == other.font_name
            and self.font_size_pt == other.font_size_pt
            and self.color_rgb == other.color_rgb
            and self.highlight == other.highlight
            and self.superscript == other.superscript
            and self.subscript == other.subscript
            and self.hyperlink_url == other.hyperlink_url
        )

    def __hash__(self) -> int:
        return hash(
            (
                self.bold,
                self.italic,
                self.underline,
                self.strikethrough,
                self.font_name,
                self.font_size_pt,
                self.color_rgb,
                self.highlight,
                self.superscript,
                self.subscript,
                self.hyperlink_url,
            )
        )


@dataclass
class Run:
    """文本 run：一个连续同格式的文本片段。"""

    text: str
    style: RunStyle = field(default_factory=RunStyle)


# ---------------------------------------------------------------------------
# 段落级别
# ---------------------------------------------------------------------------


@dataclass
class ParagraphStyle:
    """段落级格式。"""

    style_name: str = "Normal"
    alignment: str | None = None  # "left" | "center" | "right" | "justify"
    indent_left_pt: float | None = None
    indent_first_line_pt: float | None = None
    spacing_before_pt: float | None = None
    spacing_after_pt: float | None = None
    line_spacing: float | None = None
    numbering_id: str | None = None
    numbering_level: int | None = None

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ParagraphStyle):
            return NotImplemented
        return (
            self.style_name == other.style_name
            and self.alignment == other.alignment
            and self.indent_left_pt == other.indent_left_pt
            and self.indent_first_line_pt == other.indent_first_line_pt
            and self.spacing_before_pt == other.spacing_before_pt
            and self.spacing_after_pt == other.spacing_after_pt
            and self.line_spacing == other.line_spacing
            and self.numbering_id == other.numbering_id
            and self.numbering_level == other.numbering_level
        )

    def __hash__(self) -> int:
        return hash(
            (
                self.style_name,
                self.alignment,
                self.indent_left_pt,
                self.indent_first_line_pt,
                self.spacing_before_pt,
                self.spacing_after_pt,
                self.line_spacing,
                self.numbering_id,
                self.numbering_level,
            )
        )


@dataclass
class Paragraph:
    """段落节点。"""

    index: int
    style: ParagraphStyle = field(default_factory=ParagraphStyle)
    runs: list[Run] = field(default_factory=list)

    @property
    def text(self) -> str:
        """段落纯文本（拼接所有 run）。"""
        return "".join(r.text for r in self.runs)

    @property
    def is_empty(self) -> bool:
        return not self.text.strip()


# ---------------------------------------------------------------------------
# 表格
# ---------------------------------------------------------------------------


@dataclass
class TableCell:
    """表格单元格。"""

    paragraphs: list[Paragraph] = field(default_factory=list)
    merge_horizontal: int = 1
    merge_vertical: int = 1


@dataclass
class TableRow:
    """表格行。"""

    cells: list[TableCell] = field(default_factory=list)


@dataclass
class Table:
    """表格节点。"""

    index: int
    rows: list[TableRow] = field(default_factory=list)

    @property
    def text(self) -> str:
        """表格纯文本（用于相似度比较）。"""
        parts: list[str] = []
        for row in self.rows:
            for cell in row.cells:
                for para in cell.paragraphs:
                    parts.append(para.text)
        return " ".join(parts)


# ---------------------------------------------------------------------------
# 文档
# ---------------------------------------------------------------------------


@dataclass
class DocxMetadata:
    """文档元数据。"""

    author: str | None = None
    title: str | None = None
    created: str | None = None
    modified: str | None = None
    core_styles: dict[str, str] = field(default_factory=dict)


@dataclass
class DocxAST:
    """完整文档的结构化表示。"""

    nodes: list[Paragraph | Table] = field(default_factory=list)
    metadata: DocxMetadata = field(default_factory=DocxMetadata)

    @property
    def paragraphs(self) -> list[Paragraph]:
        return [n for n in self.nodes if isinstance(n, Paragraph)]

    @property
    def tables(self) -> list[Table]:
        return [n for n in self.nodes if isinstance(n, Table)]


# 类型别名
Node = Paragraph | Table
