# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""System Command Handler

处理系统命令（!命令）执行
使用轻量级沙箱执行用户命令
"""

import json
import time
import uuid
from typing import Any

from dawei.entity.lm_messages import AssistantMessage, UserMessage
from dawei.logg.logging import get_logger
from dawei.sandbox.lightweight_executor import LightweightSandbox
from dawei.websocket.protocol import (
    AssistantWebSocketMessage,
    ErrorMessage,
    MessageType,
    TaskNodeCompleteMessage,
)

logger = get_logger(__name__)


class SystemCommandHandler:
    """系统命令处理器

    使用轻量级沙箱执行系统命令：
    - 验证命令格式
    - 安全执行命令（不使用 Docker）
    - 限制输出大小
    - 发送命令结果到前端
    - 保存命令结果到对话历史
    - 错误处理和日志记录
    """

    # 输出大小限制
    MAX_OUTPUT_SIZE = 100000  # 100KB

    def __init__(self, send_message_callback):
        """初始化系统命令处理器

        Args:
            send_message_callback: 发送消息的回调函数

        """
        self._send_message = send_message_callback
        self.sandbox_executor = LightweightSandbox()
        logger.info("[SYSTEM_COMMAND] LightweightSandbox initialized (no Docker required)")

    async def handle_command(
        self,
        command: str,
        session_id: str,
        task_id: str,
        user_workspace,
        user_message_content: str,
    ) -> bool:
        """处理系统命令(!命令) - 使用安全沙箱执行

        Args:
            command: 系统命令字符串（已去除 ! 前缀）
            session_id: 会话 ID
            task_id: 任务 ID
            user_workspace: 用户工作区实例
            user_message_content: 原始用户消息内容

        Returns:
            True if command was handled successfully, False otherwise

        Raises:
            ValueError: 如果命令参数无效
            IOError: 如果沙箱执行失败

        """
        try:
            logger.info(f"[SYSTEM_COMMAND] 检测到系统命令(轻量级沙箱模式): {command}")

            # Fast Fail: 验证必需参数
            if not command or not command.strip():
                logger.warning("[SYSTEM_COMMAND] Empty command received")
                return False

            # 使用轻量级沙箱执行命令（同步方法）
            result = self.sandbox_executor.execute_command(
                command=command,
                workspace_path=user_workspace.absolute_path,
                user_id=getattr(user_workspace, "user_id", session_id),
            )

            logger.info(f"[SYSTEM_COMMAND] 沙箱命令执行完成: exit_code={result['exit_code']}")

            # 提取结果
            success = result["success"]
            stdout = result.get("stdout", "")
            stderr = result.get("stderr", "")
            exit_code = result.get("exit_code", -1)
            execution_time = result.get("execution_time", 0)

            # Fast Fail: 检查执行是否失败
            if not success:
                error_message = ErrorMessage(
                    session_id=session_id,
                    code="SANDBOX_EXECUTION_ERROR",
                    message=result.get("error", "Unknown error"),
                    recoverable=False,
                    details={"command": command, "exit_code": exit_code},
                )
                await self._send_message(session_id, error_message)
                return False

            # 1. 发送系统命令结果到前端
            await self._send_command_result(
                session_id=session_id,
                task_id=task_id,
                command=command,
                stdout=stdout,
                stderr=stderr,
                exit_code=exit_code,
                execution_time=execution_time,
                workspace_path=user_workspace.absolute_path,
            )

            # 2. 保存到对话历史（维持上下文）
            if user_workspace.current_conversation:
                self._save_command_to_history(
                    user_workspace=user_workspace,
                    user_message_content=user_message_content,
                    command=command,
                    stdout=stdout,
                    stderr=stderr,
                    exit_code=exit_code,
                )

            # 3. 发送任务完成消息
            await self._send_task_complete(
                session_id=session_id,
                task_id=task_id,
                command=command,
                exit_code=exit_code,
                execution_time=execution_time,
            )

            logger.info("[SYSTEM_COMMAND] ✅ 沙箱命令执行成功")
            return True

        except Exception as e:
            logger.error(f"[SYSTEM_COMMAND] 沙箱命令执行出错: {e}", exc_info=True)

            # 发送错误消息
            error_message = ErrorMessage(
                session_id=session_id,
                code="SANDBOX_ERROR",
                message=f"沙箱执行出错: {e!s}",
                recoverable=False,
                details={"task_id": task_id, "command": command},
            )
            await self._send_message(session_id, error_message)

            return False

    async def _send_command_result(
        self,
        session_id: str,
        task_id: str,
        command: str,
        stdout: str,
        stderr: str,
        exit_code: int,
        execution_time: float,
        workspace_path: str,
    ):
        """发送命令结果消息到前端

        Args:
            session_id: 会话 ID
            task_id: 任务 ID
            command: 执行的命令
            stdout: 标准输出
            stderr: 标准错误
            exit_code: 退出码
            execution_time: 执行时间
            workspace_path: 工作区路径

        Raises:
            IOError: 发送消息失败

        """
        # 限制输出大小（防止过大的响应）
        stdout_limited = stdout[: self.MAX_OUTPUT_SIZE]
        if len(stdout) > self.MAX_OUTPUT_SIZE:
            stdout_limited += f"\n... (output truncated, total {len(stdout)} bytes)"

        stderr_limited = stderr[: self.MAX_OUTPUT_SIZE]
        if len(stderr) > self.MAX_OUTPUT_SIZE:
            stderr_limited += f"\n... (output truncated, total {len(stderr)} bytes)"

        # 创建包含系统命令结果的 assistant 消息
        assistant_message = AssistantWebSocketMessage(
            id=str(uuid.uuid4()),
            type=MessageType.ASSISTANT_MESSAGE,
            session_id=session_id,
            content=[
                {
                    "type": "system_command_result",
                    "command": command,
                    "stdout": stdout_limited,
                    "stderr": stderr_limited,
                    "exit_code": exit_code,
                    "execution_time": execution_time,
                    "cwd": str(workspace_path),
                },
            ],
            timestamp=time.time(),
            task_id=task_id,
        )

        await self._send_message(session_id, assistant_message)
        logger.info("[SYSTEM_COMMAND] ✅ Sent system command result message")

    def _save_command_to_history(
        self,
        user_workspace,
        user_message_content: str,
        command: str,
        stdout: str,
        stderr: str,
        exit_code: int,
    ):
        """保存命令结果到对话历史

        Args:
            user_workspace: 用户工作区
            user_message_content: 用户消息内容
            command: 执行的命令
            stdout: 标准输出
            stderr: 标准错误
            exit_code: 退出码

        Raises:
            IOError: 保存对话失败

        """
        if not user_workspace.current_conversation:
            return

        try:
            # 保存用户消息（系统命令）
            user_workspace.current_conversation.say(UserMessage(content=user_message_content))

            # 保存助手消息（命令结果）
            assistant_content = json.dumps(
                {
                    "type": "system_command_result",
                    "command": command,
                    "stdout": stdout[: self.MAX_OUTPUT_SIZE],
                    "stderr": stderr[: self.MAX_OUTPUT_SIZE],
                    "exit_code": exit_code,
                },
            )

            user_workspace.current_conversation.say(AssistantMessage(content=assistant_content))

            # 保存对话
            import asyncio

            # 使用同步的方式保存（避免异步问题）
            loop = asyncio.get_event_loop()
            save_success = loop.run_until_complete(
                user_workspace.save_current_conversation()
            )

            if save_success:
                logger.info(
                    "[SYSTEM_COMMAND] ✅ Saved system command to conversation history",
                )
            else:
                logger.warning(
                    "[SYSTEM_COMMAND] Failed to save system command to conversation",
                )

        except Exception as save_error:
            logger.error(
                f"[SYSTEM_COMMAND] Error saving conversation: {save_error}",
                exc_info=True,
            )

    async def _send_task_complete(
        self,
        session_id: str,
        task_id: str,
        command: str,
        exit_code: int,
        execution_time: float,
    ):
        """发送任务完成消息

        Args:
            session_id: 会话 ID
            task_id: 任务 ID
            command: 执行的命令
            exit_code: 退出码
            execution_time: 执行时间

        Raises:
            IOError: 发送消息失败

        """
        complete_message = TaskNodeCompleteMessage(
            session_id=session_id,
            task_id=task_id,
            task_node_id=task_id,
            result={"command": command, "exit_code": exit_code},
            duration_ms=execution_time,
        )
        await self._send_message(session_id, complete_message)
