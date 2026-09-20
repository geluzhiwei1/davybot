# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""WebSocket API 路由

Authentication: All WebSocket endpoints require a valid JWT token via
the ``token`` query parameter (``ws://host/ws?token=JWT``). The token is
decoded using the same ``jwt_secret`` / ``jwt_algorithm`` as the REST API
(shared with nn-user-system). The extracted ``user_id`` (JWT ``sub`` claim)
is passed down to ``handle_websocket`` so downstream code knows the caller.
"""

import jwt
from fastapi import APIRouter, HTTPException, Query, WebSocket
from jwt import InvalidTokenError
from starlette.websockets import WebSocketState

from dawei.config.settings import get_settings
from dawei.logg.logging import get_logger
from dawei.websocket.ws_server import websocket_server

router = APIRouter(tags=["websocket"])
logger = get_logger(__name__)


async def _authenticate_ws(websocket: WebSocket, token: str | None) -> str | None:
    """Validate JWT ``token`` and return the ``user_id`` (JWT ``sub``).

    On failure the WebSocket is closed with code 1008 and ``None`` is
    returned.  Callers MUST abort the request when ``None`` is returned.

    自包含模式 (无 auth capability, 即 server/tui — server 自包含方案):
    不走账号体系; ``DAWEI_SERVER_PASSWORD`` 设了则要求 ``token`` 为该
    密码, 未设放行; 通过后返回固定本地身份 ``local-user``。
    """
    from dawei.api.auth import LOCAL_USER_ID, _check_server_access_password_token
    from dawei.runtime import get_capabilities

    if "auth" not in get_capabilities():
        try:
            _check_server_access_password_token(token)
        except HTTPException:
            logger.warning("WS auth failed: access password required")
            if websocket.client_state != WebSocketState.DISCONNECTED:
                await websocket.close(code=1008, reason="access password required")
            return None
        return LOCAL_USER_ID

    if not token:
        await websocket.close(code=1008, reason="missing token")
        return None
    try:
        settings = get_settings()
        security = settings.security
        payload = jwt.decode(token, security.jwt_secret, algorithms=[security.jwt_algorithm])
        user_id = payload.get("sub")
        if not user_id:
            raise InvalidTokenError("missing sub claim")
        return str(user_id)
    except InvalidTokenError as exc:
        logger.warning(f"WS auth failed: {exc}")
        if websocket.client_state != WebSocketState.DISCONNECTED:
            await websocket.close(code=1008, reason="invalid token")
        return None


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str | None = Query(default=None),
    workspace_id: str | None = Query(default=None),
):
    """Generic WebSocket endpoint.

    workspace_id 转发至 handle_websocket 以绑定连接(工作区过滤广播的接收端,
    如 task_node_* / subtask_lifecycle);不传则注册为无工作区连接 —— 与
    /api/ws/chat 行为一致。前端 ws-client 连接时始终携带该参数。
    """
    user_id = await _authenticate_ws(websocket, token)
    if not user_id:
        return
    await websocket_server.handle_websocket(websocket, user_id=user_id, workspace_id=workspace_id)


@router.websocket("/api/chat/stream")
async def chat_stream_endpoint(websocket: WebSocket, token: str | None = Query(default=None)):
    """Chat streaming WebSocket endpoint."""
    user_id = await _authenticate_ws(websocket, token)
    if not user_id:
        return
    await websocket_server.handle_websocket(websocket, user_id=user_id)


@router.websocket("/api/ws/chat")
async def chat_websocket_endpoint(
    websocket: WebSocket,
    token: str | None = Query(default=None),
    session_id: str | None = None,
    workspace_id: str | None = None,
    conversation_id: str | None = None,
):
    """Chat WebSocket endpoint with query params."""
    user_id = await _authenticate_ws(websocket, token)
    if not user_id:
        return
    await websocket_server.handle_websocket(
        websocket,
        session_id=session_id,
        user_id=user_id,
        workspace_id=workspace_id,
        conversation_id=conversation_id,
    )


@router.websocket("/api/ws/stream")
async def stream_websocket_endpoint(
    websocket: WebSocket,
    token: str | None = Query(default=None),
    session_id: str | None = None,
    workspace_id: str | None = None,
):
    """Streaming WebSocket endpoint."""
    user_id = await _authenticate_ws(websocket, token)
    if not user_id:
        return
    await websocket_server.handle_websocket(
        websocket,
        session_id=session_id,
        user_id=user_id,
        workspace_id=workspace_id,
    )


@router.websocket("/ws/task")
async def task_websocket_endpoint(
    websocket: WebSocket,
    token: str | None = Query(default=None),
    session_id: str | None = None,
    workspace_id: str | None = None,
):
    """Task WebSocket endpoint."""
    user_id = await _authenticate_ws(websocket, token)
    if not user_id:
        return
    await websocket_server.handle_websocket(
        websocket,
        session_id=session_id,
        user_id=user_id,
        workspace_id=workspace_id,
    )
