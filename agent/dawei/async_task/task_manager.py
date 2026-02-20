# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""异步任务管理器实现

提供统一的异步任务管理、状态跟踪、重试机制和生命周期管理功能。
"""

import asyncio
import contextlib
import threading
import time
import traceback
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timezone
from typing import Any

from dawei.logg.logging import get_logger

from .interfaces import IAsyncTaskManager, ICheckpointService, ITaskExecutor
from .task_context import SimpleCheckpointService, TaskContext
from .types import (
    AsyncTaskManagerConfig,
    CompletionCallback,
    ErrorCallback,
    ProgressCallback,
    StartCallback,
    StateChangeCallback,
    TaskDefinition,
    TaskError,
    TaskResult,
    TaskStatus,
)


class AsyncTaskManager(IAsyncTaskManager):
    """异步任务管理器实现"""

    def __init__(
        self,
        config: AsyncTaskManagerConfig | None = None,
        checkpoint_service: ICheckpointService | None = None,
    ):
        """初始化异步任务管理器

        Args:
            config: 配置对象
            checkpoint_service: 检查点服务

        """
        self.config = config or AsyncTaskManagerConfig()

        # 确定检查点存储路径
        storage_path = self.config.checkpoint_storage_path
        if not storage_path:
            # 使用默认全局路径
            from dawei.config import get_dawei_home
            storage_path = str(get_dawei_home()) + "/checkpoints"

        self._checkpoint_service = checkpoint_service or SimpleCheckpointService(
            storage_path,
        )

        # 任务存储
        self._tasks: dict[str, TaskDefinition] = {}
        self._contexts: dict[str, TaskContext] = {}
        self._results: dict[str, TaskResult] = {}
        self._futures: dict[str, asyncio.Future] = {}

        # 执行控制
        self._running_tasks: set[str] = set()
        self._paused_tasks: set[str] = set()
        self._cancelled_tasks: set[str] = set()

        # 线程池执行器
        self._executor = ThreadPoolExecutor(max_workers=self.config.max_concurrent_tasks)

        # 后台任务
        self._scheduler_task: asyncio.Task | None = None
        self._cleanup_task: asyncio.Task | None = None
        self._is_running = False

        # 回调函数
        self._progress_callback: ProgressCallback | None = None
        self._state_change_callback: StateChangeCallback | None = None
        self._error_callback: ErrorCallback | None = None
        self._completion_callback: CompletionCallback | None = None
        self._start_callback: StartCallback | None = None

        # 任务执行器注册表
        self._executors: list[ITaskExecutor] = []

        # 线程安全锁
        self._lock = threading.RLock()

        # 统计信息
        self._stats = {
            "total_tasks": 0,
            "completed_tasks": 0,
            "failed_tasks": 0,
            "cancelled_tasks": 0,
            "running_tasks": 0,
            "paused_tasks": 0,
            "total_execution_time": 0.0,
            "average_execution_time": 0.0,
            "start_time": None,
            "last_cleanup_time": None,
        }

        # 日志记录器
        self._logger = get_logger(__name__)

        self._logger.info("AsyncTaskManager initialized")

    async def submit_task(self, task_def: TaskDefinition) -> str:
        """提交任务

        Args:
            task_def: 任务定义

        Returns:
            任务ID

        """
        with self._lock:
            # 验证任务定义
            if not task_def.task_id:
                raise ValueError("Task ID is required")

            if task_def.task_id in self._tasks:
                raise ValueError(f"Task {task_def.task_id} already exists")

            if not task_def.executor:
                raise ValueError("Task executor is required")

            # Fast Fail: 快速验证任务定义完整性
            if not task_def.name:
                raise ValueError("Task name is required")
            if task_def.timeout is not None and task_def.timeout <= 0:
                raise ValueError("Task timeout must be positive")

            # 存储任务定义
            self._tasks[task_def.task_id] = task_def

            # 创建任务上下文
            context = TaskContext(
                task_id=task_def.task_id,
                checkpoint_service=self._checkpoint_service,
                auto_checkpoint_interval=self.config.checkpoint_interval,
            )

            # 设置上下文回调
            if self._progress_callback:
                context.add_progress_callback(self._progress_callback)
            if self._state_change_callback:
                context.add_state_change_callback(self._state_change_callback)

            self._contexts[task_def.task_id] = context

            # 创建结果Future
            future = asyncio.Future()
            self._futures[task_def.task_id] = future

            # 更新统计
            self._stats["total_tasks"] += 1

            self._logger.info(f"Task submitted: {task_def.task_id} ({task_def.name})")

            # 如果管理器正在运行，立即调度任务
            if self._is_running:
                await self._schedule_task(task_def.task_id)

            return task_def.task_id

    async def cancel_task(self, task_id: str) -> bool:
        """取消任务

        Args:
            task_id: 任务ID

        Returns:
            是否成功取消

        """
        with self._lock:
            if task_id not in self._tasks:
                raise ValueError(f"Task not found: {task_id}")

            if task_id in self._cancelled_tasks:
                return True  # 已取消

            # 标记为取消
            self._cancelled_tasks.add(task_id)

            # 取消上下文
            if task_id in self._contexts:
                self._contexts[task_id].cancel()

            # 取消Future
            if task_id in self._futures:
                self._futures[task_id].cancel()

            # 从运行任务中移除
            self._running_tasks.discard(task_id)

            # 创建取消结果
            result = TaskResult(
                task_id=task_id,
                status=TaskStatus.CANCELLED,
                started_at=self._contexts[task_id].get_data("started_at"),
                completed_at=datetime.now(UTC),
            )
            self._results[task_id] = result

            # 更新统计
            self._stats["cancelled_tasks"] += 1
            self._stats["running_tasks"] = max(0, self._stats["running_tasks"] - 1)

            self._logger.info(f"Task cancelled: {task_id}")

            # 调用完成回调
            if self._completion_callback:
                await self._safe_call_callback(self._completion_callback, result)

            return True

    async def pause_task(self, task_id: str) -> bool:
        """暂停任务

        Args:
            task_id: 任务ID

        Returns:
            是否成功暂停

        """
        with self._lock:
            if task_id not in self._tasks:
                raise ValueError(f"Task not found: {task_id}")

            if task_id in self._paused_tasks:
                return True  # 已暂停

            if task_id not in self._running_tasks:
                self._logger.warning(f"Task is not running: {task_id}")
                return False

            # 标记为暂停
            self._paused_tasks.add(task_id)

            # 暂停上下文
            if task_id in self._contexts:
                self._contexts[task_id].pause()

            # 更新统计
            self._stats["paused_tasks"] += 1
            self._stats["running_tasks"] = max(0, self._stats["running_tasks"] - 1)

            self._logger.info(f"Task paused: {task_id}")

            return True

    async def resume_task(self, task_id: str) -> bool:
        """恢复任务

        Args:
            task_id: 任务ID

        Returns:
            是否成功恢复

        """
        with self._lock:
            if task_id not in self._tasks:
                raise ValueError(f"Task not found: {task_id}")

            if task_id not in self._paused_tasks:
                return True  # 未暂停

            # 移除暂停标记
            self._paused_tasks.discard(task_id)

            # 恢复上下文
            if task_id in self._contexts:
                self._contexts[task_id].resume()

            # 重新调度任务
            await self._schedule_task(task_id)

            # 更新统计
            self._stats["paused_tasks"] = max(0, self._stats["paused_tasks"] - 1)

            self._logger.info(f"Task resumed: {task_id}")

            return True

    async def get_task_status(self, task_id: str) -> TaskStatus | None:
        """获取任务状态

        Args:
            task_id: 任务ID

        Returns:
            任务状态

        """
        with self._lock:
            if task_id not in self._tasks:
                return None

            # 检查结果
            if task_id in self._results:
                return self._results[task_id].status

            # 检查上下文
            if task_id in self._contexts:
                return self._contexts[task_id].get_status()

            return TaskStatus.PENDING

    async def get_task_result(self, task_id: str) -> TaskResult | None:
        """获取任务结果

        Args:
            task_id: 任务ID

        Returns:
            任务结果

        """
        with self._lock:
            return self._results.get(task_id)

    async def list_tasks(self, status_filter: TaskStatus | None = None) -> list[str]:
        """列出任务

        Args:
            status_filter: 状态过滤器

        Returns:
            任务ID列表

        """
        with self._lock:
            if status_filter is None:
                return list(self._tasks.keys())

            task_ids = []
            for task_id in self._tasks:
                task_status = await self.get_task_status(task_id)
                if task_status == status_filter:
                    task_ids.append(task_id)

            return task_ids

    async def wait_for_task(
        self,
        task_id: str,
        timeout: float | None = None,
    ) -> TaskResult | None:
        """等待任务完成

        Args:
            task_id: 任务ID
            timeout: 超时时间

        Returns:
            任务结果

        """
        with self._lock:
            if task_id not in self._futures:
                raise ValueError(f"Task not found: {task_id}")

            future = self._futures[task_id]

        try:
            if timeout:
                await asyncio.wait_for(future, timeout=timeout)
            else:
                await future

            return await self.get_task_result(task_id)
        except TimeoutError:
            self._logger.warning(f"Task wait timeout: {task_id} after {timeout}s")
            # 取消任务
            await self.cancel_task(task_id)
            return None
        except Exception:
            self._logger.exception("Error waiting for task {task_id}: ")
            return None

    def set_progress_callback(self, callback: ProgressCallback) -> None:
        """设置进度回调

        Args:
            callback: 进度回调函数

        """
        self._progress_callback = callback

        # 为现有上下文设置回调
        with self._lock:
            for context in self._contexts.values():
                context.add_progress_callback(callback)

    def set_state_change_callback(self, callback: StateChangeCallback) -> None:
        """设置状态变化回调

        Args:
            callback: 状态变化回调函数

        """
        self._state_change_callback = callback

        # 为现有上下文设置回调
        with self._lock:
            for context in self._contexts.values():
                context.add_state_change_callback(callback)

    def set_error_callback(self, callback: ErrorCallback) -> None:
        """设置错误回调

        Args:
            callback: 错误回调函数

        """
        self._error_callback = callback

    def set_completion_callback(self, callback: CompletionCallback) -> None:
        """设置完成回调

        Args:
            callback: 完成回调函数

        """
        self._completion_callback = callback

    async def set_start_callback(self, callback: StartCallback) -> None:
        """设置开始回调

        Args:
            callback: 开始回调函数

        """
        self._start_callback = callback
        # 为现有上下文设置回调
        with self._lock:
            for context in self._contexts.values():
                context.add_start_callback(callback)

    async def start(self) -> None:
        """启动任务管理器"""
        if self._is_running:
            self._logger.warning("AsyncTaskManager is already running")
            return

        self._is_running = True
        self._stats["start_time"] = datetime.now(UTC).isoformat()

        # 启动调度器任务
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())

        # 启动清理任务
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

        self._logger.info("AsyncTaskManager started")

    async def stop(self) -> None:
        """停止任务管理器"""
        if not self._is_running:
            self._logger.warning("AsyncTaskManager is not running")
            return

        self._is_running = False

        # 取消所有运行中的任务
        with self._lock:
            running_tasks = list(self._running_tasks)
            for task_id in running_tasks:
                await self.cancel_task(task_id)

        # 取消后台任务
        if self._scheduler_task:
            self._scheduler_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._scheduler_task

        if self._cleanup_task:
            self._cleanup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._cleanup_task

        # 关闭线程池
        self._executor.shutdown(wait=True)

        self._logger.info("AsyncTaskManager stopped")

    def get_statistics(self) -> dict[str, Any]:
        """获取统计信息

        Returns:
            统计信息字典

        """
        with self._lock:
            # 计算平均执行时间
            avg_time = 0.0
            if self._stats["completed_tasks"] > 0:
                avg_time = self._stats["total_execution_time"] / self._stats["completed_tasks"]

            # 计算任务状态分布
            status_distribution = {}
            for task_id in self._tasks:
                status = self._contexts.get(task_id)
                if status:
                    status_name = status.get_status().value
                    status_distribution[status_name] = status_distribution.get(status_name, 0) + 1

            return {
                **self._stats,
                "average_execution_time": avg_time,
                "current_tasks": len(self._tasks),
                "running_tasks": len(self._running_tasks),
                "paused_tasks": len(self._paused_tasks),
                "cancelled_tasks": len(self._cancelled_tasks),
                "status_distribution": status_distribution,
                "config": {
                    "max_concurrent_tasks": self.config.max_concurrent_tasks,
                    "default_timeout": self.config.default_timeout,
                    "checkpoint_interval": self.config.checkpoint_interval,
                    "enable_metrics": self.config.enable_metrics,
                    "enable_checkpoints": self.config.enable_checkpoints,
                },
            }

    def register_executor(self, executor: ITaskExecutor) -> None:
        """注册任务执行器

        Args:
            executor: 任务执行器

        """
        self._executors.append(executor)
        self._logger.info(f"Task executor registered: {executor.get_executor_name()}")

    def unregister_executor(self, executor: ITaskExecutor) -> None:
        """注销任务执行器

        Args:
            executor: 任务执行器

        """
        if executor in self._executors:
            self._executors.remove(executor)
            self._logger.info(f"Task executor unregistered: {executor.get_executor_name()}")

    async def _schedule_task(self, task_id: str) -> None:
        """调度任务执行

        Args:
            task_id: 任务ID

        """
        if task_id in self._running_tasks or task_id in self._paused_tasks:
            return

        # 检查并发限制
        if len(self._running_tasks) >= self.config.max_concurrent_tasks:
            self._logger.debug(f"Task {task_id} queued (max concurrent reached)")
            return

        # 标记为运行中
        self._running_tasks.add(task_id)

        # 创建执行任务
        asyncio.create_task(self._execute_task(task_id))

        self._logger.debug(f"Task scheduled: {task_id}")

    async def _execute_task(self, task_id: str) -> None:
        """执行任务

        Args:
            task_id: 任务ID

        """
        task_def = self._tasks.get(task_id)
        context = self._contexts.get(task_id)

        if not task_def or not context:
            self._logger.error(f"Task or context not found: {task_id}")
            return

        start_time = time.time()
        result = None

        try:
            # 设置任务状态为运行中
            context.set_status(TaskStatus.RUNNING)
            context.set_data("started_at", datetime.now(UTC))

            # 更新统计
            self._stats["running_tasks"] += 1

            self._logger.info(f"Task started: {task_id}")

            # 🔧 调用任务开始回调
            if self._start_callback:
                await self._start_callback(task_id, context)

            # 执行任务
            if asyncio.iscoroutinefunction(task_def.executor):
                # 异步函数
                result = await self._execute_with_timeout(
                    task_def.executor,
                    task_def.parameters,
                    context,
                    task_def.timeout,
                )
            else:
                # 同步函数，在线程池中执行
                result = await asyncio.get_event_loop().run_in_executor(
                    self._executor,
                    lambda: self._execute_sync(
                        task_def.executor,
                        task_def.parameters,
                        context,
                        task_def.timeout,
                    ),
                )

            # 任务成功完成
            execution_time = time.time() - start_time
            task_result = TaskResult(
                task_id=task_id,
                status=TaskStatus.COMPLETED,
                result=result,
                execution_time=execution_time,
                started_at=context.get_data("started_at"),
                completed_at=datetime.now(UTC),
            )

            # 更新统计
            self._stats["completed_tasks"] += 1
            self._stats["total_execution_time"] += execution_time
            self._stats["running_tasks"] -= 1

            self._logger.info(f"Task completed: {task_id} (time: {execution_time:.2f}s)")

        except asyncio.CancelledError:
            # 任务被取消
            execution_time = time.time() - start_time
            task_result = TaskResult(
                task_id=task_id,
                status=TaskStatus.CANCELLED,
                execution_time=execution_time,
                started_at=context.get_data("started_at"),
                completed_at=datetime.now(UTC),
            )

            self._stats["cancelled_tasks"] += 1
            self._stats["running_tasks"] -= 1

            self._logger.info(f"Task cancelled: {task_id}")

        except (ValueError, TypeError) as e:
            # Programming errors: invalid input, wrong types - Fast Fail
            execution_time = time.time() - start_time
            self._logger.error(f"Task validation failed: {task_id} - {e!s}", exc_info=True)
            task_result = TaskResult(
                task_id=task_id,
                status=TaskStatus.FAILED,
                error=e,
                execution_time=execution_time,
                started_at=context.get_data("started_at"),
                completed_at=datetime.now(UTC),
            )
            self._stats["failed_tasks"] += 1
            self._stats["running_tasks"] -= 1
            raise  # Fast Fail: these are bugs that should be fixed
        except (OSError, RuntimeError) as e:
            # Recoverable errors: system issues - retry with backoff
            execution_time = time.time() - start_time
            self._logger.warning(
                f"Task execution failed (recoverable): {task_id} - {e!s}",
                exc_info=True,
            )
            task_result = TaskResult(
                task_id=task_id,
                status=TaskStatus.FAILED,
                error=e,
                execution_time=execution_time,
                started_at=context.get_data("started_at"),
                completed_at=datetime.now(UTC),
            )
            self._stats["failed_tasks"] += 1
            self._stats["running_tasks"] -= 1
            # Will trigger retry logic below
        except Exception as e:
            # Unexpected errors - log and fail
            execution_time = time.time() - start_time
            self._logger.error(
                f"Task failed with unexpected error: {task_id} - {e!s}",
                exc_info=True,
            )
            task_result = TaskResult(
                task_id=task_id,
                status=TaskStatus.FAILED,
                error=e,
                execution_time=execution_time,
                started_at=context.get_data("started_at"),
                completed_at=datetime.now(UTC),
            )
            self._stats["failed_tasks"] += 1
            self._stats["running_tasks"] -= 1

            # 创建错误对象
            task_error = TaskError(
                task_id=task_id,
                error_type=type(e).__name__,
                error_message=str(e),
                error_details={"traceback": traceback.format_exc()},
            )

            # 调用错误回调
            if self._error_callback:
                await self._safe_call_callback(self._error_callback, task_error)

            # 尝试重试
            if task_def.retry_policy and task_def.retry_policy.should_retry(
                e,
                task_result.attempts,
            ):
                await self._retry_task(task_id, task_def)
                return

        finally:
            # 清理
            self._running_tasks.discard(task_id)
            self._results[task_id] = task_result

            # 设置Future结果
            if task_id in self._futures and not self._futures[task_id].done():
                self._futures[task_id].set_result(task_result)

            # 调用完成回调
            if self._completion_callback:
                await self._safe_call_callback(self._completion_callback, task_result)

    async def _execute_with_timeout(
        self,
        executor_func: Callable,
        parameters: dict[str, Any],
        context: TaskContext,
        timeout: float | None,
    ) -> Any:
        """带超时的异步执行

        Args:
            executor_func: 执行器函数
            parameters: 参数
            context: 任务上下文
            timeout: 超时时间

        Returns:
            执行结果

        """
        timeout = timeout or self.config.default_timeout

        if timeout:
            try:
                return await asyncio.wait_for(executor_func(parameters, context), timeout=timeout)
            except TimeoutError:
                # 记录超时错误并设置任务状态
                self._logger.warning(f"Task execution timeout after {timeout}s")
                context.set_status(TaskStatus.TIMEOUT)
                raise
        else:
            return await executor_func(parameters, context)

    def _execute_sync(
        self,
        executor_func: Callable,
        parameters: dict[str, Any],
        context: TaskContext,
        timeout: float | None,
    ) -> Any:
        """同步执行（在线程池中）

        Args:
            executor_func: 执行器函数
            parameters: 参数
            context: 任务上下文
            timeout: 超时时间

        Returns:
            执行结果

        """
        import threading

        # Fast Fail: 验证参数
        if not executor_func:
            raise ValueError("Executor function is required")

        if timeout and timeout > 0:
            # 使用线程和信号实现超时机制
            result_container = {}
            exception_container = {}

            def target():
                try:
                    result_container["result"] = executor_func(parameters, context)
                except Exception as e:
                    exception_container["exception"] = e

            thread = threading.Thread(target=target)
            thread.daemon = True
            thread.start()
            thread.join(timeout)

            if thread.is_alive():
                # 线程仍在运行，表示超时
                self._logger.warning(f"Sync task execution timeout after {timeout}s")
                context.set_status(TaskStatus.TIMEOUT)
                raise TimeoutError(f"Task execution timed out after {timeout}s")

            if "exception" in exception_container:
                raise exception_container["exception"]

            return result_container["result"]
        # Fast Fail: 直接执行，捕获异常
        try:
            return executor_func(parameters, context)
        except Exception:
            self._logger.exception("Sync task execution failed: ")
            raise

    async def _retry_task(self, task_id: str, task_def: TaskDefinition) -> None:
        """重试任务

        Args:
            task_id: 任务ID
            task_def: 任务定义

        """
        # Fast Fail: 验证重试策略
        if not task_def.retry_policy:
            self._logger.error(f"Cannot retry task {task_id}: no retry policy defined")
            return

        # Fast Fail: 验证任务结果存在
        if task_id not in self._results:
            self._logger.error(f"Cannot retry task {task_id}: task result not found")
            return

        # 计算重试延迟
        try:
            delay = task_def.retry_policy.calculate_delay(self._results[task_id].attempts)
        except Exception:
            self._logger.exception("Failed to calculate retry delay for task {task_id}: ")
            return

        self._logger.info(
            f"Retrying task {task_id} in {delay:.2f}s (attempt {self._results[task_id].attempts + 1})",
        )

        # 等待延迟
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            self._logger.info(f"Retry cancelled for task {task_id}")
            return

        # Fast Fail: 更新尝试次数
        if task_id in self._results:
            self._results[task_id].attempts += 1

        # 重新调度任务
        try:
            await self._schedule_task(task_id)
        except Exception:
            self._logger.exception("Failed to reschedule task {task_id} for retry: ")
            raise

    async def _scheduler_loop(self) -> None:
        """调度器循环"""
        self._logger.info("Scheduler loop started")

        while self._is_running:
            try:
                await asyncio.sleep(0.1)  # 100ms

                # 调度待执行的任务
                with self._lock:
                    pending_tasks = [task_id for task_id in self._tasks if task_id not in self._running_tasks and task_id not in self._paused_tasks and task_id not in self._cancelled_tasks and task_id not in self._results]

                # Fast Fail: 检查并发限制
                if len(self._running_tasks) >= self.config.max_concurrent_tasks:
                    self._logger.debug("Max concurrent tasks reached, skipping new task scheduling")
                else:
                    # 调度待执行的任务
                    for task_id in pending_tasks:
                        if len(self._running_tasks) >= self.config.max_concurrent_tasks:
                            break
                        try:
                            await self._schedule_task(task_id)
                        except Exception:
                            self._logger.exception("Failed to schedule task {task_id}: ")
                            # 继续调度其他任务，不中断整个循环

            except asyncio.CancelledError:
                # Graceful shutdown on cancellation
                break
            except (TimeoutError, OSError) as e:
                # Network/scheduling errors - log and continue loop
                self._logger.error(f"Transient error in scheduler loop: {e}", exc_info=True)
                await asyncio.sleep(1.0)  # Brief delay before retry
            except Exception as e:
                # Unexpected errors - log with full traceback but continue loop
                self._logger.error(f"Unexpected error in scheduler loop: {e}", exc_info=True)
                await asyncio.sleep(1.0)  # Brief delay before retry

        self._logger.info("Scheduler loop stopped")

    async def _cleanup_loop(self) -> None:
        """清理循环"""
        self._logger.info("Cleanup loop started")

        while self._is_running:
            try:
                await asyncio.sleep(self.config.cleanup_interval)
                await self._cleanup_completed_tasks()
            except asyncio.CancelledError:
                # Graceful shutdown on cancellation
                break
            except (TimeoutError, OSError) as e:
                # Network/scheduling errors - log and continue loop
                self._logger.error(f"Transient error in cleanup loop: {e}", exc_info=True)
                await asyncio.sleep(1.0)  # Brief delay before retry
            except Exception as e:
                # Unexpected errors - log with full traceback but continue loop
                self._logger.error(f"Unexpected error in cleanup loop: {e}", exc_info=True)
                await asyncio.sleep(1.0)  # Brief delay before retry

        self._logger.info("Cleanup loop stopped")

    async def _cleanup_completed_tasks(self) -> None:
        """清理已完成的任务"""
        with self._lock:
            completed_tasks = [
                task_id
                for task_id, result in self._results.items()
                if result.status
                in [
                    TaskStatus.COMPLETED,
                    TaskStatus.FAILED,
                    TaskStatus.CANCELLED,
                    TaskStatus.TIMEOUT,
                ]
            ]

            # 保留最近的任务结果
            if len(completed_tasks) > 100:
                # 按完成时间排序，删除最旧的
                sorted_tasks = sorted(
                    completed_tasks,
                    key=lambda tid: self._results[tid].completed_at or datetime.min,
                )

                tasks_to_remove = sorted_tasks[:-100]  # 保留最新的100个

                # 添加短暂延迟，确保所有回调都完成
                await asyncio.sleep(0.1)

                # 检查任务是否有活跃引用，只清理没有活跃引用的任务结果
                for task_id in tasks_to_remove:
                    # 检查是否有活跃的Future引用
                    if task_id in self._futures and not self._futures[task_id].done():
                        self._logger.debug(
                            f"Skipping cleanup for task with active future: {task_id}",
                        )
                        continue

                    # 检查是否有活跃的上下文引用
                    if task_id in self._contexts and self._contexts[task_id].has_active_callbacks():
                        self._logger.debug(
                            f"Skipping cleanup for task with active callbacks: {task_id}",
                        )
                        continue

                    # Fast Fail: 安全地删除任务相关数据
                    try:
                        if task_id in self._results:
                            del self._results[task_id]
                        if task_id in self._tasks:
                            del self._tasks[task_id]
                        if task_id in self._contexts:
                            del self._contexts[task_id]
                        if task_id in self._futures:
                            del self._futures[task_id]
                    except KeyError as e:
                        # Fast Fail: 如果清理失败，记录错误并抛出异常
                        self._logger.exception("Critical cleanup error for task {task_id}: ")
                        raise RuntimeError(f"Failed to cleanup task {task_id}: {e}")

                self._logger.info(f"Cleaned up {len(tasks_to_remove)} completed tasks")

        self._stats["last_cleanup_time"] = datetime.now(UTC).isoformat()

    async def _safe_call_callback(self, callback: Callable, *args) -> None:
        """安全调用回调函数"""
        try:
            if asyncio.iscoroutinefunction(callback):
                await callback(*args)
            else:
                callback(*args)
        except Exception:
            self._logger.exception("Error in callback: ")

    def __str__(self) -> str:
        """字符串表示"""
        return f"AsyncTaskManager(tasks={len(self._tasks)}, running={len(self._running_tasks)})"

    def __repr__(self) -> str:
        """详细字符串表示"""
        return f"AsyncTaskManager(tasks={len(self._tasks)}, running={len(self._running_tasks)}, config={self.config})"
