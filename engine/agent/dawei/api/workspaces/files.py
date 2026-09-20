# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""File Operations API Routes

文件系统操作和目录树管理
"""

import logging
import shutil
from pathlib import Path
from typing import List, Dict, Any

from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

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


def _build_file_tree(files: List[Dict[str, Any]], base_path: str = "") -> List[FileTreeItem]:
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
    def _tree_to_list(tree_dict: dict, level: int = 0) -> List[FileTreeItem]:
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

    # Fast Fail: 检查路径是否在工作区内（防止路径遍历攻击）
    _validate_path_safety(workspace_path, full_path)

    # Fast Fail: 检查路径是否已存在
    _validate_path_not_exists(full_path, f"Path already exists: {data.path}")

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


@router.get("/{workspace_id}/file-tree")
async def get_workspace_file_tree(
    workspace_id: str,
    path: str = Query(".", description="要列出的路径"),
    include_hidden: bool = Query(True, description="是否包含隐藏文件"),
    max_depth: int = Query(5, description="递归最大深度"),
    file_service: Storage = Depends(get_workspace_file_service),
):
    """获取工作区的文件树结构"""
    files = await file_service.list_directory(
        path=path,
        recursive=True,
        include_hidden=include_hidden,
        max_depth=max_depth,
    )

    # Fast Fail: 验证文件列表数据
    if not isinstance(files, list):
        raise HTTPException(status_code=500, detail="Invalid file data format received from storage")

    # 构建扁平化的文件树列表（兼容前端现有格式）
    flat_tree = []
    for file in files:
        # Fast Fail: 验证单个文件数据
        if not isinstance(file, dict) or "path" not in file or "name" not in file:
            raise HTTPException(status_code=500, detail=f"Invalid file data structure: {file}")

        # 排除 .dawei 临时目录及其所有内容（第二层防护）
        path_parts = file["path"].split("/")
        if ".dawei" in path_parts:
            continue

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

    # 确保目标目录存在
    target_dir.mkdir(parents=True, exist_ok=True)

    # 构建文件路径（支持文件夹上传时的相对路径）
    file_path = target_dir / file.filename

    # 验证最终路径安全性，防止路径遍历攻击
    _validate_path_safety(workspace_path, file_path)

    # 确保文件所在目录存在（file.filename 可能包含子路径）
    file_path.parent.mkdir(parents=True, exist_ok=True)

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


class UploadByPathRequest(BaseModel):
    """Request body for path-based file import (desktop/sidecar only)."""

    source_path: str = Field(..., description="Absolute local file path to import")
    parent_path: str = Field("", description="Destination directory within workspace")


@router.post("/{workspace_id}/files/upload-by-path")
async def upload_file_by_path(
    workspace_id: str,
    req: UploadByPathRequest,
    file_service: Storage = Depends(get_workspace_file_service),
):
    """Import a local file by its absolute path (desktop/sidecar only).

    Copies the file from ``source_path`` directly into the workspace directory,
    bypassing HTTP multipart upload. Only called by the desktop (Tauri) frontend
    where the sidecar has direct filesystem access — the file never traverses
    the network stack.
    """
    workspace_path = Path(file_service.root_dir)
    source = Path(req.source_path).resolve()

    # Fast Fail: validate source
    if not source.exists():
        raise HTTPException(status_code=404, detail=f"Source file not found: {source}")
    if not source.is_file():
        raise HTTPException(status_code=400, detail=f"Source path is not a regular file: {source}")

    # Build target path
    target_dir = workspace_path / req.parent_path if req.parent_path else workspace_path
    _validate_path_safety(workspace_path, target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    file_path = target_dir / source.name
    _validate_path_safety(workspace_path, file_path)

    if file_path.exists():
        logger.warning(f"File already exists, will overwrite: {file_path}")

    shutil.copy2(source, file_path)
    logger.info(f"File imported by path: {source} -> {file_path}")

    return {
        "success": True,
        "message": "File imported successfully",
        "filename": source.name,
        "path": str(file_path.relative_to(workspace_path)),
    }


@router.post("/{workspace_id}/files/upload-folder")
async def upload_folder(
    workspace_id: str,
    files: List[UploadFile],
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

        except Exception as e:
            # Non-critical operation: log and continue with next file
            error_msg = str(e)
            errors.append(f"{file.filename}: {error_msg}")
            logger.warning(f"{file.filename}: {error_msg}")

    logger.info(
        f"Folder upload completed: {len(uploaded_files)} files uploaded, {len(errors)} errors",
    )

    return {
        "success": len(errors) == 0,
        "message": f"Uploaded {len(uploaded_files)} files" + (f" with {len(errors)} errors" if errors else ""),
        "uploaded_files": uploaded_files,
        "errors": errors,
    }


class DeleteFileRequest(BaseModel):
    """删除文件或目录请求"""

    path: str = Field(..., description="要删除的文件或目录路径")


@router.delete("/{workspace_id}/files/delete")
async def delete_file_or_directory(
    workspace_id: str,
    request: DeleteFileRequest,
    file_service: Storage = Depends(get_workspace_file_service),
):
    """删除文件或目录

    Args:
        workspace_id: 工作区ID
        request: 包含要删除路径的请求体
        file_service: 文件服务依赖

    Returns:
        删除结果

    """
    # 获取工作区根路径
    workspace_path = Path(file_service.root_dir)

    # 构建完整路径
    full_path = workspace_path / request.path

    # Fast Fail: 检查路径是否存在
    _validate_path_exists(full_path, f"Path not found: {request.path}")

    # Fast Fail: 检查路径是否在工作区内（防止路径遍历攻击）
    _validate_path_safety(workspace_path, full_path)

    # 删除文件或目录
    if full_path.is_file():
        full_path.unlink()
        logger.info(f"Deleted file: {full_path}")
    elif full_path.is_dir():
        shutil.rmtree(full_path)
        logger.info(f"Deleted directory: {full_path}")
    else:
        raise HTTPException(status_code=400, detail=f"Invalid path type: {request.path}")

    return {
        "success": True,
        "message": f"{'Directory' if full_path.is_dir() else 'File'} deleted successfully",
        "path": request.path,
    }


class CopyFileRequest(BaseModel):
    """复制文件或目录请求"""

    source_path: str
    destination_path: str


class MoveFileRequest(BaseModel):
    """移动文件或目录请求"""

    source_path: str = Field(alias="sourcePath", description="源文件路径")
    target_path: str = Field(alias="targetPath", description="目标文件路径")
    overwrite: bool = Field(default=False, description="是否覆盖已存在的文件")

    model_config = {"populate_by_name": True, "json_schema_extra": {"example": {"sourcePath": "path/to/file.txt", "targetPath": "new/location/file.txt", "overwrite": False}}}


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


@router.post("/{workspace_id}/files/move")
async def move_file_or_directory(
    workspace_id: str,
    data: MoveFileRequest,
    file_service: Storage = Depends(get_workspace_file_service),
):
    """移动文件或目录

    Args:
        workspace_id: 工作区ID
        data: 包含源路径、目标路径和覆盖标志的请求数据
        file_service: 文件服务依赖

    Returns:
        移动结果

    """
    # 获取工作区根路径
    workspace_path = Path(file_service.root_dir)

    # 构建完整路径
    source_path = workspace_path / data.source_path
    target_path = workspace_path / data.target_path

    # Fast Fail: 检查源路径是否存在
    _validate_path_exists(source_path, f"Source path not found: {data.source_path}")

    # Fast Fail: 检查路径是否在工作区内（防止路径遍历攻击）
    _validate_path_safety(workspace_path, source_path)
    _validate_path_safety(workspace_path, target_path)

    # 检查目标路径是否已存在
    if target_path.exists():
        if data.overwrite:
            # 删除现有目标
            if target_path.is_file():
                target_path.unlink()
            elif target_path.is_dir():
                shutil.rmtree(target_path)
            logger.info(f"Removed existing target for overwrite: {target_path}")
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Target path already exists: {data.target_path}. Use overwrite=true to replace.",
            )

    # 确保目标目录存在
    target_path.parent.mkdir(parents=True, exist_ok=True)

    # 移动文件或目录
    try:
        shutil.move(str(source_path), str(target_path))
        logger.info(f"Moved: {source_path} -> {target_path}")
    except Exception as e:
        logger.error(f"Failed to move {source_path} to {target_path}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to move file: {str(e)}",
        ) from e

    return {
        "success": True,
        "message": f"{'Directory' if source_path.is_dir() else 'File'} moved successfully",
        "sourcePath": data.source_path,
        "targetPath": data.target_path,
        "size": target_path.stat().st_size if target_path.is_file() else 0,
        "movedAt": Path(target_path).stat().st_mtime if target_path.exists() else None,
    }


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

    # 重命名文件或目录
    old_path.rename(new_path)
    logger.info(f"Renamed: {old_path} -> {new_path}")

    return {
        "success": True,
        "message": f"{'Directory' if old_path.is_dir() else 'File'} renamed successfully",
        "old_path": data.old_path,
        "new_path": data.new_path,
    }


@router.get("/{workspace_id}/files/info")
async def get_file_info(
    workspace_id: str,
    path: str = Query(..., description="文件或目录路径"),
    file_service: Storage = Depends(get_workspace_file_service),
):
    """获取文件或目录的元信息（大小、时间、权限等）"""
    import mimetypes
    import os
    from datetime import datetime, timezone

    workspace_path = Path(file_service.root_dir)
    full_path = workspace_path / path

    _validate_path_exists(full_path, f"Path not found: {path}")
    _validate_path_safety(workspace_path, full_path)

    stat = full_path.stat()
    is_dir = full_path.is_dir()
    mime_type = None if is_dir else (mimetypes.guess_type(str(full_path))[0])
    language = None
    if not is_dir:
        ext_map = {
            ".py": "python", ".js": "javascript", ".ts": "typescript", ".tsx": "tsx",
            ".jsx": "jsx", ".json": "json", ".yaml": "yaml", ".yml": "yaml",
            ".md": "markdown", ".html": "html", ".css": "css", ".sh": "shell",
            ".rs": "rust", ".go": "go", ".sql": "sql",
        }
        language = ext_map.get(full_path.suffix.lower())

    def _iso(ts: float) -> str:
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()

    return {
        "success": True,
        "info": {
            "path": path,
            "name": full_path.name,
            "type": "directory" if is_dir else "file",
            "size": 0 if is_dir else stat.st_size,
            "created_at": _iso(stat.st_ctime),
            "modified_at": _iso(stat.st_mtime),
            "permissions": {
                "readable": os.access(full_path, os.R_OK),
                "writable": os.access(full_path, os.W_OK),
                "executable": os.access(full_path, os.X_OK),
            },
            "mime_type": mime_type,
            "language": language,
        },
    }


@router.get("/{workspace_id}/files/download")
async def download_file_or_directory(
    workspace_id: str,
    path: str = Query(..., description="要下载的文件或目录路径"),
    file_service: Storage = Depends(get_workspace_file_service),
):
    """下载文件或目录

    Args:
        workspace_id: 工作区ID
        path: 要下载的文件或目录路径
        file_service: 文件服务依赖

    Returns:
        文件或目录（打包成zip）的下载响应

    """
    import io
    import zipfile

    from fastapi.responses import FileResponse, StreamingResponse

    # 获取工作区根路径
    workspace_path = Path(file_service.root_dir)

    # 构建完整路径
    full_path = workspace_path / path

    # Fast Fail: 检查路径是否存在
    _validate_path_exists(full_path, f"Path not found: {path}")

    # Fast Fail: 检查路径是否在工作区内（防止路径遍历攻击）
    _validate_path_safety(workspace_path, full_path)

    if full_path.is_file():
        # 下载单个文件
        logger.info(f"Downloading file: {full_path}")

        # 获取文件名
        filename = full_path.name

        # 返回文件响应
        return FileResponse(path=str(full_path), filename=filename, media_type="application/octet-stream")

    if full_path.is_dir():
        # 下载目录（打包成zip）
        logger.info(f"Downloading directory as zip: {full_path}")

        # 创建zip文件在内存中
        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for file_path in full_path.rglob("*"):
                if file_path.is_file():
                    # 计算相对路径
                    relative_path = file_path.relative_to(full_path)
                    # 添加到zip
                    zip_file.write(file_path, relative_path)

        zip_buffer.seek(0)

        # 生成zip文件名
        dir_name = full_path.name
        zip_filename = f"{dir_name}.zip"

        # 返回zip文件
        return StreamingResponse(io.BytesIO(zip_buffer.getvalue()), media_type="application/zip", headers={"Content-Disposition": f"attachment; filename={zip_filename}"})
    raise HTTPException(status_code=400, detail=f"Invalid path type: {path}")


# --- 老格式转换 (.doc/.xls → .docx/.xlsx) ---

# 需要转换的老格式 → 目标格式
_LEGACY_CONVERT_MAP: Dict[str, str] = {
    ".doc": "docx",
    ".xls": "xlsx",
    ".ppt": "pptx",
    ".odt": "docx",
    ".ods": "xlsx",
    ".rtf": "docx",
}


@router.get("/{workspace_id}/files/convert")
async def convert_legacy_document(
    workspace_id: str,
    path: str = Query(..., description="要转换的文件路径"),
    file_service: Storage = Depends(get_workspace_file_service),
):
    """用 LibreOffice headless 将老格式文档转换为 OOXML 格式

    .doc → .docx, .xls → .xlsx, .ppt → .pptx 等
    """
    import tempfile

    from fastapi.responses import FileResponse

    workspace_path = Path(file_service.root_dir)
    full_path = workspace_path / path

    _validate_path_exists(full_path, f"Path not found: {path}")
    _validate_path_safety(workspace_path, full_path)

    ext = full_path.suffix.lower()
    if ext not in _LEGACY_CONVERT_MAP:
        raise HTTPException(status_code=400, detail=f"Unsupported format for conversion: {ext}")

    target_format = _LEGACY_CONVERT_MAP[ext]
    tmpdir = tempfile.mkdtemp(prefix="lo_convert_")

    try:
        import subprocess

        result = subprocess.run(
            [
                "libreoffice", "--headless", "--norestore", "--nologo",
                "--convert-to", target_format,
                "--outdir", tmpdir, str(full_path),
            ],
            check=True,
            timeout=60,
            capture_output=True,
            text=True,
        )
        logger.debug(f"LibreOffice stdout: {result.stdout}")
        converted_path = Path(tmpdir) / (full_path.stem + "." + target_format)
        if not converted_path.exists():
            raise HTTPException(
                status_code=500,
                detail=f"Conversion failed: {result.stderr or 'unknown error'}",
            )
        logger.info(f"Converted {full_path.name} → {target_format} ({converted_path.stat().st_size} bytes)")
        return FileResponse(
            path=str(converted_path),
            filename=converted_path.name,
            media_type="application/octet-stream",
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="LibreOffice conversion timed out (>60s)") from None
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"LibreOffice error: {e.stderr or str(e)}") from e
    finally:
        # 延迟清理：FileResponse 读取完文件后再删
        import threading

        def _cleanup():
            import time

            time.sleep(5)
            shutil.rmtree(tmpdir, ignore_errors=True)

        threading.Thread(target=_cleanup, daemon=True).start()
