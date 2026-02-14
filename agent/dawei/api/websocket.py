# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""WebSocket API 路由"""

from fastapi import APIRouter, WebSocket

from dawei.websocket.ws_server import websocket_server

router = APIRouter(tags=["websocket"])


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """新的 WebSocket 端点 - 使用优化的WebSocket服务器"""
    await websocket_server.handle_websocket(websocket)


@router.websocket("/api/chat/stream")
async def chat_stream_endpoint(websocket: WebSocket):
    """聊天流式响应 WebSocket 端点 - 使用优化的WebSocket服务器"""
    await websocket_server.handle_websocket(websocket)


@router.websocket("/api/ws/chat")
async def chat_websocket_endpoint(
    websocket: WebSocket,
    session_id: str | None = None,
    user_id: str | None = None,
    workspace_id: str | None = None,
    conversation_id: str | None = None,
):
    """新的聊天WebSocket端点 - 使用优化的消息协议"""
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
    session_id: str | None = None,
    user_id: str | None = None,
    workspace_id: str | None = None,
):
    """新的流式WebSocket端点 - 支持大文件传输和实时数据流"""
    await websocket_server.handle_websocket(
        websocket,
        session_id=session_id,
        user_id=user_id,
        workspace_id=workspace_id,
    )


@router.websocket("/ws/task")
async def task_websocket_endpoint(
    websocket: WebSocket,
    session_id: str | None = None,
    user_id: str | None = None,
    workspace_id: str | None = None,
):
    """任务 WebSocket 端点 - 处理任务执行请求"""
    await websocket_server.handle_websocket(
        websocket,
        session_id=session_id,
        user_id=user_id,
        workspace_id=workspace_id,
    )
