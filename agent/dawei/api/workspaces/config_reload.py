# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Configuration Reload API Routes

提供工作区配置的重新加载功能,确保 skills 和 modes 的修改能立即生效
"""

import logging
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from dawei.api.error_codes import ErrorCodes, error_detail
from dawei.workspace import workspace_manager
from dawei.workspace.user_workspace import UserWorkspace

logger = logging.getLogger(__name__)

# 创建路由器
router = APIRouter(tags=["workspaces-config-reload"])


# --- Pydantic 模型 ---


class ConfigReloadRequest(BaseModel):
    """配置重新加载请求"""

    config_type: Literal["all", "skills", "modes", "tools"] = "all"
    force: bool = True  # 是否强制重新加载(绕过缓存)


class ConfigReloadResponse(BaseModel):
    """配置重新加载响应"""

    success: bool
    message: str
    details: dict[str, str | int | bool]


# --- 辅助函数 ---


def get_user_workspace(workspace_id: str) -> UserWorkspace:
    """Dependency to get a UserWorkspace instance."""
    workspace_info = workspace_manager.get_workspace_by_id(workspace_id)
    if not workspace_info:
        raise HTTPException(
            status_code=404,
            detail=error_detail(ErrorCodes.WORKSPACE_NOT_FOUND, f"Workspace {workspace_id} not found"),
        )
    return workspace_info


# --- API 端点 ---


@router.post("/{workspace_id}/reload-config", response_model=ConfigReloadResponse)
async def reload_workspace_config(
    workspace_id: str,
    request: ConfigReloadRequest,
) -> ConfigReloadResponse:
    """重新加载工作区配置

    支持重新加载以下配置:
    - skills: 技能配置(重新发现 skills)
    - modes: 模式配置(清除缓存并重新加载)
    - tools: 工具配置(重新加载工具配置和 MCP 配置)
    - all: 所有配置

    Args:
        workspace_id: 工作区 ID
        request: 重新加载请求
            - config_type: 配置类型 ("all", "skills", "modes", "tools")
            - force: 是否强制重新加载(绕过缓存)

    Returns:
        ConfigReloadResponse: 重新加载结果

    Raises:
        HTTPException: 工作区不存在或重新加载失败
    """
    workspace = get_user_workspace(workspace_id)

    details = {}
    success_count = 0
    total_count = 0

    try:
        # 重新加载 Skills
        if request.config_type in ["all", "skills"]:
            total_count += 1
            try:
                if workspace.tool_manager and workspace.tool_manager.skill_manager:
                    # 强制重新发现 skills
                    workspace.tool_manager.skill_manager.discover_skills(force=request.force)

                    # 重新创建 skills 工具
                    workspace.tool_manager._skills_tools = workspace.tool_manager._create_skills_tools()

                    skills_count = len(workspace.tool_manager.skill_manager._skills)
                    details["skills"] = f"Reloaded {skills_count} skills"
                    details["skills_count"] = skills_count
                    success_count += 1

                    logger.info(f"[CONFIG_RELOAD] Skills reloaded for workspace {workspace_id}: {skills_count} skills")
                else:
                    details["skills"] = "No skill manager found"
                    details["skills_count"] = 0
            except Exception as e:
                logger.error(f"[CONFIG_RELOAD] Failed to reload skills: {e}", exc_info=True)
                details["skills"] = f"Failed: {str(e)}"
                details["skills_count"] = 0

        # 重新加载 Modes
        if request.config_type in ["all", "modes"]:
            total_count += 1
            try:
                if workspace.mode_manager:
                    # 清除缓存
                    if hasattr(workspace.mode_manager, 'config_loader'):
                        workspace.mode_manager.config_loader.clear_cache()

                    # 重新加载所有 modes
                    await workspace.mode_manager.load_all_modes()

                    modes_count = len(workspace.mode_manager.modes)
                    details["modes"] = f"Reloaded {modes_count} modes"
                    details["modes_count"] = modes_count
                    success_count += 1

                    logger.info(f"[CONFIG_RELOAD] Modes reloaded for workspace {workspace_id}: {modes_count} modes")
                else:
                    details["modes"] = "No mode manager found"
                    details["modes_count"] = 0
            except Exception as e:
                logger.error(f"[CONFIG_RELOAD] Failed to reload modes: {e}", exc_info=True)
                details["modes"] = f"Failed: {str(e)}"
                details["modes_count"] = 0

        # 重新加载 Tools
        if request.config_type in ["all", "tools"]:
            total_count += 1
            try:
                if workspace.tool_manager:
                    # 重新加载工具配置
                    workspace.tool_manager.reload_tool_configs()

                    # 重新加载 MCP 配置
                    if workspace.tool_manager.mcp_tool_manager:
                        workspace.tool_manager.reload_mcp_configs()

                    tool_stats = workspace.tool_manager.get_statistics()
                    details["tools"] = "Tool configs reloaded"
                    details["tools_count"] = tool_stats.get("workspace_specific", {}).get("available_tools_count", 0)
                    success_count += 1

                    logger.info(f"[CONFIG_RELOAD] Tools reloaded for workspace {workspace_id}")
                else:
                    details["tools"] = "No tool manager found"
                    details["tools_count"] = 0
            except Exception as e:
                logger.error(f"[CONFIG_RELOAD] Failed to reload tools: {e}", exc_info=True)
                details["tools"] = f"Failed: {str(e)}"
                details["tools_count"] = 0

        # 构建响应消息
        if success_count == total_count:
            message = f"Successfully reloaded {success_count}/{total_count} configuration type(s)"
            logger.info(f"[CONFIG_RELOAD] {message} for workspace {workspace_id}")
        else:
            message = f"Partially reloaded {success_count}/{total_count} configuration type(s)"
            logger.warning(f"[CONFIG_RELOAD] {message} for workspace {workspace_id}")

        return ConfigReloadResponse(
            success=success_count > 0,
            message=message,
            details=details,
        )

    except Exception as e:
        logger.error(f"[CONFIG_RELOAD] Unexpected error reloading config for workspace {workspace_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=error_detail(
                ErrorCodes.INTERNAL_ERROR,
                f"Failed to reload configuration: {str(e)}",
            ),
        )
