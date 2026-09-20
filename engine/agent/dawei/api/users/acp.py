# Copyright (c) 2025 格律至微
# SPDX-License-License-Identifier: AGPL-3.0-only

"""用户级 ACP Agent API（无 workspace 上下文）。

ACP agent 注册本就是全局存储（``{DAWEI_HOME}/configs/acp_agents.json``）——
workspace 级路由 ``/{workspace_id}/acp-agents`` 的 handler 也忽略 workspace_id。
此路由提供 ``/api/users/me/acp-agents`` 入口，与 workspace 级路由共享同一 registry，
是「路径归位」兼容层：不改变存储与现有 workspace 端点，仅暴露 user 级路径。
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

router = APIRouter(prefix="/me/acp-agents", tags=["User ACP"])


# --- Request / Response Models (与 workspace acp_agents.py 一致) ---


class ACPAgentAddRequest(BaseModel):
    command: str = Field(..., description="Executable command, e.g. codex")
    name: str | None = Field(None, description="Display name")
    description: str = Field("", description="Agent description")


class ACPAgentToggleRequest(BaseModel):
    disabled: bool = Field(..., description="True to disable, False to enable")


class ACPAgentResponse(BaseModel):
    success: bool = True
    agent: ACPAgentInfo | None = None
    message: str = ""


class ACPAgentsResponse(BaseModel):
    success: bool = True
    agents: List[ACPAgentInfo] = Field(default_factory=list)


class ACPScanResponse(BaseModel):
    success: bool = True
    agents: List[ACPAgentInfo] = Field(default_factory=list)
    message: str = ""


# --- API Endpoints (复用全局 agent_registry，无 workspace_id) ---


@router.get("", response_model=ACPAgentsResponse)
async def list_user_acp_agents():
    """获取所有已注册的 ACP agent（user 级入口，全局 registry）"""
    return ACPAgentsResponse(success=True, agents=load_registry())


@router.get("/available", response_model=ACPAgentsResponse)
async def list_user_available_acp_agents():
    """获取当前可用的 ACP agent（已安装且未禁用）"""
    return ACPAgentsResponse(success=True, agents=list_available_agents())


@router.post("/scan", response_model=ACPScanResponse)
async def scan_user_acp_agents():
    """扫描系统 PATH，发现可用 ACP agent 并与已有注册合并"""
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
async def create_user_acp_agent(request: ACPAgentAddRequest):
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
async def delete_user_acp_agent(command: str):
    """删除 ACP agent"""
    if not remove_agent(command):
        raise HTTPException(status_code=404, detail=f"Agent '{command}' 不存在")
    return ACPAgentResponse(success=True, message=f"Agent '{command}' 已删除")


@router.put("/{command}/toggle", response_model=ACPAgentResponse)
async def toggle_user_acp_agent(command: str, request: ACPAgentToggleRequest):
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
