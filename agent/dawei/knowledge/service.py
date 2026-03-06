# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Knowledge service - High-level interface for knowledge base operations

This service provides a unified interface for the Agent to interact with
the knowledge base system, integrating document management, vector search,
and RAG capabilities.
"""

import logging
from pathlib import Path
from typing import List, Dict, Any

from dawei.knowledge.chunking.chunker import ChunkingConfig, ChunkingStrategy, TextChunker
from dawei.knowledge.embeddings.manager import EmbeddingManager, EmbeddingModelType, EmbeddingService
from dawei.knowledge.models import (
    Document,
    DocumentMetadata,
    DocumentType,
    RetrievalMode,
    RetrievalQuery,
    RetrievalResult,
)
from dawei.knowledge.parsers.base import BaseParser
from dawei.knowledge.parsers.docx_parser import DocxParser
from dawei.knowledge.parsers.markdown_parser import MarkdownParser
from dawei.knowledge.parsers.pdf_parser import PDFParser
from dawei.knowledge.parsers.text_parser import TextParser
from dawei.knowledge.retrieval.hybrid_retriever import HybridRetriever
from dawei.knowledge.retrieval.rag_pipeline import RAGPipeline
from dawei.knowledge.vector.sqlite_vec_store import SQLiteVecVectorStore

logger = logging.getLogger(__name__)


class KnowledgeService:
    """Knowledge service - Main interface for knowledge base operations

    This service integrates all knowledge base components:
    - Document parsing and chunking
    - Embedding generation
    - Vector storage
    - Hybrid retrieval
    - RAG pipeline

    Usage:
        service = KnowledgeService(workspace_id="my-workspace")
        await service.initialize()

        # Add document
        doc_info = await service.add_document("path/to/file.pdf")

        # Search
        results = await service.search_knowledge("query text")

        # RAG query
        rag_result = await service.query_with_context("query")
    """

    def __init__(
        self,
        workspace_id: str,
        config: Any | None = None,
    ):
        """Initialize knowledge service

        Args:
            workspace_id: Workspace identifier
            config: Knowledge configuration (optional)
        """
        self.workspace_id = workspace_id
        self.config = config or self._default_config()

        # Component placeholders (initialized in initialize())
        self.vector_store: SQLiteVecVectorStore | None = None
        self.embedding_manager: EmbeddingManager | None = None
        self.embedding_service: EmbeddingService | None = None
        self.retriever: HybridRetriever | None = None
        self.rag_pipeline: RAGPipeline | None = None

        # Parsers
        self.parsers: Dict[str, BaseParser] = {}

        # Chunker
        self.chunker: TextChunker | None = None

        logger.info(f"Knowledge service created for workspace: {workspace_id}")

    def _default_config(self) -> Dict[str, Any]:
        """Get default configuration

        Returns:
            Default configuration dictionary
        """
        return {
            "vector_store": {
                "type": "sqlite-vec",
                "db_path": f"./data/workspaces/{self.workspace_id}/knowledge_vectors.db",
                "dimension": 384,
            },
            "embedding": {
                "model": EmbeddingModelType.MINILM,
                "cache_dir": "./data/embeddings",
                "device": "cpu",
            },
            "chunking": {
                "strategy": ChunkingStrategy.RECURSIVE,
                "chunk_size": 512,
                "chunk_overlap": 50,
            },
            "retrieval": {
                "default_mode": RetrievalMode.HYBRID,
                "default_top_k": 5,
                "vector_weight": 0.5,
                "graph_weight": 0.3,
                "fulltext_weight": 0.2,
            },
        }

    async def initialize(self) -> None:
        """Initialize knowledge service components

        This method must be called before using the service.
        """
        logger.info("Initializing knowledge service...")

        # Initialize vector store
        vector_config = self.config["vector_store"]
        self.vector_store = SQLiteVecVectorStore(
            db_path=vector_config["db_path"],
            dimension=vector_config["dimension"],
        )
        await self.vector_store.initialize()
        logger.info(f"Vector store initialized: {vector_config['db_path']}")

        # Initialize embedding manager
        embedding_config = self.config["embedding"]
        self.embedding_manager = EmbeddingManager(
            model_type=embedding_config["model"],
            cache_dir=embedding_config["cache_dir"],
            device=embedding_config["device"],
        )
        self.embedding_service = EmbeddingService(self.embedding_manager)
        logger.info(f"Embedding manager initialized: {embedding_config['model']}")

        # Initialize retriever
        self.retriever = HybridRetriever(
            vector_store=self.vector_store,
            embedding_manager=self.embedding_manager,
        )
        logger.info("Hybrid retriever initialized")

        # Initialize RAG pipeline
        self.rag_pipeline = RAGPipeline(
            retriever=self.retriever,
            embedding_service=self.embedding_service,
        )
        logger.info("RAG pipeline initialized")

        # Initialize parsers
        self.parsers = {
            "pdf": PDFParser(),
            "docx": DocxParser(),
            "markdown": MarkdownParser(),
            "md": MarkdownParser(),
            "txt": TextParser(),
            "text": TextParser(),
        }
        logger.info(f"Parsers initialized: {list(self.parsers.keys())}")

        # Initialize chunker
        chunking_config = self.config["chunking"]
        self.chunker = TextChunker(
            config=ChunkingConfig(
                strategy=chunking_config["strategy"],
                chunk_size=chunking_config["chunk_size"],
                chunk_overlap=chunking_config["chunk_overlap"],
            ),
        )
        logger.info(f"Chunker initialized: {chunking_config['strategy']}")

        logger.info("Knowledge service initialization complete")

    async def search_knowledge(
        self,
        query: str,
        mode: RetrievalMode = RetrievalMode.HYBRID,
        top_k: int = 5,
    ) -> List[RetrievalResult]:
        """Search knowledge base

        Args:
            query: Search query
            mode: Retrieval mode
            top_k: Number of results

        Returns:
            List of search results
        """
        if self.retriever is None:
            raise RuntimeError("Knowledge service not initialized. Call initialize() first.")

        retrieval_query = RetrievalQuery(
            query=query,
            mode=mode,
            top_k=top_k,
        )

        result = await self.retriever.retrieve(retrieval_query)
        return result.results

    async def query_with_context(
        self,
        query: str,
        max_context_length: int = 4000,
    ) -> Dict[str, Any]:
        """Query knowledge base with RAG context

        Args:
            query: Query string
            max_context_length: Maximum context length

        Returns:
            Dictionary with context, sources, citations
        """
        if self.rag_pipeline is None:
            raise RuntimeError("Knowledge service not initialized. Call initialize() first.")

        return await self.rag_pipeline.retrieve_and_build_context(
            query=query,
            max_context_length=max_context_length,
        )

    async def add_document(
        self,
        file_path: str,
    ) -> DocumentMetadata:
        """Add document to knowledge base

        Args:
            file_path: Path to document file

        Returns:
            Document metadata
        """
        if self.vector_store is None or self.embedding_service is None or self.chunker is None:
            raise RuntimeError("Knowledge service not initialized. Call initialize() first.")

        logger.info(f"Adding document: {file_path}")

        # Get file extension
        path = Path(file_path)
        ext = path.suffix.lstrip(".").lower()

        # Get parser
        parser = self.parsers.get(ext)
        if parser is None:
            raise ValueError(f"Unsupported file type: {ext}. Supported types: {list(self.parsers.keys())}")

        # Parse document
        document = await parser.parse(str(path))
        logger.info(f"Document parsed: {len(document.content)} characters")

        # Chunk document
        chunks = await self.chunker.chunk(document)
        logger.info(f"Document chunked: {len(chunks)} chunks")

        # Generate embeddings
        chunk_texts = [chunk.content for chunk in chunks]
        embeddings = await self.embedding_service.embed_batch(chunk_texts)
        logger.info(f"Embeddings generated: {len(embeddings)} vectors")

        # Add to vector store
        from dawei.knowledge.models import VectorDocument

        vector_docs = []
        for chunk, embedding in zip(chunks, embeddings):
            vector_doc = VectorDocument(
                id=chunk.id,
                embedding=embedding,
                metadata={
                    **chunk.metadata,
                    "document_id": chunk.document_id,
                    "chunk_index": chunk.chunk_index,
                },
                content=chunk.content,
            )
            vector_docs.append(vector_doc)

        await self.vector_store.add(vector_docs)
        logger.info(f"Document indexed: {len(vector_docs)} vectors added")

        # Update indexed timestamp
        document.metadata.indexed_at = document.metadata.updated_at

        return document.metadata

    async def delete_document(
        self,
        document_id: str,
    ) -> bool:
        """Delete document from knowledge base

        Args:
            document_id: Document ID

        Returns:
            True if deleted successfully
        """
        if self.vector_store is None:
            raise RuntimeError("Knowledge service not initialized. Call initialize() first.")

        logger.info(f"Deleting document: {document_id}")

        # Delete all chunks for this document
        chunk_ids = [f"{document_id}_chunk_{i}" for i in range(10000)]  # Broad range

        deleted = await self.vector_store.delete(chunk_ids)

        logger.info(f"Document deleted: {deleted} chunks removed")
        return deleted > 0

    async def reindex_document(
        self,
        document_id: str,
    ) -> bool:
        """Reindex document

        Args:
            document_id: Document ID

        Returns:
            True if reindexed successfully
        """
        # TODO: Implement reindexing
        # For now, just return True
        logger.info(f"Reindexing document: {document_id}")
        return True

    async def list_documents(
        self,
        limit: int = 20,
        skip: int = 0,
    ) -> List[Document]:
        """List documents in knowledge base

        Args:
            limit: Maximum documents to return
            skip: Number of documents to skip

        Returns:
            List of documents
        """
        # TODO: Implement document listing
        # For now, return empty list
        logger.info(f"Listing documents: limit={limit}, skip={skip}")
        return []

    async def get_stats(self) -> Dict[str, Any]:
        """Get knowledge base statistics

        Returns:
            Statistics dictionary
        """
        if self.vector_store is None:
            raise RuntimeError("Knowledge service not initialized. Call initialize() first.")

        count = await self.vector_store.count()

        return {
            "total_documents": 0,  # TODO: Implement document counting
            "total_chunks": count,
            "total_entities": 0,  # TODO: Implement graph entity counting
            "avg_relevance": 0.0,  # TODO: Implement relevance tracking
            "last_indexed": None,
        }

    async def health_check(self) -> Dict[str, Any]:
        """Check knowledge base health

        Returns:
            Health status dictionary
        """
        is_healthy = (
            self.vector_store is not None
            and self.embedding_manager is not None
            and self.retriever is not None
            and self.rag_pipeline is not None
        )

        return {
            "healthy": is_healthy,
            "workspace_id": self.workspace_id,
            "vector_store_type": "sqlite-vec",
            "embedding_model": str(self.config["embedding"]["model"]) if self.embedding_manager else None,
        }
