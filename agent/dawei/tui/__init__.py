# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Dawei TUI - Terminal User Interface for Agent

A modern, async TUI for interacting with the Agent system directly,
without WebSocket overhead. Uses Textual framework for rich terminal UI.

Usage:
    python -m dawei.tui --workspace ./my-workspace --mode ask
"""

__version__ = "0.1.0"

# Apply Windows IME patch early (before importing Textual)
from dawei.tui import windows_ime_patch  # noqa: F401
from dawei.tui.app import GeweiTUIApp
from dawei.tui.config import TUIConfig, create_tui_config

__all__ = [
    "GeweiTUIApp",
    "TUIConfig",
    "create_tui_config",
]
