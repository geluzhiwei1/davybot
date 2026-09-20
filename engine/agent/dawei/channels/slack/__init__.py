"""Slack channel implementation for DavyBot.

This channel integrates with the Slack Web API:
- Webhook-based message reception
- Slack mrkdwn formatting
    - Thread support
- App mentions and commands
- File uploads and downloads
- Block Kit for rich messages

Configuration:
    bot_token: Slack bot token (xoxb-)
    signing_secret: Slack signing secret for webhook verification
    app_token: Slack app-level token (for socket mode, optional)
    allowed_teams: Optional list of allowed team IDs
    allowed_channels: Optional list of allowed channel IDs
    text_chunk_limit: Max message length (default: 4000)

Environment variables:
    SLACK_BOT_TOKEN: Bot token (overrides config)
    SLACK_SIGNING_SECRET: Signing secret (overrides config)
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
    """Slack channel configuration."""

    bot_token: str = ""
    signing_secret: str = ""
    app_token: str = ""
    allowed_teams: set[str] | None = None
    allowed_channels: set[str] | None = None
    text_chunk_limit: int = 4000


@register_channel("slack")
class SlackChannel(WebhookChannel):
    """Slack Web API channel implementation.

    This is a stub implementation. The full implementation would:
    - Verify webhook signatures
    - Handle events API payloads
    - Send messages via Web API
    - Handle slash commands
    - Support threads
    - Handle file uploads
    - Use Block Kit for rich messages
    """

    channel_type: str = "slack"
    capabilities = ChannelCapabilities(
        format_type="slack_mrkdwn",
        max_text_length=4000,
        threading=True,
        reactions=True,
        media_send=True,
        media_receive=True,
        groups=True,
        mentions=True,
        chat_types=("direct", "group", "thread"),
        edit=True,
        unsend=True,
        native_commands=True,
    )
    config_class = Config
    webhook_path = "/slack"
    webhook_secret = ""  # Set from config.signing_secret

    def __init__(self, config: Config, *args: Any, **kwargs: Any) -> None:
        super().__init__(config, *args, **kwargs)
        self.config: Config = config
        self.webhook_secret = config.signing_secret

    async def _start(self) -> None:
        """Start Slack webhook handler."""
        logger.info("Slack channel started (stub implementation)")

    async def _stop(self) -> None:
        """Stop Slack webhook handler."""
        logger.info("Slack channel stopped")

    async def _health_check(self) -> ChannelHealth:
        """Check Slack API health."""
        # In full implementation, this would call auth.test API
        return ChannelHealth(healthy=True, message="Slack API OK")

    async def send_message(
        self,
        chat_id: str,
        content: str,
        reply_to: str | None = None,
        media: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Send message to Slack.

        Args:
            chat_id: Slack channel ID
            content: Markdown content (will be converted to mrkdwn)
            reply_to: Optional thread timestamp to reply to
            media: Optional file URLs/paths
            metadata: Optional metadata (blocks, attachments, etc.)
        """
        # Convert Markdown to Slack mrkdwn
        mrkdwn_content = self.format_content(content)

        # In full implementation, this would call chat.postMessage API
        logger.debug(
            f"Sending message to Slack channel {chat_id} "
            f"({len(mrkdwn_content)} chars)"
        )

    async def _verify_webhook(
        self,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> bool:
        """Verify Slack webhook signature."""
        # In full implementation, this would verify the X-Slack-Signature header
        return True

    async def _process_webhook(
        self,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> None:
        """Process incoming Slack webhook event.

        Args:
            payload: Slack event data
            headers: HTTP headers
        """
        event_type = payload.get("type", "")
        event = payload.get("event", {})

        if event_type == "url_verification":
            # URL verification challenge
            return
        elif event_type == "event_callback":
            await self._handle_event(event)

    async def _handle_event(self, event: dict[str, Any]) -> None:
        """Handle Slack event."""
        event_type = event.get("type", "")

        if event_type == "message":
            await self._handle_message(event)
        elif event_type == "app_mention":
            await self._handle_app_mention(event)

    async def _handle_message(self, event: dict[str, Any]) -> None:
        """Handle incoming Slack message."""
        user = event.get("user", "")
        channel = event.get("channel", "")
        team = event.get("team", "")
        text = event.get("text", "")
        thread_ts = event.get("thread_ts", "")
        subtype = event.get("subtype", "")

        # Skip bot messages and message changed events
        if subtype in ("bot_message", "message_changed"):
            return

        # Check if allowed
        if self.config.allowed_teams and team not in self.config.allowed_teams:
            logger.debug(f"Team not allowed: {team}")
            return

        if self.config.allowed_channels and channel not in self.config.allowed_channels:
            logger.debug(f"Channel not allowed: {channel}")
            return

        # Extract files
        media = []
        for file in event.get("files", []):
            media.append(file.get("url_private", ""))

        # Check if this is a thread
        is_thread = bool(thread_ts)
        chat_id = f"{channel}:{thread_ts}" if is_thread else channel

        # Check if bot was mentioned
        was_mentioned = f"<@{self.config.bot_token}>" in text  # Simplified

        # Receive the message
        await self.receive_incoming(
            sender_id=user,
            chat_id=chat_id,
            content=text,
            message_id=event.get("ts", ""),
            media=media,
            metadata=event,
            is_group=True,  # All Slack channels are "groups" except DMs
            was_mentioned=was_mentioned,
        )

    async def _handle_app_mention(self, event: dict[str, Any]) -> None:
        """Handle app mention event."""
        # App mentions are similar to regular messages
        await self._handle_message(event)


__all__ = ["SlackChannel", "Config"]
