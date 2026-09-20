# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Settings Screen

Configuration UI for TUI settings.
"""

from dataclasses import dataclass
from typing import ClassVar

from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import (
    Button,
    Checkbox,
    Footer,
    Header,
    Input,
    Label,
    Static,
)

from dawei.tui.i18n import _


@dataclass
class TUISettings:
    """TUI settings dataclass"""

    # Display settings
    refresh_rate: float = 0.1
    max_history: int = 1000
    show_thinking: bool = True
    show_tools: bool = True
    enable_markdown: bool = True
    enable_syntax_highlight: bool = True

    # Theme settings
    theme: str = "default"

    # Editor settings
    max_thinking_lines: int = 10
    max_tool_lines: int = 5

    def to_dict(self) -> dict:
        """Convert to dictionary

        Returns:
            Dictionary representation

        """
        return {
            "refresh_rate": self.refresh_rate,
            "max_history": self.max_history,
            "show_thinking": self.show_thinking,
            "show_tools": self.show_tools,
            "enable_markdown": self.enable_markdown,
            "enable_syntax_highlight": self.enable_syntax_highlight,
            "theme": self.theme,
            "max_thinking_lines": self.max_thinking_lines,
            "max_tool_lines": self.max_tool_lines,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TUISettings":
        """Create from dictionary

        Args:
            data: Dictionary with settings

        Returns:
            TUISettings instance

        """
        return cls(**data)


class SettingsScreen(Screen):
    """Settings screen for TUI configuration"""

    BINDINGS = [
        ("s", "save_settings", "Save"),
        ("r", "reset_settings", "Reset"),
        ("escape", "pop_screen", "Cancel"),
        ("q", "pop_screen", "Cancel"),
    ]

    CSS = """
    SettingsScreen {
        align: center middle;
    }

    .settings-container {
        width: 80%;
        height: 80%;
        border: thick $primary;
        background: $surface;
        padding: 2;
    }

    .section-title {
        text-style: bold;
        margin-top: 1;
        margin-bottom: 1;
    }

    .setting-row {
        height: 3;
        margin-bottom: 1;
    }

    .button-row {
        height: 3;
        dock: bottom;
    }
    """

    def __init__(self, settings: TUISettings | None = None, **kwargs):
        """Initialize settings screen

        Args:
            settings: Current settings (optional)

        """
        super().__init__(**kwargs)
        self.settings = settings or TUISettings()

    def compose(self):
        """Compose settings UI"""
        yield Header()

        with Vertical(id="settings_container"):
            yield Static("[bold cyan]Dawei TUI - Settings[/bold cyan]")

            # Language settings removed - use header language selector (top right corner)
            # Click the language indicator (🌐) in the header to switch languages

            # Display Settings
            yield Static(
                f"[bold yellow]{_('Display Settings')}[/bold yellow]",
                classes="section-title",
            )

            yield Label("Refresh Rate (seconds):")
            yield Input(
                value=str(self.settings.refresh_rate),
                placeholder="0.1",
                id="refresh_rate_input",
            )

            yield Label("Max History:")
            yield Input(
                value=str(self.settings.max_history),
                placeholder="1000",
                id="max_history_input",
            )

            # Checkboxes
            yield Checkbox(
                "Show Thinking Panel",
                value=self.settings.show_thinking,
                id="show_thinking_check",
            )

            yield Checkbox("Show Tool Panel", value=self.settings.show_tools, id="show_tools_check")

            yield Checkbox(
                "Enable Markdown",
                value=self.settings.enable_markdown,
                id="enable_markdown_check",
            )

            yield Checkbox(
                "Enable Syntax Highlighting",
                value=self.settings.enable_syntax_highlight,
                id="enable_syntax_check",
            )

            # Panel Settings
            yield Static(
                f"[bold yellow]{_('Panel Settings')}[/bold yellow]",
                classes="section-title",
            )

            yield Label("Max Thinking Lines:")
            yield Input(
                value=str(self.settings.max_thinking_lines),
                placeholder="10",
                id="max_thinking_input",
            )

            yield Label("Max Tool Lines:")
            yield Input(
                value=str(self.settings.max_tool_lines),
                placeholder="5",
                id="max_tool_input",
            )

            # Buttons
            with Horizontal(classes="button-row"):
                yield Button("Save (S)", id="save_button", variant="primary")
                yield Button("Reset (R)", id="reset_button", variant="warning")
                yield Button("Cancel (Esc)", id="cancel_button", variant="default")

        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press

        Args:
            event: Button pressed event

        """
        button_id = event.button.id

        if button_id == "save_button":
            self.action_save_settings()
        elif button_id == "reset_button":
            self.action_reset_settings()
        elif button_id == "cancel_button":
            self.dismiss()

    def action_save_settings(self) -> None:
        """Save settings and close"""
        try:
            # Get values from inputs
            refresh_rate = self.query_one("#refresh_rate_input", Input).value
            max_history = self.query_one("#max_history_input", Input).value
            show_thinking = self.query_one("#show_thinking_check", Checkbox).value
            show_tools = self.query_one("#show_tools_check", Checkbox).value
            enable_markdown = self.query_one("#enable_markdown_check", Checkbox).value
            enable_syntax = self.query_one("#enable_syntax_check", Checkbox).value
            max_thinking = self.query_one("#max_thinking_input", Input).value
            max_tool = self.query_one("#max_tool_input", Input).value

            # Create new settings
            new_settings = TUISettings(
                refresh_rate=float(refresh_rate) if refresh_rate else 0.1,
                max_history=int(max_history) if max_history else 1000,
                show_thinking=show_thinking,
                show_tools=show_tools,
                enable_markdown=enable_markdown,
                enable_syntax_highlight=enable_syntax,
                max_thinking_lines=int(max_thinking) if max_thinking else 10,
                max_tool_lines=int(max_tool) if max_tool else 5,
            )

            self.dismiss(new_settings)

        except ValueError:
            self.app.bell()
            # Show error message (could improve this)

    def action_reset_settings(self) -> None:
        """Reset to default settings"""
        defaults = TUISettings()

        # Update UI
        self.query_one("#refresh_rate_input", Input).value = str(defaults.refresh_rate)
        self.query_one("#max_history_input", Input).value = str(defaults.max_history)
        self.query_one("#show_thinking_check", Checkbox).value = defaults.show_thinking
        self.query_one("#show_tools_check", Checkbox).value = defaults.show_tools
        self.query_one("#enable_markdown_check", Checkbox).value = defaults.enable_markdown
        self.query_one("#enable_syntax_check", Checkbox).value = defaults.enable_syntax_highlight
        self.query_one("#max_thinking_input", Input).value = str(defaults.max_thinking_lines)
        self.query_one("#max_tool_input", Input).value = str(defaults.max_tool_lines)
