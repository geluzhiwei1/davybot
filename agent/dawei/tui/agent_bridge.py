# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""AgentBridge - Direct Integration between TUI and Agent

This is the CRITICAL component that enables TUI to interact with Agent
without going through WebSocket. It manages Agent lifecycle and subscribes
to CORE_EVENT_BUS events.
"""

import asyncio
import logging
from pathlib import Path
from typing import Any

from dawei.agentic.agent import Agent
from dawei.agentic.agent_pdca_integration import add_pdca_to_agent
from dawei.core.events import CORE_EVENT_BUS, TaskEvent, TaskEventType
from dawei.core.exceptions import (
    AgentInitializationError,
    ConfigurationError,
    WorkspaceError,
)
from dawei.entity.user_input_message import UserInputText
from dawei.workspace.user_workspace import UserWorkspace

logger = logging.getLogger(__name__)


class AgentBridge:
    """Bridge between TUI and Agent.

    Manages Agent lifecycle and subscribes to CORE_EVENT_BUS events,
    forwarding them to the UI via an async queue.
    """

    def __init__(
        self,
        workspace_path: str,
        llm_model: str,
        mode: str,
        ui_update_queue: asyncio.Queue,
    ):
        """Initialize AgentBridge

        Args:
            workspace_path: Path to workspace directory
            llm_model: LLM model identifier
            mode: Agent mode
            ui_update_queue: Queue for forwarding events to UI

        """
        self.workspace_path = Path(workspace_path).resolve()
        self.llm_model = llm_model
        self.mode = mode
        self.ui_queue = ui_update_queue

        # Agent and workspace (initialized later)
        self.agent: Agent | None = None
        self.user_workspace: UserWorkspace | None = None
        self.pdca_extension = None  # PDCA extension (initialized after agent)

        # Event tracking
        self._event_handlers: dict[TaskEventType, str] = {}
        self._is_initialized = False

        logger.debug(f"AgentBridge created for workspace: {self.workspace_path}")

    async def initialize(self) -> None:
        """Initialize Agent and workspace

        This creates the UserWorkspace and Agent instances,
        preparing the bridge for message handling.
        """
        if self._is_initialized:
            logger.warning("AgentBridge already initialized")
            return

        logger.info("Initializing AgentBridge...")

        # Initialize workspace
        await self._initialize_workspace()

        # Initialize agent
        await self._initialize_agent()

        self._is_initialized = True
        logger.info("AgentBridge initialization complete")

    async def _initialize_workspace(self) -> None:
        """Initialize UserWorkspace

        Raises:
            WorkspaceError: If workspace initialization fails

        """
        try:
            self.user_workspace = UserWorkspace(workspace_path=str(self.workspace_path))
            await self.user_workspace.initialize()
        except FileNotFoundError:
            raise WorkspaceError(f"Workspace path not found: {self.workspace_path}")
        except PermissionError:
            raise WorkspaceError(
                f"Permission denied accessing workspace: {self.workspace_path}",
            )
        except Exception as e:
            raise WorkspaceError(f"Failed to initialize workspace: {e}")

    async def _initialize_agent(self) -> None:
        """Initialize Agent with PDCA extension

        Raises:
            AgentInitializationError: If agent initialization fails
            ConfigurationError: If agent configuration is invalid

        """
        try:
            self.agent = await Agent.create_with_default_engine(
                user_workspace=self.user_workspace,
                config={
                    "llm_model": self.llm_model,
                    "mode": self.mode,
                    "enable_auto_mode_switch": True,
                },
            )
            await self.agent.initialize()
            self.pdca_extension = add_pdca_to_agent(self.agent)
        except Exception as e:
            # Classify error type based on message content
            error_msg = str(e)
            if "LLM" in error_msg.upper() or "MODEL" in error_msg.upper():
                logger.error(f"LLM model configuration error: {e}", exc_info=True)
                raise AgentInitializationError(
                    f"Invalid LLM model '{self.llm_model}': {e}",
                )
            if "configuration" in error_msg.lower() or "config" in error_msg.lower():
                logger.error(f"Agent configuration error: {e}", exc_info=True)
                raise ConfigurationError(f"Agent configuration failed: {e}")
            logger.error(f"Agent initialization runtime error: {e}", exc_info=True)
            raise AgentInitializationError(f"Agent initialization failed: {e}")

    async def subscribe_to_events(self) -> None:
        """Subscribe to CORE_EVENT_BUS events

        Subscribes to all relevant event types and forwards them
        to the UI update queue.
        """
        if not self._is_initialized:
            raise RuntimeError("AgentBridge not initialized. Call initialize() first.")

        logger.info("Subscribing to Agent events...")

        # Subscribe to all relevant events
        event_types = [
            TaskEventType.CONTENT_STREAM,
            TaskEventType.REASONING,
            TaskEventType.TOOL_CALL_START,
            TaskEventType.TOOL_CALL_PROGRESS,
            TaskEventType.TOOL_CALL_RESULT,
            TaskEventType.TASK_STARTED,
            TaskEventType.TASK_COMPLETED,
            TaskEventType.MODE_SWITCHED,
            TaskEventType.ERROR_OCCURRED,
            TaskEventType.MODEL_SELECTED,
            TaskEventType.FILES_REFERENCED,
            TaskEventType.FOLLOWUP_QUESTION,
            # PDCA events
            TaskEventType.PDCA_CYCLE_STARTED,
            TaskEventType.PDCA_PHASE_ADVANCED,
            TaskEventType.PDCA_CYCLE_COMPLETED,
            TaskEventType.PDCA_DOMAIN_DETECTED,
        ]

        try:
            for event_type in event_types:
                # ✅ 修复：使用内部async函数正确捕获event_type
                # lambda不能是async的，需要使用async def
                async def async_handler(event, et=event_type):
                    await self._forward_event(et, event)

                handler_id = CORE_EVENT_BUS.on(
                    event_type.value,
                    async_handler,  # ✅ 正确的async handler
                )
                self._event_handlers[event_type] = handler_id
                logger.info(f"[AGENT_BRIDGE] Subscribed to event: {event_type.value}")

            logger.info(f"[AGENT_BRIDGE] Subscribed to {len(event_types)} event types")
        except KeyError as e:
            logger.error(f"Invalid event type referenced: {e}", exc_info=True)
            # Clean up any partial subscriptions
            self._cleanup_event_handlers()
            raise EventSystemError(f"Invalid event type in subscription: {e}")
        except AttributeError as e:
            logger.error(f"CORE_EVENT_BUS not properly initialized: {e}", exc_info=True)
            self._cleanup_event_handlers()
            raise EventSystemError("Event system not available")
        except Exception as e:
            logger.error(f"Unexpected error during event subscription: {e}", exc_info=True)
            self._cleanup_event_handlers()
            raise EventSystemError(f"Event subscription failed: {e}")

    async def _forward_event(self, event_type: TaskEventType, event: TaskEvent) -> None:
        """Forward event to UI queue

        Args:
            event_type: Type of event
            event: Event object

        Raises:
            ValueError: If event structure is invalid
            RuntimeError: If UI queue is not available
            asyncio.CancelledError: If operation is cancelled

        """
        logger.info(f"[AGENT_BRIDGE] _forward_event called: {event_type.value}")

        # Create event dict for UI
        event_dict = {
            "event_type": event_type,
            "event_id": event.event_id,
            "task_id": event.task_id,
            "source": event.source,
            "timestamp": event.timestamp,
            "data": event.data,
        }

        # Forward to UI queue - Fast Fail if queue is broken
        try:
            await self.ui_queue.put(event_dict)
            logger.info(f"[AGENT_BRIDGE] Forwarded event to UI: {event_type.value}, data keys: {list(event.data.keys()) if isinstance(event.data, dict) else 'N/A'}")
        except asyncio.CancelledError:
            logger.warning(f"Event forwarding cancelled for {event_type.value}")
            raise
        except Exception as e:
            logger.critical(f"Failed to forward event to UI queue: {e}", exc_info=True)
            # Re-raise - UI queue failures are critical
            raise RuntimeError(f"Event forwarding failed: {e}")

    async def send_message(self, message: str) -> None:
        """Send user message to Agent (direct call)

        Args:
            message: User message text

        Raises:
            RuntimeError: If AgentBridge not initialized or Agent not available
            ValueError: If message is invalid

        """
        if not self._is_initialized:
            raise RuntimeError("AgentBridge not initialized. Call initialize() first.")

        logger.info(f"Sending message to Agent: {message[:100]}...")

        # Create UserInputText message
        user_message = UserInputText(text=message)

        # Send directly to Agent (no WebSocket!)
        # Fast Fail on any error
        try:
            await self.agent.process_message(user_message)
        except AttributeError as e:
            logger.error(f"Agent not properly initialized: {e}", exc_info=True)
            raise RuntimeError("Agent system not properly initialized")
        except Exception as e:
            logger.error(f"Failed to send message to Agent: {e}", exc_info=True)
            # Re-raise with context
            raise

        logger.info("Message sent to Agent successfully")

    def _cleanup_event_handlers(self) -> None:
        """Cleanup event handlers to prevent memory leaks"""
        for event_type, handler_id in self._event_handlers.items():
            try:
                CORE_EVENT_BUS.off(event_type.value, handler_id)
                logger.debug(f"Unsubscribed from event: {event_type.value}")
            except KeyError as e:
                logger.warning(f"Event handler not found for cleanup: {e}")
            except Exception as e:
                logger.error(f"Error unsubscribing from {event_type.value}: {e}", exc_info=True)

        self._event_handlers.clear()

    async def stop_agent(self) -> str:
        """Stop Agent execution

        Returns:
            Result summary

        """
        if not self._is_initialized:
            raise RuntimeError("AgentBridge not initialized")

        result = await self.agent.stop()
        logger.info("Agent stopped")
        return result

    def get_pdca_status(self) -> dict[str, Any] | None:
        """Get PDCA cycle status

        Returns:
            PDCA status information or None if no active cycle

        """
        if self.pdca_extension:
            return self.pdca_extension.get_pdca_status()
        return None

    async def cleanup(self) -> None:
        """Cleanup resources

        Unsubscribes from events and cleans up Agent/workspace.
        """
        logger.info("Cleaning up AgentBridge...")

        # Unsubscribe from events
        self._cleanup_event_handlers()

        # Cleanup agent
        if self.agent:
            await self._cleanup_agent()

        # Cleanup workspace
        if self.user_workspace:
            await self._cleanup_workspace()

        self._is_initialized = False
        logger.info("AgentBridge cleanup complete")

    async def _cleanup_agent(self) -> None:
        """Cleanup Agent resources"""
        try:
            await self.agent.cleanup()
        except Exception as e:
            logger.error(f"Error cleaning up Agent: {e}", exc_info=True)

    async def _cleanup_workspace(self) -> None:
        """Cleanup UserWorkspace resources"""
        try:
            await self.user_workspace.cleanup()
        except Exception as e:
            logger.error(f"Error cleaning up UserWorkspace: {e}", exc_info=True)
