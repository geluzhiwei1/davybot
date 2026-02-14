# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""MainScreen

Main chat interface with multi-panel layout.
"""

from pathlib import Path

from textual.containers import Horizontal, Vertical
from textual.screen import Screen

from dawei.tui.i18n import _

# Use enhanced InputBox with @skill support (autocomplete + syntax highlighting)
from dawei.tui.ui.widgets.autocomplete_input import AutocompleteInputBox as InputBox
from dawei.tui.ui.widgets.chat_area import ChatArea
from dawei.tui.ui.widgets.pdca_panel import PDCAPanel
from dawei.tui.ui.widgets.status_bar import StatusBar
from dawei.tui.ui.widgets.thinking_panel import ThinkingPanel
from dawei.tui.ui.widgets.tool_panel import ToolPanel


class MainScreen(Screen):
    """Main chat interface with multi-panel layout"""

    def compose(self):
        """Compose UI layout"""
        # Get workspace path from app
        workspace_path = Path.cwd()
        if hasattr(self.app, "config") and hasattr(self.app.config, "workspace_absolute"):
            workspace_path = Path(self.app.config.workspace_absolute)

        # Main content area - split horizontally
        yield Horizontal(
            # Left panel (70%): Chat area + Input box
            Vertical(
                ChatArea(id="chat_area"),
                InputBox(
                    id="input_box",
                    placeholder=_("Type @skill:name or message... (Tab to autocomplete, Enter to send)"),
                    workspace_path=workspace_path,
                ),
                id="left_panel",
            ),
            # Right panel (30%): Status + Info
            Vertical(
                StatusBar(id="status_bar"),
                PDCAPanel(id="pdca_panel"),
                ThinkingPanel(id="thinking_panel"),
                ToolPanel(id="tool_panel"),
                id="right_panel",
            ),
            id="main_container",
        )
