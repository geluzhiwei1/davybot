# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Knowledge Base Management API - Multi-tenancy support"""

import asyncio
import json
import logging
import time
import uuid
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
from dawei.knowledge.models import RetrievalMode

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/knowledge/bases", tags=["knowledge-bases"])


# ============================================================================
# Sync Task Manager (in-memory, lightweight)
# ============================================================================


class SyncTaskStatus:
    """Status of a background sync task."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class SyncTask:
    """A single background sync task."""

    def __init__(self, task_id: str, base_id: str, force_rebuild: bool):
        self.task_id = task_id
        self.base_id = base_id
        self.force_rebuild = force_rebuild
        self.status = SyncTaskStatus.PENDING
        self.progress: float = 0.0  # 0-100
        self.current_file: str = ""
        self.total_files: int = 0
        self.processed_files: int = 0
        self.result: dict[str, Any] | None = None
        self.error: str | None = None
        self.created_at: float = time.time()
        self.finished_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "base_id": self.base_id,
            "status": self.status,
            "progress": round(self.progress, 1),
            "current_file": self.current_file,
            "total_files": self.total_files,
            "processed_files": self.processed_files,
            "result": self.result,
            "error": self.error,
            "force_rebuild": self.force_rebuild,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
        }


class SyncTaskManager:
    """Manages background sync tasks with duplicate prevention per knowledge base."""

    def __init__(self) -> None:
        self._tasks: dict[str, SyncTask] = {}  # task_id -> SyncTask
        self._base_tasks: dict[str, str] = {}  # base_id -> task_id (active only)

    def create_task(self, base_id: str, force_rebuild: bool) -> SyncTask | None:
        """Create a new sync task. Returns None if a task already running for this base."""
        if base_id in self._base_tasks:
            existing_id = self._base_tasks[base_id]
            existing = self._tasks.get(existing_id)
            if existing and existing.status in (SyncTaskStatus.PENDING, SyncTaskStatus.RUNNING):
                return None  # Duplicate
        task_id = f"sync_{uuid.uuid4().hex[:12]}"
        task = SyncTask(task_id, base_id, force_rebuild)
        self._tasks[task_id] = task
        self._base_tasks[base_id] = task_id
        return task

    def get_task(self, task_id: str) -> SyncTask | None:
        return self._tasks.get(task_id)

    def get_active_task_for_base(self, base_id: str) -> SyncTask | None:
        """Get the active (pending/running) task for a knowledge base, if any."""
        task_id = self._base_tasks.get(base_id)
        if not task_id:
            return None
        task = self._tasks.get(task_id)
        if task and task.status in (SyncTaskStatus.PENDING, SyncTaskStatus.RUNNING):
            return task
        # Clean up stale mapping
        del self._base_tasks[base_id]
        return None

    def finish_task(self, task: SyncTask) -> None:
        """Mark task as finished and remove base_id mapping."""
        task.finished_at = time.time()
        if task.base_id in self._base_tasks and self._base_tasks[task.base_id] == task.task_id:
            del self._base_tasks[task.base_id]
        # Keep completed tasks for a while (last 100) for status polling
        self._cleanup_old_tasks()

    def cancel_task(self, base_id: str) -> SyncTask | None:
        """Force-cancel the active task for a knowledge base."""
        task_id = self._base_tasks.get(base_id)
        if not task_id:
            return None
        task = self._tasks.get(task_id)
        if task and task.status in (SyncTaskStatus.PENDING, SyncTaskStatus.RUNNING):
            task.status = SyncTaskStatus.FAILED
            task.error = "Cancelled by user"
            self.finish_task(task)
            return task
        return None

    def _cleanup_old_tasks(self) -> None:
        """Keep only the last 100 finished tasks."""
        finished = [(tid, t) for tid, t in self._tasks.items() if t.status in (SyncTaskStatus.COMPLETED, SyncTaskStatus.FAILED)]
        if len(finished) > 100:
            finished.sort(key=lambda x: x[1].finished_at or 0)
            for tid, _ in finished[:-100]:
                del self._tasks[tid]


# Global singleton
_sync_task_manager = SyncTaskManager()


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


@router.get("/scan-dir")
async def scan_directory(
    dir_path: str = Query(..., min_length=1, description="Directory path to scan"),
    recursive: bool = Query(True, description="Scan subdirectories recursively"),
):
    """Scan a directory for supported files (no knowledge base required)

    Used during knowledge base creation to preview files before saving.

    Args:
        dir_path: Directory path to scan
        recursive: Whether to scan subdirectories

    Returns:
        List of supported files found in the directory
    """
    scan_path = dir_path
    directory = Path(scan_path).expanduser().resolve()
    if not directory.exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Directory does not exist: {scan_path}",
        )

    if not directory.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Path is not a directory: {scan_path}",
        )

    supported = {".md", ".markdown"}

    files = []
    try:
        glob_iter = directory.rglob("*") if recursive else directory.glob("*")
        for file_path in glob_iter:
            if file_path.is_file() and file_path.suffix.lower() in supported:
                stat = file_path.stat()
                rel_path = str(file_path.relative_to(directory))
                files.append({
                    "name": file_path.name,
                    "path": str(file_path),
                    "relative_path": rel_path,
                    "size": stat.st_size,
                    "extension": file_path.suffix.lower(),
                    "modified_at": stat.st_mtime,
                    "exists_in_kb": False,
                })
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied: {scan_path}",
        )

    files.sort(key=lambda f: f["name"].lower())

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "files": files,
            "total": len(files),
            "dir_path": str(directory),
            "existing_count": 0,
            "new_count": len(files),
        },
    )


@router.get("/by-id/{base_id}", response_model=KnowledgeBase)
async def get_knowledge_base(base_id: str):
    """Get knowledge base by ID

    Returns detailed information about a specific knowledge base.
    """
    manager = get_base_manager()
    kb = manager.get_base(base_id)
    if not kb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Knowledge base not found: {base_id}")
    return kb


@router.put("/by-id/{base_id}", response_model=KnowledgeBase)
async def update_knowledge_base(base_id: str, update_data: KnowledgeBaseUpdate):
    """Update knowledge base

    Updates configuration and metadata of a knowledge base.
    Cannot change embedding_model if the knowledge base already has indexed documents.
    """
    manager = get_base_manager()
    existing = manager.get_base(base_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Knowledge base not found: {base_id}")

    # Prevent embedding_model change when documents exist
    if update_data.settings is not None and existing.stats.total_documents > 0:
        if update_data.settings.embedding_model != existing.settings.embedding_model:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot change embedding_model from '{existing.settings.embedding_model}' to "
                f"'{update_data.settings.embedding_model}': knowledge base already has "
                f"{existing.stats.total_documents} document(s). Delete all documents first or create a new knowledge base.",
            )

    kb = manager.update_base(base_id, update_data)
    return kb


@router.delete("/by-id/{base_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_knowledge_base(base_id: str, force: bool = Query(False, description="Force deletion even if base has documents")):
    """Delete knowledge base

    Deletes a knowledge base and all its data.
    Cannot delete the default knowledge base.
    """
    manager = get_base_manager()
    success = manager.delete_base(base_id, force=force)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Knowledge base not found: {base_id}")


@router.post("/by-id/{base_id}/set-default", response_model=KnowledgeBase)
async def set_default_knowledge_base(base_id: str):
    """Set default knowledge base

    Sets the specified knowledge base as the default.
    """
    manager = get_base_manager()
    kb = manager.set_default_base(base_id)
    if not kb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Knowledge base not found: {base_id}")
    return kb


@router.get("/by-id/{base_id}/stats", response_model=dict)
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


@router.get("/by-id/{base_id}/documents", response_model=dict)
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


@router.post("/by-id/{base_id}/documents/upload")
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
    supported_extensions = {".md", ".markdown"}

    if file_extension not in supported_extensions:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported file type: {file_extension}. Supported types: {', '.join(sorted(supported_extensions))}")

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
    from dawei.knowledge.parsers.markdown_parser import MarkdownParser

    parser = MarkdownParser()

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
        "markdown": ChunkingStrategy.MARKDOWN,
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
        embedding_service = manager.get_embedding_manager(base_id)
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
            if hasattr(value, "isoformat"):
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

    # Index in full-text search
    try:
        fulltext_store = manager.get_fulltext_store(base_id)
        await fulltext_store.initialize()
        await fulltext_store.add_documents(chunks)
        logger.info(f"Added {len(chunks)} chunks to full-text index")
    except Exception as e:
        logger.warning(f"Failed to index full-text search: {e}")
        # Non-fatal, continue with graph indexing

    # Index in graph store — extract from FULL document, not per-chunk
    try:
        graph_store = manager.get_graph_store(base_id)
        await graph_store.initialize()

        from dawei.knowledge._graph_builder import build_document_graph
        from dawei.knowledge.extraction import ExtractionFactory

        extraction_strategy = kb.settings.extraction_strategy or "rule_based"
        domain = getattr(kb.settings, "domain", "general")
        extraction_llm_config = getattr(kb.settings, "extraction_llm_config", "") or None

        # Auto-upgrade to sanctions_hybrid for sanctions domain
        if domain == "sanctions" and extraction_strategy == "llm":
            extraction_strategy = "sanctions_hybrid"

        extractor = ExtractionFactory.create(extraction_strategy, domain=domain, llm_config_name=extraction_llm_config)

        total_entities, total_relations = await build_document_graph(
            graph_store=graph_store,
            document=document,
            chunks=chunks,
            extractor=extractor,
            base_id=base_id,
            extraction_strategy=extraction_strategy,
            file_name=file.filename,
        )
    except Exception as e:
        logger.warning(f"Failed to index graph: {e}")
        # Non-fatal, continue

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


@router.delete("/by-id/{base_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
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



@router.get("/by-id/{base_id}/documents/{document_id}", response_model=dict)
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
                available_docs = [{"document_id": row[0], "file_name": row[1]} for row in list_rows if row[0] and row[1]]
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


@router.post("/by-id/{base_id}/reindex")
async def reindex_knowledge_base(base_id: str):
    """Rebuild all indexes for a knowledge base (vector, fulltext, graph)

    Args:
        base_id: Knowledge base ID

    Returns:
        Re-indexing status with statistics
    """
    manager = get_base_manager()
    kb = manager.get_base(base_id)
    if not kb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Knowledge base not found: {base_id}")

    base_storage_path = manager._get_storage_path(base_id)
    uploads_dir = base_storage_path / "uploads"

    # Check if there are uploaded files
    if not uploads_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No uploads directory found. Please upload documents first.",
        )

    uploaded_files = list(uploads_dir.iterdir())
    if not uploaded_files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No uploaded files found. Please upload documents first.",
        )

    logger.info(f"Starting re-indexing for knowledge base {base_id} with {len(uploaded_files)} files")

    # Import required modules
    from dawei.knowledge.chunking.chunker import ChunkingConfig, ChunkingStrategy, TextChunker
    from dawei.knowledge.extraction import (
        ExtractionFactory,
        ExtractionStrategyType,
    )
    from dawei.knowledge.models import GraphEntity, GraphRelation, VectorDocument
    from dawei.knowledge.parsers.markdown_parser import MarkdownParser
    from dawei.knowledge.vector.sqlite_vec_store import SQLiteVecVectorStore

    # Initialize stores
    vector_db_path = base_storage_path / "vectors.db"
    vector_store = SQLiteVecVectorStore(
        db_path=str(vector_db_path),
        dimension=kb.settings.embedding_dimension,
    )
    await vector_store.initialize()

    fulltext_store = manager.get_fulltext_store(base_id)
    await fulltext_store.initialize()

    graph_store = manager.get_graph_store(base_id)
    await graph_store.initialize()

    # Clear old graph data
    await graph_store.clear()
    logger.info("Cleared old graph data")

    # Get embedding manager
    embedding_service = manager.get_embedding_manager(base_id)

    # Determine chunk size from knowledge base settings
    chunk_size = kb.settings.chunk_size
    chunk_overlap = kb.settings.chunk_overlap
    chunk_strategy_name = kb.settings.chunk_strategy

    strategy_map = {
        "recursive": ChunkingStrategy.RECURSIVE,
        "semantic": ChunkingStrategy.SEMANTIC,
        "markdown": ChunkingStrategy.MARKDOWN,
    }
    chunk_strategy = strategy_map.get(chunk_strategy_name, ChunkingStrategy.RECURSIVE)

    chunker = TextChunker(
        config=ChunkingConfig(
            strategy=chunk_strategy,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        ),
    )

    # Get extraction strategy
    extraction_strategy = kb.settings.extraction_strategy or "rule_based"
    domain = getattr(kb.settings, "domain", "general")

    # Auto-upgrade to sanctions_hybrid for sanctions domain
    if domain == "sanctions" and extraction_strategy == "llm":
        extraction_strategy = "sanctions_hybrid"

    extractor = ExtractionFactory.create(extraction_strategy, domain=domain)

    # Statistics
    total_documents = 0
    total_chunks = 0
    total_entities = 0
    total_relations = 0
    errors = []

    # Process each file
    for file_path in uploaded_files:
        try:
            file_extension = file_path.suffix.lower()
            if file_extension not in {".md", ".markdown"}:
                logger.warning(f"Unsupported file type: {file_extension}, skipping {file_path.name}")
                errors.append(f"Skipped {file_path.name}: unsupported file type")
                continue

            parser = MarkdownParser()

            # Parse document
            document = await parser.parse(file_path)
            logger.info(f"Parsed document: {file_path.name}")

            # Chunk document
            chunks = await chunker.chunk(document)
            logger.info(f"Document chunked into {len(chunks)} chunks")

            # Generate embeddings
            chunk_texts = [chunk.content for chunk in chunks]
            embeddings = await embedding_service.embed_documents(chunk_texts)

            # Add to vector store
            vector_docs = []
            for chunk, embedding in zip(chunks, embeddings, strict=True):
                metadata_copy = dict(chunk.metadata)
                for key, value in metadata_copy.items():
                    if hasattr(value, "isoformat"):
                        metadata_copy[key] = value.isoformat()

                vector_doc = VectorDocument(
                    id=chunk.id,
                    embedding=embedding,
                    content=chunk.content,
                    metadata={
                        **metadata_copy,
                        "document_id": chunk.document_id,
                        "chunk_index": chunk.chunk_index,
                        "base_id": base_id,
                        "file_name": file_path.name,
                    },
                )
                vector_docs.append(vector_doc)

            await vector_store.add(vector_docs)
            logger.info(f"Added {len(vector_docs)} chunks to vector store")

            # Add to full-text store
            await fulltext_store.add_documents(chunks)
            logger.info(f"Added {len(chunks)} chunks to full-text index")

            # Build graph — extract from FULL document
            try:
                from dawei.knowledge._graph_builder import build_document_graph

                doc_entities, doc_relations = await build_document_graph(
                    graph_store=graph_store,
                    document=document,
                    chunks=chunks,
                    extractor=extractor,
                    base_id=base_id,
                    extraction_strategy=extraction_strategy,
                    file_name=file_path.name,
                )
                total_entities += doc_entities
                total_relations += doc_relations
            except Exception as e:
                logger.warning(f"Failed to build graph for {file_path.name}: {e}")

            total_documents += 1
            total_chunks += len(chunks)
            logger.info(f"Successfully indexed {file_path.name}")

        except Exception as e:
            error_msg = f"Failed to index {file_path.name}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            errors.append(error_msg)

    # Update knowledge base stats
    kb.stats.total_documents = total_documents
    kb.stats.total_chunks = total_chunks
    kb.stats.total_entities = total_entities
    kb.stats.total_relations = total_relations
    kb.stats.indexed_documents = total_documents
    kb.stats.last_indexed_at = None  # Will be set by default factory
    kb.stats.last_updated_at = None  # Will be set by default factory
    manager._save_metadata()

    logger.info(f"Re-indexing complete: {total_documents} documents, {total_chunks} chunks, {total_entities} entities, {total_relations} relations")

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "base_id": base_id,
            "message": "Knowledge base re-indexed successfully",
            "stats": {
                "total_documents": total_documents,
                "total_chunks": total_chunks,
                "total_entities": total_entities,
                "total_relations": total_relations,
            },
            "errors": errors if errors else None,
        },
    )


@router.post("/by-id/{base_id}/documents/{document_id}/reindex")
async def reindex_document_in_base(base_id: str, document_id: str):
    """Re-index a single document in a knowledge base

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

    # TODO: Implement single document re-indexing
    # For now, redirect to full re-index
    return await reindex_knowledge_base(base_id)


# ============================================================================
# File Directory Endpoints
# ============================================================================




@router.get("/by-id/{base_id}/scan-dir")
async def scan_watch_directory(
    base_id: str,
    dir_path: str = Query("", description="Directory path to scan (empty = use watch_dir from settings)"),
):
    """Scan a directory for supported files

    Args:
        base_id: Knowledge base ID
        dir_path: Optional directory path override (uses watch_dir setting if empty)

    Returns:
        List of supported files found in the directory
    """
    manager = get_base_manager()
    kb = manager.get_base(base_id)
    if not kb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Knowledge base not found: {base_id}")

    # Determine directory path
    scan_path = dir_path or kb.settings.watch_dir
    if not scan_path:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"files": [], "total": 0, "dir_path": "", "message": "No directory path configured"},
        )

    directory = Path(scan_path).expanduser().resolve()
    if not directory.exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Directory does not exist: {scan_path}",
        )

    if not directory.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Path is not a directory: {scan_path}",
        )

    # Supported extensions
    supported = {".md", ".markdown"}

    # Get existing file names in knowledge base for comparison
    existing_docs = manager.list_base_documents(base_id, skip=0, limit=10000)
    existing_names = set()
    for doc in existing_docs.get("documents", []):
        existing_names.add(doc.get("file_name", ""))

    # Scan directory
    files = []
    try:
        if kb.settings.watch_recursive:
            glob_iter = directory.rglob("*")
        else:
            glob_iter = directory.glob("*")

        for file_path in glob_iter:
            if file_path.is_file() and file_path.suffix.lower() in supported:
                stat = file_path.stat()
                rel_path = str(file_path.relative_to(directory))
                files.append({
                    "name": file_path.name,
                    "path": str(file_path),
                    "relative_path": rel_path,
                    "size": stat.st_size,
                    "extension": file_path.suffix.lower(),
                    "modified_at": stat.st_mtime,
                    "exists_in_kb": file_path.name in existing_names,
                })
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied: {scan_path}",
        )

    # Sort by name
    files.sort(key=lambda f: f["name"].lower())

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "files": files,
            "total": len(files),
            "dir_path": str(directory),
            "existing_count": sum(1 for f in files if f["exists_in_kb"]),
            "new_count": sum(1 for f in files if not f["exists_in_kb"]),
        },
    )


async def _run_sync_task(
    task: SyncTask,
    base_id: str,
    dir_path: str,
    force_rebuild: bool,
) -> None:
    """Background worker that performs the actual sync."""
    try:
        task.status = SyncTaskStatus.RUNNING

        from dawei.knowledge.chunking.chunker import ChunkingConfig, ChunkingStrategy, TextChunker
        from dawei.knowledge.extraction import ExtractionFactory
        from dawei.knowledge.fulltext.sqlite_fts_store import SQLiteFTSStore
        from dawei.knowledge.graph.sqlite_graph_store import SQLiteGraphStore
        from dawei.knowledge.models import GraphEntity, GraphRelation, VectorDocument
        from dawei.knowledge.parsers.markdown_parser import MarkdownParser
        from dawei.knowledge.vector.sqlite_vec_store import SQLiteVecVectorStore
        from datetime import datetime

        manager = get_base_manager()
        kb = manager.get_base(base_id)
        if not kb:
            raise ValueError(f"Knowledge base not found: {base_id}")

        # Determine directory path
        scan_path = dir_path or kb.settings.watch_dir
        if not scan_path:
            raise ValueError("No directory path configured")

        directory = Path(scan_path).expanduser().resolve()
        if not directory.exists():
            raise ValueError(f"Directory does not exist: {scan_path}")

        # Supported extensions
        supported = {".md", ".markdown"}

        # Get existing file names
        existing_docs = manager.list_base_documents(base_id, skip=0, limit=10000)
        existing_names = {doc.get("file_name", "") for doc in existing_docs.get("documents", [])}

        # If force_rebuild, clear existing data first
        if force_rebuild:
            base_storage_path = manager._get_storage_path(base_id)
            for db_name in ("vectors.db", "fulltext.db", "graph.db"):
                db_file = base_storage_path / db_name
                if db_file.exists():
                    db_file.unlink()
            existing_names.clear()

        # Find all supported files
        files_to_import: list[Path] = []
        try:
            glob_iter = directory.rglob("*") if kb.settings.watch_recursive else directory.glob("*")
            for file_path in glob_iter:
                if file_path.is_file() and file_path.suffix.lower() in supported:
                    if not force_rebuild and file_path.name in existing_names:
                        continue
                    files_to_import.append(file_path)
        except PermissionError:
            raise ValueError(f"Permission denied: {scan_path}")

        task.total_files = len(files_to_import)

        if not files_to_import:
            task.status = SyncTaskStatus.COMPLETED
            task.progress = 100.0
            task.result = {
                "success": True,
                "base_id": base_id,
                "message": "No new files to import",
                "imported": 0,
                "skipped": 0,
                "errors": [],
            }
            _sync_task_manager.finish_task(task)
            return

        # Initialize stores
        base_storage_path = manager._get_storage_path(base_id)
        vector_store = SQLiteVecVectorStore(
            db_path=str(base_storage_path / "vectors.db"),
            dimension=kb.settings.embedding_dimension,
        )
        await vector_store.initialize()

        fulltext_store = SQLiteFTSStore(db_path=str(base_storage_path / "fulltext.db"))
        await fulltext_store.initialize()

        graph_store = SQLiteGraphStore(db_path=str(base_storage_path / "graph.db"))
        await graph_store.initialize()

        if force_rebuild:
            await graph_store.clear()

        embedding_service = manager.get_embedding_manager(base_id)

        # Chunking config
        strategy_map = {
            "recursive": ChunkingStrategy.RECURSIVE,
            "semantic": ChunkingStrategy.SEMANTIC,
            "markdown": ChunkingStrategy.MARKDOWN,
        }
        chunk_strategy = strategy_map.get(kb.settings.chunk_strategy, ChunkingStrategy.RECURSIVE)
        chunker = TextChunker(
            config=ChunkingConfig(
                strategy=chunk_strategy,
                chunk_size=kb.settings.chunk_size,
                chunk_overlap=kb.settings.chunk_overlap,
            ),
        )

        extraction_strategy = kb.settings.extraction_strategy or "rule_based"
        domain = getattr(kb.settings, "domain", "general")
        extraction_llm_config = getattr(kb.settings, "extraction_llm_config", "") or None

        # Auto-upgrade to sanctions_hybrid for sanctions domain
        if domain == "sanctions" and extraction_strategy == "llm":
            extraction_strategy = "sanctions_hybrid"
            logger.info(f"Auto-upgraded extraction strategy from 'llm' to 'sanctions_hybrid' for sanctions domain KB {base_id}")

        extractor = ExtractionFactory.create(extraction_strategy, domain=domain, llm_config_name=extraction_llm_config)

        # Stats
        total_documents = 0
        total_chunks = 0
        total_entities = 0
        total_relations = 0
        errors: list[str] = []

        for i, file_path in enumerate(files_to_import):
            task.current_file = file_path.name
            task.processed_files = i
            task.progress = (i / len(files_to_import)) * 100

            try:
                file_extension = file_path.suffix.lower()
                if file_extension not in {".md", ".markdown"}:
                    errors.append(f"Skipped {file_path.name}: unsupported file type {file_extension}")
                    continue

                parser = MarkdownParser()
                document = await parser.parse(file_path)
                chunks = await chunker.chunk(document)

                # Generate embeddings
                chunk_texts = [chunk.content for chunk in chunks]
                embeddings = await embedding_service.embed_documents(chunk_texts)

                # Add to vector store
                vector_docs = []
                for chunk, embedding in zip(chunks, embeddings, strict=True):
                    metadata_copy = dict(chunk.metadata)
                    for key, value in metadata_copy.items():
                        if hasattr(value, "isoformat"):
                            metadata_copy[key] = value.isoformat()

                    vector_doc = VectorDocument(
                        id=chunk.id,
                        embedding=embedding,
                        content=chunk.content,
                        metadata={
                            **metadata_copy,
                            "document_id": chunk.document_id,
                            "chunk_index": chunk.chunk_index,
                            "base_id": base_id,
                            "file_name": file_path.name,
                            "source_path": str(file_path),
                        },
                    )
                    vector_docs.append(vector_doc)

                await vector_store.add(vector_docs)

                # Fulltext index
                try:
                    await fulltext_store.add_documents(chunks)
                except Exception as e:
                    logger.warning(f"Failed to index fulltext for {file_path.name}: {e}")

                # Graph index
                try:
                    from dawei.knowledge._graph_builder import build_document_graph

                    doc_entities, doc_relations = await build_document_graph(
                        graph_store=graph_store,
                        document=document,
                        chunks=chunks,
                        extractor=extractor,
                        base_id=base_id,
                        extraction_strategy=extraction_strategy,
                        file_name=file_path.name,
                    )
                    total_entities += doc_entities
                    total_relations += doc_relations
                except Exception as e:
                    logger.warning(f"Failed to index graph for {file_path.name}: {e}")

                total_documents += 1
                total_chunks += len(chunks)
                logger.info(f"Synced file: {file_path.name} ({len(chunks)} chunks)")

            except Exception as e:
                error_msg = f"Failed to import {file_path.name}: {str(e)}"
                logger.error(error_msg, exc_info=True)
                errors.append(error_msg)

        # Update progress to 100%
        task.processed_files = len(files_to_import)
        task.progress = 100.0

        # Update stats
        if force_rebuild:
            kb.stats.total_documents = total_documents
            kb.stats.total_chunks = total_chunks
            kb.stats.total_entities = total_entities
            kb.stats.total_relations = total_relations
            kb.stats.indexed_documents = total_documents
        else:
            kb.stats.total_documents += total_documents
            kb.stats.total_chunks += total_chunks
            kb.stats.total_entities += total_entities
            kb.stats.total_relations += total_relations
            kb.stats.indexed_documents += total_documents

        kb.stats.last_indexed_at = datetime.now()
        kb.stats.last_updated_at = datetime.now()
        kb.updated_at = datetime.now()
        manager._save_metadata()

        task.status = SyncTaskStatus.COMPLETED
        task.result = {
            "success": True,
            "base_id": base_id,
            "message": f"Synced {total_documents} files from directory",
            "stats": {
                "total_documents": total_documents,
                "total_chunks": total_chunks,
                "total_entities": total_entities,
                "total_relations": total_relations,
            },
            "skipped": len(files_to_import) - total_documents - len(errors),
            "errors": errors if errors else None,
        }
    except Exception as e:
        logger.error(f"Sync task {task.task_id} failed: {e}", exc_info=True)
        task.status = SyncTaskStatus.FAILED
        task.error = str(e)
    finally:
        _sync_task_manager.finish_task(task)


@router.post("/by-id/{base_id}/sync-from-dir")
async def sync_from_directory(
    base_id: str,
    dir_path: str = Query("", description="Directory path (empty = use watch_dir from settings)"),
    force_rebuild: bool = Query(False, description="Force rebuild all files, not just new ones"),
):
    """Sync files from a directory into the knowledge base (background task).

    Returns immediately with a task_id. Use GET /by-id/{base_id}/sync-status to poll progress.
    """
    manager = get_base_manager()
    kb = manager.get_base(base_id)
    if not kb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Knowledge base not found: {base_id}")

    # Check for already running task
    existing = _sync_task_manager.get_active_task_for_base(base_id)
    if existing:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "detail": "A sync task is already running for this knowledge base",
                "task_id": existing.task_id,
                "status": existing.to_dict(),
            },
        )

    # Validate inputs before creating task
    scan_path = dir_path or kb.settings.watch_dir
    if not scan_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No directory path configured. Set watch_dir in knowledge base settings or provide dir_path parameter.",
        )
    directory = Path(scan_path).expanduser().resolve()
    if not directory.exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Directory does not exist: {scan_path}",
        )

    # Create background task
    task = _sync_task_manager.create_task(base_id, force_rebuild)
    if not task:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A sync task is already running for this knowledge base")

    # Fire-and-forget background coroutine
    asyncio.create_task(_run_sync_task(task, base_id, dir_path, force_rebuild))

    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={
            "task_id": task.task_id,
            "base_id": base_id,
            "status": "pending",
            "message": "Sync task started",
        },
    )


@router.get("/by-id/{base_id}/sync-status")
async def get_sync_status(base_id: str):
    """Get the sync task status for a knowledge base."""
    # Check active task first
    task = _sync_task_manager.get_active_task_for_base(base_id)
    if not task:
        # No active task - return idle status
        return {"base_id": base_id, "status": "idle", "task_id": None}
    return task.to_dict()


@router.get("/sync-task/{task_id}")
async def get_sync_task_status(task_id: str):
    """Get a specific sync task status by task_id."""
    task = _sync_task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Task not found: {task_id}")
    return task.to_dict()


@router.post("/by-id/{base_id}/sync-cancel")
async def cancel_sync(base_id: str):
    """Cancel the active sync task for a knowledge base.

    Force-cancels any running or pending sync task and marks it as failed.
    """
    task = _sync_task_manager.cancel_task(base_id)
    if not task:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"detail": "No active task for this knowledge base", "base_id": base_id},
        )
    return JSONResponse(
    status_code=status.HTTP_200_OK, content=task.to_dict())
@router.post("/by-id/{base_id}/auto-sync")
async def trigger_auto_sync(base_id: str):
    """Manually trigger auto-sync for a knowledge base

    Checks for new files in the watch directory and syncs them.
    This is the same operation the background scheduler performs.

    Args:
        base_id: Knowledge base ID

    Returns:
        Sync results
    """
    manager = get_base_manager()
    kb = manager.get_base(base_id)
    if not kb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Knowledge base not found: {base_id}")

    if not kb.settings.watch_dir:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No watch directory configured for this knowledge base.",
        )

    try:
        from dawei.knowledge.sync_scheduler import sync_scheduler
        result = await sync_scheduler.sync_base(base_id)
    except Exception as e:
        logger.error(f"Auto-sync failed for {base_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Auto-sync failed: {str(e)}",
        )

    if result is None:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"success": True, "message": "No sync needed", "imported": 0},
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "base_id": base_id,
            "message": f"Auto-synced {result.get('imported', 0)} files",
            "imported": result.get("imported", 0),
            "chunks": result.get("chunks", 0),
            "errors": result.get("errors"),
        },
    )


# ============================================================================
# Search Endpoints
# ============================================================================


@router.post("/by-id/{base_id}/search")
async def search_in_base(
    base_id: str,
    query: str = Query(..., min_length=1, description="Search query"),
    mode: RetrievalMode = Query(RetrievalMode.HYBRID, description="Retrieval mode"),
    top_k: int = Query(5, ge=1, le=50, description="Number of results to return"),
):
    """Search within a specific knowledge base

    Args:
        base_id: Knowledge base ID
        query: Search query text
        mode: Retrieval mode (vector, fulltext, graph, hybrid)
        top_k: Maximum number of results to return

    Returns:
        Search results with scores and metadata
    """
    import time

    manager = get_base_manager()
    kb = manager.get_base(base_id)
    if not kb:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "Knowledge base not found",
                "base_id": base_id,
                "message": f"Knowledge base '{base_id}' does not exist.",
                "available_bases": [base.id for base in manager.list_bases().items],
            },
        )

    base_storage_path = manager._get_storage_path(base_id)
    vector_db_path = base_storage_path / "vectors.db"

    if not vector_db_path.exists():
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "success": True,
                "query": query,
                "mode": mode,
                "top_k": top_k,
                "results": [],
                "total_count": 0,
                "vector_count": 0,
                "graph_count": 0,
                "fulltext_count": 0,
                "latency_ms": 0,
                "message": "Vector store not found. Please upload documents first.",
            },
        )

    start_time = time.time()

    # Initialize stores
    from dawei.knowledge.vector.sqlite_vec_store import SQLiteVecVectorStore

    vector_store = SQLiteVecVectorStore(
        db_path=str(vector_db_path),
        dimension=kb.settings.embedding_dimension,
    )
    await vector_store.initialize()

    fulltext_store = None
    graph_store = None

    try:
        fulltext_store = manager.get_fulltext_store(base_id)
        await fulltext_store.initialize()
    except Exception as e:
        logger.warning(f"Failed to initialize fulltext store: {e}")

    try:
        graph_store = manager.get_graph_store(base_id)
        await graph_store.initialize()
    except Exception as e:
        logger.warning(f"Failed to initialize graph store: {e}")

    # Use HybridRetriever
    from dawei.knowledge.models import RetrievalQuery
    from dawei.knowledge.retrieval.hybrid_retriever import HybridRetriever

    retriever = HybridRetriever(
        vector_store=vector_store,
        fulltext_store=fulltext_store,
        graph_store=graph_store,
        embedding_manager=manager.get_embedding_manager(base_id),
    )

    # Create retrieval query
    retrieval_query = RetrievalQuery(
        query=query,
        mode=mode,
        top_k=top_k,
        vector_weight=kb.settings.vector_weight,
        graph_weight=kb.settings.graph_weight,
        fulltext_weight=kb.settings.fulltext_weight,
    )

    # Execute search
    search_result = await retriever.retrieve(retrieval_query)

    latency_ms = (time.time() - start_time) * 1000

    # Convert to response format
    results = []
    for result in search_result.results:
        results.append(
            {
                "id": result.id,
                "content": result.content,
                "score": result.score,
                "source": result.source,
                "metadata": result.metadata,
            }
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "query": query,
            "mode": mode,
            "top_k": top_k,
            "results": results,
            "total_count": len(results),
            "vector_count": search_result.vector_count,
            "graph_count": search_result.graph_count,
            "fulltext_count": search_result.fulltext_count,
            "latency_ms": round(latency_ms, 2),
        },
    )


@router.post("/default/search")
async def search_default_base(
    query: str = Query(..., min_length=1, description="Search query"),
    mode: RetrievalMode = Query(RetrievalMode.HYBRID, description="Retrieval mode"),
    top_k: int = Query(5, ge=1, le=50, description="Number of results to return"),
):
    """Search in the default knowledge base

    Args:
        query: Search query text
        mode: Retrieval mode (vector, fulltext, graph, hybrid)
        top_k: Maximum number of results to return

    Returns:
        Search results with scores and metadata
    """
    manager = get_base_manager()
    default_kb = manager.get_default_base()
    if not default_kb:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No default knowledge base found",
        )

    # Delegate to base-specific search
    return await search_in_base(default_kb.id, query, mode, top_k)


@router.get("/by-id/{base_id}/graph/entities")
async def get_graph_entities(
    base_id: str,
    limit: int = Query(100, ge=1, le=10000, description="Maximum number of entities to return"),
    offset: int = Query(0, ge=0, description="Number of entities to skip"),
    entity_type: str | None = Query(None, description="Filter by entity type"),
):
    """Get entities from knowledge graph

    Args:
        base_id: Knowledge base ID
        limit: Maximum number of entities
        offset: Number of entities to skip
        entity_type: Optional entity type filter

    Returns:
        List of graph entities
    """
    manager = get_base_manager()
    kb = manager.get_base(base_id)
    if not kb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")

    try:
        # Simple implementation: query from database
        import aiosqlite

        base_storage_path = manager._get_storage_path(base_id)
        graph_db_path = base_storage_path / "graph.db"

        # Check if graph database exists first
        if not graph_db_path.exists():
            logger.info(f"Graph database not found for base {base_id}, returning empty result")
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "success": True,
                    "entities": [],
                    "total": 0,
                },
            )

        # Try to initialize graph store (creates tables if needed)
        try:
            graph_store = manager.get_graph_store(base_id)
            await graph_store.initialize()
        except Exception as init_error:
            logger.error(f"Failed to initialize graph store: {init_error}", exc_info=True)
            # If initialization fails, return empty result rather than error
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "success": True,
                    "entities": [],
                    "total": 0,
                    "error": f"Graph store initialization failed: {str(init_error)}",
                },
            )

        # Get all entities (filter by type if specified)
        entities = []
        entity_ids = set()

        async with aiosqlite.connect(graph_db_path) as db:
            db.row_factory = aiosqlite.Row

            # Build query
            query = "SELECT * FROM entities"
            params = []

            if entity_type:
                query += " WHERE type = ?"
                params.append(entity_type)

            query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()

            for row in rows:
                entities.append(
                    {
                        "id": row["id"],
                        "type": row["type"],
                        "name": row["name"],
                        "description": row["description"],
                        "properties": json.loads(row["properties"]) if row["properties"] else {},
                        "base_id": row["base_id"],
                        "created_at": row["created_at"],
                    }
                )
                entity_ids.add(row["id"])

        # Get total count
        async with aiosqlite.connect(graph_db_path) as db:
            count_query = "SELECT COUNT(*) FROM entities"
            if entity_type:
                count_query += " WHERE type = ?"
                cursor = await db.execute(count_query, [entity_type] if entity_type else ())
            else:
                cursor = await db.execute(count_query)
            total = (await cursor.fetchone())[0]

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "success": True,
                "entities": entities,
                "total": total,
            },
        )

    except Exception as e:
        logger.error(f"Failed to get graph entities: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to get graph entities: {str(e)}")


@router.get("/by-id/{base_id}/graph/relations")
async def get_graph_relations(
    base_id: str,
    limit: int = Query(100, ge=1, le=10000, description="Maximum number of relations to return"),
    offset: int = Query(0, ge=0, description="Number of relations to skip"),
    relation_type: str | None = Query(None, description="Filter by relation type"),
):
    """Get relations from knowledge graph

    Args:
        base_id: Knowledge base ID
        limit: Maximum number of relations
        offset: Number of relations to skip
        relation_type: Optional relation type filter

    Returns:
        List of graph relations
    """
    manager = get_base_manager()
    kb = manager.get_base(base_id)
    if not kb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")

    try:
        # Get relations from database
        import aiosqlite

        base_storage_path = manager._get_storage_path(base_id)
        graph_db_path = base_storage_path / "graph.db"

        # Check if graph database exists first
        if not graph_db_path.exists():
            logger.info(f"Graph database not found for base {base_id}, returning empty result")
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "success": True,
                    "relations": [],
                    "total": 0,
                },
            )

        # Try to initialize graph store (creates tables if needed)
        try:
            graph_store = manager.get_graph_store(base_id)
            await graph_store.initialize()
        except Exception as init_error:
            logger.error(f"Failed to initialize graph store: {init_error}", exc_info=True)
            # If initialization fails, return empty result rather than error
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "success": True,
                    "relations": [],
                    "total": 0,
                    "error": f"Graph store initialization failed: {str(init_error)}",
                },
            )

        async with aiosqlite.connect(graph_db_path) as db:
            db.row_factory = aiosqlite.Row

            # Build query
            query = "SELECT * FROM relations"
            params = []

            if relation_type:
                query += " WHERE relation_type = ?"
                params.append(relation_type)

            query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()

            relations = []
            for row in rows:
                relations.append(
                    {
                        "id": row["id"],
                        "from_entity": row["from_entity"],
                        "to_entity": row["to_entity"],
                        "relation_type": row["relation_type"],
                        "properties": json.loads(row["properties"]) if row["properties"] else {},
                        "weight": row["weight"],
                        "base_id": row["base_id"],
                        "created_at": row["created_at"],
                    }
                )

        # Get total count
        async with aiosqlite.connect(graph_db_path) as db:
            count_query = "SELECT COUNT(*) FROM relations"
            if relation_type:
                count_query += " WHERE relation_type = ?"
                cursor = await db.execute(count_query, [relation_type] if relation_type else ())
            else:
                cursor = await db.execute(count_query)
            total = (await cursor.fetchone())[0]

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "success": True,
                "relations": relations,
                "total": total,
            },
        )

    except Exception as e:
        logger.error(f"Failed to get graph relations: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to get graph relations: {str(e)}")


@router.get("/by-id/{base_id}/graph/entities/{entity_id}/sources")
async def get_entity_sources(
    base_id: str,
    entity_id: str,
):
    """Get source provenance for a graph entity — trace back to original document title and page number

    Args:
        base_id: Knowledge base ID
        entity_id: Graph entity ID

    Returns:
        Entity with list of source documents and page numbers
    """
    manager = get_base_manager()
    kb = manager.get_base(base_id)
    if not kb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")

    try:
        import aiosqlite

        base_storage_path = manager._get_storage_path(base_id)
        graph_db_path = base_storage_path / "graph.db"

        if not graph_db_path.exists():
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={"entity": None, "sources": []},
            )

        # Query entity
        async with aiosqlite.connect(graph_db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM entities WHERE id = ?", (entity_id,))
            row = await cursor.fetchone()

        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found")

        properties = json.loads(row["properties"]) if row["properties"] else {}
        source_doc_ids = properties.get("source_documents", [])
        source_chunk_ids = properties.get("source_chunks", [])
        source_pages = sorted(p for p in properties.get("source_pages", []) if p is not None)

        # Build source list: for each doc_id, look up document title
        sources = []
        if source_doc_ids or source_chunk_ids:
            # Try to get document titles from vector store metadata
            vector_db_path = base_storage_path / "vectors.db"
            if vector_db_path.exists():
                async with aiosqlite.connect(vector_db_path) as vdb:
                    vdb.row_factory = aiosqlite.Row
                    for chunk_id in source_chunk_ids:
                        try:
                            cursor = await vdb.execute(
                                "SELECT metadata, content FROM vectors WHERE id = ?",
                                (chunk_id,),
                            )
                            vrow = await cursor.fetchone()
                            if vrow:
                                meta = json.loads(vrow["metadata"]) if vrow["metadata"] else {}
                                sources.append(
                                    {
                                        "document_id": meta.get("document_id", ""),
                                        "document_title": meta.get("file_name", ""),
                                        "chunk_id": chunk_id,
                                        "chunk_index": meta.get("chunk_index"),
                                        "page_number": meta.get("page_number"),
                                        "content": (vrow["content"] or "")[:200],
                                    }
                                )
                        except Exception:
                            pass

        # Deduplicate sources by chunk_id
        seen_chunks = set()
        deduped_sources = []
        for s in sources:
            if s["chunk_id"] not in seen_chunks:
                seen_chunks.add(s["chunk_id"])
                deduped_sources.append(s)

        entity_data = {
            "id": row["id"],
            "type": row["type"],
            "name": row["name"],
            "description": row["description"],
            "properties": properties,
        }

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "entity": entity_data,
                "sources": deduped_sources,
                "source_documents": source_doc_ids,
                "source_pages": source_pages,
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get entity sources: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get entity sources: {str(e)}",
        )


# ============================================================================
# LLM Config Endpoint (for extraction strategy)
# ============================================================================


@router.get("/llm-configs")
async def list_llm_configs():
    """List all available LLM configurations for knowledge extraction.

    Returns a list of configured LLM providers that can be used for
    knowledge extraction when the strategy is set to 'llm'.
    """
    try:
        from dawei.llm_api.llm_provider import LLMProvider
        from dawei import get_dawei_home

        workspace_root = str(get_dawei_home())
        provider = LLMProvider(workspace_root=workspace_root)
        all_configs = provider.get_all_configs()

        configs_list = []
        for config_name, config_data in all_configs.items():
            model_id = ""
            if hasattr(config_data, "config") and hasattr(config_data.config, "model_id"):
                model_id = config_data.config.model_id
            configs_list.append({"llm_id": config_name, "model_id": model_id})

        return {"success": True, "configs": sorted(configs_list, key=lambda x: x["llm_id"])}
    except Exception as e:
        logger.error(f"Failed to list LLM configs: {e}", exc_info=True)
        return {"success": True, "configs": []}
