# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""ToolPanel Widget

Displays tool execution information.
"""

from textual.reactive import reactive
from textual.widgets import Static

from dawei.tui.i18n import _


class ToolPanel(Static):
    """Tool execution display widget"""

    tool_info = reactive("")

    def __init__(self, max_lines: int = 5, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_lines = max_lines
        self._tool_history: list[str] = []
        self._current_tool: str = ""

    def watch_tool_info(self, _old_info: str, _new_info: str) -> None:
        """Update display when tool info changes

        Args:
            old_info: Old info
            new_info: New info

        """
        self.update_display()

    def start_tool(self, tool_name: str, params: dict | None = None) -> None:
        """Start tool execution

        Args:
            tool_name: Name of tool being executed
            params: Tool parameters (optional)

        """
        params_str = ""
        if params:
            # Show simplified params
            params_str = f"\n  {_('Params:')} {str(params)[:100]}..."

        self._current_tool = f"[bold yellow]→[/bold yellow] {tool_name}{params_str}"
        self.update_display()

    def complete_tool(self, tool_name: str, success: bool = True) -> None:
        """Mark tool execution as complete

        Args:
            tool_name: Name of tool that completed
            success: Whether tool execution succeeded

        """
        status = "[bold green]✓[/bold green]" if success else "[bold red]✗[/bold red]"
        self._current_tool = f"{status} {tool_name}"

        # Add to history
        self._tool_history.append(self._current_tool)

        # Limit history
        if len(self._tool_history) > self.max_lines:
            self._tool_history = self._tool_history[-self.max_lines :]

        self._current_tool = ""
        self.update_display()

    def add_tool_info(self, info: str) -> None:
        """Add tool information

        Args:
            info: Tool info text

        """
        self._tool_history.append(info)

        # Limit history
        if len(self._tool_history) > self.max_lines:
            self._tool_history = self._tool_history[-self.max_lines :]

        self.update_display()

    def clear_tools(self) -> None:
        """Clear tool history"""
        self._tool_history.clear()
        self._current_tool = ""
        self.update_display()

    def update_display(self) -> None:
        """Update the display"""
        lines = []

        # Add current tool if any
        if self._current_tool:
            lines.append(self._current_tool)

        # Add history
        if self._tool_history:
            lines.extend(self._tool_history[-self.max_lines :])

        if not lines:
            self.update(f"[dim]{_('Tools...')}[/dim]")
        else:
            display_content = "\n".join(lines)
            self.update(f"[bold]{_('Tools:')}[/bold]\n{display_content}")
