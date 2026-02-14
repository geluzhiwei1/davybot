# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""工具执行器接口定义

定义了工具执行相关的抽象接口，包括参数验证、执行和结果处理等功能。
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any


class IToolExecutor(ABC):
    """工具执行器接口

    负责执行各种工具调用，包括参数验证、执行和结果处理。
    """

    @abstractmethod
    async def execute_tool(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """执行工具

        Args:
            tool_name: 工具名称
            tool_args: 工具参数
            timeout: 超时时间（秒）

        Returns:
            工具执行结果

        """

    @abstractmethod
    def list_available_tools(self) -> list[str]:
        """列出所有可用工具

        Returns:
            可用工具名称列表

        """

    @abstractmethod
    def get_tool_schema(self, tool_name: str) -> dict[str, Any] | None:
        """获取工具模式

        Args:
            tool_name: 工具名称

        Returns:
            工具模式定义，如果工具不存在则返回None

        """

    @abstractmethod
    def register_tool(self, tool_name: str, tool_impl: Callable) -> bool:
        """注册新工具

        Args:
            tool_name: 工具名称
            tool_impl: 工具实现

        Returns:
            是否成功注册

        """
