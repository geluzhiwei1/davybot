# DavyBot Multi-Channel Integration System

## Overview

The channel system provides a unified interface for integrating with multiple chat platforms. It decouples channel implementations from the core agent logic via a message bus architecture.

## Architecture

```
┌─────────────────┐
│  Chat Platform  │ (Telegram, Discord, Slack, etc.)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Channel Layer  │ (BaseChannel subclasses)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Message Bus    │ (InboundMessage / OutboundMessage)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Agent Core    │ (PDCA modes, tools, LLM)
└─────────────────┘
```

## Supported Channels

| Channel      | Type      | Features                           |
|--------------|-----------|------------------------------------|
| Telegram     | Webhook   | HTML, media, buttons, groups       |
| Discord      | Gateway   | Markdown, threads, slash commands  |
| Slack        | Webhook   | mrkdwn, threads, reactions         |
| Feishu       | Webhook   | Markdown, cards, groups            |
| DingTalk     | Webhook   | Markdown, groups, mentions         |
| WeChat       | Webhook   | Markdown, media, groups            |
| Email        | Polling   | HTML, attachments, threading       |

## Quick Start

### 1. Basic Usage

```python
from pathlib import Path
from dawei.channels import create_channel_manager

# Create and initialize manager
manager = await create_channel_manager(
    workspace_path=Path("./my-workspace")
)

# Start all channels
await manager.start_all()

# ... channels are now receiving and sending messages ...

# Stop all channels
await manager.stop_all()
```

### 2. Configuration File

Create `.dawei/channels.yml` in your workspace:

```yaml
channels:
  - channel_type: telegram
    enabled: true
    config:
      token: "your-telegram-bot-token"
      allowed_senders: ["user123", "user456"]

  - channel_type: discord
    enabled: true
    config:
      bot_token: "your-discord-bot-token"
      command_prefix: "/"

  - channel_type: slack
    enabled: true
    config:
      bot_token: "xoxb-your-slack-bot-token"
      signing_secret: "your-signing-secret"
```

### 3. Programmatic Channel Creation

```python
from dawei.channels import (
    ChannelManager,
    MessageBus,
    register_channel,
)
from dawei.channels.telegram import TelegramChannel, Config

# Create message bus and manager
bus = MessageBus()
manager = ChannelManager(bus)

# Create and add channel
telegram_config = Config(
    token="your-bot-token",
    allowed_senders={"user123"},
)
channel = await manager.add_channel(
    ChannelSpec(
        channel_type="telegram",
        config={"token": "your-bot-token"},
    )
)

# Start channel
await manager.start_all()
```

## Creating a Custom Channel

### 1. Create Channel Package

```bash
mkdir -p dawei/channels/myplatform
touch dawei/channels/myplatform/__init__.py
```

### 2. Implement Channel Class

```python
# dawei/channels/myplatform/__init__.py

from dataclasses import dataclass
from dawei.channels import (
    BaseChannelConfig,
    ChannelCapabilities,
    ChannelHealth,
    WebhookChannel,
    register_channel,
)

@dataclass
class Config(BaseChannelConfig):
    """MyPlatform channel configuration."""
    api_key: str = ""
    webhook_secret: str = ""

@register_channel("myplatform")
class MyPlatformChannel(WebhookChannel):
    """MyPlatform integration."""

    channel_type = "myplatform"
    capabilities = ChannelCapabilities(
        format_type="markdown",
        max_text_length=4000,
        groups=True,
        mentions=True,
    )
    config_class = Config
    webhook_path = "/myplatform"

    async def _start(self) -> None:
        """Start webhook server."""
        print(f"MyPlatform channel started")

    async def _stop(self) -> None:
        """Stop webhook server."""
        print(f"MyPlatform channel stopped")

    async def _health_check(self) -> ChannelHealth:
        """Check platform health."""
        return ChannelHealth(healthy=True, message="OK")

    async def send_message(
        self,
        chat_id: str,
        content: str,
        reply_to: str | None = None,
        media: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Send message to platform."""
        # Your implementation here
        pass

    async def _process_webhook(
        self,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> None:
        """Process incoming webhook."""
        # Extract message from payload
        sender_id = payload.get("sender", "")
        chat_id = payload.get("chat", "")
        text = payload.get("text", "")

        # Receive via message bus
        await self.receive_incoming(
            sender_id=sender_id,
            chat_id=chat_id,
            content=text,
        )
```

### 3. Auto-Registration

Your channel is automatically registered when imported:

```python
from dawei.channels import ChannelManager, MessageBus

# This triggers auto-discovery and registration
manager = ChannelManager(MessageBus())

# Now you can use your channel
await manager.add_channel(ChannelSpec(
    channel_type="myplatform",
    config={"api_key": "your-key"},
))
```

## Message Flow

### Inbound (Platform → Agent)

1. Platform sends webhook or polling fetches update
2. Channel extracts message data (sender, chat, content, media)
3. Channel calls `receive_incoming()` with parsed data
4. Message is published to `MessageBus.inbound` queue
5. Agent consumes from queue and processes

### Outbound (Agent → Platform)

1. Agent publishes `OutboundMessage` to `MessageBus.outbound` queue
2. Channel's subscribed callback is invoked
3. Channel formats content (Markdown → platform format)
4. Channel sends via platform API
5. Platform delivers message to user

## Channel Capabilities

Each channel declares its capabilities via `ChannelCapabilities`:

```python
capabilities = ChannelCapabilities(
    # Messaging
    format_type="html",           # html, markdown, slack_mrkdwn, discord, plain
    max_text_length=4000,
    max_file_size=20 * 1024 * 1024,

    # Features
    streaming=False,
    threading=False,
    reactions=True,
    typing=True,
    inline_buttons=False,

    # Media
    media_send=True,
    media_receive=True,
    voice=True,
    stickers=True,
    location=True,
    video=False,

    # Group features
    groups=True,
    mentions=True,

    # Rich text
    markdown=False,
    html=True,

    # Extended
    chat_types=("direct", "group"),
    edit=True,
    unsend=True,
    native_commands=True,
    polls=True,
)
```

The framework uses these capabilities to:
- Auto-format messages (Markdown → platform format)
- Enable/disable features (streaming, buttons, etc.)
- Validate message length and attachments
- Adapt interaction patterns

## Health Monitoring

```python
from dawei.channels import HealthMonitor

# Create monitor
monitor = HealthMonitor(
    channels=manager._channels,
    check_interval_s=60.0,
    alert_threshold=3,
)

# Add alert callback
async def on_alert(alert):
    if not alert.healthy:
        print(f"ALERT: {alert.channel_type} is unhealthy: {alert.message}")

monitor.add_alert_callback(on_alert)

# Start monitoring
await monitor.start()

# Get health report
report = await monitor.get_health_report()
print(f"Overall healthy: {report.overall_healthy}")
print(f"Unhealthy channels: {report.unhealthy_channels}")

# Stop monitoring
await monitor.stop()
```

## Unified Formatting

The `UnifiedFormatter` converts Markdown to platform-specific formats:

```python
from dawei.channels import UnifiedFormatter

# Create formatter for a platform
formatter = UnifiedFormatter.for_channel("html")

# Convert Markdown to HTML
html = formatter.format("""
# Heading
**Bold** and *italic*
`inline code`

```
code block
```
""")
```

Supported formats:
- `html` - Telegram, Email
- `markdown` - Feishu, DingTalk, WeChat
- `slack_mrkdwn` - Slack
- `discord` - Discord
- `plain` - Signal, iMessage

## Retry Logic

Channels can be configured with retry logic:

```yaml
channels:
  - channel_type: telegram
    enabled: true
    config:
      token: "your-token"
    retry_config:
      attempts: 5
      min_delay_s: 0.5
      max_delay_s: 60.0
      jitter: 0.2
```

## Webhook Server

For webhook-based channels, you can use the shared webhook server:

```python
from dawei.channels import WebhookServer

# Create server
server = WebhookServer(host="0.0.0.0", port=8466)

# Register channel webhooks
server.register(
    path="/telegram",
    channel_type="telegram",
    handler=telegram_channel.handle_webhook,
    secret="webhook-secret",
)

# Start server
await server.start()

# Get webhook URL
telegram_webhook_url = server.get_url("/telegram")
print(f"Telegram webhook URL: {telegram_webhook_url}")
```

## Testing

### Test Channel Registration

```python
from dawei.channels import ChannelRegistry

# List registered channels
print(ChannelRegistry.list_channels())
# Output: ['telegram', 'discord', 'slack', 'feishu', 'dingtalk', 'wechat', 'email']

# Check if channel is registered
if ChannelRegistry.is_registered("telegram"):
    print("Telegram channel is available")
```

### Test Message Flow

```python
import asyncio
from dawei.channels import MessageBus, InboundMessage, OutboundMessage

# Create message bus
bus = MessageBus()

# Publish inbound message
await bus.publish_inbound(InboundMessage(
    channel="telegram",
    sender_id="user123",
    chat_id="chat456",
    content="Hello, bot!",
))

# Consume inbound message
msg = await bus.consume_inbound()
print(f"Received: {msg.content}")

# Subscribe to outbound messages
async def handle_outbound(msg: OutboundMessage):
    print(f"Sending to {msg.chat_id}: {msg.content}")

bus.subscribe_outbound("telegram", handle_outbound)

# Publish outbound message
await bus.publish_outbound(OutboundMessage(
    channel="telegram",
    chat_id="chat456",
    content="Hello, user!",
))
```

## Best Practices

1. **Configuration**: Store sensitive data (tokens, secrets) in environment variables
2. **Error Handling**: Always wrap platform API calls in try/except blocks
3. **Logging**: Use structured logging for debugging
4. **Rate Limiting**: Respect platform rate limits
5. **Idempotency**: Make webhook handlers idempotent (handle duplicate events)
6. **Health Checks**: Implement proper health checks for external dependencies
7. **Graceful Shutdown**: Clean up resources in `_stop()` method

## Troubleshooting

### Channel Not Registered

```python
# Ensure channels are auto-discovered
from dawei.channels.channel_manager import _ensure_channels_registered
_ensure_channels_registered()
```

### Import Errors

```bash
# Install missing dependencies
pip install aiohttp pydantic pyyaml
```

### Webhook Not Receiving Messages

1. Check webhook URL is correct
2. Verify webhook secret/signature
3. Check firewall rules
4. Review platform dashboard for webhook status

### Health Checks Failing

1. Check platform API status
2. Verify authentication credentials
3. Check network connectivity
4. Review error logs

## API Reference

See inline documentation in:
- `channel.py` - Base channel classes
- `channel_manager.py` - Channel management
- `message_bus.py` - Message bus
- `capabilities.py` - Capability declarations
- `formatter.py` - Unified formatting
- `retry.py` - Retry logic
- `health.py` - Health monitoring
- `webhook.py` - Webhook server

## License

AGPL-3.0-only
