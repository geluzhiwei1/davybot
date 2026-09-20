# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Markdown Renderer Widget

Rich markdown rendering with syntax highlighting for the TUI.
"""

import re

from textual.widgets import Markdown


class ChatMarkdown(Markdown):
    """Enhanced Markdown renderer for chat messages"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.show_line_numbers = True
        self.code_theme = "monokai"

    def on_mount(self) -> None:
        """Initialize after mount"""
        # Set default styling
        self.styles.background = "transparent"

    def process_markdown(self, content: str) -> str:
        """Pre-process markdown content

        Args:
            content: Raw markdown content

        Returns:
            Processed markdown

        """
        # Escape HTML tags (security)
        content = self._escape_html(content)

        # Enhance code blocks with language hints
        content = self._enhance_code_blocks(content)

        # Add emphasis to important keywords
        return self._highlight_keywords(content)

    def _escape_html(self, content: str) -> str:
        """Escape HTML tags

        Args:
            content: Content to escape

        Returns:
            Escaped content

        """
        # Replace HTML tags with safe alternatives
        html_escape = {
            "<": "&lt;",
            ">": "&gt;",
            "&": "&amp;",
        }
        for char, replacement in html_escape.items():
            content = content.replace(char, replacement)

        return content

    def _enhance_code_blocks(self, content: str) -> str:
        """Enhance code blocks with language hints

        Args:
            content: Content with code blocks

        Returns:
            Enhanced content

        """
        # Match code blocks with language hints
        pattern = r"```(\w+)?\n(.*?)\n```"

        def replace_code_block(match):
            lang = match.group(1) or ""
            code = match.group(2)
            return f"\n```{lang}\n{code}\n```\n"

        return re.sub(pattern, replace_code_block, content, flags=re.DOTALL)

    def _highlight_keywords(self, content: str) -> str:
        """Highlight important keywords

        Args:
            content: Content to process

        Returns:
            Highlighted content

        """
        keywords = [
            "错误",
            "Error",
            "错误：",
            "Error:",
            "警告",
            "Warning",
            "警告：",
            "Warning:",
            "成功",
            "Success",
            "成功：",
            "Success:",
            "注意",
            "Note",
            "注意：",
            "Note:",
            "提示",
            "Tip",
            "提示：",
            "Tip:",
        ]

        for keyword in keywords:
            # Bold important keywords
            content = content.replace(keyword, f"**{keyword}**")

        return content

    def update_content(self, content: str) -> None:
        """Update markdown content

        Args:
            content: New markdown content

        """
        processed = self.process_markdown(content)
        self.update(processed)
