# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Tool Catalog — Progressive Tool Discovery 元数据

为 search_tools 工具提供工具目录搜索能力。
每个工具条目包含：名称、简短描述、关键字、所属分组、详细使用说明。

使用场景：
- Orchestrator 模式下，LLM 可调 search_tools 查找合适工具
- 前端工具浏览器可展示工具分类
"""

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ToolCatalogEntry:
    """工具目录条目"""

    name: str
    group: str
    short_desc: str  # 一行简述（≤60字）
    keywords: list[str] = field(default_factory=list)
    when_to_use: str = ""  # 何时使用此工具
    examples: list[str] = field(default_factory=list)  # 使用示例

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "group": self.group,
            "short_desc": self.short_desc,
            "keywords": self.keywords,
            "when_to_use": self.when_to_use,
            "examples": self.examples,
        }


# ============================================================================
# 工具目录注册表
# ============================================================================

_CATALOG: list[ToolCatalogEntry] = [
    # --- read ---
    ToolCatalogEntry(
        name="read_file",
        group="read",
        short_desc="读取文本文件或 PDF 内容（支持行号、行范围）",
        keywords=["文件", "读取", "pdf", "txt", "代码", "read", "file"],
        when_to_use="需要查看文件内容时使用。支持指定行范围。PDF 会自动提取文本。",
    ),
    ToolCatalogEntry(
        name="list_files",
        group="read",
        short_desc="列出目录内容（支持递归）",
        keywords=["目录", "文件列表", "ls", "dir", "list"],
        when_to_use="需要浏览工作区文件结构时使用。",
    ),
    # --- edit ---
    ToolCatalogEntry(
        name="write_text_file",
        group="edit",
        short_desc="写入或创建文本文件",
        keywords=["写入", "创建", "文件", "write", "create"],
        when_to_use="需要创建新文件或完全覆盖文件内容时使用。",
    ),
    ToolCatalogEntry(
        name="smart_text_edit",
        group="edit",
        short_desc="智能文本编辑（精确匹配替换）",
        keywords=["编辑", "替换", "修改", "edit", "replace", "smart"],
        when_to_use="需要修改文件中的特定内容时使用。基于精确字符串匹配。",
    ),
    ToolCatalogEntry(
        name="insert_text_content",
        group="edit",
        short_desc="在文件指定行插入内容",
        keywords=["插入", "添加", "insert", "append"],
        when_to_use="需要在文件特定位置插入新内容时使用。",
    ),
    # --- docx ---
    ToolCatalogEntry(
        name="docx_read_structured",
        group="docx",
        short_desc="结构化读取 DOCX 文档（保留段落、表格、样式）",
        keywords=["word", "docx", "文档", "段落", "表格", "document"],
        when_to_use="需要读取 .docx/.doc 文件且保留格式结构时使用。",
    ),
    ToolCatalogEntry(
        name="docx_edit",
        group="docx",
        short_desc="编辑 DOCX 文档（保持格式不变）",
        keywords=["word", "docx", "编辑", "修改", "edit"],
        when_to_use="需要修改 Word 文档内容且不破坏格式时使用。",
    ),
    ToolCatalogEntry(
        name="docx_diff",
        group="docx",
        short_desc="比较两个 DOCX 文档的差异",
        keywords=["word", "docx", "比较", "差异", "diff", "compare"],
        when_to_use="需要对比两个 Word 文档版本差异时使用。",
    ),
    # --- workflow ---
    ToolCatalogEntry(
        name="new_task",
        group="workflow",
        short_desc="创建新的子任务（派发即返回）",
        keywords=["任务", "创建", "子任务", "并行", "派发", "task", "new", "subtask"],
        when_to_use="需要将复杂工作拆分为子任务时使用：同一轮可并行派发多个无依赖子任务；必须给出可判定的验收标准（acceptance），执行报告会回注供逐条判定。",
    ),
    ToolCatalogEntry(
        name="update_todo_list",
        group="workflow",
        short_desc="更新待办事项列表",
        keywords=["待办", "todo", "清单", "计划", "task list"],
        when_to_use="需要跟踪任务进度或管理工作计划时使用。",
    ),
    ToolCatalogEntry(
        name="switch_mode",
        group="workflow",
        short_desc="切换 Agent 工作模式",
        keywords=["模式", "切换", "mode", "orchestrator", "pdca"],
        when_to_use="需要切换到不同的工作模式时使用。",
    ),
    ToolCatalogEntry(
        name="expand_tool_result",
        group="workflow",
        short_desc="展开被截断的工具结果（使用 snapshot_id）",
        keywords=["展开", "截断", "快照", "expand", "snapshot", "truncated"],
        when_to_use="工具结果被截断且包含 snapshot_id 时，用本工具获取完整数据。",
    ),
    ToolCatalogEntry(
        name="search_tools",
        group="workflow",
        short_desc="搜索可用工具目录（渐进式披露）",
        keywords=["搜索", "工具", "发现", "search", "tools", "discover"],
        when_to_use="不确定应该使用哪个工具时，搜索工具目录并自动激活。",
    ),
    ToolCatalogEntry(
        name="attempt_completion",
        group="workflow",
        short_desc="完成任务并提交结果",
        keywords=["完成", "提交", "结束", "completion", "finish"],
        when_to_use="任务全部完成后，用本工具提交最终结果。",
    ),
    ToolCatalogEntry(
        name="ask_followup_question",
        group="workflow",
        short_desc="向用户提问以澄清需求",
        keywords=["提问", "澄清", "追问", "followup", "question", "ask"],
        when_to_use="需要向用户确认需求或获取更多信息时使用。",
    ),
    ToolCatalogEntry(
        name="execute_command",
        group="command",
        short_desc="执行 Shell 命令",
        keywords=["命令", "执行", "shell", "command", "execute", "终端"],
        when_to_use="需要执行系统命令或脚本时使用。",
    ),
    # --- knowledge ---
    ToolCatalogEntry(
        name="search_user_knowledge_base",
        group="knowledge",
        short_desc="搜索用户知识库（向量+全文混合检索）",
        keywords=["知识库", "搜索", "rag", "向量", "kb", "knowledge"],
        when_to_use="需要在用户上传的知识库中查找信息时使用。",
    ),
    ToolCatalogEntry(
        name="query_user_knowledge_base",
        group="knowledge",
        short_desc="RAG 问答（知识库增强回答）",
        keywords=["知识库", "问答", "rag", "query", "ask"],
        when_to_use="需要基于知识库内容回答问题时使用。",
    ),
]


# ---------------------------------------------------------------------------
# S2 目录注册缝（拆库方案 §18.3）：核心静态目录 + 扩展动态注册，单向 biz→core。
#
# biz（dawei_biz/tools/_catalog.py）在包 import 时调用 register_catalog_entries()
# 注入 legal/sanctions/normflow/market/research 条目 —— biz 缺席 = 目录仅含核心
# 工具（search_tools 渐进式披露与系统提示目录摘要同步收敛）。
# ---------------------------------------------------------------------------
_EXTRA_CATALOG: list[ToolCatalogEntry] = []


def register_catalog_entries(entries: list[ToolCatalogEntry]) -> None:
    """注册扩展目录条目（biz 包 import 时调用；按名去重，幂等）。

    重名条目跳过并告警（FAST FAIL 语义 softened 为告警：目录是描述性元数据，
    悬空/重复条目由 tool_system_health 注册表一致性检查兜底上报）。
    """
    existing = {e.name for e in _CATALOG} | {e.name for e in _EXTRA_CATALOG}
    for e in entries:
        if e.name in existing:
            logger.warning("duplicate catalog entry skipped: %s", e.name)
            continue
        _EXTRA_CATALOG.append(e)
        existing.add(e.name)


def get_catalog() -> list[ToolCatalogEntry]:
    """返回完整工具目录（核心 + 注册的扩展条目）"""
    return _CATALOG + _EXTRA_CATALOG


def search_catalog(query: str, limit: int = 10) -> list[ToolCatalogEntry]:
    """搜索工具目录

    Args:
        query: 搜索关键词
        limit: 最大返回条目数

    Returns:
        匹配的工具列表（按相关度排序）
    """
    query_lower = query.lower().strip()
    if not query_lower:
        return get_catalog()[:limit]

    scored: list[tuple[int, ToolCatalogEntry]] = []

    for entry in get_catalog():
        score = 0
        # 名称匹配（最高权重）
        if query_lower in entry.name.lower():
            score += 10
        # 简述匹配
        if query_lower in entry.short_desc.lower():
            score += 5
        # 关键词匹配（双向：query 包含 keyword 或 keyword 包含 query）
        for kw in entry.keywords:
            kw_lower = kw.lower()
            if query_lower in kw_lower or kw_lower in query_lower:
                score += 3
        # 使用场景匹配
        if query_lower in entry.when_to_use.lower():
            score += 2

        if score > 0:
            scored.append((score, entry))

    # 按分数降序
    scored.sort(key=lambda x: x[0], reverse=True)
    return [entry for _, entry in scored[:limit]]


def get_catalog_summary(groups: list[str] | None = None) -> str:
    """生成工具目录摘要文本（用于系统提示）

    Args:
        groups: 可选的分组过滤。None = 所有分组

    Returns:
        格式化的工具目录摘要
    """
    entries = get_catalog()
    if groups:
        entries = [e for e in entries if e.group in groups]

    if not entries:
        return "（无可用工具）"

    lines = ["可用工具目录："]
    current_group = ""
    for entry in entries:
        if entry.group != current_group:
            current_group = entry.group
            lines.append(f"\n[{current_group}]")
        lines.append(f"  - {entry.name}: {entry.short_desc}")

    return "\n".join(lines)
