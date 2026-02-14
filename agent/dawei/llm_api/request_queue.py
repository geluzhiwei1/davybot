# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""智能请求队列

提供生产级的 LLM API 请求队列功能，支持优先级调度和并发控制。
"""

import asyncio
import contextlib
import heapq
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

from dawei.logg.logging import get_logger

logger = get_logger(__name__)


class RequestPriority(Enum):
    """请求优先级"""

    CRITICAL = auto()  # 关键请求（用户交互）
    HIGH = auto()  # 高优先级（实时任务）
    NORMAL = auto()  # 普通请求（批处理）
    LOW = auto()  # 低优先级（后台任务）


@dataclass(order=True)
class QueuedRequest:
    """队列中的请求"""

    priority: int  # 优先级（数字越小优先级越高）
    submit_time: float = field(compare=False, default_factory=time.time)  # 提交时间
    request_id: str = field(
        compare=False,
        default_factory=lambda: f"req_{int(time.time() * 1000)}_{id(object())}",
    )  # 请求ID
    func: Callable = field(compare=False, default=None)  # 要执行的函数
    args: tuple = field(compare=False, default_factory=tuple)  # 函数参数
    kwargs: dict = field(compare=False, default_factory=dict)  # 关键字参数
    future: asyncio.Future = field(compare=False, default=None)  # 结果Future
    metadata: dict = field(compare=False, default_factory=dict)  # 元数据


class RequestQueue:
    """智能请求队列

    特性：
    - 优先级调度
    - 并发控制
    - 超时处理
    - 请求取消
    - 批量处理优化

    使用示例：
        queue = RequestQueue(max_concurrent=5)
        await queue.start()

        # 提交请求
        result = await queue.submit(
            func=call_llm_api,
            priority=RequestPriority.HIGH,
            messages=messages,
            tools=tools
        )

        await queue.stop()
    """

    def __init__(
        self,
        max_concurrent: int = 5,
        max_queue_size: int = 1000,
        default_timeout: float = 300.0,
    ):
        self.max_concurrent = max_concurrent
        self.max_queue_size = max_queue_size
        self.default_timeout = default_timeout

        # 优先级队列（使用堆）
        self._queue: list[QueuedRequest] = []
        self._queue_lock = asyncio.Lock()

        # 并发控制
        self._semaphore = asyncio.Semaphore(max_concurrent)

        # 任务管理
        self._running_tasks: dict[str, asyncio.Task] = {}
        self._running_tasks_lock = asyncio.Lock()

        # 队列状态
        self._running = False
        self._worker_task: asyncio.Task | None = None

        # 统计信息
        self._stats = {
            "total_submitted": 0,
            "total_completed": 0,
            "total_failed": 0,
            "total_cancelled": 0,
            "total_timeout": 0,
            "current_queue_size": 0,
            "current_running": 0,
        }

        logger.info(
            f"RequestQueue initialized: max_concurrent={max_concurrent}, max_queue_size={max_queue_size}",
        )

    async def start(self):
        """启动队列处理"""
        if self._running:
            logger.warning("RequestQueue already running")
            return

        self._running = True
        self._worker_task = asyncio.create_task(self._worker())
        logger.info("RequestQueue started")

    async def stop(self, wait_for_completion: bool = True, timeout: float = 30.0):
        """停止队列处理"""
        if not self._running:
            return

        self._running = False

        if wait_for_completion:
            # 等待队列中的任务完成
            try:
                await asyncio.wait_for(self._wait_for_completion(), timeout=timeout)
            except TimeoutError:
                logger.warning(f"RequestQueue stop timeout after {timeout}s")

        # 取消worker任务
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker_task

        logger.info("RequestQueue stopped")

    async def submit(
        self,
        func: Callable,
        priority: RequestPriority = RequestPriority.NORMAL,
        timeout: float | None = None,
        metadata: dict | None = None,
        *args,
        **kwargs,
    ) -> Any:
        """提交请求到队列

        Args:
            func: 要执行的异步函数
            priority: 请求优先级
            timeout: 超时时间（秒）
            metadata: 元数据
            *args, **kwargs: 函数参数

        Returns:
            函数执行结果

        Raises:
            asyncio.TimeoutError: 请求超时
            Exception: 函数执行异常

        """
        if not self._running:
            raise RuntimeError("RequestQueue is not running")

        # 检查队列大小
        async with self._queue_lock:
            if len(self._queue) >= self.max_queue_size:
                logger.error(f"Queue full ({self.max_queue_size}), rejecting request")
                raise RuntimeError("Queue is full")

            # 创建请求
            request = QueuedRequest(
                priority=priority.value,
                submit_time=time.time(),
                func=func,
                args=args,
                kwargs=kwargs,
                future=asyncio.Future(),
                metadata=metadata or {},
            )

            # 加入队列
            heapq.heappush(self._queue, request)
            self._stats["total_submitted"] += 1
            self._stats["current_queue_size"] = len(self._queue)

            logger.debug(
                f"Request queued: {request.request_id}, priority={priority.name}, queue_size={len(self._queue)}",
            )

        # 等待结果
        timeout = timeout or self.default_timeout
        try:
            return await asyncio.wait_for(request.future, timeout=timeout)
        except TimeoutError:
            self._stats["total_timeout"] += 1
            logger.warning(f"Request timeout: {request.request_id}")
            await self._cancel_request(request.request_id)
            raise

    async def _worker(self):
        """队列处理worker"""
        logger.info("Queue worker started")

        while self._running:
            try:
                # 从队列中获取请求（带超时，避免阻塞）
                request = await self._get_next_request(timeout=1.0)

                if request is None:
                    continue

                # 处理请求
                task = asyncio.create_task(self._process_request(request))

                # 记录运行中的任务
                async with self._running_tasks_lock:
                    self._running_tasks[request.request_id] = task
                    self._stats["current_running"] = len(self._running_tasks)

            except asyncio.CancelledError:
                logger.info("Queue worker cancelled")
                break
            except Exception as e:
                logger.error(f"Queue worker error: {e}", exc_info=True)

        # 等待所有运行中的任务完成
        await self._wait_for_tasks()
        logger.info("Queue worker stopped")

    async def _get_next_request(self, _timeout: float = 1.0) -> QueuedRequest | None:
        """从队列中获取下一个请求"""
        try:
            async with self._queue_lock:
                if not self._queue:
                    return None

                # 从堆中取出优先级最高的请求
                request = heapq.heappop(self._queue)
                self._stats["current_queue_size"] = len(self._queue)
                return request

        except Exception:
            logger.exception("Error getting next request: ")
            return None

    async def _process_request(self, request: QueuedRequest):
        """处理单个请求"""
        request_id = request.request_id

        logger.debug(f"Processing request: {request_id}")

        # 使用信号量控制并发
        async with self._semaphore:
            try:
                # 执行函数
                result = await request.func(*request.args, **request.kwargs)

                # 设置结果
                if not request.future.done():
                    request.future.set_result(result)
                else:
                    logger.warning(f"Future already done for request {request_id}")

                self._stats["total_completed"] += 1
                logger.debug(f"Request completed: {request_id}")

            except asyncio.CancelledError:
                if not request.future.done():
                    request.future.cancel()
                    self._stats["total_cancelled"] += 1
                else:
                    logger.debug(f"Request already cancelled: {request_id}")

            except Exception as e:
                if not request.future.done():
                    request.future.set_exception(e)
                self._stats["total_failed"] += 1
                logger.exception("Request failed: {request_id}, error=")

                # 重新抛出异常以确保任务正确结束
                raise

            finally:
                # 从运行任务列表中移除
                async with self._running_tasks_lock:
                    self._running_tasks.pop(request_id, None)
                    self._stats["current_running"] = len(self._running_tasks)

    async def _cancel_request(self, request_id: str):
        """取消请求"""
        # 检查运行中的任务
        async with self._running_tasks_lock:
            task = self._running_tasks.get(request_id)
            if task and not task.done():
                task.cancel()
                logger.info(f"Cancelled running request: {request_id}")

    async def _wait_for_tasks(self):
        """等待所有运行中的任务完成"""
        while True:
            async with self._running_tasks_lock:
                if not self._running_tasks:
                    break
                tasks = list(self._running_tasks.values())

            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

    async def _wait_for_completion(self):
        """等待队列清空"""
        while self._running:
            async with self._queue_lock:
                queue_size = len(self._queue)

            async with self._running_tasks_lock:
                running_count = len(self._running_tasks)

            if queue_size == 0 and running_count == 0:
                break

            await asyncio.sleep(0.1)

    def get_stats(self) -> dict:
        """获取统计信息"""
        return self._stats.copy()
