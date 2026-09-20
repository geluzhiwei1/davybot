# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""WebSocket服务器

整合所有WebSocket组件，提供统一的WebSocket服务器实现。
"""

import json
import uuid
from typing import List, Dict, Any

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from dawei.logg.logging import clear_logging_context, get_logger
from dawei.storage import LocalFileSystemStorage

from .handlers import ChatHandler, ErrorHandler, ModeSwitchHandler, StreamHandler, TaskNodeControlHandler
from .handlers.tool_approval import ToolApprovalHandler
from .manager import WebSocketManager
from .message_validation_middleware import MessageValidationMiddleware
from .protocol import ErrorMessage, MessageSerializer
from .router import MessageRouter
from .session import SessionManager

logger = get_logger(__name__)


class WebSocketServer:
    """WebSocket服务器"""

    def __init__(self):
        """初始化WebSocket服务器"""
        from pathlib import Path

        # 使用 get_dawei_home 获取标准路径
        from dawei import get_dawei_home

        session_root = str(get_dawei_home() / "sessions")
        self.storage = LocalFileSystemStorage(root_dir=session_root)

        # connection_timeout=180s (3 min) instead of the 60s default. Browsers
        # throttle setInterval in backgrounded tabs to ~1/min after ~5 min, so a
        # 60s timeout disconnects live-but-backgrounded sessions ("连接超时"),
        # causing the periodic WS resets. 180s tolerates that throttling (and
        # brief network hiccups) while still reaping genuinely dead connections.
        self.websocket_manager = WebSocketManager(connection_timeout=180)
        self.session_manager = SessionManager(storage=self.storage)
        self.message_router = MessageRouter(self.websocket_manager)

        # Message validation middleware
        self.validation_middleware = MessageValidationMiddleware(
            max_message_size=1024 * 1024,  # 1MB
            max_messages_per_second=100,
            max_burst_messages=200,
            enabled_checks={"rate_limit", "size", "patterns"},  # Enable all security checks
        )

        # 消息处理器
        self.chat_handler = ChatHandler()
        self.stream_handler = StreamHandler()
        self.mode_handler = ModeSwitchHandler()
        self.tool_approval_handler = ToolApprovalHandler()  # P2.2 人在回路审批
        self.task_node_control_handler = TaskNodeControlHandler()  # P1b ⑩ 任务节点终结
        self.error_handler = None  # 将在initialize中设置

        self._is_initialized = False

    async def initialize(self):
        """初始化服务器"""
        if self._is_initialized:
            return

        # 设置全局 ChatHandler 实例
        from dawei.websocket.handlers.chat import set_chat_handler_instance

        set_chat_handler_instance(self.chat_handler)

        # 启动组件
        await self.websocket_manager.start()
        await self.session_manager.start()
        await self.message_router.start()

        # 初始化处理器
        await self.chat_handler.initialize(
            self.message_router,
            self.websocket_manager,
            self.session_manager,
        )
        await self.stream_handler.initialize(
            self.message_router,
            self.websocket_manager,
            self.session_manager,
        )
        await self.mode_handler.initialize(
            self.message_router,
            self.websocket_manager,
            self.session_manager,
        )
        # 错误处理器不需要初始化，直接使用
        self.error_handler = ErrorHandler()
        await self.error_handler.initialize(
            self.message_router,
            self.websocket_manager,
            self.session_manager,
        )

        # 注册处理器
        await self.message_router.register_handler(self.chat_handler)
        await self.message_router.register_handler(self.stream_handler)
        await self.message_router.register_handler(self.mode_handler)
        await self.message_router.register_handler(self.error_handler)

        # P2.2 工具审批处理器（处理前端的 tool_approval_response）
        await self.tool_approval_handler.initialize(
            self.message_router,
            self.websocket_manager,
            self.session_manager,
        )
        await self.message_router.register_handler(self.tool_approval_handler)

        # P1b ⑩ 任务节点控制处理器：TASK_NODE_STOP 自 ChatHandler 迁入独立处理器
        # （路由器按类型并行执行所有声明处理器，ChatHandler 已摘除该类型，无双发）
        await self.task_node_control_handler.initialize(
            self.message_router,
            self.websocket_manager,
            self.session_manager,
        )
        await self.message_router.register_handler(self.task_node_control_handler)

        # P2.2 注册审批 publisher：把 tool_approval_request 推给拥有该 task 的客户端。
        # gate 默认 enabled=False（惰性），此 publisher 仅在审批被显式开启时才被调用。
        from dawei.core.approval_gate import approval_gate
        from dawei.websocket.protocol import ToolApprovalRequestMessage

        websocket_manager = self.websocket_manager

        async def _approval_publisher(request: dict) -> bool:
            """Deliver a tool_approval_request to the owning client. Returns delivered."""
            try:
                from dawei.websocket.handlers.chat import chat_handler_instance

                if chat_handler_instance is None:
                    return False
                task_id = request.get("task_id")
                session_id = None
                if task_id:
                    session_id = chat_handler_instance._task_to_session_map.get(task_id)
                if not session_id:
                    return False  # 无对应客户端 → gate 走 no_channel_behavior
                msg = ToolApprovalRequestMessage(
                    session_id=session_id,
                    request_id=request["request_id"],
                    task_id=task_id,
                    tool_name=request["tool"],
                    risk=request["risk"],
                    tool_input=request.get("args", {}),
                    timeout_seconds=request.get("timeout_seconds", 120.0),
                )
                await websocket_manager.send_message(session_id, msg)
                return True
            except Exception as e:
                logger.warning("Approval publisher failed: %s", e)
                return False

        approval_gate.set_publisher(_approval_publisher)

        # 添加连接监听器
        self.websocket_manager.add_connection_listener(self._on_connection_event)

        # 添加错误处理器
        self.websocket_manager.add_error_handler(self._on_error)

        self._is_initialized = True
        logger.info("WebSocket服务器已初始化")

    async def shutdown(self):
        """关闭服务器"""
        if not self._is_initialized:
            return

        # 注销处理器
        await self.message_router.unregister_handler(self.chat_handler)
        await self.message_router.unregister_handler(self.stream_handler)
        await self.message_router.unregister_handler(self.mode_handler)
        await self.message_router.unregister_handler(self.error_handler)
        await self.message_router.unregister_handler(self.task_node_control_handler)

        # 清理处理器
        await self.chat_handler.cleanup()
        await self.stream_handler.cleanup()
        await self.mode_handler.cleanup()
        await self.error_handler.cleanup()
        await self.task_node_control_handler.cleanup()

        # 停止组件
        await self.message_router.stop()
        await self.session_manager.stop()
        await self.websocket_manager.stop()

        self._is_initialized = False
        logger.info("WebSocket服务器已关闭")

    async def handle_websocket(
        self,
        websocket: WebSocket,
        session_id: str | None = None,
        user_id: str | None = None,
        workspace_id: str | None = None,
        conversation_id: str | None = None,
    ):
        """处理WebSocket连接

        Args:
            websocket: WebSocket连接对象
            session_id: 会话ID
            user_id: 用户ID
            workspace_id: 工作空间ID
            conversation_id: 对话ID

        """
        await websocket.accept()
        if not self._is_initialized:
            await self._send_error_and_close(
                websocket,
                "SERVER_NOT_INITIALIZED",
                "WebSocket服务器未初始化",
            )
            return

        # 生成会话ID
        if not session_id:
            session_id = str(uuid.uuid4())

        try:
            # 建立连接
            connected = await self.websocket_manager.connect(websocket, session_id, workspace_id=workspace_id)
            if not connected:
                await self._send_error_and_close(websocket, "CONNECTION_FAILED", "建立连接失败")
                return

            # 创建或获取会话
            session_data = await self.session_manager.get_session(session_id)
            if not session_data:
                session_data = await self.session_manager.create_session(
                    session_id=session_id,
                    user_id=user_id,
                    workspace_id=workspace_id,
                    conversation_id=conversation_id,
                    metadata={
                        "connected_at": (getattr(websocket.client, "host", "unknown") if websocket.client else "unknown"),
                    },
                )
            else:
                # 更新会话信息
                await self.session_manager.update_session(
                    session_id=session_id,
                    user_id=user_id,
                    workspace_id=workspace_id,
                    conversation_id=conversation_id,
                )
                # v2: 通知沙箱 Provider 恢复并排空 grace 期队列 (§5.3)
                try:
                    await session_data.on_reconnect()
                except Exception as e:
                    logger.warning(f"沙箱 on_reconnect 失败: {e}")

            # 处理消息循环
            await self._message_loop(websocket, session_id)

        except WebSocketDisconnect:
            logger.info(f"WebSocket客户端断开连接: {session_id}")
        except Exception as e:
            logger.exception("WebSocket处理错误")
            await self._send_error_and_close(
                websocket,
                "WEBSOCKET_ERROR",
                f"WebSocket处理错误: {e!s}",
            )
        finally:
            # v2: 通知沙箱 Provider 进入 grace 期 (§5.3)
            try:
                session_data = await self.session_manager.get_session(session_id)
                if session_data:
                    await session_data.on_close()
            except Exception as e:
                logger.warning(f"沙箱 on_close 失败: {e}")
            # 断开连接
            await self.websocket_manager.disconnect(session_id, "连接结束")

    async def _message_loop(self, websocket: WebSocket, session_id: str):
        """消息处理循环

        Args:
            websocket: WebSocket连接对象
            session_id: 会话ID

        """
        try:
            message_count = 0
            while True:
                data = await websocket.receive_text()
                message_count += 1

                # 调试日志：确认消息被接收
                logger.debug(
                    f"📥 [WS_RAW] #{message_count} 收到原始数据 (length={len(data)}): {data[:200]}",
                )

                # Refresh session timestamp on any incoming message (including heartbeats)
                # to prevent the session cleanup from deleting sessions with active connections.
                try:
                    await self.session_manager.get_session(session_id)
                except Exception:
                    pass

                try:
                    # 1. 反序列化和验证消息
                    try:
                        message = MessageSerializer.deserialize(data)
                        message_id = message.id
                        message_type = message.type
                    except (ValidationError, json.JSONDecodeError) as e:
                        logger.warning(f"消息反序列化失败: {e}")
                        await self.websocket_manager.send_error_message(
                            session_id,
                            "DESERIALIZATION_ERROR",
                            f"消息反序列化失败: {e!s}",
                        )
                        continue  # Skip processing this message

                    # 只对非心跳消息输出详细日志
                    if message_type != "ws_heartbeat":
                        logger.info(f"📨 [WS] 收到原始消息: {data[:500]}")
                        logger.info(
                            f"✅ [WS] 消息反序列化成功: type={message_type}, id={message_id}, session_id={message.session_id}",
                        )

                    # 2. Security validation using middleware
                    (
                        is_valid,
                        error_message,
                    ) = await self.validation_middleware.validate_message(
                        session_id,
                        message,
                        raw_data=data,
                    )

                    if not is_valid:
                        logger.warning(f"Message validation failed: {error_message}")
                        # Surface the rejection to the originating conversation.
                        # send_error_message() builds an ErrorMessage WITHOUT a
                        # conversation_id, so the frontend chat-store (which routes
                        # strictly by conversation_id) would silently drop it and the
                        # user would see their message hang forever. Build the error
                        # with the message's conversation_id so it renders in the chat.
                        conv_id = getattr(message, "conversation_id", None)
                        try:
                            from dawei.websocket.protocol import ErrorMessage

                            validation_error = ErrorMessage(
                                session_id=session_id,
                                code="VALIDATION_ERROR",
                                message=error_message or "消息被安全校验拦截，请修改后重试。",
                                details={
                                    "reason": "validation_blocked",
                                    "message_type": message_type,
                                },
                                recoverable=True,
                                conversation_id=conv_id,
                            )
                            await self.websocket_manager.send_message(session_id, validation_error)
                        except Exception as send_err:
                            logger.warning(f"Failed to send routed validation error: {send_err}")
                            await self.websocket_manager.send_error_message(
                                session_id,
                                "VALIDATION_ERROR",
                                error_message or "Message validation failed",
                            )
                        continue  # Skip processing this message

                    # 3. 路由消息
                    await self.message_router.route_message(session_id, message, message_id)

                except json.JSONDecodeError:
                    logger.warning(f"无效的JSON消息: {data[:100]}")
                    await self.websocket_manager.send_error_message(
                        session_id,
                        "INVALID_JSON",
                        "消息必须是有效的JSON格式",
                    )
                except (ValidationError, ValueError) as e:
                    logger.warning(f"消息验证失败: {e}")
                    await self.websocket_manager.send_error_message(
                        session_id,
                        "INVALID_FORMAT",
                        f"消息格式无效: {e!s}",
                    )
                except Exception as e:
                    logger.error(f"处理消息时发生意外错误: {e}", exc_info=True)
                    await self.websocket_manager.send_error_message(
                        session_id,
                        "MESSAGE_ROUTING_ERROR",
                        f"消息路由失败: {e!s}",
                    )
                finally:
                    clear_logging_context()

        except WebSocketDisconnect:
            raise  # 重新抛出以由外部处理
        except Exception as e:
            logger.error(f"消息循环中的意外错误: {e}", exc_info=True)
            raise  # 重新抛出以由外部处理

    async def _on_connection_event(self, event: str, session_id: str, _connection_info):
        """连接事件监听器

        Args:
            event: 事件类型
            session_id: 会话ID
            connection_info: 连接信息

        """
        logger.info(f"连接事件: {event} - {session_id}")

        if event == "connect":
            # 连接建立时的处理
            pass
        elif event == "disconnect":
            # 连接断开时的处理
            pass

    async def _on_error(self, error_type: str, error_data: Dict[str, Any]):
        """错误事件处理器

        Args:
            error_type: 错误类型
            error_data: 错误数据

        """
        logger.error(f"WebSocket错误 ({error_type}): {error_data}")

        # 可以在这里添加错误上报、日志记录等逻辑

    async def _send_error_and_close(self, websocket: WebSocket, code: str, message: str):
        """发送错误消息并关闭连接

        Args:
            websocket: WebSocket连接对象
            code: 错误代码
            message: 错误消息

        """
        try:
            error_message = ErrorMessage(
                session_id="unknown",
                code=code,
                message=message,
                recoverable=False,
            )
            await websocket.send_text(MessageSerializer.serialize(error_message))
            await websocket.close()
        except Exception:
            logger.exception("发送错误消息失败: ")

    async def broadcast_message(self, message: Any, exclude_sessions: list | None = None, workspace_id: str | None = None):
        """广播消息到所有连接

        Args:
            message: 消息对象
            exclude_sessions: 排除的会话ID列表
            workspace_id: 若提供,仅广播给该 workspace 的连接

        """
        if not self._is_initialized:
            logger.warning("WebSocket服务器未初始化，无法广播消息")
            return

        # 如果是字典，转换为消息对象
        if isinstance(message, dict):
            # 尝试创建消息对象
            try:
                message_type = message.get("type", "info")
                session_id = message.get("session_id", "broadcast")

                from .protocol import BaseMessage

                # 安全地过滤和传递参数
                filtered_message = {k: v for k, v in message.items() if k not in ["type", "session_id"]}
                base_message = BaseMessage(
                    type=message_type,
                    session_id=session_id,
                    **filtered_message,
                )
                await self.websocket_manager.broadcast(base_message, exclude_sessions, workspace_id=workspace_id)
            except (KeyError, TypeError, AttributeError):
                logger.exception("广播消息失败 - 字典转换错误: ")
            except Exception:
                logger.exception("广播消息失败 - 未知错误: ")
        else:
            # 直接广播
            try:
                await self.websocket_manager.broadcast(message, exclude_sessions, workspace_id=workspace_id)
            except Exception:
                logger.exception("广播消息失败 - 直接广播错误: ")

    async def get_server_status(self) -> Dict[str, Any]:
        """获取服务器状态

        Returns:
            服务器状态信息

        """
        if not self._is_initialized:
            return {"status": "not_initialized", "message": "WebSocket服务器未初始化"}

        # 获取各组件状态
        connection_count = self.websocket_manager.get_connection_count()
        session_count = await self.session_manager.get_session_count()

        # 获取错误统计
        error_stats = self.websocket_manager.get_error_statistics()

        return {
            "status": "running",
            "connections": connection_count,
            "sessions": session_count,
            "errors": error_stats,
            "handlers": {
                "chat": getattr(self.chat_handler, "get_name", lambda: "unknown")(),
                "stream": getattr(self.stream_handler, "get_name", lambda: "unknown")(),
                "error": (getattr(self.error_handler, "get_name", lambda: "unknown")() if self.error_handler else "unknown"),
            },
        }

    # set_orchestrator 方法已被移除，因为 ChatHandler 现在内部使用 AgenticTask

    def get_websocket_manager(self) -> WebSocketManager:
        """获取WebSocket管理器"""
        return self.websocket_manager

    def get_session_manager(self) -> SessionManager:
        """获取会话管理器"""
        return self.session_manager

    def get_message_router(self) -> MessageRouter:
        """获取消息路由器"""
        return self.message_router


# 全局WebSocket服务器实例
# 注意：在TUI模式下不初始化WebSocket服务器，以避免产生误导性错误日志
import os

IS_TUI_MODE = os.getenv("DAWEI_TUI_MODE", "false").lower() == "true"

if not IS_TUI_MODE:
    websocket_server = WebSocketServer()
else:
    # TUI模式下使用None，通过getter延迟初始化（如果需要）
    websocket_server = None
