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

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from dawei import get_dawei_home
from dawei.api.auth import get_authenticated_user_id
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
    env: Dict[str, str] = Field(default_factory=dict, description="环境变量（per-server，全量传子进程）")
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


class MCPServerTestResponse(BaseModel):
    """MCP server test response"""

    success: bool
    message: str
    tools_count: int = 0
    resources_count: int = 0
    latency_ms: int = 0
    error: str | None = None


class MCPServerOperationResponse(BaseModel):
    """MCP server operation response"""

    success: bool
    message: str
    server: MCPServerConfig | None = None


# --- Helper Functions ---


from dawei.api.workspaces._deps import get_user_workspace

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


def get_runtime_mcp_file(workspace: UserWorkspace) -> Path:
    """运行时 mcp_tool_manager 加载的文件:{ws}/.dawei/configs/mcp.json"""
    return workspace.workspace_path / ".dawei" / "configs" / "mcp.json"


def sync_runtime_mcp_file(workspace: UserWorkspace, mcp_servers: Dict[str, Any]) -> None:
    """把更新后的 mcpServers 段同步写入 configs/mcp.json（双写一致性）。

    运行时 ``MCPConfigLoader.load_workspace_mcp_configs`` 读的是 configs/mcp.json，
    而 API CRUD 只写 mode_settings.json —— 双写断层会导致手动建的 ws MCP 运行时
    加载不到（仅市场安装 resource_installer 双写了才能用）。这里与安装逻辑一致地
    双写，但 CRUD 持完整权威视图，故整段替换（非 union），确保删除也能反映到运行时文件。
    只更新 mcpServers 段，保留文件中其他顶层字段。
    """
    runtime_file = get_runtime_mcp_file(workspace)
    runtime_file.parent.mkdir(parents=True, exist_ok=True)

    runtime_existing: Dict[str, Any] = {}
    if runtime_file.exists():
        try:
            runtime_existing = json.loads(runtime_file.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"Failed to read runtime mcp.json, will overwrite: {e}")
            runtime_existing = {}

    runtime_existing["mcpServers"] = mcp_servers
    runtime_file.write_text(
        json.dumps(runtime_existing, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info(f"Synced {len(mcp_servers)} MCP servers to {runtime_file}")


def _try_reload_workspace_mcp(workspace: UserWorkspace) -> None:
    """best-effort 让运行时共享 manager 清缓存重载（同步版，仅 reload_configs）。

    mcp_tool_manager 现由 WorkspaceContext 共享持有（非 None），MCP 工具类也引用同一实例，
    故此处 reload 对所有引用方生效。同步版本不清理已连接子进程；async 端点应优先
    调 _areload_workspace_mcp。
    """
    try:
        mcp_manager = getattr(workspace, "mcp_tool_manager", None)
        if mcp_manager is not None:
            mcp_manager.reload_configs()
    except Exception as e:
        logger.warning(f"Failed to reload MCP configs after CRUD: {e}")


async def _areload_workspace_mcp(workspace: UserWorkspace) -> None:
    """async 版 reload：先断开已连接 server 再重载，避免孤儿子进程。推荐 CRUD 端点使用。"""
    try:
        mcp_manager = getattr(workspace, "mcp_tool_manager", None)
        if mcp_manager is not None and hasattr(mcp_manager, "areload_configs"):
            await mcp_manager.areload_configs()
    except Exception as e:
        logger.warning(f"Failed to areload MCP configs after CRUD: {e}")


def mcp_config_to_api(config: Dict[str, Any]) -> MCPServerConfig:
    """将后端MCP配置转换为API格式"""
    return MCPServerConfig(name=config.get("name", ""), command=config.get("command", ""), args=config.get("args", []), cwd=config.get("cwd"), env=config.get("env", {}), transport=config.get("transport", "stdio"), url=config.get("url"), headers=config.get("headers", {}), always_allow=config.get("always_allow", config.get("alwaysAllow", [])), timeout=config.get("timeout", 300), disabled=config.get("disabled", False))


def api_config_to_mcp(config: MCPServerConfig | MCPServerCreate | MCPServerUpdate) -> Dict[str, Any]:
    """将API配置转换为后端MCP配置格式"""
    data = config.model_dump(exclude_unset=True)

    # 转换字段名
    if "always_allow" in data:
        data["alwaysAllow"] = data.pop("always_allow")

    return data


# --- API Endpoints ---


@router.get("", response_model=MCPServersResponse)
async def get_mcp_servers(workspace_id: str, request: Request):
    """获取所有MCP服务器配置

    Returns:
        MCPServersResponse: 包含所有MCP服务器配置的列表
    """
    workspace = await get_user_workspace(workspace_id, request)
    mode_settings = load_mode_settings(workspace)

    mcp_servers = mode_settings.get("mcpServers", {})

    servers = []
    for name, config in mcp_servers.items():
        server_config = mcp_config_to_api(config)
        server_config.name = name
        servers.append(server_config)

    return MCPServersResponse(success=True, servers=servers)


@router.post("", response_model=MCPServerOperationResponse, status_code=201)
async def create_mcp_server(workspace_id: str, req: Request, request: MCPServerCreate):
    """创建新的MCP服务器配置

    Args:
        workspace_id: 工作区ID
        request: MCP服务器配置

    Returns:
        MCPServerOperationResponse: 操作结果

    Raises:
        HTTPException: 服务器名称已存在时抛出400错误
    """
    workspace = await get_user_workspace(workspace_id, req)
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
    sync_runtime_mcp_file(workspace, mcp_servers)
    await _areload_workspace_mcp(workspace)

    logger.info(f"Created MCP server '{request.name}' in workspace {workspace_id}")

    server_config = mcp_config_to_api(server_data)
    server_config.name = request.name

    return MCPServerOperationResponse(success=True, message=f"MCP server '{request.name}' created successfully", server=server_config)


@router.put("/{server_name}", response_model=MCPServerOperationResponse)
async def update_mcp_server(workspace_id: str, req: Request, server_name: str, request: MCPServerUpdate):
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
    workspace = await get_user_workspace(workspace_id, req)
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
    sync_runtime_mcp_file(workspace, mcp_servers)
    await _areload_workspace_mcp(workspace)

    logger.info(f"Updated MCP server '{server_name}' in workspace {workspace_id}")

    server_config = mcp_config_to_api(existing_config)
    server_config.name = server_name

    return MCPServerOperationResponse(success=True, message=f"MCP server '{server_name}' updated successfully", server=server_config)


@router.delete("/{server_name}", response_model=MCPServerOperationResponse)
async def delete_mcp_server(workspace_id: str, request: Request, server_name: str):
    """删除MCP服务器配置

    Args:
        workspace_id: 工作区ID
        server_name: 服务器名称

    Returns:
        MCPServerOperationResponse: 操作结果

    Raises:
        HTTPException: 服务器不存在时抛出404错误
    """
    workspace = await get_user_workspace(workspace_id, request)
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
    sync_runtime_mcp_file(workspace, mcp_servers)
    await _areload_workspace_mcp(workspace)

    logger.info(f"Deleted MCP server '{server_name}' from workspace {workspace_id}")

    return MCPServerOperationResponse(success=True, message=f"MCP server '{server_name}' deleted successfully", server=None)


@router.post("/{server_name}/test", response_model=MCPServerTestResponse)
async def test_mcp_server(workspace_id: str, request: Request, server_name: str):
    """真·连接测试：spawn/连接 server，返回工具/资源数与延迟（替原 TODO 假桩）。

    用临时 MCPToolManager 加载该工作区 MCP 配置并 connect_server；成功读 tools/resources，
    失败返回 last_error；之后 disconnect 清理（临时 manager，用完即弃）。
    """
    import asyncio
    import time

    from dawei.tools.mcp_tool_manager import MCPToolManager

    workspace = await get_user_workspace(workspace_id, request)
    # 临时 manager 必须绑定当前用户：否则用户级配置与 light-app relay stub
    # （均按 user_id 索引）在测试里成为盲区（默认 default_user 看不到）。
    current_user = await get_authenticated_user_id(request)
    mgr = MCPToolManager(workspace_root=str(workspace.workspace_path), user_id=current_user)
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
        f"MCP test '{server_name}' in workspace {workspace_id}: ok={ok}, "
        f"tools={tools_count}, resources={resources_count}, latency={latency_ms}ms"
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
async def get_mcp_servers_status(workspace_id: str, request: Request):
    """主动探活：逐个连接 server 返回 status/tools/resources（显式调用，非被动 live）。

    注：API 用临时 UserWorkspace，与运行中 Agent 的 manager 不共享，故为"按需探活"，
    供前端「测试全部」按钮，不宜列表加载时自动调用（会 spawn 多进程）。
    """
    import asyncio

    from dawei.tools.mcp_tool_manager import MCPToolManager

    workspace = await get_user_workspace(workspace_id, request)
    # 同 /test：按当前用户索引用户级配置与 relay stub（Test All 的探活面与
    # 运行中 Agent 的 manager 保持一致，否则 default_user 盲区）。
    current_user = await get_authenticated_user_id(request)
    mgr = MCPToolManager(workspace_root=str(workspace.workspace_path), user_id=current_user)

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


# --- Effective (merged user-default + workspace-override) -----------------
# override-or-inherit 读取端点：ws 有同名则整体覆盖 user（server 级整替换），
# 供前端「工作区设置 MCP tab」展示三态（继承默认 / 覆盖 / 来源）。
# 整替换语义对齐运行时 _merge_configs（同名用 ws 整个配置），保证「所见即所运行」。


class EffectiveMCPServer(MCPServerConfig):
    """MCP server 带 source 归属，用于 override-or-inherit 展示。"""

    source: str = Field("user", description="user | workspace")
    user_overridden: bool = Field(False, description="workspace 是否覆盖了同名 user 配置")


class EffectiveMCPServersResponse(BaseModel):
    """override-or-inherit 合并结果。"""

    success: bool = True
    default: List[MCPServerConfig] = Field(default_factory=list, description="user 级默认")
    override: List[MCPServerConfig] = Field(default_factory=list, description="workspace 级覆盖")
    effective: List[EffectiveMCPServer] = Field(default_factory=list, description="合并后生效")


def _load_user_mcp_servers(user_id: str = "default_user") -> Dict[str, Dict[str, Any]]:
    """读取用户级 MCP 配置（configs/{user_id}/mcp.json，per-user）。"""
    safe_uid = "".join(c if c.isalnum() or c in "-_" else "_" for c in (user_id or "default_user"))
    user_file = get_dawei_home() / "configs" / safe_uid / "mcp.json"
    if not user_file.exists():
        return {}
    try:
        with user_file.open("r", encoding="utf-8") as f:
            return json.load(f).get("mcpServers", {}) or {}
    except Exception as e:
        logger.error(f"Failed to load user MCP config: {e}")
        return {}


def _to_effective(name: str, cfg: Dict[str, Any], source: str, overridden: bool = False) -> EffectiveMCPServer:
    base = mcp_config_to_api(cfg).model_dump()
    base["name"] = name
    return EffectiveMCPServer(**base, source=source, user_overridden=overridden)


@router.get("/effective", response_model=EffectiveMCPServersResponse)
async def get_effective_mcp_servers(workspace: UserWorkspace = Depends(get_user_workspace)):
    """server 级 override-or-inherit：ws 有同名则整体覆盖 user（对齐运行时整替换语义）。纯读取，不改存储。"""
    ws_mode = load_mode_settings(workspace)
    ws_servers: Dict[str, Dict[str, Any]] = ws_mode.get("mcpServers", {}) or {}
    user_servers = _load_user_mcp_servers(workspace.user_id)

    default = []
    for n, c in user_servers.items():
        sc = mcp_config_to_api(c)
        sc.name = n
        default.append(sc)

    override = []
    for n, c in ws_servers.items():
        sc = mcp_config_to_api(c)
        sc.name = n
        override.append(sc)

    effective: List[EffectiveMCPServer] = []
    seen: set[str] = set()
    for name, user_cfg in user_servers.items():
        seen.add(name)
        if name in ws_servers:
            # 整替换语义，对齐运行时 _merge_configs：ws 有同名 → 用 ws 整个配置（非字段级合并）
            effective.append(_to_effective(name, ws_servers[name], "workspace", overridden=True))
        else:
            effective.append(_to_effective(name, user_cfg, "user"))
    for name, ws_cfg in ws_servers.items():
        if name in seen:
            continue
        effective.append(_to_effective(name, ws_cfg, "workspace"))

    return EffectiveMCPServersResponse(
        success=True, default=default, override=override, effective=effective
    )
