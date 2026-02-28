# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Scheduler Engine and Manager

定时任务调度引擎和全局管理器
采用 Server 级调度器架构，实现全局单例管理
"""

import asyncio
import contextlib
import logging
import uuid
from datetime import UTC, datetime, timezone
from pathlib import Path

from dawei.agentic.agent_execution_service import agent_execution_service
from dawei.core.exceptions import ValidationError
from dawei.entity.scheduled_task import ScheduledTask, TriggerStatus
from dawei.workspace.scheduled_task_storage import ScheduledTaskStorage
from dawei.workspace.workspace_manager import workspace_manager

logger = logging.getLogger(__name__)


class TaskExecutionLock:
    """任务执行锁 - 防止任务重复执行

    使用 asyncio.Lock 为每个任务 ID 创建独立的锁
    确保同一个任务在同一时间只能被一个 worker 执行
    """

    def __init__(self):
        """初始化任务执行锁"""
        self._locks: dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

    async def acquire(self, task_id: str) -> bool:
        """尝试获取任务执行锁

        Args:
            task_id: 任务 ID

        Returns:
            True 如果成功获取锁，False 如果任务已被其他 worker 执行

        """
        async with self._global_lock:
            if task_id not in self._locks:
                # 创建新的任务锁并立即获取
                self._locks[task_id] = asyncio.Lock()

            # 获取锁引用
            lock = self._locks[task_id]

        # 尝试获取锁（非阻塞）
        try:
            # 使用 wait_for 实现非阻塞尝试获取
            await asyncio.wait_for(lock.acquire(), timeout=0.1)
            return True
        except TimeoutError:
            # 锁已被持有，说明任务正在执行
            return False

    async def release(self, task_id: str) -> None:
        """释放任务执行锁

        Args:
            task_id: 任务 ID

        """
        async with self._global_lock:
            if task_id in self._locks:
                lock = self._locks[task_id]
                if lock.locked():
                    lock.release()

                # 清理已完成的任务锁（保留最近使用的）
                if len(self._locks) > 100:
                    # 清理一半的锁
                    items_to_remove = list(self._locks.keys())[:50]
                    for task_id_to_remove in items_to_remove:
                        if not self._locks[task_id_to_remove].locked():
                            del self._locks[task_id_to_remove]


class SchedulerEngine:
    """单 workspace 调度引擎

    负责单个 workspace 的任务调度和执行
    定时任务完全复用 AgentExecutionService，与 WebSocket 调用一致
    """

    def __init__(self, workspace_id: str, workspace_path: str):
        """初始化调度引擎

        Args:
            workspace_id: workspace ID
            workspace_path: workspace 路径

        """
        self.workspace_id = workspace_id
        self.workspace_path = Path(workspace_path)

        self.storage = ScheduledTaskStorage(str(workspace_path))

        self._running = False
        self._check_interval = 1.0
        self._check_task: asyncio.Task | None = None

        self._execution_queue: asyncio.Queue = asyncio.Queue()
        self._max_concurrent = 3
        self._workers: list[asyncio.Task] = []

        # ✅ 添加任务执行锁
        self._execution_lock = TaskExecutionLock()

    async def start(self) -> None:
        """启动调度器"""
        if self._running:
            logger.warning(
                f"[SCHEDULER] Scheduler already running for workspace {self.workspace_id}",
            )
            return

        self._running = True
        await self.storage._ensure_loaded()

        self._check_task = asyncio.create_task(self._check_loop())

        for i in range(self._max_concurrent):
            worker = asyncio.create_task(self._worker(f"worker-{i}"))
            self._workers.append(worker)

        logger.info(f"[SCHEDULER] Started for workspace {self.workspace_id}")

    async def stop(self) -> None:
        """停止调度器"""
        if not self._running:
            return

        self._running = False

        # Cancel check task
        if self._check_task and not self._check_task.done():
            self._check_task.cancel()
            with contextlib.suppress(TimeoutError, asyncio.CancelledError, RuntimeError):
                await asyncio.wait_for(self._check_task, timeout=1.0)

        # Cancel workers
        for worker in self._workers:
            if not worker.done():
                worker.cancel()

        # Wait for workers to finish
        if self._workers:
            with contextlib.suppress(TimeoutError, RuntimeError):
                await asyncio.wait_for(
                    asyncio.gather(*self._workers, return_exceptions=True),
                    timeout=2.0,
                )

        self._workers.clear()
        logger.info(f"[SCHEDULER] Stopped for workspace {self.workspace_id}")

    async def _check_loop(self) -> None:
        """主检查循环 - 每秒检查到期任务"""
        while self._running:
            try:
                due_tasks = await self.storage.get_due_tasks()
                for task in due_tasks:
                    await self._execution_queue.put(task)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[SCHEDULER] Check loop error: {e}", exc_info=True)

            await asyncio.sleep(self._check_interval)

    async def _worker(self, name: str) -> None:
        """工作线程 - 从队列中获取任务并执行

        Args:
            name: 工作线程名称

        """
        while self._running:
            try:
                task: ScheduledTask = await self._execution_queue.get()

                # ✅ 尝试获取任务执行锁（防止重复执行）
                acquired = await self._execution_lock.acquire(task.task_id)
                if not acquired:
                    logger.debug(
                        f"[SCHEDULER] Worker {name}: Task {task.task_id} already being executed, skipping"
                    )
                    self._execution_queue.task_done()
                    continue

                try:
                    # 执行任务
                    await self._execute_task(task)
                finally:
                    # 释放任务锁
                    await self._execution_lock.release(task.task_id)

                self._execution_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[SCHEDULER] Worker {name} error: {e}", exc_info=True)

    async def _execute_task(self, task: ScheduledTask) -> None:
        """执行定时任务 - 直接调用 AgentExecutionService

        定时任务与 WebSocket 任务使用完全相同的执行流程
        支持失败重试机制

        Args:
            task: 要执行的任务

        """
        try:
            # 更新任务状态
            task.status = TriggerStatus.TRIGGERED
            task.triggered_at = datetime.now(UTC)
            await self.storage.save_task(task)

            logger.info(
                f"[SCHEDULER] Executing task: {task.description} "
                f"(type: {task.execution_type}, schedule: {task.schedule_type.value})"
            )

            # 获取超时时间（从 metadata 中读取，默认1小时）
            timeout = 3600  # 默认1小时
            if task.metadata:
                timeout = task.metadata.get("timeout", timeout)

            # 执行定时任务（仅支持 message 类型），带超时控制和重试机制
            max_retries = task.max_retries if task.max_retries is not None else 0

            for attempt in range(max_retries + 1):
                try:
                    # 执行任务
                    await asyncio.wait_for(self._execute_message_task(task), timeout=timeout)

                    # 执行成功，重置重试计数
                    task.retry_count = 0
                    break

                except Exception as exec_error:
                    task.retry_count = attempt

                    # 如果还有重试机会
                    if attempt < max_retries:
                        # 计算重试延迟（指数退避）
                        if task.retry_interval:
                            retry_delay = task.retry_interval
                        else:
                            retry_delay = min(2**attempt, 300)  # 最大5分钟

                        logger.warning(
                            f"[SCHEDULER] Task {task.task_id} execution failed (attempt {attempt + 1}/{max_retries + 1}): {exec_error}. "
                            f"Retrying in {retry_delay} seconds..."
                        )

                        await asyncio.sleep(retry_delay)
                        continue
                    else:
                        # 重试次数用尽，任务失败
                        raise Exception(f"Task failed after {max_retries + 1} attempts: {exec_error}")

            # 执行成功，处理重复调度
            if task.should_repeat():
                try:
                    task.schedule_next()
                    await self.storage.save_task(task)
                    logger.info(
                        f"[SCHEDULER] Task {task.task_id} ({task.schedule_type.value}) "
                        f"rescheduled for {task.trigger_time.isoformat()}",
                    )
                except ValueError as e:
                    # Cron表达式错误
                    logger.exception(f"[SCHEDULER] Cron expression error for task {task.task_id}: {e}")
                    task.status = TriggerStatus.FAILED
                    task.last_error = str(e)
                    await self.storage.save_task(task)
            else:
                # 任务完成
                task.status = TriggerStatus.COMPLETED
                await self.storage.save_task(task)
                logger.info(f"[SCHEDULER] Task {task.task_id} completed")

        except Exception as e:
            logger.error(f"[SCHEDULER] Failed to execute task {task.task_id}: {e}", exc_info=True)
            task.status = TriggerStatus.FAILED
            task.last_error = str(e)
            await self.storage.save_task(task)

    async def _execute_message_task(self, task: ScheduledTask) -> None:
        """执行消息型定时任务

        完全复用 AgentExecutionService，与 WebSocket 调用一致
        支持在 execution_data 中指定 llm 和 mode 参数

        Args:
            task: 定时任务
        """
        execution_data = task.execution_data or {}
        message = execution_data.get("message", "")

        if not message:
            raise ValueError("Message task requires 'message' field in execution_data")

        # 获取可选的 llm 和 mode 参数
        llm = execution_data.get("llm")
        mode = execution_data.get("mode")

        logger.info(
            f"[SCHEDULER] Executing message task: {task.description}\n"
            f"Message: {message[:100]}...\n"
            f"LLM: {llm or '(workspace default)'}\n"
            f"Mode: {mode or '(workspace default)'}"
        )

        # 获取 workspace（使用与 WebSocket 相同的方式）
        workspace_info = workspace_manager.get_workspace_by_id(task.workspace_id)
        if not workspace_info:
            raise ValidationError("workspace_id", task.workspace_id, f"Workspace not found: {task.workspace_id}")

        workspace_path = workspace_info.get("path")
        if not workspace_path:
            raise ValidationError("workspace_id", task.workspace_id, f"Workspace path missing: {task.workspace_id}")

        # 创建 UserWorkspace 实例并确保初始化（与 WebSocket 一致）
        from dawei.workspace.user_workspace import UserWorkspace
        user_workspace = UserWorkspace(workspace_path)
        if not user_workspace.is_initialized():
            await user_workspace.initialize()
            logger.info(f"[SCHEDULER] Initialized UserWorkspace for {task.workspace_id}")

        # 创建虚拟会话 ID（用于 conversation 记录）
        virtual_session_id = f"scheduled-{task.task_id}-{task.repeat_count}"
        virtual_task_id = str(uuid.uuid4())

        logger.info(
            f"[SCHEDULER] Virtual session: {virtual_session_id}, task: {virtual_task_id}"
        )

        try:
            # 获取 LLM 模型（从 workspace 设置）
            settings = await user_workspace.get_settings()
            llm_model = llm or settings.get("llm_model", "deepseek/deepseek-chat")
            agent_mode = mode or settings.get("agent_mode", "orchestrator")

            logger.info(
                f"[SCHEDULER] Config: LLM={llm_model}, Mode={agent_mode} "
                f"{'(override)' if llm or mode else '(workspace default)'}"
            )

            # 1. 创建 Agent（使用与 WebSocket 相同的方法）
            from dawei.agentic.agent import Agent
            agent = await Agent.create_with_default_engine(user_workspace)
            logger.info(f"[SCHEDULER] Agent created successfully")

            # 2. 初始化 Agent
            await agent.initialize()
            logger.info(f"[SCHEDULER] Agent initialized successfully")

            # 3. 配置 mode（如果指定）
            if mode:
                agent.config.mode = mode
                logger.info(f"[SCHEDULER] Agent mode configured: {mode}")

            # 4. 创建或加载 conversation（用于定时任务）
            from dawei.conversation.conversation import Conversation
            conversation = Conversation(
                id=virtual_session_id,
                title=f"📅 {task.description} (第{task.repeat_count + 1}次)",
                task_type="scheduled",
                source_task_id=task.task_id,
                agent_mode=agent.config.mode,
                llm_model=llm_model,
            )

            # 设置为当前 conversation
            user_workspace.current_conversation = conversation

            # 5. 创建用户输入消息
            from dawei.entity.user_input_message import UserInputMessage
            user_input = UserInputMessage(text=message)

            # 6. 添加用户消息到 conversation
            from dawei.entity.lm_messages import UserMessage

            user_message = UserMessage(
                id=str(uuid.uuid4()),
                content=message,
                timestamp=datetime.now(UTC),
            )

            conversation.messages.append(user_message)
            conversation.message_count = len(conversation.messages)

            # 保存 conversation
            user_workspace.current_conversation = conversation
            await user_workspace.save_current_conversation()

            logger.info(
                f"[SCHEDULER] Conversation: {virtual_session_id}, "
                f"Message count: {conversation.message_count}"
            )

            # 7. 执行 Agent（使用与 WebSocket 相同的方法）
            logger.info(f"[SCHEDULER] Running agent...")
            await agent.process_message(user_input)
            logger.info(f"[SCHEDULER] Agent execution completed")

            # 8. 保存更新后的 conversation
            user_workspace.current_conversation = conversation
            await user_workspace.save_current_conversation()

            logger.info(
                f"[SCHEDULER] Task {task.task_id} executed successfully.\n"
                f"  Conversation: {virtual_session_id}\n"
                f"  Messages: {conversation.message_count}\n"
            )

        except Exception as e:
            logger.error(f"[SCHEDULER] Agent execution failed: {e}", exc_info=True)
            raise Exception(f"Agent execution failed: {e}") from e


class SchedulerManager:
    """全局调度管理器 (单例)

    管理所有 workspace 的调度器
    """

    def __init__(self):
        self._engines: dict[str, SchedulerEngine] = {}
        self._lock = asyncio.Lock()
        self._initialized = False

    async def initialize(self) -> None:
        """初始化（在 server lifespan 启动时调用）"""
        if self._initialized:
            logger.warning("[SCHEDULER] Manager already initialized")
            return

        self._initialized = True
        logger.info("[SCHEDULER] Manager initialized")

    async def shutdown(self) -> None:
        """关闭（在 server lifespan 关闭时调用）"""
        async with self._lock:
            for workspace_id, engine in list(self._engines.items()):
                try:
                    await engine.stop()
                except Exception as e:
                    logger.error(
                        f"[SCHEDULER] Error stopping engine for {workspace_id}: {e}",
                        exc_info=True,
                    )
            self._engines.clear()

        self._initialized = False
        logger.info("[SCHEDULER] Manager shutdown")

    async def get_scheduler(self, workspace_id: str, workspace_path: str) -> SchedulerEngine:
        """获取或创建 workspace 调度器

        Args:
            workspace_id: workspace ID
            workspace_path: workspace 路径

        Returns:
            SchedulerEngine 实例

        """
        async with self._lock:
            if workspace_id not in self._engines:
                engine = SchedulerEngine(workspace_id, workspace_path)
                await engine.start()
                self._engines[workspace_id] = engine
                logger.info(f"[SCHEDULER] Created scheduler for workspace {workspace_id}")
            return self._engines[workspace_id]

    async def remove_workspace(self, workspace_id: str) -> None:
        """移除 workspace（当 workspace 关闭时）

        Args:
            workspace_id: workspace ID

        """
        async with self._lock:
            if workspace_id in self._engines:
                await self._engines[workspace_id].stop()
                del self._engines[workspace_id]
                logger.info(f"[SCHEDULER] Removed scheduler for workspace {workspace_id}")

    def is_initialized(self) -> bool:
        """检查管理器是否已初始化"""
        return self._initialized

    async def get_active_workspaces(self) -> list[str]:
        """获取活跃的 workspace ID 列表"""
        async with self._lock:
            return list(self._engines.keys())


# 全局单例
scheduler_manager = SchedulerManager()


__all__ = [
    "SchedulerEngine",
    "SchedulerManager",
    "scheduler_manager",
]
