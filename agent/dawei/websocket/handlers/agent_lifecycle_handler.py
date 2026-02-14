# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Agent Lifecycle Handlers

处理 Agent 生命周期控制消息：停止
"""

from typing import Any

from dawei.agentic.agent import Agent
from dawei.logg.logging import get_logger
from dawei.websocket.protocol import (
    AgentStopMessage,
    AgentStoppedMessage,
    MessageType,
    SystemWebSocketMessage,
    WebSocketMessage,
)

from .base_message_handler import BaseMessageHandler

logger = get_logger(__name__)


class AgentLifecycleHandler(BaseMessageHandler):
    """Agent生命周期处理器

    处理 Agent 的停止操作:
    - 验证消息类型
    - 查找活跃的 Agent 实例
    - 调用 Agent 的 stop 方法
    - 发送确认消息到前端
    - 错误处理和清理
    """

    def __init__(self, active_agents: dict[str, Agent], send_message_callback, send_error_callback):
        """初始化 Agent 生命周期处理器

        Args:
            active_agents: 活跃 Agent 实例字典的引用
            send_message_callback: 发送消息的回调函数
            send_error_callback: 发送错误消息的回调函数
        """
        # 不调用 super().__init__() 因为这个 handler 不需要完整的初始化
        self._active_agents = active_agents
        self._send_message = send_message_callback
        self._send_error = send_error_callback

    async def process_stop(
        self,
        session_id: str,
        message: WebSocketMessage,
        cleanup_callback,
    ) -> WebSocketMessage | None:
        """处理 Agent 停止请求

        Args:
            session_id: 会话 ID
            message: AgentStopMessage
            cleanup_callback: 清理事件处理器的回调函数

        Returns:
            None (异步发送消息)

        Raises:
            ValueError: 如果消息类型无效

        """
        # Fast Fail: 验证消息类型
        if not isinstance(message, AgentStopMessage):
            logger.error(f"Invalid message type for AGENT_STOP: {type(message)}")
            return await self._send_error(
                session_id,
                "INVALID_MESSAGE_TYPE",
                "Invalid message type for agent stop",
            )

        task_id = message.task_id
        logger.info(f"Received stop request for task {task_id}")
        logger.debug(f"Current active agents: {list(self._active_agents.keys())}")

        # 查找对应的 Agent 实例
        if task_id not in self._active_agents:
            logger.warning(f"No active agent found for task {task_id}")
            # Agent 可能已经完成或被清理，这实际上不是错误
            # 发送停止确认消息，告知用户任务已经结束
            stopped_message = AgentStoppedMessage(
                session_id=session_id,
                task_id=task_id,
                stopped_at=message.timestamp,
                result_summary="任务已经结束或完成",
                partial=False,  # 任务已完成（非部分完成）
            )
            await self._send_message(session_id, stopped_message)
            logger.info(f"Task {task_id} was already completed, sent AgentStoppedMessage")
            return None

        agent = self._active_agents[task_id]

        # 停止 Agent
        try:
            # 调用 Agent 的 stop 方法
            logger.info(f"Calling agent.stop() for task {task_id}")
            result_summary = await agent.stop()
            logger.info(f"agent.stop() returned successfully for task {task_id}")

            # 从活跃 agents 中移除
            if task_id in self._active_agents:
                del self._active_agents[task_id]

            # 清理事件处理器
            await cleanup_callback(task_id, agent)

            # 发送停止确认消息
            try:
                stopped_message = AgentStoppedMessage(
                    session_id=session_id,
                    task_id=task_id,
                    stopped_at=message.timestamp,
                    result_summary=result_summary or "Agent已停止",
                    partial=True,  # 用户主动停止，视为部分完成
                )
                await self._send_message(session_id, stopped_message)
                logger.info(f"Sent AgentStoppedMessage for task {task_id}")
            except Exception as msg_error:
                logger.error(f"Failed to send AgentStoppedMessage: {msg_error}", exc_info=True)

            logger.info(f"Task {task_id} stopped successfully")
            return None

        except Exception as e:
            logger.error(f"Failed to stop agent for task {task_id}: {e}", exc_info=True)
            # 即使停止失败，也尝试从 active_agents 中移除
            if task_id in self._active_agents:
                del self._active_agents[task_id]

            # 清理事件处理器
            await cleanup_callback(task_id, agent)

            # 发送错误消息，但不重新抛出异常
            try:
                await self._send_error(
                    session_id,
                    "STOP_FAILED",
                    f"Failed to stop agent: {e!s}",
                )
            except Exception as send_error:
                logger.error(f"Failed to send error message: {send_error}", exc_info=True)
            return None
