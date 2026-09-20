"""Core Workspace API Routes

核心的Workspace CRUD操作
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Any
from urllib.parse import urlparse

import yaml
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel

# 导入服务依赖
from dawei.api.services import get_workspace_file_service
from dawei import get_dawei_home
from dawei.storage.storage import Storage
from dawei.storage.storage_provider import StorageProvider
from dawei.tools.skill_manager import SkillManager
from dawei.workspace import workspace_manager
from dawei.workspace.user_workspace import UserWorkspace

# 导入共享模型
from .models import FileContent, WorkspaceList

logger = logging.getLogger(__name__)

# 创建路由器
router = APIRouter(tags=["workspaces-core"])


# --- 依赖注入 ---


from dawei.api.workspaces._deps import get_user_workspace


class UpdateModeRequest(BaseModel):
    """更新模式请求"""

    slug: str
    name: str
    description: str
    roleDefinition: str
    whenToUse: str
    customInstructions: str | None = None


class UpdateModeRulesRequest(BaseModel):
    """更新模式规则请求（支持多个文件）"""

    rules: Dict[str, str]  # key 是完整文件名（含 .md 扩展名），value 是文件内容


class ModeResponse(BaseModel):
    """模式响应"""

    success: bool
    message: str
    mode: Dict[str, Any] | None = None


class ModeRulesResponse(BaseModel):
    """模式规则响应"""

    success: bool
    rules: Dict[str, str]  # key 是完整文件名（含 .md 扩展名），value 是文件内容
    directory: str | None = None  # 规则目录路径


@router.get("/{workspace_id}/files")
async def get_workspace_files_or_content(
    workspace_id: str,
    path: str = Query(".", description="The path to the file or directory"),
    recursive: bool = Query(False, description="Whether to list subdirectories recursively"),
    include_hidden: bool = Query(False, description="Whether to include hidden files"),
    max_depth: int = Query(3, description="Maximum recursion depth"),
    storage: Storage = Depends(get_workspace_file_service),
):
    """Gets the file list of a workspace or the content of a single file."""
    if not await storage.exists(path):
        raise HTTPException(
            status_code=404,
            detail=f"Path does not exist: {path}",
        )

    if await storage.is_directory(path):
        files = await storage.list_directory(
            path=path,
            recursive=recursive,
            include_hidden=include_hidden,
            max_depth=max_depth,
        )
        return {"success": True, "type": "directory", "files": files}
    # Check if file is binary by extension
    binary_extensions = {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".bmp",
        ".ico",
        ".svg",
        ".webp",
        ".pdf",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".ppt",
        ".pptx",
        ".zip",
        ".tar",
        ".gz",
        ".rar",
        ".7z",
        ".mp3",
        ".mp4",
        ".avi",
        ".mov",
        ".wav",
        ".ttf",
        ".otf",
        ".woff",
        ".woff2",
        ".eot",
    }

    file_ext = Path(path).suffix.lower()
    is_binary = file_ext in binary_extensions

    if is_binary:
        # Return binary file
        content = await storage.read_binary_file(path)

        # Determine MIME type
        mime_types = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".bmp": "image/bmp",
            ".ico": "image/x-icon",
            ".svg": "image/svg+xml",
            ".webp": "image/webp",
            ".pdf": "application/pdf",
            ".zip": "application/zip",
            ".tar": "application/x-tar",
            ".gz": "application/gzip",
        }
        content_type = mime_types.get(file_ext, "application/octet-stream")

        return Response(content=content, media_type=content_type)
    # Return text file
    try:
        content = await storage.read_file(path)
    except UnicodeDecodeError:
        # If text decoding fails, fall back to binary
        logger.warning(f"Failed to decode file {path} as text, trying binary mode")
        content = await storage.read_binary_file(path)
        return Response(content=content, media_type="application/octet-stream")

    return {"success": True, "type": "file", "path": path, "content": content}


@router.post("/{workspace_id}/files")
async def write_workspace_file(
    workspace_id: str,
    file_content: FileContent,
    storage: Storage = Depends(get_workspace_file_service),
):
    """Writes content to a specific file in the workspace."""
    await storage.write_file(file_content.path, file_content.content)
    return {
        "success": True,
        "message": f"File '{file_content.path}' saved successfully.",
    }


@router.get("/{workspace_id}/open-files")
async def get_workspace_open_files(workspace_id: str):
    """获取工作区当前打开的文件列表。

    Reads active session state to determine which files are open.
    Falls back to empty list if no active sessions or not yet implemented
    in session manager.
    """
    workspace_info = workspace_manager.get_workspace_by_id(workspace_id)
    if not workspace_info:
        raise HTTPException(status_code=404, detail=f"Workspace with ID {workspace_id} not found")

    workspace_path = workspace_info.get("path")
    if not workspace_path:
        raise HTTPException(status_code=404, detail="Workspace path not found")

    # Try to get open files from active sessions in workspace
    open_files: list[dict[str, str]] = []
    try:
        from dawei.websocket.ws_server import websocket_server

        if websocket_server is not None and websocket_server._is_initialized:
            sessions = await websocket_server.session_manager.get_all_sessions()
            for session in sessions:
                ctx = getattr(session, "context", None)
                if ctx and isinstance(ctx, dict):
                    for f in ctx.get("open_files", []):
                        if f not in open_files:
                            open_files.append(f)
    except Exception:
        pass  # Graceful fallback — no active sessions means no open files

    return {"success": True, "openFiles": open_files}


@router.get("/v2/workspaces", response_model=WorkspaceList)
async def get_workspace_list(request: Request):
    """Get all available workspaces with UUID mapping (多租户：按 owner_user_id + tenant_id 过滤)。

    向后兼容：无 auth token 时不传 user_id/tenant_id，返回所有 workspace。
    """
    user_id = None
    tenant_id = None
    try:
        from dawei.api.auth import get_authenticated_user_id, get_authenticated_tenant_id

        user_id = await get_authenticated_user_id(request)
        tenant_id = await get_authenticated_tenant_id(request)
    except Exception:
        pass
    workspaces = workspace_manager.get_all_workspaces(user_id, tenant_id)
    active_workspaces = [w for w in workspaces if w.get("is_active", True)]
    return {"workspaces": active_workspaces}


@router.get("/v2/workspaces/{workspace_id}")
async def get_workspace_by_id(workspace_id: str):
    """Get workspace information by UUID."""
    workspace = workspace_manager.get_workspace_by_id(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail=f"Workspace with ID {workspace_id} not found")
    return {"success": True, "workspace": workspace}


@router.get("/{workspace_id}/modes")
async def get_workspace_modes(
    workspace: UserWorkspace = Depends(get_user_workspace),
    reload: bool = Query(False, description="强制重新加载配置"),
):
    """获取指定工作空间的所有可用模式。

    返回的 mode 列表会按照以下规则排序：
    1. 内置 system modes (orchestrator, plan, do, check, act) 固定在最前面，按此顺序
    2. 其他 modes 按 slug 字母顺序排列

    每个模式包含 source 字段：
    - system: 内置系统模式（5个 PDCA 模式）
    - user: 用户级自定义模式
    - workspace: 工作区级自定义模式

    Args:
        reload: 是否强制重新加载配置（绕过缓存）

    Raises:
        HTTPException: If workspace initialization fails
        HTTPException: If mode retrieval fails

    """
    # 确保工作区已初始化
    if not workspace.is_initialized():
        await workspace.initialize()

    # 如果要求强制重新加载，清除缓存
    if reload:
        workspace.mode_manager.reload_configs()
        logger.info(f"Forced reload of mode configurations for workspace: {workspace.absolute_path}")

    logger.info(f"Getting modes for workspace: {workspace.absolute_path}")
    modes_dict = workspace.mode_manager.get_all_modes()

    # 动态获取内置模式的固定顺序
    from dawei.mode import get_builtin_modes, get_default_mode

    builtin_mode_order = get_builtin_modes()
    default_mode = get_default_mode()

    # 分离 system modes 和自定义 modes
    system_modes = []
    custom_modes = []

    for mode_slug, mode_info in modes_dict.items():
        # 获取配置来源信息（user 层已删除 — Phase 4/P9，仅 builtin/workspace）
        config_sources = workspace.mode_manager.get_config_sources(mode_slug)
        source = "system" if config_sources.get("builtin") else "workspace"

        mode_data = {
            "slug": getattr(mode_info, "slug", mode_slug),
            "name": getattr(mode_info, "name", mode_slug),
            "description": getattr(mode_info, "description", ""),
            "is_default": mode_slug == default_mode,
            "source": source,
            # 包含完整的模式配置信息（groups 已退役 — mode工具解耦 D3）
            "role_definition": getattr(mode_info, "role_definition", ""),
            "when_to_use": getattr(mode_info, "when_to_use", ""),
            "custom_instructions": getattr(mode_info, "custom_instructions", ""),
        }

        # 如果是内置 system mode（在 builtin_mode_order 中且 source 为 system），按固定顺序添加
        if source == "system" and mode_slug in builtin_mode_order:
            system_modes.append((builtin_mode_order.index(mode_slug), mode_data))
        else:
            # 自定义 modes（workspace）暂存，按 slug 字母顺序排序
            custom_modes.append((mode_slug, mode_data))

    # 排序 system modes（按内置顺序）和 custom modes（按 slug 字母顺序）
    system_modes.sort(key=lambda x: x[0])
    custom_modes.sort(key=lambda x: x[0])

    # 合并：system modes 在前，custom modes 在后
    mode_list = [mode[1] for mode in system_modes] + [mode[1] for mode in custom_modes]

    logger.info(
        f"Found {len(mode_list)} modes ({len(system_modes)} system, {len(custom_modes)} custom)",
    )
    return {"success": True, "modes": mode_list}


@router.delete("/{workspace_id}/modes/{mode_slug}")
async def delete_workspace_mode(
    workspace_id: str,
    mode_slug: str,
    workspace: UserWorkspace = Depends(get_user_workspace),
):
    """删除工作区的自定义模式

    删除指定工作区的自定义模式配置，包括：
    - 删除 rules-{mode_slug} 目录（如果存在）

    注意：不能删除内置系统模式（orchestrator, plan, do, check, act）

    Args:
        workspace_id: 工作区ID
        mode_slug: 要删除的模式 slug
        workspace: UserWorkspace 实例（通过依赖注入）

    Returns:
        {"success": bool, "message": str}

    Raises:
        HTTPException: 400 - 尝试删除内置模式
        HTTPException: 404 - 工作区不存在
        HTTPException: 500 - 服务器错误

    """
    # 确保工作区已初始化
    if not workspace.is_initialized():
        await workspace.initialize()

    logger.info(f"Deleting mode {mode_slug} from workspace {workspace_id}")

    # 尝试删除模式（默认为 workspace 级别）
    try:
        workspace.mode_manager.delete_mode(mode_slug, level="workspace")
    except ValueError as e:
        # 尝试删除内置模式或模式不存在
        logger.warning(f"Failed to delete mode {mode_slug}: {e}")
        raise HTTPException(status_code=400, detail=str(e))

    logger.info(f"Successfully deleted mode {mode_slug} from workspace {workspace_id}")
    return {"success": True, "message": f"Mode '{mode_slug}' deleted successfully"}


@router.get("/{workspace_id}/modes/{mode_slug}/rules", response_model=ModeRulesResponse)
async def get_mode_rules(
    workspace_id: str,
    mode_slug: str,
    workspace: UserWorkspace = Depends(get_user_workspace),
):
    """获取工作区模式的规则文件内容

    Args:
        workspace_id: 工作区ID
        mode_slug: 模式 slug
        workspace: UserWorkspace 实例（通过依赖注入）

    Returns:
        {"success": bool, "rules": str, "path": str | None}

    Raises:
        HTTPException: 404 - 工作区不存在
        HTTPException: 500 - 服务器错误

    """
    # 确保工作区已初始化
    if not workspace.is_initialized():
        await workspace.initialize()

    logger.info(f"Getting rules for mode {mode_slug} from workspace {workspace_id}")

    # 获取模式配置（包含所有规则文件）
    mode_info = workspace.mode_manager.get_mode_info(mode_slug)

    # 获取所有规则文件字典
    rules_dict = mode_info.rules if mode_info else {}

    # 获取规则目录路径
    rules_dir = workspace.mode_manager._find_rules_directory(mode_slug)

    # 将路径转换为相对路径（如果可能）
    relative_dir = None
    if rules_dir:
        workspace_path = Path(workspace.absolute_path)
        rules_abs_path = Path(rules_dir)
        # 尝试转换为相对于工作区的路径
        try:
            relative_dir = str(rules_abs_path.relative_to(workspace_path))
        except ValueError as e:
            # 规则目录不在工作区内，这是配置错误
            logger.exception(f"Rules directory {rules_abs_path} is not within workspace {workspace_path}")
            raise HTTPException(
                status_code=400,
                detail=f"Rules directory must be within workspace path: {e}",
            )

    logger.info(f"Successfully retrieved {len(rules_dict)} rules files for mode {mode_slug}")
    return ModeRulesResponse(success=True, rules=rules_dict, directory=relative_dir)


@router.put("/{workspace_id}/modes/{mode_slug}", response_model=ModeResponse)
async def update_mode(
    workspace_id: str,
    mode_slug: str,
    request_data: UpdateModeRequest,
    workspace: UserWorkspace = Depends(get_user_workspace),
):
    """更新工作区的自定义模式

    更新模式的基本配置信息，包括名称、描述、角色定义等。

    Args:
        workspace_id: 工作区ID
        mode_slug: 模式 slug
        request_data: 更新模式请求数据
        workspace: UserWorkspace 实例（通过依赖注入）

    Returns:
        {"success": bool, "message": str, "mode": dict}

    Raises:
        HTTPException: 400 - 尝试更新内置模式
        HTTPException: 404 - 工作区不存在
        HTTPException: 500 - 服务器错误

    """
    # 确保工作区已初始化
    if not workspace.is_initialized():
        await workspace.initialize()

    logger.info(f"Updating mode {mode_slug} in workspace {workspace_id}")

    # 将请求数据转换为字典（groups 已退役 — mode工具解耦 D3）
    mode_data = {
        "slug": request_data.slug,
        "name": request_data.name,
        "description": request_data.description,
        "roleDefinition": request_data.roleDefinition,
        "whenToUse": request_data.whenToUse,
    }

    if request_data.customInstructions:
        mode_data["customInstructions"] = request_data.customInstructions

    # 更新模式
    try:
        updated_mode = workspace.mode_manager.update_mode(mode_slug, mode_data, level="workspace")
    except ValueError as e:
        # 尝试更新内置模式或模式不存在
        logger.warning(f"Failed to update mode {mode_slug}: {e}")
        raise HTTPException(status_code=400, detail=str(e))

    # 转换模式对象为字典
    mode_dict = {
        "slug": updated_mode.slug,
        "name": updated_mode.name,
        "description": updated_mode.description,
        "roleDefinition": updated_mode.role_definition,
        "whenToUse": updated_mode.when_to_use,
        "customInstructions": updated_mode.custom_instructions,
    }

    logger.info(f"Successfully updated mode {mode_slug} in workspace {workspace_id}")
    return ModeResponse(
        success=True,
        message=f"Mode '{mode_slug}' updated successfully",
        mode=mode_dict,
    )


@router.put("/{workspace_id}/modes/{mode_slug}/rules", response_model=ModeRulesResponse)
async def update_mode_rules(
    workspace_id: str,
    mode_slug: str,
    request_data: UpdateModeRulesRequest,
    workspace: UserWorkspace = Depends(get_user_workspace),
):
    """更新工作区模式的规则文件内容

    更新或创建模式的 rules.md 文件。

    Args:
        workspace_id: 工作区ID
        mode_slug: 模式 slug
        request_data: 更新规则请求数据
        workspace: UserWorkspace 实例（通过依赖注入）

    Returns:
        {"success": bool, "rules": str}

    Raises:
        HTTPException: 400 - 尝试更新内置模式的规则
        HTTPException: 404 - 工作区不存在
        HTTPException: 500 - 服务器错误

    """
    # 确保工作区已初始化
    if not workspace.is_initialized():
        await workspace.initialize()

    logger.info(f"Updating rules for mode {mode_slug} in workspace {workspace_id}")

    # 更新模式规则（支持多个文件）
    try:
        for filename, content in request_data.rules.items():
            workspace.mode_manager.update_mode_rules(
                mode_slug=mode_slug,
                rules_content=content,
                rules_filename=filename,
                level="workspace",
            )
            logger.debug(f"Updated rules file {filename}.md for mode {mode_slug}")
    except ValueError as e:
        # 尝试更新内置模式的规则
        logger.warning(f"Failed to update rules for mode {mode_slug}: {e}")
        raise HTTPException(status_code=400, detail=str(e))

    logger.info(f"Successfully updated {len(request_data.rules)} rules file(s) for mode {mode_slug} in workspace {workspace_id}")

    # 返回更新后的所有规则
    mode_info = workspace.mode_manager.get_mode_info(mode_slug)
    rules_dict = mode_info.rules if mode_info else {}
    rules_dir = workspace.mode_manager._find_rules_directory(mode_slug)

    # 将绝对路径转换为相对路径
    relative_dir = None
    if rules_dir and workspace.absolute_path:
        try:
            relative_dir = str(Path(rules_dir).relative_to(Path(workspace.absolute_path)))
        except ValueError as e:
            # 规则目录不在工作区内，这是配置错误
            logger.exception(f"Rules directory {rules_dir} is not within workspace {workspace.absolute_path}")
            raise HTTPException(
                status_code=400,
                detail=f"Rules directory must be within workspace path: {e}",
            )

    return ModeRulesResponse(
        success=True,
        rules=rules_dict,
        directory=relative_dir,
    )


# --- 代理配置路由 ---


def _validate_proxy_url(proxy_url: str, field_name: str) -> None:
    """验证代理URL格式

    Args:
        proxy_url: 代理URL
        field_name: 字段名称（用于错误消息）

    Raises:
        HTTPException: 如果URL格式无效
    """
    if not proxy_url:
        return  # 空字符串是有效的（表示禁用代理）

    try:
        result = urlparse(proxy_url)
        # 检查必需的URL组件
        if not result.scheme or not result.netloc:
            raise ValueError("Missing scheme or network location")

        # 检查支持的协议
        valid_schemes = {"http", "https", "socks", "socks5"}
        if result.scheme not in valid_schemes:
            raise ValueError(f"Unsupported scheme. Supported schemes: {', '.join(valid_schemes)}")

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {field_name} URL format: {e}",
        )


@router.get("/{workspace_id}/proxy")
async def get_proxy_config(
    workspace_id: str,
    workspace: UserWorkspace = Depends(get_user_workspace),
):
    """获取工作区代理配置"""
    # 确保工作区已初始化
    if not workspace.is_initialized():
        await workspace.initialize()

    # 确保settings已加载
    if workspace.workspace_settings is None:
        await workspace._load_settings()

    # 返回代理配置
    return {
        "http_proxy": workspace.workspace_settings.http_proxy,
        "https_proxy": workspace.workspace_settings.https_proxy,
        "no_proxy": workspace.workspace_settings.no_proxy,
    }


@router.put("/{workspace_id}/proxy")
async def update_proxy_config(
    workspace_id: str,
    proxy_update: Dict[str, Any],
    workspace: UserWorkspace = Depends(get_user_workspace),
):
    """更新工作区代理配置"""
    # 确保工作区已初始化
    if not workspace.is_initialized():
        await workspace.initialize()

    # 确保settings已加载
    if workspace.workspace_settings is None:
        await workspace._load_settings()

    # 验证并更新代理配置
    updated_fields = set()
    if "http_proxy" in proxy_update:
        _validate_proxy_url(proxy_update["http_proxy"], "http_proxy")
        workspace.workspace_settings.http_proxy = proxy_update["http_proxy"]
        updated_fields.add("httpProxy")
    if "https_proxy" in proxy_update:
        _validate_proxy_url(proxy_update["https_proxy"], "https_proxy")
        workspace.workspace_settings.https_proxy = proxy_update["https_proxy"]
        updated_fields.add("httpsProxy")
    if "no_proxy" in proxy_update:
        # no_proxy 不需要URL验证（它是逗号分隔的域名列表）
        workspace.workspace_settings.no_proxy = proxy_update["no_proxy"]
        updated_fields.add("noProxy")

    # 增量保存配置（只保存 proxy 字段，不影响其他配置）
    await workspace._save_settings(only_fields=updated_fields)

    logger.info(f"Proxy config updated for workspace {workspace_id}")

    # 重新加载 LLM 配置以应用新的 proxy 设置
    if workspace.llm_manager:
        try:
            workspace.llm_manager.reload_configs()
            logger.info(f"LLM configs reloaded after proxy update for workspace {workspace_id}")
        except Exception as e:
            logger.warning(f"Failed to reload LLM configs after proxy update: {e}")

    # 返回更新后的代理配置
    return {
        "http_proxy": workspace.workspace_settings.http_proxy,
        "https_proxy": workspace.workspace_settings.https_proxy,
        "no_proxy": workspace.workspace_settings.no_proxy,
    }


# ==================== 统计 API ====================


@router.get("/{workspace_id}/stats")
async def get_workspace_stats(workspace_id: str):
    """获取工作区统计信息

    包括：
    - 文件统计（总数量、总大小、类型分布）
    - 对话统计（对话数量、消息数量）
    - 任务统计（任务数量）
    - 技能统计（工作区级技能数量）
    - Agent 统计（工作区级 agent 数量）
    - 最后活动时间
    """
    # 获取工作区信息
    workspace_info = workspace_manager.get_workspace_by_id(workspace_id)
    if not workspace_info:
        raise HTTPException(status_code=404, detail="Workspace not found")

    workspace_path = workspace_info.get("path")
    if not workspace_path:
        raise HTTPException(status_code=404, detail="Workspace path not found")

    workspace_storage = StorageProvider.get_workspace_storage(workspace_path)

    # 统计文件信息
    total_files = 0
    total_size = 0
    file_types = {}

    files = await workspace_storage.list_directory(path="", recursive=True, include_hidden=False)
    for item in files:
        if not item["is_directory"]:
            total_files += 1
            total_size += item.get("size", 0)
            ext = item["name"].split(".")[-1].lower() if "." in item["name"] else "no_ext"
            file_types[ext] = file_types.get(ext, 0) + 1

    # 统计对话信息
    conversations_count = 0
    messages_count = 0
    last_activity_at = workspace_info.get("created_at", "")

    conversations_path = ".dawei/conversations"
    if await workspace_storage.exists(conversations_path):
        conv_files = await workspace_storage.list_directory(path=conversations_path, recursive=False, include_hidden=False)
        for item in conv_files:
            if item["name"].endswith(".json") and not item["is_directory"]:
                conversations_count += 1
                conv_content = await workspace_storage.read_file(f"{conversations_path}/{item['name']}")
                conv_data = json.loads(conv_content)
                messages_count += len(conv_data.get("messages", []))

    # 获取最后修改时间
    workspace_info_path = ".dawei/workspace.json"
    if await workspace_storage.exists(workspace_info_path):
        stat = await workspace_storage.stat(workspace_info_path)
        if stat and "modified" in stat:
            last_activity_at = stat["modified"]

    # 统计任务信息
    tasks_count = 0
    tasks_path = ".dawei/tasks.json"
    if await workspace_storage.exists(tasks_path):
        tasks_content = await workspace_storage.read_file(tasks_path)
        tasks_data = json.loads(tasks_content)
        tasks_count = len(tasks_data.get("todos", []))

    # 统计工作区级技能数量 - 使用 SkillManager
    workspace_root = Path(workspace_path)
    skills_roots = [workspace_root]
    skill_manager = SkillManager(skills_roots=skills_roots)
    skill_manager.discover_skills(force=True)
    all_skills = skill_manager.get_all_skills()
    skills_count = len([s for s in all_skills if s.scope == "workspace"])

    # 统计工作区级 modes (agents) 数量
    agents_count = 0
    modes_file = Path(workspace_path) / ".dawei" / ".roomode"
    if modes_file.exists():
        with modes_file.open(encoding="utf-8") as f:
            modes_data = yaml.safe_load(f)
            if modes_data and isinstance(modes_data, dict):
                agents_count = len(modes_data.get("modes", []))

    return {
        "totalFiles": total_files,
        "totalSize": total_size,
        "fileTypes": file_types,
        "conversationsCount": conversations_count,
        "messagesCount": messages_count,
        "tasksCount": tasks_count,
        "skillsCount": skills_count,
        "agentsCount": agents_count,
        "lastActivityAt": last_activity_at,
    }


@router.get("/global-stats")
async def get_global_stats():
    """获取全局统计信息（用户级）

    包括：
    - 工作区总数
    - 技能总数（全局用户级别）
    - 已安装的 modes (agents) 总数
    """
    system_storage = StorageProvider.get_system_storage()

    # 1. 统计工作区总数
    content = await system_storage.read_file("workspaces.json")
    data = json.loads(content)
    workspaces_count = len(data.get("workspaces", []))

    # 2. 统计用户级技能总数 - 使用 SkillManager
    dawei_home = get_dawei_home()
    skills_roots = [Path(dawei_home)]
    skill_manager = SkillManager(skills_roots=skills_roots)
    skill_manager.discover_skills(force=True)
    all_skills = skill_manager.get_all_skills()
    skills_count = len([s for s in all_skills if s.scope == "user"])

    # 3. 统计用户级 modes (agents) 总数
    modes_count = 0
    modes_file = get_dawei_home() / ".roomode"
    if modes_file.exists():
        with modes_file.open(encoding="utf-8") as f:
            modes_data = yaml.safe_load(f)
            if modes_data and isinstance(modes_data, dict):
                modes_count = len(modes_data.get("modes", []))

    return {
        "workspacesCount": workspaces_count,
        "skillsCount": skills_count,
        "agentsCount": modes_count,
    }


# 框架 mode（PDCA 编排），不属于任何模块的专家，团队工作区内保留。
# 实体部分（orchestrator/pdca）源自 builtin modes.yaml（FRAMEWORK_SLUGS，SSOT）；
# plan/do/check/act 为 pdca_extension 的运行时相位值（未在任何 modes.yaml 定义的
# 幽灵 slug），Phase 4 收口时统一处理。P11 修复：不再独立硬编码实体 slug。
def _framework_mode_slugs() -> set[str]:
    from dawei.entity.mode import FRAMEWORK_SLUGS

    return set(FRAMEWORK_SLUGS) | {"plan", "do", "check", "act"}


FRAMEWORK_MODE_SLUGS = _framework_mode_slugs()

# 模块 → 团队注册表（一个模块可绑多个 team）。
# 【2026-09-16 §8 兜底移除】业务编队 SSOT = normos-market-resources（builtin
# 仅剩 framework×2），团队模式经 market 安装进入工作区（tier A 读
# .dawei/agents/）。此映射仅作模块身份标记：命中 → 模块工作区未装团队时
# 收敛为仅框架（不得回退全量泄漏其他模块）；values 保留 team 名供诊断与
# 安装提示。key 支持 name 前缀匹配（深度调研工作区
# name = "{slug}-{id[:8]}"，见 deep_research_framework.py）。
WORKSPACE_MODULE_TEAMS: dict[str, list[str]] = {
    "MarketingAgent 工作区": ["market-team"],
    "SocialAgent 工作区": ["social-team", "social-tools"],  # 多 team 模块
    "product-survey-": ["product-survey-team"],
    "industry-research-": ["industry-research-team"],
}

# ── mode 收紧策略（2026-09-18）──────────────────────────────────────
# 模块身份键（biz_module 或 name marker）→ 本模块可见的 agent 目录
# （.dawei/agents/<dir>）。模块工作区即使装了整个多 agent 团队（如
# team/gelu-research = 4 agents × 50 modes），或经 market 资源页往同一
# 工作区加装了其他模块团队，可见 modes 也收敛为本模块相关 agent 的并集，
# 而非全部已装 agents 的并集。未登记的模块键不受影响（走原 tier A 并集）。
WORKSPACE_MODULE_AGENTS: dict[str, list[str]] = {
    # 科研助手（team/gelu-research：综述/原创/解读为流水线 agent，整体可见）
    "research-review": ["review-team"],
    "research-original": ["paper-team"],
    "research-lens": ["lens-team"],
    # 科研助手·单专家工具（gelu-experts 一个 agent 装 7 个专家 mode，
    # 各工具页只开放自己的那一个，见 WORKSPACE_MODULE_MODES）
    "research-analysis": ["gelu-experts"],
    "research-writing": ["gelu-experts"],
    "research-grant": ["gelu-experts"],
    "research-clinical": ["gelu-experts"],
    "research-submission": ["gelu-experts"],
    "research-integrity": ["gelu-experts"],
    # 法律AI工具（team/legal-tools：单 agent 3 modes，按工具收紧）
    "legal-contract-draft": ["legal-tools"],
    "legal-doc-draft": ["legal-tools"],
    "legal-contract-review": ["legal-tools"],
    # 深度调研·insight 工具页（team/insight-tools：单 agent 4 modes）
    "deep-research-competitor": ["insight-tools"],
    "deep-research-reports": ["insight-tools"],
    # 模块伞工作区（无工具页 → 不固话 biz_module，身份靠 name marker 识别，
    # 见 _resolve_module_key）：同样收紧为本模块编队 agents。团队经 market
    # 资源页装进工作区后，同工作区误装的其他模块团队不外泄。
    # market-team → agents/market；social 模块 = social-team(agents/social)
    # + social-tools(agents/social-tools) 两个 agent 目录。
    "MarketingAgent 工作区": ["market"],
    "SocialAgent 工作区": ["social", "social-tools"],
}

# biz_module → mode slug 白名单（可选二级收紧：在模块 agents 的并集内
# 再取交集）。适用于「一个 agent 承载多个独立工具」的场景（gelu-experts
# 7 专家 / legal-tools 3 起草审查工具 / insight-tools 4 报告工具）。
WORKSPACE_MODULE_MODES: dict[str, list[str]] = {
    "research-analysis": ["gelu-data-analysis-expert"],
    "research-writing": ["gelu-writing-expert"],
    "research-grant": ["gelu-grant-expert"],
    "research-clinical": ["gelu-clinical-expert"],
    "research-submission": ["gelu-submission-expert"],
    "research-integrity": ["gelu-integrity-expert"],
    "legal-contract-draft": ["legal-contract-drafter"],
    "legal-doc-draft": ["legal-doc-drafter"],
    "legal-contract-review": ["legal-contract-auditor"],
    "deep-research-competitor": ["insight-competitor-analyst"],
    "deep-research-reports": ["insight-research-reports"],
}


def _module_agents_for(biz_module: str) -> list[str]:
    """模块身份键 → 收紧后的 agent 目录白名单（未登记返回空 = 不收紧）。"""
    return WORKSPACE_MODULE_AGENTS.get(biz_module or "", [])


def _resolve_module_key(biz_module: str, ws_name: str = "", ws_display: str = "") -> str:
    """模块身份键：biz_module 优先；无 biz_module 时回退 name/display marker。

    MarketingAgent/SocialAgent 等伞工作区没有工具页（创建时不固话
    biz_module），身份只能靠 name marker 识别 —— 命中 WORKSPACE_MODULE_TEAMS
    的 marker 后，同样以该 marker 作为键享受 WORKSPACE_MODULE_AGENTS 收紧。
    """
    if biz_module:
        return biz_module
    for marker in WORKSPACE_MODULE_TEAMS:
        if ws_name.startswith(marker) or ws_display.startswith(marker):
            return marker
    return ""


def _module_teams_for_workspace(ws_name: str) -> list[str]:
    """按 name marker（前缀匹配）解析模块绑定的团队列表（身份标记用）。"""
    for marker, teams in WORKSPACE_MODULE_TEAMS.items():
        if ws_name.startswith(marker):
            return teams
    return []


def _resolve_mode_scope(dawei_dir: Path, ws_name: str = "", ws_display: str = "", biz_module: str = "") -> set[str] | None:
    """4 层判定工作区专家可见范围（见 get_workspace_resources 内注释 A–D）。

    返回 None 表示不限定（全量，旧行为）；返回集合表示 mode slug 白名单
    （调用方需再并上 FRAMEWORK_MODE_SLUGS）。

    tier A 细化（mode 收紧策略 2026-09-18）：模块工作区（biz_module 固话，
    或 name/display marker 命中 —— MarketingAgent/SocialAgent 伞工作区，
    见 _resolve_module_key）且已登记 WORKSPACE_MODULE_AGENTS 时，并集收敛
    为本模块映射 agents 的 modes，而非全部已装 agents 的并集；可用
    WORKSPACE_MODULE_MODES 二级收紧到单个 mode（一个 agent 承载多个独立
    工具的场景）。映射的 agent 一个都没装 → 仅框架（不回退全量并集泄漏
    其他模块）。未登记的模块键不受影响（走原 tier A 并集）。
    """
    agent_modes = _load_agent_modes_map(dawei_dir)
    module_key = _resolve_module_key(biz_module, ws_name, ws_display)
    module_agents = _module_agents_for(module_key)
    if agent_modes:
        if module_agents:
            # A′) 模块工作区 → 仅本模块映射 agents 的 modes（非全部已装并集）
            installed = {a: slugs for a, slugs in agent_modes.items() if a in module_agents}
            if not installed:
                logger.warning(f"Module workspace {module_key} expects agents {module_agents} but none installed; scope=framework-only.")
                return set()
            scope = {s for slugs in installed.values() for s in slugs}
            subset = WORKSPACE_MODULE_MODES.get(module_key)
            if subset:
                scope &= set(subset)
            return scope
        # A) 装了团队 agents → 各 agent modes 并集
        return {s for slugs in agent_modes.values() for s in slugs}
    if (dawei_dir / "team.json").exists():
        # B) 有 team.json 但没装 agents → 仅框架（不得回退全量泄漏其他模块）
        return set()
    # C) name marker（模块工作区；§8 兜底移除后团队不再内置，业务模式经
    # market 安装进入 → tier A）→ 未安装时仅框架（不得回退全量泄漏其他模块）。
    # name 是稳定机器标识（"product-survey-<id8>"），display_name 可能是
    # 用户主题（如"product 页跳转验证"），两者都尝试，name 优先。
    teams = _module_teams_for_workspace(ws_name) or _module_teams_for_workspace(ws_display)
    if teams:
        logger.info(f"Module workspace (teams={teams}) has no market-installed agents; scope=framework-only. Install the team from market to enable its modes.")
        return set()
    # D) 无任何模块标识（临时聊天等）→ 全量
    return None


def _load_agent_modes_map(dawei_dir: Path) -> dict[str, list[str]]:
    """从 .dawei/agents/*/modes.yaml 还原 agent → mode slug 映射。

    resource_installer._merge_agent_modes 把各 agent 的 customModes 拍平进
    mode_settings.json（统一 source="workspace"），agent 归属只保留在
    agents/<slug>/modes.yaml。前端专家下拉按当前任务的入口专家定位所属
    agent，只展示该 agent 的 modes（否则 63 mode 工作区下拉全量暴露）。

    （mode-工具解耦 D2：aliases 并入已删除 —— 前端一律使用 canonical slug，
    历史 alias expertId 经 scripts/migrate_mode_decoupling.py 归一。）
    """
    agent_modes: dict[str, list[str]] = {}
    agents_root = dawei_dir / "agents"
    if not agents_root.is_dir():
        return agent_modes
    for agent_dir in sorted(agents_root.iterdir()):
        modes_file = agent_dir / "modes.yaml"
        if not (agent_dir.is_dir() and modes_file.exists()):
            continue
        try:
            data = yaml.safe_load(modes_file.read_text(encoding="utf-8")) or {}
            slugs: list[str] = []
            for m in data.get("customModes", []):
                if not (isinstance(m, dict) and m.get("slug")):
                    continue
                slug = str(m["slug"])
                if slug not in slugs:
                    slugs.append(slug)
            if slugs:
                agent_modes[agent_dir.name] = slugs
        except Exception as e:
            logger.warning(f"Failed to read agent modes {modes_file}: {e}")
    return agent_modes


@router.get("/{workspace_id}/resources")
async def get_workspace_resources(workspace_id: str):
    """获取工作区已安装的市场资源（skills, modes, MCP, team）。

    读取 .dawei/ 目录下的配置文件，返回工作区内安装的所有资源摘要。
    """
    workspace_info = workspace_manager.get_workspace_by_id(workspace_id)
    if not workspace_info:
        raise HTTPException(status_code=404, detail="Workspace not found")

    workspace_path = Path(workspace_info.get("path", ""))
    if not workspace_path.exists():
        raise HTTPException(status_code=404, detail="Workspace path not found")

    dawei_dir = workspace_path / ".dawei"

    # ── Skills ──
    skills: list[dict[str, str]] = []
    skills_dir = dawei_dir / "skills"
    if skills_dir.is_dir():
        for item in sorted(skills_dir.iterdir()):
            if item.is_dir() and not item.name.startswith("."):
                # Try to read skill name from SKILL.md or markdown file
                skill_name = item.name
                for md_file in item.glob("*.md"):
                    try:
                        content = md_file.read_text(encoding="utf-8")[:500]
                        for line in content.split("\n"):
                            if line.startswith("# "):
                                skill_name = line.lstrip("# ").strip()
                                break
                        # Also check frontmatter for name
                        if "name:" in content[:200]:
                            for line in content.split("\n")[:10]:
                                if line.startswith("name:"):
                                    skill_name = line.split("name:", 1)[1].strip().strip('"').strip("'")
                                    break
                    except Exception:
                        pass
                    break
                skills.append({"slug": item.name, "name": skill_name})

    # ── Modes (agents) ── 经 ModeRegistry 读取（Phase 4c：mode_settings.json 已降级为
    # 派生缓存不再作为事实源；ad-hoc ModeManager 同时禁用 — P5/P6）
    modes: list[dict[str, str]] = []
    try:
        from dawei.mode import get_builtin_modes
        from dawei.mode.registry import get_registry

        builtin_slugs = get_builtin_modes()
        ws_path = workspace_info.get("path", "")

        if ws_path:
            registry = get_registry(ws_path)
            for mode in registry.all():
                sources = registry.config_sources(mode.slug)
                source = "system" if sources.get("builtin") else "workspace"
                modes.append(
                    {
                        "slug": mode.slug,
                        "name": mode.name or mode.slug,
                        "description": mode.description,
                        "source": source,
                    }
                )

        # Sort: builtin first (fixed order), then custom alphabetically
        system_items = [(builtin_slugs.index(m["slug"]), m) for m in modes if m["slug"] in builtin_slugs]
        custom_items = [(m["slug"], m) for m in modes if m["slug"] not in builtin_slugs]
        system_items.sort(key=lambda x: x[0])
        custom_items.sort(key=lambda x: x[0])
        modes = [item[1] for item in system_items] + [item[1] for item in custom_items]
    except Exception as e:
        logger.warning(f"Failed to load modes: {e}")

    # ── Team scoping ── 工作区专家列表不可跨模块（4 层判定见 _resolve_mode_scope：
    #  A) agents 已装 → 并集（带 biz_module 时收敛为本模块映射 agents，见
    #  WORKSPACE_MODULE_AGENTS/MODES）；B) 仅 team.json → 仅框架；C) name
    #  marker → 模块已识别但团队未装 → 仅框架；D) 无标识 → 全量）。
    biz_module = workspace_info.get("biz_module") or ""
    if not biz_module:
        # 兜底：索引项早于 biz_module 持久化的存量工作区，读 workspace.json
        ws_config_file = dawei_dir / "workspace.json"
        if ws_config_file.exists():
            try:
                biz_module = json.loads(ws_config_file.read_text(encoding="utf-8")).get("biz_module") or ""
            except Exception as e:
                logger.warning(f"Failed to read biz_module from {ws_config_file}: {e}")
    scope = _resolve_mode_scope(
        dawei_dir,
        workspace_info.get("name") or "",
        workspace_info.get("display_name") or "",
        biz_module=biz_module,
    )
    module_key = _resolve_module_key(
        biz_module,
        workspace_info.get("name") or "",
        workspace_info.get("display_name") or "",
    )
    module_agents = _module_agents_for(module_key)
    # （mode-工具解耦 D2：include_aliases 已删除，agent_modes 纯 canonical slug）
    agent_modes = _load_agent_modes_map(dawei_dir)
    if module_agents:
        # 模块工作区：agent_modes 也收敛为本模块映射的 agents
        agent_modes = {a: slugs for a, slugs in agent_modes.items() if a in module_agents}
    if scope is not None:
        allowed = FRAMEWORK_MODE_SLUGS | scope
        modes = [m for m in modes if m["slug"] in allowed]

    # ── MCP Servers ── read mode_settings.json mcpServers or configs/mcp.json
    mcp_servers: list[dict[str, str]] = []
    mcp_config_file = dawei_dir / "configs" / "mcp.json"
    if not mcp_config_file.exists():
        mcp_config_file = dawei_dir / "mode_settings.json"
    if mcp_config_file.exists():
        try:
            mcp_data = json.loads(mcp_config_file.read_text(encoding="utf-8"))
            for server_name, server_conf in mcp_data.get("mcpServers", {}).items():
                if isinstance(server_conf, dict):
                    mcp_servers.append(
                        {
                            "name": server_name,
                            "command": server_conf.get("command", ""),
                            "url": server_conf.get("url", ""),
                        }
                    )
        except Exception as e:
            logger.warning(f"Failed to read MCP config: {e}")

    # ── Team ── read team.json
    team: dict | None = None
    team_file = dawei_dir / "team.json"
    if team_file.exists():
        try:
            team = json.loads(team_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    return {
        "success": True,
        "skills": skills,
        "modes": modes,
        "mcp_servers": mcp_servers,
        "team": team,
        "agent_modes": agent_modes,
    }


# ── Task Context API ──────────────────────────────────────────────────


class TaskContextUpdate(BaseModel):
    """Request body for updating task context metadata."""

    summary: str | None = None
    key_decisions: list[str] | None = None
    files: list[dict[str, str]] | None = None
    variables: dict[str, str] | None = None


class FileAssociation(BaseModel):
    """Request body for adding a file association to task context."""

    path: str
    type: str = "attachment"  # attachment | reference | generated
    description: str = ""


@router.get("/{workspace_id}/task-context/{conversation_id}")
async def get_task_context(workspace_id: str, conversation_id: str):
    """Aggregate task context: conversation metadata + task_graph summary + workspace resources."""
    workspace_info = workspace_manager.get_workspace_by_id(workspace_id)
    if not workspace_info:
        raise HTTPException(status_code=404, detail="Workspace not found")

    workspace_dir = workspace_info.get("path")
    if not workspace_dir:
        raise HTTPException(status_code=400, detail="Workspace path not found")

    dawei_dir = Path(workspace_dir) / ".dawei"
    conversations_dir = dawei_dir / "conversations"

    # 1. Load conversation metadata
    conv_file = conversations_dir / f"{conversation_id}.json"
    conv_meta: Dict[str, Any] = {}
    if conv_file.exists():
        try:
            conv_data = json.loads(conv_file.read_text(encoding="utf-8"))
            ctx = conv_data.get("metadata", {}).get("context", {})
            conv_meta = {
                "id": conversation_id,
                "title": conv_data.get("title", ""),
                "status": conv_data.get("metadata", {}).get("status", "active"),
                "mode": conv_data.get("metadata", {}).get("mode", "team"),
                "model": conv_data.get("metadata", {}).get("model", ""),
                "summary": ctx.get("summary", ""),
                "key_decisions": ctx.get("key_decisions", []),
                "files": ctx.get("files", []),
                "variables": ctx.get("variables", {}),
            }
        except Exception as e:
            logger.warning(f"Failed to read conversation {conversation_id}: {e}")
    else:
        conv_meta = {"id": conversation_id, "title": "", "summary": "", "key_decisions": [], "files": [], "variables": {}}

    # 2. Scan task_graphs for associated graph (best-effort match by conversation_id in nodes)
    task_graphs_dir = dawei_dir / "task_graphs"
    task_graph_ref = None
    if task_graphs_dir.is_dir():
        for gf in task_graphs_dir.glob("*.json"):
            try:
                gd = json.loads(gf.read_text(encoding="utf-8"))
                nodes = gd.get("nodes", {})
                if not nodes:
                    continue
                # Check if any node context references this conversation
                matched = False
                for nid, nd in nodes.items():
                    ctx_ref = nd.get("data", {}).get("context", {})
                    session_id = ctx_ref.get("session_id", "")
                    if session_id == conversation_id:
                        matched = True
                        break
                if not matched:
                    continue

                total = len(nodes)
                completed = sum(1 for n in nodes.values() if n.get("data", {}).get("status") == "completed")
                node_list = []
                for nid, nd in nodes.items():
                    node_list.append(
                        {
                            "id": nid,
                            "name": nd.get("data", {}).get("description", "")[:60] if isinstance(nd.get("data", {}).get("description"), str) else nid,
                            "status": nd.get("data", {}).get("status", "pending"),
                        }
                    )
                task_graph_ref = {
                    "graph_id": gd.get("task_graph_id", gf.stem),
                    "total_nodes": total,
                    "completed_nodes": completed,
                    "status": "completed" if completed == total else "running" if completed > 0 else "idle",
                    "nodes": node_list,
                }
                break
            except Exception:
                continue

    # 3. Get workspace resources (reuse the resources logic)
    resources = await _get_workspace_resources(dawei_dir)

    return {
        "success": True,
        "task": conv_meta,
        "task_graph": task_graph_ref,
        "resources": resources,
    }


@router.patch("/{workspace_id}/task-context/{conversation_id}")
async def update_task_context(workspace_id: str, conversation_id: str, body: TaskContextUpdate):
    """Update task context fields in conversation metadata."""
    workspace_info = workspace_manager.get_workspace_by_id(workspace_id)
    if not workspace_info:
        raise HTTPException(status_code=404, detail="Workspace not found")

    workspace_dir = workspace_info.get("path")
    if not workspace_dir:
        raise HTTPException(status_code=400, detail="Workspace path not found")

    conv_file = Path(workspace_dir) / ".dawei" / "conversations" / f"{conversation_id}.json"

    # Load existing or create new
    if conv_file.exists():
        try:
            conv_data = json.loads(conv_file.read_text(encoding="utf-8"))
        except Exception:
            conv_data = {"id": conversation_id, "title": "", "messages": [], "metadata": {}}
    else:
        conv_data = {"id": conversation_id, "title": "新任务", "messages": [], "metadata": {}}

    # Ensure metadata.context exists
    if "metadata" not in conv_data:
        conv_data["metadata"] = {}
    if "context" not in conv_data["metadata"]:
        conv_data["metadata"]["context"] = {}

    ctx = conv_data["metadata"]["context"]

    # Update fields
    if body.summary is not None:
        ctx["summary"] = body.summary
    if body.key_decisions is not None:
        ctx["key_decisions"] = body.key_decisions
    if body.files is not None:
        ctx["files"] = body.files
    if body.variables is not None:
        ctx["variables"] = body.variables

    # Save
    conv_file.parent.mkdir(parents=True, exist_ok=True)
    conv_file.write_text(json.dumps(conv_data, indent=2, ensure_ascii=False), encoding="utf-8")

    return {
        "success": True,
        "metadata": conv_data["metadata"],
    }


@router.post("/{workspace_id}/task-context/{conversation_id}/summarize")
async def summarize_task_context(workspace_id: str, conversation_id: str):
    """Generate summary and key decisions from conversation history using LLM."""
    workspace_info = workspace_manager.get_workspace_by_id(workspace_id)
    if not workspace_info:
        raise HTTPException(status_code=404, detail="Workspace not found")

    workspace_dir = workspace_info.get("path")
    if not workspace_dir:
        raise HTTPException(status_code=400, detail="Workspace path not found")

    conv_file = Path(workspace_dir) / ".dawei" / "conversations" / f"{conversation_id}.json"
    if not conv_file.exists():
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Load conversation
    try:
        conv_data = json.loads(conv_file.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read conversation: {e}")

    messages = conv_data.get("messages", [])
    if not messages:
        return {"success": True, "summary": "", "key_decisions": []}

    # Build conversation transcript for LLM (limit to last 30 messages for token budget)
    recent_messages = messages[-30:]
    transcript_lines = []
    for msg in recent_messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        if isinstance(content, str) and content.strip():
            # Truncate very long messages
            display = content[:500] + "..." if len(content) > 500 else content
            transcript_lines.append(f"[{role}]: {display}")
    transcript = "\n".join(transcript_lines)

    if not transcript.strip():
        return {"success": True, "summary": "", "key_decisions": []}

    # Call LLM to generate summary
    from dawei.llm_api.llm_provider import LLMProvider
    from dawei.entity.lm_messages import UserMessage, SystemMessage

    try:
        llm_provider = LLMProvider(workspace_root=workspace_dir)
    except Exception:
        # Fallback to global dawei home
        llm_provider = LLMProvider(workspace_root=str(get_dawei_home()))

    system_prompt = """你是一个对话摘要助手。请根据以下对话历史，生成：
1. 一段简洁的对话摘要（2-3句话，描述用户的核心需求和讨论进展）
2. 关键决策列表（列表形式，每项一个决策点）

请严格按以下 JSON 格式返回，不要包含其他内容：
{"summary": "摘要内容", "key_decisions": ["决策1", "决策2"]}"""

    user_prompt = f"请总结以下对话：\n\n{transcript}"

    try:
        result = await llm_provider.complete(
            messages=[SystemMessage(content=system_prompt), UserMessage(content=user_prompt)],
            temperature=0.3,
            max_tokens=500,
        )
        llm_text = result.get("content", "") or ""
    except Exception as e:
        logger.warning(f"LLM summarize failed for {conversation_id}: {e}")
        raise HTTPException(status_code=502, detail=f"LLM summarization failed: {e}")

    # Parse LLM response
    summary = ""
    key_decisions: list[str] = []
    try:
        # Try to extract JSON from response (handle markdown code blocks)
        import re

        json_match = re.search(r"\{[^{}]+\}", llm_text, re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group())
            summary = parsed.get("summary", "")
            key_decisions = parsed.get("key_decisions", [])
        else:
            summary = llm_text.strip()
    except json.JSONDecodeError:
        summary = llm_text.strip()

    # Save back to conversation metadata.context
    if "metadata" not in conv_data:
        conv_data["metadata"] = {}
    if "context" not in conv_data["metadata"]:
        conv_data["metadata"]["context"] = {}

    conv_data["metadata"]["context"]["summary"] = summary
    conv_data["metadata"]["context"]["key_decisions"] = key_decisions

    try:
        conv_file.write_text(json.dumps(conv_data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        logger.warning(f"Failed to save summary for {conversation_id}: {e}")

    return {
        "success": True,
        "summary": summary,
        "key_decisions": key_decisions,
    }


@router.post("/{workspace_id}/task-context/{conversation_id}/files")
async def add_task_context_file(workspace_id: str, conversation_id: str, body: FileAssociation):
    """Add a file association to task context."""
    workspace_info = workspace_manager.get_workspace_by_id(workspace_id)
    if not workspace_info:
        raise HTTPException(status_code=404, detail="Workspace not found")

    workspace_dir = workspace_info.get("path")
    if not workspace_dir:
        raise HTTPException(status_code=400, detail="Workspace path not found")

    conv_file = Path(workspace_dir) / ".dawei" / "conversations" / f"{conversation_id}.json"

    # Load existing or create new
    if conv_file.exists():
        try:
            conv_data = json.loads(conv_file.read_text(encoding="utf-8"))
        except Exception:
            conv_data = {"id": conversation_id, "title": "", "messages": [], "metadata": {}}
    else:
        conv_data = {"id": conversation_id, "title": "新任务", "messages": [], "metadata": {}}

    # Ensure metadata.context exists
    if "metadata" not in conv_data:
        conv_data["metadata"] = {}
    if "context" not in conv_data["metadata"]:
        conv_data["metadata"]["context"] = {}
    if "files" not in conv_data["metadata"]["context"]:
        conv_data["metadata"]["context"]["files"] = []

    files_list = conv_data["metadata"]["context"]["files"]

    # Check for duplicate path
    for existing in files_list:
        if existing.get("path") == body.path:
            raise HTTPException(status_code=409, detail="File already associated with this task")

    # Add new file entry
    from datetime import datetime, timezone

    file_entry = {
        "path": body.path,
        "type": body.type,
        "description": body.description,
        "added_at": datetime.now(timezone.utc).isoformat(),
    }
    files_list.append(file_entry)

    # Save
    conv_file.parent.mkdir(parents=True, exist_ok=True)
    conv_file.write_text(json.dumps(conv_data, indent=2, ensure_ascii=False), encoding="utf-8")

    return {"success": True, "file": file_entry, "total_files": len(files_list)}


@router.delete("/{workspace_id}/task-context/{conversation_id}/files")
async def remove_task_context_file(workspace_id: str, conversation_id: str, path: str = Query(..., description="File path to remove")):
    """Remove a file association from task context."""
    workspace_info = workspace_manager.get_workspace_by_id(workspace_id)
    if not workspace_info:
        raise HTTPException(status_code=404, detail="Workspace not found")

    workspace_dir = workspace_info.get("path")
    if not workspace_dir:
        raise HTTPException(status_code=400, detail="Workspace path not found")

    conv_file = Path(workspace_dir) / ".dawei" / "conversations" / f"{conversation_id}.json"
    if not conv_file.exists():
        raise HTTPException(status_code=404, detail="Conversation not found")

    try:
        conv_data = json.loads(conv_file.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read conversation: {e}")

    files_list = conv_data.get("metadata", {}).get("context", {}).get("files", [])
    original_len = len(files_list)
    conv_data["metadata"]["context"]["files"] = [f for f in files_list if f.get("path") != path]

    if len(conv_data["metadata"]["context"]["files"]) == original_len:
        raise HTTPException(status_code=404, detail="File not found in task context")

    conv_file.write_text(json.dumps(conv_data, indent=2, ensure_ascii=False), encoding="utf-8")

    return {"success": True, "removed": path, "total_files": len(conv_data["metadata"]["context"]["files"])}


async def _get_workspace_resources(dawei_dir: Path) -> Dict[str, Any]:
    """Extract workspace resources (skills, modes, MCP, team) — shared logic."""
    skills: list[dict[str, str]] = []
    skills_dir = dawei_dir / "skills"
    if skills_dir.is_dir():
        for item in sorted(skills_dir.iterdir()):
            if item.is_dir() and not item.name.startswith("."):
                skill_name = item.name
                for md_file in item.glob("*.md"):
                    try:
                        content = md_file.read_text(encoding="utf-8")[:500]
                        for line in content.split("\n"):
                            if line.startswith("# "):
                                skill_name = line.lstrip("# ").strip()
                                break
                    except Exception:
                        pass
                    break
                skills.append({"slug": item.name, "name": skill_name})

    modes: list[dict[str, str]] = []
    try:
        from dawei.mode import get_builtin_modes
        from dawei.mode.registry import get_registry

        builtin_slugs = get_builtin_modes()
        ws_path = str(dawei_dir.parent)  # dawei_dir is .dawei/, parent is workspace root

        # 经 ModeRegistry 读取（Phase 4c：mode_settings.json 已降级为派生缓存，
        # 不再作为事实源；ad-hoc ModeManager 同时禁用 — P5/P6）
        registry = get_registry(ws_path)
        for mode in registry.all():
            sources = registry.config_sources(mode.slug)
            source = "system" if sources.get("builtin") else "workspace"
            modes.append(
                {
                    "slug": mode.slug,
                    "name": mode.name or mode.slug,
                    "description": mode.description,
                    "source": source,
                }
            )

        # Sort: builtin first (fixed order), then custom alphabetically
        system_items = [(builtin_slugs.index(m["slug"]), m) for m in modes if m["slug"] in builtin_slugs]
        custom_items = [(m["slug"], m) for m in modes if m["slug"] not in builtin_slugs]
        system_items.sort(key=lambda x: x[0])
        custom_items.sort(key=lambda x: x[0])
        modes = [item[1] for item in system_items] + [item[1] for item in custom_items]
    except Exception:
        pass

    mcp_servers: list[dict[str, str]] = []
    mcp_config_file = dawei_dir / "configs" / "mcp.json"
    if mcp_config_file.exists():
        try:
            mcp_data = json.loads(mcp_config_file.read_text(encoding="utf-8"))
            for server_name, server_conf in mcp_data.get("mcpServers", {}).items():
                if isinstance(server_conf, dict):
                    mcp_servers.append(
                        {
                            "name": server_name,
                            "command": server_conf.get("command", ""),
                            "url": server_conf.get("url", ""),
                        }
                    )
        except Exception:
            pass

    team: dict | None = None
    team_file = dawei_dir / "team.json"
    if team_file.exists():
        try:
            team = json.loads(team_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    return {
        "skills": skills,
        "modes": modes,
        "mcp_servers": mcp_servers,
        "team": team,
    }
