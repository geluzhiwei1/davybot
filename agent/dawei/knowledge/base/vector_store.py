# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Abstract base class for vector storage implementations"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any

from dawei.knowledge.models import VectorDocument, VectorSearchResult


class VectorStore(ABC):
    """Abstract base class for vector storage

    Implementations:
    - SQLiteVecVectorStore: Personal edition (sqlite-vec)
    - PGVectorVectorStore: Team edition (PostgreSQL + pgvector)
    - QdrantVectorStore: Enterprise edition (Qdrant)
    """

    def __init__(self, dimension: int, **kwargs):
        """Initialize vector store

        Args:
            dimension: Embedding dimension
            **kwargs: Additional implementation-specific parameters
        """
        self.dimension = dimension
        self.config = kwargs

    @abstractmethod
    async def add(self, documents: List[VectorDocument]) -> None:
        """Add documents to vector store

        Args:
            documents: List of documents with embeddings
        """
        pass

    @abstractmethod
    async def delete(self, document_ids: List[str]) -> int:
        """Delete documents from vector store

        Args:
            document_ids: List of document IDs to delete

        Returns:
            Number of documents deleted
        """
        pass

    @abstractmethod
    async def search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        filters: Dict[str, Any] | None = None,
        min_score: float = 0.0,
    ) -> List[VectorSearchResult]:
        """Search for similar documents

        Args:
            query_embedding: Query vector
            top_k: Number of results to return
            filters: Optional metadata filters
            min_score: Minimum similarity score

        Returns:
            List of search results ranked by similarity
        """
        pass

    @abstractmethod
    async def update(self, document_id: str, document: VectorDocument) -> bool:
        """Update a document in the vector store

        Args:
            document_id: Document ID to update
            document: New document data

        Returns:
            True if updated, False if not found
        """
        pass

    @abstractmethod
    async def get(self, document_id: str) -> VectorDocument | None:
        """Get a document by ID

        Args:
            document_id: Document ID

        Returns:
            Document if found, None otherwise
        """
        pass

    @abstractmethod
    async def count(self) -> int:
        """Get total number of documents in store

        Returns:
            Total document count
        """
        pass

    @abstractmethod
    async def clear(self) -> None:
        """Clear all documents from store"""
        pass

    @abstractmethod
    async def create_index(self, index_type: str = "HNSW", **params) -> None:
        """Create index for faster searches

        Args:
            index_type: Type of index (HNSW, IVF, FLAT, etc.)
            **params: Index-specific parameters
        """
        pass

    async def health_check(self) -> bool:
        """Check if vector store is healthy

        Returns:
            True if healthy, False otherwise
        """
        try:
            await self.count()
            return True
        except Exception:
            return False
