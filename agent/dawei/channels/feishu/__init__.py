"""Feishu (Lark) channel implementation for DavyBot.

This channel integrates with the Feishu Open API:
- Webhook-based message reception
- Markdown formatting support
- Card messages for rich content
- Group chat support with @ mentions
- File uploads and downloads

Configuration:
    app_id: Feishu app ID
    app_secret: Feishu app secret
    encrypt_key: Optional encryption key (for encrypted events)
    verification_token: Optional verification token
    allowed_tenants: Optional list of allowed tenant IDs
    allowed_chats: Optional list of allowed chat IDs
    text_chunk_limit: Max message length (default: 4096)

Environment variables:
    FEISHU_APP_ID: App ID (overrides config)
    FEISHU_APP_SECRET: App secret (overrides config)
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
    """Feishu channel configuration."""

    app_id: str = ""
    app_secret: str = ""
    encrypt_key: str = ""
    verification_token: str = ""
    allowed_tenants: set[str] | None = None
    allowed_chats: set[str] | None = None
    text_chunk_limit: int = 4096


@register_channel("feishu")
class FeishuChannel(WebhookChannel):
    """Feishu Open API channel implementation.

    This is a stub implementation. The full implementation would:
    - Verify event signatures
    - Handle event callbacks
    - Send messages via API
    - Handle card messages
    - Support rich text formatting
    - Handle file uploads
    """

    channel_type: str = "feishu"
    capabilities = ChannelCapabilities(
        format_type="markdown",
        max_text_length=4096,
        reactions=True,
        media_send=True,
        media_receive=True,
        voice=True,
        stickers=True,
        groups=True,
        mentions=True,
        markdown=True,
        chat_types=("direct", "group"),
        edit=True,
        unsend=True,
    )
    config_class = Config
    webhook_path = "/feishu"
    webhook_secret = ""  # Set from config.verification_token

    def __init__(self, config: Config, *args: Any, **kwargs: Any) -> None:
        super().__init__(config, *args, **kwargs)
        self.config: Config = config
        self.webhook_secret = config.verification_token

    async def _start(self) -> None:
        """Start Feishu webhook handler."""
        logger.info("Feishu channel started (stub implementation)")

    async def _stop(self) -> None:
        """Stop Feishu webhook handler."""
        logger.info("Feishu channel stopped")

    async def _health_check(self) -> ChannelHealth:
        """Check Feishu API health."""
        # In full implementation, this would call a test API
        return ChannelHealth(healthy=True, message="Feishu API OK")

    async def send_message(
        self,
        chat_id: str,
        content: str,
        reply_to: str | None = None,
        media: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Send message to Feishu.

        Args:
            chat_id: Feishu chat ID
            content: Markdown content
            reply_to: Optional message ID to reply to
            media: Optional file URLs/paths
            metadata: Optional metadata (card, msg_type, etc.)
        """
        # Feishu supports Markdown natively
        formatted_content = self.format_content(content)

        # In full implementation, this would call message.send API
        logger.debug(
            f"Sending message to Feishu chat {chat_id} "
            f"({len(formatted_content)} chars)"
        )

    async def _verify_webhook(
        self,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> bool:
        """Verify Feishu webhook signature."""
        # In full implementation, this would verify the signature
        return True

    async def _process_webhook(
        self,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> None:
        """Process incoming Feishu webhook event.

        Args:
            payload: Feishu event data
            headers: HTTP headers
        """
        # Feishu events are JSON strings in the POST body
        if isinstance(payload, str):
            import json

            payload = json.loads(payload)

        event_type = payload.get("type", "")
        if event_type == "url_verification":
            # URL verification challenge
            return
        elif event_type == "event_callback":
            await self._handle_event(payload.get("event", {}))

    async def _handle_event(self, event: dict[str, Any]) -> None:
        """Handle Feishu event."""
        event_type = event.get("type", "")

        if event_type == "message":
            await self._handle_message(event)

    async def _handle_message(self, event: dict[str, Any]) -> None:
        """Handle incoming Feishu message."""
        sender = event.get("sender", {})
        chat_id = event.get("chat_id", "")
        tenant_key = event.get("tenant_key", "")
        content = event.get("content", {})
        message_id = event.get("message_id", "")

        sender_id = sender.get("sender_id", "")
        msg_type = content.get("message_type", "")

        # Check if allowed
        if self.config.allowed_tenants and tenant_key not in self.config.allowed_tenants:
            logger.debug(f"Tenant not allowed: {tenant_key}")
            return

        if self.config.allowed_chats and chat_id not in self.config.allowed_chats:
            logger.debug(f"Chat not allowed: {chat_id}")
            return

        # Extract text content
        text = ""
        if msg_type == "text":
            text = content.get("text", "")

        # Extract media
        media = []
        if msg_type == "image":
            media.append(content.get("image_key", ""))
        elif msg_type == "file":
            media.append(content.get("file_key", ""))
        elif msg_type == "audio":
            media.append(content.get("audio_key", ""))

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
            is_group=True,  # Most Feishu chats are groups
            was_mentioned=was_mentioned,
        )


__all__ = ["FeishuChannel", "Config"]
