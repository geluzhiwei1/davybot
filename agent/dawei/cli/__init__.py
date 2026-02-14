# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Dawei CLI - Refactored Command Line Interface

Modern, modular CLI using Click with grouped commands.

Structure:
    dawei <command> [options]

Commands:
    server       Start the web server
    tui          Start the terminal UI
    agent        Run agent directly (bypass HTTP)
    workspace    Workspace management
    config       Configuration management

Example:
    dawei server --port 8465
    dawei tui --workspace ./my-ws
    dawei agent run ./my-ws "create hello world"

"""

__version__ = "1.0.0"

from dawei.cli.commands import *
from dawei.cli.core import cli

__all__ = ["cli"]
