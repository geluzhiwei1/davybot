# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""工作区级安全配置 API"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Workspace Security"])


class SecuritySettingsResponse(BaseModel):
    """安全配置响应"""

    success: bool
    settings: dict | None = None
    message: str | None = None


@router.get("")
async def get_workspace_security_settings(
    workspace_id: str,
) -> SecuritySettingsResponse:
    """获取工作区安全配置"""
    try:
        from dawei.workspace.workspace_manager import workspace_manager

        workspace = await workspace_manager.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Workspace {workspace_id} not found")

        # 确保 workspace 已初始化（加载 workspace_settings）
        if not workspace._initialized:
            await workspace.initialize()

        # 从 WorkspaceSettings 中获取 security 字段
        security_settings = {}
        if workspace.workspace_settings and hasattr(workspace.workspace_settings, "security"):
            security_settings = workspace.workspace_settings.security
        elif workspace.workspace_settings:
            # 如果 security 字段不存在，返回空字典
            security_settings = {}

        return SecuritySettingsResponse(success=True, settings=security_settings, message="Workspace security settings retrieved successfully")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to load workspace security settings: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.put("")
async def update_workspace_security_settings(
    workspace_id: str,
    settings_data: dict,
) -> SecuritySettingsResponse:
    """更新工作区安全配置"""
    try:
        from dawei.workspace.workspace_manager import workspace_manager

        workspace = await workspace_manager.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Workspace {workspace_id} not found")

        # 确保 workspace 已初始化（加载 workspace_settings）
        if not workspace._initialized:
            await workspace.initialize()

        # 更新安全配置
        if workspace.workspace_settings:
            workspace.workspace_settings.security = settings_data

            # 保存到持久化存储
            await workspace._save_settings({"security"})

            # 同步更新 SecurityManager 内存缓存
            from dawei.core.security_manager import security_manager
            security_manager.update_workspace_security(settings_data)

        return SecuritySettingsResponse(success=True, settings=settings_data, message="Workspace security settings updated successfully")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update workspace security settings: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/reset")
async def reset_workspace_security_settings(
    workspace_id: str,
) -> SecuritySettingsResponse:
    """重置工作区安全配置为默认值（空字典，表示使用用户级配置）"""
    try:
        from dawei.workspace.workspace_manager import workspace_manager

        workspace = await workspace_manager.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Workspace {workspace_id} not found")

        # 确保 workspace 已初始化（加载 workspace_settings）
        if not workspace._initialized:
            await workspace.initialize()

        # 重置为空配置（将使用用户级配置）
        empty_settings = {}
        if workspace.workspace_settings:
            workspace.workspace_settings.security = empty_settings
            # 保存到持久化存储
            await workspace._save_settings({"security"})

            # 同步更新 SecurityManager 内存缓存
            from dawei.core.security_manager import security_manager
            security_manager.update_workspace_security(empty_settings)

        return SecuritySettingsResponse(success=True, settings=empty_settings, message="Workspace security settings reset (will use user-level settings)")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to reset workspace security settings: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
