"""Async message bus that decouples chat channels from the agent core."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from .events import InboundMessage, OutboundMessage

logger = logging.getLogger(__name__)

OutboundCallback = Callable[[OutboundMessage], Awaitable[None]]


class MessageBus:
    """Async message bus that decouples chat channels from the agent core."""

    def __init__(self):
        self.inbound: asyncio.Queue[InboundMessage] = asyncio.Queue(maxsize=5000)
        self.outbound: asyncio.Queue[OutboundMessage] = asyncio.Queue(maxsize=5000)
        self._outbound_subscribers: dict[str, list[OutboundCallback]] = {}
        self._running = False

    # inbound (channel -> agent)

    async def publish_inbound(self, msg: InboundMessage) -> None:
        await self.inbound.put(msg)

    async def consume_inbound(self) -> InboundMessage:
        return await self.inbound.get()

    # outbound (agent -> channel)

    async def publish_outbound(self, msg: OutboundMessage) -> None:
        await self.outbound.put(msg)

    async def consume_outbound(self) -> OutboundMessage:
        return await self.outbound.get()

    # subscriber routing

    def subscribe_outbound(self, channel: str, callback: OutboundCallback) -> None:
        if channel not in self._outbound_subscribers:
            self._outbound_subscribers[channel] = []
        self._outbound_subscribers[channel].append(callback)

    async def dispatch_outbound(self) -> None:
        self._running = True
        while self._running:
            try:
                msg = await asyncio.wait_for(self.outbound.get(), timeout=1.0)
            except TimeoutError:
                continue
            subscribers = self._outbound_subscribers.get(msg.channel, [])
            if not subscribers:
                logger.warning(f"No subscriber for channel: {msg.channel}")
                continue
            for callback in subscribers:
                try:
                    await callback(msg)
                except Exception as e:
                    logger.error(f"Error dispatching to {msg.channel}: {e}")

    def stop(self) -> None:
        self._running = False

    @property
    def inbound_size(self) -> int:
        return self.inbound.qsize()

    @property
    def outbound_size(self) -> int:
        return self.outbound.qsize()
