# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""聊天消息处理器

处理用户发送的聊天消息，使用新的 Agent 接口进行处理。
"""

import time
import uuid
from datetime import UTC, datetime, timezone
from dawei.core.datetime_compat import UTC
from typing import List, Dict, Any

from dawei.core.events import TaskEvent
from dawei.sandbox.lightweight_executor import CommandExecutor
from dawei.websocket.protocol import (
    AgentCompleteMessage,
    AgentSpanMessage,
    AgentStartMessage,
    AgentStatusUpdateMessage,
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
# 图谱节点状态(TaskGraph/TaskNode 侧)。注意与 async_task.types.TaskStatus
# (异步任务管理器侧)是两个不同枚举,勿混用——见 docs/任务终结交互方案.md §2
from dawei.entity.task_types import TaskStatus as GraphTaskStatus

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


def _categorize_llm_error(error_str: str) -> tuple[str | None, str | None, bool]:
    """Map an LLM/gateway error string to a user-friendly (code, message, recoverable).

    The support system has NO machine account by design (no client_credentials
    endpoint exists; only user password-login), so gateway calls depend on the
    user's frontend JWT. When that's missing/expired/invalid the gateway returns
    HTTP 401. Without this mapping the user sees a cryptic "LLM error from
    openai: HTTP 401"; this turns it into an actionable "请重新登录" prompt.
    Returns (None, None, False) when the error doesn't match a known category
    (caller keeps the original code/message).
    """
    s = error_str or ""
    low = s.lower()
    if "HTTP 401" in s or "invalid token" in low or "unauthorized" in low:
        return ("AUTH_ERROR", "认证失败：登录已过期或无效，请重新登录后再试。", True)
    if "HTTP 402" in s or "insufficient credits" in low:
        return ("INSUFFICIENT_CREDITS", "积分不足，无法完成请求。请联系管理员充值后重试。", True)
    if "HTTP 429" in s or "rate limit" in low:
        return ("RATE_LIMITED", "请求过于频繁，请稍等片刻后再试。", True)
    if "HTTP 404" in s or "model not found" in low:
        return ("MODEL_NOT_FOUND", "当前选择的模型不可用，请切换到其他模型后重试。", True)
    # 5xx：同时识别 "HTTP 502" 和网关 SSE 格式 "Provider error (502)"
    import re as _re
    if any(c in s for c in ("HTTP 500", "HTTP 502", "HTTP 503", "HTTP 504")) or _re.search(r"Provider error \((50[0234])\)", s):
        return ("SERVER_ERROR", "AI 服务暂时不可用，请稍后重试。", True)
    # 网络错误：必须是客户端到网关的连接问题。
    # 排除 "Cannot connect to provider" —— 那是网关到上游 provider 的错误，已归类为 SERVER_ERROR。
    if ("ConnectionError" in s or "ConnectError" in s or "Connection refused" in s
            or ("Cannot connect" in s and "provider" not in low)):
        return ("NETWORK_ERROR", "网络连接失败，请检查网络后重试。", True)
    if "timeout" in low or "timed out" in low:
        return ("TIMEOUT_ERROR", "请求超时，AI 服务响应时间过长。请稍后重试。", True)
    return (None, None, False)


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
    DEFAULT_TASK_TIMEOUT = 600  # 兜底值；实际取 agent_execution.chat_task_timeout（env: AGENT_CHAT_TASK_TIMEOUT）
    DEFAULT_RETRY_ATTEMPTS = 2
    DEFAULT_RETRY_DELAY = 1.0
    DEFAULT_MAX_RETRY_DELAY = 10.0
    MAX_OUTPUT_SIZE = 100000  # 100KB

    @classmethod
    def _resolve_task_timeout(cls) -> float | None:
        """整轮 Agent 任务超时（秒）。

        读取 agent_execution.chat_task_timeout（env: AGENT_CHAT_TASK_TIMEOUT）：
        -1 = 不限时（默认，由单次 LLM/工具超时与迭代上限兜底），>0 = 秒数。
        读取失败时回退 DEFAULT_TASK_TIMEOUT。
        """
        try:
            from dawei.config.settings import get_settings  # 延迟导入避免循环依赖

            cfg_seconds = get_settings().agent_execution.chat_task_timeout
        except Exception:
            return float(cls.DEFAULT_TASK_TIMEOUT)
        return None if cfg_seconds < 0 else float(cfg_seconds)

    def __init__(self, max_concurrent_tasks: int | None = None):
        _max_tasks = max_concurrent_tasks or self.DEFAULT_MAX_CONCURRENT_TASKS
        super().__init__(max_concurrent_tasks=_max_tasks)

        # 存储活跃的 Agent 实例
        self._active_agents: Dict[str, Agent] = {}

        # 存储任务ID到会话ID的映射，用于回调中查找正确的会话ID
        self._task_to_session_map: Dict[str, str] = {}

        # 存储任务ID到conversation_id的映射，用于错误消息路由到正确的前端对话
        self._task_to_conv_id_map: Dict[str, str] = {}

        # 任务ID到注册表工作区ID的映射：UserWorkspace.uuid 是每实例随机值
        # (user_workspace.py __init__),不能作为跨请求稳定键;agent_span 的
        # WS 消息与持久化列必须用注册表 ID(前端路由/workspaceTraceSpans 的键)。
        self._task_workspace_map: Dict[str, str] = {}

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
        self.sandbox_executor = CommandExecutor()
        logger.info("[CHAT_HANDLER] CommandExecutor initialized")

    def get_supported_types(self) -> List[str]:
        """获取支持的消息类型

        P1b ⑩：TASK_NODE_STOP 已迁入独立 TaskNodeControlHandler
        （ws_server 注册；路由器按类型并行执行所有声明处理器，此处保留
        会造成双发——每条 stop 触发两次级联终结与两条回执）。
        """
        return [
            MessageType.USER_MESSAGE,
            MessageType.RESET_CONVERSATION,
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

        # 处理 RESET_CONVERSATION 消息
        if message.type == MessageType.RESET_CONVERSATION:
            return await self._process_reset_conversation(session_id, message)

        # 处理 FOLLOWUP_RESPONSE 消息
        if message.type == MessageType.FOLLOWUP_RESPONSE:
            return await self._process_followup_response(session_id, message)

        # 处理 FOLLOWUP_CANCEL 消息
        if message.type == MessageType.FOLLOWUP_CANCEL:
            return await self.handle_followup_cancel(session_id, message)

        # 处理 AGENT_STOP 消息
        if message.type == MessageType.AGENT_STOP:
            return await self._process_agent_stop(session_id, message)

        # TASK_NODE_STOP 已迁入 TaskNodeControlHandler(P1b ⑩)

        # 处理 USER_MESSAGE 消息
        session_data = await self.get_session(session_id)
        if not session_data:
            # Auto-recover: session expired (cleanup) but WebSocket connection is still active.
            # Recreate the session so the user can continue without manual reconnection.
            logger.warning(f"会话已过期，尝试自动恢复: {session_id}")

            ws_workspace_id = None
            conversation_id = getattr(message, "conversation_id", None)

            # Try to get workspace_id from WebSocket connection info
            if self.websocket_manager:
                conn_info = await self.websocket_manager.get_connection_info(session_id)
                if conn_info:
                    ws_workspace_id = getattr(conn_info, "workspace_id", None)

            # Fallback: extract from message metadata (set by frontend)
            if not ws_workspace_id:
                msg_meta = getattr(message, "metadata", None)
                if isinstance(msg_meta, dict):
                    ws_workspace_id = msg_meta.get("workspaceId") or msg_meta.get("workspace_id")

            try:
                session_data = await self.session_manager.create_session(
                    session_id=session_id,
                    workspace_id=ws_workspace_id,
                    conversation_id=conversation_id,
                )
                logger.info(
                    f"会话已自动恢复: {session_id}, workspace_id={ws_workspace_id}",
                )
            except Exception as e:
                logger.error(f"会话自动恢复失败: {session_id}, error={e}")
                return await self.send_error_message(
                    session_id,
                    "SESSION_NOT_FOUND",
                    "会话不存在且自动恢复失败，请重新连接",
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
            timeout=self._resolve_task_timeout(),
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
        session_id: str | None = None,
    ) -> tuple[str, str, UserWorkspace]:
        """获取和验证工作区

        Args:
            user_message: 用户消息
            session_id: WS 会话 ID（用于在 initialize() 前注入真实 user_id）

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

        # 1.1 注入真实 user_id —— 必须在 initialize() 之前：WorkspaceContext 按
        # (path, user_id) 分键，MCP/relay stub、SecurityManager 等账户隔离资源
        # 全部跟随 context 键。事后注入只改 _user_id 不换 context，会造成
        # 「壳按真实账号注册、引擎按 default_user 取面」的拆分（2026-09-18
        # paper-search 回归根因）。Web 部署会话必带 JWT user；无身份仅剩
        # 本地桌面单机场景（保持 UserWorkspace 自身缺省）。
        if session_id:
            try:
                _sess = await self.get_session(session_id)
                _uid = getattr(_sess, "user_id", None) if _sess else None
                if _uid:
                    user_workspace.user_id = _uid
            except Exception as uid_err:
                logger.warning(f"[CHAT_HANDLER] 读取会话 user_id 失败, 工作区将以本地缺省身份初始化: {uid_err}")

        # 确保工作区已初始化，这样 tool_manager 就不会为 None
        if not user_workspace.is_initialized():
            await user_workspace.initialize()

        # P1: 沙箱预热 — 在 Agent 创建之前主动创建沙箱, 消除首次 execute_command 的冷启动。
        # 失败不阻塞会话: SandboxFacade 内部已吞异常, 这里再加一层防御, 严格 FAST FAIL。
        try:
            import asyncio as _asyncio

            from dawei.core.security_manager import current_user_id
            from dawei.sandbox.base import from_user_workspace
            from dawei.sandbox.sandbox_facade import SandboxFacade

            # user_id 取当前会话用户 (旧硬编码 "local" → provider 恒缺省 ro)
            prewarm_ctx = from_user_workspace(current_user_id(), workspace_path)
            # 【2026-09-14 事件循环阻塞修复】prewarm_session 是同步重 IO(建沙箱+pip 装依赖),
            # 直接调用会阻塞整个事件循环(实测沙箱 pip 网络挂起时阻塞 180s, 期间所有 WS 会话
            # 无响应被 nginx 切断)。改为线程池执行 + 45s 有界等待, 超时/失败均降级为 lazy 创建。
            await _asyncio.wait_for(
                _asyncio.to_thread(SandboxFacade.prewarm_session, prewarm_ctx),
                timeout=45,
            )
        except Exception as prewarm_err:
            # 注意: chat.py 的 logger 是 AgenticLogger, 不支持 %-args, 必须用 f-string
            logger.warning(f"[CHAT_HANDLER] 沙箱预热失败(或超时), 将在首次执行时 lazy 创建: {prewarm_err}")

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
        # 从 metadata 获取前端选择的模型（可能通过 user_ui_context 或 metadata 传入）
        requested_model = None
        if hasattr(user_message, "metadata") and isinstance(user_message.metadata, dict):
            requested_model = user_message.metadata.get("current_llm_id") or user_message.metadata.get("requestedModel")

        if hasattr(user_message, "user_ui_context") and user_message.user_ui_context:
            from dawei.entity.system_info import UserUIContext

            ui_context_data = user_message.user_ui_context

            try:
                # 创建UserUIContext对象
                new_ui_context = UserUIContext.from_dict(ui_context_data)

                # P0-1 模式保持：前端 payload 不带 current_mode 时保留已持久化的
                # 模式 —— 下方整体替换曾把 current_mode 擦成 None，自定义编排模式
                # 的 roleDefinition 随之失效（E2E 2026-09-18：bare LLM 兜底乱选派发模式）
                if not new_ui_context.current_mode:
                    _prev_mode = getattr(
                        getattr(user_workspace.workspace_info, "user_ui_context", None),
                        "current_mode",
                        None,
                    )
                    if _prev_mode:
                        new_ui_context.current_mode = _prev_mode

                # 如果 metadata 有模型信息但 user_ui_context 没有，补充进去
                if requested_model and not new_ui_context.current_llm_id:
                    new_ui_context.current_llm_id = requested_model

                # mode-工具解耦 §4.3：持久化收口 —— current_mode/current_experts
                # 必须是已注册 slug，未知值报错回前端、绝不落盘。
                # 历史事故（conv d1eae353 2026-09-19）：前端别名 expert_id 原样
                # 写入 workspace.json → 下游静默合成 mode → tools=[] → 模型裸吐 DSML。
                from dawei.mode.registry import get_registry

                _registry = get_registry(str(user_workspace.workspace_path))
                _unknown = []
                if new_ui_context.current_mode and not _registry.is_valid(new_ui_context.current_mode):
                    _unknown.append(new_ui_context.current_mode)
                for _expert in new_ui_context.current_experts or []:
                    if _expert and not _registry.is_valid(_expert):
                        _unknown.append(_expert)
                if _unknown:
                    _available = sorted(m.slug for m in _registry.all())
                    raise ValueError(
                        f"Unknown mode slug(s): {sorted(set(_unknown))} (available: {_available[:30]}"
                        f"{'...' if len(_available) > 30 else ''})"
                    )

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
        elif requested_model:
            # 没有 user_ui_context 但 metadata 有模型选择
            from dawei.entity.system_info import UserUIContext

            try:
                # P0-1 模式保持：无 ui_context 的 payload 只更新模型，
                # current_mode 保留既有值（此前整体替换会擦成 None）
                _ctx_data = {"current_llm_id": requested_model}
                _prev_mode = getattr(
                    getattr(user_workspace.workspace_info, "user_ui_context", None),
                    "current_mode",
                    None,
                )
                if _prev_mode:
                    _ctx_data["current_mode"] = _prev_mode
                new_ui_context = UserUIContext.from_dict(_ctx_data)
                user_workspace.workspace_info.user_ui_context = new_ui_context
                logger.info(f"[CHAT_HANDLER] Set current_llm_id from metadata: {requested_model}")
            except Exception as e:
                logger.warning(f"[CHAT_HANDLER] Failed to create UI context from metadata model: {e}")

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
        conversation_id = user_message.metadata.get("conversationId") or getattr(user_message, "conversation_id", None)
        if not conversation_id:
            if user_workspace.current_conversation:
                return

            from dawei.conversation.conversation import Conversation

            # P0-1：新建会话显式带 agent_mode（经 workspace.mode 兜底解析），
            # 不再落 None（E2E 2026-09-18：agent_mode=None 导致编排模式未激活）
            user_workspace.current_conversation = Conversation(
                agent_mode=user_workspace.mode or "orchestrator",
            )
            logger.info(f"[CHAT_HANDLER] Created new conversation with ID: {user_workspace.current_conversation.id}")
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
                # 会话在磁盘上找不到 — 使用前端传来的 conversation_id 创建新会话
                from dawei.conversation.conversation import Conversation

                # 如果前端已经指定了 conversation_id (例如 task 页面的 task.id)，
                # 则使用该 ID 创建新会话，确保前后端 conversation_id 一致
                logger.info(
                    f"[CHAT_HANDLER] Conversation {conversation_id} not found on disk, "
                    f"creating new conversation with specified ID",
                )
                user_workspace.current_conversation = Conversation(
                    id=conversation_id,
                    agent_mode=user_workspace.mode or "orchestrator",  # P0-1：不落 None
                )

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
        # 【2026-09-14 串台修复】PDCA 阶段 mode 仅在用户当前明确处于 pdca 编排模式时生效。
        # 此前无条件覆盖: 用户切到 social/research 等业务模式后, 只要 PDCA 扩展
        # 还挂着 current_cycle, 每轮仍被拉回 plan/do/check/act (业务模式被劫持)。
        _ui_ctx = user_workspace.workspace_info.user_ui_context if user_workspace.workspace_info else None
        _user_mode = getattr(_ui_ctx, "current_mode", None) if _ui_ctx else None
        if (
            pdca_extension
            and pdca_extension.pdca_enabled
            and pdca_extension.current_cycle
            and _user_mode == "pdca"
        ):
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
            # 【2026-09-14 await 修复】start_pdca_cycle 是 async（返回协程），此前未 await，
            # pdca_cycle 变成 coroutine 对象 → 下游取 cycle_id 抛 AttributeError。
            pdca_cycle = await pdca_extension.start_pdca_cycle(
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

    async def _send_pdca_cycle_start_message(self, session_id: str, task_id: str, pdca_cycle):
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

    async def _send_pdca_status_update_message(self, session_id: str, task_id: str, pdca_extension):
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
            # Collect degraded features from agent for user notification
            degraded = {}
            if getattr(agent, "memory_degraded", False):
                degraded["memory"] = {
                    "reason": "Memory system failed to initialize",
                    "impact": "跨会话上下文可能丢失",
                }
            if hasattr(agent, "_degraded_features"):
                for k, v in agent._degraded_features.items():
                    if k not in degraded:
                        degraded[k] = v

            trace_id = getattr(agent, "_trace_id", None)

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
                degraded_features=degraded if degraded else None,
                trace_id=trace_id,
            )
            await self.send_message(session_id, agent_start_message)
            logger.info(f"[CHAT_HANDLER] ✅ Sent AGENT_START message: mode={agent_mode}")
        except (OSError, ConnectionError, WebSocketError) as e:
            logger.error(f"[CHAT_HANDLER] Failed to send agent start message: {e}", exc_info=True)
            raise

    async def _send_agent_span(
        self,
        session_id: str,
        task_id: str,
        span_name: str,
        phase: str | None = None,
        status: str = "running",
        parent_span_id: str | None = None,
        trace_id: str | None = None,
        input_summary: str | None = None,
        output_summary: str | None = None,
        duration_ms: int | None = None,
        metadata: Dict[str, Any] | None = None,
    ):
        """Send an AgentSpanMessage for execution tracing.

        Args:
            session_id: WebSocket session ID
            task_id: Backend task ID
            span_name: Span name (plan/do/check/act/llm_call/tool_call)
            phase: PDCA phase this span belongs to
            status: Span status (running/success/error)
            parent_span_id: Parent span ID for tree building
            trace_id: Trace ID (from agent._trace_id)
            input_summary: Brief input description
            output_summary: Brief output description
            duration_ms: Duration in milliseconds (for completed spans)
            metadata: Extra metadata
        """
        import uuid as uuid_mod
        from datetime import datetime as dt, timezone as tz

        span_id = str(uuid_mod.uuid4())
        start_time = dt.now(tz.utc).isoformat()
        if status != "running":
            start_time = (dt.now(tz.utc).isoformat())

        # Resolve workspace_id for frontend routing: 优先注册表 ID(self._task_workspace_map,
        # 与前端 workspaceId 同源)。UserWorkspace.uuid 是每实例随机值,直接用作 WS 消息
        # 键会导致 span 落入前端永远读不到的桶(2026-09-18 修复:execution trace 区空)。
        _agent_ref = self._active_agents.get(task_id)
        _ws_id = self._task_workspace_map.get(task_id)
        if not _ws_id and _agent_ref and hasattr(_agent_ref, "user_workspace"):
            _info = getattr(_agent_ref.user_workspace, "workspace_info", None)
            _ws_id = str(getattr(_info, "id", None) or None)

        span_msg = AgentSpanMessage(
            session_id=session_id,
            workspace_id=_ws_id,
            task_node_id=task_id,
            trace_id=trace_id or "unknown",
            span_id=span_id,
            parent_span_id=parent_span_id,
            span_name=span_name,
            phase=phase,
            start_time=start_time,
            end_time=start_time if status != "running" else None,
            duration_ms=duration_ms,
            status=status,
            input_summary=input_summary,
            output_summary=output_summary,
            metadata=metadata,
        )
        try:
            await self.send_message(session_id, span_msg)
        except Exception as e:
            logger.debug(f"[CHAT_HANDLER] Failed to send agent_span: {e}")

        # ── Phase 3: Persist span to SpanStore ──
        try:
            from dawei.agentic.span_store import get_span_store

            agent = self._active_agents.get(task_id)
            workspace_path = None
            conversation_id = None
            workspace_id = None
            if agent and hasattr(agent, "user_workspace"):
                workspace_path = str(agent.user_workspace.absolute_path)
                # 与 WS 消息同一稳定 ID(_task_workspace_map 注册表 ID),
                # 不再用每实例随机的 user_workspace.uuid。
                workspace_id = _ws_id
                if agent.user_workspace.current_conversation:
                    conversation_id = agent.user_workspace.current_conversation.id

            if workspace_path:
                store = get_span_store(workspace_path)
                await store.persist_span(
                    trace_id=trace_id or "unknown",
                    span_id=span_id,
                    span_name=span_name,
                    status=status,
                    parent_span_id=parent_span_id,
                    phase=phase,
                    start_time=start_time,
                    end_time=start_time if status != "running" else None,
                    duration_ms=duration_ms,
                    input_summary=input_summary,
                    output_summary=output_summary,
                    metadata=metadata,
                    conversation_id=conversation_id,
                    task_id=task_id,
                    workspace_id=workspace_id,
                )
        except Exception as persist_err:
            logger.debug(f"[CHAT_HANDLER] SpanStore persist failed (non-fatal): {persist_err}")

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

                # ── Send PDCA phase trace span ──
                agent_ref = self._active_agents.get(task_id)
                agent_trace_id = getattr(agent_ref, "_trace_id", None) if agent_ref else None
                await self._send_agent_span(
                    session_id=session_id,
                    task_id=task_id,
                    span_name=current_phase,
                    phase=current_phase,
                    status="success",
                    trace_id=agent_trace_id,
                    output_summary=f"Advanced to {next_phase}",
                )

                # 更新PDCA循环状态
                # 【2026-09-14 await 修复】advance_pdca_phase 是 async，此前未 await。
                result_content = f"Completed {current_phase} phase"
                phase_result = await pdca_extension.advance_pdca_phase(
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
        task_id: str,
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
        task_id: str,
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
        auth_token: str | None = None,
    ) -> None:
        """配置 LLM Provider

        Args:
            session_id: 会话ID
            task_id: 任务ID
            agent: Agent 实例
            user_workspace: 用户工作区
            auth_token: 用户 JWT token，用于 gateway 认证

        """
        # 从 user_ui_context 获取用户选择的 LLM 并设置到 LLMProvider
        if not (user_workspace.workspace_info.user_ui_context and user_workspace.workspace_info.user_ui_context.current_llm_id):
            logger.info("[CHAT_HANDLER] No current_llm_id in user_ui_context, using default LLM")
            return

        ui_ctx = user_workspace.workspace_info.user_ui_context
        current_llm_id = ui_ctx.current_llm_id
        current_llm_source = ui_ctx.current_llm_source
        current_config_name = ui_ctx.current_config_name

        # 按 UI 明确选择的来源路由，不靠 model id 猜测本地 vs 官方：
        # - local: 用 provider 配置名精确命中本地 provider（直连用户自配 Key）
        # - official/其他: 用 model id，由 set_current_config 走官方网关
        if current_llm_source == "local" and current_config_name:
            target_config = current_config_name
            logger.info(f"[CHAT_HANDLER] Routing to LOCAL provider '{target_config}' (model={current_llm_id})")
        else:
            target_config = current_llm_id
            logger.info(f"[CHAT_HANDLER] Routing to OFFICIAL gateway model '{target_config}'")

        # 获取 LLMProvider 并设置当前配置
        llm_provider = agent.execution_engine._llm_service
        if not hasattr(llm_provider, "set_current_config"):
            logger.warning(
                "[CHAT_HANDLER] ⚠️  LLMProvider does not have set_current_config method",
            )
            return

        # 设置 gateway 认证 token（在 set_current_config 之前，因为 _register_gateway_config 需要用到）
        if auth_token and hasattr(llm_provider, "set_gateway_token"):
            llm_provider.set_gateway_token(auth_token)
            logger.info("[CHAT_HANDLER] Set gateway auth token for LLM provider")

        # 先列出所有可用的配置
        available_configs = llm_provider.get_config_names() if hasattr(llm_provider, "get_config_names") else []
        logger.info(f"[CHAT_HANDLER] Available LLM configs: {available_configs}")

        try:
            success = llm_provider.set_current_config(target_config)
            if not success:
                logger.warning(f"[CHAT_HANDLER] ⚠️  Failed to set LLM config to: {target_config}")
                logger.warning(
                    f"[CHAT_HANDLER] ⚠️  Config not found. Available configs: {available_configs}",
                )

                # 发送错误消息给前端
                llm_conv_id = None
                if user_workspace and user_workspace.current_conversation:
                    llm_conv_id = user_workspace.current_conversation.id
                error_message = ErrorMessage(
                    session_id=session_id,
                    code="LLM_CONFIG_NOT_FOUND",
                    message=f"您选择的 LLM 配置 '{target_config}' 不可用。系统将使用默认配置 '{available_configs[0] if available_configs else 'N/A'}' 继续执行。",
                    recoverable=False,
                    details={
                        "task_id": task_id,
                        "requested_config": target_config,
                        "available_configs": available_configs,
                        "fallback_config": available_configs[0] if available_configs else None,
                    },
                    conversation_id=llm_conv_id,
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
        original_ws_message: WebSocketMessage = None,  # 🔧 新增：接收原始 WebSocket 消息
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

        # 【调试】打印 user_message 的所有属性
        logger.info(f"[CHAT_HANDLER] user_message type: {type(user_message)}")
        logger.info(f"[CHAT_HANDLER] user_message attributes: {dir(user_message)}")
        if hasattr(user_message, "__dict__"):
            logger.info(f"[CHAT_HANDLER] user_message.__dict__: {user_message.__dict__}")

        # 检查消息中是否包含@文件引用
        if "@" in original_message:
            from dawei.websocket.handlers.at_message_processor import AtMessageProcessor

            # 仅提取文件引用（不读取内容）
            file_refs = AtMessageProcessor.extract_file_references(original_message)

            if file_refs:
                logger.info(f"[CHAT_HANDLER] Detected {len(file_refs)} @ file references (will be processed by Agent)")

        # Extract knowledge_base_ids and pass to UserInputMessage
        metadata = {}
        if hasattr(user_message, "metadata") and user_message.metadata:
            metadata = dict(user_message.metadata)

        # Extract knowledge_base_ids from WebSocket message
        knowledge_base_ids = None
        if original_ws_message and hasattr(original_ws_message, "knowledge_base_ids"):
            if original_ws_message.knowledge_base_ids:
                knowledge_base_ids = original_ws_message.knowledge_base_ids
                metadata["knowledge_base_ids"] = knowledge_base_ids
                logger.debug(f"Knowledge base IDs extracted from WebSocket message: {knowledge_base_ids}")

        # Return original message with metadata (do not modify user content)
        return UserInputMessage(text=original_message, metadata=metadata if metadata else None)

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
        finally:
            # MarketingAgent 编队可观测性(E1 徽标):任务结束(成功/失败)→ 活跃子智能体
            # 归位 idle;非 market 工作区为 no-op(失败仅告警,不影响对话)。
            try:
                from dawei.websocket.market_fleet import mark_workspace_idle

                ws = getattr(agent, "user_workspace", None)
                await mark_workspace_idle(getattr(ws, "workspace_id", "") or "")
            except Exception as e:  # noqa: BLE001
                logger.debug(f"[CHAT_HANDLER] market fleet idle broadcast failed: {e}")

            # SocialAgent 编队可观测性(E1 徽标,镜像 market):任务结束 → 活跃
            # 子智能体归位 idle;非 social 工作区为 no-op(失败仅告警,不影响对话)。
            try:
                from dawei.websocket.social_fleet import mark_social_workspace_idle

                ws = getattr(agent, "user_workspace", None)
                await mark_social_workspace_idle(getattr(ws, "workspace_id", "") or "")
            except Exception as e:  # noqa: BLE001
                logger.debug(f"[CHAT_HANDLER] social fleet idle broadcast failed: {e}")

            # GeluResearch 编队可观测性(E1 徽标,镜像 social):任务结束 → 活跃
            # 子智能体归位 idle;非 research 工作区为 no-op(失败仅告警,不影响对话)。
            try:
                from dawei.websocket.research_fleet import mark_research_workspace_idle

                ws = getattr(agent, "user_workspace", None)
                await mark_research_workspace_idle(getattr(ws, "workspace_id", "") or "")
            except Exception as e:  # noqa: BLE001
                logger.debug(f"[CHAT_HANDLER] research fleet idle broadcast failed: {e}")

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

        # 【修复】如果错误已经由内层（task_node_executor._send_error_to_frontend）处理并发送到前端，
        # 则跳本次 _handle_agent_error，避免用户看到重复错误消息。
        # 内层通过 EventBus ERROR_OCCURRED 事件已经发送了详细的错误信息（rate_limit_exceeded /
        # llm_api_error / timeout 等），这些事件被 event_handler 转发到前端 WebSocket。
        # 此处是 _execute_agent_task 的顶层 except，会捕获从 agent.process_message() 冒泡上来的
        # TaskExecutionError，如果不拦截，会再发一条重复错误。
        _already_handled_patterns = (
            "429", "rate_limit", "Rate limit",
            "Provider error", "llm_api_error", "LLM error from",
            "missing field", "invalid_request_error",
        )
        if any(p in error_str for p in _already_handled_patterns):
            logger.info(
                f"[CHAT_HANDLER] Skipping _handle_agent_error for already-handled error: {error_str[:200]}"
            )
            # 仍然需要发送 STREAM_COMPLETE 以终止前端流式状态
            from dawei.websocket.protocol import StreamCompleteMessage

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
            logger.info(
                "[CHAT_HANDLER] ✅ Sent STREAM_COMPLETE after already-handled error (skipped duplicate error message)",
            )
            return

        user_friendly_message = error_str
        error_code = "AGENT_EXECUTION_ERROR"
        error_category = "unknown"  # frontend 用: auth | credits | rate_limit | server | network | unknown
        recoverable = False

        # 如果是StateTransitionError,需要从traceback中提取原始错误
        if "StateTransitionError" in error_str:
            logger.info(
                "[CHAT_HANDLER] Detected StateTransitionError, checking traceback for original error...",
            )
            user_friendly_message = self._extract_llm_error_message(error_str, error)
            # 递归检查提取后的消息是否包含 gateway 错误
            error_str = user_friendly_message

        # ── Gateway / 认证错误 (HTTP 401) ──
        if "HTTP 401" in error_str or "Invalid token" in error_str or "Unauthorized" in error_str:
            error_code = "AUTH_ERROR"
            error_category = "auth"
            user_friendly_message = "认证失败：登录已过期或无效，请重新登录后再试。"
            recoverable = True

        # ── 积分不足 (HTTP 402) ──
        elif "HTTP 402" in error_str or "Insufficient credits" in error_str or "insufficient credits" in error_str.lower():
            error_code = "INSUFFICIENT_CREDITS"
            error_category = "credits"
            # 从错误信息中提取需要的积分和当前余额
            import re
            required_match = re.search(r"Required:\s*~?([\d.]+)", error_str)
            available_match = re.search(r"Available:\s*([\d.]+)", error_str)
            if required_match and available_match:
                user_friendly_message = f"积分不足：本次请求约需 {required_match.group(1)} 积分，当前余额 {available_match.group(1)} 积分。请联系管理员充值。"
            else:
                user_friendly_message = "积分不足，无法完成请求。请联系管理员充值后重试。"
            recoverable = True

        # ── 余额/配额不足(必须先于 429 判定:zai code 1113「余额不足」与 OpenAI
        # insufficient_quota 都以 HTTP 429 下发,重试不可能成功,fast-fail) ──
        elif any(kw in error_str for kw in ("余额不足", "请充值", "无可用资源包", "insufficient balance", "insufficient_balance", "insufficient_quota")):
            error_code = "INSUFFICIENT_BALANCE"
            error_category = "credits"
            user_friendly_message = "API 账户余额不足，请联系管理员充值。"
            recoverable = True

        # ── 请求频率限制 (HTTP 429, 真限流) ──
        elif "HTTP 429" in error_str or "Rate limit" in error_str or "rate limit" in error_str.lower():
            error_code = "RATE_LIMITED"
            error_category = "rate_limit"
            user_friendly_message = "请求过于频繁，请稍等片刻后再试。"
            recoverable = True

        # ── 模型未找到 (HTTP 404) ──
        elif "HTTP 404" in error_str or "Model not found" in error_str:
            error_code = "MODEL_NOT_FOUND"
            error_category = "server"
            user_friendly_message = "当前选择的模型不可用，请切换到其他模型后重试。"
            recoverable = True

        # ── 服务器错误 (HTTP 5xx 或 网关 SSE "Provider error (50x)") ──
        elif ("HTTP 500" in error_str or "HTTP 502" in error_str or "HTTP 503" in error_str or "HTTP 504" in error_str
              or "Provider error (502)" in error_str or "Provider error (500)" in error_str
              or "Provider error (503)" in error_str or "Provider error (504)" in error_str):
            error_code = "SERVER_ERROR"
            error_category = "server"
            user_friendly_message = "AI 服务暂时不可用，请稍后重试。如果问题持续，请联系管理员。"
            recoverable = True

        # ── 网络连接错误 ──
        # 排除 "Cannot connect to provider" —— 那是网关到上游 provider 的错误（已归类为 SERVER_ERROR），
        # 不是用户本地网络问题。
        elif ("ConnectionError" in error_str or "ConnectError" in error_str
              or "Connection refused" in error_str
              or ("Cannot connect" in error_str and "provider" not in error_str.lower())):
            error_code = "NETWORK_ERROR"
            error_category = "network"
            user_friendly_message = "网络连接失败，请检查网络后重试。"
            recoverable = True

        # ── 请求超时 ──
        elif "TimeoutError" in error_str or "timeout" in error_str.lower() or "timed out" in error_str.lower():
            error_code = "TIMEOUT_ERROR"
            error_category = "network"
            user_friendly_message = "请求超时，AI 服务响应时间过长。请稍后重试。"
            recoverable = True

        # ── 通用 LLM 错误 ──
        elif "LLM error" in error_str:
            error_code = "LLM_ERROR"
            error_category = "server"
            user_friendly_message = f"AI 模型调用失败，请稍后重试。({error_str[:100]})"

        # 获取 workspace_id for proper routing
        workspace_id = None
        try:
            if agent and hasattr(agent, "user_workspace") and hasattr(agent.user_workspace, "workspace_info"):
                workspace_id = agent.user_workspace.workspace_info.id
        except Exception as ws_id_error:
            logger.warning(f"[CHAT_HANDLER] Failed to get workspace_id for error: {ws_id_error}")

        # 获取 conversation_id 以便前端能路由到正确的对话
        error_conv_id = None
        if _user_workspace and _user_workspace.current_conversation:
            error_conv_id = _user_workspace.current_conversation.id

        # 发送错误消息到前端
        error_message = ErrorMessage(
            session_id=session_id,
            code=error_code,
            message=user_friendly_message,
            recoverable=recoverable,
            details={
                "task_id": task_id,
                "error_category": error_category,
                "original_error": error_str,
                "error_type": type(error).__name__,
            },
            conversation_id=error_conv_id,
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

        # 清理工作区稳定键映射(与 _task_to_session_map 同生命周期)
        self._task_workspace_map.pop(task_id, None)

        logger.info(f"[CHAT_HANDLER] Skipping agent.cleanup() to avoid disrupting active handlers. Agent {task_id} will be garbage collected naturally.")

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
        handler_ids = task_info.get("handler_ids", {})
        saved_event_bus_id = task_info.get("event_bus_id")
        saved_event_bus = task_info.get("event_bus")

        logger.info(
            f"[EVENT_HANDLER] 🧹 Cleaning up {len(handler_ids)} event handlers for task {task_id}",
        )

        # 获取事件总线
        event_bus = saved_event_bus

        # 验证：如果保存的 event_bus 和当前 agent 的 event_bus 不同，记录警告
        if agent and hasattr(agent, "event_bus"):
            current_event_bus_id = id(agent.event_bus)
            if current_event_bus_id != saved_event_bus_id:
                logger.error(
                    f"[EVENT_HANDLER] ❌ CRITICAL: Event bus mismatch!\n  - Saved event_bus_id: {saved_event_bus_id}\n  - Current agent event_bus_id: {current_event_bus_id}\n  - This means the agent was recreated or replaced!\n  - Using saved event_bus reference for cleanup.",
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
            f"[EVENT_HANDLER] ✅ Cleanup complete for task {task_id}: removed {removed_count}, already removed {already_removed_count}/{len(handler_ids)} handlers. Remaining active handlers: {len(self._task_event_handler_ids)}",
        )

    # ==================== 重构后的主执行方法 ====================

    async def _steer_running_subtasks(
        self,
        user_input: UserInputMessage,
        exclude_task_id: str,
        target_subtask_id: str | None = None,
    ) -> int:
        """F7 steering：用户消息镜像注入运行中子任务的隔离会话。

        定位方式：遍历 self._active_agents（历史轮 agent 存活至
        _cleanup_agent_task）取 agent.execution_engine —— 注意不能用
        user_workspace.execution_engine（每个新轮次的引擎都会覆盖该指针），
        而 agent.execution_engine 属性不被覆盖；新轮引擎 _node_executors
        为空，天然只命中仍在执行旧轮子任务的 executor。

        仅覆盖 P2-7 隔离会话（conv.task_type=="subtask"）且节点未终结的
        子任务；共享对话路径零影响（子任务本就与主对话同流）。注入文本带
        [steer] 前缀，与 message_task 工具同契约，子任务下一轮 LLM 即见。
        主对话仍照常处理本消息 —— steer 是叠加而非改道。

        P3 定向路由：target_subtask_id 非空时只注入该节点（不广播）；
        目标不在可注入集合（不存在/已终结/共享会话）→ 记 warning 返回 0，
        主对话不受影响（FAST FAIL 可观测）。

        注入安全（方案 §7.2）：文本先过 injection_guard.sanitize_output
        中和伪造系统标签（与报告回注同标准），命中即记日志。

        Args:
            user_input: 本轮用户输入（取 .text）
            exclude_task_id: 当前轮任务 ID（跳过自身）
            target_subtask_id: 定向插话目标子任务节点 ID；None = 广播

        Returns:
            注入的子任务数（0 = 无运行中隔离子任务，零开销）
        """
        text = (getattr(user_input, "text", "") or "").strip()
        if not text:
            return 0

        from dawei.agentic.injection_guard import sanitize_output

        safe_text = sanitize_output(text)
        if safe_text != text:
            logger.warning(
                "[CHAT_HANDLER] F7 steer: sanitized forged system tags in user steer text",
            )
            text = safe_text

        from dawei.entity.lm_messages import UserMessage

        _TERMINAL = (
            GraphTaskStatus.COMPLETED,
            GraphTaskStatus.FAILED,
            GraphTaskStatus.ABORTED,
            GraphTaskStatus.CANCELLED,
        )
        # 先收集可注入集合（隔离会话 + 节点未终结），再按定向/广播选择目标
        injectable = []  # [(node_id, conv, node)]
        for tid, agent in list(self._active_agents.items()):
            if tid == exclude_task_id:
                continue
            engine = getattr(agent, "execution_engine", None)
            for node_id, executor in list(getattr(engine, "_node_executors", {}).items()):
                conv = getattr(executor, "_conversation", None)
                # 仅隔离会话（共享对话子任务与主对话同流，无需镜像）
                if conv is None or getattr(conv, "task_type", None) != "subtask":
                    continue
                node = getattr(executor, "task_node", None)
                if getattr(node, "status", None) in _TERMINAL:
                    continue  # 已终结子任务不会再有下一轮 LLM
                injectable.append((node_id, conv, node))

        if target_subtask_id is not None:
            picked = [item for item in injectable if item[0] == target_subtask_id]
            if not picked:
                logger.warning(
                    f"[CHAT_HANDLER] F7 steer: target subtask {target_subtask_id} not steerable "
                    f"(not found / terminal / shared conversation); "
                    f"injectable={[nid for nid, _, _ in injectable]}",
                )
                return 0
        else:
            picked = injectable

        steered = 0
        for node_id, conv, node in picked:
            try:
                conv.say(UserMessage(content=f"[steer] {text}"))
                steered += 1
                logger.info(
                    f"[CHAT_HANDLER] F7 steer: injected user message into subtask {node_id} (conversation {conv.id})",
                )
                # P3-6: steered 生命周期事件（fire-and-forget，前端经 WS 可观测）
                from dawei.agentic.subtask_events import emit_subtask_lifecycle

                await emit_subtask_lifecycle(
                    "steered",
                    task_node_id=node_id,
                    parent_id=getattr(node, "parent_id", None),
                    conversation_id=conv.id,
                    status="running",
                    extra={"by": "user", "preview": text[:100]},
                )
            except Exception:  # noqa: BLE001 — 单个子任务注入失败不影响其余
                logger.warning(f"[CHAT_HANDLER] F7 steer failed for subtask {node_id}", exc_info=True)
        if steered:
            logger.info(f"[CHAT_HANDLER] F7 steer: mirrored user message to {steered} running subtask(s)")
        return steered

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
            # 1. 获取和验证工作区（session user_id 在 initialize() 前注入，
            # 见 _get_and_validate_workspace 1.1 —— 事后注入不再需要）
            (
                workspace_id,
                workspace_path,
                user_workspace,
            ) = await self._get_and_validate_workspace(
                user_message,
                session_id=session_id,
            )

            # 1.5. 存储 workspace_id 到 session，供 reset_conversation 等消息使用
            await self.update_session_data(
                session_id,
                data={"last_workspace_id": workspace_id},
            )

            # 1.6. 记录注册表工作区 ID(稳定键):agent_span 的 WS 消息与
            # SpanStore 持久化列用它与前端 workspaceId 对齐(见 _send_agent_span)。
            self._task_workspace_map[task_id] = workspace_id

            # 2. 更新用户UI上下文
            await self._update_user_ui_context(user_workspace, user_message)

            # 3. 加载或创建会话
            await self._load_or_create_conversation(user_workspace, user_message)

            # 3.1. 记录 conversation_id 映射，用于错误消息路由
            if user_workspace.current_conversation:
                self._task_to_conv_id_map[task_id] = user_workspace.current_conversation.id

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

            # 4.1. 尝试恢复降级的记忆系统（Phase 3: auto-retry）
            await agent.retry_memory_init()

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

            # NOTE: 专家配置已移至 prompt builder — current_experts 通过 user_ui_context
            # 传递到 llm_message_builder._prepare_context()，自动注入 system prompt。

            # 6. 发送 Agent 启动消息
            await self._send_agent_start_message(
                session_id,
                task_id,
                agent,
                workspace_id,
                user_message,
            )

            # 7. 配置 LLM Provider（传递 gateway 认证 token）
            auth_token = None
            if hasattr(user_message, "metadata") and isinstance(user_message.metadata, dict):
                auth_token = user_message.metadata.get("auth_token")
            # 多租户业务工具（kb-searcher / sanctions）按当前用户 JWT 调内部服务。
            # 写入 local_context，工具运行时以 Bearer 透明注入，永不进 LLM 上下文。
            local_context.set_auth_token(auth_token)
            # 社媒编辑会话上下文(A-M1,设计 A.3):前端 data.social_context{content_id, tenant_id}
            # 与 auth_token 同通路 —— 工具经 ContextVar 读取,不进 LLM 上下文、不落盘。
            from dawei.social import session_context as _social_session_ctx

            _social_ctx_raw = None
            if isinstance(user_message.metadata, dict):
                _fd = user_message.metadata.get("frontend_data")
                if isinstance(_fd, dict):
                    _social_ctx_raw = _fd.get("social_context")
                _social_ctx_raw = _social_ctx_raw or user_message.metadata.get("social_context")
            _social_session_ctx.set_social_context(_social_ctx_raw)
            # SocialAgent(social-team)兜底:模块级会话不携带 social_context,但需调
            # 模块级工具(social_lookup_trending / social_rule_check / social_generate_images)
            # → 绑定租户级上下文(content_id 留空:稿件级工具 read_draft / propose_edit /
            # validate_artifact 仍要求创作工坊编辑会话内绑定,诚实报"未关联稿件")。
            if _social_session_ctx.get_social_context() is None:
                from dawei.websocket.social_fleet import SOCIAL_TEAM_MODES as _SOCIAL_TEAM_MODES

                if getattr(agent, "current_mode", None) in _SOCIAL_TEAM_MODES:
                    _social_session_ctx.set_social_context({"tenant_id": "default"})
            await self._configure_llm_provider(session_id, task_id, agent, user_workspace, auth_token=auth_token)

            # 8. 存储 Agent 实例
            self._active_agents[task_id] = agent

            # 9. 设置事件转发
            await self._setup_event_forwarding(agent, session_id, task_id, user_workspace)

            # 10. 启动任务
            await self.update_session_data(session_id, data={"current_task_id": task_id})

            # 11. 处理文件引用（传递原始 WebSocket 消息以提取 knowledge_base_ids）
            user_input = await self._process_file_references(user_message, workspace_path, user_message)

            # 11.5. 处理 user_ui_context.action（如 summarize、analyze）
            if user_input.text:
                ui_context = user_workspace.workspace_info.user_ui_context
                action = ui_context.action if ui_context else None
                if action == "summarize":
                    user_input.text = (
                        "[系统指令] 请简要总结以上对话的关键要点和法律建议。"
                        "保持简洁，按以下结构组织：\n"
                        "1. 关键要点\n2. 法律建议\n3. 下一步行动\n\n"
                        f"[用户消息] {user_input.text}"
                    )
                    logger.info("[CHAT_HANDLER] Applied summarize action to user input")
                elif action == "analyze":
                    # analyze action: the user selected a file via upload dialog,
                    # the file path is in the message as @ref. Agent will handle it.
                    logger.info("[CHAT_HANDLER] Analyze action detected — agent will process file references")

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

            # 12.5. F7 steering：用户消息镜像注入运行中子任务的隔离会话
            # （P2-7 隔离转正后子任务不再与主对话同流，用户中途指令需显式送达；
            #   主对话仍照常处理本消息 —— steer 是叠加而非改道。
            #   P3 定向插话：WS 消息带 target_subtask_id 时只注入该节点，否则广播）
            try:
                await self._steer_running_subtasks(
                    user_input,
                    exclude_task_id=task_id,
                    target_subtask_id=getattr(user_message, "target_subtask_id", None),
                )
            except Exception:  # noqa: BLE001 — steering 失败绝不阻断主流程
                logger.warning("[CHAT_HANDLER] F7 steer running subtasks failed", exc_info=True)

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

            # 🔧 统一获取 conversation_id（消除 6 处重复逻辑，保证所有 WS 消息都带上）
            _conversation_id = None
            if user_workspace and user_workspace.current_conversation:
                _conversation_id = user_workspace.current_conversation.id
            if not _conversation_id:
                # 🔧 回退：user_workspace 是按 (path,user) 共享的可变状态，任务执行期间
                # current_conversation 可能被其他标签页切换/清空为 None —— 此时终态消息
                # （AGENT_COMPLETE 等）缺 conversation_id 会被前端按 convId 路由直接丢弃，
                # isStreaming 永不复位（生产事故 2026-09-17：停止按钮卡运行态，用户连点
                # 停止 ×10 无效）。回退到任务启动时记录的映射（_load_or_create_conversation
                # 之后写入，对本 task 权威），与 _process_agent_stop 的回退链一致。
                _conversation_id = self._task_to_conv_id_map.get(task_id)

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

                    # ── Send execution completion span ──
                    agent_ref = self._active_agents.get(task_id)
                    agent_trace_id = getattr(agent_ref, "_trace_id", None) if agent_ref else None
                    await self._send_agent_span(
                        session_id=session_id,
                        task_id=task_id,
                        span_name="execute",
                        status="success",
                        trace_id=agent_trace_id,
                        output_summary=result_content[:200] if result_content else "Task completed",
                    )

                    # 发送 AGENT_COMPLETE 消息（用于状态栏显示）
                    import time

                    # 使用默认60秒作为任务执行时间
                    total_duration_ms = 60000  # 默认60秒

                    agent_complete_message = AgentCompleteMessage(
                        session_id=session_id,
                        task_id=task_id,
                        result_summary=result_content[:200] if result_content else "任务已完成",
                        total_duration_ms=total_duration_ms,
                        tasks_completed=1,  # 可以从实际统计数据中获取
                        tools_used=[],  # 可以从实际统计数据中获取
                        conversation_id=_conversation_id,
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
                        conversation_id=_conversation_id,
                    )
                # 处理任务错误事件
                elif event_type_enum == TaskEventType.TASK_ERROR:
                    # Apply friendly categorization (e.g. gateway 401 → re-login)
                    raw_msg = event_data.error_message if hasattr(event_data, "error_message") else "未知错误"
                    cat_code, cat_msg, cat_recoverable = _categorize_llm_error(raw_msg)
                    message_to_send = ErrorMessage(
                        session_id=session_id,
                        code=(
                            cat_code
                            or (event_data.error_code if hasattr(event_data, "error_code") else "TASK_ERROR")
                        ),
                        message=cat_msg or raw_msg,
                        recoverable=(
                            cat_recoverable
                            if cat_code
                            else (event_data.recoverable if hasattr(event_data, "recoverable") else False)
                        ),
                        details={"task_id": task_id},
                        conversation_id=_conversation_id,
                    )
                # 处理错误发生事件
                elif event_type_enum == TaskEventType.ERROR_OCCURRED:
                    # event_data 是字典格式：{"error_type": ..., "message": ..., "details": {...}}
                    error_type = event_data.get("error_type", "unknown") if isinstance(event_data, dict) else "unknown"
                    error_message = event_data.get("message", "未知错误") if isinstance(event_data, dict) else "未知错误"
                    error_details = event_data.get("details", {}) if isinstance(event_data, dict) else {}

                    # 获取 conversation_id 以便前端能路由到正确的对话
                    conv_id = _conversation_id

                    # Apply friendly categorization (e.g. gateway 401 → re-login)
                    cat_code, cat_msg, cat_recoverable = _categorize_llm_error(error_message)
                    final_code = cat_code or error_type.upper()

                    logger.info(
                        f"[ERROR_TRACE] Creating ErrorMessage: error_type={error_type}, categorized={cat_code or 'none'}, error_message={error_message[:100]}..., session_id={session_id}, conversation_id={conv_id}",
                    )

                    message_to_send = ErrorMessage(
                        session_id=session_id,
                        code=final_code,
                        message=cat_msg or error_message,
                        recoverable=cat_recoverable if cat_code else False,
                        details={"task_id": task_id, **error_details},
                        conversation_id=conv_id,
                    )

                    logger.info(
                        f"[ERROR_TRACE] ErrorMessage created successfully: message_to_send={message_to_send is not None}, final_code={final_code}",
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
                        # ── llm_call trace span（补齐 _send_agent_span 文档承诺的
                        # span 类型;每轮 LLM 请求一条,与 LLMApiComplete 同源耗时）──
                        await self._send_agent_span(
                            session_id=session_id,
                            task_id=task_id,
                            span_name="llm_call",
                            status="success",
                            trace_id=getattr(agent, "_trace_id", None),
                            input_summary=f"{current_llm_provider or 'unknown'}/{current_llm_model or 'unknown'}",
                            duration_ms=duration_ms,
                        )
                        llm_api_active = False

                        # 🔧 修复：清理 LLM API 状态
                        self._task_llm_api_state.pop(task_id, None)
                # 处理完成接收事件
                elif event_type_enum == TaskEventType.COMPLETE_RECEIVED:
                    # event_data 是 CompleteMessage 对象，使用 from_stream_message 方法
                    message_to_send = StreamCompleteMessage.from_stream_message(
                        event_data,
                        session_id=session_id,
                        task_id=task_id,
                        conversation_id=_conversation_id,
                    )
                    message_to_send.user_message_id = user_message_id

                    # 如果 LLM API 还在活跃状态，发送完成消息
                    if llm_api_active:
                        import time

                        duration_ms = int((time.time() - llm_request_start_time) * 1000) if llm_request_start_time else None
                        _finish_reason = event_data.finish_reason if hasattr(event_data, "finish_reason") else None
                        llm_api_message = LLMApiCompleteMessage(
                            session_id=session_id,
                            task_id=task_id,
                            provider=current_llm_provider or "unknown",
                            model=current_llm_model or "unknown",
                            finish_reason=_finish_reason,
                            usage=event_data.usage if hasattr(event_data, "usage") else None,
                            duration_ms=duration_ms,
                        )
                        # ── llm_call trace span（同 USAGE_RECEIVED 分支;两分支谁先
                        # 触发谁发,llm_api_active 置 False 保证每轮仅一条）──
                        await self._send_agent_span(
                            session_id=session_id,
                            task_id=task_id,
                            span_name="llm_call",
                            status="error" if _finish_reason == "error" else "success",
                            trace_id=getattr(agent, "_trace_id", None),
                            input_summary=f"{current_llm_provider or 'unknown'}/{current_llm_model or 'unknown'}",
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
                        conversation_id=_conversation_id,
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
                        conversation_id=_conversation_id,
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
                                _tc_msg = StreamToolCallMessage(
                                    session_id=session_id,
                                    task_id=task_id,
                                    tool_call=tool_call,
                                    all_tool_calls=tool_calls,
                                    user_message_id=user_message_id,
                                    conversation_id=_conversation_id,
                                )
                                await self.send_message(session_id, _tc_msg)
                # 处理工具调用开始事件
                elif event_type_enum == TaskEventType.TOOL_CALL_START:
                    message_to_send = ToolCallStartMessage(
                        session_id=session_id,
                        task_id=task_id,
                        tool_name=event_data.tool_name if hasattr(event_data, "tool_name") else "",
                        tool_input=(event_data.tool_input if hasattr(event_data, "tool_input") else {}),
                        tool_call_id=getattr(event_data, "tool_call_id", None),
                        conversation_id=_conversation_id,
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
                        conversation_id=_conversation_id,
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

                    # ── tool_call trace span（事件自带 execution_time(秒)与 is_error,
                    # 就地一条终态 span,无需 START/RUNNING 配对状态）──
                    await self._send_agent_span(
                        session_id=session_id,
                        task_id=task_id,
                        span_name=f"tool:{tool_name}" if tool_name else "tool_call",
                        status="error" if is_error else "success",
                        trace_id=getattr(agent, "_trace_id", None),
                        input_summary=tool_call_id,
                        # float() 兼容数值/数字字符串,避免入参求值抛错中断后续消息发送
                        duration_ms=int(float(execution_time) * 1000) if execution_time is not None else None,
                    )

                    message_to_send = ToolCallResultMessage(
                        session_id=session_id,
                        task_id=task_id,
                        tool_name=tool_name,
                        result=result,
                        is_error=is_error,
                        tool_call_id=tool_call_id,
                        workspace_id=workspace_id,
                        conversation_id=_conversation_id,
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
                # 处理 TaskGraph 更新事件 — 即时持久化节点状态
                elif event_type_enum == TaskEventType.TASK_GRAPH_UPDATED:
                    try:
                        if user_workspace and hasattr(user_workspace, "task_graph"):
                            # 🔥 修复（2026-09-17 new_task 60s 超时事故，纵深防御）：
                            # 不再在事件 handler 内同步 await save_task_graph。
                            # save_task_graph → get_all_tasks 需要获取图谱锁；若恰逢 TaskGraph
                            # 持锁 emit 本事件，会形成循环等待（死锁）。改为后台任务调度。
                            import asyncio as _asyncio

                            _graph_snapshot = user_workspace.task_graph

                            async def _persist_graph_in_background() -> None:
                                try:
                                    await user_workspace.save_task_graph(_graph_snapshot)
                                except Exception as bg_err:
                                    logger.warning(f"[CHAT_HANDLER] Background task-graph persist failed: {bg_err}")

                            _asyncio.create_task(_persist_graph_in_background())
                            logger.debug(
                                f"[CHAT_HANDLER] TASK_GRAPH_UPDATED: scheduled background persist for node={event_data.get('updated_node_id', '?')}"
                            )
                    except Exception as persist_err:
                        logger.warning(
                            f"[CHAT_HANDLER] Failed to schedule task graph persist: {persist_err}"
                        )
                # 处理追问问题事件
                elif event_type_enum == TaskEventType.FOLLOWUP_QUESTION:
                    from dawei.websocket.protocol import FollowupQuestionMessage

                    # event_data 是字典，使用 .get() 访问
                    event_session_id = event_data.get("session_id", session_id)

                    message_to_send = FollowupQuestionMessage(
                        session_id=event_session_id,  # 使用事件数据中的 session_id
                        task_id=task_id,
                        conversation_id=event_data.get("conversation_id", ""),  # 前端按此路由到对话
                        question=event_data.get("question", ""),
                        suggestions=event_data.get("suggestions", []),
                        tool_call_id=event_data.get("tool_call_id", ""),
                        user_message_id=user_message_id,
                    )

                    logger.info(
                        f"Forwarding FOLLOWUP_QUESTION to session: {event_session_id}, question: {event_data.get('question', 'N/A')[:50]}...",
                    )
                # 处理记忆系统恢复就绪事件（Phase 3: auto-retry success）
                elif event_type_enum == TaskEventType.MEMORY_READY:
                    from dawei.websocket.protocol import AgentStatusUpdateMessage

                    retry_count = event_data.get("retry_count", 0) if isinstance(event_data, dict) else 0
                    logger.info(
                        f"[CHAT_HANDLER] Memory system recovered after {retry_count} retries, "
                        f"sending AGENT_STATUS_UPDATE with memory_ready=true to session: {session_id}"
                    )
                    message_to_send = AgentStatusUpdateMessage(
                        session_id=session_id,
                        task_id=task_id,
                        degraded_features=agent._degraded_features if hasattr(agent, "_degraded_features") else {},
                        memory_ready=True,
                        trace_id=getattr(agent, "_trace_id", None),
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
                    # 🔧 统一兜底：保证所有走统一出口的消息都带 conversation_id
                    if not getattr(message_to_send, "conversation_id", None):
                        message_to_send.conversation_id = _conversation_id

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
            TaskEventType.TASK_GRAPH_UPDATED,  # TaskGraph 节点状态变更 → 即时持久化
            TaskEventType.FOLLOWUP_QUESTION,  # 添加追问问题事件
            TaskEventType.A2UI_SURFACE_EVENT,  # 添加A2UI UI组件事件
            TaskEventType.MEMORY_READY,  # 记忆系统恢复就绪（Phase 3: auto-retry）
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
            "handler_ids": handler_ids,
            "event_bus_id": id(event_bus),
            "event_bus": event_bus,  # 保存引用，确保清理时使用同一个 event_bus
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
            task_err_conv_id = self._task_to_conv_id_map.get(task_error.task_id)
            error_message = ErrorMessage(
                session_id=session_id,
                code=task_error.error_type,
                message=task_error.error_message,
                recoverable=task_error.recoverable,
                details={"task_id": task_error.task_id},
                conversation_id=task_err_conv_id,
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
                    task_fail_conv_id = self._task_to_conv_id_map.get(task_result.task_id)
                    error_message = ErrorMessage(
                        session_id=session_id,
                        code="TASK_FAILED",
                        message=str(task_result.error),
                        recoverable=False,
                        details={"task_id": task_result.task_id},
                        conversation_id=task_fail_conv_id,
                    )
                    await self.send_message(session_id, error_message)
            finally:
                # 发送完消息后清理映射，避免内存泄漏
                if task_result.task_id in self._task_to_session_map:
                    del self._task_to_session_map[task_result.task_id]
                self._task_to_conv_id_map.pop(task_result.task_id, None)
        except Exception as e:
            logger.error(
                f"发送任务完成时出错: {e}",
                exc_info=True,
                context={"task_id": task_result.task_id, "component": "chat_handler"},
            )

    # _process_task_node_stop 已整体迁入 TaskNodeControlHandler._handle_stop(P1b ⑩)

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

        # 解析 conversation_id 供停止确认消息回填，使前端能按 convId 路由收尾。
        # 优先级：消息自带 > _task_to_conv_id_map > Agent 当前会话 > None
        conv_id = (
            getattr(message, "conversation_id", None)
            or self._task_to_conv_id_map.get(task_id)
        )
        if not conv_id:
            agent_for_conv = self._active_agents.get(task_id)
            if agent_for_conv and getattr(agent_for_conv, "user_workspace", None):
                current_conv = getattr(agent_for_conv.user_workspace, "current_conversation", None)
                if current_conv:
                    conv_id = getattr(current_conv, "id", None)

        # 🔧 修复：task_id 未命中时，按 conversation_id 反查仍在运行的 agent。
        # 前端拿不到后端 task_id 时会以 conversation_id 兜底作为 task_id 发送 stop，
        # 通过 _task_to_conv_id_map 反查同会话下活跃的任务，避免"点了停止但任务继续跑"。
        if task_id not in self._active_agents:
            message_conv_id = getattr(message, "conversation_id", None)
            if message_conv_id:
                matched_task_ids = [
                    tid
                    for tid, cid in self._task_to_conv_id_map.items()
                    if cid == message_conv_id and tid in self._active_agents
                ]
                if matched_task_ids:
                    # dict 保持插入顺序，取最近一次启动的任务
                    task_id = matched_task_ids[-1]
                    logger.info(
                        f"AGENT_STOP: resolved active task {task_id} via conversation_id {message_conv_id}"
                    )

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
                conversation_id=conv_id,
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

            # 🔧 修复：不再在此处 del _active_agents。agent.stop() 是协作式停止
            # （仅置标志/取消子任务/标记节点 ABORTED），根协程可能仍在收尾
            # （生产事故 2026-09-18 08:28：stop 返回 2ms 后仍有一次 8s 的 LLM
            # 流式调用在跑）。提前注销会让后续 agent_stop 全部落入"任务已经
            # 结束"空转分支，用户无法再次停止真正的残留工作。注销统一由自然
            # 完成路径的 finally 块负责；重复 stop 幂等（engine.stop() 空集合
            # 遍历为 no-op），还能终止停止后新拉起的工作。

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
                    conversation_id=conv_id,
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
            # 🔧 修复：停止失败同样不提前注销——保留注册让用户可以重试停止；
            # 最终注销仍由自然完成路径的 finally 块兜底（任务有超时上限）。

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

    async def _process_reset_conversation(
        self,
        session_id: str,
        message: WebSocketMessage,
    ) -> WebSocketMessage | None:
        """处理重置会话请求

        清空当前会话消息并创建新会话，返回新的 conversation_id 给前端。
        """
        # 从 session 获取上次使用的 workspace_id
        last_workspace_id = await self.get_session_data(session_id, "last_workspace_id")
        if not last_workspace_id:
            logger.warning(f"[CHAT_HANDLER] reset_conversation: 找不到 workspace_id for session {session_id}")
            return await self.send_error_message(
                session_id,
                "WORKSPACE_NOT_FOUND",
                "无法重置会话：未找到关联的工作区。请先发送一条消息建立工作区连接。",
            )

        try:
            # 获取工作区信息
            workspace_info = workspace_manager.get_workspace_by_id(last_workspace_id)
            if not workspace_info:
                raise ValueError(f"找不到工作区信息: '{last_workspace_id}'")

            workspace_path = workspace_info.get("path")
            if not workspace_path:
                raise ValueError(f"工作区 '{last_workspace_id}' 的配置中缺少 'path' 字段。")

            # 加载 UserWorkspace
            user_workspace = UserWorkspace(workspace_path)
            if not user_workspace:
                raise RuntimeError(f"无法从路径加载工作区: '{workspace_path}'")

            # 注入会话真实 user_id（initialize() 之前, 与 chat 主路径同约束）
            try:
                _sess = await self.get_session(session_id)
                _uid = getattr(_sess, "user_id", None) if _sess else None
                if _uid:
                    user_workspace.user_id = _uid
            except Exception as uid_err:
                logger.warning(f"[CHAT_HANDLER] reset_conversation: 读取会话 user_id 失败: {uid_err}")

            if not user_workspace.is_initialized():
                await user_workspace.initialize()

            # 清除当前会话消息（清空 in-memory + 持久化）
            if user_workspace.current_conversation:
                old_conv_id = user_workspace.current_conversation.id
                user_workspace.current_conversation.clear_messages()
                # 同时保存空会话以覆盖持久化数据
                try:
                    await user_workspace.save_current_conversation()
                except Exception as save_err:
                    logger.warning(f"[CHAT_HANDLER] 保存空会话时出现问题: {save_err}")

                logger.info(
                    f"[CHAT_HANDLER] Reset conversation {old_conv_id} "
                    f"in workspace {last_workspace_id}"
                )

            # 创建新会话
            new_conv = await user_workspace.new_conversation()
            new_conv_id = new_conv.id if new_conv else None

            logger.info(
                f"[CHAT_HANDLER] Created new conversation {new_conv_id} "
                f"in workspace {last_workspace_id}"
            )

            # 通知前端新的 conversation_id
            if new_conv_id:
                from dawei.websocket.protocol import ConversationInfoMessage

                conv_info_msg = ConversationInfoMessage(
                    session_id=session_id,
                    conversation_id=new_conv_id,
                    title="新对话",
                    created_at=(
                        new_conv.created_at.isoformat()
                        if hasattr(new_conv, "created_at") and new_conv.created_at
                        else None
                    ),
                )
                await self.send_message(session_id, conv_info_msg)

            return None

        except Exception as e:
            logger.error(f"[CHAT_HANDLER] reset_conversation 失败: {e}", exc_info=True)
            return await self.send_error_message(
                session_id,
                "RESET_FAILED",
                f"重置会话失败: {e!s}",
            )

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
                sandbox_conv_id = None
                if user_workspace and user_workspace.current_conversation:
                    sandbox_conv_id = user_workspace.current_conversation.id
                error_message = ErrorMessage(
                    session_id=session_id,
                    code="SANDBOX_EXECUTION_ERROR",
                    message=result.get("error", "Unknown error"),
                    recoverable=False,
                    details={"command": command, "exit_code": exit_code},
                    conversation_id=sandbox_conv_id,
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
            import json

            assistant_message = AssistantWebSocketMessage(
                id=str(uuid.uuid4()),
                type=MessageType.ASSISTANT_MESSAGE,
                session_id=session_id,
                content=json.dumps([
                    {
                        "type": "system_command_result",
                        "command": command,
                        "stdout": stdout_limited,
                        "stderr": stderr_limited,
                        "exit_code": exit_code,
                        "execution_time": execution_time,
                        "cwd": str(user_workspace.absolute_path),
                    },
                ], ensure_ascii=False),
                timestamp=datetime.now(UTC).isoformat(),
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
            sandbox_err_conv_id = None
            if user_workspace and user_workspace.current_conversation:
                sandbox_err_conv_id = user_workspace.current_conversation.id
            error_message = ErrorMessage(
                session_id=session_id,
                code="SANDBOX_ERROR",
                message=f"沙箱执行出错: {e!s}",
                recoverable=False,
                details={"task_id": task_id, "command": command},
                conversation_id=sandbox_err_conv_id,
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
            self._task_to_conv_id_map.clear()
            self._task_workspace_map.clear()

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
