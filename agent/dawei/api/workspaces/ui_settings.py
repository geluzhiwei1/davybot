# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""UI Settings API Routes

UI环境设置和配置管理
"""

import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from dawei.workspace import workspace_manager
from dawei.workspace.user_workspace import UserWorkspace

logger = logging.getLogger(__name__)

# 创建路由器
router = APIRouter(tags=["workspaces-ui"])


# --- Pydantic 模型 ---


class UIEnvironmentsUpdate(BaseModel):
    """更新UI环境的请求模型"""

    environments: dict[str, dict[str, str]] | None = None
    activeEnvironment: str | None = None


class UIContextUpdate(BaseModel):
    """更新UI上下文的请求模型"""

    context: dict[str, Any] | None = None
    currentFile: str | None = None
    openFiles: list[str] | None = None


class SystemEnvironmentsUpdate(BaseModel):
    """更新系统环境的请求模型"""

    os_name: str | None = None
    os_version: str | None = None
    python_version: str | None = None
    cpu_count: int | None = None
    memory_total: int | None = None
    memory_available: int | None = None
    disk_total: int | None = None
    disk_available: int | None = None


# --- 辅助函数 ---


async def _ensure_workspace_initialized(workspace: UserWorkspace) -> None:
    """确保工作区已初始化"""
    if not workspace.is_initialized():
        await workspace.initialize()


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


# --- UI设置管理路由 ---


@router.get("/{workspace_id}/ui/environments")
@router.get("/{workspace_id}/ui-environments")
async def get_workspace_ui_environments(workspace_id: str):
    """获取工作区的UI环境配置"""
    try:
        workspace = get_user_workspace(workspace_id)
        await _ensure_workspace_initialized(workspace)

        # 从.ui_config.json读取UI配置
        ui_config_file = workspace.workspace_path / ".ui_config.json"

        if not ui_config_file.exists():
            return {"success": True, "environments": {}, "activeEnvironment": None}

        with ui_config_file.open(encoding="utf-8") as f:
            ui_config = json.load(f)

        return {
            "success": True,
            "environments": ui_config.get("environments", {}),
            "activeEnvironment": ui_config.get("activeEnvironment"),
        }

    except (OSError, json.JSONDecodeError, AttributeError, KeyError) as e:
        logger.error(f"Failed to get UI environments: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get UI environments: {e!s}",
        )


@router.put("/{workspace_id}/ui/environments")
@router.put("/{workspace_id}/ui-environments")
async def update_workspace_ui_environments(workspace_id: str, ui_update: UIEnvironmentsUpdate):
    """更新工作区的UI环境配置"""
    try:
        workspace = get_user_workspace(workspace_id)
        await _ensure_workspace_initialized(workspace)

        ui_config_file = workspace.workspace_path / ".ui_config.json"

        # 读取现有配置
        if ui_config_file.exists():
            with ui_config_file.open(encoding="utf-8") as f:
                ui_config = json.load(f)
        else:
            ui_config = {"environments": {}, "activeEnvironment": None}

        # 更新配置
        if ui_update.environments is not None:
            ui_config["environments"] = ui_update.environments

        if ui_update.activeEnvironment is not None:
            ui_config["activeEnvironment"] = ui_update.activeEnvironment

        # 写入文件
        with ui_config_file.open("w", encoding="utf-8") as f:
            json.dump(ui_config, f, indent=2, ensure_ascii=False)

        logger.info(f"Updated UI environments for workspace {workspace_id}")

        return {
            "success": True,
            "message": "UI environments updated successfully",
            "environments": ui_config.get("environments"),
            "activeEnvironment": ui_config.get("activeEnvironment"),
        }

    except (
        OSError,
        json.JSONDecodeError,
        AttributeError,
        KeyError,
        ValueError,
        TypeError,
    ) as e:
        logger.error(f"Failed to update UI environments: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update UI environments: {e!s}",
        )


@router.get("/{workspace_id}/ui/context")
@router.get("/{workspace_id}/ui-context")
async def get_workspace_ui_context(workspace_id: str):
    """获取工作区的UI上下文"""
    try:
        workspace = get_user_workspace(workspace_id)
        await _ensure_workspace_initialized(workspace)

        # 从.ui_state.json读取UI状态
        ui_state_file = workspace.workspace_path / ".ui_state.json"

        if not ui_state_file.exists():
            return {
                "success": True,
                "context": {},
                "currentFile": None,
                "openFiles": [],
            }

        with ui_state_file.open(encoding="utf-8") as f:
            ui_state = json.load(f)

        return {
            "success": True,
            "context": ui_state.get("context", {}),
            "currentFile": ui_state.get("currentFile"),
            "openFiles": ui_state.get("openFiles", []),
        }

    except (OSError, json.JSONDecodeError, AttributeError, KeyError) as e:
        logger.error(f"Failed to get UI context: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get UI context: {e!s}")


@router.put("/{workspace_id}/ui/context")
@router.put("/{workspace_id}/ui-context")
async def update_workspace_ui_context(workspace_id: str, context_update: UIContextUpdate):
    """更新工作区的UI上下文"""
    try:
        workspace = get_user_workspace(workspace_id)
        await _ensure_workspace_initialized(workspace)

        ui_state_file = workspace.workspace_path / ".ui_state.json"

        # 读取现有状态
        if ui_state_file.exists():
            with ui_state_file.open(encoding="utf-8") as f:
                ui_state = json.load(f)
        else:
            ui_state = {"context": {}, "currentFile": None, "openFiles": []}

        # 更新状态
        if context_update.context is not None:
            ui_state["context"] = context_update.context

        if context_update.currentFile is not None:
            ui_state["currentFile"] = context_update.currentFile

        if context_update.openFiles is not None:
            ui_state["openFiles"] = context_update.openFiles

        # 写入文件
        with ui_state_file.open("w", encoding="utf-8") as f:
            json.dump(ui_state, f, indent=2, ensure_ascii=False)

        logger.info(f"Updated UI context for workspace {workspace_id}")

        return {
            "success": True,
            "message": "UI context updated successfully",
            "context": ui_state.get("context"),
            "currentFile": ui_state.get("currentFile"),
            "openFiles": ui_state.get("openFiles"),
        }

    except (
        OSError,
        json.JSONDecodeError,
        AttributeError,
        KeyError,
        ValueError,
        TypeError,
    ) as e:
        logger.error(f"Failed to update UI context: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update UI context: {e!s}")


@router.get("/{workspace_id}/system/environments")
@router.get("/{workspace_id}/system-environments")
async def get_workspace_system_environments(workspace_id: str):
    """获取工作区的系统环境配置"""
    try:
        workspace = get_user_workspace(workspace_id)
        await _ensure_workspace_initialized(workspace)

        # 从 workspace.json 读取系统环境信息
        workspace_file = workspace.workspace_path / ".dawei" / "workspace.json"

        if not workspace_file.exists():
            return {
                "success": True,
                "system_environments": {
                    "os_name": "",
                    "os_version": "",
                    "python_version": "",
                    "cpu_count": 0,
                    "memory_total": 0,
                    "memory_available": 0,
                    "disk_total": 0,
                    "disk_available": 0,
                }
            }

        with workspace_file.open(encoding="utf-8") as f:
            workspace_config = json.load(f)

        system_envs = workspace_config.get("system_environments", {})
        return {
            "success": True,
            "system_environments": system_envs
        }

    except (OSError, json.JSONDecodeError, AttributeError, KeyError) as e:
        logger.error(f"Failed to get system environments: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get system environments: {e!s}",
        )


@router.put("/{workspace_id}/system/environments")
@router.put("/{workspace_id}/system-environments")
async def update_workspace_system_environments(
    workspace_id: str,
    system_update: SystemEnvironmentsUpdate
):
    """更新工作区的系统环境配置"""
    try:
        workspace = get_user_workspace(workspace_id)
        await _ensure_workspace_initialized(workspace)

        workspace_file = workspace.workspace_path / ".dawei" / "workspace.json"

        # 读取现有配置
        if workspace_file.exists():
            with workspace_file.open(encoding="utf-8") as f:
                workspace_config = json.load(f)
        else:
            workspace_config = {
                "id": workspace_id,
                "system_environments": {},
                "user_ui_environments": {},
                "user_ui_context": {}
            }

        # 更新系统环境信息
        if "system_environments" not in workspace_config:
            workspace_config["system_environments"] = {}

        system_envs = workspace_config["system_environments"]

        # 只更新提供的字段
        update_data = system_update.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if value is not None:
                system_envs[key] = value

        # 写入文件
        with workspace_file.open("w", encoding="utf-8") as f:
            json.dump(workspace_config, f, indent=2, ensure_ascii=False)

        logger.info(f"Updated system environments for workspace {workspace_id}")

        return {
            "success": True,
            "message": "System environments updated successfully",
            "system_environments": system_envs
        }

    except (
        OSError,
        json.JSONDecodeError,
        AttributeError,
        KeyError,
        ValueError,
        TypeError,
    ) as e:
        logger.error(f"Failed to update system environments: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update system environments: {e!s}",
        )
