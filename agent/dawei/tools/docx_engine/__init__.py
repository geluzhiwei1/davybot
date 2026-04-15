# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""docx_engine — 结构化 docx 解析、diff、patch 与修订追踪。"""

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
from .diff_parser import DocxDiffParser
from .differ import DiffOp, DiffType, DocxDiffer, DocxDiffResult, RunDiffOp
from .formatter import DocxASTFormatter
from .parser import DocxParser
from .patcher import DocxPatcher
from .revision import RevisionManager
from .serializer import DocxSerializer

__all__ = [
    # AST models
    "DocxAST",
    "DocxMetadata",
    "Paragraph",
    "ParagraphStyle",
    "Run",
    "RunStyle",
    "Table",
    "TableCell",
    "TableRow",
    # Diff
    "DiffOp",
    "DiffType",
    "DocxDiffer",
    "DocxDiffResult",
    "RunDiffOp",
    # Parser / Serializer / Formatter
    "DocxParser",
    "DocxSerializer",
    "DocxASTFormatter",
    "DocxDiffParser",
    "DocxPatcher",
    # Revision
    "RevisionManager",
]
