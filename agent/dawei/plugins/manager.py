# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Plugin manager for coordinating plugin system with 3-tier discovery"""

import logging
from pathlib import Path
from typing import Any

from dawei.plugins.base import PluginMetadata, PluginType
from dawei.plugins.registry import PluginRegistry

logger = logging.getLogger(__name__)


class PluginManager:
    """Central plugin manager with 3-tier discovery system.

    Discovery tiers (highest to lowest priority):
    1. workspace - Workspace-specific plugins ({workspace}/.dawei/plugins/)
    2. user - User-specific plugins (~/.dawei/plugins/)
    3. builtin - Built-in plugins (rarely used)
    """

    def __init__(self, workspace_path: Path | None = None):
        """Initialize plugin manager.

        Args:
            workspace_path: Optional workspace path for tier 3 discovery

        """
        self.workspace_path = workspace_path
        self.registry = PluginRegistry()
        self.loader = self.registry.loader

        # 4-tier discovery paths (same as skills discovery)
        self.discovery_paths = self._init_discovery_paths()

        logger.info(f"PluginManager initialized with workspace: {workspace_path}")

    def _init_discovery_paths(self) -> list[Path]:
        """Initialize 4-tier discovery paths"""
        paths = []

        # Tier 1: Workspace plugins (highest priority)
        if self.workspace_path:
            workspace_plugin_dir = self.workspace_path / ".dawei" / "plugins"
            if workspace_plugin_dir.exists():
                paths.append(workspace_plugin_dir)
                logger.debug(f"Workspace plugin path: {workspace_plugin_dir}")

        # Tier 2: User plugins
        from pathlib import Path

        home = Path.home()
        # User plugins: ~/.dawei/plugins/
        user_plugin_dir = home / ".dawei" / "plugins"
        if user_plugin_dir.exists():
            paths.append(user_plugin_dir)
            logger.debug(f"User plugin path: {user_plugin_dir}")

        # Tier 3: Builtin plugins (lowest priority, rarely used)
        builtin_plugin_dir = Path(__file__).parent / "builtin"
        if builtin_plugin_dir.exists():
            paths.append(builtin_plugin_dir)
            logger.debug(f"Builtin plugin path: {builtin_plugin_dir}")

        return paths

    async def discover_and_load_all(self, settings: dict[str, str] | None = None) -> int:
        """Discover and load all plugins from discovery paths.

        Args:
            settings: Optional settings per plugin name

        Returns:
            Number of plugins loaded

        """
        settings = settings or {}

        # Discover plugins
        manifests = await self.loader.discover_plugins(self.discovery_paths, recursive=True)

        logger.info(f"Discovered {len(manifests)} plugins")

        # Load plugins
        loaded_count = 0
        for manifest in manifests:
            # Try full plugin_id first (name@version), then fallback to just name
            plugin_id = f"{manifest.name}@{manifest.version}"
            plugin_settings = settings.get(plugin_id) or settings.get(manifest.name) or manifest.settings

            # Register plugin (don't auto-activate to avoid config errors)
            # User can activate manually after configuration
            success = await self.registry.register_plugin(
                manifest,
                plugin_settings,
                auto_activate=False,  # Changed from True to avoid activation failures
            )

            if success:
                loaded_count += 1

        logger.info(f"Loaded {loaded_count}/{len(manifests)} plugins")
        return loaded_count

    async def load_plugin_from_path(self, plugin_dir: Path, settings: dict[str, Any]) -> bool:
        """Load a plugin from a specific directory.

        Args:
            plugin_dir: Path to plugin directory
            settings: Plugin settings

        Returns:
            True if loaded successfully

        """
        from dawei.plugins.validators import validate_plugin_directory

        # Validate plugin
        is_valid, errors = validate_plugin_directory(plugin_dir)

        if not is_valid:
            logger.error(f"Plugin validation failed: {errors}")
            return False

        # Load manifest
        import json

        from dawei.plugins.utils import load_yaml_file

        yaml_path = plugin_dir / "plugin.yaml"
        manifest_data = load_yaml_file(yaml_path)

        # Handle config_schema file reference
        config_schema_value = manifest_data.get("config_schema")
        if isinstance(config_schema_value, str):
            # It's a file path, load JSON from it
            schema_path = plugin_dir / config_schema_value
            if schema_path.exists():
                try:
                    with schema_path.open(encoding="utf-8") as f:
                        manifest_data["config_schema"] = json.load(f)
                    logger.debug(f"Loaded config_schema from {schema_path}")
                except Exception as e:
                    logger.exception(f"Failed to load config_schema from {schema_path}: {e}")
                    manifest_data["config_schema"] = {}
            else:
                logger.warning(f"config_schema file not found: {schema_path}")
                manifest_data["config_schema"] = {}

        manifest = PluginMetadata(**manifest_data)
        manifest._plugin_dir = plugin_dir

        # Register plugin
        return await self.registry.register_plugin(
            manifest,
            settings,
            auto_activate=settings.get("enabled", True),
        )

    async def activate_plugin(self, plugin_id: str) -> bool:
        """Activate a plugin by ID"""
        return await self.registry.activate_plugin(plugin_id)

    async def deactivate_plugin(self, plugin_id: str) -> bool:
        """Deactivate a plugin by ID"""
        return await self.registry.deactivate_plugin(plugin_id)

    async def reload_plugin(self, plugin_id: str) -> bool:
        """Reload a plugin"""
        plugin = self.registry.get_plugin(plugin_id)

        if not plugin:
            logger.warning(f"Cannot reload: Plugin {plugin_id} not found")
            return False

        # Get manifest and settings
        manifest = self.registry.get_manifest(plugin_id)
        settings = self.registry.get_plugin_settings(plugin_id)

        # Unregister
        await self.registry.unregister_plugin(plugin_id)

        # Re-register
        return await self.registry.register_plugin(
            manifest,
            settings,
            auto_activate=settings.get("enabled", True),
        )

    def get_plugin(self, plugin_id: str):
        """Get plugin instance by ID"""
        return self.registry.get_plugin(plugin_id)

    def get_plugin_by_name(self, name: str):
        """Get first plugin matching name (any version)"""
        for plugin_id in self.registry.registrations:
            if plugin_id.startswith(f"{name}@"):
                return self.registry.get_plugin(plugin_id)
        return None

    def list_plugins(
        self,
        plugin_type: PluginType | None = None,
        activated_only: bool = False,
    ) -> list[dict[str, Any]]:
        """List all plugins with their status.

        Args:
            plugin_type: Filter by plugin type
            activated_only: Only show activated plugins

        Returns:
            List of plugin info dictionaries

        """
        plugins = []

        for registration in self.registry.registrations.values():
            if plugin_type and registration.manifest.plugin_type != plugin_type:
                continue

            if activated_only and not registration.activated:
                continue

            plugins.append(
                {
                    "id": registration.plugin_id,
                    "name": registration.manifest.name,
                    "version": registration.manifest.version,
                    "type": registration.manifest.plugin_type,
                    "description": registration.manifest.description,
                    "author": registration.manifest.author,
                    "activated": registration.activated,
                    "enabled": registration.settings.get("enabled", True),
                },
            )

        return plugins

    async def uninstall_plugin(self, plugin_id: str) -> bool:
        """Uninstall a plugin by ID.

        Args:
            plugin_id: Plugin ID to uninstall (format: name@version)

        Returns:
            True if uninstalled successfully

        """
        # Check if plugin is registered (even if loading failed)
        registration = self.registry.registrations.get(plugin_id)

        # If exact plugin not found, check if there's a version mismatch
        if not registration:
            # Try to find any plugin with the same name
            plugin_name = plugin_id.split("@", maxsplit=1)[0] if "@" in plugin_id else plugin_id

            # Check all registered plugins for same name
            matching_plugins = [pid for pid in self.registry.registrations if pid.startswith(f"{plugin_name}@")]

            if matching_plugins:
                # Found same plugin but different version
                logger.warning(f"Cannot uninstall: Plugin {plugin_id} not found. Did you mean: {', '.join(matching_plugins)}?")
            else:
                # No plugin with that name at all
                logger.warning(f"Cannot uninstall: Plugin {plugin_id} not found")

            return False

        # Get manifest
        manifest = registration.manifest

        # Check if plugin can be uninstalled (workspace plugins only)
        plugin_dir = getattr(manifest, "_plugin_dir", None)
        if not plugin_dir:
            logger.error(f"Plugin {plugin_id} has no plugin directory, cannot uninstall")
            return False

        # Check if it's a builtin plugin (cannot uninstall)
        builtin_dir = Path(__file__).parent / "builtin"
        if plugin_dir.exists() and builtin_dir.exists() and plugin_dir.samefile(builtin_dir):
            logger.error(f"Cannot uninstall builtin plugin {plugin_id}")
            return False

        try:
            # Unregister the plugin first (was: unload_plugin which doesn't exist)
            await self.registry.unregister_plugin(plugin_id)

            # Remove plugin directory if it exists
            if plugin_dir.exists():
                import shutil

                shutil.rmtree(plugin_dir)
                logger.info(f"Removed plugin directory: {plugin_dir}")

            logger.info(f"Uninstalled plugin: {plugin_id}")
            return True

        except Exception:
            logger.exception(f"Failed to uninstall plugin {plugin_id}: ")
            return False

    async def uninstall_plugin_by_name(self, plugin_name: str) -> bool:
        """Uninstall a plugin by name (any version).

        Args:
            plugin_name: Plugin name (without version suffix)

        Returns:
            True if uninstalled successfully, False if not found

        """
        # Find all plugins with this name
        matching_plugins = [pid for pid in self.registry.registrations if pid.startswith(f"{plugin_name}@")]

        if not matching_plugins:
            logger.warning(f"Cannot uninstall: No plugin found with name '{plugin_name}'")
            return False

        if len(matching_plugins) > 1:
            logger.warning(f"Multiple versions found for '{plugin_name}': {', '.join(matching_plugins)}. Uninstalling all of them.")

        # Uninstall all matching plugins
        success_count = 0
        for plugin_id in matching_plugins:
            if await self.uninstall_plugin(plugin_id):
                success_count += 1

        return success_count > 0

    async def emit_event(self, event_name: str, event_data: Any) -> None:
        """Emit an event to all registered plugin hooks.

        Args:
            event_name: Name of the event
            event_data: Event data

        """
        await self.registry.emit_event(event_name, event_data)

    async def get_plugin_tools(self) -> list[Any]:
        """Get all tools from activated tool plugins.

        Returns:
            List of tool instances

        """
        tools = []

        for registration in self.registry.registrations.values():
            if not registration.activated:
                continue

            if registration.manifest.plugin_type == PluginType.TOOL:
                plugin_tools = registration.plugin.register_tools()
                tools.extend(plugin_tools)

        return tools

    async def update_plugin_settings(self, plugin_id: str, settings: dict[str, Any]) -> bool:
        """Update plugin settings"""
        return await self.registry.update_plugin_settings(plugin_id, settings)

    def get_plugin_settings(self, plugin_id: str) -> dict[str, Any] | None:
        """Get plugin settings"""
        return self.registry.get_plugin_settings(plugin_id)

    async def shutdown(self) -> None:
        """Shutdown plugin manager and cleanup all plugins"""
        logger.info("Shutting down plugin manager...")

        # Deactivate all activated plugins
        for plugin_id in list(self.registry.registrations.keys()):
            try:
                await self.registry.unregister_plugin(plugin_id)
            except Exception:
                logger.exception("Error shutting down plugin {plugin_id}: ")

        logger.info("Plugin manager shutdown complete")

    def get_statistics(self) -> dict[str, Any]:
        """Get plugin system statistics"""
        total = len(self.registry.registrations)
        activated = sum(1 for r in self.registry.registrations.values() if r.activated)

        by_type = {}
        for registration in self.registry.registrations.values():
            ptype = registration.manifest.plugin_type
            by_type[ptype] = by_type.get(ptype, 0) + 1

        return {
            "total_plugins": total,
            "activated_plugins": activated,
            "by_type": by_type,
            "discovery_paths": [str(p) for p in self.discovery_paths],
        }

    def get_config_schema(self, plugin_id: str) -> dict[str, Any] | None:
        """Get configuration schema for a plugin.

        Args:
            plugin_id: Plugin identifier

        Returns:
            Configuration schema (JSON Schema format) or None if not found

        """
        manifest = self.registry.get_manifest(plugin_id)
        if not manifest:
            return None

        return getattr(manifest, "config_schema", None)

    def validate_config(self, plugin_id: str, config: dict[str, Any]) -> tuple[bool, list[str]]:
        """Validate plugin configuration against schema.

        Args:
            plugin_id: Plugin identifier
            config: Configuration to validate

        Returns:
            Tuple of (is_valid, error_messages)

        """
        import jsonschema

        schema = self.get_config_schema(plugin_id)
        if not schema:
            # No schema defined, accept any config
            return True, []

        errors = []
        try:
            jsonschema.validate(instance=config, schema=schema)
            return True, []
        except jsonschema.ValidationError as e:
            errors.append(f"Configuration validation failed: {e.message}")
            if e.path:
                errors.append(f"  Path: {' -> '.join(str(p) for p in e.path)}")
            return False, errors
        except Exception as e:
            errors.append(f"Validation error: {e!s}")
            return False, errors

    def get_config_manager(self) -> "PluginConfigManager":
        """Get PluginConfigManager instance for this workspace.

        Returns:
            PluginConfigManager instance
        """
        from dawei.plugins.config import PluginConfigManager

        return PluginConfigManager(workspace_path=self.workspace_path)

    async def save_plugin_config(self, plugin_id: str, config: dict[str, Any]) -> bool:
        """Save and apply plugin configuration using PluginConfigManager.

        Args:
            plugin_id: Plugin identifier
            config: Configuration to save

        Returns:
            True if successful

        """
        from dawei.plugins.config import PluginConfigManager

        # Validate config first
        is_valid, errors = self.validate_config(plugin_id, config)
        if not is_valid:
            logger.error(f"Invalid config for {plugin_id}: {errors}")
            return False

        # Get plugin manifest to find plugin directory
        manifest = self.registry.get_manifest(plugin_id)
        if not manifest:
            logger.error(f"Plugin {plugin_id} not found")
            return False

        try:
            # Use PluginConfigManager to save config (follows plugin location)
            config_manager = self.get_config_manager()
            config_manager.save_plugin_config(plugin_id, config)

            logger.info(f"Saved config for {plugin_id}")

            # Update plugin settings
            await self.update_plugin_settings(plugin_id, {"config": config, "enabled": True})

            # Activate plugin with new config
            await self.activate_plugin(plugin_id)

            return True
        except Exception:
            logger.exception(f"Failed to save config for {plugin_id}: ")
            return False

    def get_plugin_config(self, plugin_id: str) -> dict[str, Any] | None:
        """Load saved plugin configuration using PluginConfigManager.

        Args:
            plugin_id: Plugin identifier

        Returns:
            Configuration dict or None if not found

        """
        from dawei.plugins.config import PluginConfigManager

        try:
            # Use PluginConfigManager to load config (follows plugin location)
            config_manager = self.get_config_manager()
            return config_manager.load_plugin_config(plugin_id)
        except Exception:
            logger.exception(f"Failed to load config for {plugin_id}: ")
            return None
