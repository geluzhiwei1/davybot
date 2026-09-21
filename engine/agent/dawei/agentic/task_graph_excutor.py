# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""任务执行引擎
负责任务的执行、消息处理和工具调用

重构版本：使用接口抽象而非直接依赖具体实现
"""

import asyncio
import uuid
from typing import List, Dict, Any

# 导入错误类型
from dawei.agentic.errors import TaskExecutionError, ToolExecutionError
from dawei.core.errors import (
    CheckpointError,
    ConfigurationError,
    StorageError,
    TaskNotFoundError,
    TaskStateError,
    ValidationError,
)
from dawei.core.exceptions import (
    LLMConnectionError,
    LLMContextOverflowError,
    LLMError as LLMExceptionError,
    LLMRateLimitError,
    LLMResponseError,
    LLMTimeoutError,
)
from dawei.entity.task_types import TaskStatus
from dawei.entity.user_input_message import UserInputMessage

# 导入新的接口
from dawei.interfaces import ILLMService, IMessageProcessor, IToolCallService
from dawei.logg.logging import get_logger
from dawei.task_graph.task_node import TaskNode
from dawei.workspace.user_workspace import UserWorkspace

from .task_node_executor import TaskNodeExecutionEngine

# 编排续跑轮数上限：父任务每消费一批 [子任务执行报告] 可再派发一批子任务，
# 上限兜底防止"每轮只派发不收尾"的死循环（7 段综述流水线约需 6-7 轮）
_MAX_ORCHESTRATION_ROUNDS = 8


class TaskGraphExecutionEngine:
    """任务执行引擎实现
    委托给 TaskNodeExecutionEngine 执行任务
    """

    def __init__(
        self,
        user_workspace: UserWorkspace,
        message_processor: IMessageProcessor,
        llm_service: ILLMService,
        tool_call_service: IToolCallService,
        config: Any,
        agent=None,  # 添加agent引用用于暂停检查
    ):
        """初始化任务图执行引擎

        Args:
            user_workspace: 用户工作区实例
            message_processor: 消息处理器接口实例
            llm_service: LLM 服务接口实例
            tool_call_service: 工具调用服务接口实例
            event_bus: 事件总线接口实例
            config: 统一配置实例
            agent: Agent实例（可选，用于暂停/恢复控制）

        """
        if user_workspace is None:
            raise ConfigurationError("user_workspace must be provided")

        # 初始化logger（必须在最开始）
        self.logger = get_logger(__name__)

        self._user_workspace = user_workspace
        self._message_processor = message_processor
        self._llm_service = llm_service
        self._tool_call_service = tool_call_service
        # 🔧 修复：使用 Agent 的 event_bus
        # 这样确保 ExecutionEngine、TaskNodeExecutor 和 Agent 使用同一个 event_bus
        # WebSocket handler 订阅的是 Agent 的 event_bus，所以所有事件都必须发送到那里
        if not agent:
            raise ConfigurationError("agent must be provided for event_bus")
        if not hasattr(agent, "event_bus"):
            raise ConfigurationError("agent must have event_bus attribute")
        self._event_bus = agent.event_bus
        self._config = config
        self._agent = agent  # 保存agent引用

        # 验证必要的服务是否可用
        if message_processor is None:
            raise ConfigurationError("message_processor must be provided")
        if llm_service is None:
            raise ConfigurationError("llm_service must be provided")
        if tool_call_service is None:
            raise ConfigurationError("tool_call_service must be provided")

        # 任务节点执行引擎管理
        self._node_executors: Dict[str, TaskNodeExecutionEngine] = {}

        # 执行状态跟踪
        self._execution_status: Dict[str, TaskStatus] = {}

        # 🔧 修复：停止标志。stop() 置位后，收尾路径不再启动新的子任务
        self._stop_requested = False
        self._execution_tasks: Dict[str, asyncio.Task] = {}

        # 锁
        self._lock = asyncio.Lock()

        # 当前执行的任务节点ID（用于获取当前步骤描述）
        self._current_task_node_id: str | None = None

        # 最大并行任务节点数限制（从配置读取，默认为2）
        self._max_parallel_tasks = getattr(config, "max_parallel_tasks", 2)
        self._parallel_semaphore = asyncio.Semaphore(self._max_parallel_tasks)

        # 注册为活动执行引擎，供 run_task 工具内联执行子任务（延迟导入避免循环依赖）
        try:
            from dawei.tools.custom_tools.workflow_tools_fixed import set_active_execution_engine

            set_active_execution_engine(self)
        except Exception:  # noqa: BLE001 — 注册失败只影响 run_task，不影响主流程
            self.logger.warning("Failed to register as active execution engine for run_task tool")

        self.logger.info(
            f"TaskGraphExecutionEngine initialized with max_parallel_tasks={self._max_parallel_tasks}",
        )

    @property
    def tool_call_service(self):
        """Expose tool_call_service for knowledge base ID injection"""
        return self._tool_call_service

    async def execute_task_graph(self) -> TaskStatus:
        """执行任务图
        根据任务图中的节点顺序和依赖关系执行任务
        多个没有依赖关系的node可并行执行

        Returns:
            最终执行状态

        """
        try:
            # 获取根任务
            root_task = await self._user_workspace.task_graph.get_root_task()
            if not root_task:
                self.logger.error("No root task found in task graph")
                raise TaskNotFoundError("No root task found in task graph")

            # 初始化执行状态
            await self._initialize_execution_status()

            # 启动时处理孤儿/中断子任务（P2-6）
            await self._reconcile_subtasks_on_startup()

            # 执行任务图
            final_status = await self._execute_task_graph_recursive(root_task)
            self.logger.info(f"Task graph execution completed with status: {final_status.value}")

            # 触发任务完成事件
            await self._emit_task_completion_event(root_task.task_node_id, final_status)

            return final_status

        except TaskNotFoundError:
            self.logger.exception("Task execution failed: ")
            await self._emit_task_completion_event("unknown", TaskStatus.FAILED)
            raise
        except ConfigurationError:
            self.logger.exception("Configuration error in task execution: ")
            await self._emit_task_completion_event("unknown", TaskStatus.FAILED)
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error during task graph execution: {e}", exc_info=True)
            await self._emit_task_completion_event("unknown", TaskStatus.FAILED)
            raise TaskExecutionError("unknown", f"Task graph execution failed: {e}")

    async def _emit_task_completion_event(self, task_id: str, status: TaskStatus) -> None:
        """发送任务完成事件

        Args:
            task_id: 任务ID
            status: 任务状态

        """
        import json as _json

        from dawei.core.events import TaskEventType, emit_typed_event

        # 从会话消息中提取 attempt_completion 的实际结果内容
        fallback_msg = f"Task completed with status: {status.value}"
        result_content = fallback_msg
        # 【单一事实源】优先读任务节点上的 result（attempt_completion 时写入）；
        # 缺失时回落会话消息扫描（兼容写入机制上线前的历史会话）
        node_result = None
        try:
            node = await self._user_workspace.task_graph.get_task(task_id)
            node_result = getattr(getattr(node, "data", None), "result", None)
        except Exception:  # noqa: BLE001 — 节点读取失败回落会话扫描
            self.logger.debug(f"Failed to read node result for {task_id}, falling back to conversation scan")
        if node_result:
            result_content = str(node_result)
        else:
            try:
                conversation = self._user_workspace.current_conversation
                if conversation and conversation.messages:
                    for msg in reversed(conversation.messages):
                        # 优先：检查 ToolMessage（attempt_completion 工具返回的 JSON 结果）
                        if hasattr(msg, "tool_call_id") and hasattr(msg, "content") and msg.content:
                            try:
                                content_data = _json.loads(msg.content)
                                if isinstance(content_data, dict) and content_data.get("type") == "task_completion":
                                    result_content = content_data.get("result", result_content)
                                    break
                            except (ValueError, TypeError):
                                pass
                        # 备选：检查 AssistantMessage 的 tool_calls 中的 attempt_completion 参数
                        if hasattr(msg, "tool_calls") and msg.tool_calls:
                            found = False
                            for tc in msg.tool_calls:
                                if hasattr(tc, "function") and tc.function.name == "attempt_completion":
                                    try:
                                        args = _json.loads(tc.function.arguments)
                                        result_content = args.get("result", result_content)
                                        found = True
                                        break
                                    except (ValueError, TypeError):
                                        pass
                            if found:
                                break
            except Exception as e:
                self.logger.warning(f"Failed to extract attempt_completion result from conversation: {e}")

        task_completed_data = {
            "result": result_content,
            "task_id": task_id,
            "status": status.value,
        }

        await emit_typed_event(
            TaskEventType.TASK_COMPLETED,
            task_completed_data,
            self._event_bus,
            task_id=task_id,
            source="task_graph_excutor",
        )
        self.logger.info(f"Emitted TASK_COMPLETED event for task {task_id}, result length={len(result_content)}")

    async def _initialize_execution_status(self) -> None:
        """初始化执行状态"""
        try:
            async with self._lock:  # 添加锁保护
                all_tasks = await self._user_workspace.task_graph.get_all_tasks()
                if all_tasks is None:
                    raise TaskNotFoundError("No tasks found in task graph")

                for task in all_tasks:
                    if task.task_node_id is None:
                        raise ValidationError("Task with None ID found in task graph")
                    self._execution_status[task.task_node_id] = task.status
        except Exception as e:
            self.logger.error(f"Failed to initialize execution status: {e}", exc_info=True)
            raise TaskExecutionError(
                "unknown",
                f"Failed to initialize execution status: {e}",
            )

    async def _reconcile_subtasks_on_startup(self) -> None:
        """启动时对账子任务状态（P2-6）

        - 父任务已终结（COMPLETED/FAILED/ABORTED）但子任务仍处于未终结状态 → 孤儿，标记 ABORTED
        - 父任务未终结但子任务卡在 RUNNING/WAITING_FOR_TOOL（上次进程崩溃残留）→ 重置为 PENDING 以便恢复执行
        """
        unfinished = {TaskStatus.PENDING, TaskStatus.RUNNING, TaskStatus.WAITING_FOR_TOOL, TaskStatus.PAUSED}
        terminal = {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.ABORTED, TaskStatus.CANCELLED}
        try:
            all_tasks = await self._user_workspace.task_graph.get_all_tasks()
            tasks_by_id = {t.task_node_id: t for t in all_tasks if t.task_node_id}
            for task in all_tasks:
                if not task.task_node_id or not task.parent_id or task.status not in unfinished:
                    continue
                parent = tasks_by_id.get(task.parent_id)
                if parent is None:
                    continue
                if parent.status in terminal:
                    # 孤儿子任务：父已终结，无法再被调度 → 标记 ABORTED（fast fail）
                    await self._user_workspace.task_graph.update_task_status(task.task_node_id, TaskStatus.ABORTED)
                    self._execution_status[task.task_node_id] = TaskStatus.ABORTED
                    self.logger.warning(
                        f"Orphan subtask {task.task_node_id} (parent {task.parent_id}={parent.status.value}) marked ABORTED on startup"
                    )
                elif task.status in (TaskStatus.RUNNING, TaskStatus.WAITING_FOR_TOOL):
                    # 进程崩溃残留：重置为 PENDING，随父任务执行流程恢复
                    await self._user_workspace.task_graph.update_task_status(task.task_node_id, TaskStatus.PENDING)
                    self._execution_status[task.task_node_id] = TaskStatus.PENDING
                    self.logger.info(
                        f"Stale subtask {task.task_node_id} reset RUNNING->PENDING on startup for resume"
                    )
        except Exception as e:  # noqa: BLE001 — 对账失败不阻塞主流程
            self.logger.warning(f"Subtask reconciliation on startup failed (non-fatal): {e}")

    async def _execute_task_graph_recursive(self, current_task: TaskNode) -> TaskStatus:
        """递归执行任务图
        确保父任务完成后才执行子任务
        修改后支持多轮执行机制：等待所有node完成后才结束

        Args:
            current_task: 当前任务节点

        Returns:
            执行状态

        """
        task_node_id = current_task.task_node_id

        # 检查任务是否已完成
        if await self._is_task_already_completed(task_node_id):
            return self._execution_status[task_node_id]

        # 创建或获取任务执行引擎
        executor = await self._get_or_create_executor(current_task, task_node_id)

        # 更新任务状态为运行中
        await self._update_task_status(task_node_id, TaskStatus.RUNNING)

        try:
            # 执行任务并处理结果
            return await self._execute_task_and_handle_completion(
                current_task,
                task_node_id,
                executor,
            )

        except asyncio.CancelledError:
            return await self._handle_task_cancellation(task_node_id)
        except (TaskExecutionError, ToolExecutionError, ValueError, KeyError) as e:
            return await self._handle_task_error(task_node_id, e, "business error")
        except (OSError, RuntimeError, ConnectionError) as e:
            # Unexpected but recoverable errors
            return await self._handle_task_error(task_node_id, e, "unexpected error")

    async def _is_task_already_completed(self, task_node_id: str) -> bool:
        """检查任务是否已完成

        Args:
            task_node_id: 任务节点ID

        Returns:
            如果任务已完成或中止返回True

        """
        async with self._lock:
            current_status = self._execution_status.get(task_node_id)
            if current_status in [TaskStatus.COMPLETED, TaskStatus.ABORTED]:
                self.logger.info(
                    f"Task {task_node_id} already completed with status: {current_status.value}",
                )
                return True
            return False

    async def _get_or_create_executor(
        self,
        current_task: TaskNode,
        task_node_id: str,
    ) -> "TaskNodeExecutionEngine":
        """获取或创建任务执行引擎

        P2-7 会话隔离：子任务（parent_id 非空）且灰度 flag on 时，创建/恢复
        独立 Conversation 注入 executor；flag off / 根任务 → conversation=None（原路径）。

        Args:
            current_task: 当前任务节点
            task_node_id: 任务节点ID

        Returns:
            TaskNodeExecutionEngine实例

        """
        if task_node_id not in self._node_executors:
            conversation = None
            if getattr(current_task, "parent_id", None) is not None:
                conversation = await self._get_or_create_subtask_conversation(current_task)
            self._node_executors[task_node_id] = TaskNodeExecutionEngine(
                task_node=current_task,
                user_workspace=self._user_workspace,
                message_processor=self._message_processor,
                llm_service=self._llm_service,
                tool_call_service=self._tool_call_service,
                event_bus=self._event_bus,
                config=self._config,
                agent=self._agent,  # 传递agent引用
                conversation=conversation,  # P2-7: 子任务隔离会话
            )
        return self._node_executors[task_node_id]

    async def _get_or_create_subtask_conversation(self, current_task: TaskNode):
        """P2-7：获取或创建子任务隔离会话（单一入口）

        - flag off → None（共享 workspace.current_conversation，零行为变化）
        - TaskData.conversation_id 命中历史会话 → 复用（重启恢复）
        - 否则新建（task_type="subtask"），写回 TaskData.conversation_id 并即刻持久化
        - 任何失败降级为 None（共享对话），绝不阻断子任务执行
        """
        from dawei.agentic.subtask_conversation import (
            create_subtask_conversation,
            is_subtask_isolation_enabled,
        )

        if not is_subtask_isolation_enabled():
            return None
        try:
            data = getattr(current_task, "data", None)
            cid = getattr(data, "conversation_id", None)
            if cid:
                mgr = getattr(self._user_workspace, "conversation_history_manager", None)
                if mgr is not None:
                    restored = await mgr.get_by_id(cid)
                    if restored is not None:
                        return restored
                    self.logger.warning(
                        f"Subtask conversation {cid} not found in history, creating a new one",
                    )

            meta = getattr(data, "metadata", None) or {}
            conv = create_subtask_conversation(
                task_node_id=current_task.task_node_id,
                message=getattr(data, "description", ""),
                context_note=meta.get("context_note"),
                agent=meta.get("agent"),
            )
            try:
                data.conversation_id = conv.id  # F9: 随 TaskData 持久化，重启可恢复
            except Exception:  # noqa: BLE001
                self.logger.exception("Failed to record conversation_id on TaskData: ")
            saver = getattr(self._user_workspace, "save_subtask_conversation", None)
            if saver is not None:
                await saver(conv)
            self.logger.info(
                f"P2-7: isolated conversation {conv.id} created for subtask {current_task.task_node_id}",
            )
            return conv
        except Exception:  # noqa: BLE001 — 隔离失败降级共享对话，不阻断子任务
            self.logger.exception("Subtask conversation isolation failed, falling back to shared conversation: ")
            return None

    async def _update_task_status(self, task_node_id: str, status: TaskStatus) -> None:
        """更新任务状态

        Args:
            task_node_id: 任务节点ID
            status: 新状态

        """
        await self._user_workspace.task_graph.update_task_status(task_node_id, status)
        self._execution_status[task_node_id] = status
        await self._emit_subtask_lifecycle_event(task_node_id, status)

    # P3-6: 状态迁移 → 子任务生命周期事件名（None = 不发）
    _STATUS_TO_LIFECYCLE = {
        TaskStatus.RUNNING: "started",
        TaskStatus.COMPLETED: "completed",
        TaskStatus.FAILED: "failed",
        TaskStatus.ABORTED: "aborted",
    }

    async def _emit_subtask_lifecycle_event(self, task_node_id: str, status: TaskStatus) -> None:
        """P3-6：状态迁移单一 choke point 发射子任务生命周期事件（fire-and-forget）

        根任务（parent_id None）与未知节点不发。
        """
        try:
            from dawei.agentic.subtask_events import emit_subtask_lifecycle

            lifecycle = self._STATUS_TO_LIFECYCLE.get(status)
            if lifecycle is None:
                return
            node = await self._user_workspace.task_graph.get_task(task_node_id)
            if node is None or getattr(node, "parent_id", None) is None:
                return
            data = getattr(node, "data", None)
            meta = getattr(data, "metadata", None) or {}
            await emit_subtask_lifecycle(
                lifecycle,
                task_node_id=node.task_node_id,
                parent_id=node.parent_id,
                conversation_id=getattr(data, "conversation_id", None),
                agent=meta.get("agent"),
                depth=getattr(data, "depth", None),
                status=status.value if hasattr(status, "value") else str(status),
                event_bus=self._event_bus,
            )
        except Exception:  # noqa: BLE001 — 事件失败绝不影响状态迁移主流程
            self.logger.exception(f"Failed to emit subtask lifecycle event for {task_node_id}: ")

    async def _execute_task_and_handle_completion(
        self,
        current_task: TaskNode,
        task_node_id: str,
        executor: "TaskNodeExecutionEngine",
    ) -> TaskStatus:
        """执行任务并处理完成逻辑（带超时重试机制）

        Args:
            current_task: 当前任务节点
            task_node_id: 任务节点ID
            executor: 任务执行引擎

        Returns:
            最终任务状态

        """
        # Phase 4: 使用节点自身的重试配置（idempotent execution）
        base_delay = 2.0  # 基础延迟2秒

        # 跳过已完成节点（断点续传恢复）
        if current_task.data.status == TaskStatus.COMPLETED:
            self.logger.info(
                f"Task {task_node_id} already COMPLETED, skipping (idempotent execution)",
            )
            return TaskStatus.COMPLETED

        while current_task.data.can_retry():
            current_task.data.increment_retry()
            attempt = current_task.data.retry_count

            try:
                # 执行当前任务（等待直到完成或中止）
                await executor.execute_task()

                # 成功执行，退出重试循环
                break

            except TimeoutError as e:
                # 超时错误处理
                if current_task.data.can_retry():
                    # 计算指数退避延迟
                    delay = base_delay * (2 ** (attempt - 1))
                    self.logger.warning(
                        f"Task {task_node_id} timeout on attempt {attempt}/{current_task.data.max_retries}, "
                        f"retrying in {delay:.1f}s...",
                    )

                    await asyncio.sleep(delay)

                    # 重新创建executor以避免状态污染
                    executor = await self._get_or_create_executor(current_task, task_node_id)

                    continue
                # 重试次数用尽，记录错误并返回失败状态
                self.logger.exception(
                    f"Task {task_node_id} failed after {attempt}/{current_task.data.max_retries} attempts due to timeout",
                )
                await self._emit_error_event(task_node_id, e, f"timeout after {attempt} retries")
                return TaskStatus.FAILED

            except (
                LLMRateLimitError,
                LLMResponseError,
                LLMContextOverflowError,
            ) as e:
                # 【FAST FAIL】不可重试的 LLM 错误：
                # - RateLimit (429): rate limit 窗口 60s >> 退避周期，重试无意义
                # - ResponseError: 响应格式错误，重试同样的请求结果不变
                # - ContextOverflow: 上下文溢出，必须截断后才能重试
                self.logger.error(
                    f"Task {task_node_id} non-retryable LLM error ({type(e).__name__}): {e}",
                )
                await self._emit_error_event(task_node_id, e, f"non-retryable LLM error ({type(e).__name__})")
                return TaskStatus.FAILED

            except (LLMConnectionError, LLMTimeoutError, OSError) as e:
                # 可重试的瞬态错误：连接超时/服务端 500/网络中断
                if current_task.data.can_retry():
                    delay = base_delay * (2 ** (attempt - 1))
                    self.logger.warning(
                        f"Task {task_node_id} transient LLM/network error ({type(e).__name__}) on attempt "
                        f"{attempt}/{current_task.data.max_retries}: {e}, "
                        f"retrying in {delay:.1f}s...",
                    )
                    await asyncio.sleep(delay)
                    executor = await self._get_or_create_executor(current_task, task_node_id)
                    continue
                self.logger.exception(
                    f"Task {task_node_id} failed after {attempt}/{current_task.data.max_retries} attempts "
                    f"due to transient LLM/network error: {e}",
                )
                await self._emit_error_event(task_node_id, e, "LLM/network error")
                return TaskStatus.FAILED

            except Exception as e:
                # 检查是否为可重试的网络/传输错误（aiohttp 连接/传输类瞬态错误等）
                # 这些异常不继承自标准 OSError/ConnectionError，必须通过类型名或消息匹配
                _exc_type = type(e).__name__
                _err_msg = str(e).lower()
                _is_retryable = (
                    _exc_type
                    in (
                        # aiohttp 连接被对端关闭/断开等瞬态错误（网关超时、keep-alive 复用失效）
                        "ClientConnectionError",  # ← “Connection closed” 的直接类型
                        "ClientConnectorError",
                        "ClientOSError",
                        "ClientPayloadError",
                        "ServerDisconnectedError",
                        "ServerTimeoutError",
                        "SocketTimeoutError",
                        "TransferEncodingError",
                        "PayloadEncodingError",
                    )
                    or "connection closed" in _err_msg
                    or "server disconnected" in _err_msg
                    or "not enough data" in _err_msg
                )

                if _is_retryable and current_task.data.can_retry():
                    delay = base_delay * (2 ** (attempt - 1))
                    self.logger.warning(
                        f"Task {task_node_id} network/transport error on attempt {attempt}/{current_task.data.max_retries}: {e}, "
                        f"retrying in {delay:.1f}s...",
                    )
                    await asyncio.sleep(delay)
                    executor = await self._get_or_create_executor(current_task, task_node_id)
                    continue
                elif _is_retryable:
                    self.logger.exception(
                        f"Task {task_node_id} failed after {attempt}/{current_task.data.max_retries} attempts due to network error: {e}",
                    )
                    await self._emit_error_event(task_node_id, e, "network transfer error")
                    return TaskStatus.FAILED
                else:
                    # 不可重试的未知错误，向上抛出
                    self.logger.exception(f"Task {task_node_id} encountered unexpected error: ")
                    await self._emit_error_event(task_node_id, e, "unexpected error")
                    raise

        # 🔧 修复：不管当前状态如何，都要检查是否有子任务或子图需要处理
        # 这是为了避免主任务标记为COMPLETED但子任务还在执行的情况
        #
        # 🔧 修复（P0 编排续跑循环，2026-09-16 conv 10e6e91c 实证）：旧逻辑是
        # "单发"——子任务跑完、[子任务执行报告]回注父对话后，直接用子任务状态
        # 聚合收尾，父任务永远不会再获得 LLM 轮次去消费报告。后果：review-
        # orchestrator 派发 Stage1-2 后立即 attempt_completion（"派发即收工"），
        # 子任务完成、报告回注 1356 字符却无人读取 → 7 段综述流水线停在第 2 段，
        # 图被标记 completed、AGENT_COMPLETE 提前触发。
        # 正确语义：每批"新"子任务完成并回注报告后续跑（resume）父任务一个执行期
        # ——execute_task 每次调用都会重置 _has_attempt_completion / executed_tool_calls
        # （task_node_executor.py:494-497），且对话尾部=报告 user 消息 → 父 LLM 必然
        # 读到报告——父任务要么派发下一批子任务（继续循环），要么 attempt_completion
        # 真正收尾（无新子任务 → 退出循环）。轮数上限兜底防派发死循环。
        _terminal = {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.ABORTED, TaskStatus.CANCELLED}
        executed_subtask_ids: set = set()
        subgraph_executed = False
        final_status = current_task.status

        for _round in range(1, _MAX_ORCHESTRATION_ROUNDS + 1):
            subtasks = await self._get_subtasks_with_grace(task_node_id)
            # "新" = 本循环尚未处理过。刻意不做 terminal 过滤：new_task 同步执行路径
            # 下新子任务可能已完成——它们会被 _is_task_already_completed 幂等跳过，
            # 但其结果仍需回注报告并触发父任务续跑（否则回到旧 bug：报告无人消费）
            new_subtasks = [s for s in subtasks if s.task_node_id not in executed_subtask_ids]
            # 沿用原语义：子任务优先；sub_graph 仅在无任何子任务时才执行
            has_new_work = bool(new_subtasks) or (
                bool(current_task.sub_graph) and not subgraph_executed and not subtasks
            )

            if not has_new_work:
                if _round > 1:
                    self.logger.info(
                        f"Task {task_node_id} orchestration round {_round}: no new subtasks/subgraph "
                        f"after resumed parent turn, exiting loop with status {final_status.value}",
                    )
                break

            if self._stop_requested:
                # 🔧 修复：用户已请求停止——绝不在此启动 pending 子任务/子图，
                # 直接把未终结的子任务标记 ABORTED 收口（此前 stop 之后收尾
                # 逻辑仍会 "Starting subtask ..." 把新子任务拉起来跑）。
                self.logger.info(
                    f"Task {task_node_id} finished after stop request, aborting "
                    f"{len([s for s in subtasks if s.status not in _terminal])} subtasks instead of starting them",
                )
                for _sub in subtasks:
                    if _sub.status in _terminal:
                        continue
                    try:
                        await asyncio.wait_for(
                            self._update_task_status(_sub.task_node_id, TaskStatus.ABORTED), timeout=5.0
                        )
                    except Exception:  # noqa: BLE001 — 单个子任务收口失败不影响其余
                        self.logger.exception(f"Failed to abort subtask {_sub.task_node_id} during stop: ")
                final_status = current_task.status
                break

            self.logger.info(
                f"Task {task_node_id} orchestration round {_round}/{_MAX_ORCHESTRATION_ROUNDS}: "
                f"executing {len(new_subtasks)} new subtasks{'/subgraph' if not new_subtasks else ''} "
                f"before resuming parent...",
            )
            if new_subtasks:
                # 只执行"新"子任务：已执行节点若再次传入会被重跑并重复回注报告
                children_status = await self._execute_subtasks_and_check_status(new_subtasks)
                executed_subtask_ids.update(s.task_node_id for s in new_subtasks)
            else:
                subgraph_executed = True
                children_status = await self._handle_subtasks_and_subgraphs(current_task, task_node_id)
                # 兜底：子图执行期间若竞态出现子任务，标记已处理避免下轮重复执行
                for _s in await self._get_subtasks_with_grace(task_node_id):
                    executed_subtask_ids.add(_s.task_node_id)

            if children_status != TaskStatus.COMPLETED:
                # 【FAST FAIL】子任务有失败 → 父任务直接判失败，不再续跑父 LLM
                final_status = TaskStatus.FAILED
                break

            if self._stop_requested:
                final_status = current_task.status
                break

            # 🔧 续跑父任务：报告已回注（_inject_subtask_summaries），父任务获得
            # 新执行期读取 [子任务执行报告] 并决定下一步（派发新 Stage 或收尾）
            try:
                # 🔧 P0-3 修复（2026-09-20 TUI conv 9f2d4586 实证）：父任务自身轮次
                # 结束时已把节点置为 COMPLETED（attempt_completion / 自然收尾），
                # 而 _run_task_loop 的终态门（task_node_executor.py:1226-1231）会在
                # 任何 LLM 轮次之前直接 break —— 续跑沦为 0 轮空转，报告无人消费，
                # 收尾保护只能降级 COMPLETED→FAILED（子任务成果全部作废=白烧 token）。
                # 恢复手段：COMPLETED 终态先经唯一合法重跑入口 reset_task_for_rerun
                # 回 PENDING（旧 result stash 进 metadata.prev_*，审计可追溯），
                # 续跑才有真实 LLM 轮次去消费报告并真正收尾。FAILED/ABORTED 不复活。
                if current_task.status is TaskStatus.COMPLETED:
                    _reset_ok = False
                    try:
                        _reset_ok = bool(
                            await self._user_workspace.task_graph.reset_task_for_rerun(
                                task_node_id,
                                reason="orchestration resume: consume injected subtask report",
                            )
                        )
                    except Exception:  # noqa: BLE001 — reset 失败保留终态，续跑按旧语义空转，收尾保护兜底
                        self.logger.exception(f"Task {task_node_id} rerun reset before resume failed: ")
                    if _reset_ok:
                        self.logger.info(
                            f"Task {task_node_id} reset COMPLETED -> PENDING before resume "
                            f"(stashed previous result to metadata.prev_*), parent will get real LLM rounds",
                        )
                self.logger.info(
                    f"Task {task_node_id} resuming parent executor to consume subtask report "
                    f"(round {_round}/{_MAX_ORCHESTRATION_ROUNDS})...",
                )
                await executor.execute_task()
            except Exception:  # noqa: BLE001 — 续跑失败按失败收口，不吞异常细节
                self.logger.exception(f"Task {task_node_id} parent resume failed: ")
                final_status = TaskStatus.FAILED
                break
        else:
            self.logger.warning(
                f"Task {task_node_id} hit max orchestration rounds ({_MAX_ORCHESTRATION_ROUNDS}), "
                f"forcing finalize with status {final_status.value}",
            )

        # 【状态和解】orchestration 续跑前会把 COMPLETED 节点 reset 回 PENDING
        # （reset_task_for_rerun，见上方循环）；若续跑轮结束时节点未再度终结
        # （父 LLM 消费报告后自然收尾、未调 attempt_completion），final_status
        # （终态）与状态机现状（PENDING）脱节 —— 直接 PENDING→COMPLETED/FAILED
        # 会被状态机拒绝并炸掉整图（E2E 2026-09-21 tui-review 实证：S3-6 报告
        # 消费后 pending→completed 崩溃，CLI 退出码 1）。先补 PENDING→RUNNING
        # 跳板，后续终态转换（含下方收尾保护 FAILED 路径与最终 final_status
        # 收口）在状态机中均合法。
        if final_status in _terminal:
            try:
                _graph_status = await self._user_workspace.task_graph.get_task_status(task_node_id)
            except Exception:  # noqa: BLE001 — 查询失败按节点对象状态兜底
                _graph_status = current_task.status
            if _graph_status == TaskStatus.PENDING:
                self.logger.info(
                    f"Task {task_node_id} status reconcile: PENDING -> RUNNING hop "
                    f"before final {final_status.value} (resume turn ended without re-finalizing)",
                )
                await self._update_task_status(task_node_id, TaskStatus.RUNNING)

        # P0-2 收尾保护（仅根任务）：COMPLETED 且对话尾部仍有未消费的
        # [子任务执行报告] 时不得静默成功 —— 派发结果被无视等于白烧 token
        # （E2E 2026-09-18：报告回注后父任务无任何 LLM 轮次，图却标记完成）。
        # FAST FAIL 降级 FAILED 并写机器可读原因；不新增 completed_degraded
        # 枚举（状态机/前端/持久化连锁改动，违背 KISS），FAILED 可经既有重试补救。
        if (
            final_status == TaskStatus.COMPLETED
            and getattr(current_task, "parent_id", None) is None
            and not self._stop_requested
            and self._has_unconsumed_subtask_report()
        ):
            self.logger.warning(
                f"Task {task_node_id} finish protection: unconsumed subtask report at completion, "
                f"degrading COMPLETED -> FAILED",
            )
            await self._emit_error_event(
                task_node_id,
                TaskExecutionError(task_node_id, "subtask execution report left unconsumed at completion"),
                "finish protection",
            )
            _fp_reason = "(收尾保护: 子任务执行报告未被父任务消费 — 派发结果被无视，禁止静默标记完成)"
            _fp_finalized = False
            try:
                _fp_finalize = getattr(self._user_workspace.task_graph, "finalize_task", None)
                if callable(_fp_finalize):
                    _fp_finalized = bool(await _fp_finalize(task_node_id, TaskStatus.FAILED, _fp_reason))
            except Exception:  # noqa: BLE001 — finalize 失败退普通状态更新
                self.logger.exception(f"Failed to finalize degraded task {task_node_id}: ")
            if not _fp_finalized:
                await self._update_task_status(task_node_id, TaskStatus.FAILED)
            final_status = TaskStatus.FAILED

        # 状态同步：续跑后以父任务最新状态为准（未被失败路径覆盖时）
        if final_status != TaskStatus.FAILED and current_task.status in _terminal:
            final_status = current_task.status

        if not executed_subtask_ids and not subgraph_executed:
            self.logger.info(
                f"Task {task_node_id} executor finished with no subtasks or subgraph, "
                f"using current status: {final_status.value}",
            )

        # 更新任务状态
        await self._update_task_status(task_node_id, final_status)
        self.logger.info(
            f"Task {task_node_id} execution completed with status: {final_status.value}",
        )
        return final_status

    async def _get_subtasks_with_grace(
        self,
        task_node_id: str,
        attempts: int = 3,
        delay: float = 0.1,
    ) -> List[TaskNode]:
        """带宽限期地获取子任务

        防御性兜底：new_task 工具现为同步确认式创建（await 写入图后才返回），
        正常情况下 executor 收尾时子任务已在图中。但为防止任何残留的异步写入
        路径造成 check-then-act 竞态，这里做短轮询。

        Args:
            task_node_id: 任务节点ID
            attempts: 查询次数
            delay: 每次查询间隔（秒）

        Returns:
            子任务列表（可能为空）
        """
        subtasks = await self._user_workspace.task_graph.get_subtasks(task_node_id)
        for i in range(attempts - 1):
            if subtasks:
                return subtasks
            self.logger.debug(
                f"Task {task_node_id}: no subtasks found (attempt {i + 1}/{attempts}), retrying in {delay}s...",
            )
            await asyncio.sleep(delay)
            subtasks = await self._user_workspace.task_graph.get_subtasks(task_node_id)
        return subtasks

    async def _handle_subtasks_and_subgraphs(
        self,
        current_task: TaskNode,
        task_node_id: str,
    ) -> TaskStatus:
        """处理子任务和子图的执行

        Args:
            current_task: 当前任务节点
            task_node_id: 任务节点ID

        Returns:
            最终状态

        """
        # 获取子任务（带宽限期，见 _get_subtasks_with_grace）
        subtasks = await self._get_subtasks_with_grace(task_node_id)

        if subtasks:
            # 并行执行子任务并检查结果
            return await self._execute_subtasks_and_check_status(subtasks)

        # 没有子任务，检查是否有子图需要执行
        if current_task.sub_graph:
            # 递归执行子图
            # 🔧 修复：原 execute_task_graph(current_task.sub_graph) 与方法签名
            # execute_task_graph(self) 不符，一旦触发即 TypeError。
            # 正确做法：遍历子图的根节点（无父节点）递归执行。
            self.logger.info(
                f"Task {task_node_id} has sub_graph; executing sub_graph root nodes",
            )
            sub_graph_roots: List[TaskNode] = []
            if hasattr(current_task.sub_graph, "get_all_nodes"):
                try:
                    sub_graph_roots = [
                        n for n in current_task.sub_graph.get_all_nodes() if getattr(n, "parent_id", None) is None
                    ]
                except Exception:  # noqa: BLE001 — 子图遍历失败不应导致父任务崩溃
                    self.logger.exception("Failed to traverse sub_graph nodes: ")
                    return current_task.status
            if not sub_graph_roots:
                self.logger.warning(f"Task {task_node_id} sub_graph has no root nodes, skipping")
                return current_task.status
            statuses = []
            for sg_root in sub_graph_roots:
                statuses.append(await self._execute_task_graph_recursive(sg_root))
            if statuses and all(s == TaskStatus.COMPLETED for s in statuses):
                return TaskStatus.COMPLETED
            return TaskStatus.FAILED

        # 没有子任务也没有子图
        self.logger.info(
            f"Task {task_node_id} executor finished without explicit completion, checking status...",
        )
        return current_task.status

    async def _execute_subtasks_and_check_status(self, subtasks: List[TaskNode]) -> TaskStatus:
        """并行执行子任务并检查状态，并将子任务结果摘要回注父对话

        Args:
            subtasks: 子任务列表

        Returns:
            任务状态（COMPLETED或FAILED）

        """
        # P1: 记录子任务执行前的对话长度，用于事后提取子任务产出
        conversation = getattr(self._user_workspace, "current_conversation", None)
        msg_snapshot = len(conversation.messages) if conversation else 0

        # 并行执行子任务
        subtask_results = await self._execute_subtasks_parallel(subtasks)

        # P1: 子任务 summary 回注父对话 —— 父任务（及其后续 LLM 轮次）必须能
        # 看到"子任务做了什么、结果如何"，而不只是一个布尔状态聚合
        try:
            await self._inject_subtask_summaries(subtasks, subtask_results, msg_snapshot)
        except Exception:  # noqa: BLE001 — 摘要回注失败不影响主流程
            self.logger.exception("Failed to inject subtask summaries into parent conversation: ")

        # 检查子任务执行结果
        if all(result == TaskStatus.COMPLETED for result in subtask_results):
            return TaskStatus.COMPLETED
        # 如果有子任务失败，父任务也标记为失败
        return TaskStatus.FAILED

    async def _inject_subtask_summaries(
        self,
        subtasks: List[TaskNode],
        subtask_results: List[TaskStatus],
        msg_snapshot: int,
        max_chars: int = 2000,
    ) -> None:
        """把子任务执行结果摘要写入父对话（P1: 结果回传）

        对每个子任务：状态 + 描述 + 从对话新增消息中提取的 task_completion 结果。
        摘要以一条 UserMessage（标注为系统报告）追加，保证后续 build_messages 可见。

        Args:
            subtasks: 子任务列表
            subtask_results: 对应的执行状态
            msg_snapshot: 子任务执行前的对话消息数（用于提取增量消息）
            max_chars: 每个子任务结果的最大字符数
        """
        import json as _json

        from dawei.agentic.subtask_conversation import (
            NO_RESULT_PLACEHOLDER,
            extract_task_completion,
            get_subtask_conversation,
        )
        from dawei.entity.lm_messages import UserMessage

        conversation = getattr(self._user_workspace, "current_conversation", None)
        if conversation is None:
            return

        # flag off 共享路径的位置匹配兜底：从子任务执行期间新增的消息里按序提取
        completion_results: List[str] = []
        snapshot_valid = msg_snapshot <= len(conversation.messages)
        new_msgs = conversation.messages[msg_snapshot:] if snapshot_valid else []
        for msg in new_msgs:
            content = getattr(msg, "content", None)
            if not content or not isinstance(content, str):
                continue
            try:
                data = _json.loads(content)
            except (ValueError, TypeError):
                continue
            if isinstance(data, dict) and data.get("type") == "task_completion" and data.get("result"):
                completion_results.append(str(data["result"]))

        # 🔧 修复：new_task 工具是同步确认式创建并执行——子任务在父节点工具阶段
        # 就已完成，task_completion（工具结果消息）落在 msg_snapshot 之前，
        # 上面的增量扫描扑空，报告显示"(无显式完成结果)"而用户看不到执行结果。
        # 兜底：增量扫描为空时，反向全量扫描取最近一条 task_completion。
        if not completion_results:
            for msg in reversed(conversation.messages):
                content = getattr(msg, "content", None)
                if not content or not isinstance(content, str):
                    continue
                try:
                    data = _json.loads(content)
                except (ValueError, TypeError):
                    continue
                if isinstance(data, dict) and data.get("type") == "task_completion" and data.get("result"):
                    completion_results.append(str(data["result"]))
                    break  # 只取最近一条，避免与历史轮次混淆

        lines = ["[子任务执行报告 / Subtask Execution Report]"]
        has_acceptance = False
        for i, (node, status) in enumerate(zip(subtasks, subtask_results, strict=False)):
            desc = ""
            try:
                desc = str(getattr(node.data, "description", "") or "")[:150]
            except Exception:  # noqa: BLE001
                pass
            # 【单一事实源】节点 result 优先（attempt_completion / 预算超限时写入）；
            # 缺失时回落旧提取链（隔离会话定向提取 → 共享对话位置匹配），
            # 兼容写入机制上线前的历史会话。
            node_result = getattr(node.data, "result", None) if node.data is not None else None
            iso_conv = get_subtask_conversation(self, node.task_node_id)
            if node_result:
                result_text = str(node_result)[:max_chars]
            else:
                # P1a ④ SSOT 收敛：节点 result 缺失才会走到旧提取链 —— 记弃用日志，
                # 命中率归零后即可退役扫描链（docs/子任务组织管理交互方案.md §P1a）
                self.logger.warning(
                    f"[SSOT-deprecated] subtask {node.task_node_id} has no node-level result; "
                    f"falling back to conversation scan chain (isolated_conv={iso_conv is not None})",
                )
                # §8 扫描兜底命中率埋点（fire-and-forget）
                try:
                    from dawei.agentic.subtask_metrics import get_metrics

                    get_metrics().record_scan_fallback(isolated=iso_conv is not None)
                except Exception:  # noqa: BLE001
                    pass
                if iso_conv is not None:
                    result_text = extract_task_completion(iso_conv, max_chars=max_chars)
                    # 🔧 修复：隔离会话里没有 task_completion 时回落共享对话提取，
                    # 不再直接落到"(无显式完成结果)"占位符。
                    if result_text == NO_RESULT_PLACEHOLDER and i < len(completion_results):
                        result_text = completion_results[i][:max_chars]
                else:
                    result_text = completion_results[i][:max_chars] if i < len(completion_results) else NO_RESULT_PLACEHOLDER
            # 报告占位符统一中文：报告面向父任务 LLM/用户，与 workflow_tools_fixed
            # 的 "(无显式完成结果)" 同文案；提取链内部仍用英文常量判定
            _is_placeholder = result_text == NO_RESULT_PLACEHOLDER
            if _is_placeholder:
                result_text = "(无显式完成结果)"
            # §8 占位率埋点：每条子任务报告条目计一次（fire-and-forget）
            try:
                from dawei.agentic.subtask_metrics import get_metrics

                get_metrics().record_report(placeholder=_is_placeholder)
            except Exception:  # noqa: BLE001
                pass
            # P3-7: 回注前扫描伪造系统标签（<system-reminder>/<command-message> 等），命中即中和
            from dawei.agentic.injection_guard import sanitize_output

            safe = sanitize_output(result_text)
            if safe != result_text:
                self.logger.warning(
                    f"Injection guard: sanitized forged system tags in subtask {node.task_node_id} result",
                )
                result_text = safe
            # P1b ⑧ 报告回显：验收标准 + 成本/耗时（父 LLM 判定"完成"vs"完成但未达标"的数据源）
            _bits = [f"status={status.value}"]
            _data_meta = node.data
            _acceptance = getattr(_data_meta, "acceptance_criteria", None)
            if _acceptance:
                has_acceptance = True
                _bits.append(f"acceptance={str(_acceptance)[:300]}")
            _tokens = getattr(_data_meta, "tokens_used", None)
            _started = getattr(_data_meta, "started_at", None)
            _completed = getattr(_data_meta, "completed_at", None)
            _duration_s = int((_completed - _started).total_seconds()) if (_started and _completed) else None
            if _tokens is not None or _duration_s is not None:
                _bits.append(
                    f"cost={_tokens if _tokens is not None else '?'}tokens/{_duration_s if _duration_s is not None else '?'}s"
                )
            lines.append(
                f"- Subtask {node.task_node_id}: {', '.join(_bits)}, description={desc}\n  result: {result_text}",
            )

        # （mode-工具解耦 D6："工具被模式拦截"反馈闭环（suggest_modes 提示）
        #   已随 mode 拦截工具的机制整体删除 —— mode 不再拦截工具，任何模式的
        #   子任务都可见已安装工具，不存在"被模式拦截"的子任务结果。）

        # 有验收标准的报告必须给出判定指令：父 LLM 逐条对照，未达标不得当作已完成
        if has_acceptance:
            lines.append(
                "判定提示: 请逐条对照各子任务的 acceptance 验收标准核对 result；"
                "达标=完成。未达标=完成但未达标，需补救/重新派发并回显未达标原因，不得当作已完成。"
            )

        report = "\n".join(lines)
        conversation.say(UserMessage(content=report))
        self.logger.info(
            f"Injected subtask execution report into conversation {conversation.id} "
            f"({len(subtasks)} subtasks, report {len(report)} chars)",
        )
        try:
            await self._user_workspace.save_current_conversation()
        except Exception:  # noqa: BLE001
            self.logger.warning("Failed to save conversation after subtask summary injection")

    def _has_unconsumed_subtask_report(self) -> bool:
        """P0-2 收尾保护探测：对话尾部是否为未被父任务消费的 [子任务执行报告]。

        从尾部反向扫描：先遇到 AssistantMessage（含带 tool_calls 的）= 父任务
        已回应（消费）；先遇到报告 UserMessage = 报告注入后父任务再无任何
        LLM 轮次（未消费）。ToolMessage 跳过（必伴随其前置 AssistantMessage）。
        """
        conv = getattr(self._user_workspace, "current_conversation", None)
        msgs = list(getattr(conv, "messages", None) or [])
        if not msgs:
            return False
        from dawei.entity.lm_messages import AssistantMessage

        for msg in reversed(msgs):
            if isinstance(msg, AssistantMessage):
                return False
            if getattr(msg, "tool_call_id", None) is not None:
                continue  # ToolMessage
            content = getattr(msg, "content", None)
            if isinstance(content, str) and content.startswith("[子任务执行报告"):
                return True
        return False

    async def _handle_task_cancellation(self, task_node_id: str) -> None:
        """处理任务取消

        Args:
            task_node_id: 任务节点ID

        Raises:
            asyncio.CancelledError: 重新抛出取消异常

        """
        self.logger.info(f"Task {task_node_id} was cancelled")
        await self._update_task_status(task_node_id, TaskStatus.ABORTED)
        raise  # 重新抛出让上层处理

    async def _emit_error_event(
        self,
        task_node_id: str,
        error: Exception,
        error_category: str = "error",
    ):
        """发送错误事件到前端

        Args:
            task_node_id: 任务节点ID
            error: 异常对象
            error_category: 错误分类描述

        """
        from dawei.core.events import TaskEventType, emit_typed_event

        error_message = str(error)
        error_class = type(error).__name__

        # 针对特定错误类型提供更友好的错误消息
        user_friendly_message = error_message
        if "Cannot connect to host" in error_message or "Network is unreachable" in error_message:
            user_friendly_message = "无法连接到LLM服务，请检查网络连接和API配置。"
        elif "connection closed" in error_message.lower() or "server disconnected" in error_message.lower():
            user_friendly_message = "与LLM服务的连接被中断（网络波动或服务端关闭了连接），请稍后重试。"
        elif "429" in error_message or "insufficient balance" in error_message:
            # 【修复】rate_limit / 余额不足错误已由 task_node_executor._send_error_to_frontend
            # 发送了详细的 rate_limit_exceeded 错误事件到前端。此处再发一次会造成
            # 用户看到重复错误消息。跳过本次发射，避免重复。
            self.logger.info(
                f"Skipping duplicate error event for {error_class} (already sent by task_node_executor): {error_message[:200]}"
            )
            return
        elif error_class in ("LLMError", "LLMResponseError") or "Provider error" in error_message:
            # 【修复】所有 LLM API 错误（400/401/402 等）已由 task_node_executor 的
            # except LLMError 块发送了 llm_api_error 错误事件到前端。
            # 此处再发一次会造成用户看到重复错误消息。跳过，避免重复。
            self.logger.info(
                f"Skipping duplicate error event for {error_class} (LLM error already sent by task_node_executor): {error_message[:200]}"
            )
            return
        elif "500" in error_message:
            user_friendly_message = "LLM服务暂时不可用，请稍后重试。"
        elif "timeout" in error_message.lower():
            user_friendly_message = "请求超时，请检查网络连接或稍后重试。"

        # 构建错误事件数据
        error_data = {
            "error_type": error_class,
            "message": user_friendly_message,
            "details": {
                "task_node_id": task_node_id,
                "original_error": error_message,
                "error_category": error_category,
            },
        }

        # 发送错误事件
        await emit_typed_event(
            TaskEventType.ERROR_OCCURRED,
            error_data,
            self._event_bus,
            task_id=task_node_id,
            source="task_graph_executor",
        )

    async def _handle_task_error(
        self,
        task_node_id: str,
        error: Exception,
        error_type: str,
    ) -> TaskStatus:
        """处理任务执行错误

        Args:
            task_node_id: 任务节点ID
            error: 异常对象
            error_type: 错误类型描述

        Returns:
            TaskStatus.FAILED

        """
        self.logger.error(
            f"{error_type.capitalize()} executing task {task_node_id}: {error}",
            exc_info=True,
        )

        # 发送错误事件到前端
        await self._emit_error_event(task_node_id, error, error_type)

        await self._update_task_status(task_node_id, TaskStatus.FAILED)
        return TaskStatus.FAILED

    def _topological_sort_subtasks(self, subtasks: List[TaskNode]) -> List[List[TaskNode]]:
        """Phase 3: Topologically sort subtasks into execution waves.

        Groups nodes by their dependency depth so that all nodes in wave N
        depend only on nodes in waves < N. Nodes within the same wave are
        independent and can run in parallel.

        Args:
            subtasks: 子任务列表

        Returns:
            List of waves, each wave is a list of TaskNodes
        """
        # Build in-degree map (count of unfinished predecessors within this subtask set)
        subtask_ids = {s.task_node_id for s in subtasks}
        in_degree: Dict[str, int] = {}
        dependents: Dict[str, List[str]] = {}  # node -> list of nodes that depend on it

        for s in subtasks:
            in_degree[s.task_node_id] = 0
            dependents[s.task_node_id] = []

        # Count dependencies: a subtask depends on another if the other is its parent
        # and both are in the subtask set
        for s in subtasks:
            if s.parent_id and s.parent_id in subtask_ids:
                in_degree[s.task_node_id] += 1
                dependents.setdefault(s.parent_id, []).append(s.task_node_id)

        # Topological sort into waves
        waves: List[List[TaskNode]] = []
        id_to_node = {s.task_node_id: s for s in subtasks}
        remaining = set(s.task_node_id for s in subtasks)

        while remaining:
            current_wave_ids = [nid for nid in remaining if in_degree.get(nid, 0) == 0]
            if not current_wave_ids:
                # Cycle detected (shouldn't happen in a valid DAG) — break remaining into flat list
                self.logger.warning(
                    "Cycle detected in subtask dependencies, flattening remaining nodes into single wave"
                )
                current_wave_ids = list(remaining)

            current_wave = [id_to_node[nid] for nid in current_wave_ids if nid in id_to_node]
            waves.append(current_wave)

            for nid in current_wave_ids:
                remaining.discard(nid)
                for dep_id in dependents.get(nid, []):
                    if dep_id in in_degree:
                        in_degree[dep_id] -= 1

        return waves

    async def _execute_subtasks_parallel(self, subtasks: List[TaskNode]) -> List[TaskStatus]:
        """Phase 3: 并行执行子任务（拓扑排序 + 信号量限制最大并行数）

        先按拓扑排序分组为 waves，同一 wave 内的节点无依赖关系，可并行执行。
        Wave N 完成后才开始 Wave N+1。

        Args:
            subtasks: 子任务列表

        Returns:
            子任务执行状态列表

        """
        # Phase 3: 拓扑排序分组
        waves = self._topological_sort_subtasks(subtasks)
        if len(waves) > 1:
            wave_sizes = [len(w) for w in waves]
            self.logger.info(f"Subtask waves (topological): {wave_sizes} total_nodes={len(subtasks)}")

        all_results: Dict[str, TaskStatus] = {}

        # P3 部分屏障（依赖失败闸门）：集合内依赖（父节点）终结于 FAILED/ABORTED/
        # CANCELLED 时，其后继 wave 节点不再起跑 —— 缺上游产物的执行只会烧 token
        # （FAST FAIL，与 P3-3 预算哲学一致）。被跳过节点以 ABORTED 终结：
        # result 写明原因、metadata 落审计键，父任务聚合（all COMPLETED）与
        # 报告回注自然可见。同一 wave 内的节点互不依赖，整体继续并行不互相牵连。
        subtask_ids = {s.task_node_id for s in subtasks}
        _DEP_FAILURES = (TaskStatus.FAILED, TaskStatus.ABORTED, TaskStatus.CANCELLED)

        try:
            for wave_idx, wave in enumerate(waves):
                runnable_wave: List[TaskNode] = []
                for node in wave:
                    dep_id = getattr(node, "parent_id", None)
                    dep_status = all_results.get(dep_id) if dep_id in subtask_ids else None
                    if dep_status in _DEP_FAILURES:
                        skip_reason = f"dependency {dep_id} {dep_status.value}"
                        self.logger.warning(
                            f"Subtask {node.task_node_id} skipped by dependency gate: {skip_reason}",
                        )
                        try:
                            meta = getattr(getattr(node, "data", None), "metadata", None)
                            if meta is not None:
                                meta["skipped_by"] = "dependency_gate"
                                meta["skipped_reason"] = skip_reason
                            finalize = getattr(
                                getattr(self._user_workspace, "task_graph", None),
                                "finalize_task",
                                None,
                            )
                            finalized = False
                            if callable(finalize):
                                finalized = bool(
                                    await finalize(
                                        node.task_node_id,
                                        TaskStatus.ABORTED,
                                        f"(依赖未通过: {skip_reason})",
                                    )
                                )
                            if finalized:
                                self._execution_status[node.task_node_id] = TaskStatus.ABORTED
                                await self._emit_subtask_lifecycle_event(node.task_node_id, TaskStatus.ABORTED)
                            else:
                                await self._update_task_status(node.task_node_id, TaskStatus.ABORTED)
                        except Exception:  # noqa: BLE001 — 闸门单节点失败不阻断其余节点
                            self.logger.exception(
                                f"Dependency gate failed to finalize subtask {node.task_node_id}: ",
                            )
                            self._execution_status[node.task_node_id] = TaskStatus.ABORTED
                        all_results[node.task_node_id] = TaskStatus.ABORTED
                    else:
                        runnable_wave.append(node)

                if not runnable_wave:
                    continue
                if len(waves) > 1:
                    self.logger.info(
                        f"Wave {wave_idx + 1}/{len(waves)}: executing {len(runnable_wave)} nodes "
                        f"(skipped {len(wave) - len(runnable_wave)} by dependency gate)...",
                    )

                # 创建执行任务（同一 wave 内并行）
                wave_tasks = {}
                for node in runnable_wave:
                    task = asyncio.create_task(self._execute_subtask_with_semaphore(node))
                    wave_tasks[node.task_node_id] = task
                    self._execution_tasks[node.task_node_id] = task

                # 等待当前 wave 完成
                # （保持 return_exceptions=True 全 wave 屏障：异常已被 semaphore
                # 包装层归一为 FAILED 状态返回，提前唤醒只会拿到残缺结果列表、
                # 中断无关兄弟节点 —— 部分屏障由上方依赖闸门按需裁剪，而非
                # 打散 gather 语义）
                results = await asyncio.gather(*wave_tasks.values(), return_exceptions=True)
                for node, result in zip(runnable_wave, results, strict=True):
                    processed = self._process_single_subtask_result(result, node)
                    all_results[node.task_node_id] = processed
                    # 🔧 修复：异常路径兜底写回终态。_execute_task_graph_recursive /
                    # _execute_subtask_with_semaphore 的 except 列表覆盖不了全部异常
                    # （如 LLMError 400），异常经 gather(return_exceptions=True) 被映射为
                    # FAILED 后只改内存状态，图节点永远停在 running（E2E 2026-09-15:
                    # 子任务 91e22db4 LLM 400 后卡 running，前端"点了停止还在继续"）。
                    # 此处统一收口：结果为终态但图上未终结 → 补写回 + 发生命周期事件。
                    if processed in (TaskStatus.FAILED, TaskStatus.ABORTED):
                        _current = self._execution_status.get(node.task_node_id)
                        if _current not in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.ABORTED, TaskStatus.CANCELLED):
                            try:
                                await self._update_task_status(node.task_node_id, processed)
                            except Exception:  # noqa: BLE001 — 单节点写回失败不阻断其余结果处理
                                self.logger.exception(
                                    f"Failed to finalize subtask {node.task_node_id} as {processed.value}: ",
                                )

            # Return results in original subtask order
            ordered_results = [all_results.get(s.task_node_id, TaskStatus.FAILED) for s in subtasks]
            return ordered_results

        finally:
            # 清理执行任务
            for subtask in subtasks:
                self._execution_tasks.pop(subtask.task_node_id, None)

    def _process_single_subtask_result(
        self, result: Any, subtask: TaskNode
    ) -> TaskStatus:
        """Process a single subtask result and return its status."""
        if isinstance(result, TaskStatus):
            return result
        if isinstance(result, asyncio.CancelledError):
            self.logger.info(f"Subtask {subtask.task_node_id} was cancelled")
            return TaskStatus.ABORTED
        if isinstance(result, Exception):
            self.logger.error(
                f"Subtask {subtask.task_node_id} failed with exception: {result}",
                exc_info=True,
            )
            return TaskStatus.FAILED
        self.logger.error(
            f"Unexpected result type for subtask {subtask.task_node_id}: {type(result)}",
        )
        return TaskStatus.FAILED

    async def _execute_subtask_with_semaphore(self, subtask: TaskNode) -> TaskStatus:
        """使用信号量限制并行的任务执行

        Args:
            subtask: 子任务节点

        Returns:
            任务状态

        """
        async with self._parallel_semaphore:
            self.logger.info(
                f"Starting subtask {subtask.task_node_id} (max_parallel: {self._max_parallel_tasks})",
            )
            try:
                result = await self._execute_task_graph_recursive(subtask)
                self.logger.info(
                    f"Completed subtask {subtask.task_node_id} with status: {result.value}",
                )
                return result
            except asyncio.CancelledError:
                self.logger.info(f"Subtask {subtask.task_node_id} was cancelled")
                return TaskStatus.ABORTED
            except (TaskExecutionError, ToolExecutionError, ValueError, KeyError) as e:
                self.logger.error(
                    f"Subtask {subtask.task_node_id} failed with business error: {e}",
                    exc_info=True,
                )
                return TaskStatus.FAILED
            except (
                TaskNotFoundError,
                TaskStateError,
                ValidationError,
                StorageError,
                ConfigurationError,
                CheckpointError,
            ) as e:
                self.logger.error(
                    f"Subtask {subtask.task_node_id} failed with error: {e}",
                    exc_info=True,
                )
                return TaskStatus.FAILED

    def _process_subtask_results(
        self,
        results: List[Any],
        subtasks: List[TaskNode],
    ) -> List[TaskStatus]:
        """处理子任务执行结果

        Args:
            results: 执行结果列表
            subtasks: 子任务列表

        Returns:
            任务状态列表

        """
        status_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                if isinstance(result, asyncio.CancelledError):
                    self.logger.info(f"Subtask {subtasks[i].task_node_id} was cancelled")
                    status_results.append(TaskStatus.ABORTED)
                else:
                    self.logger.error(
                        f"Subtask {subtasks[i].task_node_id} failed with exception: {result}",
                    )
                    status_results.append(TaskStatus.FAILED)
            elif isinstance(result, TaskStatus):
                status_results.append(result)
            else:
                self.logger.warning(
                    f"Unexpected result type for subtask {subtasks[i].task_node_id}: {type(result)}",
                )
                status_results.append(TaskStatus.FAILED)

        return status_results

    def set_max_parallel_tasks(self, max_parallel: int) -> None:
        """设置最大并行任务节点数

        Args:
            max_parallel: 最大并行数（必须 >= 1）

        """
        if max_parallel < 1:
            raise ValueError(f"max_parallel must be >= 1, got {max_parallel}")

        old_max = self._max_parallel_tasks
        self._max_parallel_tasks = max_parallel

        # 创建新的信号量（旧信号量仍在使用中的任务会继续使用旧的）
        self._parallel_semaphore = asyncio.Semaphore(self._max_parallel_tasks)

        self.logger.info(f"Max parallel tasks updated from {old_max} to {self._max_parallel_tasks}")

    def get_max_parallel_tasks(self) -> int:
        """获取当前最大并行任务节点数

        Returns:
            最大并行数

        """
        return self._max_parallel_tasks

    async def process_message(self, message: UserInputMessage) -> Any:
        """处理消息

        Args:
            message: 用户消息

        Returns:
            处理结果

        """
        task_node_id = message.task_node_id

        # 添加用户消息到对话
        await self._add_message_to_conversation(message)

        # 确保根任务存在
        root_task = await self._ensure_root_task_exists(message)

        # 获取任务节点
        task_node, task_node_id = self._get_or_create_task_node(task_node_id, root_task)

        # 获取或创建执行引擎
        self._node_executors[task_node_id] = TaskNodeExecutionEngine(
            task_node=task_node,
            user_workspace=self._user_workspace,
            message_processor=self._message_processor,
            llm_service=self._llm_service,
            tool_call_service=self._tool_call_service,
            event_bus=self._event_bus,
            config=self._config,
            agent=self._agent,
        )

        # 同步任务状态
        if task_node_id:
            await self._sync_task_status(task_node_id)

        return None

    async def _add_message_to_conversation(self, message: UserInputMessage) -> None:
        """添加用户消息到当前对话

        Args:
            message: 用户消息

        """
        message_content = getattr(message, "text", str(message))

        if not self._user_workspace.current_conversation:
            self.logger.warning(
                "No current conversation found, user message not added to conversation history",
            )
            return

        from dawei.entity.lm_messages import UserMessage

        self._user_workspace.current_conversation.say(UserMessage(content=message_content))
        self.logger.info(
            f"Added user message to conversation {self._user_workspace.current_conversation.id}. Message count: {self._user_workspace.current_conversation.message_count}",
        )

        # 保存对话
        try:
            save_success = await self._user_workspace.save_current_conversation()
            if save_success:
                self.logger.info("Successfully saved conversation before processing")
            else:
                self.logger.warning("Failed to save conversation before processing")
        except Exception as save_error:
            self.logger.error(f"Error saving conversation: {save_error}", exc_info=True)

    async def _ensure_root_task_exists(self, message: UserInputMessage) -> TaskNode:
        """确保根任务存在，如果不存在则创建

        Args:
            message: 用户消息

        Returns:
            根任务节点

        """
        root_task = await self._user_workspace.task_graph.get_root_task()
        if root_task:
            return root_task

        # 创建根任务
        from dawei.task_graph.task_node_data import TaskData

        root_task_id = str(uuid.uuid4())
        task_data = TaskData(
            task_node_id=root_task_id,
            description=message,
            mode=self._user_workspace.mode,
            context=self._user_workspace.create_task_context(),
        )
        root_task = await self._user_workspace.task_graph.create_root_task(task_data)
        self.logger.info(
            f"Created root task: {root_task_id} with mode: {self._user_workspace.mode}",
        )
        return root_task

    def _get_or_create_task_node(
        self,
        task_node_id: str | None,
        root_task: TaskNode,
    ) -> tuple[TaskNode, str]:
        """获取或创建任务节点

        Args:
            task_node_id: 任务ID
            root_task: 根任务

        Returns:
            (任务节点, 任务ID)元组

        """
        if task_node_id and task_node_id in self._node_executors:
            # 使用已有的执行引擎对应的任务节点
            return self._node_executors[task_node_id].task_node, task_node_id
        if task_node_id:
            # 尝试获取任务节点（如果失败则使用根任务）
            try:
                # Note: This assumes get_task is async, but the parent context may vary
                # For now, we'll use root_task as fallback
                return root_task, root_task.task_node_id
            except Exception:
                return root_task, root_task.task_node_id
        else:
            # 使用根任务
            return root_task, root_task.task_node_id

    async def _sync_task_status(self, task_node_id: str) -> None:
        """同步任务状态

        Args:
            task_node_id: 任务ID

        """
        try:
            # 检查 task_node_id 是否有效
            if not task_node_id or task_node_id is None:
                return

            # 检查 task_graph 是否存在
            if not self._user_workspace.task_graph:
                return

            # 获取执行引擎中的任务状态
            if task_node_id in self._node_executors:
                executor = self._node_executors[task_node_id]
                await executor.get_execution_status()

                # 获取任务图中的任务状态
                task_node = await self._user_workspace.task_graph.get_task(task_node_id)
                if task_node:
                    # 如果状态不一致，同步到任务图
                    if task_node.status != self._execution_status.get(task_node_id):
                        await self._user_workspace.task_graph.update_task_status(
                            task_node_id,
                            task_node.status,
                        )
                        self._execution_status[task_node_id] = task_node.status

        except (TaskNotFoundError, TaskStateError) as e:
            self.logger.error(f"Task error syncing status for {task_node_id}: {e}", exc_info=True)
            raise  # Fast fail: re-raise task errors
        except StorageError as e:
            self.logger.error(
                f"Storage error syncing status for {task_node_id}: {e}",
                exc_info=True,
            )
            raise  # Fast fail: re-raise storage errors
        except (OSError, ConnectionError) as e:
            # 作为最后的保障，但记录为未预期的错误
            self.logger.error(
                f"Unexpected error syncing task status for {task_node_id}: {e}",
                exc_info=True,
            )
            raise  # Fast fail: re-raise unexpected errors

    async def cancel_task_execution(self, task_node_id: str) -> bool:
        """取消任务执行

        Args:
            task_node_id: 任务ID

        Returns:
            是否成功取消

        """
        try:
            # 取消执行任务
            if task_node_id in self._execution_tasks:
                self._execution_tasks[task_node_id].cancel()
                del self._execution_tasks[task_node_id]

            # 取消节点执行引擎
            if task_node_id in self._node_executors:
                executor = self._node_executors[task_node_id]
                # P2-E 取消回收审计：拆除前回收已消耗 tokens(无论 CancelledError
                # 落点在 execute_task 内还是外)，并触发补偿持久化把记账落盘
                reclaim = getattr(executor, "reclaim_accounting_on_cancel", None)
                if callable(reclaim):
                    try:
                        wrote = bool(reclaim(reason="cancel_task_execution"))
                    except Exception:  # noqa: BLE001 — 回收失败不阻断取消
                        self.logger.exception(f"Accounting reclaim failed for {task_node_id}: ")
                        wrote = False
                    if wrote:
                        graph = getattr(self._user_workspace, "task_graph", None)
                        emit_updated = getattr(graph, "emit_graph_updated", None)
                        if callable(emit_updated):
                            try:
                                await emit_updated(task_node_id, reason="cancel_accounting_reclaim")
                            except Exception:  # noqa: BLE001 — 持久化失败不阻断取消
                                self.logger.exception(f"Compensating persist failed for {task_node_id}: ")
                await executor.cancel_task_execution()
                # 清理引擎引用,防止内存泄漏
                del self._node_executors[task_node_id]

            # 清理状态
            if task_node_id in self._execution_status:
                del self._execution_status[task_node_id]

            self.logger.info(f"Task execution cancelled: {task_node_id}")
            return True

        except (TaskNotFoundError, TaskStateError):
            self.logger.exception("Task error cancelling {task_node_id}: ")
            return False
        except KeyError as e:
            self.logger.warning(f"Task {task_node_id} not found for cancellation: {e}")
            return True  # 如果任务不存在，认为已经取消
        except (OSError, RuntimeError) as e:
            # 作为最后的保障
            self.logger.error(
                f"Unexpected error cancelling task execution for {task_node_id}: {e}",
                exc_info=True,
            )
            raise  # Fast fail: re-raise unexpected errors

    async def get_task_execution_status(self, task_node_id: str) -> Dict[str, Any]:
        """获取任务执行状态

        Args:
            task_node_id: 任务ID

        Returns:
            执行状态信息

        """
        try:
            if task_node_id in self._node_executors:
                executor = self._node_executors[task_node_id]
                return await executor.get_execution_status()
            return {
                "task_node_id": task_node_id,
                "is_executing": False,
                "last_checkpoint_time": 0,
                "execution_time": 0,
            }

        except (KeyError, TaskNotFoundError) as e:
            self.logger.warning(f"Task {task_node_id} not found: {e}")
            return {
                "task_node_id": task_node_id,
                "is_executing": False,
                "last_checkpoint_time": 0,
                "execution_time": 0,
            }
        except (KeyError, AttributeError, RuntimeError) as e:
            self.logger.error(
                f"Unexpected error getting task execution status for {task_node_id}: {e}",
                exc_info=True,
            )
            raise  # Fast fail: re-raise unexpected errors instead of returning empty dict

    async def get_current_step_description(self) -> str:
        """获取当前正在执行的步骤描述

        Returns:
            str: 当前步骤描述

        """
        if self._current_task_node_id:
            # 尝试从任务图获取任务节点信息
            try:
                task_node = await self._user_workspace.task_graph.get_task(
                    self._current_task_node_id,
                )
                if task_node:
                    return f"执行任务: {task_node.description or task_node.task_node_id}"
            except (TaskNotFoundError, StorageError) as e:
                self.logger.debug(f"Could not retrieve task details for step description: {e}")
            except (ValueError, RuntimeError) as e:
                self.logger.error(
                    f"Unexpected error getting current step description: {e}",
                    exc_info=True,
                )

        return "正在执行"

    async def stop(self) -> str:
        """停止任务图执行

        Returns:
            str: 停止结果的摘要

        """
        self.logger.info("Stopping task graph execution")

        # 🔧 修复：先置停止标志，收尾路径（_execute_task_with_retries）据此
        # 跳过"启动 pending 子任务"，避免 stop 之后又把新子任务拉起来跑。
        self._stop_requested = True

        # 取消所有正在执行的任务
        cancelled_count = 0
        for _task_node_id, task in self._execution_tasks.items():
            if not task.done():
                task.cancel()
                cancelled_count += 1

        # 🔧 修复：唤醒所有节点执行引擎（含根任务）。
        # _execution_tasks 只登记子任务 asyncio task，根任务的 _run_task_loop 不在其中
        # （此前日志「已停止 0 个正在执行的任务」即此因）。request_stop 通过停止事件
        # 即时中断工具/追问阶段的人机等待，而不是等 300s 超时后停止才生效。
        woken_engines = 0
        for engine in self._node_executors.values():
            if hasattr(engine, "request_stop"):
                engine.request_stop()
                woken_engines += 1

        # 等待所有任务完成（被取消）
        if cancelled_count > 0:
            # 🔧 修复：等待上限 10s。子任务可能卡在不可中断点（如同步工具跑在线程池），
            # 此前无条件 gather 会让 agent.stop() 永久挂起 → 停止请求无响应。
            _pending = [t for t in self._execution_tasks.values() if not t.done()]
            if _pending:
                _, _stuck = await asyncio.wait(set(_pending), timeout=10.0)
                for _t in _stuck:
                    self.logger.warning(
                        f"Cancelled task did not finish within 10s after stop, abandoning: {_t}",
                    )

        result_summary = f"已停止 {cancelled_count} 个正在执行的任务, 唤醒 {woken_engines} 个执行引擎"

        # 🔧 修复：把仍未终结的节点（含根任务）统一标记为 ABORTED。此前 stop 只
        # cancel asyncio 任务，若协程在状态写回前被取消/卡死，图节点会残留
        # running/pending，前端重连恢复时再次当作活跃任务展示（"点了停止还在继续"）。
        _terminal = {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.ABORTED, TaskStatus.CANCELLED}
        for _node_id, _status in list(self._execution_status.items()):
            if _status in _terminal:
                continue
            try:
                # 🔧 修复：状态写回加 5s 上限（FAST FAIL）。写回内部会发事件→持久化→
                # 再获取图锁，若图锁被卡死的工作协程长期持有，stop 会跟着挂起，
                # 前端迟迟收不到 agent_stopped（表现为"点了停止没反应"）。
                await asyncio.wait_for(self._update_task_status(_node_id, TaskStatus.ABORTED), timeout=5.0)
            except Exception:  # noqa: BLE001 — 单节点写回失败/超时不影响其余收口
                self.logger.exception(f"Failed to mark node {_node_id} ABORTED during stop: ")

        # 清理执行引擎
        self._node_executors.clear()
        self._execution_status.clear()
        self._execution_tasks.clear()

        self.logger.info(f"Task graph execution stopped: {result_summary}")
        return result_summary

    async def cleanup(self) -> None:
        """清理资源"""
        try:
            # 取消所有执行任务
            for _task_node_id, task in self._execution_tasks.items():
                if not task.done():
                    task.cancel()

            # 清理执行引擎
            self._node_executors.clear()
            self._execution_status.clear()
            self._execution_tasks.clear()

            self.logger.info("Task graph execution engine cleaned up")

        except (asyncio.CancelledError, RuntimeError) as e:
            self.logger.warning(f"Cleanup interrupted or runtime error: {e}")
            raise  # Fast fail: re-raise cleanup errors
        except OSError as e:
            self.logger.error(f"Unexpected error during cleanup: {e}", exc_info=True)
            raise  # Fast fail: re-raise unexpected cleanup errors
