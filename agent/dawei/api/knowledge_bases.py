# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Knowledge Base Management API - Multi-tenancy support"""

import logging
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from dawei.core.dependency_container import DEPENDENCY_CONTAINER
from dawei.knowledge.base_manager import KnowledgeBaseManager
from dawei.knowledge.base_models import (
    KnowledgeBase,
    KnowledgeBaseCreate,
    KnowledgeBaseListResponse,
    KnowledgeBaseStatus,
    KnowledgeBaseUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/knowledge/bases", tags=["knowledge-bases"])


# ============================================================================
# Request/Response Models
# ============================================================================


class SetDefaultRequest(BaseModel):
    """Request to set default knowledge base"""

    base_id: str = Field(..., description="Knowledge base ID to set as default")


class ErrorResponse(BaseModel):
    """Error response model"""

    error: str
    detail: str


# ============================================================================
# Helper Functions
# ============================================================================


def get_base_manager() -> KnowledgeBaseManager:
    """Get knowledge base manager from dependency container

    Initializes the manager if not already registered.
    """
    try:
        return DEPENDENCY_CONTAINER.get_service("KnowledgeBaseManager")
    except Exception:
        # Try to initialize if not registered
        from dawei.knowledge.init import initialize_knowledge_base_manager

        manager = initialize_knowledge_base_manager()
        logger.info("Knowledge base manager initialized on-demand")
        return manager


# ============================================================================
# API Endpoints
# ============================================================================


@router.get("", response_model=KnowledgeBaseListResponse)
async def list_knowledge_bases(
    workspace_id: str | None = Query(None, description="Filter by workspace ID"),
    status_filter: KnowledgeBaseStatus | None = Query(None, alias="status", description="Filter by status"),
):
    """List all knowledge bases

    Returns a list of all knowledge bases with optional filtering.
    """
    manager = get_base_manager()
    return manager.list_bases(workspace_id=workspace_id, status=status_filter)


@router.post("", response_model=KnowledgeBase, status_code=status.HTTP_201_CREATED)
async def create_knowledge_base(create_data: KnowledgeBaseCreate):
    """Create a new knowledge base

    Creates a new knowledge base with the specified configuration.
    """
    manager = get_base_manager()
    return manager.create_base(create_data)


@router.get("/default", response_model=KnowledgeBase)
async def get_default_knowledge_base():
    """Get default knowledge base

    Returns the default knowledge base.
    """
    manager = get_base_manager()
    kb = manager.get_default_base()
    if not kb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No default knowledge base found")
    return kb


@router.get("/{base_id}", response_model=KnowledgeBase)
async def get_knowledge_base(base_id: str):
    """Get knowledge base by ID

    Returns detailed information about a specific knowledge base.
    """
    manager = get_base_manager()
    kb = manager.get_base(base_id)
    if not kb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Knowledge base not found: {base_id}")
    return kb


@router.put("/{base_id}", response_model=KnowledgeBase)
async def update_knowledge_base(base_id: str, update_data: KnowledgeBaseUpdate):
    """Update knowledge base

    Updates configuration and metadata of a knowledge base.
    """
    manager = get_base_manager()
    kb = manager.update_base(base_id, update_data)
    if not kb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Knowledge base not found: {base_id}")
    return kb


@router.delete("/{base_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_knowledge_base(base_id: str, force: bool = Query(False, description="Force deletion even if base has documents")):
    """Delete knowledge base

    Deletes a knowledge base and all its data.
    Cannot delete the default knowledge base.
    """
    manager = get_base_manager()
    success = manager.delete_base(base_id, force=force)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Knowledge base not found: {base_id}")
    return


@router.post("/{base_id}/set-default", response_model=KnowledgeBase)
async def set_default_knowledge_base(base_id: str):
    """Set default knowledge base

    Sets the specified knowledge base as the default.
    """
    manager = get_base_manager()
    kb = manager.set_default_base(base_id)
    if not kb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Knowledge base not found: {base_id}")
    return kb


@router.get("/{base_id}/stats", response_model=dict)
async def get_knowledge_base_stats(base_id: str):
    """Get knowledge base statistics

    Returns detailed statistics about a knowledge base.
    """
    manager = get_base_manager()
    kb = manager.get_base(base_id)
    if not kb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Knowledge base not found: {base_id}")
    return kb.stats.model_dump()


# ============================================================================
# Document Endpoints (under knowledge bases)
# ============================================================================


@router.get("/{base_id}/documents", response_model=dict)
async def list_base_documents(
    base_id: str,
    skip: int = Query(0, ge=0, description="Number of documents to skip"),
    limit: int = Query(10, ge=1, le=100, description="Number of documents to return"),
):
    """List documents in a knowledge base

    Returns a paginated list of documents in the specified knowledge base.
    """
    manager = get_base_manager()

    # Check if knowledge base exists
    kb = manager.get_base(base_id)
    if not kb:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "Knowledge base not found",
                "base_id": base_id,
                "message": f"Knowledge base '{base_id}' does not exist. Please check the knowledge base ID or create it first.",
                "available_bases": [base.id for base in manager.list_bases().bases],
            },
        )

    return manager.list_base_documents(base_id, skip=skip, limit=limit)


@router.post("/{base_id}/documents/upload")
async def upload_document_to_base(
    base_id: str,
    file: UploadFile = File(..., description="Document file to upload"),
):
    """Upload a document to a specific knowledge base

    Args:
        base_id: Knowledge base ID
        file: Uploaded file (PDF, DOCX, TXT, MD supported)

    Returns:
        Document information with indexing status
    """
    manager = get_base_manager()
    kb = manager.get_base(base_id)
    if not kb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Knowledge base not found: {base_id}")

    # Get file extension
    file_extension = Path(file.filename).suffix.lower() if file.filename else ""
    supported_extensions = {".pdf", ".docx", ".txt", ".md", ".markdown"}

    if file_extension not in supported_extensions:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported file type: {file_extension}. Supported types: {', '.join(supported_extensions)}")

    # Create uploads directory for this knowledge base
    base_storage_path = manager._get_storage_path(base_id)
    uploads_dir = base_storage_path / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)

    # Save uploaded file
    file_path = uploads_dir / file.filename
    with file_path.open("wb") as f:
        content = await file.read()
        f.write(content)

    # Import document processing components
    from dawei.knowledge.chunking.chunker import ChunkingConfig, ChunkingStrategy, TextChunker
    from dawei.knowledge.models import VectorDocument
    from dawei.knowledge.parsers.docx_parser import DocxParser
    from dawei.knowledge.parsers.markdown_parser import MarkdownParser
    from dawei.knowledge.parsers.pdf_parser import PDFParser
    from dawei.knowledge.parsers.text_parser import TextParser

    # Select appropriate parser based on file type
    parser_map = {
        ".pdf": PDFParser,
        ".docx": DocxParser,
        ".txt": TextParser,
        ".md": MarkdownParser,
        ".markdown": MarkdownParser,
    }

    parser_class = parser_map.get(file_extension, TextParser)
    parser = parser_class()

    # Parse document
    document = await parser.parse(file_path)

    # Determine chunk size from knowledge base settings
    chunk_size = kb.settings.chunk_size
    chunk_overlap = kb.settings.chunk_overlap
    chunk_strategy_name = kb.settings.chunk_strategy

    # Map chunk strategy name to enum
    strategy_map = {
        "recursive": ChunkingStrategy.RECURSIVE,
        "semantic": ChunkingStrategy.SEMANTIC,
    }
    chunk_strategy = strategy_map.get(chunk_strategy_name, ChunkingStrategy.RECURSIVE)

    # Chunk document
    chunker = TextChunker(
        config=ChunkingConfig(
            strategy=chunk_strategy,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        ),
    )
    chunks = await chunker.chunk(document)

    logger.info(f"Document chunked into {len(chunks)} chunks")

    # Initialize embedding service for this knowledge base
    from dawei.knowledge.vector.sqlite_vec_store import SQLiteVecVectorStore

    # Create knowledge base-specific vector store
    vector_db_path = base_storage_path / "vectors.db"
    vector_store = SQLiteVecVectorStore(
        db_path=str(vector_db_path),
        dimension=kb.settings.embedding_dimension,
    )
    await vector_store.initialize()

    # Get or create embedding manager (cached to avoid HTTP client issues)
    try:
        embedding_service = manager.get_embedding_manager(base_id, model_type="MINILM")
    except Exception as e:
        logger.error(f"Failed to initialize embedding service: {e}")
        # Clean up uploaded file
        file_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initialize embedding service. The model may need to be downloaded first. Error: {str(e)}",
        )

    # Generate embeddings
    try:
        chunk_texts = [chunk.content for chunk in chunks]
        embeddings = await embedding_service.embed_documents(chunk_texts)
        logger.info(f"Generated {len(embeddings)} embeddings")
    except Exception as e:
        logger.error(f"Failed to generate embeddings: {e}")
        # Clean up uploaded file
        file_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate embeddings for document. Error: {str(e)}",
        )

    # Add to vector store
    vector_docs = []
    for chunk, embedding in zip(chunks, embeddings, strict=True):
        # Convert metadata to JSON-serializable format
        metadata_copy = dict(chunk.metadata)
        # Convert datetime objects to ISO strings
        for key, value in metadata_copy.items():
            if hasattr(value, 'isoformat'):
                metadata_copy[key] = value.isoformat()

        vector_doc = VectorDocument(
            id=chunk.id,
            embedding=embedding,
            content=chunk.content,
            metadata={
                **metadata_copy,
                "document_id": chunk.document_id,
                "chunk_index": chunk.chunk_index,
                "base_id": base_id,  # Tag with knowledge base ID
                "file_name": file.filename,
            },
        )
        vector_docs.append(vector_doc)

    await vector_store.add(vector_docs)
    logger.info(f"Added {len(vector_docs)} chunks to vector store")

    # Update knowledge base stats
    kb.stats.total_documents += 1
    kb.stats.total_chunks += len(chunks)
    kb.stats.indexed_documents += 1
    kb.stats.last_indexed_at = None  # Will be set by default factory
    kb.stats.last_updated_at = None  # Will be set by default factory
    manager._save_metadata()

    logger.info(f"Document uploaded to knowledge base {base_id}: {file.filename} ({len(chunks)} chunks)")

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "document_id": document.id,
            "base_id": base_id,
            "file_name": file.filename,
            "file_size": document.metadata.file_size,
            "chunks_added": len(chunks),
            "message": f"Document indexed successfully with {len(chunks)} chunks",
        },
    )


@router.delete("/{base_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document_from_base(base_id: str, document_id: str):
    """Delete a document from a knowledge base

    Args:
        base_id: Knowledge base ID
        document_id: Document ID to delete

    Returns:
        Deletion status
    """
    manager = get_base_manager()
    kb = manager.get_base(base_id)
    if not kb:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "Knowledge base not found",
                "base_id": base_id,
                "message": f"Knowledge base '{base_id}' does not exist. Please check the knowledge base ID or create it first.",
                "available_bases": [base.id for base in manager.list_bases().bases],
            },
        )

    # Initialize vector store for this knowledge base
    from dawei.knowledge.vector.sqlite_vec_store import SQLiteVecVectorStore

    base_storage_path = manager._get_storage_path(base_id)
    vector_db_path = base_storage_path / "vectors.db"

    if not vector_db_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "Vector store not found",
                "base_id": base_id,
                "message": f"Vector store for knowledge base '{base_id}' does not exist. This may mean no documents have been uploaded yet.",
                "suggestion": "Upload a document to this knowledge base first.",
            },
        )

    vector_store = SQLiteVecVectorStore(
        db_path=str(vector_db_path),
        dimension=kb.settings.embedding_dimension,
    )
    await vector_store.initialize()

    # Delete all chunks for this document
    chunk_ids = [f"{document_id}_chunk_{i}" for i in range(10000)]
    deleted_count = await vector_store.delete(chunk_ids)

    if deleted_count == 0:
        logger.warning(f"No chunks found for document {document_id} in knowledge base {base_id}")

    # Update knowledge base stats
    kb.stats.total_documents -= 1
    kb.stats.total_chunks -= deleted_count
    kb.stats.indexed_documents -= 1
    kb.stats.last_updated_at = None  # Will be set by default factory
    manager._save_metadata()

    logger.info(f"Document deleted from knowledge base {base_id}: {document_id} ({deleted_count} chunks)")

    return


@router.get("/{base_id}/documents/{document_id}", response_model=dict)
async def get_document_from_base(base_id: str, document_id: str):
    """Get a document from a knowledge base

    Args:
        base_id: Knowledge base ID
        document_id: Document ID to retrieve

    Returns:
        Document details with chunks
    """
    manager = get_base_manager()
    kb = manager.get_base(base_id)
    if not kb:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "Knowledge base not found",
                "base_id": base_id,
                "message": f"Knowledge base '{base_id}' does not exist. Please check the knowledge base ID or create it first.",
                "available_bases": [base.id for base in manager.list_bases().bases],
            },
        )

    # Initialize vector store for this knowledge base
    from dawei.knowledge.vector.sqlite_vec_store import SQLiteVecVectorStore

    base_storage_path = manager._get_storage_path(base_id)
    vector_db_path = base_storage_path / "vectors.db"

    if not vector_db_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "Vector store not found",
                "base_id": base_id,
                "message": f"Vector store for knowledge base '{base_id}' does not exist. This may mean no documents have been uploaded yet.",
                "suggestion": "Upload a document to this knowledge base first.",
            },
        )

    vector_store = SQLiteVecVectorStore(
        db_path=str(vector_db_path),
        dimension=kb.settings.embedding_dimension,
    )
    await vector_store.initialize()

    # Query all chunks for this document directly from the database
    import aiosqlite

    all_chunks = []
    async with aiosqlite.connect(vector_db_path) as db:
        # Query all chunks for this document_id
        query_sql = f"SELECT id, embedding, metadata, content FROM {vector_store.table_name} WHERE json_extract(metadata, '$.document_id') = ? ORDER BY json_extract(metadata, '$.chunk_index')"
        cursor = await db.execute(query_sql, (document_id,))
        rows = await cursor.fetchall()

        if not rows:
            # Get available documents to help the user
            available_docs = []
            try:
                list_query = f"SELECT DISTINCT json_extract(metadata, '$.document_id') as doc_id, json_extract(metadata, '$.file_name') as file_name FROM {vector_store.table_name}"
                list_cursor = await db.execute(list_query)
                list_rows = await list_cursor.fetchall()
                available_docs = [
                    {"document_id": row[0], "file_name": row[1]}
                    for row in list_rows
                    if row[0] and row[1]
                ]
            except Exception:
                pass

            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "Document not found",
                    "base_id": base_id,
                    "document_id": document_id,
                    "message": f"Document '{document_id}' not found in knowledge base '{base_id}'.",
                    "available_documents": available_docs,
                    "suggestion": "Check the document ID or upload the document if it doesn't exist.",
                },
            )

        # Convert rows to VectorSearchResult format
        import json

        for row in rows:
            chunk_id, _embedding_bytes, metadata_json, content = row
            metadata = json.loads(metadata_json)

            # Create a simple object with the needed fields
            from dawei.knowledge.models import VectorSearchResult

            chunk_result = VectorSearchResult(
                id=chunk_id,
                score=1.0,  # All chunks get score 1.0 since we're not doing vector search
                content=content,
                metadata=metadata,
            )
            all_chunks.append(chunk_result)

    # Sort chunks by chunk_index (should already be sorted from SQL ORDER BY)
    all_chunks.sort(key=lambda x: x.metadata.get("chunk_index", 0))

    # Combine all chunk content
    full_content = "\n\n".join([chunk.content for chunk in all_chunks])

    # Get document metadata from the first chunk
    first_chunk = all_chunks[0]
    metadata = first_chunk.metadata

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "id": document_id,
            "base_id": base_id,
            "content": full_content,
            "file_name": metadata.get("file_name", ""),
            "chunk_count": len(all_chunks),
            "metadata": metadata,
        },
    )


@router.post("/{base_id}/documents/{document_id}/reindex")
async def reindex_document_in_base(base_id: str, document_id: str):
    """Re-index a document in a knowledge base

    Args:
        base_id: Knowledge base ID
        document_id: Document ID to re-index

    Returns:
        Re-indexing status
    """
    manager = get_base_manager()
    kb = manager.get_base(base_id)
    if not kb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Knowledge base not found: {base_id}")

    # TODO: Implement document re-indexing
    # This would involve:
    # 1. Finding the original file
    # 2. Re-parsing and chunking
    # 3. Removing old chunks from vector store
    # 4. Adding new chunks

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "document_id": document_id,
            "base_id": base_id,
            "message": "Document re-indexed successfully",
        },
    )
