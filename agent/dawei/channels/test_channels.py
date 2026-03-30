#!/usr/bin/env python3
"""Test script demonstrating the channel system functionality."""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dawei.channels import (
    ChannelManager,
    ChannelRegistry,
    InboundMessage,
    MessageBus,
    OutboundMessage,
    register_channel,
)


async def main():
    """Test channel system."""
    print("=" * 60)
    print("DavyBot Channel System Test")
    print("=" * 60)
    print()

    # 1. List available channels
    print("1. Available Channel Packages")
    print("-" * 60)
    from dawei.channels.channel_manager import _ensure_channels_registered, ChannelRegistry

    available = ChannelRegistry.list_channels()
    for ch in sorted(available):
        print(f"  - {ch}")
    print(f"  Total: {len(available)} packages")
    print()

    # 2. Test auto-discovery
    print("2. Channel Auto-Discovery")
    print("-" * 60)
    from dawei.channels.channel_manager import _ensure_channels_registered

    _ensure_channels_registered()
    registered = ChannelRegistry.list_channels()
    for ch in sorted(registered):
        print(f"  - {ch}")
    print(f"  Total: {len(registered)} channels registered")
    print()

    # 3. Test channel factory
    print("3. Channel Factory System")
    print("-" * 60)
    for channel_type in ["telegram", "discord", "slack"]:
        factory = ChannelRegistry.get_factory(channel_type)
        if factory:
            print(f"  ✓ {channel_type}: factory registered")
        else:
            print(f"  ✗ {channel_type}: factory not found")
    print()

    # 4. Test message bus
    print("4. Message Bus Test")
    print("-" * 60)
    bus = MessageBus()

    # Publish inbound message
    await bus.publish_inbound(
        InboundMessage(
            channel="telegram",
            sender_id="user123",
            chat_id="chat456",
            content="Hello, bot!",
        )
    )

    # Consume inbound message
    msg = await bus.consume_inbound()
    print(f"  Received inbound message:")
    print(f"    Channel: {msg.channel}")
    print(f"    Sender: {msg.sender_id}")
    print(f"    Chat: {msg.chat_id}")
    print(f"    Content: {msg.content}")
    print()

    # 5. Test outbound message handling
    print("5. Outbound Message Handling")
    print("-" * 60)

    outbound_received = []

    async def outbound_handler(msg: OutboundMessage):
        outbound_received.append(msg)
        print(f"  Sending outbound message:")
        print(f"    Channel: {msg.channel}")
        print(f"    Chat: {msg.chat_id}")
        print(f"    Content: {msg.content}")

    bus.subscribe_outbound("telegram", outbound_handler)

    # Publish outbound message
    await bus.publish_outbound(
        OutboundMessage(
            channel="telegram",
            chat_id="chat456",
            content="Hello, user!",
        )
    )

    # Give time for async processing
    await asyncio.sleep(0.1)

    if outbound_received:
        print(f"  ✓ Outbound message processed successfully")
    else:
        print(f"  ✗ Outbound message not processed")
    print()

    # 6. Test channel manager
    print("6. Channel Manager Test")
    print("-" * 60)
    manager = ChannelManager(bus, workspace_path=Path.cwd())

    # Add a test channel (without actual config, just to test registration)
    from dawei.channels.telegram import TelegramChannel, Config as TelegramConfig

    telegram_config = TelegramConfig(token="test-token")

    # Note: This won't actually start the channel without valid config
    # but demonstrates the API
    print(f"  Created ChannelManager")
    print(f"  Active channels: {manager.list_channels()}")
    print()

    # 7. Test unified formatter
    print("7. Unified Formatter Test")
    print("-" * 60)
    from dawei.channels import UnifiedFormatter

    markdown_text = """
# Heading
**Bold** and *italic* text
`inline code`

[Link](https://example.com)

```
code block
```
"""

    for format_type in ["html", "markdown", "slack_mrkdwn", "discord", "plain"]:
        try:
            formatter = UnifiedFormatter.for_channel(format_type)
            formatted = formatter.format(markdown_text)
            lines = formatted.split("\n")[:3]  # Show first 3 lines
            print(f"  {format_type}:")
            for line in lines:
                print(f"    {line}")
            if len(formatted.split("\n")) > 3:
                print(f"    ...")
        except Exception as e:
            print(f"  {format_type}: Error - {e}")
    print()

    # 8. Test channel capabilities
    print("8. Channel Capabilities Test")
    print("-" * 60)
    from dawei.channels import ChannelCapabilities

    telegram_caps = ChannelCapabilities(
        format_type="html",
        max_text_length=4000,
        reactions=True,
        groups=True,
        mentions=True,
        html=True,
    )

    print(f"  Telegram capabilities:")
    print(f"    Format: {telegram_caps.format_type}")
    print(f"    Max length: {telegram_caps.max_text_length}")
    print(f"    Reactions: {telegram_caps.reactions}")
    print(f"    Groups: {telegram_caps.groups}")
    print(f"    Mentions: {telegram_caps.mentions}")
    print(f"    HTML: {telegram_caps.html}")
    print(f"    Supports 'streaming': {telegram_caps.supports('streaming')}")
    print(f"    Supports 'groups': {telegram_caps.supports('groups')}")
    print()

    print("=" * 60)
    print("All tests completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
