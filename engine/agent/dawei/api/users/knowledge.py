# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""用户级 Knowledge 配置 API。

提供 user 级知识库默认（per-user），存 ``{DAWEI_HOME}/configs/{user_id}/knowledge.json``。
注：引擎参数（embedding/dimension/chunk 等）运行时由每个 KB 实体自身的 ``kb.settings``
驱动；此处的 user 级默认仅供 override-or-inherit 展示与新库参考。workspace 级真正生效的
字段主要是 ``enabled``。
"""

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from dawei import get_dawei_home
from dawei.api.auth import get_authenticated_user_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/me/knowledge", tags=["User Knowledge"])

_DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "vector_store_type": "sqlite-vec",
    "embedding_model": "Qwen/Qwen3-Embedding-0.6B",
    "dimension": 1024,
    "chunk_size": 500,
    "chunk_overlap": 50,
    "default_top_k": 5,
    "retrieval_mode": "hybrid",
    "rag_context_length": 2000,
}


def _safe_uid(user_id: str | None) -> str:
    uid = user_id or "default_user"
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in uid)


def _config_file(user_id: str = "default_user") -> Path:
    return get_dawei_home() / "configs" / _safe_uid(user_id) / "knowledge.json"


def _load(user_id: str = "default_user") -> dict[str, Any]:
    path = _config_file(user_id)
    if not path.exists():
        return dict(_DEFAULTS)
    try:
        with path.open("r", encoding="utf-8") as f:
            return {**dict(_DEFAULTS), **json.load(f)}
    except Exception as e:
        logger.error("Failed to load user knowledge config: %s", e)
        return dict(_DEFAULTS)


def _save(cfg: dict[str, Any], user_id: str = "default_user") -> None:
    path = _config_file(user_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def load_user_knowledge(user_id: str = "default_user") -> dict[str, Any]:
    """供 effective merge 端点 / agent 桥接复用：读取 user 级 knowledge 默认（per-user）。"""
    return _load(user_id)


class UserKnowledgeConfig(BaseModel):
    enabled: bool = True
    vector_store_type: str = "sqlite-vec"
    embedding_model: str = "Qwen/Qwen3-Embedding-0.6B"
    dimension: int = 1024
    chunk_size: int = 500
    chunk_overlap: int = 50
    default_top_k: int = 5
    retrieval_mode: str = "hybrid"
    rag_context_length: int = 2000


@router.get("", response_model=UserKnowledgeConfig)
async def get_user_knowledge(current_user: str = Depends(get_authenticated_user_id)):
    """获取用户级 knowledge 默认配置"""
    return UserKnowledgeConfig(**{k: v for k, v in _load(current_user).items() if k in _DEFAULTS})


@router.put("", response_model=UserKnowledgeConfig)
async def update_user_knowledge(
    config: UserKnowledgeConfig, current_user: str = Depends(get_authenticated_user_id)
):
    """更新用户级 knowledge 默认配置"""
    _save(config.model_dump(), current_user)
    logger.info("User knowledge config updated (user=%s)", current_user)
    return config
