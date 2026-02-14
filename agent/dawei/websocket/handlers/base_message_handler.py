# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""
基础消息处理器

提供所有消息处理的通用逻辑，遵循 KISS 原则：
- 提取公共逻辑到基类
- 避免代码重复
- 简化子类的实现

遵循 Fast Fail 原则：
- 验证所有输入参数
- 错误时快速失败
- 提供清晰的错误信息
"""

import logging
from pathlib import Path
from typing import Any

from dawi.websocket.protocol import MessageType

from dawei.core.validators import validate_dict_key, validate_not_none, validate_string_not_empty
from dawei.workspace.user_workspace import UserWorkspace

logger = logging.getLogger(__name__)


class BaseMessageHandler:
    """基础消息处理器

    提供所有消息处理的通用功能：
    - 会话管理
    - 任务管理接口
    - 错误处理
    - 日志记录
    """

    def __init__(self, user_workspace: UserWorkspace, task_manager: Any = None, agent_lifecycle_manager: Any = None):
        """
        初始化基础消息处理器

        Args:
            user_workspace: 用户工作区实例
            task_manager: 任务管理器（可选）
            agent_lifecycle_manager: Agent生命周期管理器（可选）
        """
        self.user_workspace = user_workspace
        self.task_manager = task_manager
        self.agent_lifecycle_manager = agent_lifecycle_manager

    async def get_session(self, session_id: str) -> Any:
        """获取会话信息

        Args:
            session_id: 会话ID

        Returns:
            会话对象或None

        Raises:
            ValueError: 如果会话ID无效
        """
        validate_not_none(session_id, "session_id")
        validate_string_not_empty(session_id, "session_id")

        try:
            return await self.user_workspace.get_session(session_id)
        except Exception as e:
            logger.exception(f"Failed to get session {session_id}: {e}")
            raise

    async def get_workspace(self, session_id: str) -> UserWorkspace:
        """获取用户工作区

        Args:
            session_id: 会话ID

        Returns:
            用户工作区实例

        Raises:
            ValueError: 如果工作区无效或不存在
        """
        validate_not_none(session_id, "session_id")

        try:
            return await self.user_workspace.get_workspace(session_id)
        except Exception as e:
            logger.exception(f"Failed to get workspace {session_id}: {e}")
            raise

    async def send_message(self, session_id: str, message_type: str, **kwargs) -> dict[str, Any]:
        """发送消息到客户端

        Args:
            session_id: 会话ID
            message_type: 消息类型
            **kwargs: 消息内容

        Returns:
            发送的消息字典

        Raises:
            ValueError: 如果参数无效
        """
        validate_not_none(session_id, "session_id")
        validate_string_not_empty(message_type, "message_type")

        try:
            # 具体实现由子类提供
            raise NotImplementedError(f"send_message not implemented for {message_type}")
        except Exception as e:
            logger.exception(f"Failed to send {message_type} message: {e}")
            raise

    async def send_error(self, session_id: str, error_code: str, error_message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
        """发送错误消息

        Args:
            session_id: 会话ID
            error_code: 错误代码
            error_message: 错误消息
            details: 错误详情（可选）

        Returns:
            错误消息字典

        Raises:
            ValueError: 如果参数无效
        """
        validate_not_none(session_id, "session_id")
        validate_string_not_empty(error_code, "error_code")

        error_response = {
            "code": error_code,
            "message": error_message,
        }

        if details:
            error_response["details"] = details

        try:
            # 具体实现由子类提供
            return await self.send_message(session_id, "error", error_response)
        except Exception as e:
            logger.exception(f"Failed to send error message: {e}")
            raise

    async def get_task_manager(self) -> Any:
        """获取任务管理器"""
        return self.task_manager

    async def get_agent_lifecycle_manager(self) -> Any:
        """获取Agent生命周期管理器"""
        return self.agent_lifecycle_manager
