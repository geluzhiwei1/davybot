# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Knowledge Base Manager - Multi-tenancy support for knowledge bases"""

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any
from uuid import uuid4

from pydantic import ValidationError

from dawei.knowledge.base_models import (
    KnowledgeBase,
    KnowledgeBaseCreate,
    KnowledgeBaseUpdate,
    KnowledgeBaseStatus,
    KnowledgeBaseSettings,
    KnowledgeBaseListResponse,
)

logger = logging.getLogger(__name__)


class KnowledgeBaseManager:
    """Manages multiple knowledge bases with isolation and configuration"""

    def __init__(self, root_path: str | Path):
        """Initialize knowledge base manager

        Args:
            root_path: Root directory for knowledge bases storage
        """
        self.root_path = Path(root_path)
        self.root_path.mkdir(parents=True, exist_ok=True)

        # Metadata storage
        self.metadata_file = self.root_path / "bases_metadata.json"
        self.bases_dir = self.root_path / "bases"
        self.bases_dir.mkdir(exist_ok=True)

        # In-memory cache
        self._bases_cache: Dict[str, KnowledgeBase] = {}
        self._default_base_id: Optional[str] = None

        # Embedding manager cache (reuse HTTP clients)
        self._embedding_managers: Dict[str, Any] = {}

        # Load existing bases
        self._load_metadata()

    def _load_metadata(self):
        """Load knowledge bases metadata from disk"""
        if not self.metadata_file.exists():
            logger.info("No existing knowledge bases metadata found")
            return

        try:
            with open(self.metadata_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            for base_data in data.get('bases', []):
                try:
                    kb = KnowledgeBase(**base_data)
                    self._bases_cache[kb.id] = kb
                    if kb.is_default:
                        self._default_base_id = kb.id
                except ValidationError as e:
                    logger.error(f"Failed to load knowledge base: {e}")

            logger.info(f"Loaded {len(self._bases_cache)} knowledge bases")

        except Exception as e:
            logger.error(f"Failed to load knowledge bases metadata: {e}")

    def _save_metadata(self):
        """Save knowledge bases metadata to disk"""
        try:
            data = {
                'version': '1.0',
                'updated_at': datetime.now().isoformat(),
                'bases': [kb.model_dump(mode='json') for kb in self._bases_cache.values()]
            }

            with open(self.metadata_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            logger.debug("Saved knowledge bases metadata")

        except Exception as e:
            logger.error(f"Failed to save knowledge bases metadata: {e}")
            raise

    def _get_storage_path(self, base_id: str) -> Path:
        """Get storage path for a knowledge base"""
        return self.bases_dir / base_id

    def create_base(self, create_data: KnowledgeBaseCreate) -> KnowledgeBase:
        """Create a new knowledge base

        Args:
            create_data: Knowledge base creation data

        Returns:
            Created knowledge base

        Raises:
            ValueError: If default base already exists
        """
        # Check if this should be default
        if create_data.is_default and self._default_base_id:
            raise ValueError(f"Default knowledge base already exists: {self._default_base_id}")

        # Generate unique ID
        base_id = f"kb_{uuid4().hex[:8]}"

        # Create storage directory
        storage_path = self._get_storage_path(base_id)
        storage_path.mkdir(parents=True, exist_ok=True)

        # Create subdirectories
        (storage_path / "documents").mkdir(exist_ok=True)
        (storage_path / "vectors").mkdir(exist_ok=True)
        (storage_path / "graph").mkdir(exist_ok=True)
        (storage_path / "fulltext").mkdir(exist_ok=True)

        # Create knowledge base
        kb = KnowledgeBase(
            id=base_id,
            name=create_data.name,
            description=create_data.description,
            settings=create_data.settings or KnowledgeBaseSettings(),
            workspace_id=create_data.workspace_id,
            tags=create_data.tags,
            is_default=create_data.is_default,
            storage_path=f"bases/{base_id}/",
        )

        # Save to cache and disk
        self._bases_cache[base_id] = kb
        if kb.is_default:
            self._default_base_id = base_id

        self._save_metadata()

        logger.info(f"Created knowledge base: {base_id} - {kb.name}")
        return kb

    def get_base(self, base_id: str) -> Optional[KnowledgeBase]:
        """Get knowledge base by ID

        Args:
            base_id: Knowledge base ID

        Returns:
            Knowledge base or None if not found
        """
        return self._bases_cache.get(base_id)

    def get_default_base(self) -> Optional[KnowledgeBase]:
        """Get default knowledge base

        Returns:
            Default knowledge base or None
        """
        if self._default_base_id:
            return self._bases_cache.get(self._default_base_id)
        return None

    def list_bases(
        self,
        workspace_id: Optional[str] = None,
        status: Optional[KnowledgeBaseStatus] = None,
    ) -> KnowledgeBaseListResponse:
        """List all knowledge bases

        Args:
            workspace_id: Filter by workspace ID
            status: Filter by status

        Returns:
            List of knowledge bases
        """
        bases = list(self._bases_cache.values())

        # Apply filters
        if workspace_id:
            bases = [b for b in bases if b.workspace_id == workspace_id]
        if status:
            bases = [b for b in bases if b.status == status]

        # Sort by updated_at (newest first)
        bases.sort(key=lambda b: b.updated_at, reverse=True)

        return KnowledgeBaseListResponse(
            total=len(bases),
            items=bases,
            default_base_id=self._default_base_id,
        )

    def update_base(self, base_id: str, update_data: KnowledgeBaseUpdate) -> Optional[KnowledgeBase]:
        """Update knowledge base

        Args:
            base_id: Knowledge base ID
            update_data: Update data

        Returns:
            Updated knowledge base or None if not found
        """
        kb = self._bases_cache.get(base_id)
        if not kb:
            return None

        # Update fields
        if update_data.name is not None:
            kb.name = update_data.name
        if update_data.description is not None:
            kb.description = update_data.description
        if update_data.settings is not None:
            kb.settings = update_data.settings
        if update_data.tags is not None:
            kb.tags = update_data.tags
        if update_data.status is not None:
            kb.status = update_data.status

        kb.updated_at = datetime.now()

        # Save to disk
        self._save_metadata()

        logger.info(f"Updated knowledge base: {base_id}")
        return kb

    def set_default_base(self, base_id: str) -> Optional[KnowledgeBase]:
        """Set default knowledge base

        Args:
            base_id: Knowledge base ID

        Returns:
            Updated knowledge base or None if not found
        """
        kb = self._bases_cache.get(base_id)
        if not kb:
            return None

        # Unset current default
        if self._default_base_id and self._default_base_id in self._bases_cache:
            self._bases_cache[self._default_base_id].is_default = False

        # Set new default
        kb.is_default = True
        self._default_base_id = base_id
        kb.updated_at = datetime.now()

        # Save to disk
        self._save_metadata()

        logger.info(f"Set default knowledge base: {base_id}")
        return kb

    def delete_base(self, base_id: str, force: bool = False) -> bool:
        """Delete knowledge base

        Args:
            base_id: Knowledge base ID
            force: Force deletion even if it has documents

        Returns:
            True if deleted, False if not found or cannot delete

        Raises:
            ValueError: If trying to delete default base or base has documents
        """
        kb = self._bases_cache.get(base_id)
        if not kb:
            return False

        # Prevent deleting default base
        if kb.is_default:
            raise ValueError("Cannot delete default knowledge base")

        # Check if base has documents
        if not force and kb.stats.total_documents > 0:
            raise ValueError(f"Cannot delete knowledge base with {kb.stats.total_documents} documents. Use force=True to override.")

        # Mark as deleting
        kb.status = KnowledgeBaseStatus.DELETING
        self._save_metadata()

        # Delete storage directory
        storage_path = self._get_storage_path(base_id)
        if storage_path.exists():
            shutil.rmtree(storage_path)

        # Remove from cache
        del self._bases_cache[base_id]
        self._save_metadata()

        logger.info(f"Deleted knowledge base: {base_id}")
        return True

    def get_base_storage_path(self, base_id: str) -> Optional[Path]:
        """Get storage path for knowledge base

        Args:
            base_id: Knowledge base ID

        Returns:
            Storage path or None if not found
        """
        if base_id not in self._bases_cache:
            return None
        return self._get_storage_path(base_id)

    def update_base_stats(self, base_id: str, stats_update: Dict[str, Any]):
        """Update knowledge base statistics

        Args:
            base_id: Knowledge base ID
            stats_update: Statistics to update
        """
        kb = self._bases_cache.get(base_id)
        if not kb:
            return

        # Update stats
        for key, value in stats_update.items():
            if hasattr(kb.stats, key):
                setattr(kb.stats, key, value)

        kb.stats.last_updated_at = datetime.now()
        kb.updated_at = datetime.now()

        # Save to disk
        self._save_metadata()

    def get_embedding_manager(self, base_id: str, model_type: str = "MINILM"):
        """Get or create embedding manager for a knowledge base

        Args:
            base_id: Knowledge base ID
            model_type: Embedding model type (MINILM, BGE_M3, etc.)

        Returns:
            EmbeddingService instance
        """
        # Create cache key
        cache_key = f"{base_id}_{model_type}"

        # Return cached manager if exists
        if cache_key in self._embedding_managers:
            return self._embedding_managers[cache_key]

        # Create new embedding manager
        from dawei.knowledge.embeddings.manager import (
            EmbeddingManager,
            EmbeddingModelType,
            EmbeddingService,
        )

        # Map string to enum
        model_type_map = {
            "MINILM": EmbeddingModelType.MINILM,
            "BGE_M3": EmbeddingModelType.BGE_M3,
            "BGE_LARGE": EmbeddingModelType.BGE_LARGE,
            "JINA_V4": EmbeddingModelType.JINA_V4,
        }

        embedding_model_type = model_type_map.get(model_type, EmbeddingModelType.MINILM)

        # Get storage path for this knowledge base
        storage_path = self._get_storage_path(base_id)
        cache_dir = storage_path / "embeddings"

        # Create embedding manager and service
        embedding_manager = EmbeddingManager(
            model_type=embedding_model_type,
            cache_dir=str(cache_dir),
        )
        embedding_service = EmbeddingService(embedding_manager)

        # Cache it
        self._embedding_managers[cache_key] = embedding_service

        logger.info(f"Created new embedding manager for {base_id} with model {model_type}")
        return embedding_service

    def list_base_documents(
        self, base_id: str, skip: int = 0, limit: int = 10
    ) -> Dict[str, Any]:
        """List documents in a knowledge base

        Args:
            base_id: Knowledge base ID
            skip: Number of documents to skip
            limit: Maximum number of documents to return

        Returns:
            Dictionary with documents list and total count
        """
        import sqlite3

        kb = self.get_base(base_id)
        if not kb:
            raise ValueError(f"Knowledge base not found: {base_id}")

        # Get vector database path for this knowledge base
        base_storage_path = self._get_storage_path(base_id)
        vector_db_path = base_storage_path / "vectors.db"

        if not vector_db_path.exists():
            # No vector database means no documents uploaded yet
            return {"documents": [], "total": 0, "skip": skip, "limit": limit}

        # Query vector database to get unique document IDs
        documents_dict = {}  # Use dict to deduplicate by document_id

        try:
            # Synchronous query to get documents
            with sqlite3.connect(str(vector_db_path)) as db:
                cursor = db.cursor()
                # Get distinct documents with their metadata
                query = """
                    SELECT DISTINCT
                        json_extract(metadata, '$.document_id') as document_id,
                        json_extract(metadata, '$.file_name') as file_name,
                        json_extract(metadata, '$.chunk_index') as chunk_index,
                        MIN(json_extract(metadata, '$.file_size')) as file_size
                    FROM vectors
                    GROUP BY json_extract(metadata, '$.document_id')
                    ORDER BY MIN(rowid) DESC
                """
                cursor.execute(query)
                rows = cursor.fetchall()

                for row in rows:
                    document_id, file_name, chunk_index, file_size = row
                    if document_id and file_name:
                        # Get file stats from uploads directory if available
                        uploads_dir = base_storage_path / "uploads"
                        uploaded_at = None
                        if uploads_dir.exists():
                            file_path = uploads_dir / file_name
                            if file_path.exists():
                                stat = file_path.stat()
                                uploaded_at = stat.st_mtime

                        documents_dict[document_id] = {
                            "id": document_id,  # Use actual document ID from vector DB
                            "file_name": file_name,
                            "file_size": file_size or 0,
                            "uploaded_at": uploaded_at or 0,
                            "file_path": f"uploads/{file_name}",
                        }
        except Exception as e:
            logger.warning(f"Failed to query documents from vector database: {e}")
            # Fall back to empty list
            return {"documents": [], "total": 0, "skip": skip, "limit": limit}

        # Convert to list and sort
        documents = list(documents_dict.values())
        documents.sort(key=lambda x: x["uploaded_at"], reverse=True)

        # Apply pagination
        total = len(documents)
        paginated_documents = documents[skip : skip + limit]

        return {
            "documents": paginated_documents,
            "total": total,
            "skip": skip,
            "limit": limit,
        }

    def cleanup_embedding_managers(self):
        """Clean up all embedding managers

        Call this during shutdown to properly release resources.
        """
        for cache_key, service in self._embedding_managers.items():
            try:
                # Clean up the underlying manager
                if hasattr(service, 'manager'):
                    manager = service.manager
                    if hasattr(manager, '_model') and manager._model is not None:
                        del manager._model
                        logger.debug(f"Cleaned up embedding manager: {cache_key}")
            except Exception as e:
                logger.warning(f"Failed to cleanup embedding manager {cache_key}: {e}")

        self._embedding_managers.clear()
        logger.info("All embedding managers cleaned up")
