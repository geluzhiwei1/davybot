# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""CLI Commands Module

Import all command groups to register them with the CLI.
"""

from dawei.cli.commands.agent import agent_cmd
from dawei.cli.commands.server import server_cmd
from dawei.cli.commands.tui import tui_cmd

# from dawei.cli.commands.workspace import workspace_cmd
# from dawei.cli.commands.config import config_cmd

__all__ = [
    "agent_cmd",
    "server_cmd",
    "tui_cmd",
    # "workspace_cmd",
    # "config_cmd",
]
