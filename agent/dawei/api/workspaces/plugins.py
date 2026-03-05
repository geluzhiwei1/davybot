# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Plugin settings API endpoints for workspaces.

Provides CRUD operations for plugin configuration per workspace.
"""

import json
import logging
import traceback
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from dawei.plugins.base import PluginType
from dawei.plugins.manager import PluginManager
from dawei.workspace.models import PluginInstanceConfig, PluginsConfig

from .core import UserWorkspace, get_user_workspace

logger = logging.getLogger(__name__)

# Plugin manager cache per workspace (simple singleton pattern)
_plugin_managers: dict[str, PluginManager] = {}


def get_cached_plugin_manager(workspace_id: str, workspace_path: Path) -> "PluginManager":
    """Get or create plugin manager for workspace with caching.

    Args:
        workspace_id: Unique workspace identifier
        workspace_path: Path to workspace directory

    Returns:
        PluginManager instance (cached or newly created)
    """
    # Return cached manager if exists
    if workspace_id in _plugin_managers:
        manager = _plugin_managers[workspace_id]
        logger.debug(f"Returning cached plugin manager for workspace {workspace_id}")
        return manager

    # Import PluginManager here to avoid circular dependency
    from dawei.plugins.manager import PluginManager as PMClass

    # Create new manager and cache it
    manager = PMClass(workspace_path=workspace_path)
    _plugin_managers[workspace_id] = manager

    logger.info(f"Created new plugin manager for workspace {workspace_id}")

    return manager


router = APIRouter(prefix="/{workspace_id}/plugins", tags=["plugins"])


# Request/Response Models


class PluginInfo(BaseModel):
    """Plugin information"""

    id: str
    name: str
    version: str
    type: str
    description: str
    author: str
    activated: bool
    enabled: bool


class PluginSettings(BaseModel):
    """Plugin settings"""

    enabled: bool = True
    settings: dict[str, Any] = Field(default_factory=dict)


class UpdatePluginSettingsRequest(BaseModel):
    """Update plugin settings request"""

    enabled: bool | None = None
    settings: dict[str, Any] | None = None


class PluginActionRequest(BaseModel):
    """Plugin action request"""

    action: str  # "enable", "disable", "activate", "deactivate", "reload"


class ValidateConfigRequest(BaseModel):
    """Validate plugin configuration request"""

    config: dict[str, Any]


class SaveConfigRequest(BaseModel):
    """Save plugin configuration request"""

    config: dict[str, Any]


# Dependency to get plugin manager


async def get_plugin_manager(
    workspace: UserWorkspace = Depends(get_user_workspace),
) -> PluginManager:
    """Get or create plugin manager for workspace with caching."""
    workspace_id = workspace.uuid  # Use workspace.uuid, not workspace_id (which doesn't exist)
    workspace_path = Path(workspace.workspace_path)

    # Use cached manager to ensure state consistency across API calls
    manager = get_cached_plugin_manager(workspace_id, workspace_path)

    # Load plugins if not already loaded
    if not manager.loader.list_loaded_plugins():
        try:
            # Load plugin settings from workspace
            if workspace.plugins_config is None:
                await workspace._load_plugins_config()

            # Convert plugins_config to settings dict for discover_and_load_all
            settings_for_load = {}
            if workspace.plugins_config and workspace.plugins_config.plugins:
                for plugin_name, plugin_config in workspace.plugins_config.plugins.items():
                    # Keep hierarchical structure: metadata at root, settings in nested "settings" key
                    merged_settings = {
                        "enabled": plugin_config.enabled,
                        "activated": plugin_config.activated,
                        "version": plugin_config.version,
                        "install_path": plugin_config.install_path,
                        "settings": plugin_config.settings,  # 保持层级结构
                    }
                    settings_for_load[plugin_name] = merged_settings

            await manager.discover_and_load_all(settings=settings_for_load)
        except Exception as e:
            import traceback

            tb = traceback.format_exc()
            logger.exception(f"Failed to load plugins: {e}\n{tb}")
            # Re-raise to fail fast - plugin loading errors should not be silent
            raise HTTPException(status_code=500, detail=f"Failed to load plugins: {e!s}")

    return manager


# Endpoints


@router.get("")
async def list_plugins(
    workspace: UserWorkspace = Depends(get_user_workspace),
    plugin_type: str | None = None,
    activated_only: bool = False,
    manager: PluginManager = Depends(get_plugin_manager),
):
    """List all plugins in workspace.

    Query parameters:
    - plugin_type: Filter by plugin type (channel, tool, service, memory)
    - activated_only: Only show activated plugins
    """
    ptype = PluginType(plugin_type) if plugin_type else None
    plugins = manager.list_plugins(plugin_type=ptype, activated_only=activated_only)

    # Return in format expected by frontend
    # Build plugin info with manifest data and registration state
    plugin_list = []
    for plugin in plugins:
        # plugin is now a dict, not an object
        plugin_info = {
            "id": plugin.get("id"),
            "name": plugin.get("name"),
            "version": plugin.get("version"),
            "type": plugin.get("type"),
            "description": plugin.get("description"),
            "author": plugin.get("author"),
            "enabled": plugin.get("enabled", True),
            "activated": plugin.get("activated", False),
        }
        plugin_list.append(plugin_info)

    return {"plugins": plugin_list}


@router.get("/statistics")
async def get_plugin_statistics(
    workspace: UserWorkspace = Depends(get_user_workspace),
    manager: PluginManager = Depends(get_plugin_manager),
):
    """Get plugin system statistics.

    Must be defined before /{plugin_id} to avoid route conflicts!
    """
    return manager.get_statistics()


# ============================================================================
# 两层配置系统：插件配置 API（使用 PluginsConfig）
# These routes must be defined before /{plugin_id} to avoid route conflicts!
# ============================================================================


class PluginsConfigResponse(BaseModel):
    """插件配置响应模型"""

    success: bool
    config: dict[str, Any]
    message: str | None = None


@router.get("/config")
async def get_plugins_config(
    workspace: UserWorkspace = Depends(get_user_workspace),
) -> PluginsConfigResponse:
    """获取所有插件配置（两层配置系统）

    返回格式：
    {
        "plugins": {
            "plugin-id": {
                "enabled": true,
                "activated": false,
                "settings": {...},
                "version": "1.0.0",
                "install_path": "/path/to/plugin"
            }
        },
        "max_plugins": 50,
        "auto_discovery": true,
        "enabled": true
    }
    """
    # 确保工作区已初始化
    if not workspace.is_initialized():
        await workspace.initialize()

    # 获取插件配置（已通过 _load_plugins_config 加载）
    if workspace.plugins_config is None:
        await workspace._load_plugins_config()

    config_dict = workspace.plugins_config.model_dump()

    return PluginsConfigResponse(
        success=True,
        config=config_dict,
        message=None,
    )


@router.put("/config")
async def update_plugins_config(
    config_update: dict[str, Any],
    workspace: UserWorkspace = Depends(get_user_workspace),
) -> PluginsConfigResponse:
    """更新插件配置（两层配置系统）

    请求体示例：
    {
        "plugins": {
            "my-plugin": {
                "enabled": true,
                "settings": {"api_key": "new-key"}
            }
        }
    }
    """
    # 确保工作区已初始化
    if not workspace.is_initialized():
        await workspace.initialize()

    # 加载当前配置
    if workspace.plugins_config is None:
        await workspace._load_plugins_config()

    # 更新插件配置
    if "plugins" in config_update and isinstance(config_update["plugins"], dict):
        for plugin_id, plugin_data in config_update["plugins"].items():
            if isinstance(plugin_data, dict):
                # 获取或创建插件配置
                if plugin_id in workspace.plugins_config.plugins:
                    plugin_config = workspace.plugins_config.plugins[plugin_id]
                else:
                    plugin_config = PluginInstanceConfig()
                    workspace.plugins_config.plugins[plugin_id] = plugin_config

                # 更新字段
                if "enabled" in plugin_data:
                    plugin_config.enabled = plugin_data["enabled"]
                if "activated" in plugin_data:
                    plugin_config.activated = plugin_data["activated"]
                if "settings" in plugin_data:
                    plugin_config.settings.update(plugin_data["settings"])
                if "version" in plugin_data:
                    plugin_config.version = plugin_data["version"]
                if "install_path" in plugin_data:
                    plugin_config.install_path = plugin_data["install_path"]

    # 保存配置
    await workspace._save_plugins_config()

    logger.info(f"Plugins config updated for workspace {workspace.workspace_id}")

    return PluginsConfigResponse(
        success=True,
        config=workspace.plugins_config.model_dump(),
        message="Plugins configuration updated successfully",
    )


@router.post("/config/reset")
async def reset_plugins_config(
    workspace: UserWorkspace = Depends(get_user_workspace),
) -> PluginsConfigResponse:
    """重置插件配置为默认值（两层配置系统）

    将删除所有插件配置，恢复为空的默认配置
    """
    # 确保工作区已初始化
    if not workspace.is_initialized():
        await workspace.initialize()

    # 重置为默认配置
    workspace.plugins_config = PluginsConfig()

    # 保存配置
    await workspace._save_plugins_config()

    logger.info(f"Plugins config reset to defaults for workspace {workspace.workspace_id}")

    return PluginsConfigResponse(
        success=True,
        config=workspace.plugins_config.model_dump(),
        message="Plugins configuration reset to defaults",
    )


@router.get("/{plugin_id}", response_model=PluginInfo)
async def get_plugin(
    plugin_id: str,
    workspace: UserWorkspace = Depends(get_user_workspace),
    manager: PluginManager = Depends(get_plugin_manager),
):
    """Get specific plugin information."""
    plugin = manager.get_plugin(plugin_id)

    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin not found: {plugin_id}")

    manifest = manager.get_manifest(plugin_id)

    # Get enabled status from workspace.plugins_config
    plugin_config = workspace.plugins_config.get_plugin_config(plugin_id) if workspace.plugins_config else None
    enabled = plugin_config.enabled if plugin_config else True

    return PluginInfo(
        id=plugin_id,
        name=manifest.name,
        version=manifest.version,
        type=manifest.plugin_type,
        description=manifest.description,
        author=manifest.author,
        activated=plugin.is_activated,
        enabled=enabled,
    )


@router.get("/{plugin_id}/settings")
async def get_plugin_settings(
    plugin_id: str,
    workspace: UserWorkspace = Depends(get_user_workspace),
    manager: PluginManager = Depends(get_plugin_manager),
):
    """Get plugin settings."""
    settings = manager.get_plugin_settings(plugin_id)

    if settings is None:
        raise HTTPException(status_code=404, detail=f"Plugin not found: {plugin_id}")

    return settings


@router.put("/{plugin_id}/settings")
async def update_plugin_settings(
    plugin_id: str,
    request: UpdatePluginSettingsRequest,
    workspace: UserWorkspace = Depends(get_user_workspace),
    manager: PluginManager = Depends(get_plugin_manager),
):
    """Update plugin settings."""
    settings = manager.get_plugin_settings(plugin_id)

    if settings is None:
        raise HTTPException(status_code=404, detail=f"Plugin not found: {plugin_id}")

    # Build updated settings
    updated = {}

    if request.enabled is not None:
        updated["enabled"] = request.enabled

    if request.settings is not None:
        # settings is now already the inner settings (after loader.py extraction)
        updated["settings"] = {**settings, **request.settings}

    # Apply update
    success = await manager.update_plugin_settings(plugin_id, updated)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to update plugin settings")

    # Enable/disable plugin
    if request.enabled is not None:
        if request.enabled and not manager.get_plugin(plugin_id).is_activated:
            await manager.activate_plugin(plugin_id)
        elif not request.enabled and manager.get_plugin(plugin_id).is_activated:
            await manager.deactivate_plugin(plugin_id)

    # Persist to disk (保持层级结构)
    if workspace.plugins_config is None:
        await workspace._load_plugins_config()

    # Try exact match first, then try without version suffix
    actual_plugin_id = plugin_id
    if plugin_id not in workspace.plugins_config.plugins:
        # Try extracting name from name@version format
        if "@" in plugin_id:
            base_name = plugin_id.split("@", maxsplit=1)[0]
            for key in workspace.plugins_config.plugins:
                if key.startswith(base_name + "@"):
                    actual_plugin_id = key
                    break

    if actual_plugin_id in workspace.plugins_config.plugins:
        plugin_config = workspace.plugins_config.plugins[actual_plugin_id]
        if "settings" in updated:
            plugin_config.settings = updated["settings"]
        if "enabled" in updated:
            plugin_config.enabled = updated["enabled"]
        await workspace._save_plugins_config()

    return {"success": True, "settings": manager.get_plugin_settings(plugin_id)}


@router.post("/{plugin_id}/action")
async def plugin_action(
    plugin_id: str,
    request: PluginActionRequest,
    workspace: UserWorkspace = Depends(get_user_workspace),
    manager: PluginManager = Depends(get_plugin_manager),
):
    """Perform action on plugin (enable, disable, activate, deactivate, reload)."""
    logger.info(f"[DEBUG] plugin_action called: plugin_id={plugin_id}, action={request.action}")
    plugin = manager.get_plugin(plugin_id)

    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin not found: {plugin_id}")

    action = request.action.lower()
    result = False

    if action == "enable":
        # Enable in settings and activate
        settings = manager.get_plugin_settings(plugin_id) or {}
        settings["enabled"] = True
        await manager.update_plugin_settings(plugin_id, settings)

        # 同时更新 Workspace.plugins_config 并保存到文件
        if workspace.plugins_config is None:
            await workspace._load_plugins_config()

        workspace.plugins_config.enable_plugin(plugin_id)
        await workspace._save_plugins_config()

        if not plugin.is_activated:
            result = await manager.activate_plugin(plugin_id)
            if not result:
                logger.warning(f"Failed to activate plugin {plugin_id} during enable")
        else:
            result = True

    elif action == "disable":
        # Disable in settings and deactivate
        settings = manager.get_plugin_settings(plugin_id) or {}
        settings["enabled"] = False
        await manager.update_plugin_settings(plugin_id, settings)

        # 同时更新 Workspace.plugins_config 并保存到文件
        if workspace.plugins_config is None:
            await workspace._load_plugins_config()

        logger.info(f"[DEBUG] Before disable: plugins_config.plugins = {list(workspace.plugins_config.plugins.keys()) if workspace.plugins_config else 'None'}")

        workspace.plugins_config.disable_plugin(plugin_id)

        logger.info(f"[DEBUG] After disable: plugins_config.plugins['{plugin_id}'].enabled = {workspace.plugins_config.plugins.get(plugin_id, {}).enabled if plugin_id in workspace.plugins_config.plugins else 'NOT FOUND'}")

        await workspace._save_plugins_config()

        logger.info("[DEBUG] Saved plugins_config to file")

        if plugin.is_activated:
            result = await manager.deactivate_plugin(plugin_id)
            if not result:
                logger.warning(f"Failed to deactivate plugin {plugin_id} during disable")
        else:
            result = True

    elif action == "activate":
        # 先执行实际的插件激活，成功后再更新配置
        # 避免配置与运行时状态不一致
        result = await manager.activate_plugin(plugin_id)

        if result:
            # 激活成功，更新配置并保存
            if workspace.plugins_config is None:
                await workspace._load_plugins_config()

            workspace.plugins_config.enable_plugin(plugin_id)
            if plugin_id in workspace.plugins_config.plugins:
                workspace.plugins_config.plugins[plugin_id].activated = True

            await workspace._save_plugins_config()
        else:
            logger.warning(f"Failed to activate plugin {plugin_id}")

    elif action == "deactivate":
        # 先执行实际的插件停用，成功后再更新配置
        # 避免配置与运行时状态不一致
        result = await manager.deactivate_plugin(plugin_id)

        if not result:
            # Already deactivated is not an error
            logger.info(f"Plugin {plugin_id} is already deactivated")
            result = True  # Consider it success
        else:
            # 停用成功，更新配置并保存
            if workspace.plugins_config is None:
                await workspace._load_plugins_config()

            if plugin_id in workspace.plugins_config.plugins:
                workspace.plugins_config.plugins[plugin_id].activated = False

            await workspace._save_plugins_config()

    elif action == "reload":
        result = await manager.reload_plugin(plugin_id)
        if not result:
            logger.warning(f"Failed to reload plugin {plugin_id}")

    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {action}")

    if not result:
        raise HTTPException(status_code=500, detail=f"Failed to {action} plugin")

    return {"success": True, "action": action, "plugin_id": plugin_id}


@router.get("/{plugin_id}/schema")
async def get_plugin_config_schema(
    plugin_id: str,
    workspace: UserWorkspace = Depends(get_user_workspace),
    manager: PluginManager = Depends(get_plugin_manager),
):
    """Get plugin configuration schema.

    Returns the JSON Schema for plugin configuration.
    Frontend uses this to auto-generate configuration forms.
    """
    schema = manager.get_config_schema(plugin_id)

    if schema is None:
        raise HTTPException(status_code=404, detail=f"Plugin not found: {plugin_id}")

    # Normalize schema format - extract nested schema if present
    # Handle both old format (direct type/properties) and new format (nested schema/ui_schema)
    actual_schema = schema
    actual_ui_schema = {}

    if isinstance(schema, dict):
        if "schema" in schema:
            # New format: {schema: {...}, ui_schema: {...}}
            actual_schema = schema["schema"]
            actual_ui_schema = schema.get("ui_schema", {})
        elif "type" in schema and "properties" in schema:
            # Old format: direct JSON Schema
            actual_schema = schema
            actual_ui_schema = {}

    # Load existing config if available
    existing_config = manager.get_plugin_config(plugin_id)

    return {
        "plugin_id": plugin_id,
        "schema": actual_schema,
        "ui_schema": actual_ui_schema,
        "existing_config": existing_config,
    }


@router.post("/{plugin_id}/config/validate")
async def validate_plugin_config(
    plugin_id: str,
    request: ValidateConfigRequest,
    workspace: UserWorkspace = Depends(get_user_workspace),
    manager: PluginManager = Depends(get_plugin_manager),
):
    """Validate plugin configuration.

    Validates configuration against the plugin's schema without saving.
    """
    is_valid, errors = manager.validate_config(plugin_id, request.config)

    return {
        "valid": is_valid,
        "errors": errors,
    }


@router.post("/{plugin_id}/config")
async def save_plugin_config(
    plugin_id: str,
    request: SaveConfigRequest,
    workspace: UserWorkspace = Depends(get_user_workspace),
    manager: PluginManager = Depends(get_plugin_manager),
):
    """Save and apply plugin configuration.

    Validates, encrypts, and saves configuration, then activates the plugin.
    """
    # Check if plugin manifest exists via registry (plugin may not be loaded yet)
    manifest = manager.registry.get_manifest(plugin_id)
    if not manifest:
        raise HTTPException(status_code=404, detail=f"Plugin not found: {plugin_id}")

    # Save configuration (will validate and activate)
    success = await manager.save_plugin_config(plugin_id, request.config)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to save plugin configuration")

    # Get updated plugin info (may still be None if plugin failed to load)
    updated_plugin = manager.get_plugin(plugin_id)

    return {
        "success": True,
        "plugin_id": plugin_id,
        "activated": updated_plugin.is_activated if updated_plugin else False,
        "message": "Plugin configuration saved successfully",
    }


@router.delete("/{plugin_id}")
async def uninstall_plugin_endpoint(
    plugin_id: str,
    workspace: UserWorkspace = Depends(get_user_workspace),
    manager: PluginManager = Depends(get_plugin_manager),
) -> dict[str, Any]:
    """卸载插件。支持两种格式：
    - 完整ID：name@version（如 feishu-channel@0.1.0）
    - 仅名称：name（卸载该名称的所有版本）
    """
    # 确保工作区已初始化
    if not workspace.is_initialized():
        await workspace.initialize()

    # 智能处理：根据plugin_id格式选择卸载方式
    if "@" in plugin_id:
        # 完整ID格式：尝试精确卸载
        success = await manager.uninstall_plugin(plugin_id)

        if not success:
            # 如果精确卸载失败，尝试按名称卸载（版本可能不匹配）
            plugin_name = plugin_id.split("@", maxsplit=1)[0]
            logger.warning(f"Failed to uninstall {plugin_id}, trying by name '{plugin_name}'")
            success = await manager.uninstall_plugin_by_name(plugin_name)

            if success:
                logger.info(f"Uninstalled plugin by name: {plugin_name}")
                return {"success": True, "plugin_id": plugin_name, "message": f"Plugin {plugin_name} (version may differ) has been uninstalled"}
            # 仍然失败，返回404
            raise HTTPException(status_code=404, detail=f"Plugin {plugin_id} not found or cannot be uninstalled")
        logger.info(f"Plugin {plugin_id} uninstalled successfully")
        return {"success": True, "plugin_id": plugin_id, "message": f"Plugin {plugin_id} has been uninstalled"}
    # 仅名称格式：卸载所有版本
    success = await manager.uninstall_plugin_by_name(plugin_id)

    if success:
        logger.info(f"Plugin {plugin_id} uninstalled successfully")
        return {"success": True, "plugin_id": plugin_id, "message": f"Plugin {plugin_id} has been uninstalled"}
    raise HTTPException(status_code=404, detail=f"Plugin {plugin_id} not found or cannot be uninstalled")


# ============================================================================
# 飞书插件专用端点
# ============================================================================


class TestFeishuMessageRequest(BaseModel):
    """测试飞书消息发送请求"""

    message: str = Field(default="这是一条测试消息", description="测试消息内容")


@router.post("/{plugin_id}/test-connection")
async def test_feishu_connection(
    plugin_id: str,
    workspace: UserWorkspace = Depends(get_user_workspace),
    manager: PluginManager = Depends(get_plugin_manager),
) -> dict[str, Any]:
    """测试飞书长连接状态

    检查项目：
    1. 插件是否已启用
    2. 插件是否已激活
    3. 事件服务器是否运行（检查端口）
    4. 健康检查端点是否响应
    """
    # 只支持飞书插件
    if not plugin_id.startswith("feishu-channel"):
        return {"success": False, "error": "此功能仅支持飞书插件"}

    # 直接从配置文件读取状态（简单直接）
    import json
    from pathlib import Path

    config_file = Path(workspace.workspace_path) / ".dawei" / "plugins" / f"{plugin_id}.json"

    if not config_file.exists():
        return {"success": False, "error": "插件配置文件不存在"}

    with config_file.open() as f:
        plugin_config = json.load(f)

    enabled = plugin_config.get("enabled", False)
    activated = plugin_config.get("activated", False)

    if not enabled:
        return {"success": False, "error": "插件未启用"}

    if not activated:
        return {"success": False, "error": "插件未激活", "status": "inactive"}

    # 获取插件实例以访问配置
    plugin = manager.get_plugin(plugin_id)

    if not plugin:
        return {"success": False, "error": "插件未加载"}

    # 检查事件服务器状态
    import socket

    event_port = plugin_config.get("settings", {}).get("event_port", 8466)
    event_host = plugin.config.settings.get("event_host", "0.0.0.0")

    # 检查端口是否监听
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    result = sock.connect_ex(("localhost", event_port))
    sock.close()

    port_listening = result == 0

    # 健康检查
    health_ok = False
    health_status = {}

    if port_listening:
        import aiohttp

        async with aiohttp.ClientSession() as session, session.get(f"http://localhost:{event_port}/feishu/health", timeout=aiohttp.ClientTimeout(total=2)) as resp:
            if resp.status == 200:
                health_data = await resp.json()
                health_ok = health_data.get("status") == "ok"
                health_status = health_data

    return {
        "success": True,
        "plugin_id": plugin_id,
        "connection_status": {"plugin_activated": True, "event_server_running": port_listening, "health_check_passed": health_ok, "event_port": event_port, "event_host": event_host},
        "health_status": health_status,
        "message": "✅ 长连接已建立" if (port_listening and health_ok) else "⚠️ 长连接未完全建立",
    }


@router.post("/{plugin_id}/send-test-message")
async def send_feishu_test_message(
    plugin_id: str,
    request: TestFeishuMessageRequest,
    workspace: UserWorkspace = Depends(get_user_workspace),
    manager: PluginManager = Depends(get_plugin_manager),
) -> dict[str, Any]:
    """发送飞书测试消息

    发送一条测试消息到配置的飞书群聊
    """
    # 只支持飞书插件
    if not plugin_id.startswith("feishu-channel"):
        return {"success": False, "error": "此功能仅支持飞书插件"}

    # 直接从配置文件读取状态（与 test-connection 保持一致）
    import json
    from pathlib import Path

    config_file = Path(workspace.workspace_path) / ".dawei" / "plugins" / f"{plugin_id}.json"

    if not config_file.exists():
        return {"success": False, "error": "插件配置文件不存在"}

    with config_file.open() as f:
        plugin_config = json.load(f)

    enabled = plugin_config.get("enabled", False)
    activated = plugin_config.get("activated", False)

    if not enabled:
        return {"success": False, "error": "插件未启用"}

    if not activated:
        return {"success": False, "error": "插件未激活，请先激活插件"}

    plugin = manager.get_plugin(plugin_id)

    if not plugin:
        return {"success": False, "error": "插件未加载"}

    # 获取配置
    receive_id = plugin.config.settings.get("receive_id")
    if not receive_id:
        return {"success": False, "error": "未配置receive_id，请先配置插件"}

    # 发送测试消息
    test_message = f"🔔 测试消息\n\n{request.message}\n\n发送时间: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

    success = await plugin.send_message(test_message)

    if success:
        return {"success": True, "plugin_id": plugin_id, "message": "测试消息发送成功！", "sent_content": test_message, "receive_id": receive_id}
    return {"success": False, "error": "消息发送失败，请检查配置和权限"}
