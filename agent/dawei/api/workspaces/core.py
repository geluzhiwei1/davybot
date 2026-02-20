"""Core Workspace API Routes

核心的Workspace CRUD操作
"""

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel

# 导入服务依赖
from dawei.api.services import get_workspace_file_service
from dawei.storage.storage import Storage
from dawei.workspace import workspace_manager
from dawei.workspace.user_workspace import UserWorkspace

# 导入共享模型
from .models import FileContent, WorkspaceList

logger = logging.getLogger(__name__)

# 创建路由器
router = APIRouter(tags=["workspaces-core"])


# --- 依赖注入 ---


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


# --- Pydantic 模型 ---


class UpdateModeRequest(BaseModel):
    """更新模式请求"""

    slug: str
    name: str
    description: str
    roleDefinition: str
    whenToUse: str
    groups: list[str] | None = None
    customInstructions: str | None = None


class UpdateModeRulesRequest(BaseModel):
    """更新模式规则请求（支持多个文件）"""

    rules: dict[str, str]  # key 是完整文件名（含 .md 扩展名），value 是文件内容


class ModeResponse(BaseModel):
    """模式响应"""

    success: bool
    message: str
    mode: dict[str, Any] | None = None


class ModeRulesResponse(BaseModel):
    """模式规则响应"""

    success: bool
    rules: dict[str, str]  # key 是完整文件名（含 .md 扩展名），value 是文件内容
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
        raise FileNotFoundError(f"Path does not exist: {path}")

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
        try:
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
        except (OSError, PermissionError) as e:
            # Filesystem error - fast fail
            logger.error(f"Filesystem error reading binary file {path}: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to read file: {e!s}")
        except Exception as e:
            # Unexpected error - fast fail
            logger.critical(f"Unexpected error reading binary file {path}: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Internal server error")
    else:
        # Return text file
        try:
            content = await storage.read_file(path)
            return {"success": True, "type": "file", "path": path, "content": content}
        except UnicodeDecodeError:
            # If text decoding fails, fall back to binary
            logger.warning(f"Failed to decode file {path} as text, trying binary mode")
            try:
                content = await storage.read_binary_file(path)
                return Response(content=content, media_type="application/octet-stream")
            except (OSError, PermissionError) as e:
                # Filesystem error - fast fail
                logger.error(
                    f"Filesystem error reading file {path} in binary mode: {e}",
                    exc_info=True,
                )
                raise HTTPException(status_code=500, detail=f"Failed to read file: {e!s}")
            except Exception as e:
                # Unexpected error - fast fail
                logger.critical(
                    f"Unexpected error reading file {path} in binary mode: {e}",
                    exc_info=True,
                )
                raise HTTPException(status_code=500, detail="Internal server error")
        except (OSError, PermissionError) as e:
            # Filesystem error - fast fail
            logger.error(f"Filesystem error reading file {path}: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to read file: {e!s}")
        except Exception as e:
            # Unexpected error - fast fail
            logger.critical(f"Unexpected error reading file {path}: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Internal server error")


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
    """获取工作区当前打开的文件列表（临时实现，后续可以从会话状态中获取）"""
    # 临时实现：返回空列表，后续可以从会话状态或配置中获取
    # 这里可以扩展为从用户的会话状态中获取当前打开的文件
    return {"success": True, "openFiles": [], "message": "打开的文件列表功能待实现"}


@router.get("/v2/workspaces", response_model=WorkspaceList)
async def get_workspace_list():
    """Get all available workspaces with UUID mapping."""
    workspaces = workspace_manager.get_all_workspaces()
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
    try:
        # 确保工作区已初始化
        if not workspace.is_initialized():
            await workspace.initialize()

        # 如果要求强制重新加载，清除缓存
        if reload:
            workspace.mode_manager.reload_configs()
            logger.info(f"Forced reload of mode configurations for workspace: {workspace.absolute_path}")

        logger.info(f"Getting modes for workspace: {workspace.absolute_path}")
        modes_dict = workspace.mode_manager.get_all_modes()

        # 定义内置 system modes 的固定顺序
        builtin_mode_order = ["orchestrator", "plan", "do", "check", "act"]

        # 分离 system modes 和自定义 modes
        system_modes = []
        custom_modes = []

        for mode_slug, mode_info in modes_dict.items():
            # 获取配置来源信息
            config_sources = workspace.mode_manager.get_config_sources(mode_slug)
            source = "system" if config_sources.get("builtin") else ("workspace" if config_sources.get("workspace") else "user")

            mode_data = {
                "slug": getattr(mode_info, "slug", mode_slug),
                "name": getattr(mode_info, "name", mode_slug),
                "description": getattr(mode_info, "description", ""),
                "is_default": mode_slug == "orchestrator",
                "source": source,
                # 包含完整的模式配置信息
                "role_definition": getattr(mode_info, "role_definition", ""),
                "when_to_use": getattr(mode_info, "when_to_use", ""),
                "groups": getattr(mode_info, "groups", []),
                "custom_instructions": getattr(mode_info, "custom_instructions", ""),
            }

            # 如果是内置 system mode（在 builtin_mode_order 中且 source 为 system），按固定顺序添加
            if source == "system" and mode_slug in builtin_mode_order:
                system_modes.append((builtin_mode_order.index(mode_slug), mode_data))
            else:
                # 自定义 modes（user/workspace）暂存，按 slug 字母顺序排序
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

    except (OSError, PermissionError) as e:
        # Filesystem error during workspace initialization
        logger.error(f"Failed to initialize workspace for modes: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to access workspace: {e!s}")
    except (AttributeError, KeyError) as e:
        # Mode manager error - fast fail
        logger.error(f"Failed to get workspace modes: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get modes: {e!s}")
    except Exception as e:
        # Unexpected error - fast fail
        logger.critical(f"Unexpected error getting workspace modes: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/{workspace_id}/modes/{mode_slug}")
async def delete_workspace_mode(
    workspace_id: str,
    mode_slug: str,
    workspace: UserWorkspace = Depends(get_user_workspace),
):
    """删除工作区的自定义模式

    删除指定工作区的自定义模式配置，包括：
    - 删除 rules-{mode_slug} 目录（如果存在）
    - 从 modes.yaml 中移除模式定义

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
    try:
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

    except HTTPException:
        raise
    except (OSError, PermissionError) as e:
        # Filesystem error during mode deletion
        logger.error(f"Failed to delete mode {mode_slug}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete mode: {e!s}")
    except (AttributeError, KeyError) as e:
        # Mode manager error - fast fail
        logger.error(f"Mode manager error deleting mode {mode_slug}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete mode: {e!s}")
    except Exception as e:
        # Unexpected error - fast fail
        logger.critical(f"Unexpected error deleting mode {mode_slug}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


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
    try:
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
            try:
                workspace_path = Path(workspace.absolute_path)
                rules_abs_path = Path(rules_dir)
                # 尝试转换为相对于工作区的路径
                try:
                    relative_dir = str(rules_abs_path.relative_to(workspace_path))
                except ValueError:
                    # 如果不在工作区内，使用绝对路径但简化显示
                    relative_dir = str(rules_abs_path)
            except Exception as e:
                logger.warning(f"Failed to convert rules dir to relative: {e}")
                relative_dir = str(rules_dir) if rules_dir else None

        logger.info(f"Successfully retrieved {len(rules_dict)} rules files for mode {mode_slug}")
        return ModeRulesResponse(success=True, rules=rules_dict, directory=relative_dir)

    except HTTPException:
        raise
    except (OSError, PermissionError) as e:
        # Filesystem error during rules retrieval
        logger.error(f"Failed to get rules for mode {mode_slug}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get rules: {e!s}")
    except (AttributeError, KeyError) as e:
        # Mode manager error - fast fail
        logger.error(f"Mode manager error getting rules for mode {mode_slug}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get rules: {e!s}")
    except Exception as e:
        # Unexpected error - fast fail
        logger.critical(f"Unexpected error getting rules for mode {mode_slug}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


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
    try:
        # 确保工作区已初始化
        if not workspace.is_initialized():
            await workspace.initialize()

        logger.info(f"Updating mode {mode_slug} in workspace {workspace_id}")

        # 将请求数据转换为字典
        mode_data = {
            "slug": request_data.slug,
            "name": request_data.name,
            "description": request_data.description,
            "roleDefinition": request_data.roleDefinition,
            "whenToUse": request_data.whenToUse,
            "groups": request_data.groups or [],
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
            "groups": updated_mode.groups,
            "customInstructions": updated_mode.custom_instructions,
        }

        logger.info(f"Successfully updated mode {mode_slug} in workspace {workspace_id}")
        return ModeResponse(
            success=True,
            message=f"Mode '{mode_slug}' updated successfully",
            mode=mode_dict,
        )

    except HTTPException:
        raise
    except (OSError, PermissionError) as e:
        # Filesystem error during mode update
        logger.error(f"Failed to update mode {mode_slug}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update mode: {e!s}")
    except (AttributeError, KeyError) as e:
        # Mode manager error - fast fail
        logger.error(f"Mode manager error updating mode {mode_slug}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update mode: {e!s}")
    except Exception as e:
        # Unexpected error - fast fail
        logger.critical(f"Unexpected error updating mode {mode_slug}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


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
    try:
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
            except ValueError:
                relative_dir = rules_dir

        return ModeRulesResponse(
            success=True,
            rules=rules_dict,
            directory=relative_dir,
        )

    except HTTPException:
        raise
    except (OSError, PermissionError) as e:
        # Filesystem error during rules update
        logger.error(f"Failed to update rules for mode {mode_slug}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update rules: {e!s}")
    except (AttributeError, KeyError) as e:
        # Mode manager error - fast fail
        logger.error(f"Mode manager error updating rules for mode {mode_slug}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update rules: {e!s}")
    except Exception as e:
        # Unexpected error - fast fail
        logger.critical(f"Unexpected error updating rules for mode {mode_slug}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

