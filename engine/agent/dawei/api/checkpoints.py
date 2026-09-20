# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Checkpoint Management API Routes

Global checkpoint management endpoints (not workspace-specific).
Scans .dawei/checkpoints/ in each workspace for checkpoint files.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from dawei.workspace import workspace_manager

logger = logging.getLogger(__name__)

# 创建路由器
router = APIRouter(prefix="/api/checkpoints", tags=["checkpoints"])


def _scan_workspace_checkpoints(workspace_path: str) -> list[dict[str, Any]]:
    """Scan a single workspace for checkpoint files."""
    checkpoints_dir = Path(workspace_path) / ".dawei" / "checkpoints"
    if not checkpoints_dir.exists():
        return []

    results = []
    for cp_file in checkpoints_dir.glob("*.json"):
        try:
            stat = cp_file.stat()
            results.append({
                "name": cp_file.name,
                "path": str(cp_file),
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })
        except OSError:
            continue
    return results


@router.get("/statistics")
async def get_checkpoint_statistics():
    """获取检查点统计信息

    Returns global statistics across all workspaces.
    """
    all_checkpoints: list[dict[str, Any]] = []

    workspaces = workspace_manager.get_all_workspaces()
    for ws in workspaces:
        ws_path = ws.get("path")
        if ws_path:
            all_checkpoints.extend(_scan_workspace_checkpoints(ws_path))

    total_size = sum(cp["size"] for cp in all_checkpoints)
    latest = max((cp["modified"] for cp in all_checkpoints), default=None)
    oldest = min((cp["modified"] for cp in all_checkpoints), default=None)

    return {
        "total_checkpoints": len(all_checkpoints),
        "total_size": total_size,
        "latest_checkpoint": latest,
        "oldest_checkpoint": oldest,
    }


@router.get("/list")
async def list_checkpoints(page: int = 1, limit: int = 100):
    """获取检查点列表

    Args:
        page: 页码（从1开始）
        limit: 每页数量

    Returns:
        检查点列表
    """
    all_checkpoints: list[dict[str, Any]] = []

    workspaces = workspace_manager.get_all_workspaces()
    for ws in workspaces:
        ws_path = ws.get("path")
        if ws_path:
            cps = _scan_workspace_checkpoints(ws_path)
            for cp in cps:
                cp["workspace"] = ws.get("name", "")
            all_checkpoints.extend(cps)

    # Sort by modified time descending
    all_checkpoints.sort(key=lambda x: x.get("modified", ""), reverse=True)

    total = len(all_checkpoints)
    pages = (total + limit - 1) // limit if limit > 0 else 0
    start = (page - 1) * limit
    items = all_checkpoints[start : start + limit]

    return {
        "items": items,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": pages,
    }
