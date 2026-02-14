"""Core Workspace API Routes

核心的Workspace CRUD操作
"""

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Response

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


# --- 核心Workspace CRUD操作 ---
# 注意：GET /workspaces 和 GET /workspaces/{id}/info 已移至 crud.py
# 这里保留注释以说明路由已迁移

# @router.get("/workspaces")
# async def get_workspaces():
#     """Get all available workspaces."""
#     workspaces = workspace_manager.get_all_workspaces()
#     active_workspaces = [w for w in workspaces if w.get('is_active', True)]
#     return {
#         "success": True,
#         "workspaces": active_workspaces
#     }


# @router.get("/workspaces/{workspace_id}/info")
# async def get_workspace_info(workspace_id: str):
#     """Get detailed information about a specific workspace by ID."""
#     workspace = workspace_manager.get_workspace_by_id(workspace_id)
#     if not workspace:
#         raise HTTPException(status_code=404, detail=f"Workspace with ID {workspace_id} not found")
#
#     return {
#         "success": True,
#         "workspace": workspace
#     }


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
async def get_workspace_modes(workspace: UserWorkspace = Depends(get_user_workspace)):
    """获取指定工作空间的所有可用模式。

    返回的 mode 列表会按照以下规则排序：
    1. 内置 system modes (orchestrator, plan, do, check, act) 固定在最前面，按此顺序
    2. 其他 modes 按 slug 字母顺序排列

    每个模式包含 source 字段：
    - system: 内置系统模式（5个 PDCA 模式）
    - user: 用户级自定义模式
    - workspace: 工作区级自定义模式

    Raises:
        HTTPException: If workspace initialization fails
        HTTPException: If mode retrieval fails

    """
    try:
        # 确保工作区已初始化
        if not workspace.is_initialized():
            await workspace.initialize()

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
