# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Skill-Aware Input Box Widget

Enhanced input widget with @ directive syntax highlighting.
Supports visual distinction between:
- @skill:xxx - Special skill directives (blue/purple)
- @file.py - File references (green)
- @folder/ - Folder references (yellow)
"""

import re

from rich.console import RenderableType
from rich.text import Text
from textual.message import Message
from textual.widgets import Input


class SkillAwareInputBox(Input):
    """User input widget with @ directive syntax highlighting"""

    class MessageSubmitted(Message):
        """Message emitted when user submits input"""

        def __init__(self, message: str):
            super().__init__()
            self.message = message

    # Syntax highlighting patterns
    PATTERNS = [
        (r"@skill:\w+", "bold blue", "skill"),  # @skill:xxx
        (
            r"@\w+\.(py|js|ts|vue|md|txt|json|yaml|yml)",
            "bold green",
            "file",
        ),  # @file.py
        (r"@\w+/", "bold yellow", "folder"),  # @folder/
        (r"@\w+", "bold cyan", "other"),  # @other
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def render(self) -> RenderableType:
        """Render the input with syntax highlighting

        Overrides the default render to apply syntax highlighting
        to @ directives while preserving the cursor position.
        """
        # Get current value
        value = self.value

        # If empty, just show placeholder
        if not value:
            return super().render()

        # Apply syntax highlighting
        return self._apply_highlighting(value)

    def _apply_highlighting(self, text: str) -> Text:
        """Apply syntax highlighting to @ directives

        Args:
            text: Input text

        Returns:
            Rich Text object with highlighting applied

        """
        result = Text()

        # Track position in text
        pos = 0

        # Find all @ directives
        at_pattern = re.compile(r"@\w+[:/\.]?\w*")

        for match in at_pattern.finditer(text):
            # Add text before the match
            if match.start() > pos:
                result.append(text[pos : match.start()])

            # Get the matched directive
            directive = match.group()

            # Apply appropriate styling
            styled = self._get_styled_directive(directive)
            result.append(styled)

            pos = match.end()

        # Add remaining text
        if pos < len(text):
            result.append(text[pos:])

        return result

    def _get_styled_directive(self, directive: str) -> Text:
        """Get styled directive based on type

        Args:
            directive: The @ directive string

        Returns:
            Rich Text object with appropriate style

        """
        # Check each pattern
        for pattern, style, _type_name in self.PATTERNS:
            if re.match(pattern, directive):
                return Text(directive, style=style)

        # Default styling
        return Text(directive, style="bold cyan")

    def _detect_directive_type(self, directive: str) -> str:
        """Detect the type of @ directive

        Args:
            directive: The @ directive (without @)

        Returns:
            Type string: 'skill', 'file', 'folder', 'other'

        """
        if directive.startswith("skill:"):
            return "skill"
        if directive.endswith("/"):
            return "folder"
        if "." in directive:
            return "file"
        return "other"

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle input submission

        Args:
            event: Input submitted event

        """
        message = event.value.strip()

        if not message:
            return

        # Clear input
        self.value = ""

        # Emit message to app
        self.post_message(self.MessageSubmitted(message))


# Convenience alias
InputBox = SkillAwareInputBox
