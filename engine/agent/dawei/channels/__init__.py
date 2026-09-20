"""Dawei multi-channel messaging framework.

Provides a unified interface for communicating across chat platforms
(Telegram, Discord, Slack, WeChat, Feishu, DingTalk, QQ, Email,
Signal, iMessage) via a pluggable channel architecture.
"""

from __future__ import annotations

from .bridge import AgentSession, ChannelBridge
from .bus import InboundMessage, MessageBus, OutboundMessage
from .capabilities import ChannelCapabilities
from .channel import BaseChannel, ChannelHealth, SimplePollingChannel, WebhookChannel
from .channel_manager import ChannelManager, ChannelRegistry, register_channel
from .config import BaseChannelConfig
from .formatter import UnifiedFormatter
from .retry import RetryConfig, retry_async
from .webhook import WebhookServer

__all__ = [
    "AgentSession",
    "BaseChannel",
    "BaseChannelConfig",
    "ChannelBridge",
    "ChannelCapabilities",
    "ChannelHealth",
    "ChannelManager",
    "ChannelRegistry",
    "InboundMessage",
    "MessageBus",
    "OutboundMessage",
    "RetryConfig",
    "SimplePollingChannel",
    "UnifiedFormatter",
    "WebhookChannel",
    "WebhookServer",
    "register_channel",
    "retry_async",
]
