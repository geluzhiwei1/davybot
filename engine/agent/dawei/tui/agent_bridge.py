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
from typing import List, Dict, Any

from dawei.agentic.agent import Agent
from dawei.agentic.agent_pdca_integration import add_pdca_to_agent

# from dawei.core.events import CORE_EVENT_BUS, TaskEvent, TaskEventType  # REMOVED: CORE_EVENT_BUS deleted
from dawei.core.events import TaskEvent, TaskEventType
from dawei.core.exceptions import (
    AgentInitializationError,
    ConfigurationError,
    WorkspaceError,
)
from dawei.entity.user_input_message import UserInputText
from dawei.workspace.user_workspace import UserWorkspace

logger = logging.getLogger(__name__)

# 与 server 自包含模式身份统一（= dawei/api/auth.py LOCAL_USER_ID，勿改名）。
# TUI 无认证态：未显式指定 --user 且注册表查不到 owner 时回落到该身份，
# 使 LLM/MCP 等用户级配置与 server 加载同一份（configs/local-user/）。
_SERVER_LOCAL_USER_ID = "local-user"


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
        user_id: str = "",
    ):
        """Initialize AgentBridge

        Args:
            workspace_path: Path to workspace directory
            llm_model: LLM model identifier
            mode: Agent mode
            ui_update_queue: Queue for forwarding events to UI
            user_id: 运行时用户身份（空=自动解析：--user > 注册表 owner_user_id > local-user）

        """
        self.workspace_path = Path(workspace_path).resolve()
        self.llm_model = llm_model
        self.mode = mode
        self.ui_queue = ui_update_queue
        self.user_id = user_id or ""

        # Agent and workspace (initialized later)
        self.agent: Agent | None = None
        self.user_workspace: UserWorkspace | None = None
        self.pdca_extension = None  # PDCA extension (initialized after agent)

        # Event tracking
        self._event_handlers: Dict[TaskEventType, str] = {}
        self._is_initialized = False

        # C23：轻量子任务状态 dict（id → {status, item_identity, batch_id,
        # parent_id, ts, todos}）。SUBTASK_* 事件到达时在 _forward_event 记账，
        # 供 SubtaskPanel/StatusBar 渲染 —— 纯 UI 态，不进任何会话历史。
        self.subtask_states: Dict[str, Dict[str, Any]] = {}

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

    def _resolve_user_id(self) -> str:
        """解析 TUI 运行时用户身份（与 server 版统一）

        优先级：
            1. --user 显式指定
            2. 工作区注册表（workspaces.json）的 owner_user_id（server 端同源）
            3. local-user（server 自包含模式固定身份，见 api/auth.py LOCAL_USER_ID）

        Returns:
            用户 ID（总返回非空值）
        """
        if self.user_id:
            logger.info(f"[AGENT_BRIDGE] User identity from --user: {self.user_id}")
            return self.user_id

        try:
            from dawei.workspace.workspace_manager import workspace_manager

            info = workspace_manager.get_workspace_by_path(str(self.workspace_path))
            owner = (info or {}).get("owner_user_id") or ""
            if owner:
                logger.info(f"[AGENT_BRIDGE] User identity from registry owner: {owner}")
                return owner
        except Exception as e:
            logger.warning(f"[AGENT_BRIDGE] Registry owner lookup failed, fallback to '{_SERVER_LOCAL_USER_ID}': {e}")

        logger.info(f"[AGENT_BRIDGE] User identity fallback to server local identity: {_SERVER_LOCAL_USER_ID}")
        return _SERVER_LOCAL_USER_ID

    async def _initialize_workspace(self) -> None:
        """Initialize UserWorkspace

        Raises:
            WorkspaceError: If workspace initialization fails

        """
        try:
            self.user_workspace = UserWorkspace(workspace_path=str(self.workspace_path))
            # 身份注入须在 initialize() 之前（context 按 (path, user_id) 分键，
            # 与 server 端 websocket/handlers/chat.py 同一模式）：
            #   --user 显式指定 > 注册表 owner_user_id > local-user（server 自包含身份）
            resolved_user = self._resolve_user_id()
            if resolved_user:
                self.user_workspace.user_id = resolved_user
                logger.info(f"[AGENT_BRIDGE] Workspace user identity: {resolved_user} (path={self.workspace_path})")
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
        """Subscribe to Agent events

        NOTE: CORE_EVENT_BUS has been removed - this function now uses agent.event_bus

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
            # C23：子任务生命周期 + todo 步级进度（TUI 进程内直收，
            # 此前订阅清单不含 SUBTASK_* → TUI 对子任务完全失明）
            TaskEventType.SUBTASK_CREATED,
            TaskEventType.SUBTASK_STARTED,
            TaskEventType.SUBTASK_COMPLETED,
            TaskEventType.SUBTASK_FAILED,
            TaskEventType.SUBTASK_ABORTED,
            TaskEventType.SUBTASK_STEERED,
            TaskEventType.SUBTASK_PROGRESS,
        ]

        # NOTE: CORE_EVENT_BUS has been removed - using agent.event_bus instead
        agent_event_bus = self.agent.event_bus if self.agent else None
        if not agent_event_bus:
            logger.error("[AGENT_BRIDGE] Agent event bus not available - cannot subscribe to events")
            raise RuntimeError("Agent event bus not available")

        try:
            for event_type in event_types:
                # ✅ 修复：使用内部async函数正确捕获event_type
                # lambda不能是async的，需要使用async def
                async def async_handler(event, et=event_type):
                    await self._forward_event(et, event)

                # Use agent's event bus instead of CORE_EVENT_BUS
                handler_id = agent_event_bus.on(
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
            raise RuntimeError(f"Invalid event type in subscription: {e}")
        except AttributeError as e:
            logger.error(f"Event bus not properly initialized: {e}", exc_info=True)
            self._cleanup_event_handlers()
            raise RuntimeError("Event system not available")
        except Exception as e:
            logger.error(f"Unexpected error during event subscription: {e}", exc_info=True)
            self._cleanup_event_handlers()
            raise RuntimeError(f"Event subscription failed: {e}")

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
        logger.debug(f"[AGENT_BRIDGE] _forward_event called: {event_type.value}")

        # C23：SUBTASK_* 事件先记账到状态 dict（异常安全 —— 纯 UI 态
        # 记账失败只记日志，绝不阻断向 UI 队列的转发）
        self._update_subtask_state(event_type, event)

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
            logger.debug(f"[AGENT_BRIDGE] Forwarded event to UI: {event_type.value}")
        except asyncio.CancelledError:
            logger.warning(f"Event forwarding cancelled for {event_type.value}")
            raise
        except Exception as e:
            logger.critical(f"Failed to forward event to UI queue: {e}", exc_info=True)
            # Re-raise - UI queue failures are critical
            raise RuntimeError(f"Event forwarding failed: {e}")

    def _update_subtask_state(self, event_type: TaskEventType, event: TaskEvent) -> None:
        """C23：从 SUBTASK_* 事件维护轻量状态 dict

        生命周期事件写 status/item_identity/batch_id；subtask_progress 额外
        写 todos 摘要 {total, completed, current}。非 SUBTASK_* 事件直接返回。
        """
        try:
            if not str(event_type.value).startswith("subtask_"):
                return
            data = getattr(event, "data", None)
            if not isinstance(data, dict):
                return
            subtask_id = data.get("subtask_id")
            if not subtask_id:
                return
            state = self.subtask_states.setdefault(str(subtask_id), {})
            if data.get("parent_id"):
                state["parent_id"] = str(data["parent_id"])
            if data.get("batch_id"):
                state["batch_id"] = str(data["batch_id"])
            if data.get("item_identity"):
                state["item_identity"] = str(data["item_identity"])[:40]
            if event_type is TaskEventType.SUBTASK_PROGRESS:
                state["todos"] = data.get("todos") or {}
            else:
                # 生命周期事件：status（TaskStatus value）优先，缺省回落事件名
                state["status"] = str(data.get("status") or data.get("event") or event_type.value.replace("subtask_", ""))
            state["ts"] = str(getattr(event, "timestamp", "") or "")
        except Exception:  # noqa: BLE001 — 纯 UI 态记账失败不影响事件转发
            logger.exception("[AGENT_BRIDGE] Failed to update subtask state dict: ")

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

    async def answer_followup_question(self, tool_call_id: str, answer: str) -> bool:
        """Deliver the user's answer to a pending followup question (user_question tool)

        Mirrors the websocket FOLLOWUP_RESPONSE path
        (websocket/handlers/chat.py:_process_followup_response): iterate the
        execution engine's node executors until one accepts the answer and
        resolves the asyncio.Future it is awaiting.

        Args:
            tool_call_id: ID of the ask_followup_question tool call
            answer: User's answer text

        Returns:
            True if a pending followup accepted the answer, False otherwise
        """
        if self.agent is None:
            logger.error("Cannot answer followup question: agent not available")
            return False

        engine = getattr(self.agent, "execution_engine", None)
        executors = getattr(engine, "_node_executors", None)
        if not executors:
            logger.warning("Cannot answer followup question: no node executors")
            return False

        logger.info(f"Delivering followup answer for tool_call {tool_call_id}")
        for node_id, executor in list(executors.items()):
            try:
                if await executor.handle_followup_response(tool_call_id, answer):
                    logger.info(f"Followup answer delivered to node {node_id}")
                    return True
            except Exception as e:
                # One broken executor must not block delivery to the others
                logger.error(f"Error delivering followup answer to node {node_id}: {e}", exc_info=True)

        logger.warning(f"No node executor accepted followup answer for tool_call_id: {tool_call_id}")
        return False

    def _cleanup_event_handlers(self) -> None:
        """Cleanup event handlers to prevent memory leaks"""
        agent_event_bus = self.agent.event_bus if self.agent else None

        for event_type, handler_id in self._event_handlers.items():
            try:
                if agent_event_bus:
                    agent_event_bus.off(event_type.value, handler_id)
                    logger.debug(f"Unsubscribed from event: {event_type.value}")
                else:
                    logger.warning(f"Cannot unsubscribe from {event_type.value}: agent event bus not available")
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

    def get_pdca_status(self) -> Dict[str, Any] | None:
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
