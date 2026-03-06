# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""工具调用服务接口定义

定义了工具调用相关的抽象接口，包括工具执行、管理等功能。
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any


class IToolCallService(ABC):
    """工具调用服务接口"""

    @abstractmethod
    async def execute_tool(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        context: Any,
    ) -> Dict[str, Any]:
        """执行工具

        Args:
            tool_name: 工具名称
            parameters: 工具参数
            context: 执行上下文

        Returns:
            工具执行结果

        """

    @abstractmethod
    def list_available_tools(self) -> List[str]:
        """列出所有可用工具

        Returns:
            工具名称列表

        """

    @abstractmethod
    def get_tool_schema(self, tool_name: str) -> Dict[str, Any] | None:
        """获取工具模式

        Args:
            tool_name: 工具名称

        Returns:
            工具模式字典

        """

    @abstractmethod
    def register_tool(self, tool_name: str, tool_impl: Any) -> bool:
        """注册新工具

        Args:
            tool_name: 工具名称
            tool_impl: 工具实现

        Returns:
            是否注册成功

        """

    @abstractmethod
    def unregister_tool(self, tool_name: str) -> bool:
        """注销工具

        Args:
            tool_name: 工具名称

        Returns:
            是否注销成功

        """

    @abstractmethod
    def validate_tool_parameters(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
    ) -> Dict[str, Any]:
        """验证工具参数

        Args:
            tool_name: 工具名称
            parameters: 参数字典

        Returns:
            验证结果

        """

    @abstractmethod
    def get_tool_execution_history(self, tool_name: str | None = None) -> List[Dict[str, Any]]:
        """获取工具执行历史

        Args:
            tool_name: 工具名称，为 None 时获取所有工具的历史

        Returns:
            执行历史列表

        """

    @abstractmethod
    def set_tool_timeout(self, tool_name: str, timeout: int) -> bool:
        """设置工具超时时间

        Args:
            tool_name: 工具名称
            timeout: 超时时间（秒）

        Returns:
            是否设置成功

        """
