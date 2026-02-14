# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""LLM 服务接口定义

定义了 LLM 服务相关的抽象接口，包括消息创建、提供者管理等功能。
"""

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dawei.entity.lm_messages import LLMMessage
    from dawei.entity.stream_message import StreamMessages
else:
    # 运行时使用字符串类型注解
    LLMMessage = Any
    StreamMessages = Any


class ILLMService(ABC):
    """LLM 服务接口"""

    @abstractmethod
    def get_available_providers(self) -> list[str]:
        """获取可用的 LLM 提供者列表

        Returns:
            提供者名称列表

        """

    @abstractmethod
    def get_current_provider(self) -> str | None:
        """获取当前 LLM 提供者

        Returns:
            当前提供者名称

        """

    @abstractmethod
    def set_provider(self, provider_name: str) -> bool:
        """设置 LLM 提供者

        Args:
            provider_name: 提供者名称

        Returns:
            是否设置成功

        """

    @abstractmethod
    def get_provider_config(self, provider_name: str) -> dict[str, Any] | None:
        """获取提供者配置

        Args:
            provider_name: 提供者名称

        Returns:
            提供者配置字典

        """

    @abstractmethod
    def update_provider_config(self, provider_name: str, config: dict[str, Any]) -> bool:
        """更新提供者配置

        Args:
            provider_name: 提供者名称
            config: 新配置

        Returns:
            是否更新成功

        """

    @abstractmethod
    def get_model_info(self, provider_name: str | None = None) -> dict[str, Any]:
        """获取模型信息

        Args:
            provider_name: 提供者名称，为 None 时使用当前提供者

        Returns:
            模型信息字典

        """

    @abstractmethod
    async def test_connection(self, provider_name: str | None = None) -> bool:
        """测试提供者连接

        Args:
            provider_name: 提供者名称，为 None 时使用当前提供者

        Returns:
            是否连接成功

        """

    @abstractmethod
    async def process_message(self, messages: list[LLMMessage], **kwargs) -> dict[str, Any]:
        """处理消息并返回完整结果

        Args:
            messages: 消息列表
            **kwargs: 其他参数（如 tools、temperature 等）

        Returns:
            包含完整内容和工具调用的字典

        """

    @abstractmethod
    async def create_message_with_callback(
        self,
        messages: list[LLMMessage],
        callback: Callable[[StreamMessages], Awaitable[None]],
        **kwargs,
    ) -> dict[str, Any]:
        """创建消息并通过回调函数处理流式响应

        Args:
            messages: 消息列表
            callback: 流式消息回调函数
            **kwargs: 其他参数（如 tools、temperature 等）

        Returns:
            包含完整内容和工具调用的字典

        """
