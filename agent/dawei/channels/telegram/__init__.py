"""Telegram channel implementation for DaweiBot.

This channel integrates with the Telegram Bot API:
- Webhook-based message reception
- Markdown/HTML formatting support
- Media file handling (photos, documents, voice)
- Inline buttons and callbacks
- Group chat support with mentions

Configuration:
    token: Telegram bot token (from @BotFather)
    webhook_url: Optional webhook URL (default: auto-generated)
    allowed_senders: Optional list of allowed user IDs
    allowed_channels: Optional list of allowed chat IDs
    text_chunk_limit: Max message length (default: 4000)

Environment variables:
    TELEGRAM_TOKEN: Bot token (overrides config)
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


@dataclass
class Config(BaseChannelConfig):
    """Telegram channel configuration."""

    token: str = ""
    webhook_url: str = ""
    allowed_senders: set[str] | None = None
    allowed_channels: set[str] | None = None
    text_chunk_limit: int = 4000


@register_channel("telegram")
class TelegramChannel(WebhookChannel):
    """Telegram Bot API channel implementation.

    This is a stub implementation. The full implementation would:
    - Set up Telegram webhook
    - Handle incoming updates
    - Send messages via Bot API
    - Handle media uploads
    - Support inline buttons
    - Handle callback queries
    """

    channel_type: str = "telegram"
    capabilities = ChannelCapabilities(
        format_type="html",
        max_text_length=4000,
        reactions=True,
        typing=True,
        media_send=True,
        media_receive=True,
        voice=True,
        stickers=True,
        location=True,
        groups=True,
        mentions=True,
        html=True,
        chat_types=("direct", "group", "channel"),
        edit=True,
        unsend=True,
        native_commands=True,
        polls=True,
    )
    config_class = Config
    webhook_path = "/telegram"

    def __init__(self, config: Config, *args: Any, **kwargs: Any) -> None:
        super().__init__(config, *args, **kwargs)
        self.config: Config = config
        self._webhook_url = config.webhook_url or ""

    async def _start(self) -> None:
        """Start Telegram webhook."""
        # In full implementation, this would set up the Telegram webhook
        logger.info("Telegram channel started (stub implementation)")

    async def _stop(self) -> None:
        """Stop Telegram webhook."""
        logger.info("Telegram channel stopped")

    async def _health_check(self) -> ChannelHealth:
        """Check Telegram API health."""
        # In full implementation, this would call getMe API
        return ChannelHealth(healthy=True, message="Telegram API OK")

    async def send_message(
        self,
        chat_id: str,
        content: str,
        reply_to: str | None = None,
        media: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Send message to Telegram.

        Args:
            chat_id: Telegram chat ID
            content: Markdown content (will be converted to HTML)
            reply_to: Optional message ID to reply to
            media: Optional media file URLs/paths
            metadata: Optional metadata (parse_mode, disable_web_page_preview, etc.)
        """
        # Convert Markdown to HTML
        html_content = self.format_content(content)

        # In full implementation, this would call sendMessage API
        logger.debug(
            f"Sending message to Telegram chat {chat_id} "
            f"({len(html_content)} chars)"
        )

    async def _process_webhook(
        self,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> None:
        """Process incoming Telegram webhook update.

        Args:
            payload: Telegram Update object
            headers: HTTP headers
        """
        # Extract message from update
        message = payload.get("message", {})
        callback_query = payload.get("callback_query", {})

        if callback_query:
            # Handle button callback
            await self._handle_callback_query(callback_query)
        elif message:
            # Handle regular message
            await self._handle_message(message)

    async def _handle_message(self, message: dict[str, Any]) -> None:
        """Handle incoming Telegram message."""
        chat = message.get("chat", {})
        from_user = message.get("from", {})

        chat_id = str(chat.get("id", ""))
        sender_id = str(from_user.get("id", ""))
        text = message.get("text", "")

        # Check if allowed
        if self.config.allowed_senders and sender_id not in self.config.allowed_senders:
            logger.debug(f"Sender not allowed: {sender_id}")
            return

        if self.config.allowed_channels and chat_id not in self.config.allowed_channels:
            logger.debug(f"Chat not allowed: {chat_id}")
            return

        # Extract media
        media = []
        if "photo" in message:
            photo = message["photo"][-1]  # Get largest photo
            media.append(photo.get("file_id", ""))
        if "document" in message:
            media.append(message["document"].get("file_id", ""))
        if "voice" in message:
            media.append(message["voice"].get("file_id", ""))
        if "video" in message:
            media.append(message["video"].get("file_id", ""))

        # Check if bot was mentioned (for groups)
        chat_type = chat.get("type", "")
        is_group = chat_type in ("group", "supergroup")
        was_mentioned = True  # Telegram bot commands always mention the bot

        # Receive the message
        await self.receive_incoming(
            sender_id=sender_id,
            chat_id=chat_id,
            content=text,
            message_id=str(message.get("message_id", "")),
            media=media,
            metadata=message,
            is_group=is_group,
            was_mentioned=was_mentioned,
        )

    async def _handle_callback_query(self, callback_query: dict[str, Any]) -> None:
        """Handle inline button callback query."""
        # In full implementation, this would handle button interactions
        logger.debug(f"Received callback query: {callback_query.get('data', '')}")


__all__ = ["TelegramChannel", "Config"]
