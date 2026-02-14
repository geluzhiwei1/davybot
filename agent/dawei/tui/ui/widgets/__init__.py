# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""TUI Widgets

Textual widget components for the Dawei TUI.
"""

from dawei.tui.ui.widgets.autocomplete_input import AutocompleteInputBox
from dawei.tui.ui.widgets.chat_area import ChatArea
from dawei.tui.ui.widgets.input_box import InputBox

# Enhanced InputBox variants for @skill support
from dawei.tui.ui.widgets.skill_aware_input import SkillAwareInputBox
from dawei.tui.ui.widgets.status_bar import StatusBar
from dawei.tui.ui.widgets.thinking_panel import ThinkingPanel
from dawei.tui.ui.widgets.toast_notifications import ToastManager, show_toast
from dawei.tui.ui.widgets.tool_panel import ToolPanel

__all__ = [
    "ChatArea",
    "InputBox",
    "StatusBar",
    "ThinkingPanel",
    "ToolPanel",
    # Enhanced InputBox variants
    "SkillAwareInputBox",
    "AutocompleteInputBox",
    # Toast notifications
    "ToastManager",
    "show_toast",
]
