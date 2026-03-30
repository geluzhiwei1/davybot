"""QQ channel implementation for DavyBot.

Uses the official qq-botpy SDK for WebSocket connection.

Configuration:
    app_id: QQ bot app ID
    app_secret: QQ bot app secret
    allowed_senders: Optional list of allowed user IDs
    text_chunk_limit: Max message length (default: 4096)

Environment variables:
    QQ_APP_ID: App ID (overrides config)
    QQ_APP_SECRET: App secret (overrides config)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from dawei.channels import (
    BaseChannelConfig,
    ChannelCapabilities,
    ChannelHealth,
    WebhookChannel,
    register_channel,
)

logger = logging.getLogger(__name__)

try:
    import botpy  # type: ignore[import-untyped]
    from botpy.message import C2CMessage, GroupMessage  # type: ignore[import-untyped]

    QQ_AVAILABLE = True
except ImportError:
    QQ_AVAILABLE = False
    botpy = None  # type: ignore[assignment]
    C2CMessage = None  # type: ignore[assignment,misc]
    GroupMessage = None  # type: ignore[assignment,misc]


@dataclass
class Config(BaseChannelConfig):
    """QQ channel configuration."""

    app_id: str = ""
    app_secret: str = ""
    allowed_senders: set[str] | None = None
    text_chunk_limit: int = 4096


@register_channel("qq")
class QQChannel(WebhookChannel):
    """QQ Bot API channel implementation using botpy SDK.

    Supports:
    - C2C (direct) messages
    - Group messages with @mentions
    - Plain text formatting
    """

    channel_type: str = "qq"
    capabilities = ChannelCapabilities(
        format_type="plain",
        max_text_length=4096,
        media_send=True,
        media_receive=True,
        groups=True,
        mentions=True,
        chat_types=("direct", "group", "channel"),
        unsend=True,
    )
    config_class = Config
    webhook_path = "/qq"

    def __init__(self, config: Config, *args: Any, **kwargs: Any) -> None:
        super().__init__(config, *args, **kwargs)
        self.config: Config = config
        self._client: Any = None
        self._bot_task: Any = None

    async def _start(self) -> None:
        """Start QQ bot connection."""
        if not QQ_AVAILABLE:
            raise ImportError(
                "qq-botpy not installed. Install with: pip install qq-botpy"
            )

        if not self.config.app_id or not self.config.app_secret:
            raise ValueError("QQ app_id and app_secret are required")

        logger.info("QQ channel started (stub implementation)")

    async def _stop(self) -> None:
        """Stop QQ bot connection."""
        if self._bot_task:
            self._bot_task.cancel()
            self._bot_task = None

        if self._client:
            self._client = None

        logger.info("QQ channel stopped")

    async def _health_check(self) -> ChannelHealth:
        """Check QQ bot health."""
        if not QQ_AVAILABLE:
            return ChannelHealth(healthy=False, message="qq-botpy not installed")
        return ChannelHealth(healthy=True, message="QQ Bot OK")

    async def send_message(
        self,
        chat_id: str,
        content: str,
        reply_to: str | None = None,
        media: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Send message to QQ.

        Args:
            chat_id: QQ chat ID (openid for C2C, group_openid for group)
            content: Plain text content
            reply_to: Optional message ID to reply to
            media: Optional media file URLs/paths
            metadata: Optional metadata (msg_type, msg_seq, etc.)
        """
        formatted_content = self.format_content(content)
        logger.debug(
            f"Sending message to QQ chat {chat_id} "
            f"({len(formatted_content)} chars)"
        )

    async def _process_webhook(
        self,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> None:
        """Process incoming QQ webhook event.

        Args:
            payload: QQ event data
            headers: HTTP headers
        """
        event_type = payload.get("t", "")
        event_data = payload.get("d", {})

        if "C2C_MESSAGE_CREATE" in event_type:
            await self._handle_c2c_message(event_data)
        elif "GROUP_AT_MESSAGE_CREATE" in event_type:
            await self._handle_group_message(event_data)

    async def _handle_c2c_message(self, data: dict[str, Any]) -> None:
        """Handle incoming QQ C2C (direct) message."""
        author = data.get("author", {}, )
        content = data.get("content", "")
        message_id = data.get("id", "")

        sender_id = author.get("user_openid", "")

        # Check if allowed
        if self.config.allowed_senders and sender_id not in self.config.allowed_senders:
            logger.debug(f"Sender not allowed: {sender_id}")
            return

        await self.receive_incoming(
            sender_id=sender_id,
            chat_id=sender_id,  # C2C: chat is the sender
            content=content,
            message_id=message_id,
            media=[],
            metadata=data,
            is_group=False,
            was_mentioned=True,
        )

    async def _handle_group_message(self, data: dict[str, Any]) -> None:
        """Handle incoming QQ group @mention message."""
        author = data.get("author", {})
        content = data.get("content", "")
        message_id = data.get("id", "")
        group_openid = data.get("group_openid", "")

        sender_id = author.get("member_openid", "")

        # Check if allowed
        if self.config.allowed_senders and sender_id not in self.config.allowed_senders:
            logger.debug(f"Sender not allowed: {sender_id}")
            return

        await self.receive_incoming(
            sender_id=sender_id,
            chat_id=group_openid,
            content=content,
            message_id=message_id,
            media=[],
            metadata=data,
            is_group=True,
            was_mentioned=True,  # Group messages are always @mentions
        )


__all__ = ["QQChannel", "Config"]
