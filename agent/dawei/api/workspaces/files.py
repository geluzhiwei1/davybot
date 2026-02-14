# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""File Operations API Routes

文件系统操作和目录树管理
"""

import logging
import shutil
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel

# 导入服务依赖
from dawei.api.services import get_workspace_file_service
from dawei.storage.storage import Storage

# 导入共享模型
from .models import FileTreeItem

logger = logging.getLogger(__name__)

# 创建路由器
router = APIRouter(tags=["workspaces-files"])


# --- 安全验证辅助函数 ---


def _validate_path_safety(workspace_path: Path, target_path: Path) -> None:
    """验证路径安全性，防止路径遍历攻击"""
    try:
        target_path.resolve().relative_to(workspace_path.resolve())
    except (ValueError, RuntimeError):
        raise HTTPException(status_code=403, detail="Access denied: path outside workspace") from None


def _validate_path_exists(file_path: Path, error_message: str) -> None:
    """验证路径是否存在"""
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=error_message)


def _validate_path_not_exists(file_path: Path, error_message: str) -> None:
    """验证路径不存在"""
    if file_path.exists():
        raise HTTPException(status_code=400, detail=error_message)


# --- 文件树构建函数 ---


def _build_file_tree(files: list[dict[str, Any]], base_path: str = "") -> list[FileTreeItem]:
    """构建文件树结构"""
    tree = {}

    for file in files:
        path_parts = file["path"].split("/")
        current_level = tree

        # 构建树形结构
        for i, part in enumerate(path_parts):
            if part not in current_level:
                is_last_part = i == len(path_parts) - 1
                current_level[part] = {
                    "name": part,
                    "path": file["path"],
                    "type": ("folder" if not is_last_part else ("file" if not file["is_directory"] else "folder")),
                    "level": i,
                    "children": {},
                }
            current_level = current_level[part]["children"]

    # 转换为列表格式
    def _tree_to_list(tree_dict: dict, level: int = 0) -> list[FileTreeItem]:
        result = []
        for item in tree_dict.values():
            result.append(
                FileTreeItem(
                    name=item["name"],
                    path=item["path"],
                    type=item["type"],
                    level=item["level"],
                    children=_tree_to_list(item["children"], level + 1),
                ),
            )
        return result

    return _tree_to_list(tree)


# --- 文件树操作路由 ---

# --- 文件创建和修改API ---


class CreateFileRequest(BaseModel):
    """创建文件请求"""

    path: str
    content: str = ""
    is_directory: bool = False


@router.post("/{workspace_id}/files/create")
async def create_file_or_directory(
    workspace_id: str,
    data: CreateFileRequest,
    file_service: Storage = Depends(get_workspace_file_service),
):
    """创建文件或目录

    在工作区中创建新的文件或目录
    """
    # 获取工作区根路径
    workspace_path = Path(file_service.root_dir)

    # 构建完整路径
    full_path = workspace_path / data.path

    # Fast Fail: 检查路径是否已存在
    _validate_path_not_exists(full_path, f"Path already exists: {data.path}")

    try:
        # 创建文件或目录
        if data.is_directory:
            # 创建目录
            full_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created directory: {full_path}")
        else:
            # 确保父目录存在
            full_path.parent.mkdir(parents=True, exist_ok=True)

            # 创建文件
            full_path.write_text(data.content, encoding="utf-8")
            logger.info(f"Created file: {full_path}")

        return {
            "success": True,
            "message": f"{'Directory' if data.is_directory else 'File'} created successfully",
            "path": data.path,
        }

    except OSError as e:
        logger.error(f"创建文件失败 (文件系统错误): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"File system error: {e!s}")
    except UnicodeEncodeError as e:
        logger.error(f"创建文件失败 (编码错误): {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"Encoding error: {e!s}")
    except Exception as e:
        logger.error(f"创建文件失败 (未知错误): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create file: {e!s}")


@router.get("/{workspace_id}/file-tree")
async def get_workspace_file_tree(
    workspace_id: str,
    path: str = Query(".", description="要列出的路径"),
    include_hidden: bool = Query(False, description="是否包含隐藏文件"),
    max_depth: int = Query(5, description="递归最大深度"),
    file_service: Storage = Depends(get_workspace_file_service),
):
    """获取工作区的文件树结构"""
    try:
        files = await file_service.list_directory(
            path=path,
            recursive=True,
            include_hidden=include_hidden,
            max_depth=max_depth,
        )

        # Fast Fail: 验证文件列表数据
        if not isinstance(files, list):
            raise ValueError("Invalid file data format received from storage")

        # 构建扁平化的文件树列表（兼容前端现有格式）
        flat_tree = []
        for file in files:
            # Fast Fail: 验证单个文件数据
            if not isinstance(file, dict) or "path" not in file or "name" not in file:
                raise ValueError(f"Invalid file data structure: {file}")

            path_parts = file["path"].split("/")
            level = len(path_parts) - 1
            flat_tree.append(
                {
                    "id": file["path"],  # 添加 id 字段，使用 path 作为 id
                    "name": file["name"],
                    "path": file["path"],
                    "type": ("directory" if file["is_directory"] else "file"),  # 使用 directory 而不是 folder
                    "level": level,
                    "size": file.get("size", 0),
                    "createdAt": file.get("created_at", ""),
                    "updatedAt": file.get("updated_at", ""),
                    "children": [],  # 添加 children 字段
                },
            )

        # 按路径排序，确保文件夹在前，文件在后
        flat_tree.sort(key=lambda x: (x["path"], x["type"] == "file"))

        return {"success": True, "fileTree": flat_tree}
    except (ValueError, TypeError) as e:
        logger.exception("获取文件树失败 (数据格式错误): ")
        raise HTTPException(status_code=400, detail=f"Invalid data format: {e!s}")
    except Exception as e:
        logger.error(f"获取文件树失败 (服务错误): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get file tree: {e!s}")


# --- 文件上传API ---


@router.post("/{workspace_id}/files/upload")
async def upload_file(
    workspace_id: str,
    file: UploadFile,
    parent_path: str = Form(""),
    file_service: Storage = Depends(get_workspace_file_service),
):
    """上传单个文件到工作区

    Args:
        workspace_id: 工作区ID
        file: 上传的文件
        parent_path: 父目录路径（空字符串表示根目录）
        file_service: 文件服务依赖

    Returns:
        上传结果

    """
    # 获取工作区根路径
    workspace_path = Path(file_service.root_dir)

    # 构建目标目录路径
    target_dir = workspace_path / parent_path if parent_path else workspace_path

    # Fast Fail: 验证文件对象
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="Invalid file or missing filename")

    # Fast Fail: 验证目标目录安全性
    _validate_path_safety(workspace_path, target_dir)

    try:
        # 确保目标目录存在
        target_dir.mkdir(parents=True, exist_ok=True)

        # 构建文件路径（支持文件夹上传时的相对路径）
        file_path = target_dir / file.filename

        # 验证最终路径安全性，防止路径遍历攻击
        _validate_path_safety(workspace_path, file_path)

        # 检查文件是否已存在
        if file_path.exists():
            logger.warning(f"File already exists, will overwrite: {file_path}")

        # 保存文件
        with Path(file_path).open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        logger.info(f"File uploaded successfully: {file_path}")

        return {
            "success": True,
            "message": "File uploaded successfully",
            "filename": file.filename,
            "path": str(file_path.relative_to(workspace_path)),
        }

    except OSError as e:
        logger.error(f"文件上传失败 (文件系统错误): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"File system error: {e!s}")
    except OSError as e:
        logger.error(f"文件上传失败 (I/O错误): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"I/O error: {e!s}")
    except Exception as e:
        logger.error(f"文件上传失败 (未知错误): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to upload file: {e!s}")


@router.post("/{workspace_id}/files/upload-folder")
async def upload_folder(
    workspace_id: str,
    files: list[UploadFile],
    parent_path: str = Form(""),
    file_service: Storage = Depends(get_workspace_file_service),
):
    """上传文件夹（多个文件）到工作区

    Args:
        workspace_id: 工作区ID
        files: 上传的文件列表
        parent_path: 父目录路径（空字符串表示根目录）
        file_service: 文件服务依赖

    Returns:
        上传结果

    """
    # Fast Fail: 验证文件列表
    if not files:
        raise HTTPException(status_code=400, detail="No files provided for upload")

    # 获取工作区根路径
    workspace_path = Path(file_service.root_dir)

    # 构建目标目录路径
    target_dir = workspace_path / parent_path if parent_path else workspace_path

    # Fast Fail: 验证目标目录安全性
    _validate_path_safety(workspace_path, target_dir)

    uploaded_files = []
    errors = []

    for file in files:
        # Fast Fail: 验证文件对象
        if not file or not file.filename:
            error_msg = "Invalid file or missing filename"
            errors.append(error_msg)
            logger.error(f"{file.filename or 'Unknown file'}: {error_msg}")
            continue

        try:
            # 使用文件的完整相对路径（支持文件夹上传时的相对路径）
            file_path = target_dir / file.filename

            # 验证最终路径安全性，防止路径遍历攻击
            _validate_path_safety(workspace_path, file_path)

            # 确保父目录存在
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # 检查文件是否已存在
            if file_path.exists():
                logger.warning(f"File already exists, will overwrite: {file_path}")

            # 保存文件
            with Path(file_path).open("wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

            uploaded_files.append(
                {
                    "filename": file.filename,
                    "path": str(file_path.relative_to(workspace_path)),
                },
            )
            logger.info(f"File uploaded successfully: {file_path}")

        except OSError as e:
            error_msg = f"File system error: {e!s}"
            errors.append(f"{file.filename}: {error_msg}")
            logger.error(f"{file.filename}: {error_msg}", exc_info=True)
        except OSError as e:
            error_msg = f"I/O error: {e!s}"
            errors.append(f"{file.filename}: {error_msg}")
            logger.error(f"{file.filename}: {error_msg}", exc_info=True)
        except Exception as e:
            error_msg = f"Unknown error: {e!s}"
            errors.append(f"{file.filename}: {error_msg}")
            logger.error(f"{file.filename}: {error_msg}", exc_info=True)

    logger.info(
        f"Folder upload completed: {len(uploaded_files)} files uploaded, {len(errors)} errors",
    )

    return {
        "success": len(errors) == 0,
        "message": f"Uploaded {len(uploaded_files)} files" + (f" with {len(errors)} errors" if errors else ""),
        "uploaded_files": uploaded_files,
        "errors": errors,
    }


@router.delete("/{workspace_id}/files/delete")
async def delete_file_or_directory(
    workspace_id: str,
    path: str = Query(..., description="要删除的文件或目录路径"),
    file_service: Storage = Depends(get_workspace_file_service),
):
    """删除文件或目录

    Args:
        workspace_id: 工作区ID
        path: 要删除的文件或目录路径
        file_service: 文件服务依赖

    Returns:
        删除结果

    """
    # 获取工作区根路径
    workspace_path = Path(file_service.root_dir)

    # 构建完整路径
    full_path = workspace_path / path

    # Fast Fail: 检查路径是否存在
    _validate_path_exists(full_path, f"Path not found: {path}")

    # Fast Fail: 检查路径是否在工作区内（防止路径遍历攻击）
    _validate_path_safety(workspace_path, full_path)

    try:
        # 删除文件或目录
        if full_path.is_file():
            full_path.unlink()
            logger.info(f"Deleted file: {full_path}")
        elif full_path.is_dir():
            shutil.rmtree(full_path)
            logger.info(f"Deleted directory: {full_path}")
        else:
            raise HTTPException(status_code=400, detail=f"Invalid path type: {path}")

        return {
            "success": True,
            "message": f"{'Directory' if full_path.is_dir() else 'File'} deleted successfully",
            "path": path,
        }

    except PermissionError as e:
        logger.error(f"删除文件失败 (权限错误): {e}", exc_info=True)
        raise HTTPException(status_code=403, detail=f"Permission denied: {e!s}")
    except OSError as e:
        logger.error(f"删除文件失败 (文件系统错误): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"File system error: {e!s}")
    except Exception as e:
        logger.error(f"删除文件失败 (未知错误): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete file: {e!s}")


class CopyFileRequest(BaseModel):
    """复制文件或目录请求"""

    source_path: str
    destination_path: str


@router.post("/{workspace_id}/files/copy")
async def copy_file_or_directory(
    workspace_id: str,
    data: CopyFileRequest,
    file_service: Storage = Depends(get_workspace_file_service),
):
    """复制文件或目录

    Args:
        workspace_id: 工作区ID
        data: 包含源路径和目标路径的请求数据
        file_service: 文件服务依赖

    Returns:
        复制结果

    """
    # 获取工作区根路径
    workspace_path = Path(file_service.root_dir)

    # 构建完整路径
    source_path = workspace_path / data.source_path
    destination_path = workspace_path / data.destination_path

    # Fast Fail: 检查源路径是否存在
    _validate_path_exists(source_path, f"Source path not found: {data.source_path}")

    # Fast Fail: 检查路径是否在工作区内（防止路径遍历攻击）
    _validate_path_safety(workspace_path, source_path)
    _validate_path_safety(workspace_path, destination_path)

    # Fast Fail: 检查目标路径是否已存在
    _validate_path_not_exists(
        destination_path,
        f"Destination path already exists: {data.destination_path}",
    )

    try:
        # 复制文件或目录
        if source_path.is_file():
            # 确保目标目录存在
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, destination_path)
            logger.info(f"Copied file: {source_path} -> {destination_path}")
        elif source_path.is_dir():
            shutil.copytree(source_path, destination_path)
            logger.info(f"Copied directory: {source_path} -> {destination_path}")
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid source path type: {data.source_path}",
            )

        return {
            "success": True,
            "message": f"{'Directory' if source_path.is_dir() else 'File'} copied successfully",
            "source": data.source_path,
            "destination": data.destination_path,
        }

    except PermissionError as e:
        logger.error(f"复制文件失败 (权限错误): {e}", exc_info=True)
        raise HTTPException(status_code=403, detail=f"Permission denied: {e!s}")
    except OSError as e:
        logger.error(f"复制文件失败 (文件系统错误): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"File system error: {e!s}")
    except Exception as e:
        logger.error(f"复制文件失败 (未知错误): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to copy file: {e!s}")


class RenameFileRequest(BaseModel):
    """重命名文件或目录请求"""

    old_path: str
    new_path: str


@router.put("/{workspace_id}/files/rename")
async def rename_file_or_directory(
    workspace_id: str,
    data: RenameFileRequest,
    file_service: Storage = Depends(get_workspace_file_service),
):
    """重命名文件或目录

    Args:
        workspace_id: 工作区ID
        data: 包含旧路径和新路径的请求数据
        file_service: 文件服务依赖

    Returns:
        重命名结果

    """
    # 获取工作区根路径
    workspace_path = Path(file_service.root_dir)

    # 构建完整路径
    old_path = workspace_path / data.old_path
    new_path = workspace_path / data.new_path

    # Fast Fail: 检查旧路径是否存在
    _validate_path_exists(old_path, f"Source path not found: {data.old_path}")

    # Fast Fail: 检查路径是否在工作区内（防止路径遍历攻击）
    _validate_path_safety(workspace_path, old_path)
    _validate_path_safety(workspace_path, new_path)

    # Fast Fail: 检查新路径是否已存在
    _validate_path_not_exists(new_path, f"Destination path already exists: {data.new_path}")

    try:
        # 重命名文件或目录
        old_path.rename(new_path)
        logger.info(f"Renamed: {old_path} -> {new_path}")

        return {
            "success": True,
            "message": f"{'Directory' if old_path.is_dir() else 'File'} renamed successfully",
            "old_path": data.old_path,
            "new_path": data.new_path,
        }

    except PermissionError as e:
        logger.error(f"重命名文件失败 (权限错误): {e}", exc_info=True)
        raise HTTPException(status_code=403, detail=f"Permission denied: {e!s}")
    except OSError as e:
        logger.error(f"重命名文件失败 (文件系统错误): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"File system error: {e!s}")
    except Exception as e:
        logger.error(f"重命名文件失败 (未知错误): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to rename file: {e!s}")
