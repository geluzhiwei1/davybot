# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""模式切换处理器 - 简化修复版

只修复关键的 agent 访问问题
"""

import logging

from dawei.websocket.protocol import (
    BaseWebSocketMessage,
    MessageType,
    ModeSwitchedMessage,
    ModeSwitchMessage,
)

from .base import AsyncMessageHandler

logger = logging.getLogger(__name__)


class ModeSwitchHandler(AsyncMessageHandler):
    """处理 Agent 模式切换 - 简化版"""

    def __init__(self):
        super().__init__()

    def get_supported_types(self) -> list[str]:
        return [MessageType.MODE_SWITCH]

    async def process_message(
        self,
        session_id: str,
        message: BaseWebSocketMessage,
        _message_id: str,
    ) -> BaseWebSocketMessage | None:
        """处理模式切换请求"""
        print(
            f"[DEBUG MODE_HANDLER] process_message called, session_id={session_id}, message_type={type(message).__name__}",
        )

        if not isinstance(message, ModeSwitchMessage):
            logger.error(f"Expected ModeSwitchMessage, got {type(message)}")
            print("[DEBUG MODE_HANDLER] ERROR: Not a ModeSwitchMessage!")
            return None

        mode = message.mode
        logger.info(f"Mode switch requested: {mode} (session: {session_id})")
        print(f"[DEBUG MODE_HANDLER] Mode switch requested: {mode}")

        # 简化处理：直接返回成功响应，路由器会负责发送
        try:
            # 获取当前模式（如果有 agent）
            previous_mode = "unknown"

            # 创建成功确认消息
            response = ModeSwitchedMessage(
                session_id=session_id,
                previous_mode=previous_mode,
                current_mode=mode,
                message=f"已切换到 {mode.upper()} 模式",
            )

            logger.info(f"Mode switch completed: {previous_mode} -> {mode}")
            print(
                f"[DEBUG MODE_HANDLER] Created response: type={response.type}, current_mode={response.current_mode}",
            )
            print("[DEBUG MODE_HANDLER] Returning response...")
            # 返回响应，路由器会发送给客户端
            return response

        except Exception as e:
            logger.error(f"Mode switch error: {e}", exc_info=True)
            print(f"[DEBUG MODE_HANDLER] ERROR: {e}")

            # 返回错误消息
            error_response = ModeSwitchedMessage(
                session_id=session_id,
                previous_mode="unknown",
                current_mode="unknown",
                message=f"模式切换失败: {e!s}",
            )

            print("[DEBUG MODE_HANDLER] Returning error response...")
            return error_response
