# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""SQLite FTS5 full-text search implementation"""

import logging
import sqlite3
import aiosqlite
from pathlib import Path
from typing import List, Dict, Any, Optional

from dawei.knowledge.base.fulltext_store import FullTextStore
from dawei.knowledge.models import DocumentChunk

logger = logging.getLogger(__name__)


class SQLiteFTSStore(FullTextStore):
    """SQLite FTS5 full-text search implementation

    Uses SQLite's FTS5 (Full-Text Search) extension for fast keyword search.
    """

    def __init__(
        self,
        db_path: str | Path,
        table_name: str = "fts_index",
    ):
        """Initialize SQLite FTS store

        Args:
            db_path: Path to SQLite database file
            table_name: Name of FTS table
        """
        super().__init__(db_path=str(db_path), table_name=table_name)
        self.db_path = Path(db_path)
        self.table_name = table_name

    async def initialize(self) -> None:
        """Initialize FTS table

        Creates FTS5 virtual table if it doesn't exist. Safe to call multiple times.
        """
        async with aiosqlite.connect(self.db_path) as db:
            # Check if FTS table already exists
            cursor = await db.execute(
                f"SELECT name FROM sqlite_master WHERE type='table' AND name='{self.table_name}'"
            )
            existing_tables = await cursor.fetchall()

            if existing_tables:
                logger.info(f"FTS table already exists: {self.table_name}")
                return

            # Create FTS5 virtual table
            await db.execute(
                f"""CREATE VIRTUAL TABLE {self.table_name}
                USING fts5(
                    chunk_id UNINDEXED,
                    document_id UNINDEXED,
                    content,
                    file_name,
                    metadata,
                    tokenize='porter unicode61'
                )"""
            )

            await db.commit()
            logger.info(f"Initialized FTS table: {self.table_name}")

    async def add_documents(self, chunks: List[DocumentChunk]) -> None:
        """Add document chunks to full-text index

        Args:
            chunks: Document chunks to index
        """
        import json

        success_count = 0
        error_count = 0

        async with aiosqlite.connect(self.db_path) as db:
            for chunk in chunks:
                try:
                    # Convert metadata to JSON string
                    # Use model_dump() instead of dict() for Pydantic models
                    if hasattr(chunk.metadata, 'model_dump'):
                        metadata_dict = chunk.metadata.model_dump()
                    else:
                        metadata_dict = dict(chunk.metadata)

                    metadata_json = json.dumps(metadata_dict, default=str)

                    # Extract file name from metadata
                    file_name = metadata_dict.get('file_name', metadata_dict.get('file_path', ''))

                    # Use document_id from metadata if available, otherwise from chunk
                    document_id = metadata_dict.get('document_id', chunk.document_id)

                    # Insert into FTS table
                    await db.execute(
                        f"""INSERT INTO {self.table_name}
                        (chunk_id, document_id, content, file_name, metadata)
                        VALUES (?, ?, ?, ?, ?)""",
                        (chunk.id, document_id, chunk.content, file_name, metadata_json)
                    )

                    success_count += 1

                except Exception as e:
                    error_count += 1
                    logger.error(f"Failed to add chunk {chunk.id} to FTS index: {e}")

            await db.commit()

        logger.info(f"Added {success_count} chunks to FTS index, {error_count} errors")

    async def search(
        self,
        query: str,
        top_k: int = 5,
        filters: Dict[str, Any] | None = None,
    ) -> List[tuple[str, float]]:
        """Search documents by text query

        Args:
            query: Search query (supports FTS5 query syntax)
            top_k: Number of results to return
            filters: Optional metadata filters

        Returns:
            List of (chunk_id, score) tuples
        """
        async with aiosqlite.connect(self.db_path) as db:
            # Build query with optional filters
            where_clauses = []
            params = []

            if filters:
                for key, value in filters.items():
                    where_clauses.append(f"json_extract(metadata, '$.{key}') = ?")
                    params.append(value)

            where_sql = ""
            if where_clauses:
                where_sql = " AND " + " AND ".join(where_clauses)

            # FTS5 search with BM25 ranking
            # Use simple query or match query
            fts_query = query.strip()
            if " " in fts_query:
                # Multi-word query - use phrase search or AND
                fts_query = f'"{fts_query}"'  # Exact phrase
            else:
                # Single word - direct search
                fts_query = fts_query

            sql = f"""
                SELECT chunk_id, bm25({self.table_name}) as score
                FROM {self.table_name}
                WHERE {self.table_name} MATCH ?{where_sql}
                ORDER BY score
                LIMIT ?
            """

            params = [fts_query] + params + [top_k]

            try:
                cursor = await db.execute(sql, params)
                rows = await cursor.fetchall()

                # Convert BM25 score (lower is better) to similarity score (0-1, higher is better)
                # BM25 typically ranges 0-20, we invert to 0-1
                results = []
                for chunk_id, bm25_score in rows:
                    # Convert BM25 to similarity: score = 1 / (1 + bm25_score)
                    similarity_score = 1.0 / (1.0 + bm25_score)
                    results.append((chunk_id, similarity_score))

                return results

            except aiosqlite.Error as e:
                logger.warning(f"FTS search failed: {e}, trying simple LIKE search")
                # Fallback to simple LIKE search
                like_query = f"%{query}%"
                sql = f"""
                    SELECT chunk_id,
                           LENGTH(content) - LENGTH(REPLACE(LOWER(content), LOWER(?), '')) as match_count
                    FROM {self.table_name}
                    WHERE LOWER(content) LIKE ?{where_sql}
                    ORDER BY match_count DESC
                    LIMIT ?
                """

                params = [query, like_query] + params + [top_k]
                cursor = await db.execute(sql, params)
                rows = await cursor.fetchall()

                results = []
                for chunk_id, match_count in rows:
                    # Simple relevance score based on match count
                    score = min(match_count / 10.0, 1.0)  # Cap at 1.0
                    results.append((chunk_id, score))

                return results

    async def delete_document(self, document_id: str) -> int:
        """Delete all chunks for a document

        Args:
            document_id: Document ID

        Returns:
            Number of chunks deleted
        """
        async with aiosqlite.connect(self.db_path) as db:
            # Delete from FTS index
            await db.execute(
                f"DELETE FROM {self.table_name} WHERE document_id = ?",
                (document_id,)
            )

            # Delete from content table (FTS table only)
            # FTS5 doesn't need separate delete, it's already done above

            # FTS5 doesn't store data separately, so we're done

            await db.commit()
            return cursor.rowcount

    async def get_chunk(self, chunk_id: str) -> DocumentChunk | None:
        """Get a chunk by ID

        Args:
            chunk_id: Chunk ID

        Returns:
            Document chunk if found, None otherwise
        """
        import json

        async with aiosqlite.connect(self.db_path) as db:
            # Query from FTS table (we only have FTS table now, no separate content table)
            cursor = await db.execute(
                f"SELECT chunk_id, document_id, content, file_name, metadata FROM {self.table_name} WHERE chunk_id = ?",
                (chunk_id,)
            )
            row = await cursor.fetchone()

            if not row:
                return None

            chunk_id, document_id, content, file_name, metadata_json = row
            metadata = json.loads(metadata_json) if metadata_json else {}

            return DocumentChunk(
                id=chunk_id,
                document_id=document_id,
                chunk_index=metadata.get('chunk_index', 0),
                content=content,
                metadata=metadata,
            )

    async def update_chunk(self, chunk_id: str, chunk: DocumentChunk) -> bool:
        """Update a chunk

        Args:
            chunk_id: Chunk ID to update
            chunk: New chunk data

        Returns:
            True if updated, False if not found
        """
        import json

        async with aiosqlite.connect(self.db_path) as db:
            metadata_json = json.dumps(dict(chunk.metadata), default=str)

            # Update FTS table (we only have FTS table now)
            cursor = await db.execute(
                f"""UPDATE {self.table_name}
                SET content = ?, metadata = ?
                WHERE chunk_id = ?""",
                (chunk.content, metadata_json, chunk_id)
            )

            await db.commit()
            return cursor.rowcount > 0

    async def count(self) -> int:
        """Get total number of chunks

        Returns:
            Total chunk count
        """
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(f"SELECT COUNT(*) FROM {self.table_name}")
            result = await cursor.fetchone()
            return result[0] if result else 0

    async def clear(self) -> None:
        """Clear all chunks from index"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(f"DELETE FROM {self.table_name}")
            await db.commit()
