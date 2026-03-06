# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Core data models for Knowledge Base & RAG System"""

from datetime import datetime
from enum import Enum
from typing import List, Dict, Any

from pydantic import BaseModel, Field


# ============================================================================
# Enums
# ============================================================================

class DocumentType(str, Enum):
    """Document type enumeration"""

    TEXT = "text"
    PDF = "pdf"
    DOCX = "docx"
    MARKDOWN = "markdown"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    TABLE = "table"
    CODE = "code"


class ChunkType(str, Enum):
    """Chunk type enumeration"""

    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    TABLE = "table"
    CODE = "code"


class EmbeddingModelType(str, Enum):
    """Embedding model type"""

    # Text models
    MINILM = "sentence-transformers/all-MiniLM-L6-v2"
    BGE_M3 = "BAAI/bge-m3"
    BGE_LARGE = "BAAI/bge-large-zh-v1.5"
    JINA_V4 = "jina-embeddings-v4"
    OPENAI_ADA = "text-embedding-3-large"

    # Image models
    CLIP = "openai/clip-vit-base-patch32"
    SIGLIP_2 = "siglip-2-large"

    # Multi-modal models
    COLQWEN2 = "colqwen2"


class VectorStoreType(str, Enum):
    """Vector store type"""

    SQLITE_VEC = "sqlite-vec"
    PGVECTOR = "pgvector"
    QDRANT = "qdrant"


class GraphStoreType(str, Enum):
    """Graph store type"""

    SQLITE = "sqlite"
    NEO4J = "neo4j"


class RetrievalMode(str, Enum):
    """Retrieval mode"""

    VECTOR = "vector"
    GRAPH = "graph"
    FULLTEXT = "fulltext"
    HYBRID = "hybrid"


# ============================================================================
# Document Models
# ============================================================================

class DocumentMetadata(BaseModel):
    """Document metadata"""

    file_path: str
    file_name: str
    file_size: int
    file_type: DocumentType
    sha256: str
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    indexed_at: datetime | None = None
    author: str | None = None
    title: str | None = None
    tags: List[str] = Field(default_factory=list)
    language: str | None = None
    page_count: int | None = None
    chunk_count: int = 0
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Document(BaseModel):
    """Document representation"""

    id: str
    metadata: DocumentMetadata
    content: str | None = None


class DocumentChunk(BaseModel):
    """Document chunk for vector storage"""

    id: str
    document_id: str
    chunk_index: int
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    embedding: List[float] | None = None


class MultiModalChunk(BaseModel):
    """Multi-modal chunk supporting different content types"""

    id: str
    document_id: str
    chunk_index: int
    chunk_type: ChunkType
    content: str
    embedding: List[float] | None = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    # Multi-modal specific fields
    image_data: bytes | None = None
    audio_data: bytes | None = None
    video_data: bytes | None = None
    table_data: Dict[str, Any] | None = None
    code_data: Dict[str, Any] | None = None


# ============================================================================
# Knowledge Graph Models
# ============================================================================

class GraphEntity(BaseModel):
    """Knowledge graph entity/node"""

    id: str
    type: str
    name: str
    properties: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)


class GraphRelation(BaseModel):
    """Knowledge graph relation/edge"""

    id: str
    from_entity: str
    to_entity: str
    relation_type: str
    properties: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)


class GraphPath(BaseModel):
    """Knowledge graph path (for multi-hop queries)"""

    entities: List[GraphEntity]
    relations: List[GraphRelation]
    score: float


# ============================================================================
# Vector Search Models
# ============================================================================

class VectorDocument(BaseModel):
    """Document with embedding for vector storage"""

    id: str
    embedding: List[float]
    metadata: Dict[str, Any] = Field(default_factory=dict)
    content: str


class VectorSearchResult(BaseModel):
    """Vector search result"""

    id: str
    score: float
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ============================================================================
# Retrieval Models
# ============================================================================

class RetrievalQuery(BaseModel):
    """Retrieval query"""

    query: str
    mode: RetrievalMode = RetrievalMode.HYBRID
    top_k: int = 5
    filters: Dict[str, Any] = Field(default_factory=dict)
    min_score: float = 0.0
    # Hybrid search weights
    vector_weight: float = 0.5
    graph_weight: float = 0.3
    fulltext_weight: float = 0.2


class RetrievalResult(BaseModel):
    """Single retrieval result"""

    id: str
    content: str
    score: float
    source: str  # "vector", "graph", or "fulltext"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class HybridSearchResult(BaseModel):
    """Hybrid search result combining multiple sources"""

    query: str
    results: List[RetrievalResult]
    total_count: int
    vector_count: int
    graph_count: int
    fulltext_count: int
    latency_ms: float
    reranked: bool = False


# ============================================================================
# Embedding Models
# ============================================================================

class EmbeddingRequest(BaseModel):
    """Embedding generation request"""

    texts: List[str]
    model: EmbeddingModelType = EmbeddingModelType.MINILM
    batch_size: int = 32
    normalize: bool = True


class EmbeddingResponse(BaseModel):
    """Embedding generation response"""

    embeddings: List[List[float]]
    model: str
    dimension: int
    total_tokens: int
    latency_ms: float


class EmbeddingModel(BaseModel):
    """Embedding model configuration"""

    name: str
    type: EmbeddingModelType
    dimension: int
    max_sequence_length: int
    supports_multilingual: bool = False
    modalities: List[ChunkType] = Field(default_factory=lambda: [ChunkType.TEXT])
