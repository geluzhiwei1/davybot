# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""消息处理器接口定义

定义了消息处理相关的抽象接口，包括消息构建、格式化等功能。
"""

from abc import ABC, abstractmethod
from typing import Any


class IMessageProcessor(ABC):
    """消息处理器接口"""

    def __init__(self, user_workspace: Any):
        self.user_workspace = user_workspace

    @abstractmethod
    async def build_messages(self, capabilities: list[str]) -> dict[str, Any]:
        """构建消息列表

        Args:
            user_workspace: 用户工作区实例
            capabilities: 能力列表

        Returns:
            包含消息和工具的字典

        """

    @abstractmethod
    def build_user_message(self, task: str, images: list[str] | None = None) -> dict[str, Any]:
        """构建用户消息

        Args:
            task: 任务描述
            images: 可选的图片列表

        Returns:
            用户消息字典

        """

    @abstractmethod
    def build_assistant_message(
        self,
        content: str | list[dict[str, Any]] | None,
        tool_calls: list[dict[str, Any]] | None = None,
        **kwargs,
    ) -> Any:
        """构建助手消息

        Args:
            content: 消息内容
            tool_calls: 工具调用列表
            **kwargs: 其他参数

        Returns:
            助手消息对象

        """

    @abstractmethod
    async def add_message_to_conversation(self, task_id: str, message: Any) -> None:
        """将消息添加到对话中

        Args:
            task_id: 任务ID
            message: 消息对象

        """

    @abstractmethod
    def _convert_tools_to_openai_format(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """转换工具为 OpenAI 格式

        Args:
            tools: 工具列表

        Returns:
            OpenAI 格式的工具列表

        """

    @abstractmethod
    def validate_message(self, message: dict[str, Any]) -> bool:
        """验证消息格式

        Args:
            message: 消息字典

        Returns:
            是否有效

        """

    @abstractmethod
    def format_system_prompt(self, base_prompt: str, context: dict[str, Any]) -> str:
        """格式化系统提示

        Args:
            base_prompt: 基础提示
            context: 上下文信息

        Returns:
            格式化后的系统提示

        """
