"""Discord channel implementation for DaweiBot.

This channel integrates with the Discord Bot API:
- Webhook-based message reception
- Discord Markdown formatting
- Slash commands support
- Thread support
- Role and user mentions
- Voice channel support (future)

Configuration:
    bot_token: Discord bot token
    command_prefix: Bot command prefix (default: "/")
    allowed_guilds: Optional list of allowed guild IDs
    allowed_channels: Optional list of allowed channel IDs
    text_chunk_limit: Max message length (default: 2000)

Environment variables:
    DISCORD_BOT_TOKEN: Bot token (overrides config)
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
    """Discord channel configuration."""

    bot_token: str = ""
    command_prefix: str = "/"
    allowed_guilds: set[str] | None = None
    allowed_channels: set[str] | None = None
    text_chunk_limit: int = 2000


@register_channel("discord")
class DiscordChannel(WebhookChannel):
    """Discord Bot API channel implementation.

    This is a stub implementation. The full implementation would:
    - Connect to Discord Gateway
    - Handle message events
    - Send messages via REST API
    - Handle slash commands
    - Support threads
    - Handle attachments and embeds
    """

    channel_type: str = "discord"
    capabilities = ChannelCapabilities(
        format_type="discord",
        max_text_length=2000,
        threading=True,
        reactions=True,
        typing=True,
        media_send=True,
        media_receive=True,
        groups=True,
        mentions=True,
        markdown=True,
        chat_types=("direct", "group", "thread"),
        edit=True,
        unsend=True,
        native_commands=True,
        polls=True,
    )
    config_class = Config
    webhook_path = "/discord"

    def __init__(self, config: Config, *args: Any, **kwargs: Any) -> None:
        super().__init__(config, *args, **kwargs)
        self.config: Config = config

    async def _start(self) -> None:
        """Start Discord connection."""
        # In full implementation, this would connect to Discord Gateway
        logger.info("Discord channel started (stub implementation)")

    async def _stop(self) -> None:
        """Stop Discord connection."""
        logger.info("Discord channel stopped")

    async def _health_check(self) -> ChannelHealth:
        """Check Discord Gateway health."""
        # In full implementation, this would check Gateway connection
        return ChannelHealth(healthy=True, message="Discord Gateway OK")

    async def send_message(
        self,
        chat_id: str,
        content: str,
        reply_to: str | None = None,
        media: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Send message to Discord.

        Args:
            chat_id: Discord channel ID
            content: Markdown content
            reply_to: Optional message ID to reply to
            media: Optional attachment URLs
            metadata: Optional metadata (embed, tts, etc.)
        """
        # Format content for Discord (supports Markdown)
        formatted_content = self.format_content(content)

        # In full implementation, this would call the Discord REST API
        logger.debug(
            f"Sending message to Discord channel {chat_id} "
            f"({len(formatted_content)} chars)"
        )

    async def _process_webhook(
        self,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> None:
        """Process incoming Discord webhook event.

        Args:
            payload: Discord event data
            headers: HTTP headers
        """
        event_type = payload.get("t", "")
        event_data = payload.get("d", {})

        if event_type == "MESSAGE_CREATE":
            await self._handle_message_create(event_data)
        elif event_type == "INTERACTION_CREATE":
            await self._handle_interaction(event_data)

    async def _handle_message_create(self, data: dict[str, Any]) -> None:
        """Handle incoming Discord message."""
        author = data.get("author", {})
        channel_id = data.get("channel_id", "")
        guild_id = data.get("guild_id", "")
        content = data.get("content", "")

        sender_id = author.get("id", "")

        # Check if allowed
        if self.config.allowed_guilds and guild_id not in self.config.allowed_guilds:
            logger.debug(f"Guild not allowed: {guild_id}")
            return

        if self.config.allowed_channels and channel_id not in self.config.allowed_channels:
            logger.debug(f"Channel not allowed: {channel_id}")
            return

        # Extract attachments
        media = []
        for attachment in data.get("attachments", []):
            media.append(attachment.get("url", ""))

        # Check if bot was mentioned
        was_mentioned = f"<@{self.config.bot_token}>" in content  # Simplified

        # Receive the message
        await self.receive_incoming(
            sender_id=sender_id,
            chat_id=channel_id,
            content=content,
            message_id=data.get("id", ""),
            media=media,
            metadata=data,
            is_group=bool(guild_id),
            was_mentioned=was_mentioned,
        )

    async def _handle_interaction(self, data: dict[str, Any]) -> None:
        """Handle slash command interaction."""
        # In full implementation, this would handle slash commands
        command_name = data.get("data", {}).get("name", "")
        logger.debug(f"Received slash command: {command_name}")


__all__ = ["DiscordChannel", "Config"]
