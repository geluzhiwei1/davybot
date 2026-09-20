# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""SpanStore — persist and query Agent execution spans for full-link observability.

Phase 3+: provides SQLite-backed span persistence and a query API so traces
survive process restarts and can be retrieved historically.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid as uuid_mod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from dawei.core.datetime_compat import UTC
from dawei.logg.logging import get_logger

logger = get_logger(__name__)


class SpanStore:
    """SQLite-backed store for agent execution spans.

    Usage:
        store = SpanStore("/path/to/.dawei/spans.db")
        await store.persist_span(trace_id, span_data)
        traces = await store.query_traces(conversation_id="abc")
    """

    def __init__(self, db_path: str | Path, max_spans_per_trace: int = 5000):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._max_spans_per_trace = max_spans_per_trace
        self._lock = threading.Lock()
        self._init_schema()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self):
        conn = self._get_conn()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS spans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trace_id TEXT NOT NULL,
                    span_id TEXT NOT NULL UNIQUE,
                    parent_span_id TEXT,
                    span_name TEXT NOT NULL,
                    phase TEXT,
                    status TEXT NOT NULL DEFAULT 'running',
                    start_time TEXT NOT NULL,
                    end_time TEXT,
                    duration_ms INTEGER,
                    input_summary TEXT,
                    output_summary TEXT,
                    metadata_json TEXT,
                    conversation_id TEXT,
                    task_id TEXT,
                    workspace_id TEXT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_spans_trace_id ON spans(trace_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_spans_conversation_id ON spans(conversation_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_spans_task_id ON spans(task_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_spans_created_at ON spans(created_at)
            """)
            conn.commit()
        finally:
            conn.close()

    async def persist_span(
        self,
        trace_id: str,
        span_id: str,
        span_name: str,
        status: str = "running",
        parent_span_id: str | None = None,
        phase: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        duration_ms: int | None = None,
        input_summary: str | None = None,
        output_summary: str | None = None,
        metadata: Dict[str, Any] | None = None,
        conversation_id: str | None = None,
        task_id: str | None = None,
        workspace_id: str | None = None,
    ) -> bool:
        """Persist a span entry. If span_id already exists, updates the record (upsert)."""
        try:
            conn = self._get_conn()
            with self._lock:
                # Check span count for this trace to prevent unbounded growth
                count = conn.execute(
                    "SELECT COUNT(*) FROM spans WHERE trace_id = ?", (trace_id,)
                ).fetchone()[0]
                if count >= self._max_spans_per_trace:
                    # Delete oldest spans for this trace above the limit
                    conn.execute(
                        """
                        DELETE FROM spans WHERE trace_id = ? AND id NOT IN (
                            SELECT id FROM spans WHERE trace_id = ?
                            ORDER BY created_at DESC LIMIT ?
                        )
                        """,
                        (trace_id, trace_id, self._max_spans_per_trace - 100),
                    )
                    logger.warning(
                        f"[SpanStore] Trace {trace_id} exceeds {self._max_spans_per_trace} spans, "
                        "pruning old entries"
                    )

                now = datetime.now(UTC).isoformat()
                if not start_time:
                    start_time = now

                conn.execute(
                    """
                    INSERT OR REPLACE INTO spans
                        (trace_id, span_id, parent_span_id, span_name, phase, status,
                         start_time, end_time, duration_ms, input_summary, output_summary,
                         metadata_json, conversation_id, task_id, workspace_id, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        trace_id, span_id, parent_span_id, span_name, phase, status,
                        start_time, end_time, duration_ms, input_summary, output_summary,
                        json.dumps(metadata) if metadata else None,
                        conversation_id, task_id, workspace_id, now,
                    ),
                )
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"[SpanStore] Failed to persist span {span_id}: {e}", exc_info=True)
            return False
        finally:
            conn.close()

    async def query_traces(
        self,
        conversation_id: str | None = None,
        task_id: str | None = None,
        trace_id: str | None = None,
        workspace_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Query trace spans.

        Returns a dict with trace summaries (each trace = {trace_id, spans: [...], ...})
        """
        try:
            conn = self._get_conn()
            conditions = []
            params: List[Any] = []

            if conversation_id:
                conditions.append("conversation_id = ?")
                params.append(conversation_id)
            if task_id:
                conditions.append("task_id = ?")
                params.append(task_id)
            if trace_id:
                conditions.append("trace_id = ?")
                params.append(trace_id)
            if workspace_id:
                conditions.append("workspace_id = ?")
                params.append(workspace_id)

            where_clause = " AND ".join(conditions) if conditions else "1=1"

            # First get distinct trace_ids
            trace_ids_query = f"""
                SELECT DISTINCT trace_id FROM spans
                WHERE {where_clause}
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            """
            rows = conn.execute(trace_ids_query, params + [limit, offset]).fetchall()
            trace_ids = [row["trace_id"] for row in rows]

            # Get all spans for these traces
            if trace_ids:
                placeholders = ",".join(["?"] * len(trace_ids))
                spans_query = f"""
                    SELECT * FROM spans
                    WHERE trace_id IN ({placeholders})
                    ORDER BY created_at ASC
                """
                span_rows = conn.execute(spans_query, trace_ids).fetchall()
            else:
                span_rows = []

            # Group spans by trace_id
            traces: Dict[str, List[Dict]] = {}
            for row in span_rows:
                tid = row["trace_id"]
                span = dict(row)
                if span.get("metadata_json"):
                    try:
                        span["metadata"] = json.loads(span["metadata_json"])
                    except json.JSONDecodeError:
                        span["metadata"] = {}
                    del span["metadata_json"]
                else:
                    span["metadata"] = {}
                traces.setdefault(tid, []).append(span)

            # Build trace summaries
            result_traces = []
            for tid in trace_ids:
                spans = traces.get(tid, [])
                total_duration = 0
                error_count = 0
                for s in spans:
                    if s.get("duration_ms"):
                        total_duration += s["duration_ms"]
                    if s.get("status") == "error":
                        error_count += 1

                result_traces.append({
                    "trace_id": tid,
                    "conversation_id": spans[0].get("conversation_id") if spans else None,
                    "task_id": spans[0].get("task_id") if spans else None,
                    "workspace_id": spans[0].get("workspace_id") if spans else None,
                    "span_count": len(spans),
                    "total_duration_ms": total_duration,
                    "error_count": error_count,
                    "created_at": spans[0].get("created_at") if spans else None,
                    "spans": spans,
                })

            return {
                "traces": result_traces,
                "total": len(trace_ids),
                "limit": limit,
                "offset": offset,
            }
        except Exception as e:
            logger.error(f"[SpanStore] Failed to query traces: {e}", exc_info=True)
            return {"traces": [], "total": 0, "limit": limit, "offset": offset}
        finally:
            conn.close()

    async def delete_old_traces(self, retention_days: int = 30) -> int:
        """Delete traces older than retention_days. Returns count of deleted spans."""
        try:
            conn = self._get_conn()
            cutoff = datetime.now(UTC)
            from datetime import timedelta
            cutoff = cutoff - timedelta(days=retention_days)
            cutoff_str = cutoff.isoformat()

            cursor = conn.execute(
                "DELETE FROM spans WHERE created_at < ?", (cutoff_str,)
            )
            deleted = cursor.rowcount
            conn.commit()
            if deleted > 0:
                logger.info(f"[SpanStore] Deleted {deleted} expired spans (older than {retention_days} days)")
            return deleted
        except Exception as e:
            logger.error(f"[SpanStore] Failed to delete old traces: {e}", exc_info=True)
            return 0
        finally:
            conn.close()


# Singleton instance (lazy-initialized per workspace)
_span_stores: Dict[str, SpanStore] = {}


def get_span_store(workspace_path: str | Path) -> SpanStore:
    """Get or create a SpanStore for the given workspace."""
    key = str(workspace_path)
    if key not in _span_stores:
        db_path = Path(workspace_path) / ".dawei" / "spans.db"
        _span_stores[key] = SpanStore(db_path)
    return _span_stores[key]


def reset_span_store(workspace_path: str | Path) -> None:
    """Delete the workspace's spans.db (all traces/logs) and re-create an empty one.

    Used by the workspace reset endpoint. Evicts the cached SpanStore first so
    the next access re-initializes the schema (deleting the db file alone would
    leave a cached instance writing into a schema-less file).
    """
    key = str(workspace_path)
    _span_stores.pop(key, None)

    db_path = Path(workspace_path) / ".dawei" / "spans.db"
    for suffix in ("", "-wal", "-shm"):
        sidecar = db_path.parent / (db_path.name + suffix)
        try:
            sidecar.unlink()
        except FileNotFoundError:
            pass

    # Re-create empty db + schema
    _span_stores[key] = SpanStore(db_path)
    logger.info(f"[SpanStore] Reset spans.db for workspace at {workspace_path}")
