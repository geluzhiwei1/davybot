"""Signal channel implementation for DavyBot.

Uses signal-cli JSON-RPC mode for real-time message streaming.

Requirements:
- signal-cli installed and configured
- A registered phone number

Configuration:
    phone_number: Signal phone number (E.164 format)
    cli_path: Path to signal-cli binary (default: "signal-cli")
    config_dir: Optional signal-cli config directory
    rpc_port: JSON-RPC port (default: 7583)
    allowed_senders: Optional list of allowed phone numbers
    text_chunk_limit: Max message length (default: 4096)

Environment variables:
    SIGNAL_PHONE_NUMBER: Phone number (overrides config)
    SIGNAL_CLI_PATH: CLI path (overrides config)
"""

from __future__ import annotations

import asyncio
import json
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
    """Signal channel configuration."""

    phone_number: str = ""
    cli_path: str = "signal-cli"
    config_dir: str = ""
    rpc_port: int = 7583
    allowed_senders: set[str] | None = None
    text_chunk_limit: int = 4096


@register_channel("signal")
class SignalChannel(SimplePollingChannel):
    """Signal channel using signal-cli JSON-RPC mode.

    Supports:
    - Direct and group messages
    - Plain text formatting
    - Media attachments
    - Reactions and typing indicators
    """

    channel_type: str = "signal"
    capabilities = ChannelCapabilities(
        format_type="plain",
        max_text_length=4096,
        reactions=True,
        typing=True,
        media_send=True,
        media_receive=True,
        voice=True,
        groups=True,
        mentions=True,
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
        """Start Signal JSON-RPC connection."""
        if not self.config.phone_number:
            raise ValueError("Signal phone_number is required")

        await super()._start()
        logger.info(f"Signal channel started for {self.config.phone_number}")

    async def _stop(self) -> None:
        """Stop Signal connection."""
        if self._writer:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:
                pass
            self._writer = None
            self._reader = None

        await super()._stop()
        logger.info("Signal channel stopped")

    async def _health_check(self) -> ChannelHealth:
        """Check Signal CLI health."""
        if not self._reader or not self._writer:
            return ChannelHealth(healthy=False, message="Signal RPC not connected")

        try:
            response = await self._rpc_call("listAccounts")
            accounts = response.get("result", {}).get("accounts", [])
            registered = any(
                acc.get("number") == self.config.phone_number for acc in accounts
            )
            if registered:
                return ChannelHealth(healthy=True, message="Signal CLI connected")
            return ChannelHealth(healthy=False, message="Phone number not registered")
        except Exception as e:
            return ChannelHealth(healthy=False, message=f"Health check failed: {e}")

    async def _rpc_call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Make a JSON-RPC call to signal-cli.

        Args:
            method: RPC method name
            params: Optional parameters

        Returns:
            Response dict
        """
        if not self._writer or not self._reader:
            raise RuntimeError("Signal RPC not connected")

        self._request_id += 1
        request = {
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
            raise RuntimeError("Signal RPC connection closed")

        return json.loads(response_line)

    async def send_message(
        self,
        chat_id: str,
        content: str,
        reply_to: str | None = None,
        media: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Send message to Signal.

        Args:
            chat_id: Signal recipient (phone number or group ID)
            content: Plain text content
            reply_to: Optional message timestamp to reply to
            media: Optional attachment file paths
            metadata: Optional metadata
        """
        formatted_content = self.format_content(content)

        try:
            params: dict[str, Any] = {
                "account": self.config.phone_number,
                "recipient": [chat_id],
                "message": formatted_content,
            }

            if media:
                params["attachments"] = media

            await self._rpc_call("send", params)
            logger.debug(f"Sent message to Signal {chat_id} ({len(formatted_content)} chars)")
        except Exception as e:
            logger.error(f"Failed to send Signal message: {e}")
            raise

    async def fetch_updates(self) -> list[Any]:
        """Fetch new Signal messages via JSON-RPC.

        Returns:
            List of incoming message dicts
        """
        try:
            response = await self._rpc_call("receiveMessages", {
                "account": self.config.phone_number,
                "timeout": 1,
            })
            messages = response.get("result", {}).get("messages", [])
            return messages
        except Exception as e:
            logger.error(f"Error fetching Signal messages: {e}")
            return []

    async def _process_updates(self, updates: list[Any]) -> None:
        """Process a batch of Signal messages.

        Args:
            updates: List of Signal message dicts
        """
        for msg in updates:
            await self._handle_message(msg)

    async def _handle_message(self, msg: dict[str, Any]) -> None:
        """Handle incoming Signal message.

        Args:
            msg: Signal message dict from signal-cli
        """
        envelope = msg.get("envelope", {})
        source = envelope.get("source", "")
        source_number = envelope.get("sourceNumber", source)
        timestamp = envelope.get("timestamp", 0)

        # Check if allowed
        if self.config.allowed_senders and source_number not in self.config.allowed_senders:
            logger.debug(f"Sender not allowed: {source_number}")
            return

        # Extract data message
        data_msg = envelope.get("dataMessage", {})
        if not data_msg:
            return

        content = data_msg.get("message", "")
        group_info = data_msg.get("groupInfo", {})
        is_group = bool(group_info)

        chat_id = group_info.get("groupId", source_number) if is_group else source_number

        # Extract attachments
        media = []
        for attachment in data_msg.get("attachments", []):
            media.append(attachment.get("filename", ""))

        # Check if mentioned
        was_mentioned = True  # Simplified

        await self.receive_incoming(
            sender_id=source_number,
            chat_id=chat_id,
            content=content,
            message_id=str(timestamp),
            media=media,
            metadata=envelope,
            is_group=is_group,
            was_mentioned=was_mentioned,
        )


__all__ = ["SignalChannel", "Config"]
