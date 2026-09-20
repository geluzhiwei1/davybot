# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Tool Discovery — Progressive Tool Disclosure 系统。

提供会话级工具池管理、工具索引、Schema 压缩，实现渐进式工具披露。

核心组件：
    - SessionToolPool:  会话级工具激活管理（Tier-0 常驻 + Tier-1 按需激活）
    - ToolIndex:        工具语义索引（关键词检索，无需 embedding）
    - SchemaCompressor: OpenAI function schema 压缩器
    - CORE_TOOLS:       Tier-0 基线工具集常量
"""

from .core_tools import CORE_TOOLS, MODE_CORE_OVERRIDES, get_core_tools_for_mode
from .schema_compressor import SchemaCompressor
from .session_pool import SessionToolPool
from .tool_index import ToolDoc, ToolIndex

__all__ = [
    "CORE_TOOLS",
    "MODE_CORE_OVERRIDES",
    "get_core_tools_for_mode",
    "SessionToolPool",
    "ToolIndex",
    "ToolDoc",
    "SchemaCompressor",
]
