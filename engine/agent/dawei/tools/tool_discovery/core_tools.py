# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""CORE_TOOLS — Tier-0 常驻工具集定义。

原则：覆盖 agent 自主运转的最低能力——读写执行 + 元操作。
非常驻工具（Tier-1）通过 search_tools 按需激活到 SessionToolPool。
"""

# Tier-0：每个会话的基线工具集
CORE_TOOLS: set[str] = {
    # 文件操作（agent 的"手脚"）
    "read_file",
    "list_files",
    "write_text_file",
    "insert_text_content",
    "smart_text_edit",
    # 命令执行
    "execute_command",
    # 工作流元操作（agent 的"大脑"）
    "update_todo_list",
    "attempt_completion",
    # 工具发现 + 结果展开（本方案新增的元工具）
    "search_tools",
    "expand_tool_result",
    # MCP 元操作：Tier-0 常驻（连接管理/资源访问是跨业务基础能力，且激活入口
    # search_tools 本身依赖工具可用——历史背景：mode groups 准入时期曾因 MCP 工具
    # 被降级形成"永远无法激活"的死锁，E2E 2026-09-03 实锤；mode-工具解耦后
    # 已无组准入，此处保留常驻兜底）。
    "use_mcp_tool",
    "access_mcp_resource",
    "list_mcp_servers",
    "connect_mcp_server",
    "disconnect_mcp_server",
    "call_acp_agent",
    # 工作流辅助
    "new_task",
    "ask_followup_question",
}

# Mode 级额外常驻：某些 mode 有强关联工具，应直接进 Tier-0
MODE_CORE_OVERRIDES: dict[str, set[str]] = {
    # orchestrator 无额外常驻
    "orchestrator": set(),
    # pdca 无额外常驻需求（mode-工具解耦后各模式工具可见性一致）
    "pdca": set(),
    # plan mode 需要看任务结构
    "plan": {"get_task_status"},
    # sanctions mode：制裁工具全部常驻
    "sanctions": {
        "sanctions_search_entities",
        "sanctions_get_entity",
        "sanctions_graph_search",
        "sanctions_screen_entity",
        "sanctions_create_watchlist",
        "sanctions_run_monitoring_check",
        "sanctions_dashboard",
        "sanctions_filters",
    },
    # 社媒编辑器专家(A-M1,设计 A.5):5 工具即核心能力面,全部 Tier-0 常驻
    # —— 否则被渐进式披露(SessionToolPool Tier-0/1 过滤)挡在 LLM 工具面之外
    # (2026-09-16 Phase 3: key 随 slug 重命名加 soc- 前缀)
    "soc-content-drafter": {
        "social_read_draft",
        "social_rule_check",
        "social_lookup_trending",
        "social_propose_edit",
        "social_validate_artifact",
        "social_generate_images",  # A-M2:配图候选(人选插入)
    },
    "soc-content-guardian": {
        "social_read_draft",
        "social_rule_check",
        "social_propose_edit",
    },
    "soc-trend-spotter": {
        "social_read_draft",
        "social_lookup_trending",
        "social_propose_edit",
    },
}


def get_core_tools_for_mode(mode: str | None = None) -> set[str]:
    """返回指定 mode 的完整 Tier-0 工具集。

    Args:
        mode: 当前 agent 模式（orchestrator/pdca/plan/sanctions 等）

    Returns:
        CORE_TOOLS ∪ MODE_CORE_OVERRIDES[mode]
    """
    base = set(CORE_TOOLS)
    if mode and mode in MODE_CORE_OVERRIDES:
        base |= MODE_CORE_OVERRIDES[mode]
    return base
