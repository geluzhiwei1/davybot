# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""系统和健康检查 API 路由"""

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["system"])

# 注意:websocket_server 需要在实际使用时定义或导入
# websocket_server = ...


@router.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    # 获取WebSocket服务器状态
    # ws_status = await websocket_server.get_server_status()

    # 临时返回,等待实际实现
    return {
        "status": "healthy",
        "service": "Dawei Agent API - Orchestrator Mode",
        "version": "2.0.0",
        "architecture": "Multi-Agent Orchestrator",
        "message": "健康检查端点已迁移,等待实现",
        "websocket": {"status": "running", "connections": 0, "sessions": 0},
    }


@router.get("/ws/status")
async def get_websocket_status():
    """获取WebSocket服务器状态"""
    # return await websocket_server.get_server_status()
    # 临时返回,等待实际实现
    return {
        "status": "running",
        "connections": 0,
        "sessions": 0,
        "message": "WebSocket状态端点已迁移,等待实现",
    }


@router.post("/ws/broadcast")
async def broadcast_message(message: dict):
    """广播消息到所有WebSocket连接"""
    # await websocket_server.broadcast_message(message)
    # 临时返回,等待实际实现
    return {
        "success": True,
        "message": "广播消息端点已迁移,等待实现",
        "broadcast_message": message,
    }


@router.get("/llms")
async def get_available_llms():
    """Get available LLM configurations.
    Returns the list of available language models for the frontend selector.
    """
    # Return GLM as the only available LLM as per user requirement
    available_llms = [
        {
            "id": "glm",
            "name": "glm-4.6.6",
            "displayName": "GLM-4.6",
            "provider": "zhipu",
            "baseUrl": "https://open.bigmodel.cn/api/paas/v4",
        },
    ]

    return {"availableLLMs": available_llms, "defaultLLM": "glm", "currentLLM": "glm"}


@router.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "message": "Dawei Agent API - AI-powered agent platform (Orchestrator Mode)",
        "version": "2.0.0",
        "architecture": "Multi-Agent Orchestrator",
        "features": [
            "Multi-agent orchestration with dynamic mode switching",
            "Dynamic task planning and execution",
            "Real-time streaming responses",
            "Conversation context management",
            "Professional workflow automation",
        ],
        "endpoints": {
            # 主要 API
            "chat": "/api/chat",
            "workflow": "/api/workflow",
            "chat_stream": "/api/chat/stream",
            "websocket": "/ws",
            # 新的WebSocket端点
            "chat_websocket": "/api/ws/chat",
            "stream_websocket": "/api/ws/stream",
            "task_websocket": "/ws/task",
            # WebSocket管理
            "websocket_status": "/api/ws/status",
            "websocket_broadcast": "/api/ws/broadcast",
            # 对话管理
            "conversation_history": "/api/conversations/{conversation_id}/history",
            "clear_conversation": "/api/conversations/{conversation_id}",
            # 工具类 API (向后兼容)
            "tools_search": "/api/tools/search",
            "tools_mermaid": "/api/tools/mermaid",
            # 文件和工作区
            "files": "/api/files",
            "workspaces": "/api/workspaces",
            "workspaces_v2": "/api/v2/workspaces",
            # 系统
            "health": "/api/health",
            "docs": "/docs",
        },
    }
