# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""任务列表嵌套（2026-09-24）：/conversations 端点 subtask 会话归父单测

覆盖 _annotate_subtask_parent_conversations 的三条归父路径：
1. 图节点链上 metadata.root_conversation_id 盖章（含祖先链上溯）
2. 时间窗回退（盖章前的旧数据）：created_at 落入用户会话活跃窗，updated_at 最新的胜出
3. 全部失败 → None（平铺兜底，绝不丢数据）
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dawei.api.conversations import _annotate_subtask_parent_conversations


class _FakeWorkspaceManager:
    def __init__(self, ws_path: Path):
        self._ws_path = ws_path

    def get_workspace_by_id(self, workspace_id: str):
        return {"id": workspace_id, "path": str(self._ws_path)}


def _write_graph(ws_root: Path, graph_id: str, nodes: dict) -> None:
    graphs_dir = ws_root / ".dawei" / "task_graphs"
    graphs_dir.mkdir(parents=True, exist_ok=True)
    (graphs_dir / f"{graph_id}.json").write_text(
        json.dumps({"nodes": nodes}, ensure_ascii=False), encoding="utf-8"
    )


def _conv(cid: str, task_type: str = "user", *, source_task_id=None, created=None, updated=None):
    return {
        "id": cid,
        "task_type": task_type,
        "source_task_id": source_task_id,
        "created_at": created,
        "updated_at": updated,
    }


@pytest.fixture()
def ws(tmp_path: Path, monkeypatch):
    """临时工作区 + workspace_manager 打桩（只替换 conversations 模块的引用）"""
    from dawei.api import conversations as conv_mod

    ws_root = tmp_path / "ws"
    (ws_root / ".dawei" / "conversations").mkdir(parents=True)
    fake = _FakeWorkspaceManager(ws_root)
    monkeypatch.setattr(conv_mod, "workspace_manager", fake)
    return ws_root


def test_stamp_on_ancestor_chain_wins(ws):
    """子任务自身节点未盖章，但祖先链（父节点）盖章 → 上溯命中"""
    _write_graph(
        ws,
        "g1",
        {
            "root-1": {"parent_id": None},
            "sub-1": {"parent_id": "root-1", "data": {"metadata": {}}},
            "leaf-1": {
                "parent_id": "sub-1",
                "data": {"metadata": {"root_conversation_id": "conv-main"}},
            },
        },
    )
    convs = [
        _conv("conv-main", created="2026-09-23T06:00:00", updated="2026-09-23T07:00:00"),
        _conv("conv-sub", "subtask", source_task_id="leaf-1", created="2026-09-23T06:30:00"),
    ]
    _annotate_subtask_parent_conversations(convs, "ws-id")
    assert convs[1]["parent_conversation_id"] == "conv-main"
    assert convs[0]["parent_conversation_id"] is None


def test_time_window_fallback_latest_updated_wins(ws):
    """旧数据（无盖章）：两个用户会话活跃窗重叠，updated_at 最新的胜出"""
    _write_graph(ws, "g1", {"root-1": {"parent_id": None}, "sub-1": {"parent_id": "root-1"}})
    convs = [
        _conv("conv-old", created="2026-09-23T05:00:00", updated="2026-09-23T07:30:00"),
        _conv("conv-new", created="2026-09-23T06:00:00", updated="2026-09-23T07:00:00"),
        _conv(
            "conv-sub",
            "subtask",
            source_task_id="sub-1",
            created="2026-09-23T06:30:00",
            updated="2026-09-23T06:40:00",
        ),
    ]
    _annotate_subtask_parent_conversations(convs, "ws-id")
    assert convs[2]["parent_conversation_id"] == "conv-old"  # 07:30 > 07:00


def test_time_window_single_candidate(ws):
    """仅一个用户会话候选时直接归入"""
    _write_graph(ws, "g1", {"sub-1": {"parent_id": "root-x"}})
    convs = [
        _conv("conv-only", created="2026-09-20T00:00:00", updated="2026-09-20T01:00:00"),
        # 时间窗不含（created 晚于用户会话 updated_at）→ 但唯一候选仍归入
        _conv("conv-sub", "subtask", source_task_id="sub-1", created="2026-09-23T00:00:00"),
    ]
    _annotate_subtask_parent_conversations(convs, "ws-id")
    assert convs[1]["parent_conversation_id"] == "conv-only"


def test_no_match_stays_flat(ws):
    """多候选且时间窗全部未命中 → None（平铺兜底）"""
    _write_graph(ws, "g1", {"sub-1": {"parent_id": "root-x"}})
    convs = [
        _conv("conv-a", created="2026-09-20T00:00:00", updated="2026-09-20T01:00:00"),
        _conv("conv-b", created="2026-09-21T00:00:00", updated="2026-09-21T01:00:00"),
        _conv("conv-sub", "subtask", source_task_id="sub-1", created="2026-09-23T00:00:00"),
    ]
    _annotate_subtask_parent_conversations(convs, "ws-id")
    assert convs[2]["parent_conversation_id"] is None


def test_unreadable_graph_falls_back_to_window(ws):
    """图目录不存在（get_workspace_by_id 打桩有效但无图文件）→ 退时间窗"""
    convs = [
        _conv("conv-main", created="2026-09-23T05:00:00", updated="2026-09-23T08:00:00"),
        _conv("conv-sub", "subtask", source_task_id="unknown-node", created="2026-09-23T06:00:00"),
    ]
    _annotate_subtask_parent_conversations(convs, "ws-id")
    assert convs[1]["parent_conversation_id"] == "conv-main"


def test_non_subtask_gets_none_default(ws):
    """无子任务会话时：所有会话仍带 parent_conversation_id=None 默认键"""
    convs = [_conv("conv-a"), _conv("conv-b")]
    _annotate_subtask_parent_conversations(convs, "ws-id")
    assert all(c["parent_conversation_id"] is None for c in convs)


# ================================================================
# 级联删除：_resolve_subtask_child_ids（2026-09-24）
# ================================================================

from dawei.api.conversations import _resolve_subtask_child_ids  # noqa: E402


def _write_conv_file(conv_dir: Path, cid: str, payload: dict) -> None:
    conv_dir.mkdir(parents=True, exist_ok=True)
    (conv_dir / f"{cid}.json").write_text(
        json.dumps({"id": cid, **payload}, ensure_ascii=False), encoding="utf-8"
    )


def test_cascade_resolves_stamp_and_window_children(ws):
    """级联解析：盖章与时间窗两条路径的子任务会话都返回；他父的不动"""
    _write_graph(
        ws,
        "g1",
        {
            "root-1": {"parent_id": None},
            "sub-stamp": {
                "parent_id": "root-1",
                "data": {"metadata": {"root_conversation_id": "conv-main"}},
            },
            "sub-win": {"parent_id": "root-1"},
            "sub-other": {
                "parent_id": "root-1",
                "data": {"metadata": {"root_conversation_id": "conv-other"}},
            },
        },
    )
    conv_dir = ws / ".dawei" / "conversations"
    _write_conv_file(
        conv_dir,
        "conv-main",
        {
            "task_type": "user",
            "created_at": "2026-09-23T05:00:00",
            "updated_at": "2026-09-23T08:00:00",
        },
    )
    _write_conv_file(
        conv_dir,
        "conv-other",
        {
            "task_type": "user",
            "created_at": "2026-09-20T00:00:00",
            "updated_at": "2026-09-20T01:00:00",
        },
    )
    _write_conv_file(
        conv_dir,
        "sub-stamp",
        {
            "task_type": "subtask",
            "source_task_id": "sub-stamp",
            "created_at": "2026-09-26T00:00:00",  # 窗外：仅靠盖章归父
        },
    )
    _write_conv_file(
        conv_dir,
        "sub-win",
        {
            "task_type": "subtask",
            "source_task_id": "sub-win",
            "created_at": "2026-09-23T06:00:00",  # conv-main 窗内
        },
    )
    _write_conv_file(
        conv_dir,
        "sub-other",
        {
            "task_type": "subtask",
            "source_task_id": "sub-other",
            "created_at": "2026-09-21T00:00:00",
        },
    )

    children = _resolve_subtask_child_ids(conv_dir, "ws-id", "conv-main")
    assert set(children) == {"sub-stamp", "sub-win"}  # sub-other 归 conv-other，不动


def test_cascade_skips_corrupt_files(ws):
    """损坏的会话文件只跳过，不阻断其余解析"""
    conv_dir = ws / ".dawei" / "conversations"
    _write_conv_file(
        conv_dir,
        "conv-main",
        {
            "task_type": "user",
            "created_at": "2026-09-23T05:00:00",
            "updated_at": "2026-09-23T08:00:00",
        },
    )
    (conv_dir / "corrupt.json").write_text("{not-json", encoding="utf-8")
    _write_conv_file(
        conv_dir,
        "sub-ok",
        {
            "task_type": "subtask",
            "source_task_id": "node-x",
            "created_at": "2026-09-23T06:00:00",
        },
    )
    children = _resolve_subtask_child_ids(conv_dir, "ws-id", "conv-main")
    assert children == ["sub-ok"]  # 单一候选回退仍命中 conv-main
