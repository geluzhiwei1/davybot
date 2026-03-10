# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Knowledge Base models for multi-tenancy support"""

from datetime import datetime
from typing import List, Dict, Any, Optional
from enum import Enum

from pydantic import BaseModel, Field


class KnowledgeBaseStatus(str, Enum):
    """Knowledge base status"""

    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETING = "deleting"


class KnowledgeBaseSettings(BaseModel):
    """Knowledge base configuration settings"""

    # Chunking settings
    chunk_size: int = Field(default=1000, ge=100, le=10000)
    chunk_overlap: int = Field(default=200, ge=0, le=1000)
    chunk_strategy: str = Field(default="recursive")

    # Embedding settings
    embedding_model: str = Field(default="minilm")
    embedding_dimension: int = Field(default=384)

    # Retrieval settings
    default_top_k: int = Field(default=5, ge=1, le=50)
    default_mode: str = Field(default="hybrid")

    # Hybrid search weights
    vector_weight: float = Field(default=0.5, ge=0.0, le=1.0)
    graph_weight: float = Field(default=0.3, ge=0.0, le=1.0)
    fulltext_weight: float = Field(default=0.2, ge=0.0, le=1.0)

    # Knowledge extraction settings
    extraction_strategy: str = Field(default="rule_based", description="Entity/relation extraction strategy: rule_based, llm, ner_model, auto")

    # Advanced settings
    enable_graph: bool = True
    enable_fulltext: bool = True
    auto_reindex: bool = False


class KnowledgeBaseStats(BaseModel):
    """Knowledge base statistics"""

    total_documents: int = 0
    total_chunks: int = 0
    total_entities: int = 0
    total_relations: int = 0
    indexed_documents: int = 0
    storage_size_bytes: int = 0
    last_indexed_at: Optional[datetime] = None
    last_updated_at: Optional[datetime] = Field(default_factory=datetime.now)


class KnowledgeBase(BaseModel):
    """Knowledge base metadata"""

    id: str
    name: str
    description: str = ""
    status: KnowledgeBaseStatus = KnowledgeBaseStatus.ACTIVE
    settings: KnowledgeBaseSettings = Field(default_factory=KnowledgeBaseSettings)
    stats: KnowledgeBaseStats = Field(default_factory=KnowledgeBaseStats)

    # Metadata
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    created_by: str = "system"

    # Organization
    workspace_id: Optional[str] = None  # Link to workspace if applicable
    tags: List[str] = Field(default_factory=list)

    # Default flag
    is_default: bool = False

    # Storage paths (relative to knowledge root)
    storage_path: str  # e.g., "bases/kb_001/"

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class KnowledgeBaseCreate(BaseModel):
    """Request model for creating a knowledge base"""

    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    settings: Optional[KnowledgeBaseSettings] = None
    workspace_id: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    is_default: bool = False


class KnowledgeBaseUpdate(BaseModel):
    """Request model for updating a knowledge base"""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    settings: Optional[KnowledgeBaseSettings] = None
    tags: Optional[List[str]] = None
    status: Optional[KnowledgeBaseStatus] = None


class KnowledgeBaseListResponse(BaseModel):
    """Response model for listing knowledge bases"""

    total: int
    items: List[KnowledgeBase]
    default_base_id: Optional[str] = None


class KnowledgeBaseDocumentUpload(BaseModel):
    """Document upload with knowledge base context"""

    base_id: str
    file_path: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class KnowledgeSearchWithBase(BaseModel):
    """Search request with knowledge base specification"""

    query: str
    base_id: Optional[str] = None  # None = use default base
    mode: str = "hybrid"
    top_k: int = 5
    filters: Dict[str, Any] = Field(default_factory=dict)
    min_score: float = 0.0
