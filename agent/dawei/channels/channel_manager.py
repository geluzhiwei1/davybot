"""Channel manager with registry, discovery, and lifecycle management.

The ChannelManager is responsible for:
- Registering and discovering channel implementations
- Managing channel lifecycle (start, stop, health checks)
- Providing a unified interface for interacting with all channels
- Auto-discovery of channel packages via lazy imports
"""

from __future__ import annotations

import asyncio
import importlib
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore[import-untyped]
    # optional yaml dependency for config loading
except ImportError:
    yaml = None  # type: ignore[assignment]

from .bus import MessageBus
from .channel import BaseChannel, ChannelHealth
from .config import BaseChannelConfig
from .retry import RetryConfig

logger = logging.getLogger(__name__)

ChannelFactory = Callable[[BaseChannelConfig, MessageBus], BaseChannel]


@dataclass
class ChannelSpec:
    """Specification for a channel instance."""

    channel_type: str
    enabled: bool = True
    config: dict[str, Any] | None = None
    retry_config: dict[str, Any] | None = None


class ChannelRegistry:
    """Registry of available channel types and their factories."""

    _factories: dict[str, ChannelFactory] = {}

    @classmethod
    def register(cls, channel_type: str, factory: ChannelFactory) -> None:
        """Register a channel factory.

        Args:
            channel_type: Unique channel type identifier (e.g., "telegram", "discord")
            factory: Function that creates a channel instance
        """
        if channel_type in cls._factories:
            logger.warning(f"Channel type '{channel_type}' already registered, overwriting")
        cls._factories[channel_type] = factory
        logger.info(f"Registered channel type: {channel_type}")

    @classmethod
    def unregister(cls, channel_type: str) -> None:
        """Unregister a channel type."""
        if channel_type in cls._factories:
            del cls._factories[channel_type]
            logger.info(f"Unregistered channel type: {channel_type}")

    @classmethod
    def get_factory(cls, channel_type: str) -> ChannelFactory | None:
        """Get a channel factory by type."""
        return cls._factories.get(channel_type)

    @classmethod
    def list_channels(cls) -> list[str]:
        """List all registered channel types."""
        return list(cls._factories.keys())

    @classmethod
    def is_registered(cls, channel_type: str) -> bool:
        """Check if a channel type is registered."""
        return channel_type in cls._factories


def register_channel(channel_type: str) -> Callable[[type[BaseChannel]], type[BaseChannel]]:
    """Decorator to register a channel class.

    Usage:
        @register_channel("telegram")
        class TelegramChannel(BaseChannel):
            ...
    """

    def decorator(cls: type[BaseChannel]) -> type[BaseChannel]:
        def factory(config: BaseChannelConfig, message_bus: MessageBus) -> BaseChannel:
            return cls(config, message_bus)

        ChannelRegistry.register(channel_type, factory)
        return cls

    return decorator


class ChannelManager:
    """Manages multiple channel instances with lifecycle and health monitoring.

    The ChannelManager is responsible for:
    - Loading channel configuration from workspace config
    - Creating channel instances via registered factories
    - Starting/stopping all channels
    - Health monitoring and error recovery
    """

    def __init__(
        self,
        message_bus: MessageBus,
        workspace_path: Path | None = None,
    ) -> None:
        """Initialize the channel manager.

        Args:
            message_bus: Shared message bus for all channels
            workspace_path: Path to workspace (for loading config)
        """
        self.message_bus = message_bus
        self.workspace_path = workspace_path or Path.cwd()
        self._channels: dict[str, BaseChannel] = {}
        self._running = False
        self._health_check_task: asyncio.Task[None] | None = None

    async def load_from_config(self, config_path: Path | None = None) -> None:
        """Load channel configuration from a YAML file.

        Args:
            config_path: Path to config file (default: workspace/.dawei/channels.yml)
        """
        if not config_path.exists():
            logger.info(f"No channel config found at {config_path}")
            return

        with open(config_path) as f:
            config_data = yaml.safe_load(f) or {}

        channels_config = config_data.get("channels", [])
        for spec_dict in channels_config:
            try:
                spec = ChannelSpec(**spec_dict)
                if spec.enabled:
                    await self.add_channel(spec)
            except Exception as e:
                logger.error(f"Failed to load channel spec {spec_dict}: {e}")

    async def add_channel(
        self,
        spec: ChannelSpec,
    ) -> BaseChannel:
        """Add a channel instance.

        Args:
            spec: Channel specification

        Returns:
            The created channel instance

        Raises:
            ValueError: If channel type is not registered
        """
        # Ensure channels are auto-discovered
        _ensure_channels_registered()

        factory = ChannelRegistry.get_factory(spec.channel_type)
        if factory is None:
            raise ValueError(
                f"Unknown channel type: {spec.channel_type}. "
                f"Available: {ChannelRegistry.list_channels()}"
            )

        # Create config object
        config = self._create_config(spec.channel_type, spec.config or {})

        # Create retry config if specified
        retry_cfg = None
        if spec.retry_config:
            retry_cfg = RetryConfig(**spec.retry_config)

        # Create channel instance
        channel = factory(config, self.message_bus)
        if retry_cfg:
            channel.retry_config = retry_cfg

        self._channels[spec.channel_type] = channel
        logger.info(f"Added channel: {spec.channel_type}")

        # Auto-start if manager is running
        if self._running:
            await channel.start()

        return channel

    def _create_config(self, channel_type: str, config_dict: dict[str, Any]) -> BaseChannelConfig:
        """Create a config object for a channel type."""
        # Import the channel module to get its config class
        try:
            module = importlib.import_module(f"dawei.channels.{channel_type}")
            config_class = getattr(module, "Config", BaseChannelConfig)
        except (ImportError, AttributeError):
            config_class = BaseChannelConfig

        return config_class(**config_dict)

    async def remove_channel(self, channel_type: str) -> None:
        """Remove a channel instance.

        Args:
            channel_type: Channel type to remove
        """
        if channel_type not in self._channels:
            logger.warning(f"Channel not found: {channel_type}")
            return

        channel = self._channels[channel_type]
        if channel.is_running:
            await channel.stop()

        del self._channels[channel_type]
        logger.info(f"Removed channel: {channel_type}")

    async def start_all(self) -> None:
        """Start all registered channels."""
        if self._running:
            logger.warning("ChannelManager already running")
            return

        logger.info(f"Starting {len(self._channels)} channels")
        self._running = True

        # Start all channels
        start_tasks = []
        for channel_type, channel in self._channels.items():
            start_tasks.append(self._start_channel_safely(channel_type, channel))

        await asyncio.gather(*start_tasks, return_exceptions=True)

        # Start health check loop
        self._health_check_task = asyncio.create_task(self._health_check_loop())

    async def _start_channel_safely(self, channel_type: str, channel: BaseChannel) -> None:
        """Start a channel with error handling."""
        try:
            await channel.start()
            logger.info(f"Channel started: {channel_type}")
        except Exception as e:
            logger.error(f"Failed to start channel {channel_type}: {e}")

    async def stop_all(self) -> None:
        """Stop all channels gracefully."""
        if not self._running:
            return

        logger.info("Stopping all channels")
        self._running = False

        # Stop health check loop
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass

        # Stop all channels
        stop_tasks = []
        for channel_type, channel in self._channels.items():
            stop_tasks.append(self._stop_channel_safely(channel_type, channel))

        await asyncio.gather(*stop_tasks, return_exceptions=True)

    async def _stop_channel_safely(self, channel_type: str, channel: BaseChannel) -> None:
        """Stop a channel with error handling."""
        try:
            await channel.stop()
            logger.info(f"Channel stopped: {channel_type}")
        except Exception as e:
            logger.error(f"Error stopping channel {channel_type}: {e}")

    async def get_channel(self, channel_type: str) -> BaseChannel | None:
        """Get a channel instance by type.

        Args:
            channel_type: Channel type identifier

        Returns:
            Channel instance or None if not found
        """
        return self._channels.get(channel_type)

    def list_channels(self) -> list[str]:
        """List all active channel types."""
        return list(self._channels.keys())

    async def health_check_all(self) -> dict[str, ChannelHealth]:
        """Check health of all channels.

        Returns:
            Dict mapping channel type to health status
        """
        results = {}
        for channel_type, channel in self._channels.items():
            try:
                health = await channel.health_check()
                results[channel_type] = health
            except Exception as e:
                logger.error(f"Health check failed for {channel_type}: {e}")
                results[channel_type] = ChannelHealth(
                    healthy=False, message=f"Health check error: {e}"
                )
        return results

    async def _health_check_loop(self) -> None:
        """Periodic health check loop."""
        while self._running:
            try:
                await asyncio.sleep(60)  # Check every 60 seconds
                health_results = await self.health_check_all()

                for channel_type, health in health_results.items():
                    if not health.healthy:
                        logger.warning(
                            f"Channel {channel_type} unhealthy: {health.message}"
                        )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in health check loop: {e}")

    @property
    def is_running(self) -> bool:
        """Check if the manager is running."""
        return self._running

    @property
    def channel_count(self) -> int:
        """Get the number of registered channels."""
        return len(self._channels)


def _ensure_channels_registered() -> None:
    """Ensure all channel packages are imported and registered.

    This function triggers lazy imports of all channel packages,
    which causes their @register_channel decorators to run.
    """
    # Get the channels package directory
    channels_dir = Path(__file__).parent

    # Find all subdirectories that might be channel packages
    for item in channels_dir.iterdir():
        if not item.is_dir() or item.name.startswith("_") or item.name.startswith("."):
            continue

        # Check if it's a Python package
        init_file = item / "__init__.py"
        if init_file.exists():
            # Import the package (triggers registration)
            try:
                module_name = f"dawei.channels.{item.name}"
                if module_name not in ChannelRegistry._factories:
                    importlib.import_module(module_name)
            except Exception as e:
                logger.debug(f"Could not import channel package {item.name}: {e}")
