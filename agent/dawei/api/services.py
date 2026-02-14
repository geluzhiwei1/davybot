# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

from dawei.storage.storage import Storage
from dawei.storage.storage_provider import StorageProvider
from dawei.workspace import workspace_manager


def get_workspace_file_service(workspace_id: str) -> Storage:
    """获取特定工作区的文件服务实例"""
    workspace = workspace_manager.get_workspace_by_id(workspace_id)
    if not workspace:
        raise ValueError(f"Workspace with id {workspace_id} not found")

    workspace_path = workspace.get("path")
    if not workspace_path:
        raise ValueError(f"Workspace with id {workspace_id} has no path configured")

    return StorageProvider.get_local_filesystem_storage(root_dir=workspace_path)
