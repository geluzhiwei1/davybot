# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""任务节点控制消息处理器
处理前端的暂停、恢复、停止任务节点请求
"""

from typing import Any

from dawei.logg.logging import get_logger
from dawei.websocket.protocol import (
    MessageType,
    TaskNodePausedMessage,
    TaskNodePauseMessage,
    TaskNodeResumedMessage,
    TaskNodeResumeMessage,
    TaskNodeStopMessage,
    TaskNodeStoppedMessage,
)

from .base import AsyncMessageHandler

logger = get_logger(__name__)


class TaskNodeControlHandler(AsyncMessageHandler):
    """任务节点控制处理器

    处理前端发送的任务节点控制请求（暂停、恢复、停止），
    并返回控制结果通知
    """

    def __init__(self, task_graph_executor=None):
        """初始化处理器

        Args:
            task_graph_executor: TaskGraphExecutionEngine实例（可选）

        """
        super().__init__(max_concurrent_tasks=10)
        self.task_graph_executor = task_graph_executor
        logger.info("TaskNodeControlHandler initialized")

    def get_supported_types(self) -> list:
        """获取支持的消息类型"""
        return [
            MessageType.TASK_NODE_PAUSE,
            MessageType.TASK_NODE_RESUME,
            MessageType.TASK_NODE_STOP,
        ]

    async def on_initialize(self):
        """初始化时的回调"""
        await super().on_initialize()
        logger.info("任务节点控制处理器已初始化")

    async def process_message(
        self,
        session_id: str,
        message,
        _message_id: str,
    ) -> dict[str, Any] | None:
        """处理任务节点控制消息

        Args:
            session_id: 会话ID
            message: WebSocket消息（TaskNodePauseMessage/ResumeMessage/StopMessage）
            message_id: 消息ID

        Returns:
            控制结果（可选）

        """
        try:
            if message.type == MessageType.TASK_NODE_PAUSE:
                return await self._handle_pause(session_id, message)

            if message.type == MessageType.TASK_NODE_RESUME:
                return await self._handle_resume(session_id, message)

            if message.type == MessageType.TASK_NODE_STOP:
                return await self._handle_stop(session_id, message)

            logger.warning(f"不支持的消息类型: {message.type}")
            return None

        except (AttributeError, KeyError, ValueError, TypeError) as e:
            logger.error(f"处理任务节点控制消息失败: {e}", exc_info=True)
            # 返回错误消息
            return {
                "type": "error",
                "error": str(e),
                "task_node_id": getattr(message, "task_node_id", None),
            }

    async def _handle_pause(self, session_id: str, message: TaskNodePauseMessage) -> dict[str, Any]:
        """处理暂停请求"""
        task_node_id = message.task_node_id
        reason = message.reason or "User requested pause"

        logger.info(f"[{session_id}] 暂停任务节点: {task_node_id}, 原因: {reason}")

        # Call TaskGraphExecutionEngine to pause task
        # If task_graph_executor exists, call its method
        if self.task_graph_executor:
            try:
                # TaskGraphExecutionEngine needs to implement pause_task method
                # success = await self.task_graph_executor.pause_task(task_node_id)
                success = True  # Temporary placeholder

                if success:
                    # Send paused notification
                    TaskNodePausedMessage(
                        session_id=session_id,
                        task_node_id=task_node_id,
                        reason=reason,
                    )

                    # Send back to frontend via WebSocket
                    # await self.websocket_manager.send(session_id, paused_msg.to_dict())

                    return {
                        "type": "task_node_paused",
                        "task_node_id": task_node_id,
                        "success": True,
                        "reason": reason,
                    }
                return {
                    "type": "error",
                    "task_node_id": task_node_id,
                    "error": "Failed to pause task",
                    "success": False,
                }
            except (AttributeError, KeyError, ValueError, TypeError, RuntimeError) as e:
                logger.error(f"暂停任务失败: {e}", exc_info=True)
                return {
                    "type": "error",
                    "task_node_id": task_node_id,
                    "error": str(e),
                    "success": False,
                }
        else:
            logger.warning("TaskGraphExecutor未设置，无法执行暂停操作")
            return {
                "type": "error",
                "task_node_id": task_node_id,
                "error": "TaskGraphExecutor not available",
                "success": False,
            }

    async def _handle_resume(
        self,
        session_id: str,
        message: TaskNodeResumeMessage,
    ) -> dict[str, Any]:
        """处理恢复请求"""
        task_node_id = message.task_node_id

        logger.info(f"[{session_id}] 恢复任务节点: {task_node_id}")

        # Call TaskGraphExecutionEngine to resume task
        if self.task_graph_executor:
            try:
                # success = await self.task_graph_executor.resume_task(task_node_id)
                success = True  # Temporary placeholder

                if success:
                    # Send resumed notification
                    TaskNodeResumedMessage(
                        session_id=session_id,
                        task_node_id=task_node_id,
                    )

                    # Send back to frontend via WebSocket
                    # await self.websocket_manager.send(session_id, resumed_msg.to_dict())

                    return {
                        "type": "task_node_resumed",
                        "task_node_id": task_node_id,
                        "success": True,
                    }
                return {
                    "type": "error",
                    "task_node_id": task_node_id,
                    "error": "Failed to resume task",
                    "success": False,
                }
            except (AttributeError, KeyError, ValueError, TypeError, RuntimeError) as e:
                logger.error(f"恢复任务失败: {e}", exc_info=True)
                return {
                    "type": "error",
                    "task_node_id": task_node_id,
                    "error": str(e),
                    "success": False,
                }
        else:
            logger.warning("TaskGraphExecutor未设置，无法执行恢复操作")
            return {
                "type": "error",
                "task_node_id": task_node_id,
                "error": "TaskGraphExecutor not available",
                "success": False,
            }

    async def _handle_stop(self, session_id: str, message: TaskNodeStopMessage) -> dict[str, Any]:
        """处理停止请求"""
        task_node_id = message.task_node_id
        reason = message.reason or "User requested stop"

        logger.info(f"[{session_id}] 停止任务节点: {task_node_id}, 原因: {reason}")

        # Call TaskGraphExecutionEngine to stop task
        if self.task_graph_executor:
            try:
                # success = await self.task_graph_executor.cancel_task_execution(task_node_id)
                success = True  # Temporary placeholder

                if success:
                    # Send stopped notification
                    TaskNodeStoppedMessage(
                        session_id=session_id,
                        task_node_id=task_node_id,
                        reason=reason,
                    )

                    # Send back to frontend via WebSocket
                    # await self.websocket_manager.send(session_id, stopped_msg.to_dict())

                    return {
                        "type": "task_node_stopped",
                        "task_node_id": task_node_id,
                        "success": True,
                        "reason": reason,
                    }
                return {
                    "type": "error",
                    "task_node_id": task_node_id,
                    "error": "Failed to stop task",
                    "success": False,
                }
            except (AttributeError, KeyError, ValueError, TypeError, RuntimeError) as e:
                logger.error(f"停止任务失败: {e}", exc_info=True)
                return {
                    "type": "error",
                    "task_node_id": task_node_id,
                    "error": str(e),
                    "success": False,
                }
        else:
            logger.warning("TaskGraphExecutor未设置，无法执行停止操作")
            return {
                "type": "error",
                "task_node_id": task_node_id,
                "error": "TaskGraphExecutor not available",
                "success": False,
            }

    def set_task_graph_executor(self, executor):
        """设置TaskGraphExecutor实例

        Args:
            executor: TaskGraphExecutionEngine实例

        """
        self.task_graph_executor = executor
        logger.info("TaskGraphExecutor已设置")
