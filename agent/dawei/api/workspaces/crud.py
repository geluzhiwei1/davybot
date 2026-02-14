"""工作区 CRUD API

实现工作区的创建、读取、更新、删除功能。

两级存储架构：
1. 系统级：~/.dawei/workspaces.json (工作区索引)
2. 工作区级：{workspace_path}/.dawei/workspace.json (详细配置)
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from dawei.core.path_security import sanitize_workspace_response
from dawei.storage.storage_provider import StorageProvider
from dawei.workspace.models import WorkspaceInfo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workspaces", tags=["workspaces-crud"])


# ==================== 请求/响应模型 ====================


class ValidatePathRequest(BaseModel):
    """路径验证请求"""

    path: str = Field(..., description="工作区路径")


class ValidatePathResponse(BaseModel):
    """路径验证响应"""

    success: bool
    valid: bool
    message: str
    exists: bool = False
    writable: bool | None = None
    is_empty: bool | None = None
    is_workspace: bool = False


class CreateWorkspaceRequest(BaseModel):
    """创建工作区请求"""

    path: str = Field(..., description="工作区完整路径")
    name: str | None = Field(None, description="工作区名称（可选，默认使用目录名）")
    display_name: str | None = Field(None, description="显示名称")
    description: str | None = Field(None, description="描述")


class UpdateWorkspaceRequest(BaseModel):
    """更新工作区请求"""

    display_name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=1000)
    is_active: bool | None = None


class WorkspaceResponse(BaseModel):
    """工作区响应"""

    success: bool
    workspace: dict[str, Any] | None = None
    message: str | None = None
    error: str | None = None


class WorkspaceListResponse(BaseModel):
    """工作区列表响应"""

    success: bool
    workspaces: list[dict[str, Any]]
    total: int


# ==================== 路径验证 API ====================


@router.post("/validate-path", response_model=ValidatePathResponse)
async def validate_path(request: ValidatePathRequest):
    """验证工作区路径

    检查项：
    1. 路径是否存在
    2. 是否有写入权限
    3. 是否已经是工作区
    4. 是否为空目录
    """
    try:
        path = Path(request.path).resolve()

        # 检查路径是否存在
        if not path.exists():
            return ValidatePathResponse(
                success=True,
                valid=True,
                message="路径不存在，将创建新目录",
                exists=False,
                writable=True,
                is_empty=True,
            )

        # 检查是否是目录
        if not path.is_dir():
            return ValidatePathResponse(
                success=True,
                valid=False,
                message="路径不是目录",
                exists=True,
            )

        # 检查是否已经是工作区
        if (path / ".dawei").exists():
            return ValidatePathResponse(
                success=True,
                valid=True,
                message="此目录已经是工作区，将添加到工作区列表",
                exists=True,
                writable=True,
                is_workspace=True,
            )

        # 检查写入权限
        if not os.access(path, os.W_OK):
            return ValidatePathResponse(
                success=True,
                valid=False,
                message="无写入权限",
                exists=True,
                writable=False,
            )

        # 检查是否为空
        is_empty = not any(path.iterdir())
        if not is_empty:
            return ValidatePathResponse(
                success=True,
                valid=True,
                message="目录不为空，将在现有目录中创建工作区",
                exists=True,
                writable=True,
                is_empty=False,
            )

        return ValidatePathResponse(
            success=True,
            valid=True,
            message="路径有效，可以创建工作区",
            exists=True,
            writable=True,
            is_empty=True,
        )

    except PermissionError:
        logger.exception("Permission denied accessing path: {request.path} - ")
        raise HTTPException(
            status_code=403,
            detail=f"Permission denied accessing path: {request.path}",
        )
    except OSError as e:
        logger.exception("OS error validating path {request.path}: ")
        raise HTTPException(status_code=400, detail=f"Invalid path: {e!s}")
    except Exception as e:
        logger.error(f"Unexpected error validating path {request.path}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal error validating path: {e!s}")


# ==================== 创建工作区 API ====================


@router.post("", response_model=WorkspaceResponse, status_code=201)
async def create_workspace(request: CreateWorkspaceRequest):
    """创建工作区

    关键步骤：
    1. 验证路径
    2. 创建工作区目录结构（如果不存在）
    3. 创建 .dawei/workspace.json（工作区级配置）
    4. 更新 ~/.dawei/workspaces.json（系统级索引）
    """
    try:
        workspace_path = Path(request.path).resolve()

        # 获取或创建 workspace_storage
        # 如果路径不存在，先创建
        if not workspace_path.exists():
            workspace_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created directory: {workspace_path}")

        workspace_storage = StorageProvider.get_workspace_storage(str(workspace_path))

        # 检查是否已是工作区（存在 workspace.json）
        workspace_config_path = workspace_path / ".dawei" / "workspace.json"
        is_existing_workspace = workspace_config_path.exists()

        if is_existing_workspace:
            # 读取现有工作区配置
            logger.info(f"Found existing workspace at {workspace_path}")
            existing_config = json.loads(workspace_config_path.read_text())
            workspace_id = existing_config.get("id")
            workspace_name = existing_config.get("name", workspace_path.name)

            # 使用提供的 display_name 和 description 更新配置（如果有）
            display_name = request.display_name or existing_config.get(
                "display_name",
                workspace_name,
            )
            description = request.description or existing_config.get("description")

            # 更新工作区配置
            workspace_info = WorkspaceInfo(
                id=workspace_id,
                name=workspace_name,
                display_name=display_name,
                description=description,
                created_at=datetime.fromisoformat(existing_config.get("created_at")),
            )

            # 写入更新后的配置
            await workspace_storage.write_file(
                ".dawei/workspace.json",
                json.dumps(workspace_info.to_dict(), indent=2, ensure_ascii=False),
            )
            logger.info(f"Updated existing workspace.json for {workspace_id}")
        else:
            # 创建 .dawei 目录结构
            await workspace_storage.create_directory(".dawei")
            await workspace_storage.create_directory(".dawei/chat-history")
            await workspace_storage.create_directory(".dawei/checkpoints")
            await workspace_storage.create_directory(".dawei/task_graphs")
            logger.info(f"Created .dawei directory structure in {workspace_path}")

            # 生成 UUID
            workspace_id = str(uuid.uuid4())

            # 创建工作区名称
            workspace_name = request.name or workspace_path.name

            # 创建工作区级配置 (.dawei/workspace.json)
            workspace_info = WorkspaceInfo(
                id=workspace_id,
                name=workspace_name,
                display_name=request.display_name or workspace_name,
                description=request.description,
                created_at=datetime.now(timezone.utc),
            )

            # 写入工作区级配置
            await workspace_storage.write_file(
                ".dawei/workspace.json",
                json.dumps(workspace_info.to_dict(), indent=2, ensure_ascii=False),
            )
            logger.info(f"Created workspace.json for {workspace_id}")

        # 更新系统级索引 (~/.dawei/workspaces.json)
        logger.info(f"About to call _register_workspace_in_system_index for {workspace_id}")
        await _register_workspace_in_system_index(
            workspace_id=workspace_id,
            name=workspace_name,
            display_name=request.display_name or workspace_name,
            path=str(workspace_path),
        )
        logger.info(f"Finished _register_workspace_in_system_index for {workspace_id}")

        # 添加 path 到返回数据（内部使用）
        workspace_dict = workspace_info.to_dict()
        workspace_dict["path"] = str(workspace_path)

        # 🔒 安全：净化响应，移除绝对路径
        sanitized_workspace = sanitize_workspace_response(workspace_dict, remove_path=True)

        return WorkspaceResponse(
            success=True,
            workspace=sanitized_workspace,
            message="工作区创建成功",
        )

    except PermissionError:
        logger.exception("Permission denied creating workspace at {request.path}: ")
        # 清理已创建的文件
        await _cleanup_workspace_directory(workspace_path)
        raise HTTPException(
            status_code=403,
            detail=f"Permission denied: Cannot create workspace at {request.path}",
        )
    except OSError as e:
        logger.exception("Filesystem error creating workspace at {request.path}: ")
        # 清理已创建的文件
        await _cleanup_workspace_directory(workspace_path)
        raise HTTPException(status_code=400, detail=f"Filesystem error: {e!s}")
    except json.JSONDecodeError:
        logger.exception("Invalid JSON in existing workspace config at {request.path}: ")
        raise HTTPException(
            status_code=400,
            detail="Invalid workspace configuration: corrupted JSON data",
        )
    except ValueError as e:
        logger.exception("Invalid data format for workspace at {request.path}: ")
        # 清理已创建的文件
        await _cleanup_workspace_directory(workspace_path)
        raise HTTPException(status_code=400, detail=f"Invalid data format: {e!s}")
    except Exception as e:
        logger.error(f"Unexpected error creating workspace at {request.path}: {e}", exc_info=True)
        # 清理已创建的文件
        await _cleanup_workspace_directory(workspace_path)
        raise HTTPException(status_code=500, detail=f"Internal error creating workspace: {e!s}")


async def _cleanup_workspace_directory(workspace_path: Path):
    """清理工作区目录中的 .dawei 配置

    Args:
        workspace_path: 工作区路径

    """
    # Fast Fail: 验证输入参数
    if workspace_path is None:
        logger.warning("Cleanup called with None workspace path, skipping")
        return

    try:
        if workspace_path.exists():
            import shutil

            dawei_path = workspace_path / ".dawei"
            if dawei_path.exists():
                shutil.rmtree(dawei_path)
                logger.info(f"Cleaned up .dawei directory at {dawei_path}")
    except OSError as e:
        logger.warning(f"Failed to cleanup workspace directory {workspace_path}: {e}")
    except Exception as e:
        logger.error(
            f"Unexpected error during workspace cleanup at {workspace_path}: {e}",
            exc_info=True,
        )


async def _register_workspace_in_system_index(
    workspace_id: str,
    name: str,
    display_name: str,
    path: str,
):
    """在系统级索引中注册工作区

    更新 ~/.dawei/workspaces.json
    """
    system_storage = StorageProvider.get_system_storage()

    logger.info(f"Registering workspace {workspace_id} in workspaces.json")

    # 读取现有的 workspaces.json
    try:
        if await system_storage.exists("workspaces.json"):
            logger.info("workspaces.json exists, reading it...")
            content = await system_storage.read_file("workspaces.json")
            data = json.loads(content)
            logger.info(f"Current workspaces count: {len(data.get('workspaces', []))}")
        else:
            logger.info("workspaces.json does not exist, creating new one...")
            data = {"workspaces": []}

        # 添加新工作区（存储基础信息 + display_name）
        data["workspaces"].append(
            {
                "id": workspace_id,
                "name": name,
                "display_name": display_name,
                "path": path,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "is_active": True,
            },
        )

        logger.info(f"Writing workspaces.json with {len(data['workspaces'])} workspaces...")

        # 写回文件
        await system_storage.write_file(
            "workspaces.json",
            json.dumps(data, indent=2, ensure_ascii=False),
        )
        logger.info(f"Registered workspace {workspace_id} in workspaces.json")

        # 清除 StorageProvider 缓存并重新加载 WorkspaceManager
        StorageProvider.clear_system_storage_cache()
        from dawei.workspace.workspace_manager import workspace_manager

        workspace_manager.reload()
        logger.info(f"Reloaded workspace_manager after registering {workspace_id}")

    except PermissionError:
        logger.exception("Permission denied updating workspaces.json: ")
        raise
    except json.JSONDecodeError:
        logger.exception("Invalid JSON in workspaces.json: ")
        raise
    except OSError:
        logger.exception("Filesystem error updating workspaces.json: ")
        raise
    except Exception as e:
        logger.error(f"Unexpected error updating workspaces.json: {e}", exc_info=True)
        raise


# ==================== 读取工作区列表 API ====================


@router.get("", response_model=WorkspaceListResponse)
async def get_workspaces(
    include_inactive: bool = Query(False, description="是否包含已停用的工作区"),
):
    """获取工作区列表

    数据来源：~/.dawei/workspaces.json (系统级索引)
    """
    system_storage = StorageProvider.get_system_storage()

    try:
        # 读取系统级索引
        if not await system_storage.exists("workspaces.json"):
            return WorkspaceListResponse(success=True, workspaces=[], total=0)

        content = await system_storage.read_file("workspaces.json")
        data = json.loads(content)

        workspaces = data.get("workspaces", [])

        # 过滤活跃的工作区
        if not include_inactive:
            workspaces = [w for w in workspaces if w.get("is_active", True)]

        # 🔒 安全：净化工作区列表，移除绝对路径
        sanitized_workspaces = [sanitize_workspace_response(ws, remove_path=True) for ws in workspaces]

        return WorkspaceListResponse(
            success=True,
            workspaces=sanitized_workspaces,
            total=len(sanitized_workspaces),
        )

    except PermissionError:
        logger.exception("Permission denied reading workspaces.json: ")
        raise HTTPException(status_code=403, detail="Permission denied accessing workspace list")
    except json.JSONDecodeError:
        logger.exception("Invalid JSON in workspaces.json: ")
        raise HTTPException(status_code=500, detail="Corrupted workspace index file")
    except OSError as e:
        logger.exception("Filesystem error reading workspaces: ")
        raise HTTPException(status_code=500, detail=f"Error reading workspace list: {e!s}")
    except Exception as e:
        logger.error(f"Unexpected error getting workspaces: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal error: {e!s}")


# ==================== 读取工作区详情 API ====================


@router.get("/{workspace_id}/info", response_model=WorkspaceResponse)
async def get_workspace_info(workspace_id: str):
    """获取工作区详情

    数据来源：
    1. 从 workspaces.json 获取 path
    2. 从 {path}/.dawei/workspace.json 读取详细信息
    """
    system_storage = StorageProvider.get_system_storage()

    try:
        # 1. 从系统级索引获取工作区路径
        if not await system_storage.exists("workspaces.json"):
            raise HTTPException(status_code=404, detail="Workspace not found")

        content = await system_storage.read_file("workspaces.json")
        data = json.loads(content)

        workspace_basic = None
        for ws in data.get("workspaces", []):
            if ws["id"] == workspace_id:
                workspace_basic = ws
                break

        if not workspace_basic:
            raise HTTPException(status_code=404, detail="Workspace not found")

        # 2. 从工作区级配置读取详细信息
        workspace_path = workspace_basic["path"]
        workspace_storage = StorageProvider.get_workspace_storage(workspace_path)

        workspace_info_path = ".dawei/workspace.json"
        if not await workspace_storage.exists(workspace_info_path):
            raise HTTPException(status_code=404, detail="Workspace config not found")

        workspace_content = await workspace_storage.read_file(workspace_info_path)
        workspace_info = json.loads(workspace_content)

        # 🔒 安全：净化工作区信息，移除绝对路径
        sanitized_info = sanitize_workspace_response(workspace_info, remove_path=True)

        return WorkspaceResponse(success=True, workspace=sanitized_info)

    except HTTPException:
        raise
    except PermissionError:
        logger.exception("Permission denied accessing workspace {workspace_id}: ")
        raise HTTPException(
            status_code=403,
            detail=f"Permission denied accessing workspace {workspace_id}",
        )
    except json.JSONDecodeError:
        logger.exception("Invalid JSON in workspace {workspace_id} config: ")
        raise HTTPException(
            status_code=500,
            detail=f"Corrupted workspace configuration for {workspace_id}",
        )
    except OSError as e:
        logger.exception("Filesystem error reading workspace {workspace_id}: ")
        raise HTTPException(status_code=500, detail=f"Error reading workspace: {e!s}")
    except Exception as e:
        logger.error(f"Unexpected error getting workspace {workspace_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal error: {e!s}")


# ==================== 更新工作区 API ====================


@router.put("/{workspace_id}", response_model=WorkspaceResponse)
async def update_workspace(workspace_id: str, request: UpdateWorkspaceRequest):
    """更新工作区信息

    同时更新系统级索引和工作区级配置
    """
    system_storage = StorageProvider.get_system_storage()

    try:
        # 1. 从系统级索引获取工作区路径
        content = await system_storage.read_file("workspaces.json")
        data = json.loads(content)

        workspace_basic = None
        for _i, ws in enumerate(data.get("workspaces", [])):
            if ws["id"] == workspace_id:
                workspace_basic = ws
                break

        if not workspace_basic:
            raise HTTPException(status_code=404, detail="Workspace not found")

        # 2. 读取工作区级配置
        workspace_path = workspace_basic["path"]
        workspace_storage = StorageProvider.get_workspace_storage(workspace_path)

        workspace_content = await workspace_storage.read_file(".dawei/workspace.json")
        workspace_info = json.loads(workspace_content)

        # 3. 更新字段
        if request.display_name is not None:
            workspace_info["display_name"] = request.display_name
            # 同时更新系统级索引中的 display_name
            workspace_basic["display_name"] = request.display_name
        if request.description is not None:
            workspace_info["description"] = request.description
        if request.is_active is not None:
            workspace_info["is_active"] = request.is_active

        # 4. 写回工作区级配置
        await workspace_storage.write_file(
            ".dawei/workspace.json",
            json.dumps(workspace_info, indent=2, ensure_ascii=False),
        )
        logger.info(f"Updated workspace {workspace_id}")

        # 5. 更新系统级索引
        await system_storage.write_file(
            "workspaces.json",
            json.dumps(data, indent=2, ensure_ascii=False),
        )

        # 添加 path 到返回数据（内部使用）
        workspace_info["path"] = workspace_path

        # 🔒 安全：净化工作区信息，移除绝对路径
        sanitized_info = sanitize_workspace_response(workspace_info, remove_path=True)

        return WorkspaceResponse(success=True, workspace=sanitized_info)

    except HTTPException:
        raise
    except PermissionError:
        logger.exception("Permission denied updating workspace {workspace_id}: ")
        raise HTTPException(
            status_code=403,
            detail=f"Permission denied updating workspace {workspace_id}",
        )
    except json.JSONDecodeError:
        logger.exception("Invalid JSON in workspace {workspace_id}: ")
        raise HTTPException(status_code=500, detail=f"Corrupted workspace data for {workspace_id}")
    except OSError as e:
        logger.exception("Filesystem error updating workspace {workspace_id}: ")
        raise HTTPException(status_code=500, detail=f"Error updating workspace: {e!s}")
    except Exception as e:
        logger.error(f"Unexpected error updating workspace {workspace_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal error: {e!s}")


# ==================== 删除工作区 API ====================


@router.delete("/{workspace_id}", response_model=WorkspaceResponse)
async def delete_workspace(
    workspace_id: str,
    delete_config: bool = Query(True, description="是否删除 .dawei 配置目录"),
    delete_files: bool = Query(False, description="是否删除整个工作区目录"),
):
    """删除工作区

    步骤：
    1. 从 workspaces.json 移除（系统级）
    2. 删除 .dawei 目录（工作区级，可选）
    3. 删除整个工作区目录（可选）
    """
    system_storage = StorageProvider.get_system_storage()

    try:
        # 1. 读取系统级索引
        content = await system_storage.read_file("workspaces.json")
        data = json.loads(content)

        workspace_basic = None
        workspace_index = -1
        for i, ws in enumerate(data.get("workspaces", [])):
            if ws["id"] == workspace_id:
                workspace_basic = ws
                workspace_index = i
                break

        if not workspace_basic:
            raise HTTPException(status_code=404, detail="Workspace not found")

        workspace_path = workspace_basic["path"]

        # 2. 删除 .dawei 目录（工作区级配置）
        if delete_config:
            workspace_storage = StorageProvider.get_workspace_storage(workspace_path)

            if await workspace_storage.exists(".dawei"):
                await workspace_storage.delete(".dawei", recursive=True)
                logger.info(f"Deleted .dawei directory for workspace {workspace_id}")

        # 3. 删除整个工作区目录（可选）
        if delete_files:
            # 注意：这需要使用父目录的 Storage
            parent_path = str(Path(workspace_path).parent)
            parent_storage = StorageProvider.get_workspace_storage(parent_path)
            workspace_dir_name = Path(workspace_path).name

            if await parent_storage.exists(workspace_dir_name):
                await parent_storage.delete(workspace_dir_name, recursive=True)
                logger.info(f"Deleted workspace directory: {workspace_path}")

        # 4. 从系统级索引移除
        data["workspaces"].pop(workspace_index)
        await system_storage.write_file(
            "workspaces.json",
            json.dumps(data, indent=2, ensure_ascii=False),
        )
        logger.info(f"Removed workspace {workspace_id} from workspaces.json")

        # 清除 StorageProvider 缓存并重新加载 WorkspaceManager
        StorageProvider.clear_system_storage_cache()
        from dawei.workspace.workspace_manager import workspace_manager

        workspace_manager.reload()
        logger.info(f"Reloaded workspace_manager after deleting {workspace_id}")

        return WorkspaceResponse(
            success=True,
            message="工作区已成功删除",
            workspace_id=workspace_id,
        )

    except HTTPException:
        raise
    except PermissionError:
        logger.exception("Permission denied deleting workspace {workspace_id}: ")
        raise HTTPException(
            status_code=403,
            detail=f"Permission denied: Cannot delete workspace {workspace_id}",
        )
    except json.JSONDecodeError:
        logger.exception("Invalid JSON in workspaces.json during delete: ")
        raise HTTPException(status_code=500, detail="Corrupted workspace index during deletion")
    except OSError as e:
        logger.exception("Filesystem error deleting workspace {workspace_id}: ")
        raise HTTPException(status_code=500, detail=f"Error deleting workspace: {e!s}")
    except Exception as e:
        logger.error(f"Unexpected error deleting workspace {workspace_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal error: {e!s}")


# ==================== 工作区统计 API ====================


@router.get("/{workspace_id}/stats")
async def get_workspace_stats(workspace_id: str):
    """获取工作区统计信息

    包括：
    - 文件统计（总数量、总大小、类型分布）
    - 对话统计（对话数量、消息数量）
    - 任务统计（任务数量）
    - 最后活动时间
    """
    system_storage = StorageProvider.get_system_storage()

    try:
        # 1. 从系统级索引获取工作区路径
        content = await system_storage.read_file("workspaces.json")
        data = json.loads(content)

        workspace_basic = None
        for ws in data.get("workspaces", []):
            if ws["id"] == workspace_id:
                workspace_basic = ws
                break

        if not workspace_basic:
            raise HTTPException(status_code=404, detail="Workspace not found")

        workspace_path = workspace_basic["path"]
        workspace_storage = StorageProvider.get_workspace_storage(workspace_path)

        # 2. 统计文件信息
        total_files = 0
        total_size = 0
        file_types = {}

        try:
            async for item in workspace_storage.list_files(recursive=True, include_hidden=False):
                if not item["is_dir"]:
                    total_files += 1
                    total_size += item.get("size", 0)

                    # 统计文件类型
                    ext = item["name"].split(".")[-1].lower() if "." in item["name"] else "no_ext"
                    file_types[ext] = file_types.get(ext, 0) + 1
        except Exception as e:
            logger.warning(f"Failed to count files for workspace {workspace_id}: {e}")

        # 3. 统计对话信息
        conversations_count = 0
        messages_count = 0
        last_activity_at = workspace_basic.get("created_at", "")

        try:
            conversations_path = ".dawei/conversations"
            if await workspace_storage.exists(conversations_path):
                async for item in workspace_storage.list_files(conversations_path, recursive=False):
                    if item["name"].endswith(".json") and not item["is_dir"]:
                        conversations_count += 1
                        # 读取对话文件统计消息数量
                        try:
                            conv_content = await workspace_storage.read_file(
                                f"{conversations_path}/{item['name']}",
                            )
                            conv_data = json.loads(conv_content)
                            messages_count += len(conv_data.get("messages", []))
                        except (json.JSONDecodeError, OSError, KeyError) as e:
                            # Log but continue - corrupted conversation files shouldn't break stats
                            logger.warning(f"Failed to read conversation {item.get('name')}: {e}")

            # 获取最后修改时间
            try:
                workspace_info_path = ".dawei/workspace.json"
                if await workspace_storage.exists(workspace_info_path):
                    stat = await workspace_storage.stat(workspace_info_path)
                    if stat and "modified" in stat:
                        last_activity_at = stat["modified"]
            except (OSError, KeyError) as e:
                # Log but continue - missing workspace info shouldn't break stats
                logger.debug(f"Failed to get workspace last activity: {e}")
        except Exception as e:
            logger.warning(f"Failed to count conversations for workspace {workspace_id}: {e}")

        # 4. 统计任务信息
        tasks_count = 0
        try:
            tasks_path = ".dawei/tasks.json"
            if await workspace_storage.exists(tasks_path):
                tasks_content = await workspace_storage.read_file(tasks_path)
                tasks_data = json.loads(tasks_content)
                tasks_count = len(tasks_data.get("todos", []))
        except (json.JSONDecodeError, OSError, KeyError) as e:
            # Log but continue - missing or corrupted tasks file shouldn't break stats
            logger.debug(f"Failed to count tasks: {e}")

        return {
            "totalFiles": total_files,
            "totalSize": total_size,
            "fileTypes": file_types,
            "conversationsCount": conversations_count,
            "messagesCount": messages_count,
            "tasksCount": tasks_count,
            "lastActivityAt": last_activity_at,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Unexpected error getting workspace stats {workspace_id}: {e}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=f"Internal error: {e!s}")
