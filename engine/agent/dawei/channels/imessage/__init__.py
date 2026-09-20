"""iMessage channel implementation for DavyBot.

Uses imsg CLI via JSON-RPC for real-time message streaming.

Requirements:
- macOS only
- imsg CLI installed
- Full Disk Access permission
- Messages.app logged into iCloud

Configuration:
    allowed_senders: Optional list of allowed handles/phone numbers
    text_chunk_limit: Max message length (default: 999999)
    rpc_port: JSON-RPC port (default: 9010)

Environment variables:
    IMESSAGE_RPC_PORT: RPC port (overrides config)
"""

from __future__ import annotations

import asyncio
import json
import logging
import platform
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
    """iMessage channel configuration."""

    allowed_senders: set[str] | None = None
    text_chunk_limit: int = 999_999
    rpc_port: int = 9010


@register_channel("imessage")
class IMessageChannel(SimplePollingChannel):
    """iMessage channel using imsg CLI via JSON-RPC.

    Supports:
    - Direct and group messages
    - Plain text formatting
    - Media attachments (photos, files)
    - SMS fallback (via service="sms" option)
    """

    channel_type: str = "imessage"
    capabilities = ChannelCapabilities(
        format_type="plain",
        max_text_length=999_999,
        media_send=True,
        media_receive=True,
        voice=True,
        groups=True,
        reactions=False,
        chat_types=("direct", "group"),
    )
    config_class = Config
    poll_interval_s = 2.0
    max_empty_polls = 10

    def __init__(self, config: Config, *args: Any, **kwargs: Any) -> None:
        super().__init__(config, *args, **kwargs)
        self.config: Config = config
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._request_id = 0

    async def _start(self) -> None:
        """Start iMessage JSON-RPC connection."""
        if platform.system() != "Darwin":
            raise RuntimeError("iMessage channel requires macOS")

        await super()._start()
        logger.info("iMessage channel started")

    async def _stop(self) -> None:
        """Stop iMessage connection."""
        if self._writer:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:
                pass
            self._writer = None
            self._reader = None

        await super()._stop()
        logger.info("iMessage channel stopped")

    async def _health_check(self) -> ChannelHealth:
        """Check iMessage CLI health."""
        if platform.system() != "Darwin":
            return ChannelHealth(healthy=False, message="macOS required for iMessage")

        if not self._reader or not self._writer:
            return ChannelHealth(healthy=False, message="iMessage RPC not connected")

        return ChannelHealth(healthy=True, message="iMessage CLI connected")

    async def _rpc_call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Make a JSON-RPC call to imsg CLI.

        Args:
            method: RPC method name
            params: Optional parameters

        Returns:
            Response dict
        """
        if not self._writer or not self._reader:
            raise RuntimeError("iMessage RPC not connected")

        self._request_id += 1
        request: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
        }
        if params:
            request["params"] = params

        self._writer.write((json.dumps(request) + "\n").encode())
        await self._writer.drain()

        response_line = await self._reader.readline()
        if not response_line:
            raise RuntimeError("iMessage RPC connection closed")

        return json.loads(response_line)

    async def send_message(
        self,
        chat_id: str,
        content: str,
        reply_to: str | None = None,
        media: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Send message via iMessage.

        Args:
            chat_id: Recipient handle (phone number, email, or chat GUID)
            content: Plain text content
            reply_to: Optional message GUID to reply to
            media: Optional attachment file paths
            metadata: Optional metadata (service="sms" for SMS fallback)
        """
        formatted_content = self.format_content(content)

        try:
            params: dict[str, Any] = {
                "handle": chat_id,
                "message": formatted_content,
            }

            if metadata and metadata.get("service"):
                params["service"] = metadata["service"]

            if media:
                params["attachments"] = media

            await self._rpc_call("send", params)
            logger.debug(f"Sent iMessage to {chat_id} ({len(formatted_content)} chars)")
        except Exception as e:
            logger.error(f"Failed to send iMessage: {e}")
            raise

    async def fetch_updates(self) -> list[Any]:
        """Fetch new iMessage messages via JSON-RPC.

        Returns:
            List of incoming message dicts
        """
        try:
            response = await self._rpc_call("getMessages", {
                "limit": 10,
            })
            messages = response.get("result", {}).get("messages", [])
            return messages
        except Exception as e:
            logger.error(f"Error fetching iMessage messages: {e}")
            return []

    async def _process_updates(self, updates: list[Any]) -> None:
        """Process a batch of iMessage messages.

        Args:
            updates: List of iMessage message dicts
        """
        for msg in updates:
            await self._handle_message(msg)

    async def _handle_message(self, msg: dict[str, Any]) -> None:
        """Handle incoming iMessage message.

        Args:
            msg: iMessage message dict
        """
        sender = msg.get("sender", "")
        chat_guid = msg.get("chat_guid", "")
        text = msg.get("text", "")
        message_id = msg.get("guid", "")
        is_from_me = msg.get("is_from_me", False)

        if is_from_me:
            return

        # Normalize sender handle
        sender_id = sender.replace(" ", "")

        # Check if allowed
        if self.config.allowed_senders and sender_id not in self.config.allowed_senders:
            logger.debug(f"Sender not allowed: {sender_id}")
            return

        # Determine if group chat
        is_group = "-group" in chat_guid or "chat" in chat_guid.lower()
        chat_id = chat_guid if is_group else sender_id

        # Extract attachments
        media = []
        for attachment in msg.get("attachments", []):
            filename = attachment.get("filename", "")
            if filename:
                media.append(filename)

        await self.receive_incoming(
            sender_id=sender_id,
            chat_id=chat_id,
            content=text,
            message_id=message_id,
            media=media,
            metadata=msg,
            is_group=is_group,
            was_mentioned=True,
        )


__all__ = ["IMessageChannel", "Config"]
