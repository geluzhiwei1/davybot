# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""WebSocket连接状态管理器实现

提供WebSocket连接的状态跟踪、心跳检测和断线处理功能。
"""

import asyncio
import contextlib
import threading
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any

from dawei.logg.logging import get_logger

from .interfaces import IWebSocketStateManager
from .types import ConnectionState, WebSocketManagerConfig, WebSocketState


class WebSocketStateManager(IWebSocketStateManager):
    """WebSocket状态管理器实现"""

    def __init__(self, config: WebSocketManagerConfig | None = None):
        """初始化WebSocket状态管理器

        Args:
            config: 配置对象

        """
        self.config = config or WebSocketManagerConfig()

        # 连接状态存储
        self._connections: dict[str, WebSocketState] = {}

        # 回调函数
        self._state_change_callbacks: list[Callable[[str, ConnectionState, ConnectionState], None]] = []
        self._heartbeat_callbacks: list[Callable[[str], None]] = []

        # 后台任务
        self._heartbeat_task: asyncio.Task | None = None
        self._cleanup_task: asyncio.Task | None = None
        self._is_running = False

        # 线程安全锁
        self._lock = threading.RLock()

        # 统计信息
        self._stats = {
            "total_connections": 0,
            "active_connections": 0,
            "failed_connections": 0,
            "total_messages": 0,
            "total_errors": 0,
            "last_cleanup_time": None,
            "start_time": None,
        }

        # 日志记录器
        self._logger = get_logger(__name__)

        self._logger.info("WebSocketStateManager initialized")

    async def register_connection(self, session_id: str) -> bool:
        """注册连接

        Args:
            session_id: 会话ID

        Returns:
            是否成功注册

        """
        with self._lock:
            if session_id in self._connections:
                self._logger.warning(f"Connection already exists: {session_id}")
                return False

            # 创建连接状态
            connection_state = WebSocketState(
                session_id=session_id,
                state=ConnectionState.CONNECTING,
                connected_at=datetime.now(timezone.utc),
            )

            self._connections[session_id] = connection_state
            self._stats["total_connections"] += 1
            self._stats["active_connections"] += 1

            self._logger.info(f"Connection registered: {session_id}")

            # 异步调用状态变化回调
            await self._notify_state_change_callbacks(
                session_id,
                ConnectionState.DISCONNECTED,
                ConnectionState.CONNECTING,
            )

            return True

    async def unregister_connection(self, session_id: str) -> bool:
        """注销连接

        Args:
            session_id: 会话ID

        Returns:
            是否成功注销

        """
        with self._lock:
            if session_id not in self._connections:
                self._logger.warning(f"Connection not found: {session_id}")
                return False

            old_state = self._connections[session_id].state
            del self._connections[session_id]
            self._stats["active_connections"] -= 1

            self._logger.info(f"Connection unregistered: {session_id}")

            # 异步调用状态变化回调
            await self._notify_state_change_callbacks(
                session_id,
                old_state,
                ConnectionState.DISCONNECTED,
            )

            return True

    async def get_connection_state(self, session_id: str) -> WebSocketState | None:
        """获取连接状态

        Args:
            session_id: 会话ID

        Returns:
            连接状态

        """
        with self._lock:
            connection = self._connections.get(session_id)
            if connection:
                # 返回副本以避免外部修改
                return WebSocketState(
                    session_id=connection.session_id,
                    state=connection.state,
                    connected_at=connection.connected_at,
                    last_heartbeat=connection.last_heartbeat,
                    message_count=connection.message_count,
                    error_count=connection.error_count,
                    last_error=connection.last_error,
                    reconnect_attempts=connection.reconnect_attempts,
                    metadata=connection.metadata.copy(),
                )
            return None

    async def set_connection_state(self, session_id: str, state: ConnectionState) -> bool:
        """设置连接状态

        Args:
            session_id: 会话ID
            state: 新状态

        Returns:
            是否成功设置

        """
        with self._lock:
            if session_id not in self._connections:
                self._logger.warning(f"Connection not found: {session_id}")
                return False

            old_state = self._connections[session_id].state
            if old_state == state:
                return True  # 状态未变化

            self._connections[session_id].state = state

            # 更新连接时间
            if state == ConnectionState.CONNECTED and old_state != ConnectionState.CONNECTED:
                self._connections[session_id].connected_at = datetime.now(timezone.utc)
                self._connections[session_id].reconnect_attempts = 0
            elif state == ConnectionState.RECONNECTING:
                self._connections[session_id].reconnect_attempts += 1

            self._logger.info(
                f"Connection {session_id} state changed: {old_state.value} -> {state.value}",
            )

            # 异步调用状态变化回调
            await self._notify_state_change_callbacks(session_id, old_state, state)

            return True

    async def update_heartbeat(self, session_id: str) -> bool:
        """更新心跳

        Args:
            session_id: 会话ID

        Returns:
            是否成功更新

        """
        with self._lock:
            if session_id not in self._connections:
                self._logger.warning(f"Connection not found: {session_id}")
                return False

            self._connections[session_id].update_heartbeat()

            # 异步调用心跳回调
            await self._notify_heartbeat_callbacks(session_id)

            return True

    async def increment_message_count(self, session_id: str) -> bool:
        """增加消息计数

        Args:
            session_id: 会话ID

        Returns:
            是否成功增加

        """
        with self._lock:
            if session_id not in self._connections:
                self._logger.warning(f"Connection not found: {session_id}")
                return False

            self._connections[session_id].increment_message_count()
            self._stats["total_messages"] += 1

            return True

    async def increment_error_count(self, session_id: str, error: str | None = None) -> bool:
        """增加错误计数

        Args:
            session_id: 会话ID
            error: 错误信息

        Returns:
            是否成功增加

        """
        with self._lock:
            if session_id not in self._connections:
                self._logger.warning(f"Connection not found: {session_id}")
                return False

            self._connections[session_id].increment_error_count(error)
            self._stats["total_errors"] += 1

            # 如果错误过多，标记连接为错误状态
            if self._connections[session_id].error_count > 5:
                await self.set_connection_state(session_id, ConnectionState.ERROR)

            return True

    async def list_connections(self, state_filter: ConnectionState | None = None) -> list[str]:
        """列出连接

        Args:
            state_filter: 状态过滤器

        Returns:
            会话ID列表

        """
        with self._lock:
            if state_filter is None:
                return list(self._connections.keys())

            return [session_id for session_id, connection in self._connections.items() if connection.state == state_filter]

    async def get_healthy_connections(self) -> list[str]:
        """获取健康的连接

        Returns:
            健康连接的会话ID列表

        """
        with self._lock:
            return [session_id for session_id, connection in self._connections.items() if connection.is_healthy]

    async def cleanup_stale_connections(self) -> int:
        """清理过期连接

        Returns:
            清理的连接数量

        """
        cleaned_count = 0
        stale_connections = []

        with self._lock:
            current_time = datetime.now(timezone.utc)

            for session_id, connection in self._connections.items():
                # 检查连接是否过期
                is_stale = False

                if connection.state == ConnectionState.CONNECTED:
                    # 检查心跳超时
                    if connection.last_heartbeat:
                        heartbeat_age = current_time - connection.last_heartbeat
                        if heartbeat_age.total_seconds() > self.config.connection_timeout:
                            is_stale = True
                    # 没有心跳记录，检查连接时间
                    elif connection.connected_at:
                        connection_age = current_time - connection.connected_at
                        if connection_age.total_seconds() > self.config.connection_timeout:
                            is_stale = True
                elif connection.state in [
                    ConnectionState.CONNECTING,
                    ConnectionState.RECONNECTING,
                ]:
                    # 检查连接/重连超时
                    if connection.connected_at:
                        state_age = current_time - connection.connected_at
                        if state_age.total_seconds() > self.config.connection_timeout:
                            is_stale = True

                if is_stale:
                    stale_connections.append(session_id)

            # 清理过期连接
            for session_id in stale_connections:
                old_state = self._connections[session_id].state
                del self._connections[session_id]
                self._stats["active_connections"] -= 1
                self._stats["failed_connections"] += 1
                cleaned_count += 1

                self._logger.info(
                    f"Stale connection cleaned up: {session_id} (state: {old_state.value})",
                )

                # 异步调用状态变化回调
                await self._notify_state_change_callbacks(
                    session_id,
                    old_state,
                    ConnectionState.DISCONNECTED,
                )

        if cleaned_count > 0:
            self._stats["last_cleanup_time"] = datetime.now(timezone.utc).isoformat()
            self._logger.info(f"Cleaned up {cleaned_count} stale connections")

        return cleaned_count

    def set_state_change_callback(
        self,
        callback: Callable[[str, ConnectionState, ConnectionState], Awaitable[None]],
    ) -> None:
        """设置状态变化回调

        Args:
            callback: 状态变化回调函数

        """
        with self._lock:
            self._state_change_callbacks.append(callback)
            self._logger.debug("State change callback added")

    def set_heartbeat_callback(self, callback: Callable[[str], Awaitable[None]]) -> None:
        """设置心跳回调

        Args:
            callback: 心跳回调函数

        """
        with self._lock:
            self._heartbeat_callbacks.append(callback)
            self._logger.debug("Heartbeat callback added")

    async def start(self) -> None:
        """启动状态管理器"""
        if self._is_running:
            self._logger.warning("WebSocketStateManager is already running")
            return

        self._is_running = True
        self._stats["start_time"] = datetime.now(timezone.utc).isoformat()

        # 启动心跳检查任务
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        # 启动清理任务
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

        self._logger.info("WebSocketStateManager started")

    async def stop(self) -> None:
        """停止状态管理器"""
        if not self._is_running:
            self._logger.warning("WebSocketStateManager is not running")
            return

        self._is_running = False

        # 取消后台任务
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._heartbeat_task

        if self._cleanup_task:
            self._cleanup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._cleanup_task

        # 清理所有连接
        with self._lock:
            # Make a copy of keys to avoid modification during iteration
            session_ids = list(self._connections.keys())
            for session_id in session_ids:
                await self.unregister_connection(session_id)

        self._logger.info("WebSocketStateManager stopped")

    def get_statistics(self) -> dict[str, Any]:
        """获取统计信息

        Returns:
            统计信息字典

        """
        with self._lock:
            # 计算连接状态分布
            state_distribution = {}
            for connection in self._connections.values():
                state_name = connection.state.value
                state_distribution[state_name] = state_distribution.get(state_name, 0) + 1

            # 计算平均错误数
            avg_errors = 0
            if self._connections:
                total_errors = sum(conn.error_count for conn in self._connections.values())
                avg_errors = total_errors / len(self._connections)

            # 计算平均消息数
            avg_messages = 0
            if self._connections:
                total_messages = sum(conn.message_count for conn in self._connections.values())
                avg_messages = total_messages / len(self._connections)

            return {
                **self._stats,
                "current_connections": len(self._connections),
                "state_distribution": state_distribution,
                "average_errors_per_connection": avg_errors,
                "average_messages_per_connection": avg_messages,
                "config": {
                    "heartbeat_interval": self.config.heartbeat_interval,
                    "connection_timeout": self.config.connection_timeout,
                    "max_reconnect_attempts": self.config.max_reconnect_attempts,
                    "enable_auto_reconnect": self.config.enable_auto_reconnect,
                },
            }

    async def _notify_state_change_callbacks(
        self,
        session_id: str,
        old_state: ConnectionState,
        new_state: ConnectionState,
    ) -> None:
        """通知状态变化回调

        Note: Callback errors are logged but don't propagate to prevent external callback failures
        from breaking the state management system. This is intentional degradation tolerance.
        """
        for callback in self._state_change_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(session_id, old_state, new_state)
                else:
                    callback(session_id, old_state, new_state)
            except (TypeError, ValueError, KeyError, AttributeError, RuntimeError) as e:
                # Specific exceptions that commonly occur in callbacks
                self._logger.error(
                    f"Error in state change callback for session {session_id}: {e}",
                    exc_info=True,
                )
            except OSError as e:
                # System-level errors in callbacks (network, file operations)
                self._logger.error(
                    f"System error in state change callback for session {session_id}: {e}",
                    exc_info=True,
                )
            except Exception as e:
                # Catch-all for truly unexpected errors in external code
                self._logger.error(
                    f"Unexpected error in state change callback for session {session_id}: {e}",
                    exc_info=True,
                )

    async def _notify_heartbeat_callbacks(self, session_id: str) -> None:
        """通知心跳回调

        Note: Callback errors are logged but don't propagate to prevent external callback failures
        from breaking the state management system. This is intentional degradation tolerance.
        """
        for callback in self._heartbeat_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(session_id)
                else:
                    callback(session_id)
            except (TypeError, ValueError, KeyError, AttributeError, RuntimeError) as e:
                # Specific exceptions that commonly occur in callbacks
                self._logger.error(
                    f"Error in heartbeat callback for session {session_id}: {e}",
                    exc_info=True,
                )
            except OSError as e:
                # System-level errors in callbacks (network, file operations)
                self._logger.error(
                    f"System error in heartbeat callback for session {session_id}: {e}",
                    exc_info=True,
                )
            except Exception as e:
                # Catch-all for truly unexpected errors in external code
                self._logger.error(
                    f"Unexpected error in heartbeat callback for session {session_id}: {e}",
                    exc_info=True,
                )

    async def _heartbeat_loop(self) -> None:
        """心跳检查循环

        Note: Loop errors are logged but don't stop the loop to maintain service availability.
        This is intentional resilience for background services.
        """
        self._logger.info("Heartbeat loop started")

        while self._is_running:
            try:
                await asyncio.sleep(self.config.heartbeat_interval)
                await self._check_heartbeats()
            except asyncio.CancelledError:
                # Graceful shutdown on cancellation
                break
            except TimeoutError as e:
                # Timeout errors - log and continue loop
                self._logger.error(f"Timeout error in heartbeat loop: {e}", exc_info=True)
            except OSError as e:
                # Network/scheduling errors - log and continue loop
                self._logger.error(f"System error in heartbeat loop: {e}", exc_info=True)
            except Exception as e:
                # Unexpected errors - log with full traceback but continue loop
                self._logger.error(f"Unexpected error in heartbeat loop: {e}", exc_info=True)

        self._logger.info("Heartbeat loop stopped")

    async def _cleanup_loop(self) -> None:
        """清理循环

        Note: Loop errors are logged but don't stop the loop to maintain service availability.
        This is intentional resilience for background services.
        """
        self._logger.info("Cleanup loop started")

        while self._is_running:
            try:
                await asyncio.sleep(self.config.connection_timeout / 2)  # 更频繁的清理
                await self.cleanup_stale_connections()
            except asyncio.CancelledError:
                # Graceful shutdown on cancellation
                break
            except TimeoutError as e:
                # Timeout errors - log and continue loop
                self._logger.error(f"Timeout error in cleanup loop: {e}", exc_info=True)
            except OSError as e:
                # Network/scheduling errors - log and continue loop
                self._logger.error(f"System error in cleanup loop: {e}", exc_info=True)
            except Exception as e:
                # Unexpected errors - log with full traceback but continue loop
                self._logger.error(f"Unexpected error in cleanup loop: {e}", exc_info=True)

        self._logger.info("Cleanup loop stopped")

    async def _check_heartbeats(self) -> None:
        """检查心跳"""
        current_time = datetime.now(timezone.utc)
        timeout_connections = []

        with self._lock:
            for session_id, connection in self._connections.items():
                if connection.state == ConnectionState.CONNECTED:
                    if connection.last_heartbeat:
                        heartbeat_age = current_time - connection.last_heartbeat
                        if heartbeat_age.total_seconds() > self.config.connection_timeout:
                            timeout_connections.append(session_id)
                    # 没有心跳记录，检查连接时间
                    elif connection.connected_at:
                        connection_age = current_time - connection.connected_at
                        if connection_age.total_seconds() > self.config.connection_timeout:
                            timeout_connections.append(session_id)

        # 处理超时连接
        for session_id in timeout_connections:
            try:
                self._logger.warning(f"Connection timeout: {session_id}")
                await self.set_connection_state(session_id, ConnectionState.ERROR)

                # 如果启用自动重连
                if self.config.enable_auto_reconnect:
                    connection = await self.get_connection_state(session_id)
                    if connection and connection.reconnect_attempts < self.config.max_reconnect_attempts:
                        await self.set_connection_state(session_id, ConnectionState.RECONNECTING)
                        self._logger.info(
                            f"Attempting to reconnect: {session_id} (attempt {connection.reconnect_attempts})",
                        )
                    else:
                        self._logger.error(f"Max reconnect attempts reached for: {session_id}")
                        await self.unregister_connection(session_id)
            except (KeyError, ValueError, AttributeError) as e:
                # Specific errors in connection state management - these are coding bugs
                self._logger.error(
                    f"Failed to process timeout connection {session_id}: {e}",
                    exc_info=True,
                )
                raise  # Fast Fail: these are bugs that should be fixed
            except TypeError as e:
                # Type errors in timeout processing - programming bug
                self._logger.error(
                    f"Type error processing timeout connection {session_id}: {e}",
                    exc_info=True,
                )
                raise  # Fast Fail: this is a bug that should be fixed
            except Exception as e:
                # Unexpected errors in timeout processing
                self._logger.error(
                    f"Unexpected error processing timeout connection {session_id}: {e}",
                    exc_info=True,
                )
                # Attempt cleanup as fallback
                try:
                    await self.unregister_connection(session_id)
                except Exception as cleanup_error:
                    # Cleanup failures are logged but don't propagate - intentional tolerance
                    self._logger.error(
                        f"Error cleaning up failed connection {session_id}: {cleanup_error}",
                        exc_info=True,
                    )

    def __str__(self) -> str:
        """字符串表示"""
        return f"WebSocketStateManager(connections={len(self._connections)}, running={self._is_running})"

    def __repr__(self) -> str:
        """详细字符串表示"""
        return f"WebSocketStateManager(connections={len(self._connections)}, running={self._is_running}, config={self.config})"
