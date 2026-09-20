# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""工作区级安全配置 API"""

import logging
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ValidationError

from dawei.core.effective_policy import WorkspaceSecurityOverride

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
    request: Request,
) -> SecuritySettingsResponse:
    """更新工作区安全配置"""
    try:
        from dawei.api.auth import get_authenticated_user_id
        from dawei.core.security_auditor import security_auditor
        from dawei.workspace.workspace_manager import workspace_manager

        workspace = await workspace_manager.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Workspace {workspace_id} not found")

        # 确保 workspace 已初始化（加载 workspace_settings）
        if not workspace._initialized:
            await workspace.initialize()

        # schema 校验：override-or-inherit 下仅校验字段 类型/枚举/范围，
        # 不做"只能收紧"判断（工作区可任意方向覆盖）。非法 → 422。
        try:
            override = WorkspaceSecurityOverride.model_validate(settings_data)
        except ValidationError as ve:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"message": "Invalid workspace security override", "errors": ve.errors()},
            )
        # 规范化：丢弃未知键，仅保留显式设置的字段（camelCase）
        normalized = override.model_dump(exclude_none=True, by_alias=True)

        # 用户归属（无有效登录直接 401，无匿名身份）
        user_id = await get_authenticated_user_id(request)

        # 更新安全配置
        if workspace.workspace_settings:
            workspace.workspace_settings.security = normalized

            # 保存到持久化存储
            await workspace._save_settings({"security"})

            # 同步更新 SecurityManager 内存缓存（按 user_id + workspace_id 分键）
            from dawei.core.security_manager import security_manager
            security_manager.update_workspace_security(
                normalized, user_id=user_id, workspace_id=workspace.absolute_path
            )

        # 审计：记录工作区级策略变更（敏感值经 SecurityAuditor 脱敏）
        security_auditor.log(
            "security.policy.change",
            user_id=user_id,
            scope="workspace",
            workspace_id=workspace_id,
            settings=normalized,
        )

        return SecuritySettingsResponse(success=True, settings=normalized, message="Workspace security settings updated successfully")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update workspace security settings: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/reset")
async def reset_workspace_security_settings(
    workspace_id: str,
    request: Request,
) -> SecuritySettingsResponse:
    """重置工作区安全配置为默认值（空字典，表示使用用户级配置）"""
    try:
        from dawei.api.auth import get_authenticated_user_id
        from dawei.workspace.workspace_manager import workspace_manager

        workspace = await workspace_manager.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Workspace {workspace_id} not found")

        # 确保 workspace 已初始化（加载 workspace_settings）
        if not workspace._initialized:
            await workspace.initialize()

        user_id = await get_authenticated_user_id(request)

        # 重置为空配置（将使用用户级配置）
        empty_settings = {}
        if workspace.workspace_settings:
            workspace.workspace_settings.security = empty_settings
            # 保存到持久化存储
            await workspace._save_settings({"security"})

            # 同步更新 SecurityManager 内存缓存（按 user_id + workspace_id 分键）
            from dawei.core.security_manager import security_manager
            security_manager.update_workspace_security(
                empty_settings, user_id=user_id, workspace_id=workspace.absolute_path
            )

        return SecuritySettingsResponse(success=True, settings=empty_settings, message="Workspace security settings reset (will use user-level settings)")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to reset workspace security settings: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
