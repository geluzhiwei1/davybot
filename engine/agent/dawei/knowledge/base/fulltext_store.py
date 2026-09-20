# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Abstract base class for full-text search storage"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any

from dawei.knowledge.models import DocumentChunk


class FullTextStore(ABC):
    """Abstract base class for full-text search

    Implementations:
    - SQLiteFTSStore: Personal/team edition (SQLite FTS5)
    - PostgresFTSStore: Team edition (PostgreSQL FTS)
    - ElasticsearchStore: Enterprise edition (Elasticsearch/OpenSearch)
    """

    def __init__(self, **kwargs):
        """Initialize full-text store

        Args:
            **kwargs: Implementation-specific parameters
        """
        self.config = kwargs

    @abstractmethod
    async def add_documents(self, chunks: List[DocumentChunk]) -> None:
        """Add document chunks to full-text index

        Args:
            chunks: Document chunks to index
        """
        pass

    @abstractmethod
    async def search(
        self,
        query: str,
        top_k: int = 5,
        filters: Dict[str, Any] | None = None,
    ) -> List[tuple[str, float]]:
        """Search documents by text query

        Args:
            query: Search query
            top_k: Number of results to return
            filters: Optional metadata filters

        Returns:
            List of (chunk_id, score) tuples
        """
        pass

    @abstractmethod
    async def delete_document(self, document_id: str) -> int:
        """Delete all chunks for a document

        Args:
            document_id: Document ID

        Returns:
            Number of chunks deleted
        """
        pass

    @abstractmethod
    async def get_chunk(self, chunk_id: str) -> DocumentChunk | None:
        """Get a chunk by ID

        Args:
            chunk_id: Chunk ID

        Returns:
            Document chunk if found, None otherwise
        """
        pass

    @abstractmethod
    async def update_chunk(self, chunk_id: str, chunk: DocumentChunk) -> bool:
        """Update a chunk

        Args:
            chunk_id: Chunk ID to update
            chunk: New chunk data

        Returns:
            True if updated, False if not found
        """
        pass

    @abstractmethod
    async def count(self) -> int:
        """Get total number of chunks

        Returns:
            Total chunk count
        """
        pass

    @abstractmethod
    async def clear(self) -> None:
        """Clear all chunks from index"""
        pass

    async def health_check(self) -> bool:
        """Check if full-text store is healthy

        Returns:
            True if healthy, False otherwise
        """
        try:
            await self.count()
            return True
        except Exception:
            return False
