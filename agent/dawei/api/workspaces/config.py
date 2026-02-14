# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Workspace Configuration API Routes

工作区配置管理API - 处理工作区级别的配置设置
"""

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from dawei.workspace import workspace_manager
from dawei.workspace.models import WorkspaceConfig  # ✨ 新增：导入统一配置模型
from dawei.workspace.user_workspace import UserWorkspace

logger = logging.getLogger(__name__)

# 创建路由器
router = APIRouter(tags=["workspaces-config"])


# --- Pydantic 模型 ---


class WorkspaceConfigUpdate(BaseModel):
    """更新工作区配置的请求模型"""

    agent: dict[str, Any] | None = None
    checkpoint: dict[str, Any] | None = None
    compression: dict[str, Any] | None = None
    memory: dict[str, Any] | None = None
    skills: dict[str, Any] | None = None
    tools: dict[str, Any] | None = None
    logging: dict[str, Any] | None = None
    monitoring: dict[str, Any] | None = None
    analytics: dict[str, Any] | None = None


class WorkspaceConfigResponse(BaseModel):
    """工作区配置响应模型"""

    success: bool
    config: dict[str, Any]
    message: str | None = None


# --- 默认配置 ---


DEFAULT_CONFIG = {
    "agent": {
        "mode": "orchestrator",
        "plan_mode_confirm_required": True,
        "enable_auto_mode_switch": False,
        "auto_approve_tools": True,
        "max_concurrent_subtasks": 3,
    },
    "checkpoint": {
        "checkpoint_interval": 300,
        "max_checkpoints": 10,
        "enable_compression": True,
        "auto_create_enabled": True,
        "min_interval_minutes": 5,
        "max_checkpoints_per_task": 50,
        "validation_enabled": True,
    },
    "compression": {
        "enabled": False,
        "preserve_recent": 20,
        "max_tokens": 100000,
        "compression_threshold": 0.5,
        "aggressive_threshold": 0.9,
        "page_size": 20,
        "max_active_pages": 5,
        "memory_integration_enabled": True,
        "auto_extract_memories": True,
        "auto_store_memories": True,
    },
    "memory": {
        "enabled": True,
        "virtual_page_size": 2000,
        "max_active_pages": 5,
        "default_energy": 1.0,
        "energy_decay_rate": 0.1,
        "min_energy_threshold": 0.2,
    },
    "skills": {
        "enabled": True,
        "auto_discovery": True,
    },
    "tools": {
        "builtin_tools_enabled": True,
        "system_tools_enabled": True,
        "user_tools_enabled": True,
        "workspace_tools_enabled": True,
        "default_timeout": 60,
        "max_concurrent_executions": 3,
    },
    "logging": {
        "level": "INFO",
        "dir": "~/.dawei/logs",
        "max_file_size": 10,
        "backup_count": 5,
        "console_output": True,
        "file_output": True,
        "enable_performance_logging": True,
        "sanitize_sensitive_data": True,
    },
    "monitoring": {
        "prometheus_enabled": True,
        "prometheus_port": 9090,
    },
    "analytics": {
        "enabled": True,
        "retention_days": 90,
        "sampling_rate": 1.0,
        "anonymize_enabled": True,
    },
}


# --- 辅助函数 ---


def get_user_workspace(workspace_id: str) -> UserWorkspace:
    """Dependency to get a UserWorkspace instance."""
    workspace_info = workspace_manager.get_workspace_by_id(workspace_id)
    if not workspace_info:
        raise HTTPException(status_code=404, detail=f"Workspace with ID {workspace_id} not found")

    workspace_path = workspace_info.get("path")
    if not workspace_path:
        raise HTTPException(
            status_code=404,
            detail=f"Workspace path not found for ID {workspace_id}",
        )

    return UserWorkspace(workspace_path=workspace_path)


def get_config_file(workspace: UserWorkspace) -> Path:
    """获取工作区配置文件路径"""
    return workspace.workspace_path / ".dawei" / "config.json"


async def load_workspace_config(workspace: UserWorkspace) -> WorkspaceConfig:
    """加载工作区配置，如果不存在则返回默认配置（使用 Pydantic 模型）"""
    config_file = get_config_file(workspace)

    if not config_file.exists():
        logger.info(f"Config file not found, using defaults: {config_file}")
        return WorkspaceConfig()

    try:
        with Path(config_file).open(encoding="utf-8") as f:
            config_dict = json.load(f)

        # 使用 WorkspaceConfig.from_dict 合并默认值
        return WorkspaceConfig.from_dict(config_dict)
    except (OSError, json.JSONDecodeError) as e:
        logger.error(f"Failed to load config file: {e}", exc_info=True)
        return WorkspaceConfig()


async def save_workspace_config(workspace: UserWorkspace, config: WorkspaceConfig) -> None:
    """保存工作区配置（使用 Pydantic 模型）"""
    config_file = get_config_file(workspace)

    # 确保配置目录存在
    config_file.parent.mkdir(parents=True, exist_ok=True)

    # 使用 WorkspaceConfig.model_dump_custom() 序列化
    config_dict = config.model_dump_custom()

    # 写入配置文件
    with config_file.open("w", encoding="utf-8") as f:
        json.dump(config_dict, f, indent=2, ensure_ascii=False)

    logger.info(f"Workspace config saved: {config_file}")


# --- 配置管理路由 ---


@router.get("/{workspace_id}/config")
async def get_workspace_config(workspace_id: str) -> WorkspaceConfigResponse:
    """获取工作区配置"""
    try:
        workspace = get_user_workspace(workspace_id)

        # 确保工作区已初始化
        if not workspace.is_initialized():
            await workspace.initialize()

        config = await load_workspace_config(workspace)

        # 转换为字典返回（兼容前端）
        return WorkspaceConfigResponse(
            success=True,
            config=config.model_dump_custom(),
            message=None,
        )

    except (OSError, json.JSONDecodeError, AttributeError, KeyError) as e:
        logger.error(f"Failed to get workspace config: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get workspace config: {e!s}",
        )


@router.put("/{workspace_id}/config")
async def update_workspace_config(
    workspace_id: str,
    config_update: WorkspaceConfigUpdate,
) -> WorkspaceConfigResponse:
    """更新工作区配置"""
    try:
        workspace = get_user_workspace(workspace_id)

        # 确保工作区已初始化
        if not workspace.is_initialized():
            await workspace.initialize()

        # 加载当前配置
        current_config = await load_workspace_config(workspace)

        # 更新配置（只更新提供的字段）
        update_dict = config_update.model_dump(exclude_unset=True)
        for key, value in update_dict.items():
            if value is not None and isinstance(value, dict):
                # 合并配置节的字段
                current_section = getattr(current_config, key)
                # 更新配置节（保留未指定的字段）
                for sub_key, sub_value in value.items():
                    setattr(current_section, sub_key, sub_value)

        # 保存配置
        await save_workspace_config(workspace, current_config)

        logger.info(f"Workspace config updated for workspace {workspace_id}")

        return WorkspaceConfigResponse(
            success=True,
            config=current_config.model_dump_custom(),
            message="Workspace configuration updated successfully",
        )

    except (
        OSError,
        json.JSONDecodeError,
        AttributeError,
        KeyError,
        ValueError,
        TypeError,
    ) as e:
        logger.error(f"Failed to update workspace config: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update workspace config: {e!s}",
        )


@router.post("/{workspace_id}/config/reset")
async def reset_workspace_config(workspace_id: str) -> WorkspaceConfigResponse:
    """重置工作区配置为默认值"""
    try:
        workspace = get_user_workspace(workspace_id)

        # 确保工作区已初始化
        if not workspace.is_initialized():
            await workspace.initialize()

        # 使用默认配置（WorkspaceConfig 默认值）
        default_config = WorkspaceConfig()

        # 保存默认配置
        await save_workspace_config(workspace, default_config)

        logger.info(f"Workspace config reset to defaults for workspace {workspace_id}")

        return WorkspaceConfigResponse(
            success=True,
            config=default_config.model_dump_custom(),
            message="Workspace configuration reset to defaults",
        )

    except (OSError, json.JSONDecodeError, AttributeError, KeyError) as e:
        logger.error(f"Failed to reset workspace config: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reset workspace config: {e!s}",
        )
