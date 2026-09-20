# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Knowledge Base initialization and setup"""

import logging
from pathlib import Path

from dawei.core.dependency_container import DEPENDENCY_CONTAINER
from dawei.knowledge.base_manager import KnowledgeBaseManager
from dawei.config.settings import get_settings
from dawei import get_dawei_home

logger = logging.getLogger(__name__)


def initialize_knowledge_base_manager() -> KnowledgeBaseManager:
    """Initialize and register the knowledge base manager

    Returns:
        KnowledgeBaseManager instance
    """
    try:
        # Get knowledge base root path - use get_dawei_home() for user-level path
        settings = get_settings()
        knowledge_root = get_dawei_home() / "knowledge"

        # Create manager
        manager = KnowledgeBaseManager(root_path=knowledge_root)

        # Register in dependency container
        DEPENDENCY_CONTAINER.register(KnowledgeBaseManager, manager)

        logger.info(f"Knowledge base manager initialized with root: {knowledge_root}")

        # Create default knowledge base if none exists
        _ensure_default_base(manager)

        return manager

    except Exception as e:
        logger.error(f"Failed to initialize knowledge base manager: {e}", exc_info=True)
        raise


def _user_knowledge_settings():
    """读取用户级 knowledge 默认（configs/knowledge.json），映射为 KnowledgeBaseSettings。

    用户级字段名 → KB settings 字段名：
      embedding_model → embedding_model
      dimension       → embedding_dimension
      chunk_size      → chunk_size
      chunk_overlap   → chunk_overlap
      default_top_k   → default_top_k
      retrieval_mode  → default_mode

    仅识别到的字段才覆盖，其余用 KnowledgeBaseSettings 默认。失败返回空 dict（由
    KnowledgeBaseCreate 回退到默认）。仅影响新建 KB，已有 KB 不受影响。
    """
    try:
        from dawei.api.users.knowledge import load_user_knowledge

        u = load_user_knowledge()
        mapping = {
            "embedding_model": "embedding_model",
            "dimension": "embedding_dimension",
            "chunk_size": "chunk_size",
            "chunk_overlap": "chunk_overlap",
            "default_top_k": "default_top_k",
            "retrieval_mode": "default_mode",
        }
        out = {}
        for user_key, kb_key in mapping.items():
            if user_key in u and u[user_key] is not None:
                out[kb_key] = u[user_key]
        return out
    except Exception as e:
        logger.debug(f"load user knowledge defaults failed, using KB defaults: {e}")
        return {}


def _ensure_default_base(manager: KnowledgeBaseManager):
    """Ensure a default knowledge base exists

    Args:
        manager: Knowledge base manager instance
    """
    try:
        default_base = manager.get_default_base()

        if default_base is None:
            # Create default knowledge base
            from dawei.knowledge.base_models import KnowledgeBaseCreate, KnowledgeBaseSettings

            create_data = KnowledgeBaseCreate(
                name="默认知识库",
                description="系统默认知识库,用于存储通用文档",
                is_default=True,
                # 用用户级 knowledge 默认（configs/knowledge.json）作为引擎参数模板；
                # 失败回退 KnowledgeBaseSettings() 硬编码默认。仅影响新建 KB。
                settings=_user_knowledge_settings(),
            )

            default_base = manager.create_base(create_data)
            logger.info(f"Created default knowledge base: {default_base.id}")
        else:
            logger.info(f"Default knowledge base exists: {default_base.id}")

    except Exception as e:
        logger.error(f"Failed to ensure default base exists", exc_info=True)
        raise  # Re-raise to see the full stack trace


def get_knowledge_base_manager() -> KnowledgeBaseManager:
    """Get the knowledge base manager from dependency container

    Returns:
        KnowledgeBaseManager instance

    Raises:
        ValueError: If manager not initialized
    """
    try:
        return DEPENDENCY_CONTAINER.get_service("knowledge_base_manager")
    except ValueError:
        # Try to initialize if not registered
        return initialize_knowledge_base_manager()
