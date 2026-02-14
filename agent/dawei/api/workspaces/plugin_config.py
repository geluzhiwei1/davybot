# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only
"""
统一插件配置 API - 动态配置管理

提供统一的插件配置接口：
1. 获取插件的配置 schema
2. 获取插件的当前配置值
3. 更新插件配置
4. 重置插件配置为默认值
5. 验证配置
"""

import logging
from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from dawei.api.workspaces.core import get_user_workspace

logger = logging.getLogger(__name__)
from dawei.workspace.user_workspace import UserWorkspace
from dawei.plugins.config import (
    PluginConfigManager,
    validate_config_against_schema,
)
from dawei.core.exceptions import ConfigurationError


# Routes will be under /api/workspaces/{workspace_id}/plugin-config/ when included by workspaces router
router = APIRouter(prefix="/{workspace_id}/plugin-config", tags=["Plugin Configuration"])


# ============================================================================
# 请求/响应模型
# ============================================================================

class GetPluginSchemaRequest(BaseModel):
    """获取插件 Schema 请求"""
    plugin_id: str = Field(..., description="插件 ID")


class GetPluginConfigRequest(BaseModel):
    """获取插件配置请求"""
    plugin_id: str = Field(..., description="插件 ID")


class UpdatePluginConfigRequest(BaseModel):
    """更新插件配置请求"""
    plugin_id: str = Field(..., description="插件 ID")
    config: Dict[str, Any] = Field(..., description="配置值（键值对）")


class ResetPluginConfigRequest(BaseModel):
    """重置插件配置请求"""
    plugin_id: str = Field(..., description="插件 ID")


class PluginConfigResponse(BaseModel):
    """插件配置响应"""
    success: bool = Field(..., description="是否成功")
    schema: Dict[str, Any] | None = Field(None, description="配置 Schema")
    config: Dict[str, Any] = Field(..., description="当前配置值")
    existing_config: Dict[str, Any] | None = Field(None, description="已存在的配置值（与config相同）")
    form_config: Dict[str, Any] | None = Field(None, description="前端表单配置")
    message: str | None = Field(None, description="提示消息")


class PluginListResponse(BaseModel):
    """插件列表响应"""
    success: bool
    plugins: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="所有插件的配置信息 {plugin_id: {schema, config}}"
    )


# ============================================================================
# 依赖项
# ============================================================================

def get_plugin_manager(
    workspace: UserWorkspace = Depends(get_user_workspace)
) -> PluginConfigManager:
    """获取插件配置管理器

    根据 workspace 初始化，返回对应级别的插件配置管理器：
    - 有 workspace_path：工作区级插件配置
    - 无 workspace_path：用户级插件配置
    """
    return PluginConfigManager(workspace_path=workspace.workspace_path)


# ============================================================================
# API 端点
# ============================================================================

@router.get("/plugins")
async def list_all_plugin_configs(
    workspace_id: str,
    workspace: UserWorkspace = Depends(get_user_workspace),
    manager: PluginConfigManager = Depends(get_plugin_manager),
) -> PluginListResponse:
    """
    获取所有插件的配置 schema 和当前值

    Returns:
        所有插件的配置信息，包括 schema 和当前值
    """
    try:
        # 扫描插件目录
        plugins_dir = workspace.workspace_path / ".dawei" / "plugins"

        plugins: Dict[str, Dict[str, Any]] = {}

        if plugins_dir.exists():
            for plugin_path in plugins_dir.iterdir():
                if not plugin_path.is_dir():
                    continue

                plugin_id = plugin_path.name

                # 读取 plugin.yaml 获取配置 schema
                plugin_yaml = plugin_path / "plugin.yaml"
                if not plugin_yaml.exists():
                    continue

                try:
                    import yaml
                    import json
                    plugin_meta = yaml.safe_load(plugin_yaml.read_text(encoding="utf-8"))
                except Exception:
                    continue

                # Handle config_schema file reference
                config_schema_value = plugin_meta.get("config_schema")
                if isinstance(config_schema_value, str):
                    # It's a file path, load JSON from it
                    schema_path = plugin_path / config_schema_value
                    if schema_path.exists():
                        try:
                            with schema_path.open(encoding="utf-8") as f:
                                plugin_meta["config_schema"] = json.load(f)
                        except Exception as e:
                            logger.error(f"Failed to load config_schema from {schema_path}: {e}")
                            plugin_meta["config_schema"] = {}
                    else:
                        logger.warning(f"config_schema file not found: {schema_path}")
                        plugin_meta["config_schema"] = {}

                schema_to_use = plugin_meta.get("config_schema", {})

                # 加载当前配置
                config = manager.load_plugin_config(plugin_id)

                # 直接返回原始 schema，不做任何转换
                plugins[plugin_id] = {
                    "schema": schema_to_use,
                    "config": config,
                }

        return PluginListResponse(
            success=True,
            plugins=plugins,
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list plugin configs: {str(e)}"
        )


@router.get("/schema")
async def get_plugin_schema(
    workspace_id: str,
    plugin_id: str = Query(..., description="Plugin ID"),
    workspace: UserWorkspace = Depends(get_user_workspace),
    manager: PluginConfigManager = Depends(get_plugin_manager),
) -> PluginConfigResponse:
    """获取单个插件的配置 schema"""
    try:
        # 获取插件列表
        list_response = await list_all_plugin_configs(workspace_id, workspace, manager)

        # 尝试直接查找
        if plugin_id in list_response.plugins:
            plugin_info = list_response.plugins[plugin_id]
            return PluginConfigResponse(
                success=True,
                schema=plugin_info.get("schema"),
                config=plugin_info.get("config", {}),
                existing_config=plugin_info.get("config", {}),  # 添加此行
                form_config=plugin_info.get("form_config"),
            )

        # 如果带版本号（如 dingtalk-channel@0.1.0），尝试提取名称查找
        if "@" in plugin_id:
            plugin_name = plugin_id.split("@")[0]
            logger.debug(f"Plugin ID '{plugin_id}' not found, trying name '{plugin_name}'")
            if plugin_name in list_response.plugins:
                plugin_info = list_response.plugins[plugin_name]
                return PluginConfigResponse(
                    success=True,
                    schema=plugin_info.get("schema"),
                    config=plugin_info.get("config", {}),
                    existing_config=plugin_info.get("config", {}),  # 添加此行
                    form_config=plugin_info.get("form_config"),
                )

        # 仍然找不到，返回 404
        available_plugins = list(list_response.plugins.keys())
        raise HTTPException(
            status_code=404,
            detail=f"Plugin '{plugin_id}' not found. Available plugins: {available_plugins}"
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get plugin schema: {str(e)}"
        )


@router.get("/config")
async def get_plugin_config(
    workspace_id: str,
    plugin_id: str = Query(..., description="Plugin ID"),
    workspace: UserWorkspace = Depends(get_user_workspace),
    manager: PluginConfigManager = Depends(get_plugin_manager),
) -> PluginConfigResponse:
    """获取插件当前配置"""
    try:
        # 获取插件列表
        list_response = await list_all_plugin_configs(workspace_id, workspace, manager)

        # 确定实际使用的 plugin_id
        actual_plugin_id = plugin_id
        found = False

        if plugin_id in list_response.plugins:
            actual_plugin_id = plugin_id
            found = True
        elif "@" in plugin_id:
            plugin_name = plugin_id.split("@")[0]
            if plugin_name in list_response.plugins:
                actual_plugin_id = plugin_name
                found = True

        if not found:
            raise HTTPException(
                status_code=404,
                detail=f"Plugin '{plugin_id}' not found"
            )

        config = manager.load_plugin_config(actual_plugin_id)
        plugin_info = list_response.plugins[actual_plugin_id]

        return PluginConfigResponse(
            success=True,
            schema=plugin_info.get("schema"),
            config=config,
            existing_config=config,
            form_config=plugin_info.get("form_config"),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get plugin config: {str(e)}"
        )


@router.put("/config")
async def update_plugin_config(
    workspace_id: str,
    request: UpdatePluginConfigRequest,
    workspace: UserWorkspace = Depends(get_user_workspace),
    manager: PluginConfigManager = Depends(get_plugin_manager),
) -> PluginConfigResponse:
    """更新插件配置"""
    try:
        # 获取插件列表
        list_response = await list_all_plugin_configs(
            workspace_id,
            workspace,
            manager,
        )

        # 确定实际使用的 plugin_id
        actual_plugin_id = request.plugin_id
        found = False

        if request.plugin_id in list_response.plugins:
            actual_plugin_id = request.plugin_id
            found = True
        elif "@" in request.plugin_id:
            plugin_name = request.plugin_id.split("@")[0]
            if plugin_name in list_response.plugins:
                actual_plugin_id = plugin_name
                found = True

        if not found:
            raise HTTPException(
                status_code=404,
                detail=f"Plugin '{request.plugin_id}' not found"
            )

        plugin_info = list_response.plugins[actual_plugin_id]
        schema = plugin_info.get("schema")

        # 验证配置
        is_valid = validate_config_against_schema(request.config, schema)

        if not is_valid:
            raise HTTPException(
                status_code=400,
                detail="Configuration validation failed. Please check your input values."
            )

        # 保存配置
        manager.save_plugin_config(actual_plugin_id, request.config)

        return PluginConfigResponse(
            success=True,
            schema=schema,
            config=request.config,
            form_config=plugin_info.get("form_config"),
            message="Configuration updated successfully",
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update plugin config: {str(e)}"
        )


@router.post("/config/reset")
async def reset_plugin_config(
    workspace_id: str,
    request: ResetPluginConfigRequest,
    workspace: UserWorkspace = Depends(get_user_workspace),
    manager: PluginConfigManager = Depends(get_plugin_manager),
) -> PluginConfigResponse:
    """重置插件配置为默认值"""
    try:
        # 获取插件列表
        list_response = await list_all_plugin_configs(
            workspace_id,
            workspace,
            manager,
        )

        # 确定实际使用的 plugin_id
        actual_plugin_id = request.plugin_id
        found = False

        if request.plugin_id in list_response.plugins:
            actual_plugin_id = request.plugin_id
            found = True
        elif "@" in request.plugin_id:
            plugin_name = request.plugin_id.split("@")[0]
            if plugin_name in list_response.plugins:
                actual_plugin_id = plugin_name
                found = True

        if not found:
            raise HTTPException(
                status_code=404,
                detail=f"Plugin '{request.plugin_id}' not found"
            )

        plugin_info = list_response.plugins[actual_plugin_id]
        schema = plugin_info.get("schema")

        # 提取默认值
        defaults = {}
        for field in schema.get("properties", {}).values():
            if "default" in field:
                defaults[field["name"]] = field["default"]

        # 保存默认配置
        manager.save_plugin_config(actual_plugin_id, defaults)

        return PluginConfigResponse(
            success=True,
            schema=schema,
            config=defaults,
            form_config=plugin_info.get("form_config"),
            message="Configuration reset to defaults",
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reset plugin config: {str(e)}"
        )
