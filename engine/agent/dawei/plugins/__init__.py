# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Dawei Plugin System

A comprehensive plugin system for extending agent capabilities.
Supports 4-tier discovery: builtin, system, user, workspace.
"""

from dawei.plugins.base import (
    BasePlugin,
    ChannelPlugin,
    MemoryPlugin,
    PluginConfig,
    PluginMetadata,
    PluginStatus,
    PluginType,
    ServicePlugin,
    ToolPlugin,
)
from dawei.plugins.loader import PluginLoader
from dawei.plugins.manager import PluginManager
from dawei.plugins.registry import PluginRegistry
from dawei.plugins.validators import PluginManifest, validate_plugin_directory

__all__ = [
    # Base classes
    "BasePlugin",
    "ChannelPlugin",
    "ToolPlugin",
    "ServicePlugin",
    "MemoryPlugin",
    # Enums and dataclasses
    "PluginType",
    "PluginStatus",
    "PluginConfig",
    "PluginMetadata",
    # Manager classes
    "PluginManager",
    "PluginLoader",
    "PluginRegistry",
    # Validators
    "PluginManifest",
    "validate_plugin_directory",
]

# Version info
__version__ = "1.0.0"
