# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Auto-memory 单元测试 — 自由 topic 模型.

覆盖:
  - topic_slug 安全化 (CJK 保留 / 敌意字符替换 / 截断 / 非法输入)
  - append_memory 自由 topic 写入 + 索引行格式
  - legacy 四类 (facts 等) 向后兼容 (仍是合法 topic)
  - list_topics / get_stats 目录扫描
  - delete_entry 按第 n 个条目删除 + 索引重建 + 空主题文件回收
  - clear_all 清理全部主题文件

Usage:
    cd agent
    pytest tests/test_auto_memory.py -v
"""

from pathlib import Path

import pytest

from dawei.memory.auto_memory import (
    append_memory,
    clear_all,
    delete_entry,
    get_stats,
    list_topics,
    read_auto_memory_index,
    topic_slug,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# topic_slug
# ---------------------------------------------------------------------------


class TestTopicSlug:
    def test_cjk_preserved(self):
        assert topic_slug("用户偏好") == "用户偏好"
        assert topic_slug("客户A要求") == "客户A要求"

    def test_ascii_passthrough(self):
        assert topic_slug("facts") == "facts"
        assert topic_slug("My-Topic_1") == "My-Topic_1"

    def test_unsafe_chars_replaced(self):
        assert "/" not in topic_slug("a/b\\c")
        assert topic_slug("项目 规范") == "项目-规范"
        assert topic_slug("a?b*c") == "a-b-c"

    def test_length_capped(self):
        assert len(topic_slug("超" * 50)) == 24

    def test_invalid_topics(self):
        assert topic_slug("") == ""
        assert topic_slug("   ") == ""
        assert topic_slug("///") == ""
        assert topic_slug("???") == ""


# ---------------------------------------------------------------------------
# append / read / list
# ---------------------------------------------------------------------------


class TestAppendMemory:
    def test_free_form_topic_creates_file(self, tmp_path: Path):
        base = tmp_path / "auto-memory"
        append_memory(base, "项目规范", "后端使用 FastAPI")

        assert (base / "项目规范.md").exists()
        index = read_auto_memory_index(base)
        assert "[项目规范]" in index
        assert "后端使用 FastAPI" in index
        assert "项目规范.md#L1" in index

    def test_multiple_entries_same_topic(self, tmp_path: Path):
        base = tmp_path / "auto-memory"
        append_memory(base, "用户偏好", "喜欢简洁回复")
        append_memory(base, "用户偏好", "偏好中文")

        topics = list_topics(base)
        assert topics == {"用户偏好": 2}
        index = read_auto_memory_index(base)
        assert index.count("[用户偏好]") == 2

    def test_legacy_categories_still_valid(self, tmp_path: Path):
        base = tmp_path / "auto-memory"
        append_memory(base, "facts", "Project uses PostgreSQL")
        append_memory(base, "debugging", "pool exhaustion caused 500")

        topics = list_topics(base)
        assert set(topics) == {"facts", "debugging"}

    def test_invalid_topic_raises(self, tmp_path: Path):
        with pytest.raises(ValueError, match="topic"):
            append_memory(tmp_path / "auto-memory", "///", "summary")

    def test_summary_dedup_in_index(self, tmp_path: Path):
        base = tmp_path / "auto-memory"
        append_memory(base, "偏好", "same summary")
        append_memory(base, "偏好", "same summary")

        index = read_auto_memory_index(base)
        assert index.count("same summary") == 1


# ---------------------------------------------------------------------------
# stats / scan
# ---------------------------------------------------------------------------


def test_stats_scans_all_topics(tmp_path: Path):
    base = tmp_path / "auto-memory"
    append_memory(base, "主题一", "a")
    append_memory(base, "主题二", "b")
    append_memory(base, "主题二", "c")

    stats = get_stats(base)
    assert stats["total_entries"] == 3
    assert stats["topics"] == {"主题一": 1, "主题二": 2}
    assert stats["index_lines"] == 3


# ---------------------------------------------------------------------------
# delete_entry — 更新 = 删旧 + 存新
# ---------------------------------------------------------------------------


class TestDeleteEntry:
    def test_delete_by_entry_ordinal(self, tmp_path: Path):
        base = tmp_path / "auto-memory"
        for s in ("first", "second", "third"):
            append_memory(base, "规范", s)

        # line = 第 n 个条目 (与索引 #L{n} 同语义), 非物理行号
        assert delete_entry(base, "规范", 2) is True

        content = (base / "规范.md").read_text(encoding="utf-8")
        assert "second" not in content
        assert "first" in content
        assert "third" in content

        index = read_auto_memory_index(base)
        assert index.count("[规范]") == 2

    def test_delete_only_entry_removes_topic_file(self, tmp_path: Path):
        base = tmp_path / "auto-memory"
        append_memory(base, "临时", "only one")

        assert delete_entry(base, "临时", 1) is True
        assert not (base / "临时.md").exists()
        assert list_topics(base) == {}
        assert get_stats(base)["total_entries"] == 0

    def test_delete_out_of_range(self, tmp_path: Path):
        base = tmp_path / "auto-memory"
        append_memory(base, "规范", "only")
        assert delete_entry(base, "规范", 5) is False
        assert delete_entry(base, "不存在", 1) is False


# ---------------------------------------------------------------------------
# clear_all
# ---------------------------------------------------------------------------


def test_clear_all_removes_free_form_topics(tmp_path: Path):
    base = tmp_path / "auto-memory"
    append_memory(base, "用户偏好", "x")
    append_memory(base, "自定义主题", "y")

    clear_all(base)
    assert list_topics(base) == {}
    assert not (base / "用户偏好.md").exists()
    assert not (base / "自定义主题.md").exists()
    assert get_stats(base)["total_entries"] == 0
