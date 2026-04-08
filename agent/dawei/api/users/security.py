# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""用户级安全配置 API"""

import json
import logging
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, status
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


async def get_current_user_id() -> str:
    """获取当前用户ID（简化实现）

    实际应该从 JWT token 或 session 中获取
    """
    # TODO: 实现真实的用户认证
    return "default_user"


def _get_config_file(user_id: str) -> Path:
    """获取用户安全配置文件路径"""
    return get_dawei_home() / "configs" / "security.json"


@router.get("", response_model=SecuritySettingsResponse)
async def get_user_security_settings(
    current_user: str = Depends(get_current_user_id),
) -> SecuritySettingsResponse:
    """获取用户安全配置"""
    try:
        settings = security_manager.get_user_settings()
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

        # 更新 SecurityManager 内存中的配置
        security_manager.update_user_settings(settings)

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

    # 更新内存
    security_manager.update_user_settings(default_settings)

    return SecuritySettingsResponse(
        success=True,
        settings=default_settings.to_dict(),
        message="User security settings reset to defaults",
    )
