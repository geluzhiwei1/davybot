# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Temporal Knowledge Graph for Memory System
Implements Zep-style temporal facts with HippoRAG-style associative retrieval
"""

import json
import logging
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from dawei.core.events import CORE_EVENT_BUS

logger = logging.getLogger(__name__)


class MemoryType(Enum):
    """Memory entry types"""

    FACT = "fact"  # Factual information (User prefers Python)
    PREFERENCE = "preference"  # User preferences
    PROCEDURE = "procedure"  # How-to knowledge
    CONTEXT = "context"  # Conversation context
    STRATEGY = "strategy"  # Learned strategies (from errors)
    EPISODE = "episode"  # Complete interaction episodes


@dataclass
class MemoryEntry:
    """A single memory entry with temporal validity"""

    id: str
    subject: str  # Entity (User, Project, File, etc.)
    predicate: str  # Relation (prefers, uses, contains, etc.)
    object: str  # Value (Python, PostgreSQL, etc.)

    # Temporal attributes
    valid_start: datetime  # When this fact became true
    valid_end: datetime | None = None  # When this fact ceased to be true

    # Dynamics
    confidence: float = 0.8  # Confidence score (0.0-1.0)
    energy: float = 1.0  # Memory energy (decays with time, boosts with access)
    access_count: int = 0  # Number of times accessed

    # Semantic search
    embedding: list[float] | None = None  # Semantic embedding (optional)
    keywords: list[str] = field(default_factory=list)

    # Metadata
    memory_type: MemoryType = MemoryType.FACT
    source_event_id: str | None = None  # Origin event
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate and initialize memory entry"""
        # Validate confidence and energy are in valid range
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"Confidence must be between 0.0 and 1.0, got {self.confidence}")
        if not 0.0 <= self.energy <= 1.0:
            raise ValueError(f"Energy must be between 0.0 and 1.0, got {self.energy}")

        # Set valid_start to now if not provided
        if isinstance(self.valid_start, str):
            self.valid_start = datetime.fromisoformat(self.valid_start)
        if self.valid_end is not None and isinstance(self.valid_end, str):
            self.valid_end = datetime.fromisoformat(self.valid_end)

    def is_valid_at(self, timestamp: datetime) -> bool:
        """Check if memory is valid at given timestamp"""
        if self.valid_end is None:
            return timestamp >= self.valid_start
        return self.valid_start <= timestamp <= self.valid_end

    def is_currently_valid(self) -> bool:
        """Check if memory is currently valid"""
        return self.valid_end is None

    def decay_energy(self, decay_rate: float = 0.95):
        """Apply decay to energy (called by MemoryGardener)"""
        self.energy = max(0.0, self.energy * decay_rate)

    def boost_energy(self, boost: float = 0.2):
        """Boost energy on access (recency effect)"""
        self.energy = min(1.0, self.energy + boost)
        self.access_count += 1

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        data = asdict(self)
        # Convert datetime to ISO string
        data["valid_start"] = self.valid_start.isoformat()
        if self.valid_end:
            data["valid_end"] = self.valid_end.isoformat()
        else:
            data["valid_end"] = None
        # Convert enum to value
        data["memory_type"] = self.memory_type.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MemoryEntry":
        """Create from dictionary"""
        # Convert ISO string to datetime
        if isinstance(data.get("valid_start"), str):
            data["valid_start"] = datetime.fromisoformat(data["valid_start"])
        if data.get("valid_end") and isinstance(data["valid_end"], str):
            data["valid_end"] = datetime.fromisoformat(data["valid_end"])
        # Convert string to enum
        if isinstance(data.get("memory_type"), str):
            data["memory_type"] = MemoryType(data["memory_type"])
        return cls(**data)


@dataclass
class MemoryStats:
    """Memory statistics"""

    total: int
    by_type: dict[str, int]
    avg_confidence: float
    avg_energy: float
    most_accessed: list[MemoryEntry]
    recent: list[MemoryEntry]
    low_energy: int  # Count of memories with energy < 0.2


class MemoryGraph:
    """Temporal Knowledge Graph for memory storage and retrieval

    Features:
    - Temporal facts (valid_start/valid_end)
    - Energy-based forgetting
    - Graph traversal for associative retrieval
    - Event-driven updates via CORE_EVENT_BUS

    Usage:
        graph = MemoryGraph(db_path="~/.dawei/memory.db")
        await graph.add_memory(memory_entry)
        memories = await graph.query_temporal(subject="User")
        related = await graph.retrieve_associative(["Python"], hops=2)
    """

    def __init__(self, db_path: str, event_bus=None):
        """Initialize MemoryGraph

        Args:
            db_path: Path to SQLite database file
            event_bus: Event bus instance (defaults to CORE_EVENT_BUS)

        """
        self.db_path = Path(db_path).expanduser().resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.event_bus = event_bus or CORE_EVENT_BUS
        self.logger = logging.getLogger(__name__)

        # Initialize database
        self._init_db()

    def _init_db(self):
        """Initialize SQLite database with memory graph schema"""
        with sqlite3.connect(self.db_path) as conn:
            # Memory graph table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memory_graph (
                    id TEXT PRIMARY KEY,
                    subject TEXT NOT NULL,
                    predicate TEXT NOT NULL,
                    object TEXT NOT NULL,

                    valid_start TIMESTAMP NOT NULL,
                    valid_end TIMESTAMP,

                    confidence REAL DEFAULT 0.8,
                    energy REAL DEFAULT 1.0,
                    access_count INTEGER DEFAULT 0,

                    memory_type TEXT DEFAULT 'fact',
                    keywords TEXT,
                    source_event_id TEXT,
                    metadata TEXT,

                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Indexes for common queries
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_subject
                ON memory_graph(subject)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_object
                ON memory_graph(object)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_valid_time
                ON memory_graph(valid_start, valid_end)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_energy
                ON memory_graph(energy)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_type
                ON memory_graph(memory_type)
            """)

            # Context pages table
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

            self.logger.info(f"Memory graph initialized at {self.db_path}")

    async def add_memory(self, memory: MemoryEntry) -> str:
        """Add a new memory entry

        Args:
            memory: MemoryEntry to add

        Returns:
            memory_id: ID of the added memory

        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO memory_graph
                    (id, subject, predicate, object, valid_start, valid_end,
                     confidence, energy, memory_type, keywords, source_event_id, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        memory.id,
                        memory.subject,
                        memory.predicate,
                        memory.object,
                        memory.valid_start.isoformat(),
                        memory.valid_end.isoformat() if memory.valid_end else None,
                        memory.confidence,
                        memory.energy,
                        memory.memory_type.value,
                        json.dumps(memory.keywords),
                        memory.source_event_id,
                        json.dumps(memory.metadata),
                    ),
                )

            # Emit event
            try:
                await self.event_bus.publish(
                    "MEMORY_ENTRY_CREATED",
                    {"memory_id": memory.id, "memory_type": memory.memory_type.value},
                )
            except Exception as e:
                self.logger.warning(f"Failed to publish MEMORY_ENTRY_CREATED event: {e}")

            self.logger.info(f"Memory added: {memory.subject} {memory.predicate} {memory.object}")
            return memory.id

        except sqlite3.Error:
            self.logger.exception("Failed to add memory: ")
            raise

    async def update_memory(
        self,
        memory_id: str,
        predicate: str | None = None,
        object: str | None = None,
        valid_end: datetime | None = None,
        confidence: float | None = None,
        energy: float | None = None,
        keywords: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Update existing memory entry

        For temporal facts, setting valid_end creates a new version.
        """
        try:
            updates = {}
            if predicate is not None:
                updates["predicate"] = predicate
            if object is not None:
                updates["object"] = object
            if valid_end is not None:
                updates["valid_end"] = valid_end.isoformat()
            if confidence is not None:
                updates["confidence"] = confidence
            if energy is not None:
                updates["energy"] = energy
            if keywords is not None:
                updates["keywords"] = json.dumps(keywords)
            if metadata is not None:
                updates["metadata"] = json.dumps(metadata)
            updates["updated_at"] = datetime.now(timezone.utc).isoformat()

            if not updates:
                return False

            set_clause = ", ".join(f"{k} = ?" for k in updates)
            values = [*list(updates.values()), memory_id]

            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(f"UPDATE memory_graph SET {set_clause} WHERE id = ?", values)
                # Check if any row was actually updated
                if cursor.rowcount == 0:
                    return False

            # Emit event
            try:
                await self.event_bus.publish(
                    "MEMORY_ENTRY_UPDATED",
                    {"memory_id": memory_id, "updates": list(updates.keys())},
                )
            except Exception as e:
                self.logger.warning(f"Failed to publish MEMORY_ENTRY_UPDATED event: {e}")

            self.logger.info(f"Memory updated: {memory_id}")
            return True

        except sqlite3.Error:
            self.logger.exception("Failed to update memory: ")
            return False

    async def get_memory(self, memory_id: str) -> MemoryEntry | None:
        """Get a single memory by ID"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("SELECT * FROM memory_graph WHERE id = ?", (memory_id,))
                row = cursor.fetchone()

                if not row:
                    return None

                return self._row_to_memory(row)

        except sqlite3.Error:
            self.logger.exception("Failed to get memory: ")
            return None

    async def delete_memory(self, memory_id: str) -> bool:
        """Delete a memory entry"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("DELETE FROM memory_graph WHERE id = ?", (memory_id,))

                if cursor.rowcount > 0:
                    self.logger.info(f"Memory deleted: {memory_id}")
                    return True

                return False

        except sqlite3.Error:
            self.logger.exception("Failed to delete memory: ")
            return False

    async def query_temporal(
        self,
        subject: str | None = None,
        predicate: str | None = None,
        object: str | None = None,
        at_time: datetime | None = None,
        only_valid: bool = True,
        memory_type: MemoryType | None = None,
        min_energy: float | None = None,
    ) -> list[MemoryEntry]:
        """Query memory graph with temporal filtering

        Args:
            subject: Filter by subject
            predicate: Filter by predicate
            object: Filter by object (partial match)
            at_time: Query specific point in time
            only_valid: Only return currently valid memories
            memory_type: Filter by memory type
            min_energy: Minimum energy threshold

        Returns:
            List of matching memories

        """
        try:
            query = "SELECT * FROM memory_graph WHERE 1=1"
            params = []

            if subject:
                query += " AND subject = ?"
                params.append(subject)
            if predicate:
                query += " AND predicate = ?"
                params.append(predicate)
            if object:
                query += " AND object LIKE ?"
                params.append(f"%{object}%")
            if memory_type:
                query += " AND memory_type = ?"
                params.append(memory_type.value)
            if min_energy is not None:
                query += " AND energy >= ?"
                params.append(min_energy)

            if only_valid or at_time:
                # Temporal filtering
                timestamp = (at_time or datetime.now(timezone.utc)).isoformat()
                query += " AND valid_start <= ? AND (valid_end IS NULL OR valid_end > ?)"
                params.extend([timestamp, timestamp])

            # Order by energy and access count
            query += " ORDER BY energy DESC, access_count DESC"

            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(query, params)
                rows = cursor.fetchall()

            memories = [self._row_to_memory(row) for row in rows]

            # Emit retrieval events
            for mem in memories:
                try:
                    await self.event_bus.publish(
                        "MEMORY_ENTRY_RETRIEVED",
                        {"memory_id": mem.id, "access_count": mem.access_count + 1},
                    )
                except Exception:
                    pass  # Don't fail on event errors

            self.logger.info(f"Temporal query returned {len(memories)} memories")
            return memories

        except sqlite3.Error:
            self.logger.exception("Failed to query memories: ")
            return []

    async def retrieve_associative(
        self,
        query_entities: list[str],
        hops: int = 1,
        min_energy: float = 0.2,
    ) -> list[MemoryEntry]:
        """HippoRAG-style associative retrieval via graph traversal

        Args:
            query_entities: List of entities to start traversal
            hops: Number of hops to traverse (1=direct neighbors, 2=neighbors of neighbors)
            min_energy: Minimum energy threshold for retrieval

        Returns:
            List of associated memories

        """
        try:
            results = []  # Changed from set to list
            seen_ids = set()  # Track seen memory IDs to avoid duplicates
            current_layer = query_entities.copy()

            # Keep track of visited entities to avoid cycles
            visited = set(query_entities)

            for _hop in range(hops + 1):
                next_layer = []

                # Find neighbors of current layer
                with sqlite3.connect(self.db_path) as conn:
                    conn.row_factory = sqlite3.Row

                    for entity in current_layer:
                        # Find outgoing edges: subject -> object
                        cursor = conn.execute(
                            """
                            SELECT * FROM memory_graph
                            WHERE subject = ?
                            AND energy >= ?
                            AND (valid_end IS NULL OR valid_end > datetime('now'))
                            """,
                            (entity, min_energy),
                        )
                        rows = cursor.fetchall()

                        for row in rows:
                            mem = self._row_to_memory(row)
                            # Add to results if not already seen
                            if mem.id not in seen_ids:
                                results.append(mem)
                                seen_ids.add(mem.id)

                            # Add object as next layer if not visited
                            if mem.object not in visited:
                                next_layer.append(mem.object)
                                visited.add(mem.object)

                current_layer = next_layer
                if not current_layer:
                    break

            memories = results

            self.logger.info(f"Associative retrieval: {len(memories)} memories found")
            return memories

        except sqlite3.Error:
            self.logger.exception("Failed associative retrieval: ")
            return []

    async def get_all_memories(
        self,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[MemoryEntry]:
        """Get all memories with optional pagination"""
        try:
            query = "SELECT * FROM memory_graph ORDER BY created_at DESC"
            if limit:
                query += f" LIMIT {limit} OFFSET {offset}"

            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(query)
                rows = cursor.fetchall()

            return [self._row_to_memory(row) for row in rows]

        except sqlite3.Error:
            self.logger.exception("Failed to get all memories: ")
            return []

    async def search_memories(self, query: str, limit: int = 100) -> list[MemoryEntry]:
        """Search memories by keyword (simple text search)

        Args:
            query: Search query string
            limit: Maximum results

        Returns:
            List of matching memories

        """
        try:
            search_term = f"%{query}%"

            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    """
                    SELECT * FROM memory_graph
                    WHERE subject LIKE ?
                       OR predicate LIKE ?
                       OR object LIKE ?
                       OR keywords LIKE ?
                    ORDER BY energy DESC
                    LIMIT ?
                    """,
                    (search_term, search_term, search_term, search_term, limit),
                )
                rows = cursor.fetchall()

            return [self._row_to_memory(row) for row in rows]

        except sqlite3.Error:
            self.logger.exception("Failed to search memories: ")
            return []

    async def get_stats(self) -> MemoryStats:
        """Get memory statistics"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                # Total count
                total_cursor = conn.execute("SELECT COUNT(*) FROM memory_graph")
                total = total_cursor.fetchone()[0]

                # By type
                type_cursor = conn.execute(
                    "SELECT memory_type, COUNT(*) FROM memory_graph GROUP BY memory_type",
                )
                by_type = {row[0]: row[1] for row in type_cursor.fetchall()}

                # Average confidence and energy
                stats_cursor = conn.execute("SELECT AVG(confidence), AVG(energy) FROM memory_graph")
                avg_confidence, avg_energy = stats_cursor.fetchone()

                # Most accessed (top 10) - wrap in try/except in case of row_factory issues
                most_accessed = []
                try:
                    accessed_cursor = conn.execute("""SELECT * FROM memory_graph
                           WHERE access_count > 0
                           ORDER BY access_count DESC
                           LIMIT 10""")
                    most_accessed = [self._row_to_memory(row) for row in accessed_cursor.fetchall()]
                except (TypeError, KeyError) as e:
                    self.logger.warning(f"Could not fetch most_accessed: {e}")

                # Recent (top 10) - wrap in try/except
                recent = []
                try:
                    recent_cursor = conn.execute("""SELECT * FROM memory_graph
                           ORDER BY created_at DESC
                           LIMIT 10""")
                    recent = [self._row_to_memory(row) for row in recent_cursor.fetchall()]
                except (TypeError, KeyError) as e:
                    self.logger.warning(f"Could not fetch recent: {e}")

                # Low energy count
                low_energy_cursor = conn.execute(
                    "SELECT COUNT(*) FROM memory_graph WHERE energy < 0.2",
                )
                low_energy = low_energy_cursor.fetchone()[0]

            return MemoryStats(
                total=total,
                by_type=by_type,
                avg_confidence=round(avg_confidence or 0, 3),
                avg_energy=round(avg_energy or 0, 3),
                most_accessed=most_accessed,
                recent=recent,
                low_energy=low_energy,
            )

        except sqlite3.Error:
            self.logger.exception("Failed to get stats: ")
            return MemoryStats(
                total=0,
                by_type={},
                avg_confidence=0.0,
                avg_energy=0.0,
                most_accessed=[],
                recent=[],
                low_energy=0,
            )

    def _row_to_memory(self, row) -> MemoryEntry:
        """Convert database row to MemoryEntry.

        Handles both sqlite3.Row objects and tuples.
        """
        # If it's a Row object, we can access by column name
        # If it's a tuple, we need to access by index
        if hasattr(row, "keys"):
            # sqlite3.Row object - access by column name
            return MemoryEntry(
                id=row["id"],
                subject=row["subject"],
                predicate=row["predicate"],
                object=row["object"],
                valid_start=datetime.fromisoformat(row["valid_start"]),
                valid_end=datetime.fromisoformat(row["valid_end"]) if row["valid_end"] else None,
                confidence=row["confidence"],
                energy=row["energy"],
                access_count=row["access_count"],
                memory_type=MemoryType(row["memory_type"]),
                keywords=json.loads(row["keywords"]) if row["keywords"] else [],
                source_event_id=row["source_event_id"],
                metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            )
        # Tuple - access by index (based on table schema)
        # Schema: id, subject, predicate, object, valid_start, valid_end,
        #         confidence, energy, access_count, memory_type, keywords,
        #         source_event_id, metadata, created_at, updated_at
        return MemoryEntry(
            id=row[0],
            subject=row[1],
            predicate=row[2],
            object=row[3],
            valid_start=datetime.fromisoformat(row[4]),
            valid_end=datetime.fromisoformat(row[5]) if row[5] else None,
            confidence=row[6],
            energy=row[7],
            access_count=row[8],
            memory_type=MemoryType(row[9]),
            keywords=json.loads(row[10]) if row[10] else [],
            source_event_id=row[11],
            metadata=json.loads(row[12]) if row[12] else {},
        )
