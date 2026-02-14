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


def get_cached_plugin_manager(workspace_id: str, workspace_path: Path) -> 'PluginManager':
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


def load_plugin_settings_file(workspace_path: Path) -> dict[str, Any]:
    """Load plugin settings from .dawei/plugins/{plugin_id}.json

    Args:
        workspace_path: Path to workspace directory

    Returns:
        Dictionary of plugin settings {plugin_id: settings_dict}

    """
    plugins_dir = workspace_path / ".dawei" / "plugins"

    if not plugins_dir.exists() or not plugins_dir.is_dir():
        logger.debug(f"No plugin settings dir: {plugins_dir}")
        return {}

    plugin_settings = {}
    for config_file in plugins_dir.glob("*.json"):
        # Skip non-plugin config files
        if config_file.name == "config_schema.json":
            continue
        try:
            plugin_id = config_file.stem
            with config_file.open(encoding="utf-8") as f:
                config_data = json.load(f)
                plugin_settings[plugin_id] = config_data
            logger.debug(f"Loaded plugin config: {plugin_id}")
        except Exception as e:
            logger.warning(f"Failed to load plugin config {config_file}: {e}")

    if plugin_settings:
        logger.info(f"Loaded {len(plugin_settings)} plugin configs from {plugins_dir}")

    return plugin_settings


def save_plugin_settings_file(workspace_path: Path, plugin_settings: dict[str, Any]) -> bool:
    """Save plugin settings to individual plugin config files.

    Saves each plugin's configuration to .dawei/plugins/{plugin_id}.json

    Args:
        workspace_path: Path to workspace directory
        plugin_settings: Dictionary of plugin settings {plugin_id: config_dict}

    Returns:
        True if successful, False otherwise
    """
    plugins_dir = workspace_path / ".dawei" / "plugins"
    plugins_dir.mkdir(parents=True, exist_ok=True)

    try:
        for plugin_id, config in plugin_settings.items():
            config_file = plugins_dir / f"{plugin_id}.json"
            with config_file.open("w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            logger.debug(f"Saved plugin config: {plugin_id}")

        logger.info(f"Saved {len(plugin_settings)} plugin configs to {plugins_dir}")
        return True
    except Exception as e:
        logger.error(f"Failed to save plugin settings: {e}")
        return False


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
            # Load plugin settings from .dawei/plugins/{plugin_id}.json
            plugin_settings = load_plugin_settings_file(workspace_path)

            # Extract 'settings' key from each plugin config for discover_and_load_all
            settings_for_load = {}
            for plugin_name, plugin_config in plugin_settings.items():
                if isinstance(plugin_config, dict) and "settings" in plugin_config:
                    settings_for_load[plugin_name] = plugin_config["settings"]
                else:
                    settings_for_load[plugin_name] = plugin_config

            await manager.discover_and_load_all(settings=settings_for_load)
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            logger.error(f"Failed to load plugins: {e}\n{tb}")
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
    try:
        ptype = PluginType(plugin_type) if plugin_type else None
        plugins = manager.list_plugins(plugin_type=ptype, activated_only=activated_only)

        # Return in format expected by frontend
        return {"plugins": [PluginInfo(**plugin) for plugin in plugins]}

    except Exception as e:
        logger.exception("Error listing plugins: ")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistics")
async def get_plugin_statistics(
    workspace: UserWorkspace = Depends(get_user_workspace),
    manager: PluginManager = Depends(get_plugin_manager),
):
    """Get plugin system statistics.

    Must be defined before /{plugin_id} to avoid route conflicts!
    """
    try:
        return manager.get_statistics()

    except Exception as e:
        logger.exception("Error getting plugin statistics: ")
        raise HTTPException(status_code=500, detail=str(e))


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
    try:
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

    except Exception as e:
        logger.exception("Failed to get plugins config: ")
        raise HTTPException(status_code=500, detail=f"Failed to get plugins config: {e!s}")


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
        },
        "max_plugins": 100,
        "auto_discovery": false
    }
    """
    try:
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

        # 更新全局设置
        if "max_plugins" in config_update:
            workspace.plugins_config.max_plugins = config_update["max_plugins"]
        if "auto_discovery" in config_update:
            workspace.plugins_config.auto_discovery = config_update["auto_discovery"]
        if "enabled" in config_update:
            workspace.plugins_config.enabled = config_update["enabled"]

        # 保存配置
        await workspace._save_plugins_config()

        logger.info(f"Plugins config updated for workspace {workspace.workspace_id}")

        return PluginsConfigResponse(
            success=True,
            config=workspace.plugins_config.model_dump(),
            message="Plugins configuration updated successfully",
        )

    except Exception as e:
        logger.exception("Failed to update plugins config: ")
        raise HTTPException(status_code=500, detail=f"Failed to update plugins config: {e!s}")


@router.post("/config/reset")
async def reset_plugins_config(
    workspace: UserWorkspace = Depends(get_user_workspace),
) -> PluginsConfigResponse:
    """重置插件配置为默认值（两层配置系统）

    将删除所有插件配置，恢复为空的默认配置
    """
    try:
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

    except Exception as e:
        logger.exception("Failed to reset plugins config: ")
        raise HTTPException(status_code=500, detail=f"Failed to reset plugins config: {e!s}")


@router.get("/{plugin_id}", response_model=PluginInfo)
async def get_plugin(
    plugin_id: str,
    workspace: UserWorkspace = Depends(get_user_workspace),
    manager: PluginManager = Depends(get_plugin_manager),
):
    """Get specific plugin information."""
    try:
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

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error getting plugin: ")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{plugin_id}/settings")
async def get_plugin_settings(
    plugin_id: str,
    workspace: UserWorkspace = Depends(get_user_workspace),
    manager: PluginManager = Depends(get_plugin_manager),
):
    """Get plugin settings."""
    try:
        settings = manager.get_plugin_settings(plugin_id)

        if settings is None:
            raise HTTPException(status_code=404, detail=f"Plugin not found: {plugin_id}")

        return settings

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error getting plugin settings: ")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{plugin_id}/settings")
async def update_plugin_settings(
    plugin_id: str,
    request: UpdatePluginSettingsRequest,
    workspace: UserWorkspace = Depends(get_user_workspace),
    manager: PluginManager = Depends(get_plugin_manager),
):
    """Update plugin settings."""
    try:
        settings = manager.get_plugin_settings(plugin_id)

        if settings is None:
            raise HTTPException(status_code=404, detail=f"Plugin not found: {plugin_id}")

        # Build updated settings
        updated = {}

        if request.enabled is not None:
            updated["enabled"] = request.enabled

        if request.settings is not None:
            updated["settings"] = {**settings.get("settings", {}), **request.settings}

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

        return {"success": True, "settings": manager.get_plugin_settings(plugin_id)}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error updating plugin settings: ")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{plugin_id}/action")
async def plugin_action(
    plugin_id: str,
    request: PluginActionRequest,
    workspace: UserWorkspace = Depends(get_user_workspace),
    manager: PluginManager = Depends(get_plugin_manager),
):
    """Perform action on plugin (enable, disable, activate, deactivate, reload)."""
    logger.info(f"[DEBUG] plugin_action called: plugin_id={plugin_id}, action={request.action}")
    try:
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

            logger.info(f"[DEBUG] Saved plugins_config to file")

            if plugin.is_activated:
                result = await manager.deactivate_plugin(plugin_id)
                if not result:
                    logger.warning(f"Failed to deactivate plugin {plugin_id} during disable")
            else:
                result = True

        elif action == "activate":
            result = await manager.activate_plugin(plugin_id)
            if not result:
                logger.warning(f"Failed to activate plugin {plugin_id}")

        elif action == "deactivate":
            result = await manager.deactivate_plugin(plugin_id)
            if not result:
                # Already deactivated is not an error
                logger.info(f"Plugin {plugin_id} is already deactivated")
                result = True  # Consider it success

        elif action == "reload":
            result = await manager.reload_plugin(plugin_id)
            if not result:
                logger.warning(f"Failed to reload plugin {plugin_id}")

        else:
            raise HTTPException(status_code=400, detail=f"Unknown action: {action}")

        if not result:
            raise HTTPException(status_code=500, detail=f"Failed to {action} plugin")

        return {"success": True, "action": action, "plugin_id": plugin_id}

    except HTTPException:
        raise
    except Exception as e:
        # Fast fail: log full stack trace AND return it to client
        import traceback
        stack_trace = traceback.format_exc()
        logger.error(f"Error performing plugin action: {e}\n{stack_trace}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": str(e),
                "type": type(e).__name__,
                "traceback": stack_trace,
            }
        )


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
    try:
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

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error getting plugin config schema: ")
        raise HTTPException(status_code=500, detail=str(e))


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
    try:
        is_valid, errors = manager.validate_config(plugin_id, request.config)

        return {
            "valid": is_valid,
            "errors": errors,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error validating plugin config: ")
        raise HTTPException(status_code=500, detail=str(e))


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
    try:
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

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error saving plugin config: ")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{plugin_id}/config/new")
async def get_plugin_config_v2(
    plugin_id: str,
    workspace: UserWorkspace = Depends(get_user_workspace),
) -> dict[str, Any]:
    """获取单个插件配置（两层配置系统）

    返回指定插件的配置，如果不存在则返回默认配置
    """
    try:
        # 确保工作区已初始化
        if not workspace.is_initialized():
            await workspace.initialize()

        # 加载插件配置
        if workspace.plugins_config is None:
            await workspace._load_plugins_config()

        # 获取插件配置
        plugin_config = workspace.plugins_config.get_plugin_config(plugin_id)

        if plugin_config is None:
            # 返回默认配置
            return {
                "plugin_id": plugin_id,
                "enabled": True,
                "activated": False,
                "settings": {},
                "version": None,
                "install_path": None,
                "exists": False,
            }

        return {
            "plugin_id": plugin_id,
            "exists": True,
            **plugin_config.model_dump(),
        }

    except Exception as e:
        logger.exception(f"Failed to get plugin config for {plugin_id}: ")
        raise HTTPException(status_code=500, detail=f"Failed to get plugin config: {e!s}")


@router.put("/{plugin_id}/config/new")
async def update_plugin_config_v2(
    plugin_id: str,
    request: UpdatePluginSettingsRequest,
    workspace: UserWorkspace = Depends(get_user_workspace),
) -> dict[str, Any]:
    """更新单个插件配置（两层配置系统）

    请求体示例：
    {
        "enabled": true,
        "settings": {"api_key": "new-key"}
    }
    """
    try:
        # 确保工作区已初始化
        if not workspace.is_initialized():
            await workspace.initialize()

        # 加载插件配置
        if workspace.plugins_config is None:
            await workspace._load_plugins_config()

        # 获取或创建插件配置
        plugin_config = workspace.plugins_config.get_plugin_config(plugin_id)
        if plugin_config is None:
            plugin_config = PluginInstanceConfig()
            workspace.plugins_config.set_plugin_config(plugin_id, plugin_config)

        # 更新字段
        if request.enabled is not None:
            plugin_config.enabled = request.enabled
        if request.settings is not None:
            plugin_config.settings.update(request.settings)

        # 保存配置
        await workspace._save_plugins_config()

        logger.info(f"Plugin config updated for {plugin_id}")

        return {
            "success": True,
            "plugin_id": plugin_id,
            **plugin_config.model_dump(),
        }

    except Exception as e:
        logger.exception(f"Failed to update plugin config for {plugin_id}: ")
        raise HTTPException(status_code=500, detail=f"Failed to update plugin config: {e!s}")


@router.post("/{plugin_id}/enable")
async def enable_plugin_v2(
    plugin_id: str,
    workspace: UserWorkspace = Depends(get_user_workspace),
    manager: PluginManager = Depends(get_plugin_manager),
) -> dict[str, Any]:
    """启用插件（两层配置系统）"""
    try:
        # 确保工作区已初始化
        if not workspace.is_initialized():
            await workspace.initialize()

        # 加载插件配置
        if workspace.plugins_config is None:
            await workspace._load_plugins_config()

        # 启用插件
        workspace.plugins_config.enable_plugin(plugin_id)

        # 同步更新 PluginManager.registry 中的 settings
        plugin_config = workspace.plugins_config.plugins.get(plugin_id)
        if plugin_config:
            await manager.update_plugin_settings(plugin_id, {
                "enabled": plugin_config.enabled,
                "activated": plugin_config.activated,
                **plugin_config.settings
            })

        # 保存配置
        await workspace._save_plugins_config()

        logger.info(f"Plugin {plugin_id} enabled")

        return {"success": True, "plugin_id": plugin_id, "enabled": True}

    except Exception as e:
        logger.exception(f"Failed to enable plugin {plugin_id}: ")
        raise HTTPException(status_code=500, detail=f"Failed to enable plugin: {e!s}")


@router.post("/{plugin_id}/disable")
async def disable_plugin_v2(
    plugin_id: str,
    workspace: UserWorkspace = Depends(get_user_workspace),
    manager: PluginManager = Depends(get_plugin_manager),
) -> dict[str, Any]:
    """禁用插件（两层配置系统）"""
    try:
        # 确保工作区已初始化
        if not workspace.is_initialized():
            await workspace.initialize()

        # 加载插件配置
        if workspace.plugins_config is None:
            await workspace._load_plugins_config()

        # 禁用插件
        workspace.plugins_config.disable_plugin(plugin_id)

        # 同步更新 PluginManager.registry 中的 settings
        plugin_config = workspace.plugins_config.plugins.get(plugin_id)
        if plugin_config:
            await manager.update_plugin_settings(plugin_id, {
                "enabled": plugin_config.enabled,
                "activated": plugin_config.activated,
                **plugin_config.settings
            })

        # 保存配置
        await workspace._save_plugins_config()

        logger.info(f"Plugin {plugin_id} disabled")

        return {"success": True, "plugin_id": plugin_id, "enabled": False}

    except Exception as e:
        logger.exception(f"Failed to disable plugin {plugin_id}: ")
        raise HTTPException(status_code=500, detail=f"Failed to disable plugin: {e!s}")


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
    try:
        # 确保工作区已初始化
        if not workspace.is_initialized():
            await workspace.initialize()

        # 智能处理：根据plugin_id格式选择卸载方式
        if "@" in plugin_id:
            # 完整ID格式：尝试精确卸载
            success = await manager.uninstall_plugin(plugin_id)

            if not success:
                # 如果精确卸载失败，尝试按名称卸载（版本可能不匹配）
                plugin_name = plugin_id.split("@")[0]
                logger.warning(
                    f"Failed to uninstall {plugin_id}, trying by name '{plugin_name}'"
                )
                success = await manager.uninstall_plugin_by_name(plugin_name)

                if success:
                    logger.info(f"Uninstalled plugin by name: {plugin_name}")
                    return {
                        "success": True,
                        "plugin_id": plugin_name,
                        "message": f"Plugin {plugin_name} (version may differ) has been uninstalled"
                    }
                else:
                    # 仍然失败，返回404
                    raise HTTPException(
                        status_code=404,
                        detail=f"Plugin {plugin_id} not found or cannot be uninstalled"
                    )
            else:
                logger.info(f"Plugin {plugin_id} uninstalled successfully")
                return {
                    "success": True,
                    "plugin_id": plugin_id,
                    "message": f"Plugin {plugin_id} has been uninstalled"
                }
        else:
            # 仅名称格式：卸载所有版本
            success = await manager.uninstall_plugin_by_name(plugin_id)

            if success:
                logger.info(f"Plugin {plugin_id} uninstalled successfully")
                return {
                    "success": True,
                    "plugin_id": plugin_id,
                    "message": f"Plugin {plugin_id} has been uninstalled"
                }
            else:
                raise HTTPException(
                    status_code=404,
                    detail=f"Plugin {plugin_id} not found or cannot be uninstalled"
                )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to uninstall plugin {plugin_id}: ")
        raise HTTPException(status_code=500, detail=str(e))
