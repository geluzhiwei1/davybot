# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Document parsers for different file types"""

from dawei.knowledge.parsers.base import BaseParser
from dawei.knowledge.parsers.markdown_parser import MarkdownParser

__all__ = [
    "BaseParser",
    "MarkdownParser",
]
