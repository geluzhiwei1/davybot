# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""任务执行引擎
负责任务的执行、消息处理和工具调用

重构版本：使用接口抽象而非直接依赖具体实现
"""

import asyncio
import uuid
from typing import Any

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
from dawei.entity.task_types import TaskStatus
from dawei.entity.user_input_message import UserInputMessage

# 导入新的接口
from dawei.interfaces import ILLMService, IMessageProcessor, IToolCallService
from dawei.logg.logging import get_logger
from dawei.task_graph.task_node import TaskNode
from dawei.workspace.user_workspace import UserWorkspace

from .task_node_executor import TaskNodeExecutionEngine


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
        if not hasattr(agent, 'event_bus'):
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
        self._node_executors: dict[str, TaskNodeExecutionEngine] = {}

        # 执行状态跟踪
        self._execution_status: dict[str, TaskStatus] = {}
        self._execution_tasks: dict[str, asyncio.Task] = {}

        # 锁
        self._lock = asyncio.Lock()

        # 当前执行的任务节点ID（用于获取当前步骤描述）
        self._current_task_node_id: str | None = None

        # 最大并行任务节点数限制（从配置读取，默认为2）
        self._max_parallel_tasks = getattr(config, "max_parallel_tasks", 2)
        self._parallel_semaphore = asyncio.Semaphore(self._max_parallel_tasks)
        self.logger.info(
            f"TaskGraphExecutionEngine initialized with max_parallel_tasks={self._max_parallel_tasks}",
        )

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
        from dawei.core.events import TaskEventType, emit_typed_event

        task_completed_data = {
            "result": f"Task completed with status: {status.value}",
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
        self.logger.info(f"Emitted TASK_COMPLETED event for task {task_id}")

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
        executor = self._get_or_create_executor(current_task, task_node_id)

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

    def _get_or_create_executor(
        self,
        current_task: TaskNode,
        task_node_id: str,
    ) -> "TaskNodeExecutionEngine":
        """获取或创建任务执行引擎

        Args:
            current_task: 当前任务节点
            task_node_id: 任务节点ID

        Returns:
            TaskNodeExecutionEngine实例

        """
        if task_node_id not in self._node_executors:
            self._node_executors[task_node_id] = TaskNodeExecutionEngine(
                task_node=current_task,
                user_workspace=self._user_workspace,
                message_processor=self._message_processor,
                llm_service=self._llm_service,
                tool_call_service=self._tool_call_service,
                event_bus=self._event_bus,
                config=self._config,
                agent=self._agent,  # 传递agent引用
            )
        return self._node_executors[task_node_id]

    async def _update_task_status(self, task_node_id: str, status: TaskStatus) -> None:
        """更新任务状态

        Args:
            task_node_id: 任务节点ID
            status: 新状态

        """
        await self._user_workspace.task_graph.update_task_status(task_node_id, status)
        self._execution_status[task_node_id] = status

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
        # 超时重试配置
        max_retries = 2  # 最多重试2次
        base_delay = 2.0  # 基础延迟2秒

        for attempt in range(max_retries + 1):
            try:
                # 执行当前任务（等待直到完成或中止）
                await executor.execute_task()

                # 成功执行，退出重试循环
                break

            except TimeoutError:
                # 超时错误处理
                if attempt < max_retries:
                    # 计算指数退避延迟
                    delay = base_delay * (2**attempt)
                    self.logger.warning(
                        f"Task {task_node_id} timeout on attempt {attempt + 1}/{max_retries + 1}, retrying in {delay:.1f}s...",
                    )

                    # 等待后重试，使用更长的超时
                    await asyncio.sleep(delay)

                    # 重新创建executor以避免状态污染
                    executor = self._get_or_create_executor(current_task, task_node_id)

                    # 下次重试时使用更长的超时时间（1.5倍递增）
                    # 注意：这里需要将超时信息传递给executor
                    continue
                # 重试次数用尽，记录错误并返回失败状态
                self.logger.exception(
                    f"Task {task_node_id} failed after {max_retries + 1} attempts due to timeout",
                )
                return TaskStatus.FAILED

            except (TimeoutError, OSError, RuntimeError):
                # 其他错误不重试，直接抛出
                self.logger.exception(f"Task {task_node_id} encountered unexpected error: ")
                raise

        # 🔧 修复：不管当前状态如何，都要检查是否有子任务或子图需要处理
        # 这是为了避免主任务标记为COMPLETED但子任务还在执行的情况
        subtasks = await self._user_workspace.task_graph.get_subtasks(task_node_id)
        has_subtasks = bool(subtasks)
        has_subgraph = bool(current_task.sub_graph)

        if has_subtasks or has_subgraph:
            # 有子任务或子图，需要等待它们完成
            self.logger.info(f"Task {task_node_id} executor finished, processing {len(subtasks) if has_subtasks else 0} subtasks or subgraph before finalizing status...")
            final_status = await self._handle_subtasks_and_subgraphs(current_task, task_node_id)
        else:
            # 没有子任务或子图，使用当前任务的状态
            final_status = current_task.status
            self.logger.info(f"Task {task_node_id} executor finished with no subtasks or subgraph, using current status: {final_status.value}")

        # 更新任务状态
        await self._update_task_status(task_node_id, final_status)
        self.logger.info(
            f"Task {task_node_id} execution completed with status: {final_status.value}",
        )
        return final_status

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
        # 获取子任务
        subtasks = await self._user_workspace.task_graph.get_subtasks(task_node_id)

        if subtasks:
            # 并行执行子任务并检查结果
            return await self._execute_subtasks_and_check_status(subtasks)

        # 没有子任务，检查是否有子图需要执行
        if current_task.sub_graph:
            # 递归执行子图
            return await self.execute_task_graph(current_task.sub_graph)

        # 没有子任务也没有子图
        self.logger.info(
            f"Task {task_node_id} executor finished without explicit completion, checking status...",
        )
        return current_task.status

    async def _execute_subtasks_and_check_status(self, subtasks: list[TaskNode]) -> TaskStatus:
        """并行执行子任务并检查状态

        Args:
            subtasks: 子任务列表

        Returns:
            任务状态（COMPLETED或FAILED）

        """
        # 并行执行子任务
        subtask_results = await self._execute_subtasks_parallel(subtasks)

        # 检查子任务执行结果
        if all(result == TaskStatus.COMPLETED for result in subtask_results):
            return TaskStatus.COMPLETED
        # 如果有子任务失败，父任务也标记为失败
        return TaskStatus.FAILED

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
        await self._update_task_status(task_node_id, TaskStatus.FAILED)
        return TaskStatus.FAILED

    async def _execute_subtasks_parallel(self, subtasks: list[TaskNode]) -> list[TaskStatus]:
        """并行执行子任务（受信号量限制最大并行数）

        Args:
            subtasks: 子任务列表

        Returns:
            子任务执行状态列表

        """
        # 创建执行任务
        execution_tasks = [asyncio.create_task(self._execute_subtask_with_semaphore(subtask)) for subtask in subtasks]

        # 记录执行任务
        for subtask, task in zip(subtasks, execution_tasks, strict=False):
            self._execution_tasks[subtask.task_node_id] = task

        try:
            # 等待所有子任务完成
            results = await asyncio.gather(*execution_tasks, return_exceptions=True)
            return self._process_subtask_results(results, subtasks)

        finally:
            # 清理执行任务
            for subtask in subtasks:
                self._execution_tasks.pop(subtask.task_node_id, None)

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
        results: list[Any],
        subtasks: list[TaskNode],
    ) -> list[TaskStatus]:
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
                await self._node_executors[task_node_id].cancel_task_execution()
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

    async def get_task_execution_status(self, task_node_id: str) -> dict[str, Any]:
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

        # 取消所有正在执行的任务
        cancelled_count = 0
        for _task_node_id, task in self._execution_tasks.items():
            if not task.done():
                task.cancel()
                cancelled_count += 1

        # 等待所有任务完成（被取消）
        if cancelled_count > 0:
            await asyncio.gather(*self._execution_tasks.values(), return_exceptions=True)

        result_summary = f"已停止 {cancelled_count} 个正在执行的任务"

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
