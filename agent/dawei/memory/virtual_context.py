# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Virtual Context Paging for Extended Memory
MemGPT-style memory paging that extends existing ContextManager
"""

import logging
import sqlite3
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dawei.agentic.context_manager import TokenEstimator

logger = logging.getLogger(__name__)


@dataclass
class ContextPage:
    """A single page of context content"""

    page_id: str
    session_id: str
    content: str
    summary: str  # Short summary for quick browsing
    tokens: int

    # LRU metadata
    access_count: int = 0
    last_accessed: float = field(default_factory=lambda: datetime.now(timezone.utc).timestamp())
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Source tracking
    source_type: str = "conversation"  # conversation, document, tool_output
    source_ref: str | None = None  # Reference to source
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def score(self) -> float:
        """LRU score: higher = more likely to evict"""
        age_hours = (datetime.now(timezone.utc).timestamp() - self.last_accessed) / 3600
        access_factor = 1 / (self.access_count + 1)
        return age_hours * access_factor

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        data = asdict(self)
        data["created_at"] = self.created_at.isoformat()
        data["last_accessed"] = datetime.fromtimestamp(self.last_accessed).isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ContextPage":
        """Create from dictionary"""
        if isinstance(data.get("created_at"), str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        if isinstance(data.get("last_accessed"), str):
            data["last_accessed"] = datetime.fromisoformat(data["last_accessed"]).timestamp()
        return cls(**data)


class VirtualContextManager:
    """Virtual context paging system extending ContextManager

    Manages context pages stored in SQLite, loading them into active context
    on-demand based on semantic relevance and LRU eviction policy.

    Usage:
        vcm = VirtualContextManager(
            base_context_manager=context_manager,
            db_path="~/.dawei/memory.db"
        )
        await vcm.create_page(session_id, content, summary)
        await vcm.page_in(session_id, query="database configuration")
    """

    def __init__(
        self,
        db_path: str,
        page_size: int = 2000,
        max_active_pages: int = 5,  # Tokens per page
    ):
        """Initialize VirtualContextManager

        Args:
            db_path: Path to SQLite database (shared with MemoryGraph)
            page_size: Target tokens per page
            max_active_pages: Maximum active pages in memory

        """
        self.db_path = Path(db_path).expanduser().resolve()
        self.page_size = page_size
        self.max_active_pages = max_active_pages

        self.logger = logging.getLogger(__name__)
        self.active_pages: dict[str, ContextPage] = {}

        # Initialize database tables if needed
        self._ensure_tables()

    def _ensure_tables(self):
        """Ensure database tables exist"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS context_pages (
                    page_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    tokens INTEGER NOT NULL,

                    access_count INTEGER DEFAULT 0,
                    last_accessed TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                    source_type TEXT,
                    source_ref TEXT,

                    metadata TEXT
                )
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_session_pages
                ON context_pages(session_id)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_page_access
                ON context_pages(access_count DESC, last_accessed DESC)
            """)

    async def create_page(
        self,
        session_id: str,
        content: str,
        summary: str,
        source_type: str = "conversation",
        source_ref: str | None = None,
    ) -> str:
        """Create a new context page

        Args:
            session_id: Session identifier
            content: Full page content
            summary: Short summary for browsing
            source_type: Type of content source
            source_ref: Reference to source

        Returns:
            page_id: ID of the created page

        """
        try:
            page_id = str(uuid.uuid4())
            tokens = TokenEstimator.estimate(content)

            # Truncate if too large
            if tokens > self.page_size * 1.5:
                content = content[: int(len(content) * self.page_size / tokens * 1.2)]
                tokens = TokenEstimator.estimate(content)

            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO context_pages
                    (page_id, session_id, content, summary, tokens, source_type, source_ref)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        page_id,
                        session_id,
                        content,
                        summary,
                        tokens,
                        source_type,
                        source_ref,
                    ),
                )

            self.logger.info(f"Page created: {page_id} ({tokens} tokens)")
            return page_id

        except sqlite3.Error:
            self.logger.exception("Failed to create page: ")
            raise

    async def page_in(
        self,
        session_id: str,
        query: str,
        top_k: int = 3,
        current_tokens: int = 0,
        max_tokens: int = 100000,
    ) -> list[str]:
        """Load relevant pages into active context

        Uses keyword matching for relevance (can be upgraded to vector search)

        Args:
            session_id: Session identifier
            query: Query to match against page content
            top_k: Number of pages to load
            current_tokens: Current token count in context
            max_tokens: Maximum tokens allowed in context

        Returns:
            List of loaded page IDs

        """
        try:
            query_lower = query.lower()

            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row

                # Build query based on active pages
                if self.active_pages:
                    # Exclude already active pages
                    excluded_ids = ",".join(
                        [f"'{pid}'" for pid in self.active_pages],
                    )
                    sql = f"""
                        SELECT * FROM context_pages
                        WHERE session_id = ?
                        AND page_id NOT IN ({excluded_ids})
                        ORDER BY access_count DESC, created_at DESC
                        LIMIT ?
                    """
                    params = (session_id, top_k * 3)
                else:
                    # No active pages, get all candidate pages
                    sql = """
                        SELECT * FROM context_pages
                        WHERE session_id = ?
                        ORDER BY access_count DESC, created_at DESC
                        LIMIT ?
                    """
                    params = (session_id, top_k * 3)

                cursor = conn.execute(sql, params)
                rows = cursor.fetchall()

            # Re-rank by query relevance
            scored_pages = []
            for row in rows:
                content_lower = row["content"].lower()
                summary_lower = row["summary"].lower()
                score = sum(1 for word in query_lower.split() if word in content_lower)
                score += sum(1 for word in query_lower.split() if word in summary_lower) * 2

                page = ContextPage(
                    page_id=row["page_id"],
                    session_id=row["session_id"],
                    content=row["content"],
                    summary=row["summary"],
                    tokens=row["tokens"],
                    access_count=row["access_count"],
                    last_accessed=(datetime.fromisoformat(row["last_accessed"]).timestamp() if row["last_accessed"] else 0),
                    created_at=datetime.fromisoformat(row["created_at"]),
                    source_type=row["source_type"],
                    source_ref=row["source_ref"],
                )

                scored_pages.append((score, page))

            scored_pages.sort(key=lambda x: x[0], reverse=True)

            # Load top pages within token budget
            loaded_ids = []
            used_tokens = current_tokens

            for score, page in scored_pages[:top_k]:
                if used_tokens + page.tokens <= max_tokens:
                    self.active_pages[page.page_id] = page
                    loaded_ids.append(page.page_id)
                    used_tokens += page.tokens

                    # Update access tracking
                    await self._update_page_access(page.page_id)

                else:
                    break

            self.logger.info(f"Loaded {len(loaded_ids)} pages into context")
            return loaded_ids

        except sqlite3.Error:
            self.logger.exception("Failed to page in: ")
            return []

    async def _update_page_access(self, page_id: str):
        """Update page access tracking"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    UPDATE context_pages
                    SET access_count = access_count + 1,
                        last_accessed = CURRENT_TIMESTAMP
                    WHERE page_id = ?
                    """,
                    (page_id,),
                )

            # Update in-memory page
            if page_id in self.active_pages:
                self.active_pages[page_id].access_count += 1
                self.active_pages[page_id].last_accessed = datetime.now(timezone.utc).timestamp()

        except sqlite3.Error as e:
            self.logger.warning(f"Failed to update page access: {e}")

    async def page_out(self, count: int = 1) -> list[str]:
        """Evict least recently used pages from active context

        Uses LRU policy based on page.score

        Args:
            count: Number of pages to evict

        Returns:
            List of evicted page IDs

        """
        if not self.active_pages:
            return []

        # Sort by score (higher = more likely to evict)
        sorted_pages = sorted(self.active_pages.items(), key=lambda x: x[1].score, reverse=True)

        evicted_ids = []
        for page_id, _ in sorted_pages[:count]:
            del self.active_pages[page_id]
            evicted_ids.append(page_id)

        self.logger.info(f"Evicted {len(evicted_ids)} pages from context")
        return evicted_ids

    def get_active_context(self) -> str:
        """Get concatenated content of all active pages"""
        if not self.active_pages:
            return ""

        pages_content = []
        for page in self.active_pages.values():
            pages_content.append(f"## {page.summary}\n{page.content}")

        return "\n---\n".join(pages_content)

    def get_active_page_ids(self) -> list[str]:
        """Get list of active page IDs"""
        return list(self.active_pages.keys())

    async def get_page(self, page_id: str) -> ContextPage | None:
        """Get a specific page by ID"""
        # Check active pages first
        if page_id in self.active_pages:
            return self.active_pages[page_id]

        # Load from database
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("SELECT * FROM context_pages WHERE page_id = ?", (page_id,))
                row = cursor.fetchone()

                if not row:
                    return None

                return ContextPage(
                    page_id=row["page_id"],
                    session_id=row["session_id"],
                    content=row["content"],
                    summary=row["summary"],
                    tokens=row["tokens"],
                    access_count=row["access_count"],
                    last_accessed=(datetime.fromisoformat(row["last_accessed"]).timestamp() if row["last_accessed"] else 0),
                    created_at=datetime.fromisoformat(row["created_at"]),
                    source_type=row["source_type"],
                    source_ref=row["source_ref"],
                )

        except sqlite3.Error:
            self.logger.exception("Failed to get page: ")
            return None

    async def get_session_pages(self, session_id: str, limit: int = 100) -> list[ContextPage]:
        """Get all pages for a session"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    """
                    SELECT * FROM context_pages
                    WHERE session_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (session_id, limit),
                )
                rows = cursor.fetchall()

            return [
                ContextPage(
                    page_id=row["page_id"],
                    session_id=row["session_id"],
                    content=row["content"],
                    summary=row["summary"],
                    tokens=row["tokens"],
                    access_count=row["access_count"],
                    last_accessed=(datetime.fromisoformat(row["last_accessed"]).timestamp() if row["last_accessed"] else 0),
                    created_at=datetime.fromisoformat(row["created_at"]),
                    source_type=row["source_type"],
                    source_ref=row["source_ref"],
                )
                for row in rows
            ]

        except sqlite3.Error:
            self.logger.exception("Failed to get session pages: ")
            return []

    async def delete_page(self, page_id: str) -> bool:
        """Delete a context page"""
        try:
            # Remove from active pages
            if page_id in self.active_pages:
                del self.active_pages[page_id]

            # Delete from database
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("DELETE FROM context_pages WHERE page_id = ?", (page_id,))

                if cursor.rowcount > 0:
                    self.logger.info(f"Page deleted: {page_id}")
                    return True

            return False

        except sqlite3.Error:
            self.logger.exception("Failed to delete page: ")
            return False

    def get_stats(self) -> dict[str, Any]:
        """Get context manager statistics"""
        return {
            "active_pages": len(self.active_pages),
            "max_active_pages": self.max_active_pages,
            "active_page_ids": list(self.active_pages.keys()),
            "total_tokens": sum(p.tokens for p in self.active_pages.values()),
        }
