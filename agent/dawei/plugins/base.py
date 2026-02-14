# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Plugin base classes for the Dawei agent platform.

This file should be kept in sync with the davybot-plugins repository.
"""

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class PluginType(StrEnum):
    """Plugin type enumeration"""

    CHANNEL = "channel"
    TOOL = "tool"
    SERVICE = "service"
    MEMORY = "memory"


class PluginStatus(StrEnum):
    """Plugin status enumeration"""

    LOADED = "loaded"
    ACTIVATED = "activated"
    DEACTIVATED = "deactivated"
    ERROR = "error"


@dataclass
class PluginConfig:
    """Plugin configuration dataclass"""

    name: str
    version: str
    plugin_type: PluginType
    settings: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True


@dataclass
class PluginMetadata:
    """Plugin metadata from plugin.yaml"""

    api_version: str
    name: str
    version: str
    description: str
    author: str
    license: str
    python_version: str
    plugin_type: PluginType
    entry_point: str
    dependencies: dict[str, list[str]] = field(default_factory=dict)
    config_schema: dict[str, Any] = field(default_factory=dict)
    hooks: list[str] = field(default_factory=list)
    settings: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PluginMetadata":
        """Create metadata from dictionary"""
        return cls(
            api_version=data.get("api_version", "1.0"),
            name=data["name"],
            version=data["version"],
            description=data["description"],
            author=data["author"],
            license=data.get("license", "MIT"),
            python_version=data.get("python_version", ">=3.12"),
            plugin_type=PluginType(data.get("type", "tool")),
            entry_point=data["entry_point"],
            dependencies=data.get("dependencies", {}),
            config_schema=data.get("config_schema", {}),
            hooks=data.get("hooks", []),
            settings=data.get("settings", {}),
        )


class BasePlugin(ABC):
    """Base plugin class that all plugins must inherit from.

    Plugin lifecycle:
    1. __init__ - Plugin created with config
    2. initialize() - Initialize resources (async)
    3. activate() - Activate plugin (async)
    4. [plugin is active and running]
    5. deactivate() - Deactivate plugin (async)
    6. cleanup() - Cleanup resources (async, optional)
    """

    version: str = "1.0.0"
    author: str = "Unknown"
    description: str = "No description"
    license: str = "MIT"

    def __init__(self, config: PluginConfig):
        """Initialize plugin with configuration.

        Args:
            config: Plugin configuration

        """
        self.config = config
        self._status = PluginStatus.LOADED
        self._activated = False
        self._hooks: dict[str, Callable] = {}

    @property
    def status(self) -> PluginStatus:
        """Get plugin status"""
        return self._status

    @property
    def is_activated(self) -> bool:
        """Check if plugin is activated"""
        return self._activated

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize plugin resources.

        Called once when plugin is first loaded.
        Use this to set up connections, load data, etc.
        """

    @abstractmethod
    async def activate(self) -> None:
        """Activate plugin.

        Called when plugin should start working.
        Sets self._activated = True
        """
        self._activated = True
        self._status = PluginStatus.ACTIVATED

    @abstractmethod
    async def deactivate(self) -> None:
        """Deactivate plugin.

        Called when plugin should stop working.
        Sets self._activated = False
        """
        self._activated = False
        self._status = PluginStatus.DEACTIVATED

    async def cleanup(self) -> None:
        """Cleanup plugin resources.

        Called before plugin is unloaded.
        Override this to release resources, close connections, etc.
        """

    def register_hooks(self) -> dict[str, Callable]:
        """Register event hooks.

        Returns:
            Dictionary mapping event names to handler functions

        """
        return {}

    def register_tools(self) -> list[Any]:
        """Register custom tools.

        Returns:
            List of tool instances or tool classes

        """
        return []

    def get_config_schema(self) -> dict[str, Any]:
        """Get configuration schema for this plugin.

        Returns:
            JSON schema for plugin configuration validation

        """
        return {}

    async def validate_config(self, config: dict[str, Any]) -> bool:
        """Validate plugin configuration.

        Args:
            config: Configuration to validate

        Returns:
            True if configuration is valid

        Raises:
            ValueError: If configuration is invalid

        """
        schema = self.get_config_schema()
        if not schema:
            return True

        # Basic validation
        required = schema.get("required", [])
        for field in required:
            if field not in config:
                raise ValueError(f"Missing required config field: {field}")

        return True


class ChannelPlugin(BasePlugin):
    """Base class for channel plugins (Slack, Feishu, iMessage, etc.)

    Channel plugins send notifications and messages to external services.
    """

    @abstractmethod
    async def send_message(self, message: str, **kwargs) -> bool:
        """Send a message to the channel.

        Args:
            message: Message content to send
            **kwargs: Additional channel-specific parameters

        Returns:
            True if message sent successfully, False otherwise

        """

    @abstractmethod
    async def send_rich_message(self, content: dict[str, Any], **kwargs) -> bool:
        """Send a rich/formatted message to the channel.

        Args:
            content: Rich content (e.g., Slack blocks, markdown)
            **kwargs: Additional channel-specific parameters

        Returns:
            True if message sent successfully, False otherwise

        """


class ToolPlugin(BasePlugin):
    """Base class for tool plugins.

    Tool plugins extend agent capabilities with custom tools.
    """

    @abstractmethod
    def register_tools(self) -> list[Any]:
        """Register custom tools provided by this plugin.

        Returns:
            List of tool instances inheriting from CustomBaseTool

        """


class ServicePlugin(BasePlugin):
    """Base class for service plugins.

    Service plugins run background tasks and provide ongoing services.
    """

    @abstractmethod
    async def start_service(self) -> None:
        """Start the background service"""

    @abstractmethod
    async def stop_service(self) -> None:
        """Stop the background service"""

    async def activate(self) -> None:
        """Activate plugin and start service"""
        await super().activate()
        await self.start_service()

    async def deactivate(self) -> None:
        """Stop service and deactivate plugin"""
        await self.stop_service()
        await super().deactivate()


class MemoryPlugin(BasePlugin):
    """Base class for memory plugins.

    Memory plugins extend agent's memory and storage capabilities.
    """

    @abstractmethod
    async def store(self, key: str, value: Any, metadata: dict | None = None) -> bool:
        """Store a value in memory"""

    @abstractmethod
    async def retrieve(self, key: str) -> Any | None:
        """Retrieve a value from memory"""

    @abstractmethod
    async def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Search memory for items matching query"""

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Delete a value from memory"""
