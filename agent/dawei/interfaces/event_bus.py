# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""事件总线接口定义

定义了事件发布订阅相关的抽象接口，包括事件管理、处理等功能。
只支持强类型事件消息系统。
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any


class IEventBus(ABC):
    """事件总线接口 - 纯强类型系统"""

    @abstractmethod
    async def emit_event(self, event_message) -> None:
        """发布强类型事件消息

        Args:
            event_message: 强类型事件消息对象

        """

    @abstractmethod
    def on(self, event_type: str, handler: Callable) -> str:
        """订阅事件

        Args:
            event_type: 事件类型
            handler: 事件处理器

        Returns:
            处理器ID

        """

    @abstractmethod
    def off(self, event_type: str, handler_id: str) -> bool:
        """取消订阅事件

        Args:
            event_type: 事件类型
            handler_id: 处理器ID

        Returns:
            是否取消成功

        """

    @abstractmethod
    def once(self, event_type: str, handler: Callable) -> str:
        """订阅一次性事件

        Args:
            event_type: 事件类型
            handler: 事件处理器

        Returns:
            处理器ID

        """

    @abstractmethod
    def get_event_history(self, event_type: str | None = None) -> list[dict[str, Any]]:
        """获取事件历史

        Args:
            event_type: 事件类型，为 None 时获取所有事件

        Returns:
            事件历史列表

        """

    @abstractmethod
    def clear_history(self, event_type: str | None = None) -> None:
        """清除事件历史

        Args:
            event_type: 事件类型，为 None 时清除所有事件历史

        """

    @abstractmethod
    def get_handler_count(self, event_type: str) -> int:
        """获取事件处理器数量

        Args:
            event_type: 事件类型

        Returns:
            处理器数量

        """

    @abstractmethod
    def set_max_history_size(self, size: int) -> None:
        """设置最大历史记录大小

        Args:
            size: 最大历史记录数量

        """

    @abstractmethod
    async def wait_for_event(
        self,
        event_type: str,
        timeout: float | None = None,
    ) -> dict[str, Any] | None:
        """等待特定事件

        Args:
            event_type: 事件类型
            timeout: 超时时间（秒）

        Returns:
            事件数据或 None（超时）

        """
