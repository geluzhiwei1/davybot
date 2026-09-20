"""Channel-to-Agent bridge: connects the MessageBus with Dawei's Agent pipeline.

The ChannelBridge is the glue between two worlds:
  - Channel world: InboundMessage / OutboundMessage on MessageBus
  - Agent world:   UserInputText / TaskEventType / EventBus / Agent

Lifecycle:
  1. Consume InboundMessage from MessageBus.inbound queue
  2. Resolve or auto-create a UserWorkspace for the channel user
  3. Create an Agent instance (one per conversation slot)
  4. Forward the message as UserInputText into Agent.process_message()
  5. Subscribe to Agent's EventBus, translate TaskEventType → OutboundMessage
  6. Publish OutboundMessage to MessageBus.outbound queue

Design choices:
  - One Agent per (channel, chat_id) pair; reused within a TTL window
  - Workspace auto-provisioned under DAWEI_HOME/channels/<channel>/<sender_id>/
  - Streaming responses are chunked and sent progressively via OutboundMessage
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dawei.channels.bus.events import InboundMessage, OutboundMessage
from dawei.channels.bus.message_bus import MessageBus
from dawei.channels.channel_manager import ChannelManager
from dawei.channels.webhook import WebhookServer
from dawei.core.events import TaskEvent, TaskEventType
from dawei.entity.user_input_message import UserInputText
from dawei.logg.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _channel_workspace_id(channel: str, chat_id: str) -> str:
    """Deterministic workspace id for a (channel, chat_id) pair."""
    raw = f"{channel}:{chat_id}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _channel_workspace_path(channel: str, chat_id: str, root: Path) -> Path:
    """Directory path for a channel user's workspace."""
    safe_chat = chat_id.replace("/", "_").replace("\\", "_").replace(":", "_")
    safe_channel = channel.replace("/", "_")
    return root / "channels" / safe_channel / safe_chat


# ---------------------------------------------------------------------------
# Agent session: one per (channel, chat_id), reused with TTL
# ---------------------------------------------------------------------------


@dataclass
class AgentSession:
    """Holds one Agent instance and its associated resources."""

    session_id: str
    channel: str
    chat_id: str
    agent: Any  # Agent instance
    user_workspace: Any  # UserWorkspace instance
    event_bus: Any  # IEventBus
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)
    handler_ids: dict[str, str] = field(default_factory=dict)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @property
    def key(self) -> str:
        return f"{self.channel}:{self.chat_id}"

    def touch(self) -> None:
        self.last_used = time.time()

    def is_expired(self, ttl: float = 1800.0) -> bool:
        """Session expires after *ttl* seconds of inactivity (default 30 min)."""
        return (time.time() - self.last_used) > ttl


# ---------------------------------------------------------------------------
# ChannelBridge
# ---------------------------------------------------------------------------


class ChannelBridge:
    """Bridges the channel MessageBus with Dawei's Agent execution pipeline.

    Usage::

        bridge = ChannelBridge(message_bus, webhook_server)
        await bridge.start()        # starts consumer loop + webhook server
        ...
        await bridge.stop()         # graceful shutdown
    """

    SESSION_TTL = 1800.0  # 30 minutes
    MAX_CONCURRENT = 50
    CLEANUP_INTERVAL = 300.0  # 5 minutes

    def __init__(
        self,
        message_bus: MessageBus,
        webhook_server: WebhookServer | None = None,
        channel_manager: ChannelManager | None = None,
        default_workspace_root: Path | None = None,
    ) -> None:
        self.message_bus = message_bus
        self.webhook_server = webhook_server
        self.channel_manager = channel_manager

        # Workspace root for auto-provisioned channel workspaces
        if default_workspace_root is None:
            from dawei import get_dawei_home
            default_workspace_root = get_dawei_home()
        self.workspace_root = default_workspace_root

        # Active agent sessions keyed by "channel:chat_id"
        self._sessions: dict[str, AgentSession] = {}
        self._semaphore = asyncio.Semaphore(self.MAX_CONCURRENT)

        # Map of channel_type -> running BaseChannel instances (managed by this bridge)
        self._channels_map: dict[str, BaseChannel] = {}

        # Background tasks
        self._consumer_task: asyncio.Task[None] | None = None
        self._cleanup_task: asyncio.Task[None] | None = None
        self._running = False
        self._channels_map: dict[str, BaseChannel] = {}

    # ===================================================================
    # Lifecycle
    # ===================================================================

    async def start(self) -> None:
        """Start the bridge: begin consuming inbound messages."""
        if self._running:
            logger.warning("[BRIDGE] Already running")
            return

        self._running = True

        # Start the outbound dispatch loop on the MessageBus
        self._dispatch_task = asyncio.create_task(
            self.message_bus.dispatch_outbound(),
        )

        # Start the inbound consumer loop
        self._consumer_task = asyncio.create_task(self._inbound_loop())

        # Start the session cleanup loop
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

        # Register webhook channels with the shared webhook server
        if self.webhook_server and self.channel_manager:
            await self._register_webhook_channels()

        logger.info("[BRIDGE] Started — consuming inbound messages")

    async def stop(self) -> None:
        """Gracefully shut down the bridge and all agent sessions."""
        if not self._running:
            return

        logger.info("[BRIDGE] Stopping...")
        self._running = False

        # Cancel background tasks
        for task in (
            self._consumer_task,
            self._cleanup_task,
            getattr(self, "_dispatch_task", None),
        ):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Close all agent sessions
        for session in list(self._sessions.values()):
            await self._close_session(session)
        self._sessions.clear()

        # Stop outbound dispatch
        self.message_bus.stop()

        logger.info("[BRIDGE] Stopped")

    # ===================================================================
    # Inbound consumer loop
    # ===================================================================

    async def _inbound_loop(self) -> None:
        """Continuously consume InboundMessage from the MessageBus."""
        while self._running:
            try:
                msg = await asyncio.wait_for(
                    self.message_bus.consume_inbound(),
                    timeout=1.0,
                )
                asyncio.create_task(self._handle_inbound(msg))
            except TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[BRIDGE] Inbound loop error: {e}", exc_info=True)
                await asyncio.sleep(1.0)

    async def _handle_inbound(self, msg: InboundMessage) -> None:
        """Process a single InboundMessage through an Agent."""
        async with self._semaphore:
            try:
                session = await self._get_or_create_session(msg)
                if session is None:
                    logger.error(
                        f"[BRIDGE] Cannot create session for {msg.channel}:{msg.chat_id}"
                    )
                    return

                session.touch()

                # Build UserInputText (Agent's expected input format)
                user_input = UserInputText(
                    text=msg.content,
                    metadata={
                        "workspaceId": session.user_workspace.workspace_info.id,
                        "conversationId": getattr(
                            session.user_workspace.current_conversation, "id", None
                        ),
                        # Channel context for downstream tools
                        "_channel": msg.channel,
                        "_chat_id": msg.chat_id,
                        "_sender_id": msg.sender_id,
                        "_message_id": msg.message_id,
                        "_is_group": msg.is_group,
                        "_was_mentioned": msg.was_mentioned,
                        **(msg.metadata or {}),
                    },
                )

                # Ensure conversation exists
                await self._ensure_conversation(session)

                # Execute agent
                await session.agent.process_message(user_input)

                logger.info(
                    f"[BRIDGE] Agent completed for {msg.channel}:{msg.chat_id}"
                )

            except Exception as e:
                logger.error(
                    f"[BRIDGE] Error handling inbound from "
                    f"{msg.channel}:{msg.chat_id}: {e}",
                    exc_info=True,
                )
                # Send error back through the channel
                await self._send_error_reply(msg, str(e))

    # ===================================================================
    # Session management
    # ===================================================================

    async def _get_or_create_session(self, msg: InboundMessage) -> AgentSession | None:
        """Get an existing agent session or create a new one."""
        key = f"{msg.channel}:{msg.chat_id}"

        existing = self._sessions.get(key)
        if existing and not existing.is_expired(self.SESSION_TTL):
            return existing

        # Close expired session if any
        if existing:
            await self._close_session(existing)

        # Create new session
        session = await self._create_session(msg)
        if session:
            self._sessions[key] = session
        return session

    async def _create_session(self, msg: InboundMessage) -> AgentSession | None:
        """Provision workspace + Agent for a (channel, chat_id) pair."""
        try:
            from dawei.agentic.agent import Agent
            from dawei.workspace.user_workspace import UserWorkspace
            from dawei.workspace.workspace_manager import workspace_manager

            channel = msg.channel
            chat_id = msg.chat_id
            workspace_id = _channel_workspace_id(channel, chat_id)
            session_id = str(uuid.uuid4())

            # 1. Resolve or create workspace
            user_workspace = await self._resolve_workspace(
                workspace_id, channel, chat_id, msg.sender_id
            )
            if user_workspace is None:
                logger.error(f"[BRIDGE] Failed to resolve workspace for {channel}:{chat_id}")
                return None

            # 2. Create Agent
            agent = await Agent.create_with_default_engine(user_workspace)
            await agent.initialize()

            # 3. Subscribe to Agent events → translate to OutboundMessage
            event_bus = agent.event_bus
            handler_ids = await self._subscribe_agent_events(
                agent, event_bus, channel, chat_id, session_id
            )

            session = AgentSession(
                session_id=session_id,
                channel=channel,
                chat_id=chat_id,
                agent=agent,
                user_workspace=user_workspace,
                event_bus=event_bus,
                handler_ids=handler_ids,
            )

            logger.info(
                f"[BRIDGE] Created session {session_id} for {channel}:{chat_id}"
            )
            return session

        except Exception as e:
            logger.error(
                f"[BRIDGE] Failed to create session for "
                f"{msg.channel}:{msg.chat_id}: {e}",
                exc_info=True,
            )
            return None

    async def _resolve_workspace(
        self,
        workspace_id: str,
        channel: str,
        chat_id: str,
        sender_id: str,
    ) -> Any | None:
        """Find an existing workspace or auto-provision one for the channel user."""
        from dawei.workspace.user_workspace import UserWorkspace
        from dawei.workspace.workspace_manager import workspace_manager

        # Try existing workspace first
        ws_info = workspace_manager.get_workspace_by_id(workspace_id)
        if ws_info and ws_info.get("path"):
            ws = UserWorkspace(ws_info["path"])
            if not ws.is_initialized():
                await ws.initialize()
            return ws

        # Auto-provision a new workspace
        ws_path = _channel_workspace_path(channel, chat_id, self.workspace_root)
        ws_path.mkdir(parents=True, exist_ok=True)

        # Initialize workspace structure
        ws = UserWorkspace(str(ws_path))
        if not ws.is_initialized():
            await ws.initialize()

        # Register with workspace_manager so it can be found later
        if hasattr(workspace_manager, "workspaces_mapping"):
            workspace_manager.workspaces_mapping[workspace_id] = {
                "id": workspace_id,
                "name": f"{channel}:{chat_id}",
                "path": str(ws_path),
            }

        logger.info(f"[BRIDGE] Auto-provisioned workspace at {ws_path}")
        return ws

    async def _ensure_conversation(self, session: AgentSession) -> None:
        """Make sure the session's workspace has an active conversation."""
        ws = session.user_workspace
        if not ws.current_conversation:
            from dawei.conversation.conversation import Conversation
            ws.current_conversation = Conversation()

    # ===================================================================
    # Event subscription: Agent EventBus → OutboundMessage
    # ===================================================================

    async def _subscribe_agent_events(
        self,
        agent: Any,
        event_bus: Any,
        channel: str,
        chat_id: str,
        session_id: str,
    ) -> dict[str, str]:
        """Subscribe to Agent events and translate them to OutboundMessage."""
        handler_ids: dict[str, str] = {}

        # Accumulated content for streaming responses
        content_parts: list[str] = []

        async def on_task_completed(event: TaskEvent) -> None:
            """Task completed: send final response to channel."""
            nonlocal content_parts
            result = ""
            data = event.data
            if hasattr(data, "result"):
                result = data.result or ""
            elif isinstance(data, dict):
                result = data.get("result", "")

            # If we accumulated stream content, use that instead
            final_content = "".join(content_parts) if content_parts else result
            content_parts.clear()

            if final_content:
                await self._send_outbound(
                    channel=channel,
                    chat_id=chat_id,
                    content=final_content,
                )

        async def on_content_stream(event: TaskEvent) -> None:
            """Streaming content: accumulate chunks."""
            data = event.data
            if isinstance(data, dict):
                chunk = data.get("content", "")
            elif hasattr(data, "content"):
                chunk = data.content
            else:
                chunk = str(data) if data else ""
            if chunk:
                content_parts.append(chunk)

        async def on_task_error(event: TaskEvent) -> None:
            """Task error: send error message to channel."""
            nonlocal content_parts
            content_parts.clear()

            data = event.data
            if isinstance(data, dict):
                err_msg = data.get("error_message", str(data))
            elif hasattr(data, "error_message"):
                err_msg = data.error_message
            else:
                err_msg = str(data)

            await self._send_outbound(
                channel=channel,
                chat_id=chat_id,
                content=f"[Error] {err_msg}",
            )

        async def on_error_occurred(event: TaskEvent) -> None:
            """General error: send error to channel."""
            data = event.data
            if isinstance(data, dict):
                err_msg = data.get("message", str(data))
            else:
                err_msg = str(data)

            await self._send_outbound(
                channel=channel,
                chat_id=chat_id,
                content=f"[Error] {err_msg}",
            )

        # Subscribe to key event types
        subscriptions = {
            TaskEventType.TASK_COMPLETED: on_task_completed,
            TaskEventType.CONTENT_STREAM: on_content_stream,
            TaskEventType.TASK_ERROR: on_task_error,
            TaskEventType.ERROR_OCCURRED: on_error_occurred,
        }

        for event_type, handler in subscriptions.items():
            try:
                hid = event_bus.add_handler(event_type, handler)
                handler_ids[event_type.value] = hid
            except Exception as e:
                logger.error(f"[BRIDGE] Failed to subscribe to {event_type}: {e}")

        return handler_ids

    # ===================================================================
    # Outbound: send response back through MessageBus
    # ===================================================================

    async def _send_outbound(
        self,
        channel: str,
        chat_id: str,
        content: str,
        reply_to: str | None = None,
        media: list[str] | None = None,
    ) -> None:
        """Publish an OutboundMessage to the MessageBus."""
        msg = OutboundMessage(
            channel=channel,
            chat_id=chat_id,
            content=content,
            reply_to=reply_to,
            media=media or [],
        )
        await self.message_bus.publish_outbound(msg)
        logger.debug(
            f"[BRIDGE] Outbound → {channel}:{chat_id} ({len(content)} chars)"
        )

    async def _send_error_reply(self, inbound: InboundMessage, error: str) -> None:
        """Send an error reply back to the channel user."""
        await self._send_outbound(
            channel=inbound.channel,
            chat_id=inbound.chat_id,
            content=f"[Error] {error[:500]}",
        )

    # ===================================================================
    # Session cleanup
    # ===================================================================

    async def _cleanup_loop(self) -> None:
        """Periodically clean up expired sessions."""
        while self._running:
            try:
                await asyncio.sleep(self.CLEANUP_INTERVAL)
                await self._cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[BRIDGE] Cleanup error: {e}", exc_info=True)

    async def _cleanup_expired(self) -> None:
        """Remove and close expired agent sessions."""
        expired = [
            s for s in self._sessions.values()
            if s.is_expired(self.SESSION_TTL)
        ]
        for session in expired:
            await self._close_session(session)
            del self._sessions[session.key]

        if expired:
            logger.info(f"[BRIDGE] Cleaned up {len(expired)} expired sessions")

    async def _close_session(self, session: AgentSession) -> None:
        """Close a single agent session and release resources."""
        # Remove event handlers
        for event_type_str, handler_id in session.handler_ids.items():
            try:
                from dawei.core.events import TaskEventType
                event_type = TaskEventType(event_type_str)
                session.event_bus.remove_handler(event_type, handler_id)
            except Exception as e:
                logger.debug(f"[BRIDGE] Error removing handler: {e}")

        # Save conversation
        try:
            ws = session.user_workspace
            if ws and ws.current_conversation:
                await ws.save_current_conversation()
        except Exception as e:
            logger.debug(f"[BRIDGE] Error saving conversation: {e}")

        logger.info(f"[BRIDGE] Closed session {session.session_id}")

    # ===================================================================
    # Webhook integration
    # ===================================================================

    async def _register_webhook_channels(self) -> None:
        """Register all webhook-based channels with the shared WebhookServer."""
        if not self.webhook_server or not self.channel_manager:
            return

        for channel_type in self.channel_manager.list_channels():
            channel = await self.channel_manager.get_channel(channel_type)
            if channel is None:
                continue

            # Only register webhook channels
            from dawei.channels.channel import WebhookChannel
            if not isinstance(channel, WebhookChannel):
                continue

            path = getattr(channel, "webhook_path", f"/{channel_type}")
            secret = getattr(channel, "webhook_secret", None)

            def _make_handler(ch: Any) -> Any:
                """Create a handler closure for the channel."""
                async def handler(
                    payload: dict[str, Any],
                    headers: dict[str, str],
                ) -> dict[str, Any]:
                    return await ch.handle_webhook(payload, headers)
                return handler

            handler = _make_handler(channel)
            self.webhook_server.register(
                path=path,
                channel_type=channel_type,
                handler=handler,
                secret=secret,
            )
            logger.info(f"[BRIDGE] Registered webhook: {path} → {channel_type}")

    # ===================================================================
    # Status / introspection
    # ===================================================================

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def active_session_count(self) -> int:
        return len(self._sessions)

    def get_session_info(self) -> list[dict[str, Any]]:
        """Return info about all active sessions."""
        return [
            {
                "channel": s.channel,
                "chat_id": s.chat_id,
                "session_id": s.session_id,
                "created_at": s.created_at,
                "last_used": s.last_used,
            }
            for s in self._sessions.values()
        ]

    # ===================================================================
    # Per-channel start/stop (for enable/disable from API)
    # ===================================================================

    async def start_channel(self, channel_type: str) -> bool:
        """Start a single channel by type.

        Reads the persisted config from channels.json, Returns True if started.
        """
        import json
        from dawei import get_dawei_home

        _ensure_channels_registered_fn()

        factory = ChannelRegistry.get_factory(channel_type)
        if factory is None:
            logger.error(f"[BRIDGE] No factory for channel type: {channel_type}")
            return False

        # Load saved config
        config_path = get_dawei_home() / "configs" / "channels.json"
        saved_config: dict[str, Any] = {}
        if config_path.exists():
            try:
                with config_path.open("r", encoding="utf-8") as f:
                    all_configs = json.load(f)
                saved_config = {
                    k: v for k, v in all_configs.get(channel_type, {}).items()
                    if k != "_enabled"
                }
            except Exception as e:
                logger.warning(f"[BRIDGE] Failed to load config for {channel_type}: {e}")

        # Create config + channel instance
        try:
            config = self.channel_manager._create_config(channel_type, saved_config)
            channel = factory(config, self.message_bus)
        except Exception as e:
            logger.error(f"[BRIDGE] Failed to create channel {channel_type}: {e}")
            return False

        # Register with channel manager
        self._channels_map[channel_type] = channel
        logger.info(f"[BRIDGE] Created channel instance: {channel_type}")

        # Start the channel
        try:
            await channel.start()
            logger.info(f"[BRIDGE] Started channel: {channel_type}")
        except Exception as e:
            logger.error(f"[BRIDGE] Failed to start channel {channel_type}: {e}")
            return False

        # Register webhook if applicable
        if self.webhook_server and isinstance(channel, WebhookChannel):
            from dawei.channels.channel import WebhookChannel
            path = getattr(channel, "webhook_path", f"/{channel_type}")
            secret = getattr(channel, "webhook_secret", None)

            async def _handler(payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
                return await channel.handle_webhook(payload, headers)

            self.webhook_server.register(
                path=path,
                channel_type=channel_type,
                handler=_handler,
                secret=secret,
            )
            logger.info(f"[BRIDGE] Registered webhook: {path} → {channel_type}")

        return True

    async def stop_channel(self, channel_type: str) -> None:
        """Stop a single channel by type."""
        channel = self._channels_map.pop(channel_type, None)
        if channel is None:
            return

        try:
            await channel.stop()
            logger.info(f"[BRIDGE] Stopped channel: {channel_type}")
        except Exception as e:
            logger.error(f"[BRIDGE] Error stopping channel {channel_type}: {e}")

        # Unregister webhook
        if self.webhook_server:
            path = getattr(channel, "webhook_path", f"/{channel_type}")
            self.webhook_server.unregister(path)

    def list_active_channels(self) -> list[str]:
        """List all channel types with running instances."""
        return [
            ct for ct, ch in self._channels_map.items()
            if ch.is_running
        ]

    async def start_enabled_channels(self) -> None:
        """Load enabled channels from config and start them.

        Called during server startup.
        """
        import json
        from dawei import get_dawei_home

        _ensure_channels_registered_fn()

        config_path = get_dawei_home() / "configs" / "channels.json"
        if not config_path.exists():
            logger.info("[BRIDGE] No channels.json found, skipping channel startup")
            return

        try:
            with config_path.open("r", encoding="utf-8") as f:
                all_configs = json.load(f)
        except Exception as e:
            logger.error(f"[BRIDGE] Failed to load channels.json: {e}")
            return

        for channel_type, entry in all_configs.items():
            if not entry.get("_enabled", False):
                continue

            logger.info(f"[BRIDGE] Starting enabled channel: {channel_type}")
            success = await self.start_channel(channel_type)
            if not success:
                logger.warning(f"[BRIDGE] Failed to start channel: {channel_type}")


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

_global_bridge: ChannelBridge | None = None


def get_global_bridge() -> ChannelBridge | None:
    """Get the global ChannelBridge singleton."""
    return _global_bridge


def set_global_bridge(bridge: ChannelBridge | None) -> None:
    """Set the global ChannelBridge singleton."""
    global _global_bridge
    _global_bridge = bridge
