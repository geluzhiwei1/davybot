# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Knowledge Base Auto-Sync Scheduler

Lightweight background task that periodically scans knowledge bases
with `watch_enabled=True` and auto-syncs new files.

Design: KISS — uses asyncio polling (default every 60s), no external dependencies.
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from dawei.knowledge.base_manager import KnowledgeBaseManager

logger = logging.getLogger(__name__)

# Default sync interval in seconds
DEFAULT_SYNC_INTERVAL = 60


class KnowledgeSyncScheduler:
    """Periodically syncs watch-enabled knowledge bases."""

    def __init__(self, manager: KnowledgeBaseManager, interval: int = DEFAULT_SYNC_INTERVAL):
        self._manager = manager
        self._interval = interval
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._last_sync_at: dict[str, datetime] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start(self):
        """Start the background sync loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info(f"KnowledgeSyncScheduler started (interval={self._interval}s)")

    async def stop(self):
        """Stop the background sync loop."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("KnowledgeSyncScheduler stopped")

    async def sync_base(self, base_id: str) -> Optional[dict]:
        """Manually trigger sync for a single knowledge base.

        Returns sync result dict or None on error.
        """
        return await self._do_sync(base_id)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _loop(self):
        """Main polling loop."""
        # Delay the first sync to let the server fully start
        await asyncio.sleep(10)

        while self._running:
            try:
                await self._sync_all_enabled()
            except Exception as e:
                logger.error(f"Error in knowledge sync loop: {e}", exc_info=True)

            await self._sleep()

    async def _sleep(self):
        """Interruptible sleep."""
        try:
            await asyncio.sleep(self._interval)
        except asyncio.CancelledError:
            pass

    async def _sync_all_enabled(self):
        """Scan all knowledge bases and sync those with watch_enabled."""
        bases = self._manager.list_bases()
        for kb in bases.items:
            if not kb.settings.watch_enabled:
                continue
            if not kb.settings.watch_dir:
                continue
            if kb.status != "active":
                continue

            try:
                result = await self._do_sync(kb.id)
                if result and result.get("imported", 0) > 0:
                    logger.info(
                        f"Auto-sync for '{kb.name}' ({kb.id}): "
                        f"{result.get('imported', 0)} files synced"
                    )
            except Exception as e:
                logger.warning(f"Auto-sync failed for '{kb.name}' ({kb.id}): {e}")

            self._last_sync_at[kb.id] = datetime.now()

    async def _do_sync(self, base_id: str) -> Optional[dict]:
        """Perform sync for a single knowledge base by reusing the API logic."""
        kb = self._manager.get_base(base_id)
        if not kb:
            return None

        scan_path = kb.settings.watch_dir
        if not scan_path:
            return None

        directory = Path(scan_path).expanduser().resolve()
        if not directory.exists() or not directory.is_dir():
            return None

        # Determine new files
        supported = {".md", ".markdown"}
        existing_docs = self._manager.list_base_documents(base_id, skip=0, limit=10000)
        existing_names = {doc.get("file_name", "") for doc in existing_docs.get("documents", [])}

        files_to_import: list[Path] = []
        try:
            glob_iter = directory.rglob("*") if kb.settings.watch_recursive else directory.glob("*")
            for fp in glob_iter:
                if fp.is_file() and fp.suffix.lower() in supported:
                    if fp.name not in existing_names:
                        files_to_import.append(fp)
        except PermissionError:
            logger.warning(f"Permission denied scanning {scan_path}")
            return None

        if not files_to_import:
            return {"imported": 0, "skipped": 0, "errors": []}

        # Delegate to the existing sync logic
        from dawei.api.knowledge_bases import sync_from_directory

        # Build a fake request context by calling the core logic directly
        return await self._import_files(base_id, files_to_import)

    async def _import_files(self, base_id: str, files: list[Path]) -> dict:
        """Import files into a knowledge base (vector + fulltext + graph)."""
        from dawei.knowledge.chunking.chunker import ChunkingConfig, ChunkingStrategy, TextChunker
        from dawei.knowledge.models import VectorDocument
        from dawei.knowledge.parsers.markdown_parser import MarkdownParser
        from dawei.knowledge.vector.sqlite_vec_store import SQLiteVecVectorStore
        from dawei.knowledge.fulltext.sqlite_fts_store import SQLiteFTSStore
        from dawei.knowledge.graph.sqlite_graph_store import SQLiteGraphStore
        from dawei.knowledge.extraction import ExtractionFactory

        kb = self._manager.get_base(base_id)
        if not kb:
            return {"imported": 0, "errors": ["Knowledge base not found"]}

        base_storage_path = self._manager._get_storage_path(base_id)

        # Initialize stores
        vector_store = SQLiteVecVectorStore(
            db_path=str(base_storage_path / "vectors.db"),
            dimension=kb.settings.embedding_dimension,
        )
        await vector_store.initialize()

        fulltext_store = SQLiteFTSStore(db_path=str(base_storage_path / "fulltext.db"))
        await fulltext_store.initialize()

        graph_store = SQLiteGraphStore(db_path=str(base_storage_path / "graph.db"))
        await graph_store.initialize()

        embedding_service = self._manager.get_embedding_manager(base_id)

        # Chunking
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

        extractor = ExtractionFactory.create(extraction_strategy, domain=domain, llm_config_name=extraction_llm_config)

        total_documents = 0
        total_chunks = 0
        total_entities = 0
        total_relations = 0
        errors: list[str] = []

        for file_path in files:
            try:
                if file_path.suffix.lower() not in {".md", ".markdown"}:
                    continue

                parser = MarkdownParser()
                document = await parser.parse(file_path)
                chunks = await chunker.chunk(document)

                chunk_texts = [c.content for c in chunks]
                embeddings = await embedding_service.embed_documents(chunk_texts)

                # Vector store
                vector_docs = []
                for chunk, embedding in zip(chunks, embeddings, strict=True):
                    metadata_copy = dict(chunk.metadata)
                    for k, v in metadata_copy.items():
                        if hasattr(v, "isoformat"):
                            metadata_copy[k] = v.isoformat()

                    vector_docs.append(
                        VectorDocument(
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
                    )
                await vector_store.add(vector_docs)

                # Fulltext
                try:
                    await fulltext_store.add_documents(chunks)
                except Exception as e:
                    logger.warning(f"Auto-sync fulltext failed for {file_path.name}: {e}")

                # Graph — delegate to shared builder (per-chunk extraction + merge)
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
                    logger.warning(f"Auto-sync graph failed for {file_path.name}: {e}")

                total_documents += 1
                total_chunks += len(chunks)
                logger.info(f"Auto-synced: {file_path.name} ({len(chunks)} chunks)")

            except Exception as e:
                error_msg = f"Failed to import {file_path.name}: {e}"
                logger.error(error_msg, exc_info=True)
                errors.append(error_msg)

        # Update stats
        kb.stats.total_documents += total_documents
        kb.stats.total_chunks += total_chunks
        kb.stats.total_entities += total_entities
        kb.stats.total_relations += total_relations
        kb.stats.indexed_documents += total_documents
        kb.stats.last_indexed_at = datetime.now()
        kb.stats.last_updated_at = datetime.now()
        kb.updated_at = datetime.now()
        self._manager._save_metadata()

        return {
            "imported": total_documents,
            "chunks": total_chunks,
            "errors": errors if errors else None,
        }


# Singleton instance
sync_scheduler = KnowledgeSyncScheduler(manager=None)  # type: ignore  # manager set during initialize


async def initialize_sync_scheduler(manager: KnowledgeBaseManager, interval: int = DEFAULT_SYNC_INTERVAL):
    """Initialize and start the sync scheduler."""
    global sync_scheduler
    sync_scheduler = KnowledgeSyncScheduler(manager=manager, interval=interval)
    await sync_scheduler.start()


async def shutdown_sync_scheduler():
    """Stop the sync scheduler."""
    await sync_scheduler.stop()
