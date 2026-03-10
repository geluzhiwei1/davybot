# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Knowledge Base Management API - Multi-tenancy support"""

import json
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
from dawei.knowledge.models import RetrievalMode

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

    # Index in graph store with knowledge extraction
    try:
        graph_store = manager.get_graph_store(base_id)
        await graph_store.initialize()

        from dawei.knowledge.models import GraphEntity, GraphRelation
        from dawei.knowledge.extraction import (
            ExtractionFactory,
            ExtractionStrategyType,
        )

        # Create document entity
        doc_entity = GraphEntity(
            id=f"doc_{document.id}",
            type="document",
            name=file.filename,
            description=f"Document: {file.filename}",
            properties={
                "file_size": document.metadata.file_size,
                "file_type": document.metadata.file_type,
            },
            base_id=base_id,
        )
        await graph_store.add_entity(doc_entity)

        # Get extraction strategy from knowledge base settings
        extraction_strategy = kb.settings.extraction_strategy or "rule_based"

        # Create extractor
        extractor = ExtractionFactory.create(extraction_strategy)

        # Extract entities and relations from each chunk
        total_entities = 1  # Start with document entity
        total_relations = 0
        entity_id_map = {}  # Map entity names to graph IDs

        for i, chunk in enumerate(chunks):
            # Create chunk entity
            chunk_entity = GraphEntity(
                id=chunk.id,
                type="chunk",
                name=f"Chunk {i}",
                description=chunk.content[:100] + "..." if len(chunk.content) > 100 else chunk.content,
                properties={
                    "chunk_index": i,
                    "document_id": chunk.document_id,
                    "content": chunk.content,
                },
                base_id=base_id,
            )
            await graph_store.add_entity(chunk_entity)
            total_entities += 1

            # Document -> chunk relation
            doc_chunk_relation = GraphRelation(
                id=f"rel_{doc_entity.id}_{chunk.id}",
                from_entity=doc_entity.id,
                to_entity=chunk.id,
                relation_type="contains",
                properties={"order": i},
                base_id=base_id,
            )
            await graph_store.add_relation(doc_chunk_relation)
            total_relations += 1

            # Knowledge extraction from chunk content
            try:
                extraction_result = await extractor.extract(
                    chunk.content,
                    chunk_id=chunk.id,
                    document_id=document.id,
                )

                # Add extracted entities
                for entity in extraction_result.entities:
                    # Create unique ID for entity (based on name)
                    entity_id = f"entity_{hash(entity.name)}_{base_id}"

                    # Store mapping for relations
                    if entity.name not in entity_id_map:
                        entity_id_map[entity.name] = entity_id

                        # Create graph entity
                        graph_entity = GraphEntity(
                            id=entity_id,
                            type=entity.type,
                            name=entity.name,
                            description=entity.properties.get("description", ""),
                            properties={
                                **entity.properties,
                                "confidence": entity.confidence,
                                "source": "extraction",
                            },
                            base_id=base_id,
                        )
                        await graph_store.add_entity(graph_entity)
                        total_entities += 1

                    # Chunk -> entity relation (mentions)
                    chunk_entity_relation = GraphRelation(
                        id=f"rel_{chunk.id}_{entity_id_map[entity.name]}",
                        from_entity=chunk.id,
                        to_entity=entity_id_map[entity.name],
                        relation_type="mentions",
                        properties={
                            "confidence": entity.confidence,
                            "strategy": extraction_strategy,
                        },
                        base_id=base_id,
                    )
                    await graph_store.add_relation(chunk_entity_relation)
                    total_relations += 1

                # Add extracted relations
                for relation in extraction_result.relations:
                    from_id = entity_id_map.get(relation.from_entity)
                    to_id = entity_id_map.get(relation.to_entity)

                    if from_id and to_id:
                        graph_relation = GraphRelation(
                            id=f"rel_{from_id}_{to_id}_{relation.relation_type}",
                            from_entity=from_id,
                            to_entity=to_id,
                            relation_type=relation.relation_type,
                            properties={
                                **relation.properties,
                                "confidence": relation.confidence,
                                "strategy": extraction_strategy,
                            },
                            base_id=base_id,
                        )
                        await graph_store.add_relation(graph_relation)
                        total_relations += 1

            except Exception as e:
                logger.warning(f"Failed to extract knowledge from chunk {i}: {e}")
                # Non-fatal, continue with next chunk

        logger.info(f"Graph indexing complete: {total_entities} entities, {total_relations} relations (strategy: {extraction_strategy})")
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


@router.post("/{base_id}/reindex")
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
    from dawei.knowledge.models import VectorDocument
    from dawei.knowledge.parsers.docx_parser import DocxParser
    from dawei.knowledge.parsers.markdown_parser import MarkdownParser
    from dawei.knowledge.parsers.pdf_parser import PDFParser
    from dawei.knowledge.parsers.text_parser import TextParser
    from dawei.knowledge.vector.sqlite_vec_store import SQLiteVecVectorStore
    from dawei.knowledge.models import GraphEntity, GraphRelation
    from dawei.knowledge.extraction import (
        ExtractionFactory,
        ExtractionStrategyType,
    )

    # Select appropriate parser based on file type
    parser_map = {
        ".pdf": PDFParser,
        ".docx": DocxParser,
        ".txt": TextParser,
        ".md": MarkdownParser,
        ".markdown": MarkdownParser,
    }

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
    embedding_service = manager.get_embedding_manager(base_id, model_type="MINILM")

    # Determine chunk size from knowledge base settings
    chunk_size = kb.settings.chunk_size
    chunk_overlap = kb.settings.chunk_overlap
    chunk_strategy_name = kb.settings.chunk_strategy

    strategy_map = {
        "recursive": ChunkingStrategy.RECURSIVE,
        "semantic": ChunkingStrategy.SEMANTIC,
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
    extractor = ExtractionFactory.create(extraction_strategy)

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
            if file_extension not in parser_map:
                logger.warning(f"Unsupported file type: {file_extension}, skipping {file_path.name}")
                errors.append(f"Skipped {file_path.name}: unsupported file type")
                continue

            parser_class = parser_map.get(file_extension, TextParser)
            parser = parser_class()

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

            # Create document entity
            doc_entity = GraphEntity(
                id=f"doc_{document.id}",
                type="document",
                name=file_path.name,
                description=f"Document: {file_path.name}",
                properties={
                    "file_size": document.metadata.file_size,
                    "file_type": document.metadata.file_type,
                },
                base_id=base_id,
            )
            await graph_store.add_entity(doc_entity)
            total_entities += 1

            # Create chunk entities and extract knowledge
            entity_id_map = {}

            for i, chunk in enumerate(chunks):
                # Create chunk entity
                chunk_entity = GraphEntity(
                    id=chunk.id,
                    type="chunk",
                    name=f"Chunk {i}",
                    description=chunk.content[:100] + "..." if len(chunk.content) > 100 else chunk.content,
                    properties={
                        "chunk_index": i,
                        "document_id": chunk.document_id,
                        "content": chunk.content,
                    },
                    base_id=base_id,
                )
                await graph_store.add_entity(chunk_entity)
                total_entities += 1

                # Document -> chunk relation
                doc_chunk_relation = GraphRelation(
                    id=f"rel_{doc_entity.id}_{chunk.id}",
                    from_entity=doc_entity.id,
                    to_entity=chunk.id,
                    relation_type="contains",
                    properties={"order": i},
                    base_id=base_id,
                )
                await graph_store.add_relation(doc_chunk_relation)
                total_relations += 1

                # Knowledge extraction from chunk content
                try:
                    extraction_result = await extractor.extract(
                        chunk.content,
                        chunk_id=chunk.id,
                        document_id=document.id,
                    )

                    # Add extracted entities
                    for entity in extraction_result.entities:
                        entity_id = f"entity_{hash(entity.name)}_{base_id}"

                        if entity.name not in entity_id_map:
                            entity_id_map[entity.name] = entity_id

                            graph_entity = GraphEntity(
                                id=entity_id,
                                type=entity.type,
                                name=entity.name,
                                description=entity.properties.get("description", ""),
                                properties={
                                    **entity.properties,
                                    "confidence": entity.confidence,
                                    "source": "extraction",
                                },
                                base_id=base_id,
                            )
                            await graph_store.add_entity(graph_entity)
                            total_entities += 1

                        # Chunk -> entity relation
                        chunk_entity_relation = GraphRelation(
                            id=f"rel_{chunk.id}_{entity_id_map[entity.name]}",
                            from_entity=chunk.id,
                            to_entity=entity_id_map[entity.name],
                            relation_type="mentions",
                            properties={
                                "confidence": entity.confidence,
                                "strategy": extraction_strategy,
                            },
                            base_id=base_id,
                        )
                        await graph_store.add_relation(chunk_entity_relation)
                        total_relations += 1

                    # Add extracted relations
                    for relation in extraction_result.relations:
                        from_id = entity_id_map.get(relation.from_entity)
                        to_id = entity_id_map.get(relation.to_entity)

                        if from_id and to_id:
                            graph_relation = GraphRelation(
                                id=f"rel_{from_id}_{to_id}_{relation.relation_type}",
                                from_entity=from_id,
                                to_entity=to_id,
                                relation_type=relation.relation_type,
                                properties={
                                    **relation.properties,
                                    "confidence": relation.confidence,
                                    "strategy": extraction_strategy,
                                },
                                base_id=base_id,
                            )
                            await graph_store.add_relation(graph_relation)
                            total_relations += 1

                except Exception as e:
                    logger.warning(f"Failed to extract knowledge from chunk {i}: {e}")

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


@router.post("/{base_id}/documents/{document_id}/reindex")
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
# Search Endpoints
# ============================================================================


@router.post("/{base_id}/search")
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
    from dawei.knowledge.retrieval.hybrid_retriever import HybridRetriever
    from dawei.knowledge.models import RetrievalQuery

    retriever = HybridRetriever(
        vector_store=vector_store,
        fulltext_store=fulltext_store,
        graph_store=graph_store,
        embedding_manager=manager.get_embedding_manager(base_id, model_type="MINILM"),
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


@router.get("/{base_id}/graph/entities")
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


@router.get("/{base_id}/graph/relations")
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
