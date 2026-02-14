# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""消息路由器

负责将接收到的消息路由到相应的处理器，并提供插件式的扩展机制。
"""

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Callable

from dawei.logg.logging import get_logger

from .manager import WebSocketManager
from .protocol import BaseWebSocketMessage, MessageSerializer, MessageType

logger = get_logger(__name__)


class MessageHandler(ABC):
    """消息处理器基类"""

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

    async def on_register(self, router: "MessageRouter"):
        """处理器注册时的回调"""

    async def on_unregister(self, router: "MessageRouter"):
        """处理器注销时的回调"""


class MessageRouter:
    """消息路由器"""

    def __init__(self, websocket_manager: WebSocketManager):
        """初始化消息路由器

        Args:
            websocket_manager: WebSocket管理器

        """
        self.websocket_manager = websocket_manager
        self.handlers: dict[str, list[MessageHandler]] = {}
        self.global_handlers: list[MessageHandler] = []
        self.middleware: list[Callable] = []
        self.error_handlers: list[Callable] = []

    async def start(self):
        """启动路由器"""
        # 注册默认处理器
        await self.register_handler(HeartbeatHandler(self.websocket_manager))
        await self.register_handler(ErrorHandler(self))

        logger.info("消息路由器已启动")

    async def stop(self):
        """停止路由器"""
        # 注销所有处理器
        for handlers in list(self.handlers.values()):
            for handler in handlers:
                await self.unregister_handler(handler)

        for handler in self.global_handlers:
            await self.unregister_handler(handler)

        logger.info("消息路由器已停止")

    async def route_message(self, session_id: str, message: BaseWebSocketMessage, message_id: str):
        """路由消息到相应的处理器

        Args:
            session_id: 会话ID
            message: 消息对象
            message_id: 消息ID

        """
        # Update heartbeat on any incoming message
        connection_info = await self.websocket_manager.get_connection_info(session_id)
        if connection_info:
            connection_info.update_heartbeat()

        # 获取消息类型
        message_type = message.type

        # 只对非心跳消息输出详细日志
        is_heartbeat = message_type == "ws_heartbeat"
        if not is_heartbeat:
            logger.info(
                f"🔀 [ROUTER] 开始路由消息: type={message_type}, session_id={session_id}, message_id={message_id}",
            )

        # 执行中间件
        for middleware in self.middleware:
            await middleware(session_id, message)

        # 获取对应的处理器列表
        handlers = self.handlers.get(message_type, [])

        # 添加全局处理器
        handlers.extend(self.global_handlers)

        if not is_heartbeat:
            logger.info(f"🔀 [ROUTER] 找到 {len(handlers)} 个处理器 for type={message_type}")

        if not handlers:
            logger.warning(f"没有找到消息类型 {message_type} 的处理器")
            await self._handle_no_handler(session_id, message)
            return

        # 并行执行所有处理器
        tasks = []
        for handler in handlers:
            task = asyncio.create_task(
                self._execute_handler(session_id, message, message_id, handler),
            )
            tasks.append(task)

        # 等待所有处理器完成
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _execute_handler(
        self,
        session_id: str,
        message: BaseWebSocketMessage,
        message_id: str,
        handler: MessageHandler,
    ):
        """执行单个处理器"""
        handler_name = handler.get_name()
        message_type = message.type

        # 只对非心跳消息输出详细日志
        is_heartbeat = message_type == "ws_heartbeat"
        if not is_heartbeat:
            logger.info(f"⚙️ [ROUTER] 执行处理器: {handler_name} for message type={message_type}")

        # FAST FAIL: Let handler exceptions propagate naturally.
        # The caller (route_message) uses asyncio.gather with return_exceptions=True,
        # which captures exceptions without crashing other handlers.
        response = await handler.handle(session_id, message, message_id)

        if not is_heartbeat:
            logger.info(f"✅ [ROUTER] 处理器 {handler_name} 执行完成")

        # 如果处理器返回响应消息，则发送
        if response:
            if not is_heartbeat:
                print(f"[DEBUG ROUTER] Sending response: {response.type}, session_id: {session_id}")
            result = await self.websocket_manager.send_message(session_id, response)
            if not is_heartbeat:
                if result:
                    print(f"[DEBUG ROUTER] Response sent SUCCESSFULLY: session_id={session_id}")
                else:
                    print(f"[DEBUG ROUTER] Response send FAILED: session_id={session_id}")

    async def register_handler(self, handler: MessageHandler):
        """注册消息处理器

        Args:
            handler: 消息处理器

        """
        supported_types = handler.get_supported_types()

        # 如果处理器支持所有类型，则添加到全局处理器
        if "*" in supported_types:
            self.global_handlers.append(handler)
        else:
            # 否则按类型注册
            for message_type in supported_types:
                if message_type not in self.handlers:
                    self.handlers[message_type] = []
                self.handlers[message_type].append(handler)

        # 调用处理器的注册回调
        await handler.on_register(self)

        logger.info(f"已注册消息处理器: {handler.get_name()} (支持类型: {supported_types})")

    async def unregister_handler(self, handler: MessageHandler):
        """注销消息处理器

        Args:
            handler: 消息处理器

        """
        # 从全局处理器中移除
        if handler in self.global_handlers:
            self.global_handlers.remove(handler)

        # 从类型处理器中移除
        for message_type, handlers in self.handlers.items():
            if handler in handlers:
                handlers.remove(handler)

                # 如果该类型没有处理器了，则删除该类型
                if not handlers:
                    del self.handlers[message_type]

        # 调用处理器的注销回调
        await handler.on_unregister(self)

        logger.info(f"已注销消息处理器: {handler.get_name()}")

    def add_middleware(self, middleware: Callable):
        """添加中间件

        Args:
            middleware: 中间件函数

        """
        self.middleware.append(middleware)
        logger.info(f"已添加中间件: {middleware.__name__}")

    def remove_middleware(self, middleware: Callable):
        """移除中间件

        Args:
            middleware: 中间件函数

        """
        if middleware in self.middleware:
            self.middleware.remove(middleware)
            logger.info(f"已移除中间件: {middleware.__name__}")

    def add_error_handler(self, error_handler: Callable):
        """添加错误处理器

        Args:
            error_handler: 错误处理函数

        """
        self.error_handlers.append(error_handler)
        logger.info(f"已添加错误处理器: {error_handler.__name__}")

    def remove_error_handler(self, error_handler: Callable):
        """移除错误处理器

        Args:
            error_handler: 错误处理函数

        """
        if error_handler in self.error_handlers:
            self.error_handlers.remove(error_handler)
            logger.info(f"已移除错误处理器: {error_handler.__name__}")

    async def _handle_no_handler(self, session_id: str, message: BaseWebSocketMessage):
        """处理没有找到处理器的情况"""
        error_message = MessageSerializer.create_error_message(
            session_id=session_id,
            code="NO_HANDLER",
            message=f"没有找到消息类型 {message.type} 的处理器",
            details={"supported_types": list(self.handlers.keys())},
        )
        await self.websocket_manager.send_message(session_id, error_message)

    async def _handle_routing_error(
        self,
        session_id: str,
        message: BaseWebSocketMessage,
        error: Exception,
    ):
        """处理路由错误"""
        logger.error(f"路由消息时出错: {error}")

        # 调用错误处理器
        for error_handler in self.error_handlers:
            await error_handler(session_id, message, error)

        # 发送错误消息
        error_message = MessageSerializer.create_error_message(
            session_id=session_id,
            code="ROUTING_ERROR",
            message=f"路由消息时出错: {error!s}",
            recoverable=True,
        )
        await self.websocket_manager.send_message(session_id, error_message)

    async def _handle_handler_error(
        self,
        session_id: str,
        message: BaseWebSocketMessage,
        handler: MessageHandler,
        error: Exception,
    ):
        """处理处理器错误"""
        logger.error(f"处理器 {handler.get_name()} 执行失败: {error}")

        # 调用错误处理器
        for error_handler in self.error_handlers:
            await error_handler(session_id, message, error, handler)

    def get_handlers_for_type(self, message_type: str) -> list[MessageHandler]:
        """获取指定消息类型的处理器列表"""
        handlers = self.handlers.get(message_type, []).copy()
        handlers.extend(self.global_handlers)
        return handlers

    def get_all_handlers(self) -> dict[str, list[MessageHandler]]:
        """获取所有处理器"""
        result = {}
        for message_type, handlers in self.handlers.items():
            result[message_type] = handlers.copy()
        result["*"] = self.global_handlers.copy()
        return result


class HeartbeatHandler(MessageHandler):
    """心跳消息处理器"""

    def __init__(self, manager: WebSocketManager):
        self.manager = manager

    async def handle(
        self,
        session_id: str,
        _message: BaseWebSocketMessage,
        _message_id: str,
    ) -> BaseWebSocketMessage | None:
        """处理心跳消息"""
        # Explicitly update heartbeat, though route_message already does this.
        # This makes the handler's purpose clearer.
        connection_info = await self.manager.get_connection_info(session_id)
        if connection_info:
            connection_info.update_heartbeat()

        # 返回pong响应
        return MessageSerializer.create_heartbeat_message(session_id=session_id, message="pong")

    def get_supported_types(self) -> list[str]:
        return [MessageType.HEARTBEAT]


class ErrorHandler(MessageHandler):
    """错误消息处理器"""

    def __init__(self, router: MessageRouter):
        self.router = router

    async def handle(
        self,
        session_id: str,
        message: BaseWebSocketMessage,
        _message_id: str,
    ) -> BaseWebSocketMessage | None:
        """处理错误消息"""
        # 记录错误日志
        logger.error(f"收到客户端错误消息 ({session_id}): {message}")

        # 这里可以添加更多的错误处理逻辑
        # 例如：错误统计、错误上报等

        return None

    def get_supported_types(self) -> list[str]:
        return [MessageType.ERROR, MessageType.WARNING]

    async def on_register(self, router: MessageRouter):
        """注册时的回调"""
        # 添加错误处理器
        router.add_error_handler(self._handle_error)

    async def on_unregister(self, router: MessageRouter):
        """注销时的回调"""
        # 移除错误处理器
        router.remove_error_handler(self._handle_error)

    async def _handle_error(
        self,
        session_id: str,
        message: BaseWebSocketMessage,
        error: Exception,
        handler: MessageHandler | None = None,
    ):
        """处理错误"""
        # 这里可以添加自定义的错误处理逻辑
        # 例如：错误统计、错误上报等
