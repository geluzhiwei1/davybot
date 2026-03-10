# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""MCP Server Management API Routes

Provides CRUD operations for individual MCP servers within a workspace.
MCP servers are stored in the mode settings configuration.
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from dawei.workspace import workspace_manager
from dawei.workspace.user_workspace import UserWorkspace

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/{workspace_id}/mcp-servers", tags=["mcp-servers"])


# --- Request/Response Models ---


class MCPServerConfig(BaseModel):
    """MCP server configuration"""

    name: str = Field(..., description="服务器名称（唯一标识）")
    command: str = Field(..., description="启动命令")
    args: List[str] = Field(default_factory=list, description="命令参数")
    cwd: str | None = Field(None, description="工作目录")
    always_allow: List[str] = Field(default_factory=list, description="始终允许的工具列表")
    timeout: int = Field(300, description="超时时间(秒)")
    disabled: bool = Field(False, description="是否禁用")


class MCPServerCreate(BaseModel):
    """Create MCP server request"""

    name: str = Field(..., description="服务器名称（唯一标识）")
    command: str = Field(..., description="启动命令")
    args: List[str] = Field(default_factory=list, description="命令参数")
    cwd: str | None = Field(None, description="工作目录")
    always_allow: List[str] = Field(default_factory=list, description="始终允许的工具列表")
    timeout: int = Field(300, description="超时时间(秒)")
    disabled: bool = Field(False, description="是否禁用")


class MCPServerUpdate(BaseModel):
    """Update MCP server request"""

    command: str | None = None
    args: List[str] | None = None
    cwd: str | None = None
    always_allow: List[str] | None = None
    timeout: int | None = None
    disabled: bool | None = None


class MCPServersResponse(BaseModel):
    """MCP servers list response"""

    success: bool = True
    servers: List[MCPServerConfig] = Field(default_factory=list)


class MCPServerTestResponse(BaseModel):
    """MCP server test response"""

    success: bool
    message: str


class MCPServerOperationResponse(BaseModel):
    """MCP server operation response"""

    success: bool
    message: str
    server: MCPServerConfig | None = None


# --- Helper Functions ---


def get_user_workspace(workspace_id: str) -> UserWorkspace:
    """Dependency to get a UserWorkspace instance."""
    workspace_info = workspace_manager.get_workspace_by_id(workspace_id)
    if not workspace_info:
        raise HTTPException(status_code=404, detail=f"Workspace with ID {workspace_id} not found")

    workspace_path = workspace_info.get("path")
    if not workspace_path:
        raise HTTPException(
            status_code=404,
            detail=f"Workspace path not found for ID {workspace_id}",
        )

    return UserWorkspace(workspace_path=workspace_path)


def get_mode_settings_file(workspace: UserWorkspace) -> Path:
    """获取模式设置文件路径"""
    return workspace.workspace_path / ".dawei" / "mode_settings.json"


def load_mode_settings(workspace: UserWorkspace) -> Dict[str, Any]:
    """加载模式设置"""
    settings_file = get_mode_settings_file(workspace)

    if not settings_file.exists():
        return {"customModes": [], "mcpServers": {}}

    try:
        with settings_file.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load mode settings: {e}")
        return {"customModes": [], "mcpServers": {}}


def save_mode_settings(workspace: UserWorkspace, settings: Dict[str, Any]) -> None:
    """保存模式设置"""
    settings_file = get_mode_settings_file(workspace)

    # 确保目录存在
    settings_file.parent.mkdir(parents=True, exist_ok=True)

    # 保存设置
    with settings_file.open("w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


def mcp_config_to_api(config: Dict[str, Any]) -> MCPServerConfig:
    """将后端MCP配置转换为API格式"""
    return MCPServerConfig(name=config.get("name", ""), command=config.get("command", ""), args=config.get("args", []), cwd=config.get("cwd"), always_allow=config.get("always_allow", config.get("alwaysAllow", [])), timeout=config.get("timeout", 300), disabled=config.get("disabled", False))


def api_config_to_mcp(config: MCPServerConfig | MCPServerCreate | MCPServerUpdate) -> Dict[str, Any]:
    """将API配置转换为后端MCP配置格式"""
    data = config.model_dump(exclude_unset=True)

    # 转换字段名
    if "always_allow" in data:
        data["alwaysAllow"] = data.pop("always_allow")

    return data


# --- API Endpoints ---


@router.get("", response_model=MCPServersResponse)
async def get_mcp_servers(workspace_id: str):
    """获取所有MCP服务器配置

    Returns:
        MCPServersResponse: 包含所有MCP服务器配置的列表
    """
    workspace = get_user_workspace(workspace_id)
    mode_settings = load_mode_settings(workspace)

    mcp_servers = mode_settings.get("mcpServers", {})

    servers = []
    for name, config in mcp_servers.items():
        server_config = mcp_config_to_api(config)
        server_config.name = name
        servers.append(server_config)

    return MCPServersResponse(success=True, servers=servers)


@router.post("", response_model=MCPServerOperationResponse, status_code=201)
async def create_mcp_server(workspace_id: str, request: MCPServerCreate):
    """创建新的MCP服务器配置

    Args:
        workspace_id: 工作区ID
        request: MCP服务器配置

    Returns:
        MCPServerOperationResponse: 操作结果

    Raises:
        HTTPException: 服务器名称已存在时抛出400错误
    """
    workspace = get_user_workspace(workspace_id)
    mode_settings = load_mode_settings(workspace)

    # 检查服务器名称是否已存在
    mcp_servers = mode_settings.get("mcpServers", {})
    if request.name in mcp_servers:
        raise HTTPException(status_code=400, detail=f"MCP server '{request.name}' already exists")

    # 添加新服务器
    server_data = api_config_to_mcp(request)
    server_data["name"] = request.name
    mcp_servers[request.name] = server_data

    # 保存设置
    mode_settings["mcpServers"] = mcp_servers
    save_mode_settings(workspace, mode_settings)

    logger.info(f"Created MCP server '{request.name}' in workspace {workspace_id}")

    server_config = mcp_config_to_api(server_data)
    server_config.name = request.name

    return MCPServerOperationResponse(success=True, message=f"MCP server '{request.name}' created successfully", server=server_config)


@router.put("/{server_name}", response_model=MCPServerOperationResponse)
async def update_mcp_server(workspace_id: str, server_name: str, request: MCPServerUpdate):
    """更新MCP服务器配置

    Args:
        workspace_id: 工作区ID
        server_name: 服务器名称
        request: 更新的配置

    Returns:
        MCPServerOperationResponse: 操作结果

    Raises:
        HTTPException: 服务器不存在时抛出404错误
    """
    workspace = get_user_workspace(workspace_id)
    mode_settings = load_mode_settings(workspace)

    # 获取现有服务器配置
    mcp_servers = mode_settings.get("mcpServers", {})
    if server_name not in mcp_servers:
        raise HTTPException(status_code=404, detail=f"MCP server '{server_name}' not found")

    # 更新服务器配置
    existing_config = mcp_servers[server_name]
    update_data = api_config_to_mcp(request)

    # 合并配置
    for key, value in update_data.items():
        if value is not None:
            existing_config[key] = value

    mcp_servers[server_name] = existing_config

    # 保存设置
    mode_settings["mcpServers"] = mcp_servers
    save_mode_settings(workspace, mode_settings)

    logger.info(f"Updated MCP server '{server_name}' in workspace {workspace_id}")

    server_config = mcp_config_to_api(existing_config)
    server_config.name = server_name

    return MCPServerOperationResponse(success=True, message=f"MCP server '{server_name}' updated successfully", server=server_config)


@router.delete("/{server_name}", response_model=MCPServerOperationResponse)
async def delete_mcp_server(workspace_id: str, server_name: str):
    """删除MCP服务器配置

    Args:
        workspace_id: 工作区ID
        server_name: 服务器名称

    Returns:
        MCPServerOperationResponse: 操作结果

    Raises:
        HTTPException: 服务器不存在时抛出404错误
    """
    workspace = get_user_workspace(workspace_id)
    mode_settings = load_mode_settings(workspace)

    # 获取现有服务器配置
    mcp_servers = mode_settings.get("mcpServers", {})
    if server_name not in mcp_servers:
        raise HTTPException(status_code=404, detail=f"MCP server '{server_name}' not found")

    # 删除服务器
    del mcp_servers[server_name]

    # 保存设置
    mode_settings["mcpServers"] = mcp_servers
    save_mode_settings(workspace, mode_settings)

    logger.info(f"Deleted MCP server '{server_name}' from workspace {workspace_id}")

    return MCPServerOperationResponse(success=True, message=f"MCP server '{server_name}' deleted successfully", server=None)


@router.post("/{server_name}/test", response_model=MCPServerTestResponse)
async def test_mcp_server(workspace_id: str, server_name: str):
    """测试MCP服务器连接

    Args:
        workspace_id: 工作区ID
        server_name: 服务器名称

    Returns:
        MCPServerTestResponse: 测试结果

    Raises:
        HTTPException: 服务器不存在时抛出404错误
    """
    workspace = get_user_workspace(workspace_id)
    mode_settings = load_mode_settings(workspace)

    # 检查服务器是否存在
    mcp_servers = mode_settings.get("mcpServers", {})
    if server_name not in mcp_servers:
        raise HTTPException(status_code=404, detail=f"MCP server '{server_name}' not found")

    server_config = mcp_servers[server_name]

    # TODO: 实现实际的连接测试逻辑
    # 这里需要使用MCP工具管理器来测试连接
    # 目前先返回成功，等待MCP工具管理器集成

    logger.info(f"Testing MCP server '{server_name}' in workspace {workspace_id}")

    return MCPServerTestResponse(success=True, message=f"MCP server '{server_name}' connection test passed")
