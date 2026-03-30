# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Channel Management API Routes

List registered channels, check health, configure and enable/disable channels.
Follows the same pattern as acp_agents.py.

Config persistence format (channels.json):
{
  "feishu": {
    "_enabled": true,
    "app_id": "...",
    "app_secret": "..."
  },
  "telegram": {
    "_enabled": false,
    "bot_token": "..."
  }
}

Channel status has 3 states:
- registered: Channel class exists (auto-discovered), not enabled
- enabled: Config saved with _enabled=true, not running yet
- running: Channel instance is alive and processing messages
"""

import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Any, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from dawei import get_dawei_home
from dawei.channels.channel_manager import (
    ChannelRegistry,
    _ensure_channels_registered,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/{workspace_id}/channels", tags=["channels"])

# Internal key for enabled flag in persisted config
_ENABLED_KEY = "_enabled"


# --- Config Persistence ---


def _channel_config_file() -> Path:
    """Return path to ``{DAWEI_HOME}/configs/channels.json``."""
    return get_dawei_home() / "configs" / "channels.json"


def _load_channel_configs() -> dict[str, dict[str, Any]]:
    """Load persisted channel configs from disk."""
    path = _channel_config_file()
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.warning("Failed to load channel configs: %s", exc)
        return {}


def _save_channel_configs(configs: dict[str, dict[str, Any]]) -> None:
    """Persist channel configs to disk."""
    path = _channel_config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(configs, f, indent=2, ensure_ascii=False)
    logger.debug("Channel configs saved: %s (%d channels)", path, len(configs))


def _get_saved_config(channel_type: str) -> dict[str, Any]:
    """Get saved config for a specific channel type (excludes _enabled key)."""
    configs = _load_channel_configs()
    saved = configs.get(channel_type, {})
    return {k: v for k, v in saved.items() if k != _ENABLED_KEY}


def _is_channel_enabled(channel_type: str) -> bool:
    """Check if a channel is enabled in persisted config."""
    configs = _load_channel_configs()
    entry = configs.get(channel_type, {})
    return entry.get(_ENABLED_KEY, False)


def _set_channel_enabled(channel_type: str, enabled: bool) -> None:
    """Set enabled flag for a channel without overwriting its config."""
    configs = _load_channel_configs()
    if channel_type not in configs:
        configs[channel_type] = {}
    configs[channel_type][_ENABLED_KEY] = enabled
    _save_channel_configs(configs)


def _update_saved_config(channel_type: str, config: dict[str, Any], enabled: bool | None = None) -> None:
    """Update saved config for a specific channel type.

    Args:
        channel_type: Channel type identifier
        config: Config dict (without _enabled key)
        enabled: Optional enabled flag. None = keep current value.
    """
    configs = _load_channel_configs()
    current_enabled = configs.get(channel_type, {}).get(_ENABLED_KEY, False)
    entry = {**config}
    entry[_ENABLED_KEY] = enabled if enabled is not None else current_enabled
    configs[channel_type] = entry
    _save_channel_configs(configs)


def _is_channel_running(channel_type: str) -> bool:
    """Check if a channel has an active running instance in ChannelBridge."""
    try:
        from dawei.channels.bridge import get_global_bridge
        bridge = get_global_bridge()
        if bridge and bridge.is_running:
            return channel_type in bridge.list_active_channels()
    except ImportError:
        pass
    return False


# --- Request / Response Models ---


class ChannelCapabilityInfo(BaseModel):
    """Serialized channel capabilities."""

    format_type: str = "plain"
    max_text_length: int = 4096
    streaming: bool = False
    threading: bool = False
    reactions: bool = False
    typing: bool = False
    media_send: bool = False
    media_receive: bool = False
    voice: bool = False
    groups: bool = False
    mentions: bool = False
    markdown: bool = False
    html: bool = False
    chat_types: list[str] = []


class ChannelInfo(BaseModel):
    """Info about a registered channel type."""

    channel_type: str
    registered: bool = True
    enabled: bool = False
    running: bool = False
    capabilities: ChannelCapabilityInfo = ChannelCapabilityInfo()
    config_fields: dict[str, Any] = Field(default_factory=dict)
    description: str = ""


class ChannelsListResponse(BaseModel):
    """List of all registered channels."""

    success: bool = True
    channels: List[ChannelInfo] = Field(default_factory=list)


class ChannelHealthResponse(BaseModel):
    """Health status of a single channel."""

    success: bool = True
    channel_type: str = ""
    healthy: bool = False
    message: str = ""
    latency_ms: float = 0.0


class ChannelsHealthResponse(BaseModel):
    """Health status of all channels."""

    success: bool = True
    health: dict[str, ChannelHealthResponse] = Field(default_factory=dict)


class ChannelConfigureRequest(BaseModel):
    """Enable / disable a channel for the workspace."""

    enabled: bool = Field(True, description="True to enable, False to disable")
    config: dict[str, Any] = Field(default_factory=dict, description="Channel-specific config")


class ChannelConfigureResponse(BaseModel):
    """Result of channel configuration."""

    success: bool = True
    message: str = ""


class ChannelEnableResponse(BaseModel):
    """Result of enable/disable operation."""

    success: bool = True
    message: str = ""
    channel_type: str = ""
    enabled: bool = False
    running: bool = False


# --- Helpers ---


def _caps_to_info(caps: Any) -> ChannelCapabilityInfo:
    """Convert a ChannelCapabilities dataclass to serializable model."""
    d = asdict(caps)
    return ChannelCapabilityInfo(
        format_type=d.get("format_type", "plain"),
        max_text_length=d.get("max_text_length", 4096),
        streaming=d.get("streaming", False),
        threading=d.get("threading", False),
        reactions=d.get("reactions", False),
        typing=d.get("typing", False),
        media_send=d.get("media_send", False),
        media_receive=d.get("media_receive", False),
        voice=d.get("voice", False),
        groups=d.get("groups", False),
        mentions=d.get("mentions", False),
        markdown=d.get("markdown", False),
        html=d.get("html", False),
        chat_types=list(d.get("chat_types", [])),
    )


def _get_config_fields(channel_type: str) -> dict[str, Any]:
    """Extract config field names and defaults from the channel's Config class."""
    import dataclasses
    import importlib

    try:
        module = importlib.import_module(f"dawei.channels.{channel_type}")
        config_cls = getattr(module, "Config", None)
        if config_cls and dataclasses.is_dataclass(config_cls):
            fields = {}
            for f in dataclasses.fields(config_cls):
                if f.name == "enabled":
                    continue
                fields[f.name] = (
                    f.default if f.default is not dataclasses.MISSING
                    else f"default_factory" if hasattr(f, "default_factory") and f.default_factory is not dataclasses.MISSING
                    else None
                )
            return fields
    except Exception:
        pass
    return {}


def _get_channel_description(channel_type: str) -> str:
    """Get the docstring summary from a channel module."""
    import importlib

    try:
        module = importlib.import_module(f"dawei.channels.{channel_type}")
        doc = getattr(module, "__doc__", "") or ""
        for line in doc.strip().splitlines():
            line = line.strip()
            if line:
                return line
    except Exception:
        pass
    return ""


def _build_channel_info(ct: str) -> ChannelInfo:
    """Build a ChannelInfo object for a registered channel type."""
    factory = ChannelRegistry.get_factory(ct)
    caps = ChannelCapabilityInfo()
    if factory:
        try:
            from dawei.channels import BaseChannelConfig, MessageBus
            tmp_bus = MessageBus()
            tmp_cfg = BaseChannelConfig()
            tmp_ch = factory(tmp_cfg, tmp_bus)
            caps = _caps_to_info(tmp_ch.capabilities)
        except Exception:
            pass

    # Merge saved config into config_fields
    saved = _get_saved_config(ct)
    default_fields = _get_config_fields(ct)
    config_fields = {**default_fields, **saved} if saved else default_fields

    enabled = _is_channel_enabled(ct)
    running = _is_channel_running(ct)

    return ChannelInfo(
        channel_type=ct,
        registered=True,
        enabled=enabled,
        running=running,
        capabilities=caps,
        config_fields=config_fields,
        description=_get_channel_description(ct),
    )


# --- API Endpoints ---


@router.get("", response_model=ChannelsListResponse)
async def list_channels(workspace_id: str):
    """列出所有已注册的 channel 类型及其能力和状态"""
    _ensure_channels_registered()

    channel_types = ChannelRegistry.list_channels()
    channels = [_build_channel_info(ct) for ct in sorted(channel_types)]

    return ChannelsListResponse(success=True, channels=channels)


@router.get("/registered", response_model=ChannelsListResponse)
async def get_registered_channels(workspace_id: str):
    """获取所有自动发现的 channel 类型（简短列表）"""
    _ensure_channels_registered()
    channel_types = ChannelRegistry.list_channels()
    channels = [
        ChannelInfo(
            channel_type=ct,
            registered=True,
            enabled=_is_channel_enabled(ct),
            running=_is_channel_running(ct),
            description=_get_channel_description(ct),
        )
        for ct in sorted(channel_types)
    ]
    return ChannelsListResponse(success=True, channels=channels)


@router.get("/health", response_model=ChannelsHealthResponse)
async def health_check_all(workspace_id: str):
    """检查所有 channel 的健康状态"""
    _ensure_channels_registered()

    # Try to get real health from running channels
    running_health: dict[str, ChannelHealthResponse] = {}
    try:
        from dawei.channels.bridge import get_global_bridge
        bridge = get_global_bridge()
        if bridge and bridge.channel_manager:
            real_health = await bridge.channel_manager.health_check_all()
            for ct, h in real_health.items():
                running_health[ct] = ChannelHealthResponse(
                    success=True,
                    channel_type=ct,
                    healthy=h.healthy,
                    message=h.message,
                    latency_ms=h.latency_ms,
                )
    except ImportError:
        pass

    # Fill in non-running channels
    channel_types = ChannelRegistry.list_channels()
    health_map: dict[str, ChannelHealthResponse] = {}
    for ct in channel_types:
        if ct in running_health:
            health_map[ct] = running_health[ct]
        elif _is_channel_enabled(ct):
            health_map[ct] = ChannelHealthResponse(
                success=True,
                channel_type=ct,
                healthy=False,
                message="Channel enabled but not running",
            )
        else:
            health_map[ct] = ChannelHealthResponse(
                success=True,
                channel_type=ct,
                healthy=False,
                message="Channel registered but not enabled",
            )

    return ChannelsHealthResponse(success=True, health=health_map)


@router.get("/{channel_type}", response_model=ChannelInfo)
async def get_channel_detail(workspace_id: str, channel_type: str):
    """获取单个 channel 类型的详细信息"""
    _ensure_channels_registered()

    factory = ChannelRegistry.get_factory(channel_type)
    if not factory:
        raise HTTPException(status_code=404, detail=f"Channel type '{channel_type}' 未注册")

    return _build_channel_info(channel_type)


@router.put("/{channel_type}/config", response_model=ChannelConfigureResponse)
async def configure_channel(
    workspace_id: str,
    channel_type: str,
    request: ChannelConfigureRequest,
):
    """更新 channel 配置"""
    _ensure_channels_registered()

    factory = ChannelRegistry.get_factory(channel_type)
    if not factory:
        raise HTTPException(status_code=404, detail=f"Channel type '{channel_type}' 未注册")

    try:
        _update_saved_config(channel_type, request.config, enabled=request.enabled)
        logger.info(
            "Channel '%s' config updated for workspace '%s' (enabled=%s)",
            channel_type, workspace_id, request.enabled,
        )
        return ChannelConfigureResponse(
            success=True,
            message=f"Channel '{channel_type}' 配置已保存",
        )
    except Exception as exc:
        logger.error("Failed to configure channel '%s': %s", channel_type, exc)
        raise HTTPException(status_code=500, detail=f"配置保存失败: {exc}") from exc


@router.post("/{channel_type}/enable", response_model=ChannelEnableResponse)
async def enable_channel(workspace_id: str, channel_type: str):
    """启用 channel：保存 enabled=true 并尝试启动"""
    _ensure_channels_registered()

    factory = ChannelRegistry.get_factory(channel_type)
    if not factory:
        raise HTTPException(status_code=404, detail=f"Channel type '{channel_type}' 未注册")

    _set_channel_enabled(channel_type, True)
    logger.info("Channel '%s' enabled for workspace '%s'", channel_type, workspace_id)

    # Try to start the channel via bridge
    running = False
    try:
        from dawei.channels.bridge import get_global_bridge
        bridge = get_global_bridge()
        if bridge and bridge.is_running:
            running = await bridge.start_channel(channel_type)
            if running:
                logger.info("Channel '%s' started successfully", channel_type)
            else:
                logger.warning("Channel '%s' enabled but failed to start", channel_type)
    except ImportError:
        logger.warning("ChannelBridge not available, channel marked as enabled but not started")
    except Exception as exc:
        logger.error("Failed to start channel '%s': %s", channel_type, exc)

    return ChannelEnableResponse(
        success=True,
        message=f"Channel '{channel_type}' 已启用" + ("并正在运行" if running else "（等待重启后生效）"),
        channel_type=channel_type,
        enabled=True,
        running=running,
    )


@router.post("/{channel_type}/disable", response_model=ChannelEnableResponse)
async def disable_channel(workspace_id: str, channel_type: str):
    """禁用 channel：保存 enabled=false 并停止运行中的实例"""
    _ensure_channels_registered()

    _set_channel_enabled(channel_type, False)
    logger.info("Channel '%s' disabled for workspace '%s'", channel_type, workspace_id)

    # Try to stop the running channel
    try:
        from dawei.channels.bridge import get_global_bridge
        bridge = get_global_bridge()
        if bridge and bridge.is_running:
            await bridge.stop_channel(channel_type)
            logger.info("Channel '%s' stopped", channel_type)
    except ImportError:
        pass
    except Exception as exc:
        logger.error("Failed to stop channel '%s': %s", channel_type, exc)

    return ChannelEnableResponse(
        success=True,
        message=f"Channel '{channel_type}' 已禁用",
        channel_type=channel_type,
        enabled=False,
        running=False,
    )
