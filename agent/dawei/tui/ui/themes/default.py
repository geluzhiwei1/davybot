# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Default theme configuration for Dawei TUI."""


def get_default_theme() -> str:
    """Get the default theme CSS

    Returns:
        CSS content for default theme

    """
    return """
/*
 * Dawei TUI - Default Theme
 *
 * Color scheme and layout styling
 */

/* Global styles */
Screen {
    background: $primary;
}

/* Header */
Header {
    background: $primary 95%;
    text-align: center;
    text-style: bold;
}

/* Footer */
Footer {
    background: $primary 95%;
}

/* Main panels */
#left_panel {
    width: 70%;
}

#right_panel {
    width: 30%;
    dock: top;
}

/* Chat Area */
ChatArea {
    /* No height specified - let Textual handle it naturally */
    border: thick $background;
    background: $surface;
    padding: 1;
    scrollbar-size: 1 1;
}

/* Input Box */
InputBox {
    dock: bottom;
    height: 3;
    margin-top: 1;
}

/* Status Bar */
StatusBar {
    height: 3;
    background: $primary 90%;
    padding: 0 1;
    content-align: center middle;
}

/* Thinking Panel */
ThinkingPanel {
    /* No height specified - let Textual handle it naturally */
    min-height: 10;
    border: thick $background;
    background: $surface 95%;
    padding: 1;
    margin-top: 1;
}

/* Tool Panel */
ToolPanel {
    /* No height specified - let Textual handle it naturally */
    min-height: 10;
    border: thick $background;
    background: $surface 95%;
    padding: 1;
    margin-top: 1;
}

/* Scrollbar styling */
ChatArea::-webkit-scrollbar {
    background: $surface;
    color: $primary;
}

/* Focus styles */
InputBox:focus {
    border: thick $accent;
}

ChatArea:focus {
    border: thick $accent;
}

/* Colors */
$primary: #3c3c3c;
$secondary: #1e90ff;
$accent: #87ceeb;
$warning: #ffa500;
$error: #ff6347;
$success: #32cd32;
$surface: #2b2b2b;
$background: #1a1a1a;
"""
