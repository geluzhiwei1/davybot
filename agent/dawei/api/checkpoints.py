# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Checkpoint Management API Routes

Global checkpoint management endpoints (not workspace-specific)
"""

import logging
from typing import Any

from fastapi import APIRouter

from dawei.workspace import workspace_manager

logger = logging.getLogger(__name__)

# 创建路由器
router = APIRouter(prefix="/api/checkpoints", tags=["checkpoints"])


@router.get("/statistics")
async def get_checkpoint_statistics():
    """获取检查点统计信息

    Returns global statistics across all workspaces.
    """
    # TODO: Implement actual statistics gathering from all workspaces
    # For now, return placeholder data
    return {
        "total_checkpoints": 0,
        "total_size": 0,
        "latest_checkpoint": None,
        "oldest_checkpoint": None,
    }
