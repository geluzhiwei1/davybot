"""Email channel implementation for DavyBot.

This channel integrates with email via IMAP/SMTP:
- Polling-based message reception (IMAP)
- HTML email formatting
- Attachment handling
- Thread support via subject matching

Configuration:
    imap_server: IMAP server address
    imap_port: IMAP port (default: 993)
    smtp_server: SMTP server address
    smtp_port: SMTP port (default: 587)
    username: Email username
    password: Email password or app-specific password
    use_tls: Use TLS for connections (default: True)
    allowed_senders: Optional list of allowed email addresses
    text_chunk_limit: Max message length (default: 999999)

Environment variables:
    EMAIL_IMAP_SERVER: IMAP server (overrides config)
    EMAIL_SMTP_SERVER: SMTP server (overrides config)
    EMAIL_USERNAME: Email username (overrides config)
    EMAIL_PASSWORD: Email password (overrides config)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from dawei.channels import (
    BaseChannelConfig,
    ChannelCapabilities,
    ChannelHealth,
    SimplePollingChannel,
    register_channel,
)

logger = logging.getLogger(__name__)


@dataclass
class Config(BaseChannelConfig):
    """Email channel configuration."""

    imap_server: str = ""
    imap_port: int = 993
    smtp_server: str = ""
    smtp_port: int = 587
    username: str = ""
    password: str = ""
    use_tls: bool = True
    allowed_senders: set[str] | None = None
    text_chunk_limit: int = 999_999


@register_channel("email")
class EmailChannel(SimplePollingChannel):
    """Email channel implementation using IMAP/SMTP.

    This is a stub implementation. The full implementation would:
    - Connect to IMAP server for receiving
    - Connect to SMTP server for sending
    - Poll for new messages periodically
    - Parse email content and attachments
    - Handle threading via subject matching
    """

    channel_type: str = "email"
    capabilities = ChannelCapabilities(
        format_type="html",
        max_text_length=999_999,
        media_send=True,
        media_receive=True,
        html=True,
        chat_types=("direct",),
    )
    config_class = Config
    poll_interval_s = 30.0  # Poll every 30 seconds
    max_empty_polls = 5

    def __init__(self, config: Config, *args: Any, **kwargs: Any) -> None:
        super().__init__(config, *args, **kwargs)
        self.config: Config = config
        self._last_uid = 0

    async def _start(self) -> None:
        """Start email polling."""
        await super()._start()
        logger.info("Email channel started (stub implementation)")

    async def _stop(self) -> None:
        """Stop email polling."""
        await super()._stop()
        logger.info("Email channel stopped")

    async def _health_check(self) -> ChannelHealth:
        """Check email server health."""
        # In full implementation, this would check IMAP/SMTP connectivity
        return ChannelHealth(healthy=True, message="Email servers OK")

    async def send_message(
        self,
        chat_id: str,
        content: str,
        reply_to: str | None = None,
        media: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Send email message.

        Args:
            chat_id: Recipient email address
            content: HTML content
            reply_to: Optional message ID (In-Reply-To header)
            media: Optional attachment file paths
            metadata: Optional metadata (subject, cc, bcc, etc.)
        """
        # Convert Markdown to HTML
        html_content = self.format_content(content)

        # In full implementation, this would send via SMTP
        logger.debug(
            f"Sending email to {chat_id} "
            f"({len(html_content)} chars, {len(media or [])} attachments)"
        )

    async def fetch_updates(self) -> list[Any]:
        """Fetch new emails from IMAP server.

        Returns:
            List of email messages
        """
        # In full implementation, this would:
        # 1. Connect to IMAP server
        # 2. Search for messages since last UID
        # 3. Fetch message content
        # 4. Parse attachments
        # 5. Return list of message objects

        return []  # Stub: no messages

    async def _process_updates(self, updates: list[Any]) -> None:
        """Process a batch of email updates.

        Args:
            updates: List of email messages
        """
        for email_msg in updates:
            await self._handle_email(email_msg)

    async def _handle_email(self, email_msg: Any) -> None:
        """Handle incoming email message.

        Args:
            email_msg: Email message object
        """
        # Extract sender
        sender_id = email_msg.get("from", "")

        # Check if allowed
        if self.config.allowed_senders and sender_id not in self.config.allowed_senders:
            logger.debug(f"Sender not allowed: {sender_id}")
            return

        # Extract content
        subject = email_msg.get("subject", "")
        body = email_msg.get("body", "")

        # Extract attachments
        media = []
        for attachment in email_msg.get("attachments", []):
            media.append(attachment.get("filename", ""))

        # Email is always direct (1:1)
        is_group = False
        was_mentioned = True  # Always process emails

        # Use sender as chat_id (email thread)
        chat_id = sender_id

        # Receive the message
        await self.receive_incoming(
            sender_id=sender_id,
            chat_id=chat_id,
            content=f"Subject: {subject}\n\n{body}",
            message_id=email_msg.get("message_id", ""),
            media=media,
            metadata=email_msg,
            is_group=is_group,
            was_mentioned=was_mentioned,
        )


__all__ = ["EmailChannel", "Config"]
