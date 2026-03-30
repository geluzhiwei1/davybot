# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""ACP Agent Management API Routes

CRUD + scan for local ACP agent discovery.
Config persisted to ``{DAWEI_HOME}/configs/acp_agents.json``.
Follows the same pattern as mcp_servers.py.
"""

import logging
from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from dawei.acp.agent_registry import (
    ACPAgentInfo,
    add_agent,
    discover_and_merge,
    list_available_agents,
    load_registry,
    remove_agent,
    toggle_agent,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/{workspace_id}/acp-agents", tags=["acp-agents"])


# --- Request / Response Models ---


class ACPAgentAddRequest(BaseModel):
    """Manually add an ACP agent."""

    command: str = Field(..., description="Executable command, e.g. codex")
    name: str | None = Field(None, description="Display name")
    description: str = Field("", description="Agent description")


class ACPAgentToggleRequest(BaseModel):
    """Toggle agent enabled/disabled."""

    disabled: bool = Field(..., description="True to disable, False to enable")


class ACPAgentResponse(BaseModel):
    """Single agent info."""

    success: bool = True
    agent: ACPAgentInfo | None = None
    message: str = ""


class ACPAgentsResponse(BaseModel):
    """List of registered agents."""

    success: bool = True
    agents: List[ACPAgentInfo] = Field(default_factory=list)


class ACPScanResponse(BaseModel):
    """Scan result."""

    success: bool = True
    agents: List[ACPAgentInfo] = Field(default_factory=list)
    message: str = ""


# --- API Endpoints ---


@router.get("", response_model=ACPAgentsResponse)
async def get_acp_agents(workspace_id: str):
    """获取所有已注册的 ACP agent 列表"""
    agents = load_registry()
    return ACPAgentsResponse(success=True, agents=agents)


@router.get("/available", response_model=ACPAgentsResponse)
async def get_available_acp_agents(workspace_id: str):
    """获取当前可用的 ACP agent（已安装且未禁用）"""
    agents = list_available_agents()
    return ACPAgentsResponse(success=True, agents=agents)


@router.post("/scan", response_model=ACPScanResponse)
async def scan_acp_agents(workspace_id: str):
    """扫描系统 PATH，发现可用的 ACP agent 并与已有注册合并"""
    try:
        agents = discover_and_merge()
        return ACPScanResponse(
            success=True,
            agents=agents,
            message=f"发现 {len(agents)} 个 ACP agent",
        )
    except Exception as exc:
        logger.error("ACP agent scan failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("", response_model=ACPAgentResponse, status_code=201)
async def create_acp_agent(workspace_id: str, request: ACPAgentAddRequest):
    """手动添加 ACP agent"""
    try:
        agent = add_agent(
            command=request.command,
            name=request.name,
            description=request.description,
        )
        return ACPAgentResponse(
            success=True,
            agent=agent,
            message=f"Agent '{request.command}' 添加成功",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{command}", response_model=ACPAgentResponse)
async def delete_acp_agent(workspace_id: str, command: str):
    """删除 ACP agent"""
    removed = remove_agent(command)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Agent '{command}' 不存在")
    return ACPAgentResponse(
        success=True,
        message=f"Agent '{command}' 已删除",
    )


@router.put("/{command}/toggle", response_model=ACPAgentResponse)
async def toggle_acp_agent(workspace_id: str, command: str, request: ACPAgentToggleRequest):
    """启用/禁用 ACP agent"""
    agent = toggle_agent(command, request.disabled)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{command}' 不存在")
    status_text = "已禁用" if request.disabled else "已启用"
    return ACPAgentResponse(
        success=True,
        agent=agent,
        message=f"Agent '{command}' {status_text}",
    )
