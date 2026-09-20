# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Traces query API — retrieve persisted Agent execution traces.

Phase 3: provides historical trace queries by conversation_id, task_id, or trace_id.
"""

from fastapi import APIRouter, Depends, Query, HTTPException

from dawei.agentic.span_store import get_span_store
from dawei.api.workspaces.core import get_user_workspace
from dawei.logg.logging import get_logger
from dawei.workspace.user_workspace import UserWorkspace

logger = get_logger(__name__)

router = APIRouter(tags=["workspace-traces"])


@router.get("/{workspace_id}/traces")
async def get_workspace_traces(
    workspace: UserWorkspace = Depends(get_user_workspace),
    conversation_id: str | None = Query(None, description="Filter by conversation ID"),
    task_id: str | None = Query(None, description="Filter by task ID"),
    trace_id: str | None = Query(None, description="Filter by specific trace ID"),
    limit: int = Query(50, ge=1, le=500, description="Max traces to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
) -> dict:
    """Query persisted agent execution traces.

    Returns a list of trace summaries with their spans.
    """
    try:
        store = get_span_store(str(workspace.absolute_path))
        # 不按 workspace_id 过滤:SpanStore 本身已按工作区路径隔离(每个工作区
        # 独立的 .dawei/spans.db),而 UserWorkspace.uuid 是每实例随机值
        # (user_workspace.py __init__),用它过滤必然 0 命中 —— 修复前
        # 追踪页 REST 引导永远为空(生产事故 2026-09-18:工作区有 46 条
        # span 但 GET /traces 返回 0)。
        result = await store.query_traces(
            conversation_id=conversation_id,
            task_id=task_id,
            trace_id=trace_id,
            limit=limit,
            offset=offset,
        )
        return {
            "success": True,
            "data": result,
        }
    except Exception as e:
        logger.error(f"[Traces API] Failed to query traces: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to query traces: {e}")


@router.delete("/{workspace_id}/traces")
async def cleanup_old_traces(
    workspace: UserWorkspace = Depends(get_user_workspace),
    retention_days: int = Query(30, ge=1, le=365, description="Retention period in days"),
) -> dict:
    """Delete trace spans older than retention_days."""
    try:
        store = get_span_store(str(workspace.absolute_path))
        deleted = await store.delete_old_traces(retention_days=retention_days)
        return {
            "success": True,
            "data": {"deleted_spans": deleted, "retention_days": retention_days},
        }
    except Exception as e:
        logger.error(f"[Traces API] Failed to cleanup traces: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to cleanup traces: {e}")
