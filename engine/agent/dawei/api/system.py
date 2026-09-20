# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""系统和健康检查 API 路由"""

import logging

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api", tags=["system"])
logger = logging.getLogger(__name__)


def _get_ws_server():
    """Lazy import of websocket_server to avoid circular deps."""
    from dawei.websocket.ws_server import websocket_server
    return websocket_server


@router.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    ws_server = _get_ws_server()
    ws_status = {}
    if ws_server is not None:
        try:
            ws_status = await ws_server.get_server_status()
        except Exception:
            ws_status = {"status": "error"}

    return {
        "status": "healthy",
        "service": "Dawei Agent API - Orchestrator Mode",
        "version": "2.0.0",
        "architecture": "Multi-Agent Orchestrator",
        "websocket": ws_status,
    }


@router.get("/ws/status")
async def get_websocket_status():
    """获取WebSocket服务器状态"""
    ws_server = _get_ws_server()
    if ws_server is not None:
        return await ws_server.get_server_status()
    return {"status": "not_initialized", "connections": 0, "sessions": 0}


@router.post("/ws/broadcast")
async def broadcast_message(message: dict):
    """广播消息到所有WebSocket连接"""
    ws_server = _get_ws_server()
    if ws_server is not None:
        await ws_server.broadcast_message(message)
        return {"success": True, "message": "Broadcast sent"}
    return {"success": False, "message": "WebSocket server not initialized"}


# ── Command Whitelist CRUD ──────────────────────────────────────────────────

from pydantic import BaseModel, Field
from typing import Any


class SystemCommandConfig(BaseModel):
    """单个命令的配置"""
    max_args: int = Field(default=10, ge=0)
    allowed_flags: list[str] = Field(default_factory=list)
    allowed_subcommands: list[str] | None = None
    description: str = ""


class SystemCommandWhitelistPayload(BaseModel):
    """完整白名单配置请求体"""
    version: int = 1
    allowed_commands: dict[str, SystemCommandConfig] = Field(default_factory=dict)
    dangerous_commands: list[str] = Field(default_factory=list)
    dangerous_patterns: list[str] = Field(default_factory=list)


@router.get("/commands", response_model=dict[str, Any])
async def get_system_command_whitelist():
    """获取系统命令白名单完整配置（供前端展示和编辑）"""
    from dawei.sandbox.command_whitelist import CommandWhitelist

    if not CommandWhitelist._loaded:
        CommandWhitelist.load_from_config()

    config = CommandWhitelist._config.copy()
    # 将内部 _config 转为 API 友好格式
    allowed_commands_out = {}
    for name, cmd_cfg in config.get("allowed_commands", {}).items():
        allowed_commands_out[name] = {
            "maxArgs": cmd_cfg.get("max_args", 10),
            "allowedFlags": cmd_cfg.get("allowed_flags", []),
            "allowedSubcommands": cmd_cfg.get("allowed_subcommands"),
            "description": cmd_cfg.get("description", ""),
        }

    return {
        "version": config.get("version", 1),
        "allowedCommands": allowed_commands_out,
        "dangerousCommands": config.get("dangerous_commands", []),
        "dangerousPatterns": config.get("dangerous_patterns", []),
    }


@router.put("/commands", response_model=dict[str, Any])
async def put_system_command_whitelist(payload: SystemCommandWhitelistPayload):
    """全量更新系统命令白名单配置"""
    from dawei.sandbox.command_whitelist import CommandWhitelist

    # 构建内部格式
    allowed_commands = {}
    for name, cfg in payload.allowed_commands.items():
        allowed_commands[name] = {
            "max_args": cfg.max_args,
            "allowed_flags": cfg.allowed_flags,
            "allowed_subcommands": cfg.allowed_subcommands,
            "description": cfg.description,
        }

    new_config = {
        "version": payload.version,
        "allowed_commands": allowed_commands,
        "dangerous_commands": payload.dangerous_commands,
        "dangerous_patterns": payload.dangerous_patterns,
    }

    CommandWhitelist._config = new_config
    saved = CommandWhitelist.save_to_config()

    return {"success": saved, "saved": saved}


@router.patch("/commands/{cmd_name}", response_model=dict[str, Any])
async def patch_system_command_whitelist(cmd_name: str, patch: SystemCommandConfig):
    """部分更新单个命令的配置"""
    from dawei.sandbox.command_whitelist import CommandWhitelist

    if not CommandWhitelist._loaded:
        CommandWhitelist.load_from_config()

    allowed = CommandWhitelist._config.setdefault("allowed_commands", {})
    if cmd_name not in allowed:
        # 新增命令
        allowed[cmd_name] = {}

    allowed[cmd_name]["max_args"] = patch.max_args
    allowed[cmd_name]["allowed_flags"] = patch.allowed_flags
    allowed[cmd_name]["allowed_subcommands"] = patch.allowed_subcommands
    allowed[cmd_name]["description"] = patch.description

    saved = CommandWhitelist.save_to_config()
    return {"success": saved, "saved": saved, "command": cmd_name}


def _get_local_llm_models(user_id: str = "default_user") -> list[dict]:
    """Read locally configured LLM models from the LLMProvider (user + workspace configs).

    多租户隔离：只加载 user_id 自己的用户级配置（configs/{user_id}/settings.json），
    不跨账号读取。调用方必须传入已认证的 user_id（无匿名身份）。

    Returns a list of {id, name, displayName, provider} dicts.
    """
    try:
        from dawei.llm_api.llm_provider import LLMProvider
        from dawei import get_dawei_home

        provider = LLMProvider(workspace_root=str(get_dawei_home()), user_id=user_id)
        configs = provider.get_all_configs()
        models = []
        seen_ids: set[str] = set()
        for config_name, pc in configs.items():
            c = pc.config
            model_id = (c.model_id or config_name)
            if model_id in seen_ids:
                continue
            seen_ids.add(model_id)
            models.append({
                "id": model_id,
                "name": model_id,
                "displayName": f"{model_id} ({c.apiProvider})",
                "provider": c.apiProvider,
                # provider 配置名（_configs 的 key），供前端明确路由本地 provider，
                # 避免后端靠 model id 猜测本地 vs 官方网关。
                "configName": config_name,
            })
        return models
    except Exception:
        logger.debug("Could not load local LLM models", exc_info=True)
        return []


@router.get("/llms")
async def get_available_llms(request: Request):
    """Get available LLM configurations.

    Fetches models from the LLM Gateway (support system) and merges
    with locally configured models. Falls back to hardcoded list if
    nothing is available.
    """
    # 多租户：按认证用户加载其自己的 LLM 配置；无有效登录直接 401（无匿名身份）
    from dawei.api.auth import get_authenticated_user_id

    user_id = await get_authenticated_user_id(request)

    # Return only locally configured models. If none, return empty list.
    # Official/"gateway" models are served by a separate API (llm-gateway-service.ts).
    local_models = _get_local_llm_models(user_id)
    return {
        "availableLLMs": local_models,
        "defaultLLM": local_models[0]["id"] if local_models else None,
        "currentLLM": local_models[0]["id"] if local_models else None,
    }


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
