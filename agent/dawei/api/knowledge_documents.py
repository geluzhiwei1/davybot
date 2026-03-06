# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""FastAPI REST API endpoints for Knowledge Base system"""

import logging
from pathlib import Path
from typing import List, Dict, Any

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse

from dawei.knowledge.chunking.chunker import ChunkingConfig, ChunkingStrategy, TextChunker
from dawei.knowledge.embeddings.manager import EmbeddingManager, EmbeddingService
from dawei.knowledge.models import (
    Document,
    DocumentMetadata,
    DocumentType,
    EmbeddingModelType,
    RetrievalMode,
)
from dawei.knowledge.parsers.pdf_parser import PDFParser
from dawei.knowledge.retrieval.hybrid_retriever import HybridRetriever
from dawei.knowledge.retrieval.rag_pipeline import RAGPipeline
from dawei.knowledge.vector.sqlite_vec_store import SQLiteVecVectorStore

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

# Global instances (will be initialized with dependency injection in production)
_vector_store: SQLiteVecVectorStore | None = None
_embedding_manager: EmbeddingManager | None = None
_embedding_service: EmbeddingService | None = None
_retriever: HybridRetriever | None = None
_rag_pipeline: RAGPipeline | None = None


async def _ensure_initialized():
    """Ensure services are initialized"""
    global _vector_store, _embedding_manager, _embedding_service, _retriever, _rag_pipeline

    if _vector_store is None:
        # Initialize vector store (personal edition with SQLite)
        _vector_store = SQLiteVecVectorStore(
            db_path="./data/knowledge_vectors.db",
            dimension=384,  # MiniLM dimension
        )
        await _vector_store.initialize()

    if _embedding_manager is None:
        # Initialize embedding manager
        _embedding_manager = EmbeddingManager(
            model_type=EmbeddingModelType.MINILM,
            cache_dir="./data/embeddings",
        )

    if _embedding_service is None:
        _embedding_service = EmbeddingService(_embedding_manager)

    if _retriever is None:
        # Initialize retriever
        _retriever = HybridRetriever(
            vector_store=_vector_store,
            embedding_manager=_embedding_manager,
        )

    if _rag_pipeline is None:
        # Initialize RAG pipeline
        _rag_pipeline = RAGPipeline(
            retriever=_retriever,
            embedding_service=_embedding_service,
        )


# ============================================================================
# Document Management
# ============================================================================


@router.post("/documents/upload")
async def upload_document(file: UploadFile = File(...)):
    """Upload and index a document

    Args:
        file: Uploaded file

    Returns:
        Document information with indexing status
    """
    await _ensure_initialized()

    try:
        # Save uploaded file
        file_path = Path("./data/uploads") / file.filename
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with file_path.open("wb") as f:
            content = await file.read()
            f.write(content)

        # Parse document
        parser = PDFParser()
        document = await parser.parse(file_path)

        # Chunk document
        chunker = TextChunker(
            config=ChunkingConfig(
                strategy=ChunkingStrategy.RECURSIVE,
                chunk_size=512,
                chunk_overlap=50,
            ),
        )
        chunks = await chunker.chunk(document)

        # Generate embeddings
        chunk_texts = [chunk.content for chunk in chunks]
        embeddings = await _embedding_service.embed_documents(chunk_texts)

        # Add to vector store
        from dawei.knowledge.models import VectorDocument

        vector_docs = []
        for chunk, embedding in zip(chunks, embeddings):
            vector_doc = VectorDocument(
                id=chunk.id,
                embedding=embedding,
                content=chunk.content,
                metadata={
                    **chunk.metadata,
                    "document_id": chunk.document_id,
                    "chunk_index": chunk.chunk_index,
                },
            )
            vector_docs.append(vector_doc)

        await _vector_store.add(vector_docs)

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "document_id": document.id,
                "file_name": file.filename,
                "file_size": document.metadata.file_size,
                "chunks_added": len(chunks),
                "message": f"Document indexed successfully with {len(chunks)} chunks",
            },
        )

    except Exception as e:
        logger.error(f"Failed to upload document: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/documents/{document_id}")
async def delete_document(document_id: str):
    """Delete a document and all its chunks

    Args:
        document_id: Document ID to delete

    Returns:
        Deletion status
    """
    await _ensure_initialized()

    try:
        # Delete all chunks for this document
        deleted_count = await _vector_store.delete([f"{document_id}_chunk_{i}" for i in range(10000)])

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "document_id": document_id,
                "chunks_deleted": deleted_count,
                "message": f"Document deleted successfully",
            },
        )

    except Exception as e:
        logger.error(f"Failed to delete document: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/documents")
async def list_documents(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    """List all documents

    Args:
        skip: Number of documents to skip
        limit: Maximum number of documents to return

    Returns:
        List of documents
    """
    await _ensure_initialized()

    try:
        # Get document count
        total_count = await _vector_store.count()

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "total": total_count,
                "documents": [],  # TODO: Implement document listing
            },
        )

    except Exception as e:
        logger.error(f"Failed to list documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Search and Retrieval
# ============================================================================


@router.post("/search")
async def search(
    query: str = Query(..., min_length=1),
    mode: RetrievalMode = Query(RetrievalMode.HYBRID),
    top_k: int = Query(5, ge=1, le=50),
):
    """Search knowledge base

    Args:
        query: Search query
        mode: Retrieval mode (vector, graph, fulltext, hybrid)
        top_k: Number of results to return

    Returns:
        Search results
    """
    await _ensure_initialized()

    try:
        # Create retrieval query
        from dawei.knowledge.models import RetrievalQuery

        retrieval_query = RetrievalQuery(
            query=query,
            mode=mode,
            top_k=top_k,
        )

        # Execute search
        results = await _retriever.retrieve(retrieval_query)

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "query": query,
                "mode": mode,
                "results": [
                    {
                        "id": r.id,
                        "content": r.content,
                        "score": r.score,
                        "source": r.source,
                        "metadata": r.metadata,
                    }
                    for r in results.results
                ],
                "total_count": results.total_count,
                "vector_count": results.vector_count,
                "graph_count": results.graph_count,
                "fulltext_count": results.fulltext_count,
                "latency_ms": results.latency_ms,
            },
        )

    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rag/query")
async def rag_query(
    query: str = Query(..., min_length=1),
    max_context_length: int = Query(4000, ge=1000, le=10000),
):
    """Query with RAG (retrieve context and build prompt)

    Args:
        query: User query
        max_context_length: Maximum context length

    Returns:
        RAG prompt with context
    """
    await _ensure_initialized()

    try:
        # Query with context
        result = await _rag_pipeline.query_with_context(
            query=query,
            max_context_length=max_context_length,
        )

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "query": query,
                "prompt": result["prompt"],
                "context": result["context"],
                "sources": result["sources"],
                "citations": result["citations"],
                "metadata": result["metadata"],
            },
        )

    except Exception as e:
        logger.error(f"RAG query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Embeddings
# ============================================================================


@router.post("/embeddings")
async def create_embeddings(
    texts: List[str],
    model: EmbeddingModelType = Query(EmbeddingModelType.MINILM),
):
    """Create embeddings for texts

    Args:
        texts: List of text strings
        model: Embedding model to use

    Returns:
        Embeddings
    """
    await _ensure_initialized()

    try:
        from dawei.knowledge.models import EmbeddingRequest

        request = EmbeddingRequest(texts=texts, model=model)
        response = await _embedding_service.process_request(request)

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "embeddings": response.embeddings,
                "model": response.model,
                "dimension": response.dimension,
                "total_tokens": response.total_tokens,
                "latency_ms": response.latency_ms,
            },
        )

    except Exception as e:
        logger.error(f"Failed to create embeddings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Health Check
# ============================================================================


@router.get("/health")
async def health_check():
    """Check knowledge base system health

    Returns:
        Health status
    """
    await _ensure_initialized()

    health_status = {
        "vector_store": False,
        "embeddings": False,
    }

    try:
        if _vector_store:
            health_status["vector_store"] = await _vector_store.health_check()
    except Exception:
        pass

    try:
        if _embedding_manager:
            health_status["embeddings"] = True  # If loaded, it's healthy
    except Exception:
        pass

    all_healthy = all(health_status.values())

    return JSONResponse(
        status_code=200 if all_healthy else 503,
        content={
            "healthy": all_healthy,
            "services": health_status,
        },
    )
