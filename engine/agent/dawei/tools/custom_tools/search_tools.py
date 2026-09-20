# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""search_tools — Progressive Tool Discovery 元工具

LLM 可调本工具查找可用工具及其使用方法。
搜索结果会自动激活到 SessionToolPool，下一次 LLM 请求时即可调用。

工作流程：
1. LLM 调用 search_tools(query="法律搜索")
2. 本工具在 ToolIndex 中检索匹配工具
3. 将匹配工具激活到 SessionToolPool（Tier-1）
4. 返回紧凑摘要（工具名 + 一句话描述 + 参数概要）
5. LLM 下一轮请求时，新激活的工具出现在 tools= 中

关键：激活不等于立即注入。当前轮次 LLM 只看到 search_tools 的返回文本，
需要下一轮才能真正调用新工具。
"""

import json
import logging

from pydantic import BaseModel, Field

from dawei.tools.custom_base_tool import CustomBaseTool
from dawei.tools.tool_catalog import get_catalog_summary, search_catalog

logger = logging.getLogger(__name__)


class SearchToolsInput(BaseModel):
    query: str = Field(
        "",
        description="搜索关键词（中文或英文）。例如：'法律搜索'、'read file'、'sanctions'",
    )
    list_all: bool = Field(
        False,
        description="若为 true，返回所有工具的摘要列表（忽略 query）",
    )


class SearchToolsTool(CustomBaseTool):
    """搜索可用工具目录，获取工具详情和使用指引。

    搜索结果自动激活到会话工具池（渐进式披露）。
    """

    name: str = "search_tools"
    description: str = (
        "搜索可用工具。当不确定应该使用哪个工具时，"
        "可用本工具查找合适工具及其使用方法。"
        "支持中英文关键词搜索。"
        "搜索到的工具将被自动激活，下一轮对话即可调用。"
    )
    args_schema = SearchToolsInput

    def __init__(self):
        super().__init__()

    def _run(self, query: str = "", list_all: bool = False, **kwargs) -> str:
        # 尝试获取 SessionToolPool 和 ToolIndex（渐进式披露模式）
        pool = self._get_session_pool()
        index = self._get_tool_index()

        if list_all:
            return self._handle_list_all(pool, index)

        return self._handle_search(query, pool, index)

    def _handle_list_all(self, pool, index) -> str:
        """处理 list_all=true 请求。"""
        # 如果有 ToolIndex，从索引获取
        if index is not None:
            all_docs = index.list_all()
            active = pool.get_active_tools() if pool else set()
            # mode-工具解耦（D6）：mode 不再拦截工具——池 active 即可调用。
            items = [
                {
                    "name": doc.name,
                    "description": doc.brief_desc,
                    "group": doc.group,
                    "params": doc.param_summary,
                    "active": doc.name in active,
                }
                for doc in all_docs
            ]
            hint = "使用具体工具名称调用对应工具。active=true 的工具已可直接调用；其余用搜索激活。"
            return json.dumps(
                {
                    "action": "list_all",
                    "total": len(items),
                    "results": items,
                    "active_tools": sorted(active) if pool else None,
                    "hint": hint,
                },
                ensure_ascii=False,
            )

        # 回退到静态目录
        summary = get_catalog_summary()
        return json.dumps(
            {
                "action": "list_all",
                "catalog": summary,
                "hint": "使用具体工具名称调用对应工具。如需详情，用关键词搜索。",
            },
            ensure_ascii=False,
        )

    def _handle_search(self, query: str, pool, index) -> str:
        """处理关键词搜索请求。"""
        # 如果有 ToolIndex，使用 BM25 检索
        if index is not None and query.strip():
            results = index.search(query, top_k=8)

            if not results:
                return json.dumps(
                    {
                        "action": "search",
                        "query": query,
                        "results": [],
                        "hint": "未找到匹配工具。使用 list_all=true 查看所有可用工具。",
                    },
                    ensure_ascii=False,
                )

            # 激活到 SessionToolPool
            newly_activated = []
            already_active = []
            if pool is not None:
                for doc in results:
                    if pool.activate(doc.name):
                        newly_activated.append(doc.name)
                    elif pool.is_active(doc.name):
                        already_active.append(doc.name)

            # mode-工具解耦（D6）：mode 不再拦截工具——激活即注入，下一轮可调用。
            items = [
                {
                    "name": doc.name,
                    "description": doc.brief_desc,
                    "group": doc.group,
                    "params": doc.param_summary,
                }
                for doc in results
            ]

            hint = "找到匹配工具，已自动激活。下一轮对话即可调用。"
            if newly_activated:
                hint += f" 新激活: {', '.join(newly_activated)}"
            if already_active:
                hint += f" 已激活: {', '.join(already_active)}"

            return json.dumps(
                {
                    "action": "search",
                    "query": query,
                    "total": len(items),
                    "results": items,
                    "newly_activated": newly_activated,
                    "already_active": already_active,
                    "hint": hint,
                },
                ensure_ascii=False,
            )

        # 回退到静态目录
        results = search_catalog(query, limit=8)

        if not results:
            return json.dumps(
                {
                    "action": "search",
                    "query": query,
                    "results": [],
                    "hint": "未找到匹配工具。使用 list_all=true 查看所有可用工具。",
                },
                ensure_ascii=False,
            )

        items = []
        for entry in results:
            item = entry.to_dict()
            items.append(item)

        # 回退模式下也尝试激活
        if pool is not None:
            newly = []
            for item in items:
                name = item.get("name", "")
                if name and pool.activate(name):
                    newly.append(name)

        return json.dumps(
            {
                "action": "search",
                "query": query,
                "total": len(items),
                "results": items,
                "hint": "找到匹配工具。请使用对应的工具名称进行调用。",
            },
            ensure_ascii=False,
        )

    def _get_session_pool(self):
        """从 user_workspace 获取 SessionToolPool（可能为 None）。"""
        if self.user_workspace is None:
            return None
        return getattr(self.user_workspace, "_session_tool_pool", None)

    def _get_tool_index(self):
        """从 user_workspace 获取 ToolIndex（可能为 None）。"""
        if self.user_workspace is None:
            return None
        return getattr(self.user_workspace, "_tool_index", None)

    # （mode-工具解耦 D6：_get_mode_allowed_tools / _suggest_modes_for 已删除——
    #   mode 不再拦截工具，搜索激活即注入，无拦截反馈链）
