# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""ThinkingPanel Widget

Displays Agent's thinking process and reasoning.
"""

from textual.reactive import reactive
from textual.widgets import Static

from dawei.tui.i18n import _


class ThinkingPanel(Static):
    """Thinking process display widget"""

    thinking_content = reactive("")

    def __init__(self, max_lines: int = 10, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_lines = max_lines
        self._thinking_history: list[str] = []

    def watch_thinking_content(self, _old_content: str, _new_content: str) -> None:
        """Update display when thinking content changes

        Args:
            old_content: Old content
            new_content: New content

        """
        self.update_display()

    def add_thinking(self, content: str) -> None:
        """Add thinking content

        Args:
            content: Thinking text to add

        """
        self._thinking_history.append(content)

        # Limit history
        if len(self._thinking_history) > self.max_lines:
            self._thinking_history = self._thinking_history[-self.max_lines :]

        self.thinking_content = "\n".join(self._thinking_history)

    def clear_thinking(self) -> None:
        """Clear thinking history"""
        self._thinking_history.clear()
        self.thinking_content = ""

    def update_display(self) -> None:
        """Update the display"""
        if not self.thinking_content:
            self.update(f"[dim]{_('Thinking...')}[/dim]")
        else:
            # Show last N lines
            lines = self.thinking_content.split("\n")
            if len(lines) > self.max_lines:
                lines = lines[-self.max_lines :]
                display_content = "...\n" + "\n".join(lines)
            else:
                display_content = self.thinking_content

            self.update(f"[bold cyan]{_('Thinking:')}[/bold cyan]\n{display_content}")
