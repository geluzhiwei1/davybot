# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""用户级 MCP 服务器配置 API

读写 {DAWEI_HOME}/configs/mcp.json，提供用户全局 MCP 服务器 CRUD。
与 workspace 级 MCP API（/{workspace_id}/mcp-servers）对应，共享相同的模型结构。
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from dawei.api.auth import get_authenticated_user_id

from dawei import get_dawei_home

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/me/mcp-servers", tags=["User MCP"])


# --- Models (与 workspace mcp_servers.py 保持一致) ---


class MCPServerConfig(BaseModel):
    """MCP server configuration"""

    name: str = Field(..., description="服务器名称（唯一标识）")
    command: str = Field(..., description="启动命令")
    args: List[str] = Field(default_factory=list, description="命令参数")
    cwd: str | None = Field(None, description="工作目录")
    env: Dict[str, str] = Field(default_factory=dict, description="环境变量")
    transport: str = Field("stdio", description="传输类型: stdio|sse|http")
    url: str | None = Field(None, description="sse/http 传输端点")
    headers: Dict[str, str] = Field(default_factory=dict, description="sse/http 自定义请求头")
    always_allow: List[str] = Field(default_factory=list, description="始终允许的工具列表")
    timeout: int = Field(300, description="超时时间(秒)")
    disabled: bool = Field(False, description="是否禁用")


class MCPServerCreate(BaseModel):
    """Create MCP server request"""

    name: str = Field(..., description="服务器名称（唯一标识）")
    command: str = Field(..., description="启动命令")
    args: List[str] = Field(default_factory=list, description="命令参数")
    cwd: str | None = Field(None, description="工作目录")
    env: Dict[str, str] = Field(default_factory=dict, description="环境变量")
    transport: str = Field("stdio", description="传输类型: stdio|sse|http")
    url: str | None = Field(None, description="sse/http 传输端点")
    headers: Dict[str, str] = Field(default_factory=dict, description="sse/http 自定义请求头")
    always_allow: List[str] = Field(default_factory=list, description="始终允许的工具列表")
    timeout: int = Field(300, description="超时时间(秒)")
    disabled: bool = Field(False, description="是否禁用")


class MCPServerUpdate(BaseModel):
    """Update MCP server request"""

    command: str | None = None
    args: List[str] | None = None
    cwd: str | None = None
    env: Dict[str, str] | None = None
    transport: str | None = None
    url: str | None = None
    headers: Dict[str, str] | None = None
    always_allow: List[str] | None = None
    timeout: int | None = None
    disabled: bool | None = None


class MCPServersResponse(BaseModel):
    """MCP servers list response"""

    success: bool = True
    servers: List[MCPServerConfig] = Field(default_factory=list)


class MCPServerOperationResponse(BaseModel):
    """MCP server operation response"""

    success: bool
    message: str
    server: MCPServerConfig | None = None


class MCPServerTestResponse(BaseModel):
    """MCP server test response"""

    success: bool
    message: str
    tools_count: int = 0
    resources_count: int = 0
    latency_ms: int = 0
    error: str | None = None


# --- Helper Functions ---


def _safe_uid(user_id: str | None) -> str:
    uid = user_id or "default_user"
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in uid)


def _get_config_file(user_id: str = "default_user") -> Path:
    """获取用户级 MCP 配置文件路径（per-user：configs/{user_id}/mcp.json）。"""
    return get_dawei_home() / "configs" / _safe_uid(user_id) / "mcp.json"


def _load_config(user_id: str = "default_user") -> Dict[str, Any]:
    """加载用户级 MCP 配置"""
    config_file = _get_config_file(user_id)
    if not config_file.exists():
        return {"mcpServers": {}}
    try:
        with config_file.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load user MCP config: {e}")
        return {"mcpServers": {}}


def _save_config(config: Dict[str, Any], user_id: str = "default_user") -> None:
    """保存用户级 MCP 配置"""
    config_file = _get_config_file(user_id)
    config_file.parent.mkdir(parents=True, exist_ok=True)
    with config_file.open("w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def _to_api_config(name: str, raw: Dict[str, Any]) -> MCPServerConfig:
    """将存储格式转为 API 模型"""
    return MCPServerConfig(
        name=name,
        command=raw.get("command", ""),
        args=raw.get("args", []),
        cwd=raw.get("cwd"),
        env=raw.get("env", {}),
        transport=raw.get("transport", "stdio"),
        url=raw.get("url"),
        headers=raw.get("headers", {}),
        always_allow=raw.get("always_allow", raw.get("alwaysAllow", [])),
        timeout=raw.get("timeout", 300),
        disabled=raw.get("disabled", False),
    )


# --- API Endpoints ---


# 后台自动重连 task 的强引用（防 GC，完成即自清）
_AUTOCONNECT_TASKS: set = set()


async def _areload_all_workspace_mcp(user_id: str = "default_user") -> None:
    """用户级 MCP 是该用户所有工作区 context 的基线，CRUD 后遍历该 user 的已初始化
    WorkspaceContext（按 key (path, user_id) 过滤），逐个 areload_configs()，让共享
    manager 立即看到新配置。best-effort，失败仅告警。不 reload 其他 user 的 context。
    """
    try:
        from dawei.workspace.workspace_service import WorkspaceService

        uid = user_id or "default_user"
        for key, ctx in WorkspaceService.get_all_contexts().items():
            # key = (path, user_id)；只 reload 当前 user 的 context
            if len(key) == 2 and key[1] != uid:
                continue
            mgr = getattr(ctx, "mcp_tool_manager", None)
            if mgr is not None and hasattr(mgr, "areload_configs"):
                try:
                    await mgr.areload_configs()
                    # reload 会 disconnect 全部 server；MCP 一级工具注入
                    # （mcp__ 前缀）依赖 connected 状态，reload 后自动重连
                    # （后台任务，不阻塞 API 响应；持引用防 GC）。
                    # FAST FAIL：hasattr 显式检查替代 except AttributeError 静默吞错；
                    # async 上下文必有 running loop，create_task 失败由外层告警。
                    if hasattr(mgr, "auto_connect_all"):
                        import asyncio

                        task = asyncio.get_running_loop().create_task(mgr.auto_connect_all())
                        _AUTOCONNECT_TASKS.add(task)
                        task.add_done_callback(_AUTOCONNECT_TASKS.discard)
                    else:
                        logger.warning(f"mcp manager of {ctx.workspace_id} lacks auto_connect_all; reconnect skipped")
                except Exception as e:
                    logger.warning(f"areload MCP configs for {ctx.workspace_id} failed: {e}")
    except Exception as e:
        logger.warning(f"_areload_all_workspace_mcp failed: {e}")


@router.get("", response_model=MCPServersResponse)
async def list_user_mcp_servers(current_user: str = Depends(get_authenticated_user_id)):
    """获取用户级所有 MCP 服务器配置"""
    config = _load_config(current_user)
    servers = []
    for name, raw in config.get("mcpServers", {}).items():
        servers.append(_to_api_config(name, raw))
    return MCPServersResponse(success=True, servers=servers)


@router.post("", response_model=MCPServerOperationResponse, status_code=201)
async def create_user_mcp_server(
    request: MCPServerCreate, current_user: str = Depends(get_authenticated_user_id)
):
    """创建用户级 MCP 服务器配置"""
    config = _load_config(current_user)
    mcp_servers = config.setdefault("mcpServers", {})

    if request.name in mcp_servers:
        raise HTTPException(status_code=400, detail=f"MCP server '{request.name}' already exists")

    server_data = request.model_dump()
    # 存储 alwaysAllow 格式（与 MCPConfigLoader 兼容）
    server_data["alwaysAllow"] = server_data.pop("always_allow", [])
    mcp_servers[request.name] = server_data
    _save_config(config, current_user)
    await _areload_all_workspace_mcp(current_user)

    logger.info(f"Created user-level MCP server '{request.name}' (user={current_user})")
    return MCPServerOperationResponse(
        success=True,
        message=f"MCP server '{request.name}' created successfully",
        server=_to_api_config(request.name, server_data),
    )


@router.put("/{server_name}", response_model=MCPServerOperationResponse)
async def update_user_mcp_server(
    server_name: str,
    request: MCPServerUpdate,
    current_user: str = Depends(get_authenticated_user_id),
):
    """更新用户级 MCP 服务器配置"""
    config = _load_config(current_user)
    mcp_servers = config.get("mcpServers", {})

    if server_name not in mcp_servers:
        raise HTTPException(status_code=404, detail=f"MCP server '{server_name}' not found")

    existing = mcp_servers[server_name]
    update_data = request.model_dump(exclude_unset=True)
    # 转换字段名
    if "always_allow" in update_data:
        update_data["alwaysAllow"] = update_data.pop("always_allow")

    for key, value in update_data.items():
        if value is not None:
            existing[key] = value

    mcp_servers[server_name] = existing
    _save_config(config, current_user)
    await _areload_all_workspace_mcp(current_user)

    logger.info(f"Updated user-level MCP server '{server_name}' (user={current_user})")
    return MCPServerOperationResponse(
        success=True,
        message=f"MCP server '{server_name}' updated successfully",
        server=_to_api_config(server_name, existing),
    )


@router.delete("/{server_name}", response_model=MCPServerOperationResponse)
async def delete_user_mcp_server(
    server_name: str, current_user: str = Depends(get_authenticated_user_id)
):
    """删除用户级 MCP 服务器配置"""
    config = _load_config(current_user)
    mcp_servers = config.get("mcpServers", {})

    if server_name not in mcp_servers:
        raise HTTPException(status_code=404, detail=f"MCP server '{server_name}' not found")

    del mcp_servers[server_name]
    _save_config(config, current_user)
    await _areload_all_workspace_mcp(current_user)

    logger.info(f"Deleted user-level MCP server '{server_name}' (user={current_user})")
    return MCPServerOperationResponse(
        success=True,
        message=f"MCP server '{server_name}' deleted successfully",
        server=None,
    )


@router.post("/{server_name}/test", response_model=MCPServerTestResponse)
async def test_user_mcp_server(
    server_name: str, current_user: str = Depends(get_authenticated_user_id)
):
    """真·连接测试（用户级）：spawn/连接，返回工具/资源数与延迟（替原 TODO 假桩）。"""
    import asyncio
    import time

    from dawei.tools.mcp_tool_manager import MCPToolManager

    mgr = MCPToolManager(workspace_root=None, user_id=current_user)  # 仅用户级配置
    if server_name not in mgr.get_all_servers():
        raise HTTPException(status_code=404, detail=f"MCP server '{server_name}' not found")

    t0 = time.time()
    try:
        ok = await asyncio.wait_for(mgr.connect_server(server_name), timeout=30)
    except asyncio.TimeoutError:
        ok = False
    latency_ms = int((time.time() - t0) * 1000)

    info = mgr.get_server_info(server_name)
    tools_count = len(info.tools) if info else 0
    resources_count = len(info.resources) if info else 0
    error = info.last_error if (info and not ok) else None

    try:
        await mgr.disconnect_server(server_name)
    except Exception as e:
        logger.warning(f"disconnect after test failed for '{server_name}': {e}")

    logger.info(
        f"MCP test(user) '{server_name}': ok={ok}, tools={tools_count}, "
        f"resources={resources_count}, latency={latency_ms}ms"
    )
    return MCPServerTestResponse(
        success=bool(ok),
        message=(
            f"已连接：{tools_count} 个工具、{resources_count} 个资源"
            if ok
            else f"连接失败：{error or '未知错误'}"
        ),
        tools_count=tools_count,
        resources_count=resources_count,
        latency_ms=latency_ms,
        error=error,
    )


@router.get("/status")
async def get_user_mcp_servers_status(current_user: str = Depends(get_authenticated_user_id)):
    """主动探活（用户级）：逐个连接返回 status/tools/resources。"""
    import asyncio

    from dawei.tools.mcp_tool_manager import MCPToolManager

    mgr = MCPToolManager(workspace_root=None, user_id=current_user)
    out = []
    for name in list(mgr.get_all_servers().keys()):
        info = mgr.get_server_info(name)
        if info and info.config.disabled:
            out.append(
                {"name": name, "status": "disabled", "tools_count": 0, "resources_count": 0, "error": None}
            )
            continue
        try:
            await asyncio.wait_for(mgr.connect_server(name), timeout=30)
        except asyncio.TimeoutError:
            pass
        info = mgr.get_server_info(name)
        out.append(
            {
                "name": name,
                "status": info.status if info else "unknown",
                "tools_count": len(info.tools) if info else 0,
                "resources_count": len(info.resources) if info else 0,
                "error": info.last_error if info else None,
            }
        )
        try:
            await mgr.disconnect_server(name)
        except Exception:
            pass
    return {"success": True, "servers": out}
