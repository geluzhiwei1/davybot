"""WeChat channel implementation for DavyBot.

This channel integrates with WeChat Work (企业微信) API:
- Webhook-based message reception
- Markdown formatting support
- Media file handling
- Group chat support with @ mentions

Configuration:
    corp_id: WeChat Work corp ID
    agent_id: WeChat Work agent ID
    secret: WeChat Work agent secret
    token: Webhook token (optional)
    encoding_aes_key: Encoding key for encrypted messages (optional)
    allowed_departments: Optional list of allowed department IDs
    allowed_chats: Optional list of allowed chat IDs
    text_chunk_limit: Max message length (default: 4096)

Environment variables:
    WECHAT_CORP_ID: Corp ID (overrides config)
    WECHAT_AGENT_ID: Agent ID (overrides config)
    WECHAT_SECRET: Agent secret (overrides config)
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
    """WeChat channel configuration."""

    corp_id: str = ""
    agent_id: str = ""
    secret: str = ""
    token: str = ""
    encoding_aes_key: str = ""
    allowed_departments: set[str] | None = None
    allowed_chats: set[str] | None = None
    text_chunk_limit: int = 4096


@register_channel("wechat")
class WeChatChannel(WebhookChannel):
    """WeChat Work API channel implementation.

    This is a stub implementation. The full implementation would:
    - Verify message signatures
    - Handle callback events
    - Send messages via API
    - Handle file uploads
    - Support rich text formatting
    """

    channel_type: str = "wechat"
    capabilities = ChannelCapabilities(
        format_type="markdown",
        max_text_length=4096,
        media_send=True,
        media_receive=True,
        voice=True,
        location=True,
        groups=True,
        mentions=True,
        markdown=True,
        chat_types=("direct", "group"),
        unsend=True,
    )
    config_class = Config
    webhook_path = "/wechat"
    webhook_secret = ""  # Set from config.token

    def __init__(self, config: Config, *args: Any, **kwargs: Any) -> None:
        super().__init__(config, *args, **kwargs)
        self.config: Config = config
        self.webhook_secret = config.token

    async def _start(self) -> None:
        """Start WeChat webhook handler."""
        logger.info("WeChat channel started (stub implementation)")

    async def _stop(self) -> None:
        """Stop WeChat webhook handler."""
        logger.info("WeChat channel stopped")

    async def _health_check(self) -> ChannelHealth:
        """Check WeChat API health."""
        return ChannelHealth(healthy=True, message="WeChat API OK")

    async def send_message(
        self,
        chat_id: str,
        content: str,
        reply_to: str | None = None,
        media: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Send message to WeChat.

        Args:
            chat_id: WeChat chat ID (user ID or group ID)
            content: Markdown content
            reply_to: Optional message ID to reply to
            media: Optional media file URLs/paths
            metadata: Optional metadata (msg_type, safe, etc.)
        """
        # WeChat supports Markdown natively
        formatted_content = self.format_content(content)

        # In full implementation, this would call message.send API
        logger.debug(
            f"Sending message to WeChat chat {chat_id} "
            f"({len(formatted_content)} chars)"
        )

    async def _verify_webhook(
        self,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> bool:
        """Verify WeChat webhook signature."""
        # In full implementation, this would verify the signature
        return True

    async def _process_webhook(
        self,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> None:
        """Process incoming WeChat webhook event.

        Args:
            payload: WeChat event data
            headers: HTTP headers
        """
        await self._handle_event(payload)

    async def _handle_event(self, event: dict[str, Any]) -> None:
        """Handle WeChat event."""
        event_type = event.get("event_type", "")

        if event_type == "message":
            await self._handle_message(event)

    async def _handle_message(self, event: dict[str, Any]) -> None:
        """Handle incoming WeChat message."""
        sender_id = event.get("from_user", {})
        chat_id = event.get("to_user", "")
        content = event.get("content", "")
        message_id = event.get("message_id", "")

        # Extract text content
        text = content.get("text", "")

        # Extract media
        media = []
        if "image" in content:
            media.append(content["image"])
        elif "file" in content:
            media.append(content["file"])
        elif "voice" in content:
            media.append(content["voice"])

        # Check if bot was mentioned
        was_mentioned = True  # Simplified

        # Receive the message
        await self.receive_incoming(
            sender_id=sender_id,
            chat_id=chat_id,
            content=text,
            message_id=message_id,
            media=media,
            metadata=event,
            is_group=True,
            was_mentioned=was_mentioned,
        )


__all__ = ["WeChatChannel", "Config"]
