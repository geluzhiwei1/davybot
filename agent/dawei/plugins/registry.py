# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Plugin registry for managing plugin registration and lifecycle"""

import contextlib
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from dawei.plugins.base import BasePlugin, PluginMetadata, PluginType
from dawei.plugins.loader import PluginLoader

logger = logging.getLogger(__name__)


@dataclass
class PluginRegistration:
    """Plugin registration information"""

    plugin_id: str
    manifest: PluginMetadata
    plugin: BasePlugin
    activated: bool = False
    settings: dict[str, Any] = field(default_factory=dict)


class PluginRegistry:
    """Central registry for managing plugins.

    Handles plugin registration, activation, deactivation, and lifecycle.
    """

    def __init__(self):
        self.loader = PluginLoader()
        self.registrations: dict[str, PluginRegistration] = {}
        self.plugin_hooks: dict[str, list[Callable]] = {}

    async def register_plugin(
        self,
        manifest: PluginMetadata,
        settings: dict[str, Any],
        auto_activate: bool = False,
    ) -> bool:
        """Register a plugin.

        Args:
            manifest: Plugin metadata
            settings: Plugin settings
            auto_activate: Whether to auto-activate the plugin

        Returns:
            True if registered successfully

        """
        from dawei.plugins.utils import create_plugin_id

        plugin_id = create_plugin_id(manifest.name, manifest.version)

        if plugin_id in self.registrations:
            logger.warning(f"Plugin {plugin_id} already registered")
            return False

        try:
            # Load plugin
            plugin = await self.loader.load_plugin(manifest, settings)

            if not plugin:
                # Plugin failed to load, but still register metadata
                logger.warning(f"Plugin {plugin_id} failed to load, registering metadata only")
                registration = PluginRegistration(
                    plugin_id=plugin_id,
                    manifest=manifest,
                    plugin=None,  # No plugin instance
                    activated=False,
                    settings=settings,
                )
                self.registrations[plugin_id] = registration
                return True  # Return True to show plugin in list

            # Create registration
            registration = PluginRegistration(
                plugin_id=plugin_id,
                manifest=manifest,
                plugin=plugin,
                activated=False,
                settings=settings,
            )

            # Register hooks
            hooks = plugin.register_hooks()
            for event_name, handler in hooks.items():
                self._register_hook(event_name, handler)

            # Store registration
            self.registrations[plugin_id] = registration

            logger.info(f"Registered plugin: {plugin_id}")

            # Auto-activate if requested
            if auto_activate or manifest.settings.get("auto_activate", False):
                await self.activate_plugin(plugin_id)

            return True

        except Exception as e:
            # On any error, still register metadata so plugin shows in list
            logger.warning(f"Failed to fully load plugin {plugin_id}: {e}. Registering metadata only.")
            registration = PluginRegistration(
                plugin_id=plugin_id,
                manifest=manifest,
                plugin=None,  # No plugin instance due to error
                activated=False,
                settings=settings,
            )
            self.registrations[plugin_id] = registration
            return True  # Return True to show plugin in list

    async def unregister_plugin(self, plugin_id: str) -> bool:
        """Unregister a plugin.

        Args:
            plugin_id: Plugin ID to unregister

        Returns:
            True if unregistered successfully

        """
        if plugin_id not in self.registrations:
            logger.warning(f"Plugin {plugin_id} not registered")
            return False

        try:
            registration = self.registrations[plugin_id]

            # Deactivate if active
            if registration.activated and registration.plugin:
                await self.deactivate_plugin(plugin_id)

            # Unload plugin
            await self.loader.unload_plugin(plugin_id)

            # Remove hooks (only if plugin instance exists)
            if registration.plugin:
                for event_name, handler in registration.plugin.register_hooks().items():
                    self._unregister_hook(event_name, handler)

            # Remove registration
            del self.registrations[plugin_id]

            logger.info(f"Unregistered plugin: {plugin_id}")
            return True

        except Exception:
            logger.exception("Failed to unregister plugin {plugin_id}: ")
            return False

    async def activate_plugin(self, plugin_id: str) -> bool:
        """Activate a plugin.

        Args:
            plugin_id: Plugin ID to activate

        Returns:
            True if activated successfully

        """
        if plugin_id not in self.registrations:
            logger.warning(f"Plugin {plugin_id} not registered")
            return False

        registration = self.registrations[plugin_id]

        if registration.activated:
            logger.warning(f"Plugin {plugin_id} already activated")
            return False

        try:
            await registration.plugin.activate()
            registration.activated = True

            logger.info(f"Activated plugin: {plugin_id}")
            return True

        except Exception:
            logger.exception("Failed to activate plugin {plugin_id}: ")
            return False

    async def deactivate_plugin(self, plugin_id: str) -> bool:
        """Deactivate a plugin.

        Args:
            plugin_id: Plugin ID to deactivate

        Returns:
            True if deactivated successfully

        """
        if plugin_id not in self.registrations:
            logger.warning(f"Plugin {plugin_id} not registered")
            return False

        registration = self.registrations[plugin_id]

        if not registration.activated:
            logger.warning(f"Plugin {plugin_id} not activated")
            return False

        try:
            await registration.plugin.deactivate()
            registration.activated = False

            logger.info(f"Deactivated plugin: {plugin_id}")
            return True

        except Exception:
            logger.exception("Failed to deactivate plugin {plugin_id}: ")
            return False

    def get_plugin(self, plugin_id: str) -> BasePlugin | None:
        """Get plugin instance by ID"""
        registration = self.registrations.get(plugin_id)
        return registration.plugin if registration else None

    def get_manifest(self, plugin_id: str) -> PluginMetadata | None:
        """Get plugin manifest by ID"""
        registration = self.registrations.get(plugin_id)
        return registration.manifest if registration else None

    def list_plugins(
        self,
        plugin_type: PluginType | None = None,
        activated_only: bool = False,
    ) -> list[PluginMetadata]:
        """List registered plugins.

        Args:
            plugin_type: Filter by plugin type
            activated_only: Only show activated plugins

        Returns:
            List of plugin manifests

        """
        plugins = []

        for registration in self.registrations.values():
            if plugin_type and registration.manifest.plugin_type != plugin_type:
                continue

            if activated_only and not registration.activated:
                continue

            plugins.append(registration.manifest)

        return plugins

    def _register_hook(self, event_name: str, handler: Callable) -> None:
        """Register an event hook"""
        if event_name not in self.plugin_hooks:
            self.plugin_hooks[event_name] = []

        self.plugin_hooks[event_name].append(handler)

    def _unregister_hook(self, event_name: str, handler: Callable) -> None:
        """Unregister an event hook"""
        if event_name in self.plugin_hooks:
            with contextlib.suppress(ValueError):
                self.plugin_hooks[event_name].remove(handler)

    async def emit_event(self, event_name: str, event_data: Any) -> None:
        """Emit an event to all registered hooks.

        Args:
            event_name: Name of the event
            event_data: Event data to pass to handlers

        """
        if event_name not in self.plugin_hooks:
            return

        for handler in self.plugin_hooks[event_name]:
            try:
                if hasattr(event_data, "__dict__"):
                    await handler(event_data)
                else:
                    await handler(event_data)
            except Exception as e:
                logger.error(f"Error in hook handler for {event_name}: {e}", exc_info=True)

    def get_plugin_settings(self, plugin_id: str) -> dict[str, Any] | None:
        """Get plugin settings"""
        registration = self.registrations.get(plugin_id)
        return registration.settings if registration else None

    async def update_plugin_settings(self, plugin_id: str, settings: dict[str, Any]) -> bool:
        """Update plugin settings.

        Args:
            plugin_id: Plugin ID
            settings: New settings

        Returns:
            True if updated successfully

        """
        if plugin_id not in self.registrations:
            return False

        registration = self.registrations[plugin_id]

        try:
            # Only validate config if plugin instance exists
            if registration.plugin is not None:
                await registration.plugin.validate_config(settings)

            # Update settings
            registration.settings.update(settings)
            if registration.plugin is not None and hasattr(registration.plugin, 'config'):
                registration.plugin.config.settings.update(settings)

            logger.info(f"Updated settings for plugin: {plugin_id}")
            return True

        except Exception:
            logger.exception("Failed to update settings for {plugin_id}: ")
            return False
