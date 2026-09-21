# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""用户级本机 MCP relay API —— davy-light-app 壳的 claim/result 通道。

壳侧协议(全部携带 Authorization: Bearer <jwt>,协议总览见
dawei/tools/mcp_relay.py 模块注释;设备模型 = 方案 §8.2):

    POST   /api/users/me/mcp-relay/register   上线注册(device_id + 本机 server 清单,全量覆盖该设备)
    POST   /api/users/me/mcp-relay/claim      长轮询领取 JSON-RPC 帧(定向给自己 + 广播)
    POST   /api/users/me/mcp-relay/result     回报响应帧
    GET    /api/users/me/mcp-relay/servers    聚合在线状态 + per-device 视图
    POST   /api/users/me/mcp-relay/call       web/SaaS → 桌面 tool 调用入口(方案 §5.2;可定向 device_id)
    DELETE /api/users/me/mcp-relay?device_id= 单设备下线(登出解绑,不影响他设备)

错误语义(FAST FAIL):register 的 device_id 粘性冲突 → 409 device_bound;
revoked 设备 register/claim → 403 device_logged_out;claim 定向帧送达优先
(保证 device/logout 控制帧可达,送完再 403)。

register/unregister 的聚合 server 面变化会触发该用户全部 WorkspaceContext
的 MCP 配置 areload(stub 配置面 = transport="local" 的影子配置)。
"""

import asyncio
import json
import logging
import time
from collections import deque
from itertools import count
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from dawei.api.auth import get_authenticated_user_id
from dawei.tools.mcp_relay import (
    NAME_RE,
    DeviceBoundError,
    DeviceRevokedError,
    RelayServerSpec,
    get_relay_registry,
    host_device,
)
from dawei.tools.mcp_relay import logger as relay_logger

from .mcp import _areload_all_workspace_mcp

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/me/mcp-relay", tags=["User MCP Relay"])


# --- Models ---


class RelayServerIn(BaseModel):
    name: str = Field(..., description="本机 server 名称(与云端 stub 配置同名)")
    timeout: int = Field(300, description="单帧(call_tool)超时秒数")


class RegisterRequest(BaseModel):
    client: str = Field("light-app", description="客户端标识")
    device_id: str = Field("", description="安装级设备 ID(device.json;空 = 旧版壳)")
    client_id: str = Field("", description="device_id 别名(旧字段,P0 遗留)")
    label: str = Field("", description="设备显示名(仅首注册生效,如 'MacBook · macOS'")
    client_version: str = Field("", description="壳版本(能力漂移提示用)")
    servers: list[RelayServerIn] = Field(default_factory=list, description="本机 server 清单(全量)")


class RegisterResponse(BaseModel):
    success: bool = True
    servers: list[str] = Field(default_factory=list)
    changed: bool = False
    heartbeat_seconds: float = 90.0


class ClaimRequest(BaseModel):
    device_id: str = Field("", description="领取设备 ID(空 = 旧版壳伪设备)")
    wait: float = Field(25.0, ge=0, le=30, description="长轮询 hold 秒数")
    limit: int = Field(8, ge=1, le=16, description="单次领取帧数上限")


class ClaimResponse(BaseModel):
    success: bool = True
    frames: list[dict[str, Any]] = Field(default_factory=list)


class ResultRequest(BaseModel):
    device_id: str = Field("", description="回报设备 ID(审计用;配对按帧 id)")
    id: str = Field(..., description="帧 id(claim 返回)")
    message: dict[str, Any] | None = Field(None, description="JSON-RPC 响应帧")
    error: str | None = Field(None, description="执行错误(合成 JSON-RPC error 回填)")


class ResultResponse(BaseModel):
    success: bool = True


class RelayCallRequest(BaseModel):
    server: str = Field(..., description="目标本机 server 名(如 dawei-track)")
    tool: str = Field(..., description="MCP tool 名(如 browser_verify)")
    arguments: dict[str, Any] = Field(default_factory=dict, description="tool 入参")
    device_id: str | None = Field(
        None, description="定向设备(§8.3 有副作用命令必选;缺省 = 唯一在线托管设备自动路由,多台则广播)"
    )


# --- Endpoints ---


@router.post("/register", response_model=RegisterResponse)
async def register_local_mcp(request: RegisterRequest, current_user: str = Depends(get_authenticated_user_id)):
    """壳上线/清单变化时注册(全量覆盖该设备)。聚合 server 面变化 → areload
    该用户全部 WorkspaceContext(stub 配置立即对 list_mcp_servers/连接可见)。

    设备语义(§8.2/§7.3/§9.3):同账号多桌面各自独立注册;device_id 已绑定
    其他用户 → 409 device_bound(须原账号登出解绑);revoked → 403。"""
    specs = []
    for s in request.servers:
        if not NAME_RE.match(s.name):
            raise HTTPException(status_code=400, detail=f"invalid server name: {s.name}")
        specs.append(RelayServerSpec(name=s.name, timeout=max(1, s.timeout)))

    device_id = (request.device_id or request.client_id).strip()
    try:
        names, changed = get_relay_registry().register(
            current_user,
            specs,
            device_id=device_id,
            label=request.label,
            client_version=request.client_version,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except DeviceBoundError as e:
        raise HTTPException(
            status_code=409,
            detail=(
                f"device_bound: 该设备已绑定其他账号(owner={e.owner_user[:8]}…);"
                "请先在原账号登出解绑后再切换账号"
            ),
        ) from e
    except DeviceRevokedError as e:
        raise HTTPException(
            status_code=403,
            detail="device_logged_out: 本设备已被账号所有者登出;请重新登录(将生成新设备身份)",
            # 结构化错误标记:壳侧 is_device_logged_out 优先按此头判定,
            # detail 措辞调整不影响契约(哨兵串仅作旧版兼容)。
            headers={"X-Relay-Error": "device_logged_out"},
        ) from e
    if changed:
        await _areload_all_workspace_mcp(current_user)

    logger.info(
        f"local mcp relay registered (user={current_user}, client={request.client}, "
        f"device={device_id[:8] or 'legacy'}, servers={names}, changed={changed})"
    )
    return RegisterResponse(servers=names, changed=changed)


@router.post("/claim", response_model=ClaimResponse)
async def claim_local_mcp_frames(request: ClaimRequest, current_user: str = Depends(get_authenticated_user_id)):
    """长轮询领取待执行帧(定向给自己 + 广播,先到先得);claim 本身即该设备
    心跳。revoked 设备:定向队列仍有帧 → 放行送达(device/logout 控制帧),
    送完 → 403 触发壳本地登出(§9.3)。真实设备不在档 → 409 device_unknown
    (服务端失忆自愈信号,见下方注释)。"""
    registry = get_relay_registry()
    device_id = request.device_id.strip()
    dev = registry.get_device(current_user, device_id) if device_id else None
    if dev is not None and dev.revoked and not registry.has_queued(current_user, device_id):
        raise HTTPException(
            status_code=403,
            detail="device_logged_out: 本设备已被账号所有者登出;请重新登录(将生成新设备身份)",
            headers={"X-Relay-Error": "device_logged_out"},  # 同 register:结构化标记优先
        )
    # 服务端失忆自愈:注册表为进程内存态,引擎重启即清空。若对未知真实设备
    # 沿用"空返回"旧语义,壳侧 claim 永远 200 空帧、无从感知,内置 MCP 在
    # 服务端视角永久离线(repos relay.rs 只在配置签名变化时 register)。
    # 故 FAST FAIL 返回 409 device_unknown,壳清 registered_sig 后重新
    # register。legacy 伪设备(空 device_id)保持空返回语义不变。
    if device_id and dev is None:
        raise HTTPException(
            status_code=409,
            detail="device_unknown: 设备未在服务端注册(服务端可能已重启),请重新 register",
            headers={"X-Relay-Error": "device_unknown"},
        )
    frames = await registry.claim(current_user, device_id, request.wait, request.limit)
    return ClaimResponse(frames=frames)


@router.post("/result", response_model=ResultResponse)
async def report_local_mcp_result(request: ResultRequest, current_user: str = Depends(get_authenticated_user_id)):
    """回报响应帧(按帧 id 配对;未知/重复 id → 404)。"""
    ok = get_relay_registry().resolve(current_user, request.id, message=request.message, error=request.error)
    if not ok:
        raise HTTPException(status_code=404, detail=f"frame '{request.id}' not found (already resolved?)")
    return ResultResponse()


@router.get("/servers")
async def get_local_mcp_servers(current_user: str = Depends(get_authenticated_user_id)):
    """聚合在线状态与 server 并集(前端 presence/兼容形态)+ per-device 视图。"""
    return {"success": True, **get_relay_registry().get_servers(current_user)}


# ── /call:web/SaaS → 桌面 tool 调用(方案 §5.2)────────────────
# 与 ClientSession 会话帧共用同一队列/壳,只是帧由云端合成。

# 限流:10 次/分钟/用户(防 web 端 bug 打爆队列;超限 FAST FAIL 不入队)。
CALL_RATE_LIMIT = 10
CALL_RATE_WINDOW = 60.0
# 等待包络:壳 claim 唤醒(≤30s)+ 本地执行(dawei-track timeout=70)+ 回报
# 余量 —— 取 75s 让桌面侧 70s 边界的超时错误帧先于 504 到达(用户看到具体
# 工具超时文案,而非笼统 504)。
CALL_TIMEOUT = 75.0

_call_ids = count(1)
_call_rate: dict[str, deque[float]] = {}


def _check_call_rate(user_id: str) -> None:
    """滑动窗口限流(单事件循环内同步执行,无锁)。"""
    now = time.monotonic()
    window = _call_rate.setdefault(user_id, deque())
    while window and now - window[0] > CALL_RATE_WINDOW:
        window.popleft()
    if len(window) >= CALL_RATE_LIMIT:
        retry = max(0.0, CALL_RATE_WINDOW - (now - window[0]))
        raise HTTPException(
            status_code=429,
            detail=f"rate limit: {CALL_RATE_LIMIT} calls/min, retry after {retry:.0f}s",
        )
    window.append(now)


def _parse_tool_payload(rpc_response: dict[str, Any]) -> Any:
    """/call 响应载荷提取:JSON-RPC error / isError → 502;成功取
    content[0].text(JSON 解析失败原样返回文本,FAST FAIL 不猜)。"""
    if isinstance(rpc_response.get("error"), dict):
        msg = rpc_response["error"].get("message") or rpc_response["error"]
        raise HTTPException(status_code=502, detail=f"tool error: {msg}")
    result = rpc_response.get("result")
    if not isinstance(result, dict):
        raise HTTPException(status_code=502, detail="tool error: malformed result payload")
    content = result.get("content")
    text = ""
    if isinstance(content, list) and content and isinstance(content[0], dict):
        text = str(content[0].get("text", ""))
    if result.get("isError"):
        raise HTTPException(status_code=502, detail=f"tool error: {text[:300] or 'isError without message'}")
    if text:
        try:
            return json.loads(text)
        except ValueError:
            return text
    return result


@router.post("/call")
async def call_local_mcp_tool(request: RelayCallRequest, current_user: str = Depends(get_authenticated_user_id)):
    """web/SaaS → 桌面 tool 调用入口:合成 tools/call JSON-RPC 帧入队(与
    ClientSession 会话帧同队列),等壳执行回报。离线/未注册 → 409,限流 →
    429,超时 → 504,工具错误 → 502(方案 §5.2)。

    路由(§8.3):显式 device_id → 定向(不存在 → 409);缺省 → 唯一在线
    托管设备自动定向,多台托管 → 广播先到先得。"""
    _check_call_rate(current_user)

    if not NAME_RE.match(request.server):
        raise HTTPException(status_code=400, detail=f"invalid server name: {request.server}")
    registry = get_relay_registry()
    device_id = (request.device_id or "").strip() or None
    if device_id is not None:
        dev = registry.get_device(current_user, device_id)
        if dev is None or dev.revoked:
            raise HTTPException(status_code=409, detail=f"设备不存在或已登出: {device_id[:8]}…")
    else:
        # 缺省路由与 transport=local 连接同源(§8.3 host_device):离线 → 409
        # 「离线」、无在线托管 → 409「未在桌面版注册」、唯一托管 → 定向、
        # 多台 → 广播。不得用「在档 spec 兜底」做预检 —— revoked/离线设备
        # 仍在设备表内时会绕过离线检查,把帧广播给无人认领,FAST FAIL
        # 退化成 75s 挂起(e2e 2026-09-19 回归)。
        try:
            device_id = host_device(current_user, request.server)
        except ConnectionError as e:
            raise HTTPException(status_code=409, detail=str(e)) from None

    frame_message = {
        "jsonrpc": "2.0",
        "id": f"call-{next(_call_ids)}",
        "method": "tools/call",
        "params": {"name": request.tool, "arguments": request.arguments},
    }
    try:
        frame_id, fut = registry.enqueue(current_user, request.server, frame_message, device_id=device_id)
    except KeyError:
        raise HTTPException(status_code=409, detail=f"设备不在线: {device_id[:8]}…") from None
    if fut is None:  # 理论不可达:method+id 必为请求帧
        raise HTTPException(status_code=500, detail="internal: synthesized frame lost its future")
    started = time.monotonic()
    try:
        response = await asyncio.wait_for(fut, timeout=CALL_TIMEOUT)
    except TimeoutError:
        relay_logger.warning(
            f"relay call timeout (user={current_user}, device={device_id or 'broadcast'}, "
            f"server={request.server}, tool={request.tool}, frame={frame_id})"
        )
        raise HTTPException(
            status_code=504,
            detail=f"tool '{request.tool}' timed out after {CALL_TIMEOUT:.0f}s (桌面版执行超时或响应丢失)",
        ) from None
    # 审计(§7.2-8:user/device/server/tool/ok/耗时;web 与云端 agent 共用)
    logger.info(
        f"relay call ok (user={current_user}, device={device_id or 'broadcast'}, "
        f"server={request.server}, tool={request.tool}, {time.monotonic() - started:.1f}s, frame={frame_id})"
    )
    return {"success": True, "frame_id": frame_id, "result": _parse_tool_payload(response)}


@router.delete("", response_model=ResultResponse)
async def unregister_local_mcp(
    device_id: str = "", current_user: str = Depends(get_authenticated_user_id)
):
    """单设备下线(登出):清该设备注册面 + 其帧错误回填 + areload 撤 stub;
    不影响该用户其他在线设备(§8.1)。真实设备同时解绑粘性映射(重新登录
    或换账号均需重新绑定)。"""
    removed = get_relay_registry().unregister(current_user, device_id.strip())
    if removed:
        await _areload_all_workspace_mcp(current_user)
        logger.info(f"local mcp relay unregistered (user={current_user}, device={device_id[:8] or 'legacy'})")
    return ResultResponse()
