# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""用户级安全配置 API"""

import json
import logging
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from dawei.config import get_dawei_home
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


async def load_user_security_settings(user_id: str) -> UserSecuritySettings:
    """从存储加载用户安全配置

    Args:
        user_id: 用户ID

    Returns:
        UserSecuritySettings: 用户安全配置
    """
    dawei_home = get_dawei_home()
    config_dir = dawei_home / "users" / user_id
    config_file = config_dir / "security_settings.json"

    if config_file.exists():
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return UserSecuritySettings.from_dict(data)
        except Exception as e:
            logger.error(f"Failed to load user security settings: {e}")
            # 返回默认配置
            return UserSecuritySettings()

    # 返回默认配置
    return UserSecuritySettings()


async def save_user_security_settings(
    user_id: str,
    settings: UserSecuritySettings
) -> None:
    """保存用户安全配置到存储

    Args:
        user_id: 用户ID
        settings: 安全配置
    """
    dawei_home = get_dawei_home()
    config_dir = dawei_home / "users" / user_id
    config_dir.mkdir(parents=True, exist_ok=True)

    config_file = config_dir / "security_settings.json"

    with open(config_file, 'w', encoding='utf-8') as f:
        json.dump(settings.to_dict(), f, indent=2, ensure_ascii=False)


@router.get("", response_model=SecuritySettingsResponse)
async def get_user_security_settings(
    current_user: str = Depends(get_current_user_id)
) -> SecuritySettingsResponse:
    """获取用户安全配置"""
    try:
        settings = await load_user_security_settings(current_user)
        return SecuritySettingsResponse(
            success=True,
            settings=settings.to_dict(),
            message="User security settings retrieved successfully"
        )
    except Exception as e:
        logger.error(f"Failed to load user security settings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.put("", response_model=SecuritySettingsResponse)
async def update_user_security_settings(
    settings_data: dict,
    current_user: str = Depends(get_current_user_id)
) -> SecuritySettingsResponse:
    """更新用户安全配置"""
    try:
        # 创建配置对象（使用 from_dict 进行验证）
        settings = UserSecuritySettings.from_dict(settings_data)

        # 保存到用户配置存储
        await save_user_security_settings(current_user, settings)

        return SecuritySettingsResponse(
            success=True,
            settings=settings.to_dict(),
            message="User security settings updated successfully"
        )
    except Exception as e:
        logger.error(f"Failed to update user security settings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/reset", response_model=SecuritySettingsResponse)
async def reset_user_security_settings(
    current_user: str = Depends(get_current_user_id)
) -> SecuritySettingsResponse:
    """重置用户安全配置为默认值"""
    # 创建默认配置
    default_settings = UserSecuritySettings()

    # 保存默认配置
    await save_user_security_settings(current_user, default_settings)

    return SecuritySettingsResponse(
        success=True,
        settings=default_settings.to_dict(),
        message="User security settings reset to defaults"
    )

