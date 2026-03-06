# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Dawei Knowledge Base & RAG System

A comprehensive knowledge management system with support for:
- Vector search (sqlite-vec, pgvector, Qdrant)
- Knowledge graphs (SQLite, Neo4j)
- Full-text search (BM25)
- Multi-modal content (text, images, audio, video, tables, code)
- Hybrid retrieval with RRF fusion
- Multi-tenancy (multiple knowledge bases)
"""

from dawei.knowledge.models import (
    # Document models
    Document,
    DocumentMetadata,
    DocumentChunk,
    MultiModalChunk,
    # Knowledge graph models
    GraphEntity,
    GraphRelation,
    GraphPath,
    # Vector models
    VectorDocument,
    VectorSearchResult,
    # Retrieval models
    RetrievalQuery,
    RetrievalResult,
    HybridSearchResult,
    # Embedding models
    EmbeddingModel,
    EmbeddingRequest,
    EmbeddingResponse,
)

from dawei.knowledge.base_models import (
    # Knowledge base models
    KnowledgeBase,
    KnowledgeBaseCreate,
    KnowledgeBaseUpdate,
    KnowledgeBaseSettings,
    KnowledgeBaseStats,
    KnowledgeBaseStatus,
    KnowledgeBaseListResponse,
    KnowledgeSearchWithBase,
)

from dawei.knowledge.base_manager import KnowledgeBaseManager

__all__ = [
    # Document models
    "Document",
    "DocumentMetadata",
    "DocumentChunk",
    "MultiModalChunk",
    # Knowledge graph models
    "GraphEntity",
    "GraphRelation",
    "GraphPath",
    # Vector models
    "VectorDocument",
    "VectorSearchResult",
    # Retrieval models
    "RetrievalQuery",
    "RetrievalResult",
    "HybridSearchResult",
    # Embedding models
    "EmbeddingModel",
    "EmbeddingRequest",
    "EmbeddingResponse",
    # Knowledge base models
    "KnowledgeBase",
    "KnowledgeBaseCreate",
    "KnowledgeBaseUpdate",
    "KnowledgeBaseSettings",
    "KnowledgeBaseStats",
    "KnowledgeBaseStatus",
    "KnowledgeBaseListResponse",
    "KnowledgeSearchWithBase",
    # Knowledge base manager
    "KnowledgeBaseManager",
]
