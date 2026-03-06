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


def _ensure_default_base(manager: KnowledgeBaseManager):
    """Ensure a default knowledge base exists

    Args:
        manager: Knowledge base manager instance
    """
    try:
        default_base = manager.get_default_base()

        if default_base is None:
            # Create default knowledge base
            from dawei.knowledge.base_models import KnowledgeBaseCreate

            create_data = KnowledgeBaseCreate(
                name="默认知识库",
                description="系统默认知识库,用于存储通用文档",
                is_default=True,
                # Provide empty settings dict instead of KnowledgeBaseSettings object
                settings={}
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
