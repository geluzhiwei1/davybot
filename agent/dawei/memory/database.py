# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Database Initialization for Memory System
Handles database schema creation and migrations
"""

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)


def init_memory_database(db_path: str) -> bool:
    """Initialize memory system database with all required tables and indexes

    Args:
        db_path: Path to SQLite database file

    Returns:
        True if successful, False otherwise

    """
    try:
        db_file = Path(db_path).expanduser().resolve()
        db_file.parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"Initializing memory database at {db_path}")

        with sqlite3.connect(db_path) as conn:
            # Enable foreign keys
            conn.execute("PRAGMA foreign_keys = ON")

            # Create memory_graph table
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
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                    CHECK (confidence >= 0.0 AND confidence <= 1.0),
                    CHECK (energy >= 0.0 AND energy <= 1.0)
                )
            """)

            # Create context_pages table
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

                    metadata TEXT,

                    CHECK (tokens >= 0)
                )
            """)

            # Create indexes for memory_graph
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_memory_subject
                ON memory_graph(subject)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_memory_object
                ON memory_graph(object)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_memory_valid_time
                ON memory_graph(valid_start, valid_end)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_memory_energy
                ON memory_graph(energy)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_memory_type
                ON memory_graph(memory_type)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_memory_access_count
                ON memory_graph(access_count DESC)
            """)

            # Create indexes for context_pages
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_context_session
                ON context_pages(session_id)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_context_access
                ON context_pages(access_count DESC, last_accessed DESC)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_context_created
                ON context_pages(created_at DESC)
            """)

            # Create triggers for automatic timestamp updates
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS update_memory_timestamp
                AFTER UPDATE ON memory_graph
                FOR EACH ROW
                BEGIN
                    UPDATE memory_graph
                    SET updated_at = CURRENT_TIMESTAMP
                    WHERE id = NEW.id;
                END;
            """)

            # Insert default settings
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memory_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    description TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Default settings
            default_settings = {
                "consolidation_enabled": "true",
                "consolidation_interval_hours": "1",
                "decay_rate": "0.95",
                "archive_threshold": "0.2",
                "archive_after_days": "30",
                "max_context_pages": "5",
                "context_page_size": "2000",
            }

            for key, value in default_settings.items():
                conn.execute(
                    """
                    INSERT OR IGNORE INTO memory_settings (key, value)
                    VALUES (?, ?)
                """,
                    (key, value),
                )

        logger.info("Memory database initialized successfully")
        return True

    except sqlite3.Error as e:
        logger.error(f"Failed to initialize memory database: {e}", exc_info=True)
        return False


def migrate_memory_database(db_path: str, target_version: int = 1) -> bool:
    """Migrate memory database to target version

    Args:
        db_path: Path to SQLite database file
        target_version: Target schema version

    Returns:
        True if successful, False otherwise

    """
    try:
        db_file = Path(db_path).expanduser().resolve()

        if not db_file.exists():
            logger.warning(f"Database file does not exist: {db_path}")
            return False

        logger.info(f"Migrating memory database to version {target_version}")

        with sqlite3.connect(db_path) as conn:
            # Get current version
            cursor = conn.execute("SELECT value FROM memory_settings WHERE key = 'schema_version'")
            row = cursor.fetchone()

            current_version = int(row[0]) if row else 0

            if current_version >= target_version:
                logger.info(f"Database already at version {current_version}")
                return True

            # Apply migrations
            for version in range(current_version + 1, target_version + 1):
                logger.info(f"Applying migration to version {version}")
                _apply_migration(conn, version)

            # Update version
            conn.execute(
                """
                UPDATE memory_settings
                SET value = ?, updated_at = CURRENT_TIMESTAMP
                WHERE key = 'schema_version'
            """,
                (str(target_version),),
            )

            if conn.rowcount == 0:
                conn.execute(
                    """
                    INSERT INTO memory_settings (key, value)
                    VALUES ('schema_version', ?)
                """,
                    (str(target_version),),
                )

        logger.info(f"Database migrated to version {target_version}")
        return True

    except sqlite3.Error as e:
        logger.error(f"Failed to migrate memory database: {e}", exc_info=True)
        return False


def _apply_migration(conn: sqlite3.Connection, version: int):
    """Apply migration for specific version"""
    if version == 1:
        # Version 1: Initial schema (already applied in init)
        pass

    # Future migrations can be added here
    # elif version == 2:
    #     # Add new columns, tables, etc.
    #     conn.execute("ALTER TABLE memory_graph ADD COLUMN ...")

    else:
        logger.warning(f"Unknown migration version: {version}")


def get_memory_setting(db_path: str, key: str, default: str | None = None) -> str | None:
    """Get a setting value from the database"""
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute("SELECT value FROM memory_settings WHERE key = ?", (key,))
            row = cursor.fetchone()

            return row[0] if row else default

    except sqlite3.Error:
        logger.exception("Failed to get setting {key}: ")
        return default


def set_memory_setting(db_path: str, key: str, value: str) -> bool:
    """Set a setting value in the database"""
    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO memory_settings (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            """,
                (key, value),
            )

        return True

    except sqlite3.Error:
        logger.exception("Failed to set setting {key}: ")
        return False


def get_all_memory_settings(db_path: str) -> dict:
    """Get all memory settings"""
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute("SELECT key, value FROM memory_settings")
            rows = cursor.fetchall()

            return {row[0]: row[1] for row in rows}

    except sqlite3.Error:
        logger.exception("Failed to get settings: ")
        return {}


def cleanup_old_memories(db_path: str, energy_threshold: float = 0.01, days_old: int = 90) -> int:
    """Cleanup old and low-energy memories

    Args:
        db_path: Path to database
        energy_threshold: Minimum energy threshold
        days_old: Age in days for deletion

    Returns:
        Number of memories deleted

    """
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute(
                """
                DELETE FROM memory_graph
                WHERE energy < ?
                  AND created_at < datetime('now', '-' || ? || ' days')
                  AND (valid_end IS NOT NULL)  -- Only expired memories
            """,
                (energy_threshold, days_old),
            )

            deleted = cursor.rowcount

        if deleted > 0:
            logger.info(f"Cleaned up {deleted} old memories")

        return deleted

    except sqlite3.Error:
        logger.exception("Failed to cleanup old memories: ")
        return 0


def vacuum_memory_database(db_path: str) -> bool:
    """Vacuum the memory database to reclaim space

    Args:
        db_path: Path to database

    Returns:
        True if successful

    """
    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute("VACUUM")

        logger.info("Memory database vacuumed")
        return True

    except sqlite3.Error:
        logger.exception("Failed to vacuum database: ")
        return False
