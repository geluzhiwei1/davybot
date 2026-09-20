# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Document parsers for different file types"""

from dawei.knowledge.parsers.base import BaseParser
from dawei.knowledge.parsers.docx_parser import DocxParser
from dawei.knowledge.parsers.factory import SUPPORTED_EXTENSIONS, get_parser
from dawei.knowledge.parsers.markdown_parser import MarkdownParser
from dawei.knowledge.parsers.pdf_parser import PdfParser
from dawei.knowledge.parsers.txt_parser import TxtParser

__all__ = [
    "BaseParser",
    "MarkdownParser",
    "PdfParser",
    "DocxParser",
    "TxtParser",
    "SUPPORTED_EXTENSIONS",
    "get_parser",
]
