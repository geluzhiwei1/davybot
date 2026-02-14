# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""WebSocket连接管理器

负责管理WebSocket连接的生命周期，包括连接建立、维护和断开。
"""

import asyncio
import contextlib
from collections.abc import Callable
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

from fastapi import WebSocket
from starlette.websockets import WebSocketState

from dawei.async_task.types import ConnectionState, WebSocketManagerConfig
from dawei.async_task.websocket_state_manager import WebSocketStateManager
from dawei.core.error_handler import handle_errors
from dawei.core.errors import ValidationError
from dawei.core.metrics import increment_counter, set_gauge
from dawei.logg.logging import get_logger, log_performance

from .protocol import (
    BaseWebSocketMessage,
    ConnectMessage,
    DisconnectMessage,
    MessageSerializer,
    MessageType,
    WebSocketMessage,
)

logger = get_logger(__name__)


class ConnectionInfo:
    """连接信息"""

    def __init__(self, websocket: WebSocket, session_id: str):
        # 验证输入
        if not session_id or not session_id.strip():
            raise ValidationError("session_id", session_id, "must be non-empty string")

        self.websocket = websocket
        self.session_id = session_id
        self.connected_at = datetime.now(UTC)
        self.last_heartbeat = datetime.now(UTC)
        self.message_count = 0
        self.is_alive = True
        self.error_count = 0  # 错误计数
        self.last_error: str | None = None  # 最后一次错误信息

    def update_heartbeat(self):
        """更新心跳时间"""
        self.last_heartbeat = datetime.now(UTC)

    def increment_message_count(self, is_heartbeat: bool = False):
        """增加消息计数"""
        if not is_heartbeat:
            self.message_count += 1

    def increment_error_count(self, error: str):
        """增加错误计数"""
        self.error_count += 1
        self.last_error = error

    def is_timeout(self, timeout_seconds: int = 60) -> bool:
        """检查连接是否超时"""
        return (datetime.now(UTC) - self.last_heartbeat).seconds > timeout_seconds

    def get_uptime(self) -> timedelta:
        """获取连接运行时间"""
        return datetime.now(UTC) - self.connected_at

    def get_status(self) -> dict[str, Any]:
        """获取连接状态信息"""
        return {
            "session_id": self.session_id,
            "connected_at": self.connected_at.isoformat(),
            "uptime_seconds": self.get_uptime().total_seconds(),
            "message_count": self.message_count,
            "error_count": self.error_count,
            "last_heartbeat": self.last_heartbeat.isoformat(),
            "is_alive": self.is_alive,
            "last_error": self.last_error,
        }


class WebSocketManager:
    """WebSocket连接管理器"""

    def __init__(self, heartbeat_interval: int = 30, connection_timeout: int = 60):
        """初始化WebSocket管理器

        Args:
            heartbeat_interval: 心跳检查间隔（秒）
            connection_timeout: 连接超时时间（秒）

        """
        # 验证输入
        if heartbeat_interval <= 0:
            raise ValidationError("heartbeat_interval", heartbeat_interval, "must be positive")
        if connection_timeout <= 0:
            raise ValidationError("connection_timeout", connection_timeout, "must be positive")

        self.active_connections: dict[str, ConnectionInfo] = {}
        self.heartbeat_interval = heartbeat_interval
        self.connection_timeout = connection_timeout
        self.message_handlers: dict[str, Callable] = {}
        self.connection_listeners: list[Callable] = []
        self.error_handlers: list[Callable] = []  # 错误处理器列表
        self._heartbeat_task: asyncio.Task | None = None
        self._is_running = False
        self._error_stats: dict[str, Any] = {
            "total_errors": 0,
            "connection_errors": 0,
            "message_errors": 0,
            "handler_errors": 0,
            "error_types": {},
        }
        self._lock = asyncio.Lock()
        self.logger = get_logger(__name__)

        # 任务取消配置
        self._task_cancel_delay = 3  # 断开连接后3秒取消任务
        self._pending_cancel_tasks: dict[str, asyncio.Task] = {}  # session_id -> cancel_task

        # 初始化WebSocket状态管理器
        self._state_manager = WebSocketStateManager(
            WebSocketManagerConfig(
                heartbeat_interval=heartbeat_interval,
                connection_timeout=connection_timeout,
                enable_auto_reconnect=True,
            ),
        )

        # 设置状态管理器回调
        self._state_manager.set_state_change_callback(self._on_connection_state_change)
        self._state_manager.set_heartbeat_callback(self._on_connection_heartbeat)

    @handle_errors(component="websocket_manager", operation="start")
    async def start(self):
        """启动管理器"""
        if self._is_running:
            return

        self._is_running = True

        # 启动状态管理器
        await self._state_manager.start()

        # 启动心跳任务
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        self.logger.info("WebSocket manager started", context={"component": "websocket_manager"})
        increment_counter("websocket_manager.start", tags={"status": "success"})

    @handle_errors(component="websocket_manager", operation="stop")
    @log_performance("websocket_manager.stop")
    async def stop(self):
        """停止管理器"""
        if not self._is_running:
            return

        self._is_running = False

        # 停止状态管理器
        await self._state_manager.stop()

        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._heartbeat_task

        # 断开所有连接
        for session_id in list(self.active_connections.keys()):
            await self.disconnect(session_id, "服务器关闭")

        self.logger.info("WebSocket manager stopped", context={"component": "websocket_manager"})
        increment_counter("websocket_manager.stop", tags={"status": "success"})

    @handle_errors(component="websocket_manager", operation="connect")
    @log_performance("websocket_manager.connect")
    async def connect(self, websocket: WebSocket, session_id: str) -> bool:
        """建立WebSocket连接

        Args:
            websocket: WebSocket连接对象
            session_id: 会话ID

        Returns:
            连接是否成功建立

        """
        # 在状态管理器中注册连接
        await self._state_manager.register_connection(session_id)
        await self._state_manager.set_connection_state(session_id, ConnectionState.CONNECTING)

        # 检查是否已存在连接
        if session_id in self.active_connections:
            self.logger.warning(
                "Session already exists, disconnecting old connection",
                context={"session_id": session_id, "component": "websocket_manager"},
            )
            await self.disconnect(session_id, "重复连接")

        # 创建连接信息
        connection_info = ConnectionInfo(websocket, session_id)
        self.active_connections[session_id] = connection_info

        # 更新状态管理器中的连接状态
        await self._state_manager.set_connection_state(session_id, ConnectionState.CONNECTED)

        # 立即初始化心跳，确保连接被认为是健康的
        await self._state_manager.update_heartbeat(session_id)

        # 发送连接确认消息
        connect_message = ConnectMessage(session_id=session_id, message="连接已建立")
        await self.send_message(session_id, connect_message)

        # 通知连接监听器
        await self._notify_connection_listeners("connect", session_id, connection_info)

        self.logger.info(
            "WebSocket connection established",
            context={"session_id": session_id, "component": "websocket_manager"},
        )
        increment_counter("websocket_manager.connections", tags={"status": "success"})
        set_gauge("websocket_manager.active_connections", len(self.active_connections))

        return True

    @handle_errors(component="websocket_manager", operation="disconnect")
    @log_performance("websocket_manager.disconnect")
    async def disconnect(self, session_id: str, reason: str | None = None):
        """断开WebSocket连接

        Args:
            session_id: 会话ID
            reason: 断开原因

        """
        # First, get the connection info without removing it
        async with self._lock:
            if session_id not in self.active_connections:
                return
            connection_info = self.active_connections.get(session_id)

        if not connection_info:
            return

        # 检查连接是否已经断开
        if not connection_info.is_alive:
            self.logger.debug(
                "Connection already marked as not alive",
                context={"session_id": session_id, "component": "websocket_manager"},
            )
            return

        # 更新状态管理器中的连接状态
        await self._state_manager.set_connection_state(session_id, ConnectionState.DISCONNECTED)

        # Attempt to send a disconnect message gracefully
        disconnect_message = DisconnectMessage(
            session_id=session_id,
            reason=reason,
        )

        # 检查WebSocket状态，避免重复关闭
        try:
            if connection_info.websocket.client_state == WebSocketState.CONNECTED:
                # 直接发送消息，避免通过send_message造成递归调用
                serialized_message = MessageSerializer.serialize(disconnect_message)
                await connection_info.websocket.send_text(serialized_message)

            # Close the WebSocket connection
            if connection_info.websocket.client_state == WebSocketState.CONNECTED:
                await connection_info.websocket.close()
        except Exception as e:
            # 捕获重复关闭的错误，避免抛出异常
            if "Cannot call 'send' once a close message has been sent" in str(
                e,
            ) or "Cannot call 'close' once a close message has been sent" in str(e):
                self.logger.debug(
                    "Connection already closed, ignoring duplicate close",
                    context={
                        "session_id": session_id,
                        "error": str(e),
                        "component": "websocket_manager",
                    },
                )
            else:
                # 其他错误仍然需要记录
                self.logger.warning(
                    "Error during disconnect",
                    context={
                        "session_id": session_id,
                        "error": str(e),
                        "component": "websocket_manager",
                    },
                )

        # Now, safely remove the connection from the active list
        async with self._lock:
            self.active_connections.pop(session_id, None)

        connection_info.is_alive = False

        # 从状态管理器中注销连接
        await self._state_manager.unregister_connection(session_id)

        # Notify connection listeners
        await self._notify_connection_listeners("disconnect", session_id, connection_info)

        # 安排延迟取消任务（3秒后）
        await self._schedule_task_cancellation(session_id, reason)

        self.logger.info(
            "WebSocket connection disconnected",
            context={
                "session_id": session_id,
                "reason": reason or "正常断开",
                "component": "websocket_manager",
            },
        )
        increment_counter("websocket_manager.disconnections", tags={"status": "success"})
        set_gauge("websocket_manager.active_connections", len(self.active_connections))

    @handle_errors(component="websocket_manager", operation="send_message")
    @log_performance("websocket_manager.send_message")
    async def send_message(
        self,
        session_id: str,
        message: WebSocketMessage,
        _skip_lock: bool = False,
    ) -> bool:
        """发送消息到指定连接

        Args:
            session_id: 会话ID
            message: 消息对象
            skip_lock: 是否跳过锁（内部调用时使用）

        Returns:
            发送是否成功

        """
        # 使用锁来避免竞态条件
        async with self._lock:
            # 检查连接是否存在
            if session_id not in self.active_connections:
                return False

            connection_info = self.active_connections.get(session_id)
            if not connection_info:
                return False

            # 检查连接是否还活着
            if not connection_info.is_alive:
                return False

            # 检查WebSocket连接状态
            if connection_info.websocket.client_state != WebSocketState.CONNECTED:
                # 标记连接为不活跃并异步断开
                connection_info.is_alive = False
                asyncio.create_task(self.disconnect(session_id, "连接已关闭"))
                return False

        # 在锁外进行状态管理器检查和实际发送，避免长时间持锁
        try:
            # 使用状态管理器检查连接健康状态
            connection_state = await self._state_manager.get_connection_state(session_id)
            if not connection_state:
                self.logger.warning(
                    "Connection state not found for session",
                    context={
                        "session_id": session_id,
                        "component": "websocket_manager",
                    },
                )
                return False

            if not connection_state.is_healthy:
                self.logger.warning(
                    "Attempt to send message to unhealthy connection",
                    context={
                        "session_id": session_id,
                        "is_connected": connection_state.is_connected,
                        "last_heartbeat": (connection_state.last_heartbeat.isoformat() if connection_state.last_heartbeat else None),
                        "message_type": getattr(message, "type", "unknown"),
                        "component": "websocket_manager",
                    },
                )
                # 异步地调用disconnect，避免阻塞当前任务
                asyncio.create_task(self.disconnect(session_id, "连接不健康"))
                return False

            # 序列化消息
            serialized_message = MessageSerializer.serialize(message)

            # 再次获取连接信息（可能在锁释放后发生变化）
            async with self._lock:
                connection_info = self.active_connections.get(session_id)
                if not connection_info or not connection_info.is_alive:
                    self.logger.warning(
                        "Connection became unavailable during send",
                        context={
                            "session_id": session_id,
                            "component": "websocket_manager",
                        },
                    )
                    return False

                # 发送消息
                await connection_info.websocket.send_text(serialized_message)

                # 检查是否为心跳消息
                is_heartbeat = getattr(message, "type", None) == MessageType.HEARTBEAT
                connection_info.increment_message_count(is_heartbeat)

            # 更新状态管理器中的消息计数
            await self._state_manager.increment_message_count(session_id)

            # 如果是心跳消息，更新心跳时间
            if is_heartbeat:
                await self._state_manager.update_heartbeat(session_id)

            # 心跳消息不计入消息发送统计
            if not is_heartbeat:
                increment_counter(
                    "websocket_manager.messages_sent",
                    tags={
                        "session_id": session_id,
                        "message_type": getattr(message, "type", "unknown"),
                    },
                )

            return True

        except Exception as e:
            self.logger.exception(
                "Error sending message",
                context={
                    "session_id": session_id,
                    "error": str(e),
                    "message_type": getattr(message, "type", "unknown"),
                    "component": "websocket_manager",
                },
            )
            # 发送失败时标记连接为不活跃并异步断开
            async with self._lock:
                connection_info = self.active_connections.get(session_id)
                if connection_info:
                    connection_info.is_alive = False

            asyncio.create_task(self.disconnect(session_id, f"发送消息失败: {e!s}"))
            return False

    @handle_errors(component="websocket_manager", operation="broadcast")
    @log_performance("websocket_manager.broadcast")
    async def broadcast(
        self,
        message: BaseWebSocketMessage,
        exclude_sessions: set[str] | None = None,
    ):
        """广播消息到所有连接

        Args:
            message: 消息对象
            exclude_sessions: 排除的会话ID集合

        """
        exclude_sessions = exclude_sessions or set()
        failed_sessions = []

        for session_id in list(self.active_connections.keys()):
            if session_id in exclude_sessions:
                continue

            success = await self.send_message(session_id, message)
            if not success:
                failed_sessions.append(session_id)

        if failed_sessions:
            self.logger.warning(
                "Broadcast message failed for some sessions",
                context={
                    "failed_sessions": failed_sessions,
                    "message_type": getattr(message, "type", "unknown"),
                    "component": "websocket_manager",
                },
            )
            increment_counter(
                "websocket_manager.broadcast_failures",
                tags={"message_type": getattr(message, "type", "unknown")},
            )

        self.logger.info(
            "Message broadcast completed",
            context={
                "total_sessions": len(self.active_connections),
                "successful_sessions": len(self.active_connections) - len(failed_sessions),
                "failed_sessions": len(failed_sessions),
                "message_type": getattr(message, "type", "unknown"),
                "component": "websocket_manager",
            },
        )
        increment_counter(
            "websocket_manager.broadcasts",
            tags={"message_type": getattr(message, "type", "unknown")},
        )

    @handle_errors(component="websocket_manager", operation="send_error_message")
    async def send_error_message(
        self,
        session_id: str,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
        recoverable: bool = True,
    ):
        """发送错误消息"""
        error_message = MessageSerializer.create_error_message(
            session_id=session_id,
            code=code,
            message=message,
            details=details,
            recoverable=recoverable,
        )
        await self.send_message(session_id, error_message)

        self.logger.info(
            "Error message sent",
            context={
                "session_id": session_id,
                "error_code": code,
                "recoverable": recoverable,
                "component": "websocket_manager",
            },
        )
        increment_counter(
            "websocket_manager.error_messages_sent",
            tags={"error_code": code, "recoverable": str(recoverable)},
        )

    def register_handler(self, message_type: str, handler: Callable):
        """注册消息处理器

        Args:
            message_type: 消息类型
            handler: 处理器函数

        """
        self.message_handlers[message_type] = handler
        logger.info(f"已注册消息处理器: {message_type}")

    def unregister_handler(self, message_type: str):
        """注销消息处理器

        Args:
            message_type: 消息类型

        """
        if message_type in self.message_handlers:
            del self.message_handlers[message_type]
            logger.info(f"已注销消息处理器: {message_type}")

    def add_connection_listener(self, listener: Callable):
        """添加连接事件监听器

        Args:
            listener: 监听器函数

        """
        self.connection_listeners.append(listener)

    def remove_connection_listener(self, listener: Callable):
        """移除连接事件监听器

        Args:
            listener: 监听器函数

        """
        if listener in self.connection_listeners:
            self.connection_listeners.remove(listener)

    def add_error_handler(self, handler: Callable):
        """添加错误处理器

        Args:
            handler: 错误处理器函数

        """
        self.error_handlers.append(handler)
        logger.info(f"已添加错误处理器: {handler.__name__}")

    def remove_error_handler(self, handler: Callable):
        """移除错误处理器

        Args:
            handler: 错误处理器函数

        """
        if handler in self.error_handlers:
            self.error_handlers.remove(handler)
            logger.info(f"已移除错误处理器: {handler.__name__}")

    @handle_errors(component="websocket_manager", operation="notify_connection_listeners")
    async def _notify_connection_listeners(
        self,
        event: str,
        session_id: str,
        connection_info: ConnectionInfo,
    ):
        """通知连接监听器"""
        for listener in self.connection_listeners:
            try:
                if asyncio.iscoroutinefunction(listener):
                    await listener(event, session_id, connection_info)
                else:
                    listener(event, session_id, connection_info)
            except Exception as e:
                self.logger.exception(
                    "Connection listener execution failed",
                    context={
                        "event": event,
                        "session_id": session_id,
                        "error": str(e),
                        "component": "websocket_manager",
                    },
                )
                increment_counter(
                    "websocket_manager.listener_errors",
                    tags={"event": event, "error_type": type(e).__name__},
                )

    @handle_errors(component="websocket_manager", operation="handle_error")
    async def _handle_error(self, error_type: str, error_data: dict[str, Any]):
        """处理错误"""
        # 通知所有错误处理器
        for handler in self.error_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(error_type, error_data)
                else:
                    handler(error_type, error_data)
            except Exception as e:
                self.logger.exception(
                    "Error handler execution failed",
                    context={
                        "error_type": error_type,
                        "handler_error": str(e),
                        "component": "websocket_manager",
                    },
                )
                increment_counter(
                    "websocket_manager.handler_errors",
                    tags={
                        "error_type": error_type,
                        "handler_error_type": type(e).__name__,
                    },
                )

    @handle_errors(component="websocket_manager", operation="heartbeat_loop")
    async def _heartbeat_loop(self):
        """心跳检查循环"""
        while self._is_running:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                await self._check_connections()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.exception(
                    "Heartbeat check error",
                    context={"error": str(e), "component": "websocket_manager"},
                )
                increment_counter(
                    "websocket_manager.heartbeat_errors",
                    tags={"error_type": type(e).__name__},
                )

    @handle_errors(component="websocket_manager", operation="check_connections")
    async def _check_connections(self):
        """检查连接状态"""
        timeout_sessions = []

        for session_id, connection_info in self.active_connections.items():
            if connection_info.is_timeout(self.connection_timeout):
                timeout_sessions.append(session_id)

        # 断开超时连接
        for session_id in timeout_sessions:
            await self.disconnect(session_id, "连接超时")

        if timeout_sessions:
            self.logger.info(
                "Disconnected timeout sessions",
                context={
                    "timeout_sessions": timeout_sessions,
                    "component": "websocket_manager",
                },
            )
            increment_counter("websocket_manager.timeouts", tags={"count": len(timeout_sessions)})

    async def get_connection_info(self, session_id: str) -> ConnectionInfo | None:
        """获取连接信息"""
        # 首先从状态管理器获取连接状态
        connection_state = await self._state_manager.get_connection_state(session_id)
        if not connection_state:
            return None

        # 然后从本地连接信息中获取详细信息
        return self.active_connections.get(session_id)

    def get_all_connections(self) -> dict[str, ConnectionInfo]:
        """获取所有连接信息"""
        return self.active_connections.copy()

    def get_connection_count(self) -> int:
        """获取活跃连接数"""
        return len(self.active_connections)

    async def is_connected(self, session_id: str) -> bool:
        """检查会话是否连接"""
        # 使用状态管理器检查连接状态
        connection_state = await self._state_manager.get_connection_state(session_id)
        return connection_state is not None and connection_state.is_connected

    def get_error_statistics(self) -> dict[str, Any]:
        """获取错误统计信息"""
        return {
            **self._error_stats,
            "active_connections": len(self.active_connections),
            "total_connections": sum(1 for conn in self.active_connections.values() if conn.error_count > 0),
            "average_errors_per_connection": (sum(conn.error_count for conn in self.active_connections.values()) / len(self.active_connections) if self.active_connections else 0),
        }

    @handle_errors(component="websocket_manager", operation="reset_error_statistics")
    def reset_error_statistics(self):
        """重置错误统计"""
        self._error_stats = {
            "total_errors": 0,
            "connection_errors": 0,
            "message_errors": 0,
            "handler_errors": 0,
            "error_types": {},
        }

        self.logger.info("Error statistics reset", context={"component": "websocket_manager"})
        increment_counter("websocket_manager.stats_reset", tags={"status": "success"})

    async def _on_connection_state_change(
        self,
        session_id: str,
        old_state: ConnectionState,
        new_state: ConnectionState,
    ):
        """连接状态变化回调"""
        try:
            self.logger.info(
                f"Connection state changed: {session_id} {old_state.value} -> {new_state.value}",
                context={"session_id": session_id, "component": "websocket_manager"},
            )

            # 如果连接变为错误状态，增加错误计数
            if new_state == ConnectionState.ERROR:
                await self._state_manager.increment_error_count(session_id, "连接状态错误")

        except Exception as e:
            self.logger.exception(
                f"Error in connection state change callback: {e}",
                context={"session_id": session_id, "component": "websocket_manager"},
            )

    async def _on_connection_heartbeat(self, session_id: str):
        """连接心跳回调"""
        try:
            # 更新本地连接信息的心跳时间
            connection_info = self.active_connections.get(session_id)
            if connection_info:
                connection_info.update_heartbeat()

        except Exception as e:
            self.logger.exception(
                f"Error in connection heartbeat callback: {e}",
                context={"session_id": session_id, "component": "websocket_manager"},
            )

    async def get_connection_statistics(self) -> dict[str, Any]:
        """获取连接统计信息"""
        try:
            # 获取状态管理器的统计信息
            state_stats = self._state_manager.get_statistics()

            # 合并本地统计信息
            local_stats = self.get_error_statistics()

            return {
                **state_stats,
                "local_errors": local_stats,
                "active_connections": len(self.active_connections),
            }
        except Exception as e:
            self.logger.exception(
                f"Error getting connection statistics: {e}",
                context={"component": "websocket_manager"},
            )

    async def _schedule_task_cancellation(self, session_id: str, reason: str | None = None):
        """安排延迟取消任务

        当用户WebSocket断开后，等待3秒后取消该session对应的所有任务。
        如果3秒内重新连接，则取消任务取消计划。

        Args:
            session_id: 会话ID
            reason: 断开原因

        """
        # 如果已有待取消任务，先取消
        if session_id in self._pending_cancel_tasks:
            self._pending_cancel_tasks[session_id].cancel()
            self.logger.info(
                f"Cancelled previous task cancellation for session {session_id}",
                context={"session_id": session_id, "component": "websocket_manager"},
            )

        # 创建新的延迟取消任务
        async def cancel_tasks_after_delay():
            try:
                await asyncio.sleep(self._task_cancel_delay)

                # 检查连接是否已恢复
                if session_id in self.active_connections:
                    self.logger.info(
                        f"Session {session_id} reconnected, cancelling task cancellation",
                        context={
                            "session_id": session_id,
                            "component": "websocket_manager",
                        },
                    )
                    return

                # 取消该session的所有任务
                await self._cancel_session_tasks(session_id, reason)

            except asyncio.CancelledError:
                self.logger.debug(
                    f"Task cancellation cancelled for session {session_id}",
                    context={
                        "session_id": session_id,
                        "component": "websocket_manager",
                    },
                )
            except Exception as e:
                self.logger.exception(
                    f"Error in task cancellation for session {session_id}: {e}",
                    context={
                        "session_id": session_id,
                        "component": "websocket_manager",
                    },
                )
            finally:
                # 清理待取消任务记录
                self._pending_cancel_tasks.pop(session_id, None)

        # 创建并存储取消任务
        cancel_task = asyncio.create_task(cancel_tasks_after_delay())
        self._pending_cancel_tasks[session_id] = cancel_task

        self.logger.info(
            f"Scheduled task cancellation for session {session_id} in {self._task_cancel_delay}s",
            context={
                "session_id": session_id,
                "delay": self._task_cancel_delay,
                "reason": reason,
                "component": "websocket_manager",
            },
        )

    async def _cancel_session_tasks(self, session_id: str, reason: str | None = None):
        """取消指定session的所有任务

        Args:
            session_id: 会话ID
            reason: 取消原因

        """
        try:
            # 从ChatHandler获取task_to_session映射
            # 需要找到所有属于该session的任务
            from dawei.websocket.handlers.chat import chat_handler_instance

            if not chat_handler_instance:
                self.logger.warning(
                    "ChatHandler instance not available",
                    context={
                        "session_id": session_id,
                        "component": "websocket_manager",
                    },
                )
                return

            # 获取task_to_session映射
            task_to_session_map = chat_handler_instance._task_to_session_map

            # 找到所有属于该session的任务
            tasks_to_cancel = [task_id for task_id, sid in task_to_session_map.items() if sid == session_id]

            if not tasks_to_cancel:
                self.logger.info(
                    f"No tasks found for session {session_id}",
                    context={
                        "session_id": session_id,
                        "component": "websocket_manager",
                    },
                )
                return

            self.logger.info(
                f"Cancelling {len(tasks_to_cancel)} tasks for session {session_id}",
                context={
                    "session_id": session_id,
                    "task_count": len(tasks_to_cancel),
                    "task_ids": tasks_to_cancel[:5],  # 只记录前5个
                    "component": "websocket_manager",
                },
            )

            # 取消每个任务
            cancelled_count = 0
            for task_id in tasks_to_cancel:
                try:
                    success = await chat_handler_instance._task_manager.cancel_task(task_id)
                    if success:
                        cancelled_count += 1
                        # 从映射中移除
                        task_to_session_map.pop(task_id, None)
                    else:
                        self.logger.warning(
                            f"Failed to cancel task {task_id}",
                            context={
                                "session_id": session_id,
                                "task_id": task_id,
                                "component": "websocket_manager",
                            },
                        )
                except Exception as e:
                    self.logger.exception(
                        f"Error cancelling task {task_id}: {e}",
                        context={
                            "session_id": session_id,
                            "task_id": task_id,
                            "component": "websocket_manager",
                        },
                    )

            self.logger.info(
                f"Cancelled {cancelled_count}/{len(tasks_to_cancel)} tasks for session {session_id}",
                context={
                    "session_id": session_id,
                    "cancelled": cancelled_count,
                    "total": len(tasks_to_cancel),
                    "reason": reason,
                    "component": "websocket_manager",
                },
            )

        except Exception as e:
            self.logger.exception(
                f"Error cancelling session tasks for {session_id}: {e}",
                context={"session_id": session_id, "component": "websocket_manager"},
            )

    async def cancel_pending_task_cancellation(self, session_id: str):
        """取消待处理的任务取消（用于重连时）

        Args:
            session_id: 会话ID

        """
        if session_id in self._pending_cancel_tasks:
            self._pending_cancel_tasks[session_id].cancel()
            self._pending_cancel_tasks.pop(session_id, None)
            self.logger.info(
                f"Cancelled pending task cancellation for session {session_id}",
                context={"session_id": session_id, "component": "websocket_manager"},
            )
