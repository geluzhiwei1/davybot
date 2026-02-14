# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Plugin loader for discovering and loading plugins from filesystem"""

import logging
import sys
from pathlib import Path
from typing import Any

from dawei.plugins.base import BasePlugin, PluginConfig, PluginMetadata, PluginType
from dawei.plugins.utils import (
    create_plugin_id,
    import_class,
    import_class_from_file,
    load_yaml_file,
    parse_entry_point,
)
from dawei.plugins.validators import PluginManifest, validate_plugin_directory

logger = logging.getLogger(__name__)


class PluginLoader:
    """Load plugins from filesystem directories.

    Supports 4-tier discovery:
    1. builtin - Built-in plugins (rarely used)
    2. system - System-wide plugins (/etc/dawei/plugins/)
    3. user - User-specific plugins (~/.dawei/plugins/)
    4. workspace - Workspace-specific plugins ({workspace}/.dawei/plugins/)
    """

    def __init__(self):
        self.loaded_plugins: dict[str, BasePlugin] = {}

    async def discover_plugins(
        self,
        search_paths: list[Path],
        recursive: bool = True,
    ) -> list[PluginMetadata]:
        """Discover all plugins in search paths.

        Args:
            search_paths: List of directories to search
            recursive: Search subdirectories recursively

        Returns:
            List of plugin metadata

        """
        discovered = []

        for search_path in search_paths:
            if not search_path.exists():
                logger.debug(f"Search path does not exist: {search_path}")
                continue

            plugin_dirs = [d for d in search_path.iterdir() if d.is_dir()] if recursive else [search_path]

            for plugin_dir in plugin_dirs:
                yaml_path = plugin_dir / "plugin.yaml"

                if yaml_path.exists():
                    try:
                        # Validate plugin
                        is_valid, errors = validate_plugin_directory(plugin_dir)

                        if not is_valid:
                            logger.warning(f"Plugin {plugin_dir.name} validation failed: {errors}")
                            continue

                        # Load manifest
                        manifest_data = load_yaml_file(yaml_path)

                        # Handle config_schema file reference
                        # If config_schema is a string (file path), load the JSON file
                        config_schema_value = manifest_data.get("config_schema")
                        if isinstance(config_schema_value, str):
                            # It's a file path, load JSON from it
                            schema_path = plugin_dir / config_schema_value
                            if schema_path.exists():
                                import json
                                try:
                                    with schema_path.open(encoding="utf-8") as f:
                                        manifest_data["config_schema"] = json.load(f)
                                    logger.debug(f"Loaded config_schema from {schema_path}")
                                except Exception as e:
                                    logger.error(f"Failed to load config_schema from {schema_path}: {e}")
                                    manifest_data["config_schema"] = {}
                            else:
                                logger.warning(f"config_schema file not found: {schema_path}")
                                manifest_data["config_schema"] = {}

                        manifest = PluginManifest(**manifest_data)

                        # Store plugin directory path
                        manifest._plugin_dir = plugin_dir

                        discovered.append(manifest)
                        logger.info(f"Discovered plugin: {manifest.name} v{manifest.version}")

                    except Exception:
                        logger.exception("Error discovering plugin in {plugin_dir}: ")

        return discovered

    async def load_plugin(
        self,
        manifest: PluginMetadata,
        settings: dict[str, Any],
    ) -> BasePlugin | None:
        """Load a plugin from its manifest.

        Args:
            manifest: Plugin metadata
            settings: Plugin configuration settings

        Returns:
            Loaded plugin instance or None if failed

        """
        plugin_id = create_plugin_id(manifest.name, manifest.version)

        if plugin_id in self.loaded_plugins:
            logger.warning(f"Plugin {plugin_id} already loaded")
            return self.loaded_plugins[plugin_id]

        try:
            # Parse entry point
            module_name, class_name = parse_entry_point(manifest.entry_point)

            # Get plugin directory
            plugin_dir = getattr(manifest, "_plugin_dir", None)
            if not plugin_dir:
                raise ValueError(f"Plugin directory not set for {manifest.name}")

            # Import plugin class from specific file path (avoid sys.path conflicts)
            plugin_file = plugin_dir / f"{module_name}.py"
            if not plugin_file.exists():
                raise ValueError(f"Plugin file not found: {plugin_file}")

            plugin_class = import_class_from_file(plugin_file, class_name)

            # Create plugin config
            config = PluginConfig(
                name=manifest.name,
                version=manifest.version,
                plugin_type=PluginType(manifest.plugin_type),
                settings=settings,
                metadata=manifest.dict(),
            )

            # Instantiate plugin
            plugin = plugin_class(config)

            # Initialize plugin
            await plugin.initialize()

            # Store loaded plugin
            self.loaded_plugins[plugin_id] = plugin

            logger.info(f"Loaded plugin: {plugin_id}")
            return plugin

        except Exception:
            logger.exception("Failed to load plugin {manifest.name}: ")
            return None

    async def unload_plugin(self, plugin_id: str) -> bool:
        """Unload a plugin.

        Args:
            plugin_id: Plugin ID (name@version)

        Returns:
            True if unloaded successfully

        """
        if plugin_id not in self.loaded_plugins:
            logger.warning(f"Plugin {plugin_id} not loaded")
            return False

        try:
            plugin = self.loaded_plugins[plugin_id]

            # Deactivate if active
            if plugin.is_activated:
                await plugin.deactivate()

            # Cleanup
            await plugin.cleanup()

            # Remove from loaded plugins
            del self.loaded_plugins[plugin_id]

            logger.info(f"Unloaded plugin: {plugin_id}")
            return True

        except Exception:
            logger.exception("Failed to unload plugin {plugin_id}: ")
            return False

    def get_plugin(self, plugin_id: str) -> BasePlugin | None:
        """Get loaded plugin by ID"""
        return self.loaded_plugins.get(plugin_id)

    def list_loaded_plugins(self) -> list[str]:
        """List all loaded plugin IDs"""
        return list(self.loaded_plugins.keys())

    async def reload_plugin(self, plugin_id: str) -> BasePlugin | None:
        """Reload a plugin.

        Args:
            plugin_id: Plugin ID to reload

        Returns:
            Reloaded plugin instance or None if failed

        """
        if plugin_id not in self.loaded_plugins:
            logger.warning(f"Cannot reload: Plugin {plugin_id} not loaded")
            return None

        # Get plugin info before unloading
        plugin = self.loaded_plugins[plugin_id]
        manifest = PluginMetadata(**plugin.config.metadata)

        # Unload
        await self.unload_plugin(plugin_id)

        # Reload
        return await self.load_plugin(manifest, plugin.config.settings)
