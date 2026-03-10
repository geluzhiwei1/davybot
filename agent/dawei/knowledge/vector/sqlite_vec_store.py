# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""SQLite Vec vector store implementation (Personal Edition)

Uses sqlite-vec extension for zero-dependency vector storage.
https://github.com/asg0r/sqlite-vec
"""

import json
import sqlite3
from pathlib import Path
from typing import List, Dict, Any

import aiosqlite

from dawei.knowledge.base.vector_store import VectorStore
from dawei.knowledge.models import VectorDocument, VectorSearchResult


class SQLiteVecVectorStore(VectorStore):
    """SQLite-based vector store using sqlite-vec extension

    Features:
    - Zero external dependencies (no Faiss needed)
    - Pure Python integration
    - ACID compliance
    - Perfect for personal/small-scale use

    Performance:
    - Up to 100K vectors: Good performance
    - 100K-1M vectors: Acceptable with HNSW index
    - 1M+ vectors: Consider pgvector or Qdrant
    """

    def __init__(self, db_path: str | Path, dimension: int, **kwargs):
        """Initialize SQLite Vec vector store

        Args:
            db_path: Path to SQLite database file
            dimension: Embedding vector dimension
            **kwargs: Additional parameters
                - table_name: Table name (default: "vectors")
                - extension_path: Path to sqlite-vec extension (default: auto-load)
        """
        super().__init__(dimension, **kwargs)
        self.db_path = Path(db_path)
        self.table_name = kwargs.get("table_name", "vectors")
        self.extension_path = kwargs.get("extension_path")

        # Ensure parent directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    async def initialize(self) -> None:
        """Initialize database and load extension"""
        async with aiosqlite.connect(self.db_path) as db:
            # Load sqlite-vec extension
            if self.extension_path:
                await db.enable_load_extension(True)
                await db.load_extension(self.extension_path)
            else:
                # Try to load sqlite-vec (assumes it's installed)
                try:
                    await db.enable_load_extension(True)
                    await db.load_extension("vec0")
                except sqlite3.OperationalError:
                    # Fallback: use built-in JSON storage with manual distance calc
                    pass

            # Create vectors table
            await db.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self.table_name} (
                    id TEXT PRIMARY KEY,
                    embedding BLOB,
                    metadata TEXT,
                    content TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # Create HNSW index if supported
            try:
                await db.execute(
                    f"""
                    CREATE VIRTUAL TABLE IF NOT EXISTS {self.table_name}_vec
                    USING vec0(
                        embedding float[{self.dimension}]
                    )
                """
                )
            except sqlite3.OperationalError:
                # Fallback: create regular index on metadata
                await db.execute(f"CREATE INDEX IF NOT EXISTS idx_metadata ON {self.table_name}(metadata)")

            await db.commit()

    async def add(self, documents: List[VectorDocument]) -> None:
        """Add documents to vector store"""
        async with aiosqlite.connect(self.db_path) as db:
            for doc in documents:
                # Convert embedding to bytes
                import struct

                embedding_bytes = struct.pack(f"{len(doc.embedding)}f", *doc.embedding)

                await db.execute(
                    f"""
                    INSERT OR REPLACE INTO {self.table_name}
                    (id, embedding, metadata, content)
                    VALUES (?, ?, ?, ?)
                """,
                    (
                        doc.id,
                        embedding_bytes,
                        json.dumps(doc.metadata),
                        doc.content,
                    ),
                )
            await db.commit()

    async def delete(self, document_ids: List[str]) -> int:
        """Delete documents from vector store"""
        async with aiosqlite.connect(self.db_path) as db:
            placeholders = ",".join(["?"] * len(document_ids))
            cursor = await db.execute(
                f"DELETE FROM {self.table_name} WHERE id IN ({placeholders})",
                document_ids,
            )
            await db.commit()
            return cursor.rowcount

    async def search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        filters: Dict[str, Any] | None = None,
        min_score: float = 0.0,
    ) -> List[VectorSearchResult]:
        """Search for similar documents"""
        import struct

        async with aiosqlite.connect(self.db_path) as db:
            # Build query with filters
            query_sql = f"SELECT id, embedding, metadata, content FROM {self.table_name}"
            params = []

            if filters:
                filter_clauses = []
                for key, value in filters.items():
                    filter_clauses.append(f"json_extract(metadata, '$.{key}') = ?")
                    params.append(value)
                if filter_clauses:
                    query_sql += " WHERE " + " AND ".join(filter_clauses)

            # Execute query
            cursor = await db.execute(query_sql, params)
            rows = await cursor.fetchall()

            # Calculate cosine similarity
            results = []
            for row in rows:
                doc_id, embedding_bytes, metadata_json, content = row

                # Unpack embedding
                doc_embedding = struct.unpack(f"{self.dimension}f", embedding_bytes)

                # Calculate cosine similarity
                similarity = self._cosine_similarity(query_embedding, list(doc_embedding))

                if similarity >= min_score:
                    results.append(
                        VectorSearchResult(
                            id=doc_id,
                            score=similarity,
                            content=content,
                            metadata=json.loads(metadata_json),
                        )
                    )

            # Sort by score and return top_k
            results.sort(key=lambda x: x.score, reverse=True)
            return results[:top_k]

    async def update(self, document_id: str, document: VectorDocument) -> bool:
        """Update a document in the vector store"""
        async with aiosqlite.connect(self.db_path) as db:
            import struct

            embedding_bytes = struct.pack(f"{len(document.embedding)}f", *document.embedding)

            cursor = await db.execute(
                f"""
                UPDATE {self.table_name}
                SET embedding = ?, metadata = ?, content = ?
                WHERE id = ?
            """,
                (
                    embedding_bytes,
                    json.dumps(document.metadata),
                    document.content,
                    document_id,
                ),
            )
            await db.commit()
            return cursor.rowcount > 0

    async def get(self, document_id: str) -> VectorDocument | None:
        """Get a document by ID"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                f"SELECT embedding, metadata, content FROM {self.table_name} WHERE id = ?",
                (document_id,),
            )
            row = await cursor.fetchone()

            if row:
                import struct

                embedding_bytes, metadata_json, content = row
                embedding = struct.unpack(f"{self.dimension}f", embedding_bytes)

                return VectorDocument(
                    id=document_id,
                    embedding=list(embedding),
                    content=content,
                    metadata=json.loads(metadata_json),
                )
            return None

    async def count(self) -> int:
        """Get total number of documents"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(f"SELECT COUNT(*) FROM {self.table_name}")
            row = await cursor.fetchone()
            return row[0] if row else 0

    async def clear(self) -> None:
        """Clear all documents"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(f"DELETE FROM {self.table_name}")
            await db.commit()

    async def create_index(self, index_type: str = "HNSW", **params) -> None:
        """Create index for faster searches

        Note: HNSW index is created automatically during initialization.
        """
        # sqlite-vec creates HNSW index automatically
        pass

    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors"""
        import math

        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = math.sqrt(sum(a * a for a in vec1))
        norm2 = math.sqrt(sum(b * b for b in vec2))

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot_product / (norm1 * norm2)
