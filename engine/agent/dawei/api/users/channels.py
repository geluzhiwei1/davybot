# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""用户级 Channels API。

IM 通道注册本就是全局存储（``{DAWEI_HOME}/configs/channels.json``）——workspace 级路由
handler 也忽略 workspace_id。此路由提供 ``/api/users/me/channels`` 入口，复用 workspace 级
``channels.py`` 的 helper 与 bridge 逻辑，是「路径归位」兼容层：不改存储与现有端点，
enable/disable 行为与 workspace 级端点完全一致（同一全局 bridge）。
"""

import logging

from fastapi import APIRouter, HTTPException

from dawei.api.workspaces.channels import (
    ChannelEnableResponse,
    ChannelInfo,
    ChannelsListResponse,
    _build_channel_info,
    _ensure_channels_registered,
    _get_channel_description,
    _is_channel_enabled,
    _is_channel_running,
    _set_channel_enabled,
)
from dawei.channels.channel_manager import ChannelRegistry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/me/channels", tags=["User Channels"])


@router.get("", response_model=ChannelsListResponse)
async def list_user_channels():
    """列出所有已注册的 channel 类型及其能力和状态（user 级入口）"""
    _ensure_channels_registered()
    channel_types = ChannelRegistry.list_channels()
    channels = [_build_channel_info(ct) for ct in sorted(channel_types)]
    return ChannelsListResponse(success=True, channels=channels)


@router.get("/registered", response_model=ChannelsListResponse)
async def list_user_registered_channels():
    """获取所有自动发现的 channel 类型（简短列表，user 级入口）"""
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


@router.post("/{channel_type}/enable", response_model=ChannelEnableResponse)
async def enable_user_channel(channel_type: str):
    """启用 channel（user 级入口；行为与 workspace 级一致：保存 enabled 并尝试启动）"""
    _ensure_channels_registered()

    factory = ChannelRegistry.get_factory(channel_type)
    if not factory:
        raise HTTPException(status_code=404, detail=f"Channel type '{channel_type}' 未注册")

    _set_channel_enabled(channel_type, True)
    logger.info("Channel '%s' enabled (user-level entry)", channel_type)

    running = False
    try:
        from dawei.channels.bridge import get_global_bridge

        bridge = get_global_bridge()
        if bridge and bridge.is_running:
            running = await bridge.start_channel(channel_type)
            if running:
                logger.info("Channel '%s' started successfully", channel_type)
    except ImportError:
        logger.warning("ChannelBridge not available, channel marked enabled but not started")
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
async def disable_user_channel(channel_type: str):
    """禁用 channel（user 级入口；行为与 workspace 级一致：保存 enabled=false 并停止）"""
    _ensure_channels_registered()

    _set_channel_enabled(channel_type, False)
    logger.info("Channel '%s' disabled (user-level entry)", channel_type)

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
