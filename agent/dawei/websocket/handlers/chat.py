# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""聊天消息处理器

处理用户发送的聊天消息，使用新的 Agent 接口进行处理。
"""

import time
import uuid
from datetime import datetime, timezone
from dawei.core.datetime_compat import UTC
from typing import List, Dict, Any

from dawei.core.events import TaskEvent
from dawei.sandbox.lightweight_executor import LightweightSandbox
from dawei.websocket.protocol import (
    AgentCompleteMessage,
    AgentStartMessage,
    AgentStopMessage,
    AgentStoppedMessage,
    BaseWebSocketMessage,
    ErrorMessage,
    LLMApiCompleteMessage,
    LLMApiRequestMessage,
    MessageType,
    PDACycleCompleteMessage,
    PDACycleStartMessage,
    PDCAPhaseAdvanceMessage,
    PDCAStatusUpdateMessage,
    StreamCompleteMessage,
    StreamContentMessage,
    StreamReasoningMessage,
    StreamToolCallMessage,
    StreamUsageMessage,
    SystemWebSocketMessage,
    TaskNodeCompleteMessage,
    TaskNodeProgressMessage,
    TaskNodeStartMessage,
    ToolCallProgressMessage,
    ToolCallResultMessage,
    ToolCallStartMessage,
    WebSocketMessage,
)

from .base import AsyncMessageHandler

# Alias for backward compatibility
SystemMessage = SystemWebSocketMessage
from dawei.agentic.agent import Agent

# PDCA Integration
from dawei.agentic.agent_pdca_integration import add_pdca_to_agent
from dawei.agentic.pdca_context import PDCAPhase
from dawei.async_task.task_manager import AsyncTaskManager
from dawei.async_task.types import RetryPolicy, TaskDefinition, TaskStatus
from dawei.core import local_context
from dawei.core.events import TaskEventType
from dawei.core.exceptions import (
    AgentInitializationError,
    ConfigurationError,
    LLMError,
    ValidationError,
    WebSocketError,
)
from dawei.entity.user_input_message import UserInputMessage
from dawei.logg.logging import get_logger
from dawei.workspace.user_workspace import UserWorkspace
from dawei.workspace.workspace_manager import workspace_manager

logger = get_logger(__name__)


class ChatHandler(AsyncMessageHandler):
    """聊天消息处理器，使用新的 Agent 接口。

    功能:
    - 处理用户聊天消息并创建Agent实例
    - 管理Agent生命周期（创建、执行、暂停、恢复、停止）
    - 转发Agent事件到WebSocket客户端
    - 处理系统命令（通过轻量级沙箱）
    - 管理任务并发和重试策略

    配置常量:
    - DEFAULT_MAX_CONCURRENT_TASKS: 默认最大并发任务数
    - DEFAULT_TASK_TIMEOUT: 默认任务超时时间（秒）
    - DEFAULT_RETRY_ATTEMPTS: 默认重试次数
    - DEFAULT_RETRY_DELAY: 默认重试延迟（秒）
    - MAX_OUTPUT_SIZE: 系统命令输出最大限制（字节）

    Attributes:
        _active_agents: 存储活跃的Agent实例
        _task_to_session_map: 任务ID到会话ID的映射
        _task_manager: 异步任务管理器
        sandbox_executor: 轻量级沙箱执行器

    """

    # 配置常量
    DEFAULT_MAX_CONCURRENT_TASKS = 10
    DEFAULT_TASK_TIMEOUT = 900.0  # 15分钟（支持大型HTML/代码生成）
    DEFAULT_RETRY_ATTEMPTS = 2
    DEFAULT_RETRY_DELAY = 1.0
    DEFAULT_MAX_RETRY_DELAY = 10.0
    MAX_OUTPUT_SIZE = 100000  # 100KB

    def __init__(self, max_concurrent_tasks: int | None = None):
        _max_tasks = max_concurrent_tasks or self.DEFAULT_MAX_CONCURRENT_TASKS
        super().__init__(max_concurrent_tasks=_max_tasks)

        # 存储活跃的 Agent 实例
        self._active_agents: Dict[str, Agent] = {}

        # 存储任务ID到会话ID的映射，用于回调中查找正确的会话ID
        self._task_to_session_map: Dict[str, str] = {}

        # 🔧 修复：存储任务ID到事件处理器ID的映射，用于清理
        self._task_event_handler_ids: Dict[str, Dict[str, str]] = {}

        # 🔧 修复：跟踪每个任务的 LLM API 状态，用于停止时清理
        self._task_llm_api_state: Dict[str, Dict[str, Any]] = {}

        # 初始化异步任务管理器
        self._task_manager = AsyncTaskManager()

        # 设置任务状态回调
        self._task_manager.set_progress_callback(self._on_task_progress)
        self._task_manager.set_state_change_callback(self._on_task_state_change)
        self._task_manager.set_error_callback(self._on_task_error)
        self._task_manager.set_completion_callback(self._on_task_completion)

        # 初始化轻量级沙箱执行器（无需Docker）
        self.sandbox_executor = LightweightSandbox()
        logger.info("[CHAT_HANDLER] LightweightSandbox initialized (no Docker required)")

    def get_supported_types(self) -> List[str]:
        """获取支持的消息类型"""
        return [
            MessageType.USER_MESSAGE,
            MessageType.FOLLOWUP_RESPONSE,
            MessageType.FOLLOWUP_CANCEL,
            MessageType.AGENT_STOP,
        ]

    async def on_initialize(self):
        """初始化时的回调"""
        await super().on_initialize()

        # 启动任务管理器
        await self._task_manager.start()

        logger.info("聊天处理器已初始化 (使用新的 Agent 接口)")

    async def process_message(
        self,
        session_id: str,
        message: WebSocketMessage,
        message_id: str,
    ) -> WebSocketMessage | None:
        """处理用户消息，创建并启动一个 Agent 实例。"""
        local_context.set_local_context(session_id=session_id, message_id=message_id)

        # 处理 FOLLOWUP_RESPONSE 消息
        if message.type == MessageType.FOLLOWUP_RESPONSE:
            return await self._process_followup_response(session_id, message)

        # 处理 FOLLOWUP_CANCEL 消息
        if message.type == MessageType.FOLLOWUP_CANCEL:
            return await self.handle_followup_cancel(session_id, message)

        # 处理 AGENT_STOP 消息
        if message.type == MessageType.AGENT_STOP:
            return await self._process_agent_stop(session_id, message)

        # 处理 USER_MESSAGE 消息
        session_data = await self.get_session(session_id)
        if not session_data:
            logger.error(f"找不到会话: {session_id}")
            return await self.send_error_message(
                session_id,
                "SESSION_NOT_FOUND",
                "会话不存在，请重新连接",
            )

        task_id = str(uuid.uuid4())

        start_message = TaskNodeStartMessage(
            session_id=session_id,
            task_id=task_id,
            task_node_id=task_id,
            node_type="agent_task",
            description="正在处理消息...",
        )
        await self.send_message(session_id, start_message)

        # 使用AsyncTaskManager管理任务，替换直接的asyncio.create_task调用
        task_def = TaskDefinition(
            task_id=task_id,
            name=f"AgentTask-{task_id[:8]}",
            description="处理用户消息的Agent任务",
            executor=self._execute_agent_task,
            parameters={
                "session_id": session_id,
                "task_id": task_id,
                "user_message": message,
            },
            timeout=self.DEFAULT_TASK_TIMEOUT,
            retry_policy=RetryPolicy(
                max_attempts=self.DEFAULT_RETRY_ATTEMPTS,
                base_delay=self.DEFAULT_RETRY_DELAY,
                max_delay=self.DEFAULT_MAX_RETRY_DELAY,
            ),
        )

        # 存储任务ID到会话ID的映射
        self._task_to_session_map[task_id] = session_id

        # 提交任务到任务管理器执行
        await self._task_manager.submit_task(task_def)

        return None

    async def _process_followup_response(
        self,
        session_id: str,
        message: WebSocketMessage,
    ) -> WebSocketMessage | None:
        """处理前端发来的追问回复

        Args:
            session_id: 会话ID
            message: FollowupResponseMessage

        Returns:
            None

        """
        from dawei.websocket.protocol import FollowupResponseMessage

        if not isinstance(message, FollowupResponseMessage):
            logger.error(f"Invalid message type for FOLLOWUP_RESPONSE: {type(message)}")
            return await self.send_error_message(
                session_id,
                "INVALID_MESSAGE_TYPE",
                "Invalid message type for followup response",
            )

        task_id = message.task_id
        tool_call_id = message.tool_call_id
        response = message.response

        logger.info(
            f"Received followup response for task {task_id}, tool_call {tool_call_id}: {response[:50]}...",
        )

        # 找到对应的 Agent 实例并处理响应
        if task_id in self._active_agents:
            agent = self._active_agents[task_id]

            # 获取任务节点执行引擎
            if hasattr(agent, "execution_engine") and agent.execution_engine:
                # 查找所有任务节点执行引擎
                for (
                    task_node_id,
                    node_executor,
                ) in agent.execution_engine._node_executors.items():
                    success = await node_executor.handle_followup_response(tool_call_id, response)
                    if success:
                        logger.info(
                            f"Successfully delivered followup response to node {task_node_id}",
                        )
                        return None

                logger.warning(f"No node executor found for tool_call_id: {tool_call_id}")
            else:
                logger.warning(f"Agent for task {task_id} has no execution_engine")
        else:
            logger.warning(f"No active agent found for task {task_id}")

        return None

    async def handle_followup_cancel(
        self,
        session_id: str,
        message: BaseWebSocketMessage,
    ) -> WebSocketMessage | None:
        """处理前端发来的追问取消

        Args:
            session_id: 会话ID
            message: FollowupCancelMessage

        Returns:
            None

        """
        from dawei.websocket.protocol import FollowupCancelMessage

        if not isinstance(message, FollowupCancelMessage):
            logger.error(f"Invalid message type for FOLLOWUP_CANCEL: {type(message)}")
            return await self.send_error_message(
                session_id,
                "INVALID_MESSAGE_TYPE",
                "Invalid message type for followup cancel",
            )

        task_id = message.task_id
        tool_call_id = message.tool_call_id
        reason = message.reason

        logger.info(
            f"Received followup cancel for task {task_id}, tool_call {tool_call_id}, reason: {reason}",
        )

        # 找到对应的 Agent 实例并处理取消
        if task_id in self._active_agents:
            agent = self._active_agents[task_id]

            # 获取任务节点执行引擎
            if hasattr(agent, "execution_engine") and agent.execution_engine:
                # 查找所有任务节点执行引擎
                for (
                    task_node_id,
                    node_executor,
                ) in agent.execution_engine._node_executors.items():
                    success = await node_executor.handle_followup_cancel(tool_call_id, reason)
                    if success:
                        logger.info(
                            f"Successfully delivered followup cancel to node {task_node_id}",
                        )
                        return None

                logger.warning(f"No node executor found for tool_call_id: {tool_call_id}")
            else:
                logger.warning(f"Agent for task {task_id} has no execution_engine")
        else:
            logger.warning(f"No active agent found for task {task_id}")

        return None

    # ==================== Agent 任务执行辅助方法 ====================

    async def _get_and_validate_workspace(
        self,
        user_message: UserInputMessage,
    ) -> tuple[str, str, UserWorkspace]:
        """获取和验证工作区

        Args:
            user_message: 用户消息

        Returns:
            tuple: (workspace_id, workspace_path, user_workspace)

        Raises:
            ValueError: 工作区验证失败
            RuntimeError: 工作区加载失败

        """
        if not user_message.metadata:
            raise ValueError("消息元数据 (metadata) 为空，无法获取 workspaceId。")

        workspace_id = user_message.metadata.get("workspaceId")
        if not workspace_id:
            raise ValueError("消息元数据中缺少 Workspace ID。")

        logger.info(f"收到的用户消息: {user_message}")
        logger.info(f"消息 metadata: {user_message.metadata}")

        # 从全局管理器获取工作区信息
        workspace_info = workspace_manager.get_workspace_by_id(workspace_id)
        if not workspace_info:
            raise ValueError(f"找不到工作区信息: '{workspace_id}'")

        workspace_path = workspace_info.get("path")
        if not workspace_path:
            raise ValueError(f"工作区 '{workspace_id}' 的配置中缺少 'path' 字段。")

        # 加载 UserWorkspace 实例并确保初始化
        user_workspace = UserWorkspace(workspace_path)
        if not user_workspace:
            raise RuntimeError(f"无法从路径加载工作区: '{workspace_path}'")

        # 确保工作区已初始化，这样 tool_manager 就不会为 None
        if not user_workspace.is_initialized():
            await user_workspace.initialize()

        return workspace_id, workspace_path, user_workspace

    async def _update_user_ui_context(
        self,
        user_workspace: UserWorkspace,
        user_message: UserInputMessage,
    ) -> None:
        """更新用户UI上下文

        Args:
            user_workspace: 用户工作区
            user_message: 用户消息

        Raises:
            ValueError: UI上下文数据无效
            IOError: 保存设置失败

        """
        if not (hasattr(user_message, "user_ui_context") and user_message.user_ui_context):
            return

        from dawei.entity.system_info import UserUIContext

        ui_context_data = user_message.user_ui_context

        try:
            # 创建UserUIContext对象
            new_ui_context = UserUIContext.from_dict(ui_context_data)

            # 更新workspace的user_ui_context
            user_workspace.workspace_info.user_ui_context = new_ui_context

            # 持久化更新
            await user_workspace.persistence_manager.save_workspace_settings(
                user_workspace.workspace_info.to_dict(),
            )

        except ValueError as e:
            logger.error(f"[CHAT_HANDLER] Invalid UI context data: {e}", exc_info=True)
            raise
        except OSError as e:
            logger.error(f"[CHAT_HANDLER] Failed to save UI context: {e}", exc_info=True)
            raise

    async def _load_or_create_conversation(
        self,
        user_workspace: UserWorkspace,
        user_message: UserInputMessage,
    ) -> None:
        """加载或创建会话

        Args:
            user_workspace: 用户工作区
            user_message: 用户消息

        Raises:
            FileNotFoundError: 会话历史文件不存在
            IOError: 读取会话历史失败

        """
        conversation_id = user_message.metadata.get("conversationId")
        if not conversation_id:
            if user_workspace.current_conversation:
                return

            from dawei.conversation.conversation import Conversation

            user_workspace.current_conversation = Conversation()
            logger.info(
                f"[CHAT_HANDLER] Created new conversation with ID: {user_workspace.current_conversation.id}"
            )
            return


        try:
            # 尝试从历史记录中加载会话
            from dawei.conversation.conversation_history_manager import (
                ConversationHistoryManager,
            )

            conv_manager = ConversationHistoryManager(workspace_path=user_workspace.absolute_path)
            await conv_manager.build_from_dir()

            conversation = await conv_manager.get_by_id(conversation_id)
            if conversation:
                user_workspace.current_conversation = conversation
            else:
                # 🔧 修复：会话找不到时，检查是否是当前内存中的会话
                if (
                    user_workspace.current_conversation
                    and user_workspace.current_conversation.id == conversation_id
                ):
                    # 如果请求的 conversation_id 正好是当前内存中的会话，直接复用
                    logger.info(
                        f"[CHAT_HANDLER] Conversation {conversation_id} not found on disk, but matches current in-memory conversation, reusing it"
                    )
                elif user_workspace.current_conversation:
                    logger.warning(
                        f"[CHAT_HANDLER] Conversation {conversation_id} not found, reusing current conversation: {user_workspace.current_conversation.id}",
                    )
                else:
                    logger.warning(
                        f"[CHAT_HANDLER] Conversation {conversation_id} not found and no current conversation, creating new one",
                    )
                    from dawei.conversation.conversation import Conversation

                    user_workspace.current_conversation = Conversation()

        except FileNotFoundError as e:
            logger.error(f"[CHAT_HANDLER] Conversation history not found: {e}", exc_info=True)
            raise
        except OSError as e:
            logger.error(f"[CHAT_HANDLER] Failed to load conversation: {e}", exc_info=True)
            raise

    async def _create_and_initialize_agent(self, user_workspace: UserWorkspace) -> Agent:
        """创建和初始化 Agent

        Args:
            user_workspace: 用户工作区

        Returns:
            Agent: 初始化后的 Agent 实例

        Raises:
            RuntimeError: Agent 创建或初始化失败

        """
        try:
            agent = await Agent.create_with_default_engine(user_workspace)
            logger.info("[CHAT_HANDLER] Agent created successfully, now initializing...")
            await agent.initialize()
            logger.info("[CHAT_HANDLER] Agent initialized successfully")
            return agent
        except (ConfigurationError, ValidationError, AgentInitializationError) as e:
            logger.error(
                f"[CHAT_HANDLER] Failed to create or initialize agent: {e}",
                exc_info=True,
                extra={
                    "workspace_id": user_workspace.workspace_info.id,
                    "error_type": type(e).__name__,
                },
            )
            raise
        except AttributeError as e:
            # 特殊处理 AttributeError（通常是 logger 未初始化）
            logger.error(
                f"[CHAT_HANDLER] AttributeError during agent initialization (possibly logger issue): {e}",
                exc_info=True,
                extra={
                    "workspace_id": user_workspace.workspace_info.id,
                    "error_type": "AttributeError",
                },
            )
            raise RuntimeError(f"Agent initialization failed due to internal error: {e}")
        except Exception as e:
            logger.error(
                f"[CHAT_HANDLER] Unexpected error during agent initialization: {e}",
                exc_info=True,
                extra={
                    "workspace_id": user_workspace.workspace_info.id,
                    "error_type": type(e).__name__,
                },
            )
            raise RuntimeError(f"Agent initialization failed: {e}")

    async def _configure_agent_mode(
        self,
        agent: Agent,
        user_workspace: UserWorkspace,
        pdca_extension=None,
    ) -> None:
        """从 user_ui_context 同步 mode 到 agent.config

        Args:
            agent: Agent 实例
            user_workspace: 用户工作区
            pdca_extension: PDCA扩展实例（可选）

        """
        # 优先使用PDCA推荐的mode，其次是用户选择的mode
        if pdca_extension and pdca_extension.pdca_enabled and pdca_extension.current_cycle:
            # 使用PDCA当前阶段对应的mode
            pdca_mode = pdca_extension.get_current_mode_name()
            agent.config.mode = pdca_mode
            logger.info(f"[CHAT_HANDLER] PDCA mode set to: {pdca_mode}")
        elif user_workspace.workspace_info.user_ui_context and user_workspace.workspace_info.user_ui_context.current_mode:
            requested_mode = user_workspace.workspace_info.user_ui_context.current_mode
            logger.info(f"[CHAT_HANDLER] Setting agent mode from user_ui_context: {requested_mode}")

            # 直接使用前端发送的模式名称，不做映射
            agent.config.mode = requested_mode
            logger.info(f"[CHAT_HANDLER] ✅ Agent mode set to: {requested_mode}")
        else:
            logger.info(
                f"[CHAT_HANDLER] No current_mode in user_ui_context, using default: {agent.config.mode}",
            )

    async def _integrate_pdca_if_needed(
        self,
        agent: Agent,
        session_id: str,
        task_id: str,
        _user_workspace: UserWorkspace,
        user_message: UserInputMessage,
    ):
        """集成PDCA扩展（如果任务需要）

        Args:
            agent: Agent实例
            session_id: 会话ID
            task_id: 任务ID
            user_workspace: 用户工作区
            user_message: 用户消息

        Returns:
            PDCA扩展实例（如果启用了PDCA），否则返回None

        """
        try:
            # 1. 添加PDCA扩展到Agent
            pdca_extension = add_pdca_to_agent(agent)

            # 2. 检查任务是否需要PDCA
            task_description = user_message.content
            should_use_pdca = pdca_extension.should_use_pdca(task_description)

            logger.info(f"[PDCA] Task complexity check: should_use_pdca={should_use_pdca}")

            if not should_use_pdca:
                # 简单任务，禁用PDCA
                pdca_extension.disable_pdca()
                logger.info("[PDCA] Simple task detected, PDCA disabled")
                return None

            # 3. 复杂任务，启动PDCA循环
            logger.info("[PDCA] Complex task detected, starting PDCA cycle")

            # 启动PDCA循环
            pdca_cycle = pdca_extension.start_pdca_cycle(
                session_id=session_id,
                task_description=task_description,
                task_goals=[f"Complete: {task_description[:100]}"],
                success_criteria=[
                    "Task completed successfully",
                    "Quality standards met",
                ],
            )

            # 4. 发送PDCA循环启动消息
            await self._send_pdca_cycle_start_message(
                session_id=session_id,
                task_id=task_id,
                pdca_cycle=pdca_cycle,
            )

            # 5. 发送PDCA状态更新消息
            await self._send_pdca_status_update_message(
                session_id=session_id,
                task_id=task_id,
                pdca_extension=pdca_extension,
            )

            logger.info(f"[PDCA] PDCA cycle started successfully: {pdca_cycle.cycle_id}")

            return pdca_extension

        except Exception as e:
            logger.error(f"[PDCA] Failed to integrate PDCA: {e}", exc_info=True)
            # PDCA失败不应阻止Agent执行，返回None让Agent继续
            return None

    async def _send_pdca_cycle_start_message(self, session_id: str, _task_id: str, pdca_cycle):
        """发送PDCA循环启动消息

        Args:
            session_id: 会话ID
            task_id: 任务ID
            pdca_cycle: PDCA循环上下文

        """
        try:
            message = PDACycleStartMessage(
                session_id=session_id,
                cycle_id=pdca_cycle.cycle_id,
                domain=pdca_cycle.domain.value,
                task_description=pdca_cycle.task_description,
                task_goals=pdca_cycle.task_goals or [],
                success_criteria=pdca_cycle.success_criteria or [],
            )

            await self.send_message(session_id, message)
            logger.info(f"[PDCA] Sent PDCA_CYCLE_START message: {pdca_cycle.cycle_id}")

        except Exception as e:
            logger.error(f"[PDCA] Failed to send PDCA cycle start message: {e}", exc_info=True)

    async def _send_pdca_status_update_message(self, session_id: str, _task_id: str, pdca_extension):
        """发送PDCA状态更新消息

        Args:
            session_id: 会话ID
            task_id: 任务ID
            pdca_extension: PDCA扩展实例

        """
        try:
            status = pdca_extension.get_pdca_status()

            if status and status.get("active"):
                # 构建phases字典
                phases = {
                    PDCAPhase.PLAN.value: "pending",
                    PDCAPhase.DO.value: "pending",
                    PDCAPhase.CHECK.value: "pending",
                    PDCAPhase.ACT.value: "pending",
                }

                # 标记当前阶段为in_progress
                current_phase = status.get("current_phase", "plan")
                if current_phase in phases:
                    phases[current_phase] = "in_progress"

                message = PDCAStatusUpdateMessage(
                    session_id=session_id,
                    cycle_id=status["cycle_id"],
                    current_phase=current_phase,
                    phases=phases,
                    completion=status.get("completion_percentage", 0),
                    cycle_count=status.get("cycle_count", 1),
                )

                await self.send_message(session_id, message)
                logger.info(f"[PDCA] Sent PDCA_STATUS_UPDATE message: phase={current_phase}")

        except Exception as e:
            logger.error(f"[PDCA] Failed to send PDCA status update message: {e}", exc_info=True)

    async def _send_agent_start_message(
        self,
        session_id: str,
        task_id: str,
        agent: Agent,
        workspace_id: str,
        user_message: UserInputMessage,
    ) -> None:
        """发送 Agent 启动消息

        Args:
            session_id: 会话ID
            task_id: 任务ID
            agent: Agent 实例
            workspace_id: 工作区ID
            user_message: 用户消息

        Raises:
            IOError: 发送消息失败

        """
        try:
            agent_mode = getattr(
                agent.config,
                "mode",
                "orchestrator",
            )  # 获取 Agent 模式 (默认使用 Orchestrator)
            agent_start_message = AgentStartMessage(
                session_id=session_id,
                task_id=task_id,
                agent_mode=agent_mode,
                user_message=user_message.content[:200],  # 前200个字符作为摘要
                workspace_id=workspace_id,
                metadata={
                    "model": getattr(agent.config, "model", "unknown"),
                    "temperature": getattr(agent.config, "temperature", 0.7),
                },
            )
            await self.send_message(session_id, agent_start_message)
            logger.info(f"[CHAT_HANDLER] ✅ Sent AGENT_START message: mode={agent_mode}")
        except (OSError, ConnectionError, WebSocketError) as e:
            logger.error(f"[CHAT_HANDLER] Failed to send agent start message: {e}", exc_info=True)
            raise

    async def _handle_pdca_phase_completion(self, session_id: str, task_id: str):
        """处理PDCA阶段完成并发送阶段推进消息

        Args:
            session_id: 会话ID
            task_id: 任务ID

        """
        try:
            # 获取当前task对应的Agent实例
            agent = self._active_agents.get(task_id)
            if not agent:
                logger.info(
                    f"[PDCA] No agent found for task_id={task_id}, skipping PDCA phase update",
                )
                return

            # 检查Agent是否有PDCA扩展
            if not hasattr(agent, "_pdca_extension"):
                logger.info("[PDCA] Agent has no PDCA extension, skipping PDCA phase update")
                return

            pdca_extension = agent._pdca_extension

            # 检查PDCA是否启用
            if not pdca_extension.pdca_enabled:
                logger.info("[PDCA] PDCA not enabled for this task")
                return

            # 检查是否有活跃的PDCA循环
            if not pdca_extension.current_cycle:
                logger.info("[PDCA] No active PDCA cycle")
                return

            # 获取当前PDCA状态
            status = pdca_extension.get_pdca_status()
            if not status or not status.get("active"):
                logger.info("[PDCA] No active PDCA cycle status")
                return

            current_phase = status.get("current_phase")
            cycle_id = status.get("cycle_id")

            logger.info(f"[PDCA] Current phase: {current_phase}, cycle: {cycle_id}")

            # 根据当前阶段决定下一阶段
            from dawei.agentic.pdca_context import PDCAPhase

            phase_transitions = {
                PDCAPhase.PLAN.value: PDCAPhase.DO.value,
                PDCAPhase.DO.value: PDCAPhase.CHECK.value,
                PDCAPhase.CHECK.value: PDCAPhase.ACT.value,
            }

            next_phase = phase_transitions.get(current_phase)

            if next_phase:
                # 推进到下一阶段
                logger.info(f"[PDCA] Advancing from {current_phase} to {next_phase}")

                # 发送阶段推进消息
                await self._send_pdca_phase_advance_message(
                    session_id=session_id,
                    task_id=task_id,
                    cycle_id=cycle_id,
                    from_phase=current_phase,
                    to_phase=next_phase,
                    reason=f"完成{current_phase}阶段，准备进入{next_phase}阶段",
                )

                # 更新PDCA循环状态
                result_content = f"Completed {current_phase} phase"
                phase_result = pdca_extension.advance_pdca_phase(
                    phase_data={"result": result_content},
                    next_phase=next_phase,
                )

                logger.info(f"[PDCA] Phase advance result: {phase_result.get('status')}")

                # 发送更新后的状态
                await self._send_pdca_status_update_message(
                    session_id=session_id,
                    task_id=task_id,
                    pdca_extension=pdca_extension,
                )
            # ACT阶段完成，检查是否需要继续循环
            elif current_phase == PDCAPhase.ACT.value:
                logger.info("[PDCA] ACT phase completed, checking if cycle should continue")

                # 发送PDCA循环完成消息
                await self._send_pdca_cycle_complete_message(
                    session_id=session_id,
                    task_id=task_id,
                    cycle_id=cycle_id,
                    pdca_extension=pdca_extension,
                )

        except Exception as e:
            logger.error(f"[PDCA] Failed to handle PDCA phase completion: {e}", exc_info=True)

    async def _send_pdca_phase_advance_message(
        self,
        session_id: str,
        _task_id: str,
        cycle_id: str,
        from_phase: str,
        to_phase: str,
        reason: str,
    ):
        """发送PDCA阶段推进消息

        Args:
            session_id: 会话ID
            task_id: 任务ID
            cycle_id: PDCA循环ID
            from_phase: 当前阶段
            to_phase: 下一阶段
            reason: 推进原因

        """
        try:
            message = PDCAPhaseAdvanceMessage(
                session_id=session_id,
                cycle_id=cycle_id,
                from_phase=from_phase,
                to_phase=to_phase,
                reason=reason,
            )

            await self.send_message(session_id, message)
            logger.info(f"[PDCA] Sent PDCA_PHASE_ADVANCE: {from_phase} -> {to_phase}")

        except Exception as e:
            logger.error(f"[PDCA] Failed to send phase advance message: {e}", exc_info=True)

    async def _send_pdca_cycle_complete_message(
        self,
        session_id: str,
        _task_id: str,
        cycle_id: str,
        pdca_extension,
    ):
        """发送PDCA循环完成消息

        Args:
            session_id: 会话ID
            task_id: 任务ID
            cycle_id: PDCA循环ID
            pdca_extension: PDCA扩展实例

        """
        try:
            status = pdca_extension.get_pdca_status()

            message = PDACycleCompleteMessage(
                session_id=session_id,
                cycle_id=cycle_id,
                domain=pdca_extension.current_cycle.domain.value,
                total_cycles=status.get("cycle_count", 1),
                completion=status.get("completion_percentage", 0),
                result_summary=f"PDCA循环已完成，完成了{status.get('cycle_count', 1)}个循环",
                start_time=pdca_extension.current_cycle.start_time,
                end_time=datetime.now(UTC).isoformat(),
            )

            await self.send_message(session_id, message)
            logger.info(f"[PDCA] Sent PDCA_CYCLE_COMPLETE: {cycle_id}")

        except Exception as e:
            logger.error(f"[PDCA] Failed to send cycle complete message: {e}", exc_info=True)

    async def _configure_llm_provider(
        self,
        session_id: str,
        task_id: str,
        agent: Agent,
        user_workspace: UserWorkspace,
    ) -> None:
        """配置 LLM Provider

        Args:
            session_id: 会话ID
            task_id: 任务ID
            agent: Agent 实例
            user_workspace: 用户工作区

        """
        # 从 user_ui_context 获取用户选择的 LLM 并设置到 LLMProvider
        if not (user_workspace.workspace_info.user_ui_context and user_workspace.workspace_info.user_ui_context.current_llm_id):
            logger.info("[CHAT_HANDLER] No current_llm_id in user_ui_context, using default LLM")
            return

        current_llm_id = user_workspace.workspace_info.user_ui_context.current_llm_id

        # 获取 LLMProvider 并设置当前配置
        llm_provider = agent.execution_engine._llm_service
        if not hasattr(llm_provider, "set_current_config"):
            logger.warning(
                "[CHAT_HANDLER] ⚠️  LLMProvider does not have set_current_config method",
            )
            return

        # 先列出所有可用的配置
        available_configs = llm_provider.get_config_names() if hasattr(llm_provider, "get_config_names") else []
        logger.info(f"[CHAT_HANDLER] Available LLM configs: {available_configs}")

        try:
            success = llm_provider.set_current_config(current_llm_id)
            if not success:
                logger.warning(f"[CHAT_HANDLER] ⚠️  Failed to set LLM config to: {current_llm_id}")
                logger.warning(
                    f"[CHAT_HANDLER] ⚠️  Config not found. Available configs: {available_configs}",
                )

                # 发送错误消息给前端
                error_message = ErrorMessage(
                    session_id=session_id,
                    code="LLM_CONFIG_NOT_FOUND",
                    message=f"您选择的 LLM 配置 '{current_llm_id}' 不可用。系统将使用默认配置 '{available_configs[0] if available_configs else 'N/A'}' 继续执行。",
                    recoverable=False,
                    details={
                        "task_id": task_id,
                        "requested_config": current_llm_id,
                        "available_configs": available_configs,
                        "fallback_config": available_configs[0] if available_configs else None,
                    },
                )
                await self.send_message(session_id, error_message)
                logger.info("[CHAT_HANDLER] ✅ Sent LLM config error message to frontend")

                # 尝试使用默认配置
                if available_configs:
                    default_config = available_configs[0]
                    logger.info(f"[CHAT_HANDLER] Using default config: {default_config}")
                    llm_provider.set_current_config(default_config)
            else:
                pass  # No available configs, skip
        except (ConfigurationError, LLMError, ValueError) as e:
            logger.error(f"[CHAT_HANDLER] Error configuring LLM provider: {e}", exc_info=True)
            # LLM 配置失败不应阻止任务继续
            raise

    async def _process_file_references(
        self,
        user_message: UserInputMessage,
        workspace_path: str,
    ) -> UserInputMessage:
        """处理消息中的文件引用

        ⚠️ **重要变更**：不再自动读取文件内容
        - @file/path 引用保留在消息中
        - Agent内部的FileReferenceParser会解析@指令
        - Agent自行决定是否使用file read工具读取文件

        Args:
            user_message: 用户消息
            workspace_path: 工作区路径

        Returns:
            UserInputMessage: 原始用户消息（保留@引用）

        """
        original_message = user_message.content

        # 检查消息中是否包含@文件引用
        if "@" in original_message:
            from dawei.websocket.handlers.at_message_processor import AtMessageProcessor

            # 仅提取文件引用（不读取内容）
            file_refs = AtMessageProcessor.extract_file_references(original_message)

            if file_refs:
                logger.info(f"[CHAT_HANDLER] Detected {len(file_refs)} @ file references (will be processed by Agent)")

        # 返回原始消息，保留@指令供Agent处理
        return UserInputMessage(text=original_message)

    async def _handle_system_command_if_needed(
        self,
        session_id: str,
        task_id: str,
        user_workspace: UserWorkspace,
        _user_input: UserInputMessage,
        user_message: UserInputMessage,
    ) -> bool:
        """处理系统命令(如果需要)

        Args:
            session_id: 会话ID
            task_id: 任务ID
            user_workspace: 用户工作区
            user_input: 用户输入消息
            user_message: 原始用户消息

        Returns:
            bool: True 如果系统命令已处理(应跳过 Agent), False 否则

        """
        original_message = user_message.content
        original_message_stripped = original_message.strip()

        if not original_message_stripped.startswith("!"):
            return False

        logger.info("[CHAT_HANDLER] Detected ! command in user message")

        # 提取命令(去除!前缀)
        system_command = original_message_stripped[1:].strip()

        # 确保有当前对话
        if not user_workspace.current_conversation:
            from dawei.conversation.conversation import Conversation

            user_workspace.current_conversation = Conversation()
            logger.info("[CHAT_HANDLER] Created new conversation for system command")

        # 处理系统命令
        try:
            handled = await self._handle_system_command(
                command=system_command,
                session_id=session_id,
                task_id=task_id,
                user_workspace=user_workspace,
                user_message_content=original_message,
            )

            if handled:
                logger.info("[CHAT_HANDLER] System command handled, skipping agent creation")
                return True
            logger.warning(
                "[CHAT_HANDLER] System command handling failed, falling back to agent",
            )
            return False
        except Exception as e:
            logger.error(f"[CHAT_HANDLER] Error handling system command: {e}", exc_info=True)
            # 系统命令失败，fallback 到 agent
            return False

    async def _save_conversation_before_agent(
        self,
        user_workspace: UserWorkspace,
        _user_message: UserInputMessage,
    ) -> None:
        """在启动 Agent 前保存对话

        Args:
            user_workspace: 用户工作区
            user_message: 用户消息

        Raises:
            IOError: 保存对话失败

        """
        if not user_workspace.current_conversation:
            return

        # 注意：用户消息会在 TaskGraphExecutionEngine.run() 中的 _add_message_to_conversation() 方法里添加
        # 这里不需要重复添加，只需要在需要时保存对话即可
        # 参考: dawei/agentic/task_graph_excutor.py:524 调用 _add_message_to_conversation()

        # 立即保存对话（在启动 agent 之前）
        try:
            save_success = await user_workspace.save_current_conversation()
            if save_success:
                logger.info(
                    f"[CHAT_HANDLER] Successfully saved conversation {user_workspace.current_conversation.id} before starting agent",
                )
            else:
                logger.warning(
                    f"[CHAT_HANDLER] Failed to save conversation {user_workspace.current_conversation.id}",
                )
        except OSError as e:
            logger.error(f"[CHAT_HANDLER] Error saving conversation: {e}", exc_info=True)
            raise

    async def _execute_agent(self, agent: Agent, user_input: UserInputMessage) -> None:
        """执行 Agent

        Args:
            agent: Agent 实例
            user_input: 用户输入

        Raises:
            RuntimeError: Agent 执行失败

        """
        logger.info("[CHAT_HANDLER] About to call agent.process_message...")
        try:
            await agent.process_message(user_input)
            logger.info("[CHAT_HANDLER] agent.process_message returned!")
        except Exception as e:
            logger.error(f"[CHAT_HANDLER] Error executing agent: {e}", exc_info=True)
            raise

    async def _handle_agent_error(
        self,
        error: Exception,
        session_id: str,
        task_id: str,
        _user_workspace: UserWorkspace | None = None,
        agent: Agent | None = None,
    ) -> None:
        """处理 Agent 错误

        Args:
            error: 异常对象
            session_id: 会话ID
            task_id: 任务ID
            user_workspace: 用户工作区(可选)
            agent: Agent 实例(可选)

        """
        logger.error(f"执行 Agent 任务时出错: {error}", exc_info=True)

        # 提取更有用的错误信息
        error_str = str(error)
        user_friendly_message = error_str
        error_code = "AGENT_EXECUTION_ERROR"

        # 如果是StateTransitionError,需要从traceback中提取原始错误
        if "StateTransitionError" in error_str:
            logger.info(
                "[CHAT_HANDLER] Detected StateTransitionError, checking traceback for original error...",
            )
            user_friendly_message = self._extract_llm_error_message(error_str, error)

        # 如果是直接的LLM API错误
        elif "HTTP 429" in error_str or "insufficient balance" in error_str:
            user_friendly_message = "LLM API 账户余额不足或调用次数超限。请检查 API 配置和账户余额,或联系管理员充值。"
        elif "HTTP 500" in error_str:
            user_friendly_message = "LLM 服务暂时不可用(HTTP 500),请稍后重试。"
        elif "LLM error" in error_str:
            user_friendly_message = f"LLM 调用失败: {error_str}"

        # 获取 workspace_id for proper routing
        workspace_id = None
        try:
            if agent and hasattr(agent, "user_workspace") and hasattr(agent.user_workspace, "workspace_info"):
                workspace_id = agent.user_workspace.workspace_info.id
        except Exception as ws_id_error:
            logger.warning(f"[CHAT_HANDLER] Failed to get workspace_id for error: {ws_id_error}")

        # 发送错误消息到前端
        error_message = ErrorMessage(
            session_id=session_id,
            code=error_code,
            message=user_friendly_message,
            recoverable=False,
            details={
                "task_id": task_id,
                "original_error": error_str,
                "error_type": type(error).__name__,
            },
        )
        await self.send_message(session_id, error_message)
        logger.info(
            f"[CHAT_HANDLER] ✅ Sent {error_code} message to frontend: {user_friendly_message}",
        )

        # 发送一个 stream_complete 消息来明确终止任务流,确保前端不会卡在"正在处理"状态
        from dawei.websocket.protocol import StreamCompleteMessage

        complete_message = StreamCompleteMessage(
            session_id=session_id,
            task_id=task_id,
            content="",  # 空内容,因为错误消息已经发送了
            reasoning_content=None,
            tool_calls=[],  # 空列表而不是 None
            usage=None,
            finish_reason="error",
        )
        await self.send_message(session_id, complete_message)
        logger.info(
            "[CHAT_HANDLER] ✅ Sent STREAM_COMPLETE message after error to terminate task flow",
        )

    def _extract_llm_error_message(self, _error_str: str, error: Exception) -> str:
        """从 StateTransitionError 中提取 LLM 错误消息

        Args:
            error_str: 错误字符串
            error: 异常对象

        Returns:
            str: 用户友好的错误消息

        """
        import re
        import traceback

        # 检查是否有原始错误信息
        tb_str = "".join(traceback.format_exception(type(error), error, error.__traceback__))

        # 查找traceback中的原始错误
        if "HTTP 429" in tb_str or "insufficient balance" in tb_str:
            logger.info("[CHAT_HANDLER] Extracted original error: LLM 429 insufficient balance")
            return "LLM API 账户余额不足或调用次数超限。请检查 API 配置和账户余额,或联系管理员充值。"
        if "HTTP 500" in tb_str:
            logger.info("[CHAT_HANDLER] Extracted original error: LLM HTTP 500")
            return "LLM 服务暂时不可用(HTTP 500),请稍后重试。"
        if "LLM error" in tb_str or "LLMError" in tb_str:
            # 尝试提取LLM错误消息
            llm_error_match = re.search(r"LLM error from \w+: (.+)", tb_str)
            if llm_error_match:
                original_llm_error = llm_error_match.group(1)
                logger.info(f"[CHAT_HANDLER] Extracted original LLM error: {original_llm_error}")
                return f"LLM 调用失败: {original_llm_error}"
            logger.info("[CHAT_HANDLER] Found LLM error but could not extract details")
            return "LLM 调用失败,请检查API配置。"
        logger.warning(
            "[CHAT_HANDLER] StateTransitionError but could not extract original error",
        )
        return "任务执行过程中出现错误。请查看上方显示的错误详情。"

    async def _cleanup_agent_task(
        self,
        session_id: str,
        task_id: str,
        user_workspace: UserWorkspace | None = None,
        agent: Agent | None = None,
    ) -> None:
        """清理 Agent 任务资源

        Args:
            session_id: 会话ID
            task_id: 任务ID
            user_workspace: 用户工作区(可选)
            agent: Agent 实例(可选)

        """
        # Agent 执行完成后（无论成功或失败），保存包含所有消息的对话
        logger.info(
            f"[CHAT_HANDLER] Finally block executed. user_workspace: {user_workspace is not None}",
        )
        if user_workspace:
            logger.info(
                f"[CHAT_HANDLER] user_workspace.current_conversation: {user_workspace.current_conversation is not None}",
            )
            if user_workspace.current_conversation:
                logger.info(
                    f"[CHAT_HANDLER] Conversation ID: {user_workspace.current_conversation.id}, Message count: {user_workspace.current_conversation.message_count}",
                )

        if user_workspace and user_workspace.current_conversation:
            logger.info(
                f"[CHAT_HANDLER] Saving conversation in finally block. Message count: {user_workspace.current_conversation.message_count}",
            )
            try:
                save_success = await user_workspace.save_current_conversation()
                if save_success:
                    logger.debug(
                        f"[CHAT_HANDLER] Successfully saved conversation {user_workspace.current_conversation.id} in finally block",
                    )
                else:
                    logger.warning(
                        f"[CHAT_HANDLER] Failed to save conversation {user_workspace.current_conversation.id} in finally block",
                    )
            except Exception as save_error:
                logger.error(
                    f"[CHAT_HANDLER] Error saving conversation in finally block: {save_error}",
                    exc_info=True,
                )
        else:
            logger.warning(
                f"[CHAT_HANDLER] Cannot save conversation: user_workspace={user_workspace is not None}, current_conversation={user_workspace.current_conversation if user_workspace else 'N/A'}",
            )

        await self.update_session_data(session_id, data={"current_task_id": None})

        # 🔴 关键修复：清理 Agent 实例
        if task_id in self._active_agents:
            del self._active_agents[task_id]

        logger.info(
            f"[CHAT_HANDLER] Skipping agent.cleanup() to avoid disrupting active handlers. "
            f"Agent {task_id} will be garbage collected naturally."
        )

        # 🔧 修复：清理事件处理器，防止内存泄漏和重复处理
        await self._cleanup_event_handlers(task_id, agent)

    async def _cleanup_event_handlers(self, task_id: str, agent: Agent | None = None) -> None:
        """清理事件处理器，防止内存泄漏和重复处理

        Args:
            task_id: 任务ID
            agent: Agent实例（可选，如果不提供则尝试从_active_agents获取）

        """
        # 🔴 关键修复：弹出完整的任务信息
        task_info = self._task_event_handler_ids.pop(task_id, None)

        if not task_info:
            return

        # 提取 handler_ids 和 event_bus
        handler_ids = task_info.get('handler_ids', {})
        saved_event_bus_id = task_info.get('event_bus_id')
        saved_event_bus = task_info.get('event_bus')

        logger.info(
            f"[EVENT_HANDLER] 🧹 Cleaning up {len(handler_ids)} event handlers for task {task_id}",
        )

        # 获取事件总线
        event_bus = saved_event_bus

        # 验证：如果保存的 event_bus 和当前 agent 的 event_bus 不同，记录警告
        if agent and hasattr(agent, 'event_bus'):
            current_event_bus_id = id(agent.event_bus)
            if current_event_bus_id != saved_event_bus_id:
                logger.error(
                    f"[EVENT_HANDLER] ❌ CRITICAL: Event bus mismatch!\n"
                    f"  - Saved event_bus_id: {saved_event_bus_id}\n"
                    f"  - Current agent event_bus_id: {current_event_bus_id}\n"
                    f"  - This means the agent was recreated or replaced!\n"
                    f"  - Using saved event_bus reference for cleanup.",
                )

        if not event_bus:
            logger.warning(
                f"[EVENT_HANDLER] ⚠️ Cannot cleanup handlers for task {task_id}: no event bus available. Handlers will remain registered (potential memory leak).",
            )
            # handler_ids 已经被 pop，无需再次删除
            return

        # 移除所有事件处理器
        removed_count = 0
        already_removed_count = 0

        for event_type_value, handler_id in handler_ids.items():
            try:
                # 将字符串转换为TaskEventType枚举
                event_type = TaskEventType(event_type_value)

                success = event_bus.remove_handler(event_type, handler_id)

                if success:
                    removed_count += 1
                else:
                    already_removed_count += 1
            except ValueError:
                logger.debug(
                    f"[EVENT_HANDLER] ⚠️ Invalid event type {event_type_value}, skipping cleanup",
                )
            except Exception as e:
                logger.error(
                    f"[EVENT_HANDLER] ❌ Error removing handler for {event_type_value}: {e}",
                    exc_info=True,
                )

        logger.info(
            f"[EVENT_HANDLER] ✅ Cleanup complete for task {task_id}: "
            f"removed {removed_count}, already removed {already_removed_count}/{len(handler_ids)} handlers. "
            f"Remaining active handlers: {len(self._task_event_handler_ids)}",
        )

    # ==================== 重构后的主执行方法 ====================

    async def _execute_agent_task(
        self,
        parameters: Dict[str, Any],
        _context: Any = None,
    ) -> None:
        """执行Agent任务（适配AsyncTaskManager的执行器接口）

        Args:
            parameters: 任务参数，包含session_id, task_id, user_message
            context: 任务上下文

        Returns:
            执行结果

        """
        session_id = parameters["session_id"]
        task_id = parameters["task_id"]
        user_message = parameters["user_message"]
        """
        完整地创建、配置并执行一个 Agent 任务。
        """
        # 初始化变量
        user_workspace = None
        agent = None

        try:
            # 1. 获取和验证工作区
            (
                workspace_id,
                workspace_path,
                user_workspace,
            ) = await self._get_and_validate_workspace(
                user_message,
            )

            # 2. 更新用户UI上下文
            await self._update_user_ui_context(user_workspace, user_message)

            # 3. 加载或创建会话
            await self._load_or_create_conversation(user_workspace, user_message)

            # 🔥 3.5. 立即发送 conversation_id 给前端
            if user_workspace.current_conversation:
                from dawei.websocket.protocol import ConversationInfoMessage
                # 🔧 FIX: Convert datetime to ISO format string
                created_at_str = None
                if user_workspace.current_conversation.created_at:
                    if isinstance(user_workspace.current_conversation.created_at, str):
                        created_at_str = user_workspace.current_conversation.created_at
                    else:
                        created_at_str = user_workspace.current_conversation.created_at.isoformat()

                conv_info_msg = ConversationInfoMessage(
                    session_id=session_id,
                    conversation_id=user_workspace.current_conversation.id,
                    title=user_workspace.current_conversation.title,
                    created_at=created_at_str,
                )
                await self.send_message(session_id, conv_info_msg)
                logger.info(f"[CHAT_HANDLER] ✅ Sent CONVERSATION_INFO message: conversation_id={user_workspace.current_conversation.id}")

            # 4. 创建和初始化 Agent
            agent = await self._create_and_initialize_agent(user_workspace)

            # 4.5. 集成 PDCA 扩展（如果需要）
            pdca_extension = await self._integrate_pdca_if_needed(
                agent,
                session_id,
                task_id,
                user_workspace,
                user_message,
            )

            # 5. 配置 Agent 模式
            await self._configure_agent_mode(agent, user_workspace, pdca_extension)

            # 6. 发送 Agent 启动消息
            await self._send_agent_start_message(
                session_id,
                task_id,
                agent,
                workspace_id,
                user_message,
            )

            # 7. 配置 LLM Provider
            await self._configure_llm_provider(session_id, task_id, agent, user_workspace)

            # 8. 存储 Agent 实例
            self._active_agents[task_id] = agent

            # 9. 设置事件转发
            await self._setup_event_forwarding(agent, session_id, task_id, user_workspace)

            # 10. 启动任务
            await self.update_session_data(session_id, data={"current_task_id": task_id})

            # 11. 处理文件引用
            user_input = await self._process_file_references(user_message, workspace_path)

            # 12. 处理系统命令(如果需要)
            should_skip_agent = await self._handle_system_command_if_needed(
                session_id,
                task_id,
                user_workspace,
                user_input,
                user_message,
            )

            if should_skip_agent:
                return

            # 13. 保存对话(在启动 Agent 前)
            await self._save_conversation_before_agent(user_workspace, user_message)

            # 14. 执行 Agent
            await self._execute_agent(agent, user_input)

        except Exception as e:
            # 统一的错误处理
            await self._handle_agent_error(e, session_id, task_id, user_workspace, agent)
        finally:
            # 清理资源
            await self._cleanup_agent_task(session_id, task_id, user_workspace, agent)

    async def _setup_event_forwarding(self, agent: Agent, session_id: str, task_id: str, user_workspace: UserWorkspace):
        """为 Agent 设置事件监听器，将任务事件转发到 WebSocket 客户端。

        Args:
            agent: Agent 实例
            session_id: WebSocket 会话ID
            task_id: 任务ID
            user_workspace: 用户工作区（用于获取 conversation_id）
        """
        # LLM API 状态追踪
        llm_api_active = False
        current_llm_provider = None
        current_llm_model = None
        llm_request_start_time = None

        async def event_handler(event: "TaskEvent"):
            """事件处理器函数 - 只处理强类型 TaskEvent 对象"""
            nonlocal llm_api_active, current_llm_provider, current_llm_model, llm_request_start_time

            # 初始化 workspace_id，确保在所有代码路径中都已定义
            workspace_id: str | None = None

            # 直接访问强类型 TaskEvent 对象的属性
            event_type = event.event_type
            event_data = event.data  # 直接使用强类型事件数据

            # 【关键调试日志】记录所有接收到的事件
            if event_type == TaskEventType.ERROR_OCCURRED:
                logger.info(
                    f"[ERROR_TRACE] Chat handler received ERROR_OCCURRED event: event_id={event.event_id}, task_id={task_id}, data={event_data}",
                )

            user_message_id = local_context.get_message_id()

            # 获取事件类型枚举，如果 event_type 是字符串则转换为枚举
            if isinstance(event_type, str):
                try:
                    event_type_enum = TaskEventType(event_type)
                except ValueError:
                    logger.error(f"未知的事件类型: {event_type}", exc_info=True)
                    return
            else:
                event_type_enum = event_type

            # 添加详细日志，特别是对于 TOOL_CALL_RESULT 事件
            if event_type_enum == TaskEventType.TOOL_CALL_RESULT:
                logger.info(
                    f"[CHAT_HANDLER] 🎯 Received TOOL_CALL_RESULT event: event_id={event.event_id}, task_id={task_id}",
                )

            message_to_send = None
            llm_api_message = None  # 用于 LLM API 状态消息

            try:
                # 处理任务完成事件
                if event_type_enum == TaskEventType.TASK_COMPLETED:
                    result_content = event_data.result if hasattr(event_data, "result") and event_data.result else "任务已完成。"

                    logger.debug(
                        f"[CHAT_HANDLER] 📦 任务完成: task_id={task_id}, 发送 AGENT_COMPLETE 消息",
                    )

                    # 🔧 PDCA: 检查是否有PDCA扩展，并发送阶段推进消息
                    await self._handle_pdca_phase_completion(session_id, task_id)

                    # 发送 AGENT_COMPLETE 消息（用于状态栏显示）
                    import time

                    # 使用默认60秒作为任务执行时间
                    total_duration_ms = 60000  # 默认60秒

                    # 获取当前会话ID（如果存在）
                    conversation_id = None
                    if user_workspace and user_workspace.current_conversation:
                        conversation_id = user_workspace.current_conversation.id
                        logger.debug(f"[CHAT_HANDLER] Including conversation_id in AGENT_COMPLETE: {conversation_id}")

                    agent_complete_message = AgentCompleteMessage(
                        session_id=session_id,
                        task_id=task_id,
                        result_summary=result_content[:200] if result_content else "任务已完成",
                        total_duration_ms=total_duration_ms,
                        tasks_completed=1,  # 可以从实际统计数据中获取
                        tools_used=[],  # 可以从实际统计数据中获取
                        conversation_id=conversation_id,
                        metadata={},
                    )
                    await self.send_message(session_id, agent_complete_message)

                    # 发送任务完成信令
                    message_to_send = TaskNodeCompleteMessage(
                        session_id=session_id,
                        task_id=task_id,
                        task_node_id=task_id,
                        result={"response": result_content},
                        duration_ms=0,
                    )
                # 处理任务错误事件
                elif event_type_enum == TaskEventType.TASK_ERROR:
                    message_to_send = ErrorMessage(
                        session_id=session_id,
                        code=(event_data.error_code if hasattr(event_data, "error_code") else "TASK_ERROR"),
                        message=(event_data.error_message if hasattr(event_data, "error_message") else "未知错误"),
                        recoverable=(event_data.recoverable if hasattr(event_data, "recoverable") else False),
                        details={"task_id": task_id},
                    )
                # 处理错误发生事件
                elif event_type_enum == TaskEventType.ERROR_OCCURRED:
                    # event_data 是字典格式：{"error_type": ..., "message": ..., "details": {...}}
                    error_type = event_data.get("error_type", "unknown") if isinstance(event_data, dict) else "unknown"
                    error_message = event_data.get("message", "未知错误") if isinstance(event_data, dict) else "未知错误"
                    error_details = event_data.get("details", {}) if isinstance(event_data, dict) else {}

                    logger.info(
                        f"[ERROR_TRACE] Creating ErrorMessage: error_type={error_type}, error_message={error_message[:100]}..., session_id={session_id}",
                    )

                    message_to_send = ErrorMessage(
                        session_id=session_id,
                        code=error_type.upper(),
                        message=error_message,
                        recoverable=False,
                        details={"task_id": task_id, **error_details},
                    )

                    logger.info(
                        f"[ERROR_TRACE] ErrorMessage created successfully: message_to_send={message_to_send is not None}",
                    )
                # 处理使用统计接收事件
                elif event_type_enum == TaskEventType.USAGE_RECEIVED:
                    # event_data 是 UsageMessage 对象，使用 from_stream_message 方法
                    message_to_send = StreamUsageMessage.from_stream_message(
                        event_data,
                        session_id=session_id,
                        task_id=task_id,
                    )
                    message_to_send.user_message_id = user_message_id

                    # 同时发送 LLM API 完成消息
                    if llm_api_active:
                        import time

                        duration_ms = int((time.time() - llm_request_start_time) * 1000) if llm_request_start_time else None
                        llm_api_message = LLMApiCompleteMessage(
                            session_id=session_id,
                            task_id=task_id,
                            provider=current_llm_provider or "unknown",
                            model=current_llm_model or "unknown",
                            usage=event_data.data if hasattr(event_data, "data") else None,
                            duration_ms=duration_ms,
                        )
                        llm_api_active = False

                        # 🔧 修复：清理 LLM API 状态
                        self._task_llm_api_state.pop(task_id, None)
                # 处理完成接收事件
                elif event_type_enum == TaskEventType.COMPLETE_RECEIVED:
                    # event_data 是 CompleteMessage 对象，使用 from_stream_message 方法
                    # 获取当前会话ID
                    conv_id = None
                    if user_workspace and user_workspace.current_conversation:
                        conv_id = user_workspace.current_conversation.id

                    message_to_send = StreamCompleteMessage.from_stream_message(
                        event_data,
                        session_id=session_id,
                        task_id=task_id,
                        conversation_id=conv_id,
                    )
                    message_to_send.user_message_id = user_message_id

                    # 如果 LLM API 还在活跃状态，发送完成消息
                    if llm_api_active:
                        import time

                        duration_ms = int((time.time() - llm_request_start_time) * 1000) if llm_request_start_time else None
                        llm_api_message = LLMApiCompleteMessage(
                            session_id=session_id,
                            task_id=task_id,
                            provider=current_llm_provider or "unknown",
                            model=current_llm_model or "unknown",
                            finish_reason=(event_data.finish_reason if hasattr(event_data, "finish_reason") else None),
                            usage=event_data.usage if hasattr(event_data, "usage") else None,
                            duration_ms=duration_ms,
                        )
                        llm_api_active = False

                        # 🔧 修复：清理 LLM API 状态
                        self._task_llm_api_state.pop(task_id, None)
                # 处理内容流事件
                elif event_type_enum == TaskEventType.CONTENT_STREAM:
                    # 如果是第一个内容块，发送 LLM API 请求开始消息
                    if not llm_api_active:
                        llm_api_active = True
                        llm_request_start_time = event.timestamp

                        # 🔧 修复：记录 LLM API 状态，用于停止时清理
                        self._task_llm_api_state[task_id] = {
                            "active": True,
                            "start_time": event.timestamp,
                            "provider": "unknown",
                            "model": "unknown",
                        }

                        # 从 agent 获取 LLM 提供商信息和 workspace_id
                        current_llm_provider = "unknown"
                        current_llm_model = "unknown"
                        # 更新 workspace_id（如果可能）
                        try:
                            if hasattr(agent, "user_workspace") and hasattr(
                                agent.user_workspace,
                                "workspace_info",
                            ):
                                workspace_id = agent.user_workspace.workspace_info.id
                            else:
                                logger.warning(
                                    "[CHAT_HANDLER] Agent or workspace_info not available for workspace_id",
                                )
                        except Exception as e:
                            logger.warning(f"[CHAT_HANDLER] Failed to get workspace_id: {e}")
                            workspace_id = None

                        try:
                            if hasattr(agent, "execution_engine") and hasattr(
                                agent.execution_engine,
                                "_llm_service",
                            ):
                                llm_service = agent.execution_engine._llm_service

                                # 获取当前配置
                                current_config = llm_service.get_current_config()
                                logger.info(
                                    f"[CHAT_HANDLER] Current LLM config: {current_config.name if current_config else 'None'}",
                                )

                                if current_config and hasattr(current_config, "config"):
                                    config = current_config.config
                                    provider = getattr(config, "apiProvider", None) or getattr(
                                        config,
                                        "provider",
                                        "unknown",
                                    )
                                    model = getattr(config, "model_id", None) or getattr(config, "openAiModelId", None) or "unknown"

                                    current_llm_provider = provider
                                    current_llm_model = model
                                    logger.info(
                                        f"[CHAT_HANDLER] Extracted LLM info: provider={provider}, model={model}",
                                    )

                                    # 🔧 修复：更新 LLM API 状态
                                    if task_id in self._task_llm_api_state:
                                        self._task_llm_api_state[task_id]["provider"] = provider
                                        self._task_llm_api_state[task_id]["model"] = model
                                else:
                                    logger.warning(
                                        f"[CHAT_HANDLER] Current config has no 'config' attribute: {current_config}",
                                    )
                            else:
                                logger.warning(
                                    "[CHAT_HANDLER] Agent or execution_engine not available",
                                )
                        except Exception as e:
                            logger.error(
                                f"[CHAT_HANDLER] Error extracting LLM config info: {e}",
                                exc_info=True,
                            )

                        llm_api_message = LLMApiRequestMessage(
                            session_id=session_id,
                            task_id=task_id,
                            provider=current_llm_provider,
                            model=current_llm_model,
                            request_type="chat",
                        )
                        await self.send_message(session_id, llm_api_message)

                    # 从 event_data 字典构建消息
                    websocket_msg = StreamContentMessage.from_event_data(
                        event_data,
                        session_id=session_id,
                        task_id=task_id,
                    )
                    await self.send_message(session_id, websocket_msg)
                # 处理推理事件
                elif event_type_enum == TaskEventType.REASONING:
                    # 发送 STREAM_REASONING 消息（用于前端显示推理过程）
                    # 确保字段名匹配：task_node_executor.py 发送的是 'content' 字段
                    assistant = {
                        "content": event_data.get("content", ""),
                        "message_id": event_data.get("message_id"),
                    }
                    stream_reasoning_message = StreamReasoningMessage.from_event_data(
                        assistant,
                        session_id=session_id,
                        task_id=task_id,
                    )
                    await self.send_message(session_id, stream_reasoning_message)
                # 处理工具调用检测事件
                elif event_type_enum == TaskEventType.TOOL_CALLS_DETECTED:
                    # event_data is ToolCallMessage with tool_call and all_tool_calls attributes
                    tool_calls = event_data.all_tool_calls if hasattr(event_data, "all_tool_calls") else []
                    if tool_calls:
                        # 发送工具调用流式消息
                        for tool_call in tool_calls:
                            if hasattr(tool_call, "function"):
                                message_to_send = StreamToolCallMessage(
                                    session_id=session_id,
                                    task_id=task_id,
                                    tool_call=tool_call,
                                    all_tool_calls=tool_calls,
                                    user_message_id=user_message_id,
                                )
                                await self.send_message(session_id, message_to_send)
                # 处理工具调用开始事件
                elif event_type_enum == TaskEventType.TOOL_CALL_START:
                    message_to_send = ToolCallStartMessage(
                        session_id=session_id,
                        task_id=task_id,
                        tool_name=event_data.tool_name if hasattr(event_data, "tool_name") else "",
                        tool_input=(event_data.tool_input if hasattr(event_data, "tool_input") else {}),
                        tool_call_id=getattr(event_data, "tool_call_id", None),
                    )
                # 处理工具调用进度事件
                elif event_type_enum == TaskEventType.TOOL_CALL_PROGRESS:
                    # 获取状态信息
                    getattr(event_data, "status", None)
                    message = getattr(event_data, "message", "")
                    progress_percentage = getattr(event_data, "progress_percentage", None)
                    current_step = getattr(event_data, "current_step", None)
                    total_steps = getattr(event_data, "total_steps", None)
                    current_step_index = getattr(event_data, "current_step_index", None)

                    # 构建详细的消息内容
                    if current_step and total_steps:
                        message = f"{message} ({current_step_index + 1}/{total_steps}: {current_step})" if current_step_index is not None else f"{message} ({current_step})"

                    message_to_send = ToolCallProgressMessage(
                        session_id=session_id,
                        task_id=task_id,
                        tool_name=event_data.tool_name if hasattr(event_data, "tool_name") else "",
                        message=message,
                        progress_percentage=progress_percentage,
                        tool_call_id=getattr(event_data, "tool_call_id", None),
                    )
                # 处理工具调用结果事件
                elif event_type_enum == TaskEventType.TOOL_CALL_RESULT:
                    logger.info("[CHAT_HANDLER] 🔧 Processing TOOL_CALL_RESULT event")

                    # event_data 是一个字典，使用字典访问而不是 getattr
                    result = event_data.get("result", "") if isinstance(event_data, dict) else getattr(event_data, "result", "")
                    is_error = event_data.get("is_error", False) if isinstance(event_data, dict) else getattr(event_data, "is_error", False)
                    error_message = event_data.get("error_message") if isinstance(event_data, dict) else getattr(event_data, "error_message", None)
                    execution_time = event_data.get("execution_time") if isinstance(event_data, dict) else getattr(event_data, "execution_time", None)
                    tool_name = event_data.get("tool_name", "") if isinstance(event_data, dict) else (getattr(event_data, "tool_name", "") if hasattr(event_data, "tool_name") else "")
                    tool_call_id = event_data.get("tool_call_id") if isinstance(event_data, dict) else getattr(event_data, "tool_call_id", None)

                    # 如果是错误，使用错误消息作为结果
                    if is_error and error_message:
                        result = error_message

                    # 如果有执行时间，添加到结果中
                    if execution_time is not None and not is_error:
                        if isinstance(result, dict):
                            result["_execution_time"] = f"{execution_time:.2f}s"
                        else:
                            result = f"{result}\n\n执行时间: {execution_time:.2f}s"

                    logger.info(
                        f"[CHAT_HANDLER] 🔧 Creating ToolCallResultMessage: tool_name={tool_name}, tool_call_id={tool_call_id}",
                    )

                    message_to_send = ToolCallResultMessage(
                        session_id=session_id,
                        task_id=task_id,
                        tool_name=tool_name,
                        result=result,
                        is_error=is_error,
                        tool_call_id=tool_call_id,
                        workspace_id=workspace_id,
                    )

                    logger.info("[CHAT_HANDLER] 🔧 ToolCallResultMessage created successfully")
                # 处理检查点创建事件
                elif event_type_enum == TaskEventType.CHECKPOINT_CREATED:
                    message_to_send = TaskNodeProgressMessage(
                        session_id=session_id,
                        task_id=task_id,
                        task_node_id=task_id,
                        progress=50,
                        status="executing",
                        message=f"检查点已创建: {event_data.checkpoint_id if hasattr(event_data, 'checkpoint_id') else ''}",
                        data={
                            "checkpoint_id": (event_data.checkpoint_id if hasattr(event_data, "checkpoint_id") else ""),
                            "checkpoint_path": (event_data.checkpoint_path if hasattr(event_data, "checkpoint_path") else ""),
                            "checkpoint_size": (event_data.checkpoint_size if hasattr(event_data, "checkpoint_size") else 0),
                        },
                    )
                # 处理状态变更事件
                elif event_type_enum == TaskEventType.STATE_CHANGED:
                    message_to_send = TaskNodeProgressMessage(
                        session_id=session_id,
                        task_id=task_id,
                        task_node_id=task_id,
                        progress=20,
                        status="state_change",
                        message=f"任务状态变更为: {event_data.new_state if hasattr(event_data, 'new_state') else ''}",
                        data=(event_data.get_event_data() if hasattr(event_data, "get_event_data") else {}),
                    )
                # 处理追问问题事件
                elif event_type_enum == TaskEventType.FOLLOWUP_QUESTION:
                    from dawei.websocket.protocol import FollowupQuestionMessage

                    # event_data 是字典，使用 .get() 访问
                    event_session_id = event_data.get("session_id", session_id)

                    message_to_send = FollowupQuestionMessage(
                        session_id=event_session_id,  # 使用事件数据中的 session_id
                        task_id=task_id,
                        question=event_data.get("question", ""),
                        suggestions=event_data.get("suggestions", []),
                        tool_call_id=event_data.get("tool_call_id", ""),
                        user_message_id=user_message_id,
                    )

                    logger.info(
                        f"Forwarding FOLLOWUP_QUESTION to session: {event_session_id}, question: {event_data.get('question', 'N/A')[:50]}...",
                    )
                # 处理A2UI UI组件事件
                elif event_type_enum == TaskEventType.A2UI_SURFACE_EVENT:
                    from dawei.websocket.protocol import A2UIServerEventMessage

                    # event_data 是字典，使用 .get() 访问
                    a2ui_message = event_data.get("a2ui_message", {})
                    surface_id = event_data.get("surface_id", "")

                    # 构建A2UI服务器事件消息
                    message_to_send = A2UIServerEventMessage(
                        messages=a2ui_message.get("messages", []),
                        metadata=a2ui_message.get("metadata", {}),
                        session_id=session_id,
                        user_message_id=user_message_id,
                    )

                    logger.info(
                        f"[A2UI] Forwarding A2UI surface to session: {session_id}, surface_id: {surface_id}",
                    )

                if message_to_send:
                    message_to_send.user_message_id = user_message_id

                    # 特别记录 ERROR_OCCURRED 和 TOOL_CALL_RESULT 消息发送
                    if event_type_enum == TaskEventType.ERROR_OCCURRED:
                        logger.info(
                            f"[ERROR_TRACE] About to send ErrorMessage to session: {session_id}, type={message_to_send.type}, code={message_to_send.code}",
                        )
                    elif event_type_enum == TaskEventType.TOOL_CALL_RESULT:
                        logger.info(
                            f"[CHAT_HANDLER] 📤 About to send ToolCallResultMessage to session: {session_id}",
                        )
                        logger.info(
                            f"[CHAT_HANDLER] 📤 Message type: {message_to_send.type}, tool_call_id: {message_to_send.tool_call_id}",
                        )

                    try:
                        await self.send_message(session_id, message_to_send)

                        if event_type_enum == TaskEventType.ERROR_OCCURRED:
                            logger.info(
                                f"[ERROR_TRACE] ErrorMessage sent successfully to session: {session_id}",
                            )
                        elif event_type_enum == TaskEventType.TOOL_CALL_RESULT:
                            logger.info(
                                "[CHAT_HANDLER] ✅ ToolCallResultMessage sent successfully",
                            )
                    except Exception as e:
                        # 如果发送消息失败，记录日志但不中断事件处理
                        self.logger.warning(
                            f"Failed to send message for event {event_type_enum}: {e}",
                            exc_info=True,
                            context={
                                "session_id": session_id,
                                "task_id": task_id,
                                "component": "chat_handler",
                            },
                        )

                # 发送 LLM API 状态消息（如果存在）
                if llm_api_message:
                    try:
                        await self.send_message(session_id, llm_api_message)
                    except Exception as e:
                        self.logger.warning(
                            f"Failed to send LLM API message: {e}",
                            exc_info=True,
                            context={
                                "session_id": session_id,
                                "task_id": task_id,
                                "component": "chat_handler",
                            },
                        )

            except Exception as e:
                logger.error(f"处理任务事件 {event_type_enum} 时出错: {e}", exc_info=True)

        # 订阅所有事件
        event_types_to_forward = [
            TaskEventType.TASK_COMPLETED,
            TaskEventType.TASK_ERROR,
            TaskEventType.ERROR_OCCURRED,
            TaskEventType.USAGE_RECEIVED,
            TaskEventType.COMPLETE_RECEIVED,
            TaskEventType.CONTENT_STREAM,
            TaskEventType.REASONING,
            TaskEventType.TOOL_CALLS_DETECTED,
            TaskEventType.TOOL_CALL_START,
            TaskEventType.TOOL_CALL_PROGRESS,
            TaskEventType.TOOL_CALL_RESULT,
            TaskEventType.CHECKPOINT_CREATED,
            TaskEventType.STATE_CHANGED,
            TaskEventType.FOLLOWUP_QUESTION,  # 添加追问问题事件
            TaskEventType.A2UI_SURFACE_EVENT,  # 添加A2UI UI组件事件
        ]

        # 获取 Agent 的事件总线
        event_bus = agent.event_bus

        # 🔧 修复：检查是否已经注册过事件处理器
        if task_id in self._task_event_handler_ids:
            logger.warning(
                f"[EVENT_HANDLER] Task {task_id} already has registered event handlers, skipping duplicate registration. This prevents the duplicate message bug.",
            )
            return

        # 🔧 简化：由于每个UserWorkspace现在使用独立的event_bus，
        # 不再需要强制清理其他任务的handler
        # 旧任务会随着UserWorkspace的释放而自动清理

        # 🔧 修复：保存事件处理器ID映射，用于清理
        handler_ids = {}

        for event_type in event_types_to_forward:
            try:
                handler_id = event_bus.add_handler(event_type, event_handler)
                handler_ids[event_type.value] = handler_id
            except Exception as e:
                logger.error(f"订阅事件 {event_type} 时出错: {e}", exc_info=True)

        # 🔴 关键修复：保存完整的任务信息（handler_ids + event_bus 引用）
        self._task_event_handler_ids[task_id] = {
            'handler_ids': handler_ids,
            'event_bus_id': id(event_bus),
            'event_bus': event_bus,  # 保存引用，确保清理时使用同一个 event_bus
        }

        logger.info(
            f"[EVENT_HANDLER] ✅ Successfully registered {len(handler_ids)} event handlers for task {task_id}. Total active handlers: {len(self._task_event_handler_ids)}",
        )

    async def _on_task_progress(self, task_progress):
        """任务进度回调"""
        try:
            # 从映射中获取 session_id
            session_id = self._task_to_session_map.get(task_progress.task_id)
            if not session_id:
                logger.warning(f"未找到任务 {task_progress.task_id} 对应的会话ID")
                return

            # 发送进度消息到WebSocket客户端
            progress_message = TaskNodeProgressMessage(
                session_id=session_id,
                task_id=task_progress.task_id,
                task_node_id=task_progress.task_id,
                progress=task_progress.progress,
                status="executing",
                message=task_progress.message,
                data=task_progress.data,
            )
            await self.send_message(session_id, progress_message)
        except Exception as e:
            logger.error(
                f"发送任务进度时出错: {e}",
                exc_info=True,
                context={"task_id": task_progress.task_id, "component": "chat_handler"},
            )

    async def _on_task_state_change(
        self,
        task_id: str,
        old_status: TaskStatus,
        new_status: TaskStatus,
    ):
        """任务状态变化回调"""
        try:
            # 从映射中获取 session_id
            session_id = self._task_to_session_map.get(task_id)
            if not session_id:
                logger.warning(f"未找到任务 {task_id} 对应的会话ID")
                return

            # 发送状态变化消息到WebSocket客户端
            state_message = TaskNodeProgressMessage(
                session_id=session_id,
                task_id=task_id,
                task_node_id=task_id,
                progress=20,
                status="planning",
                message=f"任务状态从 {old_status.value} 变更为 {new_status.value}",
                data={"old_status": old_status.value, "new_status": new_status.value},
            )
            await self.send_message(session_id, state_message)
        except Exception as e:
            logger.error(
                f"发送任务状态变化时出错: {e}",
                exc_info=True,
                context={"task_id": task_id, "component": "chat_handler"},
            )

    async def _on_task_error(self, task_error):
        """任务错误回调"""
        try:
            # 从映射中获取 session_id
            session_id = self._task_to_session_map.get(task_error.task_id)
            if not session_id:
                logger.warning(f"未找到任务 {task_error.task_id} 对应的会话ID")
                return

            # 发送错误消息到WebSocket客户端
            error_message = ErrorMessage(
                session_id=session_id,
                code=task_error.error_type,
                message=task_error.error_message,
                recoverable=task_error.recoverable,
                details={"task_id": task_error.task_id},
            )
            await self.send_message(session_id, error_message)
        except Exception as e:
            logger.error(
                f"发送任务错误时出错: {e}",
                exc_info=True,
                context={"task_id": task_error.task_id, "component": "chat_handler"},
            )

    async def _on_task_completion(self, task_result):
        """任务完成回调"""
        try:
            # 从映射中获取 session_id
            session_id = self._task_to_session_map.get(task_result.task_id)
            if not session_id:
                logger.warning(f"未找到任务 {task_result.task_id} 对应的会话ID")
                return

            try:
                if task_result.is_success:
                    # 发送完成消息到WebSocket客户端
                    complete_message = TaskNodeCompleteMessage(
                        session_id=session_id,
                        task_id=task_result.task_id,
                        task_node_id=task_result.task_id,
                        result={"response": task_result.result},
                        duration_ms=0,
                    )
                    await self.send_message(session_id, complete_message)
                else:
                    # 发送错误消息到WebSocket客户端
                    error_message = ErrorMessage(
                        session_id=session_id,
                        code="TASK_FAILED",
                        message=str(task_result.error),
                        recoverable=False,
                        details={"task_id": task_result.task_id},
                    )
                    await self.send_message(session_id, error_message)
            finally:
                # 发送完消息后清理映射，避免内存泄漏
                if task_result.task_id in self._task_to_session_map:
                    del self._task_to_session_map[task_result.task_id]
        except Exception as e:
            logger.error(
                f"发送任务完成时出错: {e}",
                exc_info=True,
                context={"task_id": task_result.task_id, "component": "chat_handler"},
            )

    async def _process_agent_stop(
        self,
        session_id: str,
        message: WebSocketMessage,
    ) -> WebSocketMessage | None:
        """处理Agent停止请求"""
        if not isinstance(message, AgentStopMessage):
            logger.error(f"Invalid message type for AGENT_STOP: {type(message)}")
            return await self.send_error_message(
                session_id,
                "INVALID_MESSAGE_TYPE",
                "Invalid message type for agent stop",
            )

        task_id = message.task_id
        logger.info(f"Received stop request for task {task_id}")
        logger.info(f"Current active agents: {list(self._active_agents.keys())}")

        # 查找对应的Agent实例
        if task_id not in self._active_agents:
            logger.warning(f"No active agent found for task {task_id}")

            # 🔧 修复：清理 LLM API 状态（即使 Agent 已经完成）
            if task_id in self._task_llm_api_state:
                try:
                    llm_state = self._task_llm_api_state[task_id]
                    if llm_state.get("active", False):
                        import time
                        duration_ms = int((time.time() - llm_state["start_time"]) * 1000) if llm_state.get("start_time") else None

                        llm_complete_message = LLMApiCompleteMessage(
                            session_id=session_id,
                            task_id=task_id,
                            provider=llm_state.get("provider", "unknown"),
                            model=llm_state.get("model", "unknown"),
                            finish_reason="stopped",
                            usage=None,
                            duration_ms=duration_ms,
                        )
                        await self.send_message(session_id, llm_complete_message)
                        logger.info(f"Sent LLMApiCompleteMessage for task {task_id} (already completed)")
                except Exception as llm_msg_error:
                    logger.error(f"Failed to send LLMApiCompleteMessage: {llm_msg_error}", exc_info=True)

                self._task_llm_api_state.pop(task_id, None)

            # Agent可能已经完成或被清理，这实际上不是错误
            # 发送停止确认消息，告知用户任务已经结束
            stopped_message = AgentStoppedMessage(
                session_id=session_id,
                task_id=task_id,
                stopped_at=message.timestamp,
                result_summary="任务已经结束或完成",
                partial=False,  # 任务已完成（非部分完成）
            )
            await self.send_message(session_id, stopped_message)
            logger.info(f"Task {task_id} was already completed, sent AgentStoppedMessage")
            return None

        agent = self._active_agents[task_id]

        # 停止Agent
        try:
            # 调用Agent的stop方法
            logger.info(f"Calling agent.stop() for task {task_id}")
            result_summary = await agent.stop()
            logger.info(f"agent.stop() returned successfully for task {task_id}")

            # 从活跃agents中移除
            if task_id in self._active_agents:
                del self._active_agents[task_id]

            # 🔧 修复：清理事件处理器
            await self._cleanup_event_handlers(task_id, agent)

            # 🔧 修复：如果 LLM API 还在活跃状态，发送完成消息
            if task_id in self._task_llm_api_state and self._task_llm_api_state[task_id].get("active", False):
                import time
                llm_state = self._task_llm_api_state[task_id]
                duration_ms = int((time.time() - llm_state["start_time"]) * 1000) if llm_state.get("start_time") else None

                try:
                    llm_complete_message = LLMApiCompleteMessage(
                        session_id=session_id,
                        task_id=task_id,
                        provider=llm_state.get("provider", "unknown"),
                        model=llm_state.get("model", "unknown"),
                        finish_reason="stopped",  # 标记为停止
                        usage=None,
                        duration_ms=duration_ms,
                    )
                    await self.send_message(session_id, llm_complete_message)
                    logger.info(f"Sent LLMApiCompleteMessage for task {task_id} (stopped)")
                except Exception as llm_msg_error:
                    logger.error(f"Failed to send LLMApiCompleteMessage: {llm_msg_error}", exc_info=True)

                # 清理 LLM API 状态
                self._task_llm_api_state.pop(task_id, None)

            # 发送停止确认消息
            try:
                stopped_message = AgentStoppedMessage(
                    session_id=session_id,
                    task_id=task_id,
                    stopped_at=message.timestamp,
                    result_summary=result_summary or "Agent已停止",
                    partial=True,  # 用户主动停止，视为部分完成
                )
                await self.send_message(session_id, stopped_message)
                logger.info(f"Sent AgentStoppedMessage for task {task_id}")
            except Exception as msg_error:
                logger.error(f"Failed to send AgentStoppedMessage: {msg_error}", exc_info=True)

            logger.info(f"Task {task_id} stopped successfully")
            return None

        except Exception as e:
            logger.error(f"Failed to stop agent for task {task_id}: {e}", exc_info=True)
            # 即使停止失败，也尝试从active_agents中移除
            if task_id in self._active_agents:
                del self._active_agents[task_id]

            # 🔧 修复：清理事件处理器
            await self._cleanup_event_handlers(task_id, agent)

            # 🔧 修复：清理 LLM API 状态（即使停止失败）
            if task_id in self._task_llm_api_state:
                try:
                    llm_state = self._task_llm_api_state[task_id]
                    if llm_state.get("active", False):
                        import time
                        duration_ms = int((time.time() - llm_state["start_time"]) * 1000) if llm_state.get("start_time") else None

                        llm_complete_message = LLMApiCompleteMessage(
                            session_id=session_id,
                            task_id=task_id,
                            provider=llm_state.get("provider", "unknown"),
                            model=llm_state.get("model", "unknown"),
                            finish_reason="error",
                            usage=None,
                            duration_ms=duration_ms,
                        )
                        await self.send_message(session_id, llm_complete_message)
                        logger.info(f"Sent LLMApiCompleteMessage for task {task_id} (error)")
                except Exception as llm_msg_error:
                    logger.error(f"Failed to send LLMApiCompleteMessage: {llm_msg_error}", exc_info=True)

                self._task_llm_api_state.pop(task_id, None)

            # 发送错误消息，但不重新抛出异常
            try:
                await self.send_error_message(
                    session_id,
                    "STOP_FAILED",
                    f"Failed to stop agent: {e!s}",
                )
            except Exception as send_error:
                logger.error(f"Failed to send error message: {send_error}", exc_info=True)
            return None

    async def _handle_system_command(
        self,
        command: str,
        session_id: str,
        task_id: str,
        user_workspace: UserWorkspace,
        user_message_content: str,
    ) -> bool:
        """处理系统命令(!命令) - 使用安全沙箱执行

        Args:
            command: 系统命令字符串(已去除!前缀)
            session_id: 会话ID
            task_id: 任务ID
            user_workspace: 用户工作区
            user_message_content: 原始用户消息内容

        Returns:
            True if command was handled, False otherwise

        """
        try:
            logger.info(f"[CHAT_HANDLER] 检测到系统命令(轻量级沙箱模式): {command}")

            # 使用轻量级沙箱执行命令（同步方法）
            result = self.sandbox_executor.execute_command(
                command=command,
                workspace_path=user_workspace.absolute_path,
                user_id=getattr(user_workspace, "user_id", session_id),
            )

            logger.info(f"[CHAT_HANDLER] 沙箱命令执行完成: exit_code={result['exit_code']}")

            # 提取结果
            success = result["success"]
            stdout = result.get("stdout", "")
            stderr = result.get("stderr", "")
            exit_code = result.get("exit_code", -1)
            execution_time = result.get("execution_time", 0)

            if not success:
                # 执行失败
                error_message = ErrorMessage(
                    session_id=session_id,
                    code="SANDBOX_EXECUTION_ERROR",
                    message=result.get("error", "Unknown error"),
                    recoverable=False,
                    details={"command": command, "exit_code": exit_code},
                )
                await self.send_message(session_id, error_message)
                return False

            # 1. 发送系统命令结果到前端
            from dawei.entity.lm_messages import AssistantMessage
            from dawei.websocket.protocol import AssistantWebSocketMessage

            # 限制输出大小（防止过大的响应）
            stdout_limited = stdout[: self.MAX_OUTPUT_SIZE]
            if len(stdout) > self.MAX_OUTPUT_SIZE:
                stdout_limited += f"\n... (output truncated, total {len(stdout)} bytes)"

            stderr_limited = stderr[: self.MAX_OUTPUT_SIZE]
            if len(stderr) > self.MAX_OUTPUT_SIZE:
                stderr_limited += f"\n... (output truncated, total {len(stderr)} bytes)"

            # 创建包含系统命令结果的assistant消息
            assistant_message = AssistantWebSocketMessage(
                id=str(uuid.uuid4()),
                type=MessageType.ASSISTANT_MESSAGE,
                session_id=session_id,
                content=[
                    {
                        "type": "system_command_result",
                        "command": command,
                        "stdout": stdout_limited,
                        "stderr": stderr_limited,
                        "exit_code": exit_code,
                        "execution_time": execution_time,
                        "cwd": str(user_workspace.absolute_path),
                    },
                ],
                timestamp=time.time(),
                task_id=task_id,
            )

            await self.send_message(session_id, assistant_message)
            logger.info("[CHAT_HANDLER] ✅ Sent system command result message")

            # 2. 保存到对话历史(维持上下文)
            if user_workspace.current_conversation:
                # 保存用户消息(系统命令)
                from dawei.entity.lm_messages import UserMessage

                user_workspace.current_conversation.say(UserMessage(content=user_message_content))

                # 保存助手消息(命令结果)
                import json

                assistant_content = json.dumps(
                    {
                        "type": "system_command_result",
                        "command": command,
                        "stdout": stdout_limited,
                        "stderr": stderr_limited,
                        "exit_code": exit_code,
                    },
                )

                user_workspace.current_conversation.say(AssistantMessage(content=assistant_content))

                # 保存对话
                try:
                    save_success = await user_workspace.save_current_conversation()
                    if save_success:
                        logger.info(
                            "[CHAT_HANDLER] ✅ Saved system command to conversation history",
                        )
                    else:
                        logger.warning(
                            "[CHAT_HANDLER] Failed to save system command to conversation",
                        )
                except Exception as save_error:
                    logger.error(
                        f"[CHAT_HANDLER] Error saving conversation: {save_error}",
                        exc_info=True,
                    )

            # 3. 发送任务完成消息
            complete_message = TaskNodeCompleteMessage(
                session_id=session_id,
                task_id=task_id,
                task_node_id=task_id,
                result={"command": command, "exit_code": exit_code},
                duration_ms=execution_time,
            )
            await self.send_message(session_id, complete_message)

            logger.info("[CHAT_HANDLER] ✅ 沙箱命令执行成功")
            return True

        except Exception as e:
            logger.error(f"[CHAT_HANDLER] 沙箱命令执行出错: {e}", exc_info=True)

            # 发送错误消息
            error_message = ErrorMessage(
                session_id=session_id,
                code="SANDBOX_ERROR",
                message=f"沙箱执行出错: {e!s}",
                recoverable=False,
                details={"task_id": task_id, "command": command},
            )
            await self.send_message(session_id, error_message)

            return False

    async def on_cleanup(self):
        """清理资源"""
        try:
            # 停止任务管理器
            if hasattr(self, "_task_manager"):
                await self._task_manager.stop()

            # 清理活跃的Agent实例
            self._active_agents.clear()

            # 清理任务到会话的映射
            self._task_to_session_map.clear()

            logger.info("ChatHandler资源清理完成")
        except Exception as e:
            logger.error(f"ChatHandler清理时出错: {e}", exc_info=True)


class ConnectHandler(AsyncMessageHandler):
    """处理客户端连接成功后的 'connect' 消息。"""

    def get_supported_types(self) -> List[str]:
        return [MessageType.CONNECT]

    async def process_message(
        self,
        session_id: str,
        message: BaseWebSocketMessage,
        message_id: str,
    ) -> BaseWebSocketMessage | None:
        """处理 'connect' 消息，可以执行会话初始化等操作。"""
        logger.info(f"会话 {session_id} 已连接。消息: {message}")

        # 可以在这里添加更多的会话初始化逻辑
        # 例如，从数据库加载用户状态等

        # 返回一个确认消息
        return BaseWebSocketMessage(
            id=f"response_{message_id}",
            type=MessageType.CONNECTED,
            session_id=session_id,
            message="Connection acknowledged",
        )


# 全局实例，供 WebSocketManager 访问
chat_handler_instance = None


def set_chat_handler_instance(handler):
    """设置 ChatHandler 全局实例"""
    global chat_handler_instance
    chat_handler_instance = handler
