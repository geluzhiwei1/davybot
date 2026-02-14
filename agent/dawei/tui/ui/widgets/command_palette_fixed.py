# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Command Palette

Quick action launcher (Ctrl+P) for TUI commands.
"""

from dataclasses import dataclass
from typing import ClassVar

from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Input, Static


@dataclass
class Command:
    """Command data structure"""

    name: str
    description: str
    action: str
    category: ClassVar[str] = "General"
    shortcut: ClassVar[str | None] = None


class CommandPalette(ModalScreen):
    """Command palette modal screen"""

    BINDINGS = [
        ("escape", "close", "Close"),
        ("enter", "execute_command", "Execute"),
    ]

    CSS = """
    CommandPalette {
        align: center middle;
    }

    #palette_container {
        width: 80%;
        height: 60%;
        border: thick $primary;
        background: $surface;
        padding: 1;
    }

    #command_input {
        margin-bottom: 1;
    }

    #commands_table {
        height: 1fr;
    }

    #preview {
        height: 3;
        margin-top: 1;
        border-top: solid $primary;
        padding-top: 1;
    }
    """

    def __init__(self, commands: list[Command], **kwargs):
        """Initialize command palette

        Args:
            commands: List of available commands

        """
        super().__init__(**kwargs)
        self.commands = commands
        self.filtered_commands = commands.copy()
        self.selected_command: Command | None = None

    def compose(self):
        """Compose command palette UI"""
        with Vertical(id="palette_container"):
            yield Static("[bold cyan]Command Palette[/bold cyan]")

            yield Input(
                placeholder="Type to filter commands... (Esc to close)",
                id="command_input",
            )

            yield DataTable(id="commands_table")

            yield Static(id="preview")

    def on_mount(self) -> None:
        """Initialize after mount"""
        table = self.query_one("#commands_table", DataTable)

        # Add columns
        table.add_columns("Command", "Description", "Shortcut")

        # Populate rows
        self._update_table(self.commands)

        # Focus input
        self.query_one("#command_input", Input).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle input change (filter commands)

        Args:
            event: Input changed event

        """
        query = event.value.lower().strip()

        if not query:
            self.filtered_commands = self.commands.copy()
        else:
            self.filtered_commands = [cmd for cmd in self.commands if query in cmd.name.lower() or query in cmd.description.lower() or query in cmd.category.lower()]

        self._update_table(self.filtered_commands)

    def on_data_table_selected(self, event: DataTable.Selected) -> None:
        """Handle row selection

        Args:
            event: Row selected event

        """
        table = event.data_table
        row_key = event.row_key

        if row_key is not None:
            # Get command from filtered list
            row_index = list(table.rows.keys()).index(row_key)
            if row_index < len(self.filtered_commands):
                self.selected_command = self.filtered_commands[row_index]
                self._update_preview(self.selected_command)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Handle row highlight

        Args:
            event: Row highlighted event

        """
        table = event.data_table
        row_key = event.row_key

        if row_key is not None:
            # Get command from filtered list
            row_index = list(table.rows.keys()).index(row_key)
            if row_index < len(self.filtered_commands):
                self.selected_command = self.filtered_commands[row_index]
                self._update_preview(self.selected_command)

    def on_input_submitted(self, _event: Input.Submitted) -> None:
        """Handle input submit (execute command)

        Args:
            event: Input submitted event

        """
        if self.selected_command:
            self.action_execute_command()

    def action_execute_command(self) -> None:
        """Execute selected command"""
        if self.selected_command:
            # Return command action to parent
            self.dismiss(self.selected_command.action)

    def action_close(self) -> None:
        """Close command palette"""
        self.dismiss(None)

    def _update_table(self, commands: list[Command]) -> None:
        """Update commands table

        Args:
            commands: Commands to display

        """
        table = self.query_one("#commands_table", DataTable)

        # Clear existing rows
        table.clear()

        # Add rows
        for cmd in commands:
            table.add_row(
                f"[bold]{cmd.name}[/bold]",
                cmd.description,
                cmd.shortcut or "",
                key=cmd.name,
            )

    def _update_preview(self, command: Command) -> None:
        """Update preview text

        Args:
            command: Command to preview

        """
        preview = self.query_one("#preview", Static)

        text = f"[bold cyan]{command.name}[/bold cyan]\n"
        text += f"{command.description}"

        if command.shortcut:
            text += f" [dim]({command.shortcut})[/dim]"

        preview.update(text)


def get_default_commands() -> list[Command]:
    """Get default command list

    Returns:
        List of default commands

    """
    return [
        # Navigation
        Command("Go to Chat", "Focus chat area", "nav.chat", "Navigation", "Alt+1"),
        Command("Go to Input", "Focus input box", "nav.input", "Navigation", "Alt+2"),
        Command(
            "Go to Thinking",
            "Focus thinking panel",
            "nav.thinking",
            "Navigation",
            "Alt+3",
        ),
        Command("Go to Tools", "Focus tool panel", "nav.tools", "Navigation", "Alt+4"),
        # View
        Command(
            "Toggle Thinking",
            "Show/hide thinking panel",
            "view.toggle_thinking",
            "View",
        ),
        Command("Toggle Tools", "Show/hide tool panel", "view.toggle_tools", "View"),
        Command("Clear Chat", "Clear chat history", "view.clear_chat", "View", "Ctrl+L"),
        # Mode
        Command("Code Mode", "Switch to code mode", "mode.code", "Mode"),
        Command("Ask Mode", "Switch to ask mode", "mode.ask", "Mode"),
        Command("Architect Mode", "Switch to architect mode", "mode.architect", "Mode"),
        Command("Plan Mode", "Switch to plan mode", "mode.plan", "Mode"),
        Command("Debug Mode", "Switch to debug mode", "mode.debug", "Mode"),
        # Session
        Command("New Session", "Start new chat session", "session.new", "Session"),
        Command("Save Session", "Save current session", "session.save", "Session", "Ctrl+S"),
        Command("Load Session", "Load previous session", "session.load", "Session"),
        Command("Export Chat", "Export chat as markdown", "session.export", "Session"),
        # Settings
        Command(
            "Open Settings",
            "Open settings screen",
            "settings.open",
            "Settings",
            "Ctrl+,",
        ),
        # Help
        Command("Show Help", "Show help screen", "help.show", "Help", "Ctrl+H"),
        Command("Show Shortcuts", "Show keyboard shortcuts", "help.shortcuts", "Help"),
        # Actions
        Command("Stop Agent", "Stop agent execution", "agent.stop", "Agent", "Ctrl+Shift+Q"),
    ]
