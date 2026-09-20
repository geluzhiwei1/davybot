# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""SessionToolPool — 会话级工具池管理。

管理单个会话的 Tier-0/Tier-1 工具集。
生命周期：一个对话会话一个实例。
存储：内存（随会话销毁）。
"""

import logging

logger = logging.getLogger(__name__)


class SessionToolPool:
    """管理单个会话的 Tier-0/Tier-1 工具集。

    Tier-0（core）：常驻工具，每次 LLM 请求都会注入。
    Tier-1（activated）：按需激活，通过 search_tools 触发。
    Tier-2（deferred）：未激活的工具，不注入 LLM 请求。

    激活的工具在**下一次** LLM 请求时才出现在 tools= 中。
    """

    def __init__(self, core_tools: set[str]):
        """
        Args:
            core_tools: Tier-0 常驻工具名集合
        """
        self._core: set[str] = set(core_tools)
        self._activated: set[str] = set()

    def activate(self, tool_name: str) -> bool:
        """将工具从 Tier-2 提升到 Tier-1。

        Args:
            tool_name: 工具名称

        Returns:
            True 表示新激活，False 表示已在核心池或已激活
        """
        if tool_name in self._core:
            return False  # 已在核心池
        if tool_name in self._activated:
            return False  # 已激活
        self._activated.add(tool_name)
        logger.debug(f"Tool activated: {tool_name} (active: {len(self._activated)})")
        return True

    def activate_many(self, tool_names: list[str]) -> list[str]:
        """批量激活工具。

        Returns:
            实际新激活的工具名列表
        """
        newly = []
        for name in tool_names:
            if self.activate(name):
                newly.append(name)
        return newly

    def get_active_tools(self) -> set[str]:
        """返回当前应注入 LLM 的工具名集合（Tier-0 + Tier-1）。"""
        return self._core | self._activated

    def is_active(self, tool_name: str) -> bool:
        """检查工具是否在当前活跃集合中。"""
        return tool_name in self._core or tool_name in self._activated

    def deactivate(self, tool_name: str) -> None:
        """手动踢出 Tier-1（如工具出错）。不会移除 Tier-0 工具。"""
        if tool_name in self._core:
            logger.warning(f"Cannot deactivate core tool: {tool_name}")
            return
        self._activated.discard(tool_name)
        logger.debug(f"Tool deactivated: {tool_name}")

    def get_stats(self) -> dict:
        """返回工具池统计信息。"""
        return {
            "core_count": len(self._core),
            "activated_count": len(self._activated),
            "total_active": len(self._core) + len(self._activated),
            "activated_tools": sorted(self._activated),
        }
