# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""消息处理器基类

定义了所有消息处理器的基础接口和通用功能。
"""

import asyncio
import contextlib
from abc import ABC, abstractmethod
from typing import Any

from dawei.logg.logging import get_logger
from dawei.websocket.manager import WebSocketManager
from dawei.websocket.protocol import (
    BaseWebSocketMessage,
    MessageSerializer,
    WebSocketMessage,
)
from dawei.websocket.router import MessageRouter
from dawei.websocket.session import SessionData, SessionManager

logger = get_logger(__name__)


class BaseWebSocketMessageHandler(ABC):
    """消息处理器基类"""

    def __init__(self):
        self.router: MessageRouter | None = None
        self.websocket_manager: WebSocketManager | None = None
        self.session_manager: SessionManager | None = None
        self._is_initialized = False

    @abstractmethod
    async def handle(
        self,
        session_id: str,
        message: BaseWebSocketMessage,
        message_id: str,
    ) -> BaseWebSocketMessage | None:
        """处理消息

        Args:
            session_id: 会话ID
            message: 接收到的消息
            message_id: 消息ID

        Returns:
            可选的响应消息

        """

    @abstractmethod
    def get_supported_types(self) -> list[str]:
        """获取支持的消息类型列表

        Returns:
            支持的消息类型列表

        """

    def get_name(self) -> str:
        """获取处理器名称"""
        return self.__class__.__name__

    def get_description(self) -> str:
        """获取处理器描述"""
        return f"{self.get_name()} - 处理消息类型: {', '.join(self.get_supported_types())}"

    async def initialize(
        self,
        router: MessageRouter,
        websocket_manager: WebSocketManager,
        session_manager: SessionManager,
    ):
        """初始化处理器

        Args:
            router: 消息路由器
            websocket_manager: WebSocket管理器
            session_manager: 会话管理器

        """
        self.router = router
        self.websocket_manager = websocket_manager
        self.session_manager = session_manager
        self._is_initialized = True

        await self.on_initialize()
        logger.info(f"消息处理器已初始化: {self.get_name()}")

    async def on_initialize(self):
        """初始化时的回调，子类可以重写"""

    async def on_register(self, router):
        """处理器注册时的回调，子类可以重写"""

    async def on_unregister(self, router):
        """处理器注销时的回调，子类可以重写"""

    async def cleanup(self):
        """清理资源，子类可以重写"""

    async def send_message(self, session_id: str, message: WebSocketMessage) -> bool:
        """发送消息到指定会话

        Args:
            session_id: 会话ID
            message: 消息对象

        Returns:
            发送是否成功

        """
        if not self.websocket_manager:
            logger.error(f"处理器 {self.get_name()} 未初始化")
            return False

        return await self.websocket_manager.send_message(session_id, message)

    async def send_error_message(
        self,
        session_id: str,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
        recoverable: bool = True,
    ) -> bool:
        """发送错误消息

        Args:
            session_id: 会话ID
            code: 错误代码
            message: 错误消息
            details: 错误详情
            recoverable: 是否可恢复

        Returns:
            发送是否成功

        """
        error_message = MessageSerializer.create_error_message(
            session_id=session_id,
            code=code,
            message=message,
            details=details,
            recoverable=recoverable,
        )
        return await self.send_message(session_id, error_message)

    async def get_session(self, session_id: str) -> SessionData | None:
        """获取会话数据

        Args:
            session_id: 会话ID

        Returns:
            会话数据，不存在返回None

        """
        if not self.session_manager:
            logger.error(f"处理器 {self.get_name()} 未初始化")
            return None

        return await self.session_manager.get_session(session_id)

    async def update_session_data(
        self,
        session_id: str,
        data: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """更新会话数据

        Args:
            session_id: 会话ID
            data: 要更新的数据
            metadata: 要更新的元数据

        Returns:
            更新是否成功

        """
        if not self.session_manager:
            logger.error(f"处理器 {self.get_name()} 未初始化")
            return False

        return await self.session_manager.update_session(session_id, data=data, metadata=metadata)

    async def get_session_data(self, session_id: str, key: str, default: Any = None) -> Any:
        """获取会话数据中的指定键值

        Args:
            session_id: 会话ID
            key: 数据键
            default: 默认值

        Returns:
            数据值

        """
        if not self.session_manager:
            logger.error(f"处理器 {self.get_name()} 未初始化")
            return default

        return await self.session_manager.get_session_data(session_id, key, default)

    async def set_session_data(self, session_id: str, key: str, value: Any) -> bool:
        """设置会话数据中的指定键值

        Args:
            session_id: 会话ID
            key: 数据键
            value: 数据值

        Returns:
            设置是否成功

        """
        if not self.session_manager:
            logger.error(f"处理器 {self.get_name()} 未初始化")
            return False

        return await self.session_manager.set_session_data(session_id, key, value)

    def is_initialized(self) -> bool:
        """检查是否已初始化"""
        return self._is_initialized

    def _ensure_initialized(self):
        """确保已初始化，否则抛出异常"""
        if not self._is_initialized:
            raise RuntimeError(f"处理器 {self.get_name()} 未初始化")


class AsyncMessageHandler(BaseWebSocketMessageHandler):
    """异步消息处理器基类"""

    def __init__(self, max_concurrent_tasks: int = 10):
        super().__init__()
        self.max_concurrent_tasks = max_concurrent_tasks
        self.active_tasks: dict[str, asyncio.Task] = {}
        self.task_semaphore = asyncio.Semaphore(max_concurrent_tasks)

    async def handle(
        self,
        session_id: str,
        message: BaseWebSocketMessage,
        message_id: str,
    ) -> BaseWebSocketMessage | None:
        """处理消息，支持异步处理

        Args:
            session_id: 会话ID
            message: 接收到的消息
            message_id: 消息ID

        Returns:
            可选的响应消息

        """
        self._ensure_initialized()

        # 检查是否已有该会话的任务在执行
        task_key = f"{session_id}_{message.id}"
        if task_key in self.active_tasks:
            logger.warning(f"会话 {session_id} 的消息 {message.id} 已在处理中")
            return await self.send_error_message(
                session_id,
                "MESSAGE_ALREADY_PROCESSING",
                "消息已在处理中，请稍后再试",
            )

        # 创建异步任务
        async with self.task_semaphore:
            task = asyncio.create_task(self._handle_async(session_id, message, message_id))
            self.active_tasks[task_key] = task

            try:
                return await task
            finally:
                # 清理完成的任务
                if task_key in self.active_tasks:
                    del self.active_tasks[task_key]

    async def _handle_async(
        self,
        session_id: str,
        message: BaseWebSocketMessage,
        message_id: str,
    ) -> BaseWebSocketMessage | None:
        """异步处理消息的具体实现，子类需要重写此方法

        Args:
            session_id: 会话ID
            message: 接收到的消息
            message_id: 消息ID

        Returns:
            可选的响应消息

        """
        return await self.process_message(session_id, message, message_id)

    @abstractmethod
    async def process_message(
        self,
        session_id: str,
        message: BaseWebSocketMessage,
        message_id: str,
    ) -> BaseWebSocketMessage | None:
        """处理消息的具体实现，子类需要重写此方法

        Args:
            session_id: 会话ID
            message: 接收到的消息
            message_id: 消息ID

        Returns:
            可选的响应消息

        """

    async def cleanup(self):
        """清理资源"""
        # 取消所有活跃任务
        for task_key, task in list(self.active_tasks.items()):
            if not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
                logger.info(f"已取消任务: {task_key}")

        self.active_tasks.clear()
        await super().cleanup()

    def get_active_task_count(self) -> int:
        """获取活跃任务数量"""
        return len(self.active_tasks)

    def get_active_tasks(self) -> list[str]:
        """获取活跃任务列表"""
        return list(self.active_tasks.keys())


class StatefulMessageHandler(BaseWebSocketMessageHandler):
    """有状态的消息处理器基类"""

    def __init__(self):
        super().__init__()
        self.handler_state: dict[str, Any] = {}
        self.state_lock = asyncio.Lock()

    async def get_state(self, key: str, default: Any = None) -> Any:
        """获取处理器状态

        Args:
            key: 状态键
            default: 默认值

        Returns:
            状态值

        """
        async with self.state_lock:
            return self.handler_state.get(key, default)

    async def set_state(self, key: str, value: Any):
        """设置处理器状态

        Args:
            key: 状态键
            value: 状态值

        """
        async with self.state_lock:
            self.handler_state[key] = value

    async def update_state(self, updates: dict[str, Any]):
        """更新处理器状态

        Args:
            updates: 要更新的状态字典

        """
        async with self.state_lock:
            self.handler_state.update(updates)

    async def clear_state(self):
        """清空处理器状态"""
        async with self.state_lock:
            self.handler_state.clear()

    async def get_all_state(self) -> dict[str, Any]:
        """获取所有处理器状态"""
        async with self.state_lock:
            return self.handler_state.copy()


class MiddlewareHandler(BaseWebSocketMessageHandler):
    """中间件处理器基类"""

    def __init__(self):
        super().__init__()
        self.next_handler: BaseWebSocketMessageHandler | None = None

    def set_next(self, handler: BaseWebSocketMessageHandler):
        """设置下一个处理器

        Args:
            handler: 下一个处理器

        """
        self.next_handler = handler

    async def handle(
        self,
        session_id: str,
        message: BaseWebSocketMessage,
        message_id: str,
    ) -> BaseWebSocketMessage | None:
        """处理消息，支持中间件链

        Args:
            session_id: 会话ID
            message: 接收到的消息
            message_id: 消息ID

        Returns:
            可选的响应消息

        """
        self._ensure_initialized()

        # 执行当前处理器的逻辑
        result = await self.process(session_id, message, message_id)

        # 如果有下一个处理器，则传递给下一个处理器
        if self.next_handler and result is None:
            result = await self.next_handler.handle(session_id, message, message_id)

        return result

    @abstractmethod
    async def process(
        self,
        session_id: str,
        message: BaseWebSocketMessage,
        message_id: str,
    ) -> BaseWebSocketMessage | None:
        """处理消息的具体实现，子类需要重写此方法

        Args:
            session_id: 会话ID
            message: 接收到的消息
            message_id: 消息ID

        Returns:
            可选的响应消息

        """
