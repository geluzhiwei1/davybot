# Copyright (c) 5 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""L4 — 输出策略（配置驱动，按工具覆盖）

每个工具有一个 OutputPolicy，定义其输出类型、token 预算、截断参数等。
"""

from enum import Enum

from pydantic import BaseModel


class ToolOutputType(str, Enum):
    """工具输出形态分类。"""

    BLOB = "blob"  # 大块文本（file/command）
    LIST = "list"  # 同构项列表（search/graph）
    STRUCTURED = "structured"  # 嵌套对象（detail/document）
    ECHO = "echo"  # 写操作确认
    COMPACT = "compact"  # 有界 JSON（免治）


class OutputPolicy(BaseModel):
    """单个工具的输出治理策略。"""

    output_type: ToolOutputType = ToolOutputType.COMPACT

    # ── 通用 ──
    max_output_tokens: int = 2000  # 硬上限（外层兜底用）
    truncation_notice: str = "...(已截断，显示部分内容)"

    # ── A 类 Blob 专用 ──
    blob_max_lines: int = 200  # 最多渲染行数
    blob_head_ratio: float = 0.7  # head 占比（剩余给 tail）
    blob_window_hint: str = "用 start_line={next} 继续读"

    # ── B 类 List 专用 ──
    list_max_items: int = 20  # 最多渲染项数
    list_item_max_chars: int = 500  # 单项最大字符
    list_summary_threshold: int = 50  # 超过则降级为概要
    list_page_hint: str = "用 offset={next} 看下一页"

    # ── C 类 Structured 专用 ──
    # ⚠️ S2 修复：每工具单独定义字段比例，sum = 1.0
    structured_field_budget: dict[str, float] = {}
    structured_array_max: int = 15  # 嵌套数组最大项数

    # ── D 类 Echo 专用 ──
    echo_max_input_chars: int = 20000  # content 参数上限（0 = 不检查）

    # ── 分页 ──
    pagination_enabled: bool = True

    class Config:
        use_enum_values = True


# ── 策略注册表 ──
POLICIES: dict[str, OutputPolicy] = {
    "default": OutputPolicy(output_type=ToolOutputType.COMPACT),

    # A 类 Blob
    "read_file": OutputPolicy(
        output_type=ToolOutputType.BLOB,
        max_output_tokens=3000,
        blob_max_lines=200,
    ),
    "execute_command": OutputPolicy(
        output_type=ToolOutputType.BLOB,
        max_output_tokens=2000,
        blob_max_lines=150,
        blob_head_ratio=0.6,
        blob_window_hint="如需完整输出，调 expand_tool_result(call_id=...)",
    ),
    "shell_command": OutputPolicy(
        output_type=ToolOutputType.BLOB,
        max_output_tokens=2000,
        blob_max_lines=150,
        blob_window_hint="如需完整输出，调 expand_tool_result(call_id=...)",
    ),
    "list_files": OutputPolicy(
        output_type=ToolOutputType.LIST,
        list_max_items=100,  # 目录列表放宽
        list_summary_threshold=200,
        list_item_max_chars=200,
    ),

    # B 类 List
    "search_legal_knowledge": OutputPolicy(
        output_type=ToolOutputType.LIST,
        max_output_tokens=2500,
        list_max_items=15,
        list_summary_threshold=30,
    ),
    "search_user_knowledge_base": OutputPolicy(
        output_type=ToolOutputType.LIST,
        max_output_tokens=2500,
        list_max_items=15,
        list_summary_threshold=30,
    ),
    "sanctions_search_entities": OutputPolicy(
        output_type=ToolOutputType.LIST,
        list_max_items=20,
    ),
    "sanctions_screen_entity": OutputPolicy(
        output_type=ToolOutputType.LIST,
        list_max_items=10,  # 筛查高风险，详情优先
        list_summary_threshold=20,
    ),
    "legal_graph_search": OutputPolicy(
        output_type=ToolOutputType.LIST,
        list_max_items=20,
    ),
    "sanctions_graph_search": OutputPolicy(
        output_type=ToolOutputType.LIST,
        list_max_items=20,
    ),

    # C 类 Structured — S2 修复：每工具单独定义字段比例，sum=1.0
    "get_legal_document": OutputPolicy(
        output_type=ToolOutputType.STRUCTURED,
        max_output_tokens=3000,
        structured_field_budget={
            "main": 0.4,
            "chunks": 0.3,
            "similar": 0.3,  # sum=1.0
        },
    ),
    "sanctions_get_entity": OutputPolicy(
        output_type=ToolOutputType.STRUCTURED,
        max_output_tokens=2500,
        structured_field_budget={
            "main": 0.3,
            "identifiers": 0.25,
            "sanctions": 0.25,
            "statements": 0.2,  # sum=1.0
        },
    ),
    "docx_read_structured": OutputPolicy(
        output_type=ToolOutputType.STRUCTURED,
        max_output_tokens=3000,
        structured_field_budget={
            "main": 0.3,
            "paragraphs": 0.5,
            "tables": 0.2,
        },
    ),
    "legal_document_timeline": OutputPolicy(
        output_type=ToolOutputType.LIST,
        max_output_tokens=2000,
        list_max_items=15,
    ),

    # D 类 Echo
    "write_text_file": OutputPolicy(
        output_type=ToolOutputType.ECHO,
        echo_max_input_chars=20000,
    ),
    "insert_text_content": OutputPolicy(
        output_type=ToolOutputType.ECHO,
        echo_max_input_chars=20000,
    ),

    # E 类 Compact（免治白名单）
    "update_todo_list": OutputPolicy(output_type=ToolOutputType.COMPACT),
    "show_cost": OutputPolicy(output_type=ToolOutputType.COMPACT),
    "switch_mode": OutputPolicy(output_type=ToolOutputType.COMPACT),
    "ask_followup_question": OutputPolicy(output_type=ToolOutputType.COMPACT),
    "attempt_completion": OutputPolicy(output_type=ToolOutputType.COMPACT),
    "timer": OutputPolicy(output_type=ToolOutputType.COMPACT),
    "new_task": OutputPolicy(output_type=ToolOutputType.COMPACT),
    "get_task_status": OutputPolicy(output_type=ToolOutputType.COMPACT),
    "ask_legal_question": OutputPolicy(output_type=ToolOutputType.COMPACT),
    "list_legal_knowledge_bases": OutputPolicy(output_type=ToolOutputType.COMPACT),
    "legal_search_facets": OutputPolicy(output_type=ToolOutputType.COMPACT),
    "legal_analytics": OutputPolicy(output_type=ToolOutputType.COMPACT),
    "sanctions_create_watchlist": OutputPolicy(output_type=ToolOutputType.COMPACT),
    "sanctions_run_monitoring_check": OutputPolicy(output_type=ToolOutputType.COMPACT),
    "sanctions_dashboard": OutputPolicy(output_type=ToolOutputType.COMPACT),
    "sanctions_filters": OutputPolicy(output_type=ToolOutputType.COMPACT),
    "docx_diff": OutputPolicy(output_type=ToolOutputType.COMPACT),
    "docx_edit": OutputPolicy(output_type=ToolOutputType.COMPACT),
    "smart_text_edit": OutputPolicy(output_type=ToolOutputType.ECHO, echo_max_input_chars=20000),
}


def get_policy(tool_name: str) -> OutputPolicy:
    """获取工具的输出策略。未注册的工具返回 default。"""
    return POLICIES.get(tool_name, POLICIES["default"])
