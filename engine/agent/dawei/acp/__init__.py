# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Dawei ACP integration package."""

from .agent_registry import (
    ACPAgentInfo,
    add_agent,
    discover_and_merge,
    get_tool_description_text,
    list_available_agents,
    load_registry,
    remove_agent,
    scan_path_for_agents,
    toggle_agent,
)
from .sdk_loader import ensure_acp_sdk_path, import_acp

__all__ = [
    "ACPAgentInfo",
    "add_agent",
    "discover_and_merge",
    "ensure_acp_sdk_path",
    "get_tool_description_text",
    "import_acp",
    "list_available_agents",
    "load_registry",
    "remove_agent",
    "scan_path_for_agents",
    "toggle_agent",
]
