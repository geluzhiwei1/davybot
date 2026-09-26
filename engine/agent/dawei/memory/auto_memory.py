# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Auto memory — Agent 自动从对话中提取的记忆。

双作用域:
  - 用户级: {DAWEI_HOME}/configs/{uid}/auto-memory/
  - 工作区级: {workspace}/.dawei/auto-memory/

每级目录结构 (topic 为自由主题, 由 LLM/用户自定, 无固定枚举):
  MEMORY.md          — 索引文件 (每条记忆一行摘要, 注入前 MAX_INDEX_LINES 行)
  {topic}.md         — 主题文件 (每个主题一个, 文件名 = topic 的安全 slug)

历史兼容: 旧固定四类 facts/preferences/procedures/debugging 自然降级为
普通 topic (目录扫描读取, 无需迁移)。

注入策略: 仅 MEMORY.md 前 MAX_INDEX_LINES 行注入系统提示词,
主题文件不注入, Agent 可用工具按需读取。

更新语义: 追加式 —— save_memory 只追加; 索引按摘要去重 (同摘要不重复);
单条删除走 delete_entry (API/UI 暴露), 偏好变化 = 删旧 + 存新。
"""

from __future__ import annotations

import logging
import re
import unicodedata
from datetime import UTC, datetime
from pathlib import Path

from dawei import get_dawei_home
from dawei.memory.memory_file import _safe_uid

logger = logging.getLogger(__name__)

# topic 为自由字符串 (不再枚举); 保留类型别名便于调用方注解
MemoryCategory = str

MAX_INDEX_LINES = 100
MAX_INDEX_BYTES = 4096

# topic slug 上限 (字符数)
MAX_TOPIC_LEN = 24

# slug 安全字符: 字母/数字/CJK/连字符/下划线; 其余 (含空白、路径分隔符、标点) → '-'
_TOPIC_UNSAFE = re.compile(r"[^\w\u4e00-\u9fff\u3400-\u4dbf-]+", re.UNICODE)

_INDEX_TEMPLATE = """\
# Auto Memory Index
<!-- Agent 自动维护, 请勿手动编辑. 每行一条记忆摘要. -->

"""


# ------------------------------------------------------------------
# Topic slug
# ------------------------------------------------------------------


def topic_slug(topic: str) -> str:
    """把自由 topic 转成安全文件名 (保留中文/字母/数字/-/_).

    - NFC 归一 + 空白折叠
    - 不安全字符替换为 '-'
    - 截断到 MAX_TOPIC_LEN
    - 返回空串表示非法 topic (调用方 FAST FAIL)
    """
    normalized = unicodedata.normalize("NFC", str(topic)).strip()
    slug = _TOPIC_UNSAFE.sub("-", normalized)
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug[:MAX_TOPIC_LEN]


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


def _topic_path(base_dir: Path, topic: str) -> Path:
    return base_dir / f"{topic_slug(topic)}.md"


def _iter_topic_files(base_dir: Path) -> list[Path]:
    """列出目录下全部主题文件 (按名排序, 排除索引)."""
    if not base_dir.exists():
        return []
    return sorted(p for p in base_dir.glob("*.md") if p.name != "MEMORY.md")


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


def read_topic_file(base_dir: Path, topic: str) -> str:
    """读取主题文件全文."""
    path = _topic_path(base_dir, topic)
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning(f"Failed to read topic file {path}: {e}")
        return ""


def list_topics(base_dir: Path) -> dict[str, int]:
    """返回 {topic_slug: line_count} 仅包含有内容的主题 (目录扫描)."""
    result = {}
    for path in _iter_topic_files(base_dir):
        try:
            content = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if content.strip():
            lines = [ln for ln in content.strip().split("\n") if ln.strip() and not ln.startswith("#")]
            result[path.stem] = len(lines)
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


def _ensure_topic(base_dir: Path, topic: str) -> Path:
    """创建主题文件如果不存在; 返回文件路径. topic 非法时抛 ValueError."""
    slug = topic_slug(topic)
    if not slug:
        raise ValueError(f"invalid memory topic: {topic!r}")
    path = base_dir / f"{slug}.md"
    if not path.exists():
        _ensure_dir(base_dir)
        # 标题用原始 topic 文本 (slug 可能被截断/替换)
        path.write_text(f"# {str(topic).strip()}\n\n", encoding="utf-8")
    return path


def append_memory(
    base_dir: Path,
    topic: str,
    summary: str,
    detail: str | None = None,
) -> None:
    """追加一条自动记忆.

    Args:
        base_dir: auto-memory 目录 (user 或 workspace)
        topic: 自由主题 (如 '用户偏好'/'项目规范'/'facts'), 决定主题文件名
        summary: 一行摘要 (写入 MEMORY.md 索引)
        detail: 详细内容 (写入主题文件), None 则只用 summary
    """
    slug = topic_slug(topic)
    if not slug:
        raise ValueError(f"invalid memory topic: {topic!r}")

    _ensure_index(base_dir)
    topic_path = _ensure_topic(base_dir, topic)

    # 1) 写主题文件
    ts = datetime.now(UTC).strftime("%Y-%m-%d")
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
    index_line = f"- [{slug}] {summary.strip()} → {slug}.md#L{line_num}\n"
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

    logger.info(f"Auto memory saved: [{slug}] {summary[:60]}")


def _count_topic_entries(topic_path: Path) -> int:
    """统计主题文件中的条目数 (非空非注释行)."""
    try:
        content = topic_path.read_text(encoding="utf-8")
        return sum(1 for ln in content.split("\n") if ln.strip().startswith("- "))
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
            # Extract summary key: "- [topic] summary → ..."
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
            logger.warning(f"Auto memory index compacted: {original_count} → {len(deduped)} (deduped + trimmed to 80%)")
        else:
            logger.info(f"Auto memory index deduplicated: {original_count} → {len(deduped)}")

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
    # Remove all topic files
    for path in _iter_topic_files(base_dir):
        try:
            path.unlink()
        except Exception as e:
            logger.warning(f"Failed to remove topic file {path}: {e}")
    logger.info(f"Cleared auto memory: {base_dir}")


def delete_entry(base_dir: Path, topic: str, line_num: int) -> bool:
    """删除主题文件中第 line_num 个条目 (与索引引用 {slug}.md#L{n} 同语义) + 重建索引."""
    topic_path = _topic_path(base_dir, topic)
    if not topic_path.exists():
        return False

    try:
        lines = topic_path.read_text(encoding="utf-8").split("\n")
        # line_num 指第 n 个条目行 ("- " 开头), 而非文件物理行号 —— 与索引 #L 引用一致
        entry_idxs = [i for i, ln in enumerate(lines) if ln.strip().startswith("- ")]
        if line_num < 1 or line_num > len(entry_idxs):
            return False

        idx = entry_idxs[line_num - 1]
        removed = lines.pop(idx)
        # 条目删空后删除整个主题文件 (不留空壳)
        remaining = [ln for ln in lines if ln.strip() and not ln.startswith("#")]
        if remaining:
            topic_path.write_text("\n".join(lines), encoding="utf-8")
        else:
            topic_path.unlink()

        # Rebuild index
        _rebuild_index(base_dir)
        logger.info(f"Deleted auto memory entry [{topic}] line {line_num}: {removed[:60]}")
        return True
    except Exception as e:
        logger.warning(f"Failed to delete entry: {e}")
        return False


def _rebuild_index(base_dir: Path) -> None:
    """从主题文件重建 MEMORY.md 索引."""
    _ensure_dir(base_dir)
    parts = [_INDEX_TEMPLATE]

    for topic_path in _iter_topic_files(base_dir):
        try:
            content = topic_path.read_text(encoding="utf-8")
            entries = [ln for ln in content.split("\n") if ln.strip().startswith("- ")]
            for i, entry in enumerate(entries, 1):
                # Extract summary from entry (strip timestamp prefix)
                summary = entry.strip()
                # Format: "- [2025-01-15] content"
                if "]" in summary:
                    summary = summary.split("]", 1)[1].strip()
                parts.append(f"- [{topic_path.stem}] {summary[:120]} → {topic_path.stem}.md#L{i}\n")
        except Exception:
            pass

    _index_path(base_dir).write_text("".join(parts), encoding="utf-8")


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
            actual_index_lines = sum(1 for ln in raw.split("\n") if ln.strip().startswith("- ["))
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
