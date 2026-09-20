# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""设备管理 API(方案 §9.3)—— 「我的设备」列表 / 重命名 / 远程登出。

数据源 = MCP relay 注册表的 device 模型(tools/mcp_relay.py,§8.2):
presence(心跳=claim/register)、label(首注册壳上报 hostname · OS,用户可
改)、client_version、revoked。仅管理自己 user_id 名下设备(JWT 隔离)。

远程登出落地(在线/离线两路都覆盖,§9.3):
- 在线设备:向该设备定向投递 ``device/logout`` 控制帧(在档 claim 立即
  唤醒)→ 壳 DELETE relay、清本地凭证、toast、重新生成 device_id;
- 离线/失联设备:revoked 标记常驻,其下次 register/claim → 403
  device_logged_out(见 mcp_relay.py)→ 壳同样本地登出。

登出不删本机浏览器登录态(cookies 属桌面数据);重新登录即重新绑定
(新设备身份)。is_current 由前端与本地 device.json 比对,云端不判断。
"""

import logging
import time
from collections import deque
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from dawei.api.auth import get_authenticated_user_id
from dawei.tools.mcp_relay import DEVICE_ID_RE, get_relay_registry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/me/devices", tags=["User Devices"])

# 远程登出限频(§9.5:kick 5 次/小时/用户;防误触/滥用)。
KICK_RATE_LIMIT = 5
KICK_RATE_WINDOW = 3600.0

_kick_rate: dict[str, deque[float]] = {}


def _check_kick_rate(user_id: str) -> None:
    """滑动窗口限流(单事件循环内同步执行,无锁)。"""
    now = time.monotonic()
    window = _kick_rate.setdefault(user_id, deque())
    while window and now - window[0] > KICK_RATE_WINDOW:
        window.popleft()
    if len(window) >= KICK_RATE_LIMIT:
        retry = max(0.0, KICK_RATE_WINDOW - (now - window[0]))
        raise HTTPException(
            status_code=429,
            detail=f"rate limit: {KICK_RATE_LIMIT} kicks/hour, retry after {retry:.0f}s",
        )
    window.append(now)


def _validate_device_id(device_id: str) -> str:
    if not DEVICE_ID_RE.match(device_id):
        raise HTTPException(status_code=400, detail=f"invalid device id: {device_id[:16]}")
    return device_id


class RenameRequest(BaseModel):
    label: str = Field(..., min_length=1, max_length=64, description="设备显示名")


class DeviceListResponse(BaseModel):
    success: bool = True
    devices: list[dict[str, Any]] = Field(default_factory=list)


class SimpleResponse(BaseModel):
    success: bool = True


@router.get("", response_model=DeviceListResponse)
async def list_my_devices(current_user: str = Depends(get_authenticated_user_id)):
    """设备列表(§9.4):online/label/version/last_seen/revoked/servers。
    is_current 由前端与本地 device.json 比对,纯浏览器访问时全部为远程设备。"""
    return DeviceListResponse(devices=get_relay_registry().devices(current_user))


@router.post("/{device_id}/rename", response_model=SimpleResponse)
async def rename_my_device(device_id: str, request: RenameRequest, current_user: str = Depends(get_authenticated_user_id)):
    """重命名设备(辨识「公司 MacBook / 家里 PC」);下一次壳 register 不会
    覆盖(label 仅首注册生效)。"""
    _validate_device_id(device_id)
    ok = get_relay_registry().rename_device(current_user, device_id, request.label)
    if not ok:
        raise HTTPException(status_code=404, detail=f"device '{device_id[:8]}' not found")
    logger.info(f"relay device renamed (user={current_user}, device={device_id[:8]}, label={request.label})")
    return SimpleResponse()


@router.delete("/{device_id}", response_model=SimpleResponse)
async def revoke_my_device(device_id: str, current_user: str = Depends(get_authenticated_user_id)):
    """远程登出(§9.3):revoked 标记 + 解绑 + device/logout 控制帧(在线设备
    在档 claim 立即收到)。离线设备标记常驻,重连即 403。限频 5 次/小时。"""
    _validate_device_id(device_id)
    _check_kick_rate(current_user)
    ok = get_relay_registry().revoke_device(current_user, device_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"device '{device_id[:8]}' not found")
    logger.warning(f"relay device remote-logout (user={current_user}, device={device_id[:8]})")
    return SimpleResponse()
