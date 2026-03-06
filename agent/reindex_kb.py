#!/usr/bin/env python3
"""Re-index documents in a knowledge base"""

import asyncio
import sys
import os
import argparse
from pathlib import Path

# IMPORTANT: Set HF mirror BEFORE importing anything
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

sys.path.insert(0, str(Path(__file__).parent))

from dawei import get_dawei_home
from dawei.knowledge.base_manager import KnowledgeBaseManager
from dawei.knowledge.parsers.text_parser import TextParser
from dawei.knowledge.parsers.pdf_parser import PDFParser
from dawei.knowledge.chunking.chunker import ChunkingConfig, ChunkingStrategy, TextChunker
from dawei.knowledge.vector.sqlite_vec_store import SQLiteVecVectorStore
from dawei.knowledge.models import VectorDocument


async def reindex_kb(base_id: str):
    """Re-index all documents in the specified knowledge base

    Args:
        base_id: Knowledge base ID (e.g., "kb_aa2a0527")
    """

    # Initialize manager
    knowledge_path = get_dawei_home() / "knowledge"
    manager = KnowledgeBaseManager(root_path=str(knowledge_path))

    # Get knowledge base
    kb = manager.get_base(base_id)
    if not kb:
        print(f"❌ Knowledge base '{base_id}' not found")
        return

    print(f"✅ Found knowledge base: {kb.name}")

    # Get uploads directory
    base_storage_path = manager._get_storage_path(base_id)
    uploads_dir = base_storage_path / "uploads"
    vector_db_path = base_storage_path / "vectors.db"

    # List files
    files = list(uploads_dir.iterdir())
    print(f"\n📁 Found {len(files)} files to re-index")

    # Initialize vector store
    vector_store = SQLiteVecVectorStore(
        db_path=str(vector_db_path),
        dimension=kb.settings.embedding_dimension,
    )
    await vector_store.initialize()

    # Get embedding service
    embedding_service = manager.get_embedding_manager(base_id, model_type="MINILM")

    # Process each file
    for file_path in files:
        if not file_path.is_file():
            continue

        print(f"\n📄 Processing: {file_path.name}")

        # Determine parser
        ext = file_path.suffix.lower()
        if ext == ".pdf":
            parser = PDFParser()
        elif ext in [".md", ".txt"]:
            parser = TextParser()
        else:
            print(f"   ⚠️  Skipping unsupported file type: {ext}")
            continue

        try:
            # Parse document
            document = await parser.parse(file_path)
            print(f"   ✅ Parsed: {len(document.content)} characters")

            # Chunk document
            chunker = TextChunker(
                config=ChunkingConfig(
                    strategy=ChunkingStrategy.RECURSIVE,
                    chunk_size=kb.settings.chunk_size,
                    chunk_overlap=kb.settings.chunk_overlap,
                ),
            )
            chunks = await chunker.chunk(document)
            print(f"   ✅ Created {len(chunks)} chunks")

            # Generate embeddings
            chunk_texts = [chunk.content for chunk in chunks]
            embeddings = await embedding_service.embed_documents(chunk_texts)
            print(f"   ✅ Generated {len(embeddings)} embeddings")

            # Create vector documents
            vector_docs = []
            for chunk, embedding in zip(chunks, embeddings, strict=True):
                # Convert metadata to JSON-serializable format
                metadata_copy = dict(chunk.metadata)
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
                        "base_id": base_id,
                        "file_name": file_path.name,
                    },
                )
                vector_docs.append(vector_doc)

            # Add to vector store
            await vector_store.add(vector_docs)
            print(f"   ✅ Added {len(vector_docs)} chunks to vector store")

        except Exception as e:
            print(f"   ❌ Failed: {e}")
            import traceback
            traceback.print_exc()

    # Verify
    import aiosqlite
    async with aiosqlite.connect(vector_db_path) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM vectors")
        count = (await cursor.fetchone())[0]
        print(f"\n✅ Total chunks in database: {count}")

    # Update stats
    kb.stats.indexed_documents = len(files)
    kb.stats.total_documents = len(files)
    manager._save_metadata()

    print("\n✅ Re-indexing complete!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Re-index documents in a knowledge base",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Re-index a specific knowledge base
  %(prog)s kb_aa2a0527

  # List all available knowledge bases
  %(prog)s --list
        """
    )
    parser.add_argument(
        "base_id",
        nargs="?",
        help="Knowledge base ID to re-index (e.g., kb_aa2a0527)"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all available knowledge bases and exit"
    )

    args = parser.parse_args()

    # Handle --list flag
    if args.list:
        knowledge_path = get_dawei_home() / "knowledge"
        manager = KnowledgeBaseManager(root_path=str(knowledge_path))

        print("📚 Available Knowledge Bases:")
        print("-" * 60)

        bases = manager.list_bases()
        if not bases:
            print("❌ No knowledge bases found")
            sys.exit(1)

        for base in bases:
            print(f"  ID: {base.id}")
            print(f"  Name: {base.name}")
            print(f"  Description: {base.description or 'N/A'}")
            print(f"  Documents: {base.stats.total_documents}")
            print("-" * 60)

        sys.exit(0)

    # Validate base_id argument
    if not args.base_id:
        parser.error("base_id is required (or use --list to see available bases)")

    # Run re-indexing
    asyncio.run(reindex_kb(args.base_id))
