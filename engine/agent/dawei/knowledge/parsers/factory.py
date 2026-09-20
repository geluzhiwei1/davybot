# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Parser factory — dispatch by file extension."""

from pathlib import Path

from dawei.knowledge.parsers.base import BaseParser
from dawei.knowledge.parsers.docx_parser import DocxParser
from dawei.knowledge.parsers.markdown_parser import MarkdownParser
from dawei.knowledge.parsers.pdf_parser import PdfParser
from dawei.knowledge.parsers.txt_parser import TxtParser

# Extensions accepted by the knowledge-base ingestion pipeline.
# Keep in sync with the frontend upload `accept` attribute.
SUPPORTED_EXTENSIONS: set[str] = {".md", ".markdown", ".pdf", ".docx", ".txt", ".text"}


def get_parser(file_path: str | Path) -> BaseParser:
    """Return a parser instance matching the file's extension.

    Raises:
        ValueError: if the extension is not supported.
    """
    ext = Path(file_path).suffix.lower()
    if ext in (".md", ".markdown"):
        return MarkdownParser()
    if ext == ".pdf":
        return PdfParser()
    if ext == ".docx":
        return DocxParser()
    if ext in (".txt", ".text"):
        return TxtParser()
    raise ValueError(
        f"Unsupported file type: {ext}. Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
    )
