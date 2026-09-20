# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Agent diagnostics API — returns the agent capability matrix for a workspace.

Provides a structured view of which agent features are enabled/degraded,
useful for debugging and transparency.
"""

import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from dawei.api.workspaces.core import get_user_workspace
from dawei.logg.logging import get_logger
from dawei.workspace.user_workspace import UserWorkspace

logger = get_logger(__name__)

router = APIRouter(tags=["workspace-diagnostics"])


@router.get("/{workspace_id}/diagnostics")
async def get_workspace_agent_diagnostics(workspace: UserWorkspace = Depends(get_user_workspace)) -> dict:
    """Get agent capability matrix for a workspace.

    Returns a structured JSON with the status of each agent subsystem:
    - memory: enabled/degraded/off
    - knowledge: enabled/degraded/off
    - compression: enabled/off (with config)
    - mode: orchestrator/pdca
    - config: current mode and other settings

    """
    workspace_id = str(workspace.uuid)
    config = workspace.get_config()

    # ── Memory subsystem ──
    memory_status = "off"
    memory_details = {}
    if config.memory.enabled:
        memory_db = Path(workspace.absolute_path) / ".dawei" / "memory.db"
        if memory_db.exists():
            memory_status = "enabled"
            memory_details = {
                "db_path": str(memory_db),
                "db_size_bytes": memory_db.stat().st_size if memory_db.is_file() else 0,
            }
        else:
            memory_status = "degraded"
            memory_details = {
                "reason": "memory.db not found",
                "recoverable": True,
            }

    # ── Knowledge subsystem ──
    knowledge_status = "enabled" if config.knowledge.enabled else "off"
    knowledge_details = {}
    if config.knowledge.enabled:
        knowledge_details = {
            "auto_index": getattr(config.knowledge, "auto_index", False),
        }

    # ── Compression ──
    compression_status = "enabled" if config.compression.enabled else "off"
    compression_details = {}
    if config.compression.enabled:
        compression_details = {
            "preserve_recent": config.compression.preserve_recent,
            "max_tokens": config.compression.max_tokens,
            "compression_threshold": config.compression.compression_threshold,
            "aggressive_threshold": config.compression.aggressive_threshold,
            "memory_integration_enabled": config.compression.memory_integration_enabled,
        }

    # ── Planner / PDCA ──
    plan_status = "available" if getattr(config, "planner_config", None) else "unavailable"

    # ── Skills ──
    dawei_home_skills = Path.home() / ".dawei" / "skills"
    workspace_skills = Path(workspace.absolute_path) / ".dawei" / "skills"
    skills_count = 0
    for root in (dawei_home_skills, workspace_skills):
        if root.exists():
            skills_count += sum(1 for _ in root.rglob("SKILL.md"))
    skills_status = f"{skills_count} skills" if skills_count > 0 else "no skills"

    # ── MCP Servers ──
    mcp_count = 0
    try:
        from dawei.mcp_servers.server_config import load_server_configs
        configs = load_server_configs(Path(workspace.absolute_path))
        mcp_count = len(configs)
    except Exception:
        pass
    mcp_status = f"{mcp_count} servers" if mcp_count > 0 else "no MCP servers"

    # ── Build capability matrix ──
    return {
        "workspace_id": workspace_id,
        "workspace_name": workspace.workspace_info.name if workspace.workspace_info else "",
        "mode": config.mode.value if hasattr(config.mode, "value") else str(config.mode),
        "capabilities": {
            "memory": {
                "status": memory_status,
                "details": memory_details,
            },
            "knowledge": {
                "status": knowledge_status,
                "details": knowledge_details,
            },
            "compression": {
                "status": compression_status,
                "details": compression_details,
            },
            "planning": {
                "status": plan_status,
            },
            "skills": {
                "status": skills_status,
            },
            "mcp": {
                "status": mcp_status,
            },
        },
    }
