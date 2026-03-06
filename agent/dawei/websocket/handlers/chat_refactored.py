# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""聊天消息处理器（Refactored Version）

处理用户发送的聊天消息，使用新的 Agent 接口进行处理。

Refactoring Changes:
- Extracted agent lifecycle handlers (pause/resume/stop) to AgentLifecycleHandler
- Extracted event forwarding to EventForwardingHandler
- Extracted system command handling to SystemCommandHandler
- Kept core agent creation and task management in ChatHandler
- Reduced from 2,562 lines to ~800 lines (68% reduction)
"""

import time
import uuid
from datetime import datetime, timezone
from dawei.core.datetime_compat import UTC
from typing import List, Dict, Any

from dawei.agentic.agent import Agent

# PDCA Integration
from dawei.agentic.agent_pdca_integration import add_pdca_to_agent
from dawei.agentic.pdca_context import PDCAPhase
from dawei.async_task.task_manager import AsyncTaskManager
from dawei.async_task.types import RetryPolicy, TaskDefinition, TaskStatus
from dawei.core import local_context
from dawei.core.events import TaskEvent, TaskEventType
from dawei.core.exceptions import (
    AgentInitializationError,
    ConfigurationError,
    ConnectionError,
    IOError,
    LLMError,
    ValidationError,
    WebSocketError,
)
from dawei.entity.user_input_message import UserInputMessage
from dawei.logg.logging import get_logger
from dawei.websocket.protocol import (
    AgentCompleteMessage,
    AgentStopMessage,
    ErrorMessage,
    FollowupResponseMessage,
    MessageType,
    PDACycleCompleteMessage,
    PDACycleStartMessage,
    PDCAPhaseAdvanceMessage,
    PDCAStatusUpdateMessage,
    StreamCompleteMessage,
    TaskNodeCompleteMessage,
    TaskNodeProgressMessage,
    TaskNodeStartMessage,
    WebSocketMessage,
)
from dawei.workspace.user_workspace import UserWorkspace
from dawei.workspace.workspace_manager import workspace_manager

from .agent_lifecycle_handler import AgentLifecycleHandler
from .base import AsyncMessageHandler
from .event_forwarding_handler import EventForwardingHandler
from .system_command_handler import SystemCommandHandler

logger = get_logger(__name__)


class ChatHandler(AsyncMessageHandler):
    """聊天消息处理器（Refactored Version）

    功能:
    - 处理用户聊天消息并创建 Agent 实例
    - 管理Agent生命周期（创建、执行）
    - 转发Agent事件到WebSocket客户端
    - 使用专用处理器处理 pause/resume/stop
    - 使用专用处理器处理事件转发
    - 使用专用处理器处理系统命令
    - 管理任务并发和重试策略

    Refactoring:
    - 委托 Agent 生命周期操作到 AgentLifecycleHandler
    - 委托事件转发到 EventForwardingHandler
    - 委托系统命令执行到 SystemCommandHandler
    - 保留核心 Agent 创建和任务管理逻辑

    配置常量:
    - DEFAULT_MAX_CONCURRENT_TASKS: 默认最大并发任务数
    - DEFAULT_TASK_TIMEOUT: 默认任务超时时间（秒）
    - DEFAULT_RETRY_ATTEMPTS: 默认重试次数
    - DEFAULT_RETRY_DELAY: 默认重试延迟（秒）

    Attributes:
        _active_agents: 存储活跃的Agent实例
        _task_to_session_map: 任务ID到会话ID的映射
        _task_manager: 异步任务管理器
        _lifecycle_handler: Agent生命周期处理器
        _event_handler: 事件转发处理器
        _command_handler: 系统命令处理器

    """

    # 配置常量
    DEFAULT_MAX_CONCURRENT_TASKS = 10
    DEFAULT_TASK_TIMEOUT = 900.0  # 15分钟（支持大型HTML/代码生成）
    DEFAULT_RETRY_ATTEMPTS = 2
    DEFAULT_RETRY_DELAY = 1.0
    DEFAULT_MAX_RETRY_DELAY = 10.0

    def __init__(self, max_concurrent_tasks: int | None = None):
        _max_tasks = max_concurrent_tasks or self.DEFAULT_MAX_CONCURRENT_TASKS
        super().__init__(max_concurrent_tasks=_max_tasks)

        # 存储活跃的 Agent 实例
        self._active_agents: Dict[str, Agent] = {}

        # 存储任务ID到会话ID的映射，用于回调中查找正确的会话ID
        self._task_to_session_map: Dict[str, str] = {}

        # 🔧 修复：存储任务ID到事件处理器ID的映射，用于清理
        self._task_event_handler_ids: Dict[str, Dict[str, str]] = {}

        # 初始化异步任务管理器
        self._task_manager = AsyncTaskManager()

        # 设置任务状态回调
        self._task_manager.set_progress_callback(self._on_task_progress)
        self._task_manager.set_state_change_callback(self._on_task_state_change)
        self._task_manager.set_error_callback(self._on_task_error)
        self._task_manager.set_completion_callback(self._on_task_completion)

        # 初始化专用处理器（使用依赖注入模式）
        self._lifecycle_handler = AgentLifecycleHandler(
            active_agents=self._active_agents,
            send_message_callback=self.send_message,
            send_error_callback=self.send_error_message,
        )

        self._event_handler = EventForwardingHandler(send_message_callback=self.send_message)

        self._command_handler = SystemCommandHandler(send_message_callback=self.send_message)

        logger.info("[CHAT_HANDLER] Refactored ChatHandler initialized with specialized handlers")

    def get_supported_types(self) -> List[str]:
        """获取支持的消息类型"""
        return [
            MessageType.USER_MESSAGE,
            MessageType.FOLLOWUP_RESPONSE,
            MessageType.AGENT_PAUSE,
            MessageType.AGENT_RESUME,
            MessageType.AGENT_STOP,
        ]

    async def on_initialize(self):
        """初始化时的回调"""
        await super().on_initialize()

        # 启动任务管理器
        await self._task_manager.start()

        logger.info("聊天处理器已初始化 (refactored version)")

    async def process_message(
        self,
        session_id: str,
        message: WebSocketMessage,
        message_id: str,
    ) -> WebSocketMessage | None:
        """处理用户消息，创建并启动一个 Agent 实例"""
        local_context.set_local_context(session_id=session_id, message_id=message_id)

        # 委托给专用处理器处理特殊消息类型
        if message.type == MessageType.FOLLOWUP_RESPONSE:
            return await self._process_followup_response(session_id, message)

        if message.type == MessageType.AGENT_STOP:
            return await self._lifecycle_handler.process_stop(session_id, message, self._cleanup_event_handlers)

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

        # 使用AsyncTaskManager管理任务
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

    # ==================== 核心方法（保留在 ChatHandler）====================

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

        # 初始化变量
        user_workspace = None
        agent = None

        try:
            # 1. 获取和验证工作区
            (
                workspace_id,
                workspace_path,
                user_workspace,
            ) = await self._get_and_validate_workspace(user_message)

            # 2. 更新用户UI上下文
            await self._update_user_ui_context(user_workspace, user_message)

            # 3. 加载或创建会话
            await self._load_or_create_conversation(user_workspace, user_message)

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

            # 9. 设置事件转发（委托给专用处理器）
            await self._setup_event_forwarding(agent, session_id, task_id)

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

    # ==================== 辅助方法（保留核心逻辑）====================

    async def _get_and_validate_workspace(
        self,
        user_message: UserInputMessage,
    ) -> tuple[str, str, UserWorkspace]:
        """获取和验证工作区"""
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

        # 确保工作区已初始化
        if not user_workspace.is_initialized():
            await user_workspace.initialize()

        return workspace_id, workspace_path, user_workspace

    async def _update_user_ui_context(self, user_workspace: UserWorkspace, user_message: UserInputMessage) -> None:
        """更新用户UI上下文"""
        if not (hasattr(user_message, "user_ui_context") and user_message.user_ui_context):
            return

        from dawei.entity.system_info import UserUIContext

        ui_context_data = user_message.user_ui_context
        logger.info(f"[CHAT_HANDLER] Updating user_ui_context with: {ui_context_data}")

        try:
            new_ui_context = UserUIContext.from_dict(ui_context_data)
            user_workspace.workspace_info.user_ui_context = new_ui_context

            await user_workspace.persistence_manager.save_workspace_settings(
                user_workspace.workspace_info.to_dict(),
            )
            logger.info("[CHAT_HANDLER] Successfully updated and persisted user_ui_context")

        except (ValueError, IOError) as e:
            logger.error(f"[CHAT_HANDLER] Failed to update UI context: {e}", exc_info=True)
            raise

    async def _load_or_create_conversation(self, user_workspace: UserWorkspace, user_message: UserInputMessage) -> None:
        """加载或创建会话"""
        conversation_id = user_message.metadata.get("conversationId")
        if not conversation_id:
            logger.info("[CHAT_HANDLER] No conversationId provided, will create new conversation")
            return

        logger.info(f"[CHAT_HANDLER] Loading existing conversation: {conversation_id}")

        try:
            from dawei.conversation.conversation_history_manager import ConversationHistoryManager

            conv_manager = ConversationHistoryManager(workspace_path=user_workspace.absolute_path)
            await conv_manager.build_from_dir()

            conversation = await conv_manager.get_by_id(conversation_id)
            if conversation:
                user_workspace.current_conversation = conversation
                logger.info(f"[CHAT_HANDLER] Successfully loaded conversation {conversation_id}")
            else:
                logger.warning(
                    f"[CHAT_HANDLER] Conversation {conversation_id} not found, will create new one",
                )

        except (FileNotFoundError, IOError) as e:
            logger.error(f"[CHAT_HANDLER] Failed to load conversation: {e}", exc_info=True)
            raise

    async def _create_and_initialize_agent(self, user_workspace: UserWorkspace) -> Agent:
        """创建和初始化 Agent"""
        try:
            logger.info(f"[CHAT_HANDLER] Starting agent creation for workspace: {user_workspace.workspace_info.id}")
            agent = await Agent.create_with_default_engine(user_workspace)
            logger.info("[CHAT_HANDLER] Agent created successfully, now initializing...")
            await agent.initialize()
            logger.info("[CHAT_HANDLER] Agent initialized successfully")
            return agent
        except (ConfigurationError, ValidationError, AgentInitializationError) as e:
            logger.error(
                f"[CHAT_HANDLER] Failed to create or initialize agent: {e}",
                exc_info=True,
            )
            raise
        except AttributeError as e:
            logger.error(
                f"[CHAT_HANDLER] AttributeError during agent initialization: {e}",
                exc_info=True,
            )
            raise RuntimeError(f"Agent initialization failed due to internal error: {e}")
        except Exception as e:
            logger.error(
                f"[CHAT_HANDLER] Unexpected error during agent initialization: {e}",
                exc_info=True,
            )
            raise RuntimeError(f"Agent initialization failed: {e}")

    async def _configure_agent_mode(self, agent: Agent, user_workspace: UserWorkspace, pdca_extension=None) -> None:
        """从 user_ui_context 同步 mode 到 agent.config"""
        # 优先使用PDCA推荐的mode，其次是用户选择的mode
        if pdca_extension and pdca_extension.pdca_enabled and pdca_extension.current_cycle:
            pdca_mode = pdca_extension.get_current_mode_name()
            agent.config.mode = pdca_mode
            logger.info(f"[CHAT_HANDLER] PDCA mode set to: {pdca_mode}")
        elif user_workspace.workspace_info.user_ui_context and user_workspace.workspace_info.user_ui_context.current_mode:
            requested_mode = user_workspace.workspace_info.user_ui_context.current_mode
            logger.info(f"[CHAT_HANDLER] Setting agent mode from user_ui_context: {requested_mode}")
            agent.config.mode = requested_mode
            logger.info(f"[CHAT_HANDLER] ✅ Agent mode set to: {requested_mode}")
        else:
            logger.info(
                f"[CHAT_HANDLER] No current_mode in user_ui_context, using default: {agent.config.mode}",
            )

    async def _integrate_pdca_if_needed(self, agent: Agent, session_id: str, task_id: str, _user_workspace: UserWorkspace, user_message: UserInputMessage):
        """集成PDCA扩展（如果任务需要）"""
        try:
            pdca_extension = add_pdca_to_agent(agent)

            task_description = user_message.content
            should_use_pdca = pdca_extension.should_use_pdca(task_description)

            logger.info(f"[PDCA] Task complexity check: should_use_pdca={should_use_pdca}")

            if not should_use_pdca:
                pdca_extension.disable_pdca()
                logger.info("[PDCA] Simple task detected, PDCA disabled")
                return None

            logger.info("[PDCA] Complex task detected, starting PDCA cycle")

            pdca_cycle = pdca_extension.start_pdca_cycle(
                session_id=session_id,
                task_description=task_description,
                task_goals=[f"Complete: {task_description[:100]}"],
                success_criteria=[
                    "Task completed successfully",
                    "Quality standards met",
                ],
            )

            await self._send_pdca_cycle_start_message(
                session_id=session_id,
                task_id=task_id,
                pdca_cycle=pdca_cycle,
            )

            await self._send_pdca_status_update_message(
                session_id=session_id,
                task_id=task_id,
                pdca_extension=pdca_extension,
            )

            logger.info(f"[PDCA] PDCA cycle started successfully: {pdca_cycle.cycle_id}")

            return pdca_extension

        except Exception as e:
            logger.error(f"[PDCA] Failed to integrate PDCA: {e}", exc_info=True)
            return None

    async def _send_pdca_cycle_start_message(self, session_id: str, _task_id: str, pdca_cycle):
        """发送PDCA循环启动消息"""
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
        """发送PDCA状态更新消息"""
        try:
            status = pdca_extension.get_pdca_status()

            if status and status.get("active"):
                phases = {
                    PDCAPhase.PLAN.value: "pending",
                    PDCAPhase.DO.value: "pending",
                    PDCAPhase.CHECK.value: "pending",
                    PDCAPhase.ACT.value: "pending",
                }

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

    async def _send_agent_start_message(self, session_id: str, task_id: str, agent: Agent, workspace_id: str, user_message: UserInputMessage) -> None:
        """发送 Agent 启动消息"""
        try:
            agent_mode = getattr(agent.config, "mode", "orchestrator")
            agent_start_message = AgentStartMessage(
                session_id=session_id,
                task_id=task_id,
                agent_mode=agent_mode,
                user_message=user_message.content[:200],
                workspace_id=workspace_id,
                metadata={
                    "model": getattr(agent.config, "model", "unknown"),
                    "temperature": getattr(agent.config, "temperature", 0.7),
                },
            )
            await self.send_message(session_id, agent_start_message)
            logger.info(f"[CHAT_HANDLER] ✅ Sent AGENT_START message: mode={agent_mode}")
        except (ConnectionError, IOError, WebSocketError) as e:
            logger.error(f"[CHAT_HANDLER] Failed to send agent start message: {e}", exc_info=True)
            raise

    async def _configure_llm_provider(self, session_id: str, task_id: str, agent: Agent, user_workspace: UserWorkspace) -> None:
        """配置 LLM Provider"""
        if not (user_workspace.workspace_info.user_ui_context and user_workspace.workspace_info.user_ui_context.current_llm_id):
            logger.info("[CHAT_HANDLER] No current_llm_id in user_ui_context, using default LLM")
            return

        current_llm_id = user_workspace.workspace_info.user_ui_context.current_llm_id
        logger.info(f"[CHAT_HANDLER] Setting LLM to user selection: {current_llm_id}")

        llm_provider = agent.execution_engine._llm_service
        if not hasattr(llm_provider, "set_current_config"):
            logger.warning("[CHAT_HANDLER] ⚠️  LLMProvider does not have set_current_config method")
            return

        available_configs = llm_provider.get_config_names() if hasattr(llm_provider, "get_config_names") else []
        logger.info(f"[CHAT_HANDLER] Available LLM configs: {available_configs}")

        try:
            success = llm_provider.set_current_config(current_llm_id)
            if not success:
                logger.warning(f"[CHAT_HANDLER] ⚠️  Failed to set LLM config to: {current_llm_id}")

                error_message = ErrorMessage(
                    session_id=session_id,
                    code="LLM_CONFIG_NOT_FOUND",
                    message=f"您选择的 LLM 配置 '{current_llm_id}' 不可用。",
                    recoverable=False,
                    details={
                        "task_id": task_id,
                        "requested_config": current_llm_id,
                        "available_configs": available_configs,
                    },
                )
                await self.send_message(session_id, error_message)

                if available_configs:
                    llm_provider.set_current_config(available_configs[0])
            else:
                logger.info(f"[CHAT_HANDLER] ✅ Successfully set LLM config to: {current_llm_id}")
        except (ConfigurationError, LLMError, ValueError) as e:
            logger.error(f"[CHAT_HANDLER] Error configuring LLM provider: {e}", exc_info=True)
            raise

    async def _process_file_references(self, user_message: UserInputMessage, workspace_path: str) -> UserInputMessage:
        """处理消息中的文件引用"""
        from dawei.websocket.handlers.at_message_processor import AtMessageProcessor

        original_message = user_message.content
        try:
            enhanced_message, file_refs = AtMessageProcessor.process_and_enhance(
                original_message,
                workspace_path,
            )

            if file_refs:
                logger.info(f"[CHAT_HANDLER] Processed {len(file_refs)} file references in message")

            return UserInputMessage(text=enhanced_message)

        except ValueError as e:
            logger.error(f"[CHAT_HANDLER] Error processing @ file references: {e}", exc_info=True)
            return UserInputMessage(text=original_message)
        except Exception as e:
            logger.warning(f"[CHAT_HANDLER] Unexpected error processing file references: {e}", exc_info=True)
            return UserInputMessage(text=original_message)

    async def _handle_system_command_if_needed(self, session_id: str, task_id: str, user_workspace: UserWorkspace, _user_input: UserInputMessage, user_message: UserInputMessage) -> bool:
        """处理系统命令(如果需要)"""
        original_message = user_message.content
        original_message_stripped = original_message.strip()

        if not original_message_stripped.startswith("!"):
            return False

        logger.info("[CHAT_HANDLER] Detected ! command in user message")

        system_command = original_message_stripped[1:].strip()

        if not user_workspace.current_conversation:
            from dawei.conversation.conversation import Conversation

            user_workspace.current_conversation = Conversation()
            logger.info("[CHAT_HANDLER] Created new conversation for system command")

        # 委托给专用处理器
        handled = await self._command_handler.handle_command(
            command=system_command,
            session_id=session_id,
            task_id=task_id,
            user_workspace=user_workspace,
            user_message_content=original_message,
        )

        if handled:
            logger.info("[CHAT_HANDLER] System command handled, skipping agent creation")
            return True

        logger.warning("[CHAT_HANDLER] System command handling failed, falling back to agent")
        return False

    async def _save_conversation_before_agent(self, user_workspace: UserWorkspace, _user_message: UserInputMessage) -> None:
        """在启动 Agent 前保存对话"""
        if not user_workspace.current_conversation:
            return

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
        except IOError as e:
            logger.error(f"[CHAT_HANDLER] Error saving conversation: {e}", exc_info=True)
            raise

    async def _execute_agent(self, agent: Agent, user_input: UserInputMessage) -> None:
        """执行 Agent"""
        logger.info("[CHAT_HANDLER] About to call agent.process_message...")
        try:
            await agent.process_message(user_input)
            logger.info("[CHAT_HANDLER] agent.process_message returned!")
        except Exception as e:
            logger.error(f"[CHAT_HANDLER] Error executing agent: {e}", exc_info=True)
            raise

    async def _handle_agent_error(self, error: Exception, session_id: str, task_id: str, _user_workspace: UserWorkspace | None = None, agent: Agent | None = None) -> None:
        """处理 Agent 错误"""
        logger.error(f"执行 Agent 任务时出错: {error}", exc_info=True)

        error_str = str(error)
        user_friendly_message = error_str
        error_code = "AGENT_EXECUTION_ERROR"

        if "StateTransitionError" in error_str:
            user_friendly_message = self._extract_llm_error_message(error_str, error)
        elif "HTTP 429" in error_str or "insufficient balance" in error_str:
            user_friendly_message = "LLM API 账户余额不足或调用次数超限。请检查 API 配置和账户余额。"
        elif "HTTP 500" in error_str:
            user_friendly_message = "LLM 服务暂时不可用(HTTP 500),请稍后重试。"
        elif "LLM error" in error_str:
            user_friendly_message = f"LLM 调用失败: {error_str}"

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

        # 发送 stream_complete 消息来明确终止任务流
        complete_message = StreamCompleteMessage(
            session_id=session_id,
            task_id=task_id,
            content="",
            reasoning_content=None,
            tool_calls=[],
            usage=None,
            finish_reason="error",
        )
        await self.send_message(session_id, complete_message)

    def _extract_llm_error_message(self, _error_str: str, error: Exception) -> str:
        """从 StateTransitionError 中提取 LLM 错误消息"""
        import re
        import traceback

        tb_str = "".join(traceback.format_exception(type(error), error, error.__traceback__))

        if "HTTP 429" in tb_str or "insufficient balance" in tb_str:
            return "LLM API 账户余额不足或调用次数超限。请检查 API 配置和账户余额。"
        if "HTTP 500" in tb_str:
            return "LLM 服务暂时不可用(HTTP 500),请稍后重试。"
        if "LLM error" in tb_str or "LLMError" in tb_str:
            llm_error_match = re.search(r"LLM error from \w+: (.+)", tb_str)
            if llm_error_match:
                return f"LLM 调用失败: {llm_error_match.group(1)}"
            return "LLM 调用失败,请检查API配置。"
        return "任务执行过程中出现错误。请查看上方显示的错误详情。"

    async def _cleanup_agent_task(self, session_id: str, task_id: str, user_workspace: UserWorkspace | None = None, agent: Agent | None = None) -> None:
        """清理 Agent 任务资源"""
        logger.info(f"[CHAT_HANDLER] Finally block executed. user_workspace: {user_workspace is not None}")

        if user_workspace and user_workspace.current_conversation:
            logger.info(
                f"[CHAT_HANDLER] Saving conversation in finally block. Message count: {user_workspace.current_conversation.message_count}",
            )
            try:
                save_success = await user_workspace.save_current_conversation()
                if save_success:
                    logger.info(
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

        await self.update_session_data(session_id, data={"current_task_id": None})

        # 清理 Agent 实例
        if task_id in self._active_agents:
            del self._active_agents[task_id]

        # 清理事件处理器
        await self._cleanup_event_handlers(task_id, agent)

    async def _cleanup_event_handlers(self, task_id: str, agent: Agent | None = None) -> None:
        """清理事件处理器，防止内存泄漏"""
        if task_id not in self._task_event_handler_ids:
            return

        handler_ids = self._task_event_handler_ids[task_id]
        logger.info(f"[EVENT_HANDLER] 🧹 Cleaning up {len(handler_ids)} event handlers for task {task_id}")

        event_bus = None
        if agent:
            event_bus = agent.event_bus
        elif task_id in self._active_agents:
            event_bus = self._active_agents[task_id].event_bus

        if not event_bus:
            logger.warning(f"[EVENT_HANDLER] ⚠️ Cannot cleanup handlers for task {task_id}: no event bus available.")
            del self._task_event_handler_ids[task_id]
            return

        removed_count = 0
        for event_type_value, handler_id in handler_ids.items():
            try:
                event_type = TaskEventType(event_type_value)
                success = event_bus.remove_handler(event_type, handler_id)
                if success:
                    removed_count += 1
            except (ValueError, Exception) as e:
                logger.error(f"[EVENT_HANDLER] ❌ Error removing handler: {e}", exc_info=True)

        del self._task_event_handler_ids[task_id]

        logger.info(
            f"[EVENT_HANDLER] ✅ Cleanup complete for task {task_id}: removed {removed_count}/{len(handler_ids)} handlers",
        )

    async def _setup_event_forwarding(self, agent: Agent, session_id: str, task_id: str):
        """设置事件转发（委托给专用处理器）"""
        # 🔧 修复：检查是否已经注册过事件处理器，防止重复注册导致内存泄漏
        if task_id in self._task_event_handler_ids:
            logger.warning(
                f"[EVENT_HANDLER] Task {task_id} already has registered event handlers, skipping duplicate registration. This prevents the memory leak issue.",
            )
            return

        # 创建 PDCA 阶段完成回调
        async def pdca_phase_callback(s_id, t_id):
            await self._handle_pdca_phase_completion(s_id, t_id)

        # 委托给 EventForwardingHandler
        handler_ids = await self._event_handler.setup_event_forwarding(
            agent=agent,
            session_id=session_id,
            task_id=task_id,
            pdca_phase_callback=pdca_phase_callback,
        )

        # 保存handler ID映射
        self._task_event_handler_ids[task_id] = handler_ids
        logger.info(
            f"[EVENT_HANDLER] ✅ Successfully registered {len(handler_ids)} event handlers for task {task_id}",
        )

    async def _handle_pdca_phase_completion(self, session_id: str, task_id: str):
        """处理PDCA阶段完成并发送阶段推进消息"""
        try:
            agent = self._active_agents.get(task_id)
            if not agent:
                return

            if not hasattr(agent, "_pdca_extension"):
                return

            pdca_extension = agent._pdca_extension

            if not pdca_extension.pdca_enabled or not pdca_extension.current_cycle:
                return

            status = pdca_extension.get_pdca_status()
            if not status or not status.get("active"):
                return

            current_phase = status.get("current_phase")
            cycle_id = status.get("cycle_id")

            logger.info(f"[PDCA] Current phase: {current_phase}, cycle: {cycle_id}")

            from dawei.agentic.pdca_context import PDCAPhase

            phase_transitions = {
                PDCAPhase.PLAN.value: PDCAPhase.DO.value,
                PDCAPhase.DO.value: PDCAPhase.CHECK.value,
                PDCAPhase.CHECK.value: PDCAPhase.ACT.value,
            }

            next_phase = phase_transitions.get(current_phase)

            if next_phase:
                logger.info(f"[PDCA] Advancing from {current_phase} to {next_phase}")

                await self._send_pdca_phase_advance_message(
                    session_id=session_id,
                    task_id=task_id,
                    cycle_id=cycle_id,
                    from_phase=current_phase,
                    to_phase=next_phase,
                    reason=f"完成{current_phase}阶段，准备进入{next_phase}阶段",
                )

                pdca_extension.advance_pdca_phase(
                    phase_data={"result": None},  # TODO: get actual result
                    next_phase=next_phase,
                )

                await self._send_pdca_status_update_message(
                    session_id=session_id,
                    task_id=task_id,
                    pdca_extension=pdca_extension,
                )
            elif current_phase == PDCAPhase.ACT.value:
                await self._send_pdca_cycle_complete_message(
                    session_id=session_id,
                    task_id=task_id,
                    cycle_id=cycle_id,
                    pdca_extension=pdca_extension,
                )

        except Exception as e:
            logger.error(f"[PDCA] Failed to handle PDCA phase completion: {e}", exc_info=True)

    async def _send_pdca_phase_advance_message(self, session_id: str, _task_id: str, cycle_id: str, from_phase: str, to_phase: str, reason: str):
        """发送PDCA阶段推进消息"""
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

    async def _send_pdca_cycle_complete_message(self, session_id: str, _task_id: str, cycle_id: str, pdca_extension):
        """发送PDCA循环完成消息"""
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

    # ==================== AsyncTaskManager 回调 ====================

    async def _on_task_progress(self, task_progress):
        """任务进度回调"""
        try:
            session_id = self._task_to_session_map.get(task_progress.task_id)
            if not session_id:
                logger.warning(f"未找到任务 {task_progress.task_id} 对应的会话ID")
                return

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
            logger.error(f"发送任务进度时出错: {e}", exc_info=True)

    async def _on_task_state_change(self, task_id: str, old_status: TaskStatus, new_status: TaskStatus):
        """任务状态变化回调"""
        try:
            session_id = self._task_to_session_map.get(task_id)
            if not session_id:
                logger.warning(f"未找到任务 {task_id} 对应的会话ID")
                return

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
            logger.error(f"发送任务状态变化时出错: {e}", exc_info=True)

    async def _on_task_error(self, task_error):
        """任务错误回调"""
        try:
            session_id = self._task_to_session_map.get(task_error.task_id)
            if not session_id:
                logger.warning(f"未找到任务 {task_error.task_id} 对应的会话ID")
                return

            error_message = ErrorMessage(
                session_id=session_id,
                code=task_error.error_type,
                message=task_error.error_message,
                recoverable=task_error.recoverable,
                details={"task_id": task_error.task_id},
            )
            await self.send_message(session_id, error_message)
        except Exception as e:
            logger.error(f"发送任务错误时出错: {e}", exc_info=True)

    async def _on_task_completion(self, task_result):
        """任务完成回调"""
        try:
            session_id = self._task_to_session_map.get(task_result.task_id)
            if not session_id:
                logger.warning(f"未找到任务 {task_result.task_id} 对应的会话ID")
                return

            try:
                if task_result.is_success:
                    complete_message = TaskNodeCompleteMessage(
                        session_id=session_id,
                        task_id=task_result.task_id,
                        task_node_id=task_result.task_id,
                        result={"response": task_result.result},
                        duration_ms=0,
                    )
                    await self.send_message(session_id, complete_message)
                else:
                    error_message = ErrorMessage(
                        session_id=session_id,
                        code="TASK_FAILED",
                        message=str(task_result.error),
                        recoverable=False,
                        details={"task_id": task_result.task_id},
                    )
                    await self.send_message(session_id, error_message)
            finally:
                if task_result.task_id in self._task_to_session_map:
                    del self._task_to_session_map[task_result.task_id]
                    logger.debug(
                        f"Cleaned up task_to_session_map entry for task {task_result.task_id}",
                    )
        except Exception as e:
            logger.error(f"发送任务完成时出错: {e}", exc_info=True)

    async def on_cleanup(self):
        """清理资源"""
        try:
            if hasattr(self, "_task_manager"):
                await self._task_manager.stop()

            self._active_agents.clear()
            self._task_to_session_map.clear()

            logger.info("ChatHandler资源清理完成")
        except Exception as e:
            logger.error(f"ChatHandler清理时出错: {e}", exc_info=True)
