# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""用户级安全配置 API"""

import json
import logging
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from dawei import get_dawei_home
from dawei.core.security_manager import security_manager
from dawei.workspace.user_security_settings import UserSecuritySettings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/me/security", tags=["User Security"])


class SecuritySettingsResponse(BaseModel):
    """安全配置响应"""

    success: bool
    settings: dict | None = None
    message: str | None = None


async def get_current_user_id(request: Request) -> str:
    """获取当前用户ID。

    F1 非破坏式认证：委托给 ``dawei.api.auth.get_authenticated_user_id``——
    server 模式取真实会话 user_id，local 模式回落 ``"default_user"``，不拒绝请求。
    保留此函数名以兼容现有 ``Depends(get_current_user_id)`` 调用点。
    """
    from dawei.api.auth import get_authenticated_user_id

    return await get_authenticated_user_id(request)


def _get_config_file(user_id: str) -> Path:
    """获取用户安全配置文件路径（按 user_id 分目录，不兼容旧 configs/security.json）"""
    safe_uid = "".join(c if c.isalnum() or c in "-_" else "_" for c in (user_id or "default_user"))
    return get_dawei_home() / "configs" / safe_uid / "security.json"


@router.get("", response_model=SecuritySettingsResponse)
async def get_user_security_settings(
    current_user: str = Depends(get_current_user_id),
) -> SecuritySettingsResponse:
    """获取用户安全配置"""
    try:
        settings = security_manager.get_user_settings(user_id=current_user)
        return SecuritySettingsResponse(
            success=True,
            settings=settings.to_dict(),
            message="User security settings retrieved successfully",
        )
    except Exception as e:
        logger.error(f"Failed to load user security settings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.put("", response_model=SecuritySettingsResponse)
async def update_user_security_settings(
    settings_data: dict,
    current_user: str = Depends(get_current_user_id),
) -> SecuritySettingsResponse:
    """更新用户安全配置"""
    try:
        # 创建配置对象（使用 from_dict 进行验证）
        settings = UserSecuritySettings.from_dict(settings_data)

        # 持久化到磁盘
        config_file = _get_config_file(current_user)
        config_file.parent.mkdir(parents=True, exist_ok=True)
        with config_file.open("w", encoding="utf-8") as f:
            json.dump(settings.to_dict(), f, indent=2, ensure_ascii=False)

        # 更新 SecurityManager 内存中的配置（按 user_id 分键）
        security_manager.update_user_settings(settings, user_id=current_user)

        # 审计：记录用户级策略变更（敏感值经 SecurityAuditor 脱敏）
        from dawei.core.security_auditor import security_auditor

        security_auditor.log(
            "security.policy.change",
            user_id=current_user,
            scope="user",
            settings=settings.to_dict(),
        )

        # 热重载：如果沙箱 Provider 配置变更，重置 Facade 使下次调用重新创建
        try:
            from dawei.sandbox.sandbox_facade import SandboxFacade

            SandboxFacade.reset()
            logger.info("[SECURITY_API] SandboxFacade 已重置 (用户沙箱配置变更)")
        except Exception as e:
            logger.warning("[SECURITY_API] SandboxFacade 重置失败: %s", e)

        return SecuritySettingsResponse(
            success=True,
            settings=settings.to_dict(),
            message="User security settings updated successfully",
        )
    except Exception as e:
        logger.error(f"Failed to update user security settings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.post("/reset", response_model=SecuritySettingsResponse)
async def reset_user_security_settings(
    current_user: str = Depends(get_current_user_id),
) -> SecuritySettingsResponse:
    """重置用户安全配置为默认值"""
    default_settings = UserSecuritySettings()

    # 持久化
    config_file = _get_config_file(current_user)
    config_file.parent.mkdir(parents=True, exist_ok=True)
    with config_file.open("w", encoding="utf-8") as f:
        json.dump(default_settings.to_dict(), f, indent=2, ensure_ascii=False)

    # 更新内存（按 user_id 分键）
    security_manager.update_user_settings(default_settings, user_id=current_user)

    return SecuritySettingsResponse(
        success=True,
        settings=default_settings.to_dict(),
        message="User security settings reset to defaults",
    )
