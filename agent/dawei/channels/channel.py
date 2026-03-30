"""Base channel class and middleware pipeline.

Channels are adapters between external chat platforms (Telegram, Discord, Slack, etc.)
and the internal MessageBus. Each channel implements:
- Async lifecycle (start, stop, health_check)
- Message transformation (platform format <-> InboundMessage/OutboundMessage)
- Webhook handling or polling
- Error handling and retry logic
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from .bus import InboundMessage, MessageBus, OutboundMessage
from .capabilities import ChannelCapabilities
from .config import BaseChannelConfig
from .formatter import UnifiedFormatter
from .retry import RetryConfig, retry_async

logger = logging.getLogger(__name__)

MiddlewareFn = Callable[[InboundMessage], Awaitable[InboundMessage | None]]
OutboundMiddlewareFn = Callable[[OutboundMessage], Awaitable[OutboundMessage | None]]


@dataclass
class ChannelHealth:
    """Health check result for a channel."""

    healthy: bool
    message: str = ""
    latency_ms: float = 0.0
    metadata: dict[str, Any] | None = None


class BaseChannel(ABC):
    """Base class for all channel implementations.

    Each channel (Telegram, Discord, Slack, etc.) subclasses this and implements
    the abstract methods. The framework handles lifecycle, message routing,
    middleware, health checks, and error recovery.
    """

    # Class-level attributes (set by subclasses)
    channel_type: str = ""
    capabilities: ChannelCapabilities = ChannelCapabilities()
    config_class: type[BaseChannelConfig] = BaseChannelConfig

    def __init__(
        self,
        config: BaseChannelConfig,
        message_bus: MessageBus,
        retry_config: RetryConfig | None = None,
    ) -> None:
        """Initialize the channel.

        Args:
            config: Channel-specific configuration
            message_bus: Shared message bus for inbound/outbound messages
            retry_config: Optional retry configuration for API calls
        """
        self.config = config
        self.message_bus = message_bus
        self.retry_config = retry_config
        self._formatter = UnifiedFormatter.for_channel(self.capabilities.format_type)
        self._running = False
        self._middleware: list[MiddlewareFn] = []
        self._outbound_middleware: list[OutboundMiddlewareFn] = []

    # Lifecycle

    async def start(self) -> None:
        """Start the channel (webhook server, polling loop, etc.)."""
        if self._running:
            logger.warning(f"{self.channel_type} channel already running")
            return
        logger.info(f"Starting {self.channel_type} channel")
        await self._start()
        self._running = True

        # Subscribe to outbound messages for this channel
        self.message_bus.subscribe_outbound(self.channel_type, self._handle_outbound)

    @abstractmethod
    async def _start(self) -> None:
        """Channel-specific startup logic (subclass implements)."""
        pass

    async def stop(self) -> None:
        """Stop the channel gracefully."""
        if not self._running:
            return
        logger.info(f"Stopping {self.channel_type} channel")
        self._running = False
        await self._stop()

    @abstractmethod
    async def _stop(self) -> None:
        """Channel-specific shutdown logic (subclass implements)."""
        pass

    # Health check

    async def health_check(self) -> ChannelHealth:
        """Check if the channel is healthy.

        Returns:
            ChannelHealth with status, message, and optional latency/metadata
        """
        if not self._running:
            return ChannelHealth(healthy=False, message="Channel not running")
        return await self._health_check()

    @abstractmethod
    async def _health_check(self) -> ChannelHealth:
        """Channel-specific health check (subclass implements)."""
        pass

    # Inbound message handling (platform -> agent)

    async def receive_incoming(
        self,
        sender_id: str,
        chat_id: str,
        content: str,
        message_id: str = "",
        media: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        is_group: bool = False,
        was_mentioned: bool = True,
    ) -> None:
        """Receive a message from the platform and publish to the message bus.

        This is typically called by the webhook handler or polling loop.

        Args:
            sender_id: Platform-specific user ID
            chat_id: Platform-specific chat ID
            content: Message text content
            message_id: Platform-specific message ID
            media: List of media file URLs/paths
            metadata: Additional platform-specific data
            is_group: Whether this is a group chat
            was_mentioned: Whether the bot was mentioned (for groups)
        """
        # Apply inbound middleware pipeline
        msg = InboundMessage(
            channel=self.channel_type,
            sender_id=sender_id,
            chat_id=chat_id,
            content=content,
            message_id=message_id,
            media=media or [],
            metadata=metadata or {},
            is_group=is_group,
            was_mentioned=was_mentioned,
        )

        for middleware in self._middleware:
            try:
                result = await middleware(msg)
                if result is None:
                    # Middleware filtered out the message
                    logger.debug(f"Message filtered by middleware: {message_id}")
                    return
                msg = result
            except Exception as e:
                logger.error(f"Middleware error in {self.channel_type}: {e}")
                # Continue processing despite middleware error

        # Publish to message bus
        await self.message_bus.publish_inbound(msg)
        logger.debug(
            f"Published inbound message from {self.channel_type}:{chat_id} "
            f"({len(content)} chars)"
        )

    # Outbound message handling (agent -> platform)

    async def _handle_outbound(self, msg: OutboundMessage) -> None:
        """Handle outbound message from the message bus (internal)."""
        try:
            # Apply outbound middleware pipeline
            processed_msg = msg
            for middleware in self._outbound_middleware:
                try:
                    result = await middleware(processed_msg)
                    if result is None:
                        # Middleware filtered out the message
                        logger.debug(f"Outbound message filtered by middleware")
                        return
                    processed_msg = result
                except Exception as e:
                    logger.error(f"Outbound middleware error: {e}")
                    # Continue processing

            # Send to platform
            await self.send_message(
                chat_id=processed_msg.chat_id,
                content=processed_msg.content,
                reply_to=processed_msg.reply_to,
                media=processed_msg.media,
                metadata=processed_msg.metadata,
            )
        except Exception as e:
            logger.error(f"Error sending outbound message on {self.channel_type}: {e}")
            raise

    @abstractmethod
    async def send_message(
        self,
        chat_id: str,
        content: str,
        reply_to: str | None = None,
        media: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Send a message to the platform (subclass implements).

        Args:
            chat_id: Platform-specific chat ID
            content: Message content (Markdown format)
            reply_to: Optional message ID to reply to
            media: List of media file URLs/paths
            metadata: Additional platform-specific data
        """
        pass

    # Utility methods

    def format_content(self, markdown: str) -> str:
        """Convert Markdown to platform-native format."""
        return self._formatter.format(markdown)

    def add_middleware(self, fn: MiddlewareFn) -> None:
        """Add inbound middleware to the processing pipeline."""
        self._middleware.append(fn)

    def add_outbound_middleware(self, fn: OutboundMiddlewareFn) -> None:
        """Add outbound middleware to the processing pipeline."""
        self._outbound_middleware.append(fn)

    async def _retry_if_needed(
        self,
        fn: Callable[[], Awaitable[Any]],
        operation: str = "operation",
    ) -> Any:
        """Execute an async function with retry logic if configured."""
        if self.retry_config is None:
            return await fn()

        return await retry_async(
            fn,
            self.retry_config,
            on_retry=lambda info: logger.warning(
                f"{self.channel_type} {operation} failed (attempt {info.attempt}): "
                f"{info.error}. Retrying in {info.delay_s:.1f}s..."
            ),
            label=f"{self.channel_type}.{operation}",
        )

    @property
    def is_running(self) -> bool:
        """Check if the channel is currently running."""
        return self._running


class SimplePollingChannel(BaseChannel):
    """Base class for channels that use polling instead of webhooks.

    Subclasses implement fetch_updates() which returns a list of updates.
    The base class handles the polling loop and error recovery.
    """

    poll_interval_s: float = 1.0
    max_empty_polls: int = 10

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._poll_task: asyncio.Task[None] | None = None
        self._empty_poll_count = 0

    async def _start(self) -> None:
        """Start the polling loop."""
        self._poll_task = asyncio.create_task(self._poll_loop())

    async def _stop(self) -> None:
        """Stop the polling loop."""
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass

    async def _poll_loop(self) -> None:
        """Poll for updates continuously."""
        while self._running:
            try:
                updates = await self._retry_if_needed(
                    self.fetch_updates,
                    operation="fetch_updates",
                )

                if updates:
                    await self._process_updates(updates)
                    self._empty_poll_count = 0
                else:
                    self._empty_poll_count += 1
                    if self._empty_poll_count >= self.max_empty_polls:
                        # Back off on empty polls
                        await asyncio.sleep(self.poll_interval_s * 5)
                        self._empty_poll_count = 0
                    else:
                        await asyncio.sleep(self.poll_interval_s)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in polling loop: {e}")
                await asyncio.sleep(self.poll_interval_s)

    @abstractmethod
    async def fetch_updates(self) -> list[Any]:
        """Fetch updates from the platform (subclass implements).

        Returns:
            List of platform-specific update objects
        """
        pass

    @abstractmethod
    async def _process_updates(self, updates: list[Any]) -> None:
        """Process a batch of updates (subclass implements)."""
        pass


class WebhookChannel(BaseChannel):
    """Base class for channels that use webhooks.

    Subclasses implement handle_webhook() which processes incoming webhook payloads.
    The base class provides a webhook handler wrapper with error handling.
    """

    webhook_path: str = ""
    webhook_secret: str | None = None

    async def handle_webhook(
        self,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> dict[str, Any]:
        """Handle an incoming webhook request.

        Args:
            payload: Webhook payload JSON
            headers: HTTP headers

        Returns:
            Response dict (will be JSON-serialized)
        """
        try:
            # Verify webhook secret if configured
            if self.webhook_secret:
                if not await self._verify_webhook(payload, headers):
                    logger.warning(f"Webhook signature verification failed")
                    return {"status": "error", "message": "Invalid signature"}

            # Process the webhook
            await self._process_webhook(payload, headers)
            return {"status": "ok"}
        except Exception as e:
            logger.error(f"Error handling webhook: {e}")
            return {"status": "error", "message": str(e)}

    async def _verify_webhook(
        self,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> bool:
        """Verify webhook signature (subclass can override)."""
        return True

    @abstractmethod
    async def _process_webhook(
        self,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> None:
        """Process webhook payload (subclass implements)."""
        pass

    @abstractmethod
    async def _start(self) -> None:
        """Start webhook server (subclass implements)."""
        pass

    @abstractmethod
    async def _stop(self) -> None:
        """Stop webhook server (subclass implements)."""
        pass

    @abstractmethod
    async def _health_check(self) -> ChannelHealth:
        """Check webhook server health (subclass implements)."""
        pass
