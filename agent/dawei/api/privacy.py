# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""隐私配置 API

提供隐私配置的读取和更新接口：
- 配置存储在 ~/.dawei/privacy/privacy_config.json
- 支持多工作区共享同一隐私配置
"""

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from dawei.config import get_workspaces_root

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/privacy", tags=["Privacy Configuration"])


# ============================================================================
# 数据模型
# ============================================================================


class PrivacyConfig(BaseModel):
    """隐私配置数据模型"""

    enabled: bool = Field(True, description="是否启用隐私保护")
    retention_days: int = Field(30, description="数据保留天数", ge=1, le=365)
    sampling_rate: float = Field(1.0, description="采样率 (0.0-1.0)", ge=0.0, le=1.0)
    anonymize_enabled: bool = Field(True, description="是否启用数据匿名化")


class PrivacyConfigResponse(BaseModel):
    """隐私配置响应"""

    success: bool
    config: PrivacyConfig | None = None
    message: str | None = None


# ============================================================================
# 辅助函数
# ============================================================================


def get_privacy_config_path() -> Path:
    """获取隐私配置文件路径"""
    dawei_home = Path(get_workspaces_root()).expanduser()
    privacy_dir = dawei_home / "privacy"
    privacy_dir.mkdir(parents=True, exist_ok=True)
    return privacy_dir / "privacy_config.json"


def load_privacy_config() -> PrivacyConfig:
    """加载隐私配置

    Returns:
        PrivacyConfig: 隐私配置对象
    """
    config_path = get_privacy_config_path()

    if config_path.exists():
        try:
            with config_path.open(encoding="utf-8") as f:
                data = json.load(f)
            return PrivacyConfig(**data)
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(f"Failed to load privacy config, using defaults: {e}")
            return PrivacyConfig()
    else:
        # 配置文件不存在，创建默认配置
        default_config = PrivacyConfig()
        save_privacy_config(default_config)
        return default_config


def save_privacy_config(config: PrivacyConfig) -> None:
    """保存隐私配置

    Args:
        config: 隐私配置对象

    Raises:
        OSError: 文件写入失败
    """
    config_path = get_privacy_config_path()

    try:
        with config_path.open("w", encoding="utf-8") as f:
            json.dump(config.model_dump(), f, indent=2, ensure_ascii=False)
        logger.info(f"Privacy config saved to {config_path}")
    except OSError as e:
        logger.error(f"Failed to save privacy config: {e}")
        raise


# ============================================================================
# API 端点
# ============================================================================


@router.get("/config", response_model=PrivacyConfigResponse)
async def get_privacy_settings() -> PrivacyConfigResponse:
    """获取隐私配置"""
    try:
        config = load_privacy_config()
        return PrivacyConfigResponse(success=True, config=config)
    except Exception as e:
        logger.error(f"Failed to get privacy config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to load privacy config: {str(e)}")


@router.put("/config", response_model=PrivacyConfigResponse)
async def update_privacy_settings(config: PrivacyConfig) -> PrivacyConfigResponse:
    """更新隐私配置"""
    try:
        save_privacy_config(config)
        return PrivacyConfigResponse(
            success=True, config=config, message="Privacy configuration updated successfully"
        )
    except OSError as e:
        logger.error(f"Failed to save privacy config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to save privacy config: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error updating privacy config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
