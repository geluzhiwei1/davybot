# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

from fastapi import HTTPException
from dawei.storage.storage import Storage
from dawei.storage.storage_provider import StorageProvider
from dawei.workspace import workspace_manager


def get_workspace_file_service(workspace_id: str) -> Storage:
    """获取特定工作区的文件服务实例

    Args:
        workspace_id: 工作区ID

    Returns:
        Storage: 文件存储服务实例

    Raises:
        HTTPException: 当工作区不存在时返回 404 错误
    """
    workspace = workspace_manager.get_workspace_by_id(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail=f"Workspace not found: {workspace_id}")

    workspace_path = workspace.get("path")
    if not workspace_path:
        raise HTTPException(status_code=400, detail=f"Workspace {workspace_id} has no path configured")

    return StorageProvider.get_local_filesystem_storage(root_dir=workspace_path)
