# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""用户级 Memory API。

两级功能：
1. **配置** (per-user): ``{DAWEI_HOME}/configs/{user_id}/memory.json``
   - GET/PUT ``/me/memory`` — memory 参数默认 (enabled, page_size, energy_decay 等)
   - workspace 级 config.json 的 memory 段可覆盖

2. **记忆数据** (per-user, 跨工作区共享): ``{DAWEI_HOME}/configs/{user_id}/memory.db``
   - GET/POST ``/me/memory/entries`` — 用户级记忆 CRUD
   - PATCH/DELETE ``/me/memory/entries/{id}``
"""

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from dawei import get_dawei_home
from dawei.api.auth import get_authenticated_user_id
from dawei.core.datetime_compat import UTC

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/me/memory", tags=["User Memory"])

_DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "read_enabled": True,
    "write_enabled": True,
    "virtual_page_size": 2000,
    "max_active_pages": 5,
    "default_energy": 1.0,
    "energy_decay_rate": 0.95,
    "min_energy_threshold": 0.2,
    "consolidation_enabled": False,
}


def _safe_uid(user_id: str | None) -> str:
    uid = user_id or "default_user"
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in uid)


def _config_file(user_id: str = "default_user") -> Path:
    return get_dawei_home() / "configs" / _safe_uid(user_id) / "memory.json"


def _user_memory_db_path(user_id: str = "default_user") -> str:
    """用户级 memory.db 路径（跨工作区共享）。"""
    path = _config_file(user_id).parent / "memory.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)


def _load(user_id: str = "default_user") -> dict[str, Any]:
    path = _config_file(user_id)
    if not path.exists():
        return dict(_DEFAULTS)
    try:
        with path.open("r", encoding="utf-8") as f:
            return {**dict(_DEFAULTS), **json.load(f)}
    except Exception as e:
        logger.error("Failed to load user memory config: %s", e)
        return dict(_DEFAULTS)


def _save(cfg: dict[str, Any], user_id: str = "default_user") -> None:
    path = _config_file(user_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def load_user_memory(user_id: str = "default_user") -> dict[str, Any]:
    """供 effective merge 端点 / agent 桥接复用：读取 user 级 memory 默认（per-user）。"""
    return _load(user_id)


class UserMemoryConfig(BaseModel):
    enabled: bool = True
    read_enabled: bool = True
    write_enabled: bool = True
    virtual_page_size: int = 2000
    max_active_pages: int = 5
    default_energy: float = 1.0
    energy_decay_rate: float = 0.95
    min_energy_threshold: float = 0.2
    consolidation_enabled: bool = False


@router.get("", response_model=UserMemoryConfig)
async def get_user_memory(current_user: str = Depends(get_authenticated_user_id)):
    """获取用户级 memory 默认配置"""
    return UserMemoryConfig(**{k: v for k, v in _load(current_user).items() if k in _DEFAULTS})


@router.put("", response_model=UserMemoryConfig)
async def update_user_memory(
    config: UserMemoryConfig, current_user: str = Depends(get_authenticated_user_id)
):
    """更新用户级 memory 默认配置"""
    _save(config.model_dump(), current_user)
    logger.info("User memory config updated (user=%s)", current_user)
    return config


# ============================================================================
# 用户级记忆数据 CRUD (跨工作区共享)
# ============================================================================


class UserMemoryCreateRequest(BaseModel):
    """创建用户级记忆"""

    subject: str
    predicate: str
    object: str
    memory_type: str = "fact"
    confidence: float = 0.8
    energy: float = 1.0
    keywords: list[str] = []


class UserMemoryUpdateRequest(BaseModel):
    """更新用户级记忆"""

    predicate: str | None = None
    object: str | None = None
    valid_end: str | None = None
    confidence: float | None = None
    energy: float | None = None
    keywords: list[str] | None = None


def _get_user_memory_graph(user_id: str):
    """获取用户级 MemoryGraph 实例"""
    from dawei.memory.memory_graph import MemoryGraph

    db_path = _user_memory_db_path(user_id)
    return MemoryGraph(db_path)


@router.get("/entries")
async def list_user_memory_entries(
    current_user: str = Depends(get_authenticated_user_id),
    type: str | None = Query(None),
    min_confidence: float | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """列出用户级记忆（跨工作区）"""
    from dawei.api.workspaces.memory import _memory_to_response
    from dawei.memory.memory_graph import MemoryType

    graph = _get_user_memory_graph(current_user)
    memory_type = MemoryType(type) if type else None

    memories = await graph.query_temporal(
        memory_type=memory_type,
        only_valid=True,
    )

    if min_confidence is not None:
        memories = [m for m in memories if m.confidence >= min_confidence]

    total = len(memories)
    start = (page - 1) * page_size
    paginated = memories[start : start + page_size]

    return {
        "items": [_memory_to_response(m) for m in paginated],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/entries", status_code=201)
async def create_user_memory_entry(
    request: UserMemoryCreateRequest,
    current_user: str = Depends(get_authenticated_user_id),
):
    """创建用户级记忆（跨工作区共享）"""
    from dawei.memory.memory_graph import MemoryEntry, MemoryType

    graph = _get_user_memory_graph(current_user)
    memory = MemoryEntry(
        id=str(uuid.uuid4()),
        subject=request.subject,
        predicate=request.predicate,
        object=request.object,
        valid_start=datetime.now(UTC),
        memory_type=MemoryType(request.memory_type),
        confidence=request.confidence,
        energy=request.energy,
        keywords=request.keywords,
        metadata={"source": "user_api", "scope": "user"},
    )
    memory_id = await graph.add_memory(memory)
    created = await graph.get_memory(memory_id)
    from dawei.api.workspaces.memory import _memory_to_response

    return _memory_to_response(created)


@router.get("/entries/{memory_id}")
async def get_user_memory_entry(
    memory_id: str,
    current_user: str = Depends(get_authenticated_user_id),
):
    """获取单条用户级记忆"""
    from dawei.api.workspaces.memory import _memory_to_response

    graph = _get_user_memory_graph(current_user)
    memory = await graph.get_memory(memory_id)
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    return _memory_to_response(memory)


@router.patch("/entries/{memory_id}")
async def update_user_memory_entry(
    memory_id: str,
    request: UserMemoryUpdateRequest,
    current_user: str = Depends(get_authenticated_user_id),
):
    """更新用户级记忆"""
    from dawei.api.workspaces.memory import _memory_to_response

    graph = _get_user_memory_graph(current_user)

    valid_end = None
    if request.valid_end:
        valid_end = datetime.fromisoformat(request.valid_end)

    success = await graph.update_memory(
        memory_id,
        predicate=request.predicate,
        object=request.object,
        valid_end=valid_end,
        confidence=request.confidence,
        energy=request.energy,
        keywords=request.keywords,
    )
    if not success:
        raise HTTPException(status_code=404, detail="Memory not found")
    updated = await graph.get_memory(memory_id)
    return _memory_to_response(updated)


@router.delete("/entries/{memory_id}", status_code=204)
async def delete_user_memory_entry(
    memory_id: str,
    current_user: str = Depends(get_authenticated_user_id),
):
    """删除用户级记忆"""
    graph = _get_user_memory_graph(current_user)
    success = await graph.delete_memory(memory_id)
    if not success:
        raise HTTPException(status_code=404, detail="Memory not found")


# ============================================================================
# Markdown Memory File (simplified, Codex-inspired)
# ============================================================================


class MemoryMdRequest(BaseModel):
    """Update memory.md content."""
    content: str


@router.get("/md")
async def get_user_memory_md(current_user: str = Depends(get_authenticated_user_id)):
    """获取用户级 memory.md 内容"""
    from dawei.memory.memory_file import read_memory_md, user_memory_md_path

    path = user_memory_md_path(current_user)
    content = read_memory_md(path)
    return {"content": content, "path": str(path)}


@router.put("/md")
async def update_user_memory_md(
    request: MemoryMdRequest,
    current_user: str = Depends(get_authenticated_user_id),
):
    """更新用户级 memory.md 内容"""
    from dawei.memory.memory_file import user_memory_md_path, write_memory_md
    from dawei.memory.redactor import redact_secrets

    content = redact_secrets(request.content)
    path = user_memory_md_path(current_user)
    write_memory_md(path, content)
    logger.info("User memory.md updated (user=%s)", current_user)
    return {"content": content, "path": str(path)}


# ============================================================================
# Auto Memory — 用户级 (Agent 自动从对话中提取, 跨工作区共享)
# ============================================================================


@router.get("/auto")
async def get_user_auto_memory(current_user: str = Depends(get_authenticated_user_id)):
    """获取用户级 auto-memory (索引 + 各主题文件内容, 主题自由命名目录扫描)."""
    from dawei.memory.auto_memory import (
        get_stats,
        list_topics,
        read_auto_memory_index,
        read_topic_file,
        user_auto_memory_dir,
    )

    base_dir = user_auto_memory_dir(current_user)
    index = read_auto_memory_index(base_dir)
    topics_content = {}
    for topic in list_topics(base_dir):
        content = read_topic_file(base_dir, topic)
        if content.strip():
            topics_content[topic] = content

    return {
        "index": index,
        "topics": topics_content,
        "topic_counts": list_topics(base_dir),
        "stats": get_stats(base_dir),
        "path": str(base_dir),
    }


@router.delete("/auto")
async def clear_user_auto_memory(current_user: str = Depends(get_authenticated_user_id)):
    """清空用户级 auto-memory."""
    from dawei.memory.auto_memory import clear_all, user_auto_memory_dir

    base_dir = user_auto_memory_dir(current_user)
    clear_all(base_dir)
    return {"message": "User auto memory cleared"}


@router.delete("/auto/entry")
async def delete_user_auto_memory_entry(
    topic: str,
    line: int,
    current_user: str = Depends(get_authenticated_user_id),
):
    """删除用户级 auto-memory 单条条目 (更新 = 删旧 + 存新).

    line 为该主题文件中第 n 个条目 (与索引 {topic}.md#L{n} 引用同语义).
    """
    from dawei.memory.auto_memory import delete_entry, user_auto_memory_dir

    base_dir = user_auto_memory_dir(current_user)
    if not delete_entry(base_dir, topic, line):
        raise HTTPException(status_code=404, detail=f"Entry not found: {topic}#L{line}")
    return {"message": "Entry deleted", "topic": topic, "line": line}


@router.get("/auto/stats")
async def get_user_auto_memory_stats(current_user: str = Depends(get_authenticated_user_id)):
    """获取用户级 auto-memory 统计."""
    from dawei.memory.auto_memory import get_stats, user_auto_memory_dir

    base_dir = user_auto_memory_dir(current_user)
    return get_stats(base_dir)

