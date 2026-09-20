# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Auto memory — Agent 自动从对话中提取的记忆。

双作用域:
  - 用户级: {DAWEI_HOME}/configs/{uid}/auto-memory/
  - 工作区级: {workspace}/.dawei/auto-memory/

每级目录结构:
  MEMORY.md          — 索引文件 (每条记忆一行摘要, 注入前 MAX_INDEX_LINES 行)
  facts.md           — 事实 (技术栈、架构等)
  preferences.md     — 偏好 (回复风格、语言)
  procedures.md      — 操作经验 (部署流程、步骤)
  debugging.md       — 踩坑记录

注入策略: 仅 MEMORY.md 前 MAX_INDEX_LINES 行注入系统提示词,
主题文件不注入, Agent 可用工具按需读取。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from dawei import get_dawei_home
from dawei.memory.memory_file import _safe_uid

logger = logging.getLogger(__name__)

MemoryCategory = Literal["facts", "preferences", "procedures", "debugging"]

MAX_INDEX_LINES = 100
MAX_INDEX_BYTES = 4096

_TOPIC_FILES: dict[str, str] = {
    "facts": "事实",
    "preferences": "偏好",
    "procedures": "操作经验",
    "debugging": "调试记录",
}

_INDEX_TEMPLATE = """\
# Auto Memory Index
<!-- Agent 自动维护, 请勿手动编辑. 每行一条记忆摘要. -->

"""


# ------------------------------------------------------------------
# Path resolution
# ------------------------------------------------------------------

def user_auto_memory_dir(user_id: str = "default_user") -> Path:
    """用户级 auto-memory 目录 (跨工作区共享)."""
    return get_dawei_home() / "configs" / _safe_uid(user_id) / "auto-memory"


def workspace_auto_memory_dir(workspace_root: str | Path) -> Path:
    """工作区级 auto-memory 目录."""
    return Path(workspace_root) / ".dawei" / "auto-memory"


def _index_path(base_dir: Path) -> Path:
    return base_dir / "MEMORY.md"


def _topic_path(base_dir: Path, category: MemoryCategory) -> Path:
    return base_dir / f"{category}.md"


# ------------------------------------------------------------------
# Read
# ------------------------------------------------------------------

def read_auto_memory_index(base_dir: Path) -> str:
    """读取 MEMORY.md 索引, 保留 header + 最近 MAX_INDEX_LINES 条目 / MAX_INDEX_BYTES 字节.

    新条目追加在末尾, 所以截取时保留最后的条目 (最近的记忆优先注入).
    """
    path = _index_path(base_dir)
    if not path.exists():
        return ""
    try:
        content = path.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning(f"Failed to read auto memory index {path}: {e}")
        return ""

    all_lines = content.split("\n")

    # Separate header lines (non-entry) from entry lines
    header_lines: list[str] = []
    entry_lines: list[str] = []
    for line in all_lines:
        if line.strip().startswith("- [") and "]" in line:
            entry_lines.append(line)
        else:
            header_lines.append(line)

    # Keep only the most recent entries (last N)
    if len(entry_lines) > MAX_INDEX_LINES:
        entry_lines = entry_lines[-MAX_INDEX_LINES:]

    result = "\n".join(header_lines + entry_lines)

    # Byte-level truncation: trim from the front of entries if over limit
    if len(result.encode("utf-8")) > MAX_INDEX_BYTES:
        # Keep header, trim oldest entries to fit
        header_text = "\n".join(header_lines)
        header_bytes = len(header_text.encode("utf-8"))
        budget = MAX_INDEX_BYTES - header_bytes
        kept: list[str] = []
        for entry in reversed(entry_lines):
            entry_bytes = len(entry.encode("utf-8")) + 1  # +1 for newline
            if budget - entry_bytes < 0:
                break
            budget -= entry_bytes
            kept.append(entry)
        kept.reverse()
        result = "\n".join(header_lines + kept)

    return result


def read_topic_file(base_dir: Path, category: MemoryCategory) -> str:
    """读取主题文件全文."""
    path = _topic_path(base_dir, category)
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning(f"Failed to read topic file {path}: {e}")
        return ""


def list_topics(base_dir: Path) -> dict[str, int]:
    """返回 {category: line_count} 仅包含有内容的主题."""
    result = {}
    for cat in _TOPIC_FILES:
        content = read_topic_file(base_dir, cat)
        if content.strip():
            # Count non-empty, non-header lines
            lines = [l for l in content.strip().split("\n") if l.strip() and not l.startswith("#")]
            result[cat] = len(lines)
    return result


# ------------------------------------------------------------------
# Write — append a memory entry
# ------------------------------------------------------------------

def _ensure_dir(base_dir: Path) -> None:
    base_dir.mkdir(parents=True, exist_ok=True)


def _ensure_index(base_dir: Path) -> None:
    """创建 MEMORY.md 如果不存在."""
    path = _index_path(base_dir)
    if not path.exists():
        _ensure_dir(base_dir)
        path.write_text(_INDEX_TEMPLATE, encoding="utf-8")


def _ensure_topic(base_dir: Path, category: MemoryCategory) -> None:
    """创建主题文件如果不存在."""
    path = _topic_path(base_dir, category)
    if not path.exists():
        _ensure_dir(base_dir)
        label = _TOPIC_FILES.get(category, category)
        path.write_text(f"# {label}\n\n", encoding="utf-8")


def append_memory(
    base_dir: Path,
    category: MemoryCategory,
    summary: str,
    detail: str | None = None,
) -> None:
    """追加一条自动记忆.

    Args:
        base_dir: auto-memory 目录 (user 或 workspace)
        category: 记忆类别
        summary: 一行摘要 (写入 MEMORY.md 索引)
        detail: 详细内容 (写入主题文件), None 则只用 summary
    """
    _ensure_index(base_dir)
    _ensure_topic(base_dir, category)

    # 1) 写主题文件
    topic_path = _topic_path(base_dir, category)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    entry = detail or summary
    block = f"- [{ts}] {entry.strip()}\n"
    try:
        with topic_path.open("a", encoding="utf-8") as f:
            f.write(block)
    except Exception as e:
        logger.warning(f"Failed to append to topic file {topic_path}: {e}")

    # 2) 写索引 (一行摘要 + 引用)
    line_num = _count_topic_entries(topic_path)
    index_path = _index_path(base_dir)
    index_line = f"- [{category}] {summary.strip()} → {category}.md#L{line_num}\n"
    try:
        with index_path.open("a", encoding="utf-8") as f:
            f.write(index_line)
    except Exception as e:
        logger.warning(f"Failed to append to index {index_path}: {e}")

    # 3) Compact: always dedup, trim if over limit
    try:
        _compact_index(base_dir)
    except Exception:
        pass

    logger.info(f"Auto memory saved: [{category}] {summary[:60]}")


def _count_topic_entries(topic_path: Path) -> int:
    """统计主题文件中的条目数 (非空非注释行)."""
    try:
        content = topic_path.read_text(encoding="utf-8")
        return sum(1 for l in content.split("\n") if l.strip().startswith("- "))
    except Exception:
        return 0


def _compact_index(base_dir: Path) -> int:
    """Compact MEMORY.md index when it exceeds MAX_INDEX_LINES.

    Strategy:
      1. Remove duplicate summaries (keep first occurrence)
      2. If still over limit, keep the most recent entries (last 80%)

    Returns:
        Number of entries after compaction.
    """
    index_path = _index_path(base_dir)
    if not index_path.exists():
        return 0

    try:
        content = index_path.read_text(encoding="utf-8")
        all_lines = content.split("\n")

        # Separate header/template lines from entry lines
        entries: list[str] = []
        for line in all_lines:
            if line.strip().startswith("- [") and "]" in line:
                entries.append(line)

        if not entries:
            return 0

        original_count = len(entries)

        # Dedup by summary text (case-insensitive)
        seen: set[str] = set()
        deduped: list[str] = []
        for entry in entries:
            # Extract summary key: "- [category] summary → ..."
            parts = entry.split("]", 2)
            summary_key = parts[1].strip().split("→")[0].strip().lower() if len(parts) >= 2 else entry.lower()
            if summary_key not in seen:
                seen.add(summary_key)
                deduped.append(entry)

        # If still over limit, keep most recent entries
        trimmed = False
        if len(deduped) > MAX_INDEX_LINES:
            keep = int(MAX_INDEX_LINES * 0.8)
            deduped = deduped[-keep:]
            trimmed = True

        # Skip rewrite if nothing changed
        if len(deduped) == original_count:
            return original_count

        if trimmed:
            logger.warning(
                f"Auto memory index compacted: {original_count} → {len(deduped)} "
                f"(deduped + trimmed to 80%)"
            )
        else:
            logger.info(
                f"Auto memory index deduplicated: {original_count} → {len(deduped)}"
            )

        # Rewrite index
        new_content = _INDEX_TEMPLATE
        for entry in deduped:
            new_content += entry + "\n"
        index_path.write_text(new_content, encoding="utf-8")

        return len(deduped)
    except Exception as e:
        logger.warning(f"Failed to compact index: {e}")
        return 0


# ------------------------------------------------------------------
# Delete
# ------------------------------------------------------------------

def clear_all(base_dir: Path) -> None:
    """清空 auto-memory 目录中的所有内容, 重置为初始模板."""
    _ensure_dir(base_dir)
    # Reset index
    _index_path(base_dir).write_text(_INDEX_TEMPLATE, encoding="utf-8")
    # Remove topic files
    for cat in _TOPIC_FILES:
        path = _topic_path(base_dir, cat)
        if path.exists():
            path.unlink()
    logger.info(f"Cleared auto memory: {base_dir}")


def delete_entry(base_dir: Path, category: MemoryCategory, line_num: int) -> bool:
    """删除主题文件中指定行 + 对应索引行."""
    topic_path = _topic_path(base_dir, category)
    if not topic_path.exists():
        return False

    try:
        lines = topic_path.read_text(encoding="utf-8").split("\n")
        if line_num < 1 or line_num > len(lines):
            return False

        # Remove the entry line
        idx = line_num - 1
        removed = lines.pop(idx)
        topic_path.write_text("\n".join(lines), encoding="utf-8")

        # Rebuild index for this category
        _rebuild_index(base_dir)
        logger.info(f"Deleted auto memory entry [{category}] line {line_num}")
        return True
    except Exception as e:
        logger.warning(f"Failed to delete entry: {e}")
        return False


def _rebuild_index(base_dir: Path) -> None:
    """从主题文件重建 MEMORY.md 索引."""
    _ensure_dir(base_dir)
    lines = [_INDEX_TEMPLATE]

    for cat, label in _TOPIC_FILES.items():
        topic_path = _topic_path(base_dir, cat)
        if not topic_path.exists():
            continue
        try:
            content = topic_path.read_text(encoding="utf-8")
            entries = [l for l in content.split("\n") if l.strip().startswith("- ")]
            for i, entry in enumerate(entries, 1):
                # Extract summary from entry (strip timestamp prefix)
                summary = entry.strip()
                # Format: "- [2025-01-15] content"
                if "]" in summary:
                    summary = summary.split("]", 1)[1].strip()
                lines.append(f"- [{cat}] {summary[:120]} → {cat}.md#L{i}\n")
        except Exception:
            pass

    _index_path(base_dir).write_text("".join(lines), encoding="utf-8")


# ------------------------------------------------------------------
# Stats
# ------------------------------------------------------------------

def get_stats(base_dir: Path) -> dict:
    """返回 auto-memory 统计信息.

    Note: index_lines counts entries in the FULL index file (not truncated),
    so index_near_limit accurately reflects when compaction will trigger.
    """
    # Count actual index entries from the raw file (not truncated)
    index_path = _index_path(base_dir)
    actual_index_lines = 0
    if index_path.exists():
        try:
            raw = index_path.read_text(encoding="utf-8")
            actual_index_lines = sum(1 for l in raw.split("\n") if l.strip().startswith("- ["))
        except Exception:
            pass

    topics = list_topics(base_dir)
    total = sum(topics.values())

    return {
        "total_entries": total,
        "index_lines": actual_index_lines,
        "index_near_limit": actual_index_lines >= int(MAX_INDEX_LINES * 0.8),
        "topics": topics,
    }
