# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""工具 API 路由

Provides REST API endpoints for slash command management and tool operations.
"""

import json
from pathlib import Path
from typing import List, Dict, Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from dawei.tools.command_manager import CommandManager
from dawei.tools.custom_tools.command_tools import RunSlashCommandTool

router = APIRouter(prefix="/api/tools", tags=["tools"])

# Global singleton instances
_command_manager: CommandManager | None = None
_slash_command_tool: RunSlashCommandTool | None = None


# Pydantic models for request/response
class MermaidRequest(BaseModel):
    """Request model for Mermaid chart generation."""

    description: str
    chart_type: str = "flowchart"
    complexity: str = "medium"


# ============================================================================
# Singleton Management
# ============================================================================


def get_command_manager() -> CommandManager:
    """Get or create the global command manager singleton instance.

    Returns:
        CommandManager: Initialized command manager with default commands

    """
    global _command_manager
    if _command_manager is None:
        import logging

        logger = logging.getLogger(__name__)
        logger.info("[CommandManager] Initializing command manager singleton...")
        _command_manager = CommandManager()
        _command_manager.create_default_builtin_commands()
        _command_manager.scan_commands()
        logger.info(f"[CommandManager] Command manager initialized with {len(_command_manager.get_all_commands())} commands")
    return _command_manager


def get_slash_command_tool() -> RunSlashCommandTool:
    """Get or create the global slash command tool singleton instance.

    Returns:
        RunSlashCommandTool: Initialized slash command tool

    """
    global _slash_command_tool
    if _slash_command_tool is None:
        _slash_command_tool = RunSlashCommandTool(command_manager=get_command_manager())
    return _slash_command_tool


def _update_workspace_context(manager: CommandManager, workspace: str | None) -> None:
    """Update command manager workspace context if provided.

    Args:
        manager: Command manager instance to update
        workspace: Optional workspace path string

    """
    if workspace:
        manager.workspace_root = Path(workspace)


def _format_command_for_response(cmd_name: str, cmd: Any) -> Dict[str, str | None]:
    """Format command object for API response.

    Args:
        cmd_name: Command name without prefix
        cmd: Command object from CommandManager

    Returns:
        Dictionary with formatted command data

    """
    return {
        "name": f"/{cmd_name}",
        "description": cmd.description,
        "argument_hint": cmd.argument_hint,
        "mode": cmd.mode,
        "source": cmd.source,
        "path": str(cmd.path) if cmd.source != "builtin" else None,
    }


# ============================================================================
# Slash Commands API Endpoints
# ============================================================================


@router.get("/commands")
async def list_commands(workspace: str | None = None, reload: bool = False) -> Dict[str, Any]:
    """List all available slash commands.

    Args:
        workspace: Optional workspace path to load workspace-specific commands
        reload: Force reload commands from disk

    Returns:
        Dictionary with command list, total count, and metadata

    Raises:
        HTTPException: If command listing fails

    """
    cmd_mgr = get_command_manager()

    # Only update workspace context if a valid workspace path is provided
    # Ignore "default" workspace string as it's not a real path
    if workspace and workspace != "default":
        _update_workspace_context(cmd_mgr, workspace)
        if reload:
            cmd_mgr.reload()
    elif reload:
        # Reload without changing workspace context
        cmd_mgr.reload()

    commands = cmd_mgr.get_all_commands()
    commands_list = [_format_command_for_response(name, cmd) for name, cmd in commands.items()]

    # Log for debugging
    import logging

    logger = logging.getLogger(__name__)
    logger.info(f"[API] Returning {len(commands_list)} slash commands (workspace={workspace}, reload={reload})")
    if len(commands_list) == 0:
        logger.warning("[API] No slash commands found! Built-in commands may not be registered.")

    return {
        "success": True,
        "total": len(commands_list),
        "commands": commands_list,
        "workspace": workspace,
        "reload": reload,
    }


@router.get("/commands/{command_name}")
async def get_command(command_name: str, workspace: str | None = None) -> Dict[str, Any]:
    """Get a specific slash command by name.

    Args:
        command_name: Name of the command (without / prefix)
        workspace: Optional workspace path

    Returns:
        Dictionary with command details including content

    Raises:
        HTTPException: If command not found (404) or retrieval fails (500)

    """
    cmd_mgr = get_command_manager()
    _update_workspace_context(cmd_mgr, workspace)

    cmd = cmd_mgr.get_command(command_name)
    if not cmd:
        raise HTTPException(status_code=404, detail=f"Command '/{command_name}' not found")

    command_data = _format_command_for_response(cmd.name, cmd)
    command_data["content"] = cmd.content

    return {"success": True, "command": command_data}


@router.post("/commands/reload")
async def reload_commands(workspace: str | None = None) -> Dict[str, Any]:
    """Reload slash commands from disk.

    Useful after adding/modifying command files without restarting the server.

    Args:
        workspace: Optional workspace path

    Returns:
        Dictionary with reload status and command count

    Raises:
        HTTPException: If reload fails

    """
    cmd_mgr = get_command_manager()
    _update_workspace_context(cmd_mgr, workspace)

    commands = cmd_mgr.reload()

    return {
        "success": True,
        "message": "Commands reloaded successfully",
        "total": len(commands),
        "workspace": workspace,
    }


@router.post("/commands/execute")
async def execute_command(
    command: str,
    args: str | None = None,
    workspace: str | None = None,
) -> Dict[str, Any]:
    """Execute a slash command and return its result.

    This endpoint provides direct command execution for testing without
    going through the agent/tool execution flow.

    Args:
        command: Command name (with or without / prefix)
        args: Optional command arguments
        workspace: Optional workspace path

    Returns:
        Dictionary with execution success status and result

    Raises:
        HTTPException: If command execution fails

    """
    tool = get_slash_command_tool()

    if workspace:
        tool.command_manager.workspace_root = Path(workspace)
        tool.command_manager.reload()

    result_json = tool._run(command, args)
    result = json.loads(result_json)

    return {"success": result.get("status") == "success", "result": result}


# ============================================================================
# X2 fix: Tool Result Snapshot API
# ============================================================================


@router.get("/snapshots/{snapshot_id}")
async def get_tool_snapshot(
    snapshot_id: str,
    request: Request,
    workspace_id: str = Query(default="", description="Workspace ID"),
) -> Dict[str, Any]:
    """获取工具结果的完整快照（前端使用）。

    X2 安全加固：
    - UUID v4 snapshot_id（不可枚举）
    - 用户鉴权（snapshot.user_id == request.user_id）
    - 工作区隔离（snapshot.workspace_id == workspace_id）
    - 访问审计日志
    - TTL 过期自动清理
    """
    import logging

    logger = logging.getLogger(__name__)

    # 1. 鉴权（无有效登录直接 401，无匿名身份）
    from dawei.api.auth import get_authenticated_user_id

    user_id = await get_authenticated_user_id(request)

    # 2. 获取快照
    from dawei.tools.result_governance import get_snapshot_store

    snapshot = get_snapshot_store().get(snapshot_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Snapshot not found or expired")

    # 3. X2 fix: 归属校验
    try:
        from dawei.core.security_auditor import security_auditor

        if snapshot.user_id and snapshot.user_id != user_id:
            security_auditor.log(
                "snapshot.access.denied",
                snapshot_id=snapshot_id,
                requester=user_id,
                owner=snapshot.user_id,
            )
            raise HTTPException(status_code=403, detail="Access denied: snapshot belongs to another user")

        if snapshot.workspace_id and workspace_id and snapshot.workspace_id != workspace_id:
            security_auditor.log(
                "snapshot.access.denied",
                snapshot_id=snapshot_id,
                requester_workspace=workspace_id,
                owner_workspace=snapshot.workspace_id,
            )
            raise HTTPException(status_code=403, detail="Access denied: snapshot belongs to another workspace")

        # 4. 审计日志
        security_auditor.log(
            "snapshot.access.granted",
            snapshot_id=snapshot_id,
            user_id=user_id,
            workspace_id=workspace_id,
            tool_name=snapshot.tool_name,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Security auditor unavailable for snapshot access: {e}")

    # 5. 返回脱敏后的结果（X3 fix）
    return {
        "tool_name": snapshot.tool_name,
        "result": snapshot.redacted_result if snapshot.redacted_result is not None else snapshot.raw_result,
        "original_size": len(str(snapshot.raw_result).encode("utf-8")) if snapshot.raw_result else 0,
        "created_at": snapshot.timestamp.isoformat() if snapshot.timestamp else None,
    }


@router.post("/snapshots/cleanup")
async def cleanup_snapshots() -> Dict[str, Any]:
    """手动触发快照清理（管理端点）。"""
    from dawei.tools.result_governance import get_snapshot_store

    cleaned = get_snapshot_store().cleanup_expired()
    stats = get_snapshot_store().stats()
    return {"success": True, "cleaned": cleaned, "stats": stats}


@router.get("/governance/metrics")
async def get_governance_metrics() -> Dict[str, Any]:
    """获取工具输出治理的指标摘要。"""
    from dawei.tools.result_governance.metrics import get_metrics

    return get_metrics().get_summary()


@router.post("/governance/metrics/reset")
async def reset_governance_metrics() -> Dict[str, Any]:
    """重置治理指标计数器。"""
    from dawei.tools.result_governance.metrics import get_metrics

    get_metrics().reset()
    return {"success": True, "message": "Governance metrics reset"}


# ============================================================================
# Governance Config API (PR-F3)
# ============================================================================


class GovernanceConfigResponse(BaseModel):
    """治理配置响应模型。"""

    default_policy: dict[str, Any] = {}
    tool_policies: dict[str, dict[str, Any]] = {}
    snapshot_ttl_hours: int = 24
    progressive_disclosure: dict[str, Any] = {}


class ToolPolicyUpdate(BaseModel):
    """单个工具策略更新。"""

    tool_name: str
    max_output_tokens: int | None = None
    output_type: str | None = None
    blob_max_lines: int | None = None
    list_max_items: int | None = None
    echo_max_input_chars: int | None = None


class GovernanceConfigUpdate(BaseModel):
    """治理配置更新请求。"""

    default_max_tokens: int | None = None
    snapshot_ttl_hours: int | None = None
    tool_overrides: list[ToolPolicyUpdate] = []


@router.get("/governance/config")
async def get_governance_config() -> Dict[str, Any]:
    """获取当前输出治理配置（所有工具策略 + 全局设置）。"""
    from dawei.tools.result_governance.policy import POLICIES
    from dawei.tools.result_governance.store import get_snapshot_store

    # 序列化所有策略
    tool_policies: dict[str, dict[str, Any]] = {}
    for name, policy in POLICIES.items():
        tool_policies[name] = policy.model_dump()

    # snapshot TTL
    store = get_snapshot_store()
    ttl_hours = int(store._default_ttl.total_seconds() // 3600) if hasattr(store, "_default_ttl") else 24

    # progressive disclosure config
    try:
        from dawei.config import get_settings

        ptd = get_settings().progressive_tool_disclosure
        pd_config = {
            "enabled": ptd.enabled,
            "schema_compression": ptd.schema_compression,
            "max_activated_tools": ptd.max_activated_tools,
        }
    except Exception:
        pd_config = {}

    return {
        "success": True,
        "config": {
            "default_policy": tool_policies.pop("default", {}),
            "tool_policies": tool_policies,
            "snapshot_ttl_hours": ttl_hours,
            "progressive_disclosure": pd_config,
        },
    }


@router.put("/governance/config")
async def update_governance_config(update: GovernanceConfigUpdate) -> Dict[str, Any]:
    """更新输出治理配置（热加载，立即生效）。

    可更新：
    - default_max_tokens: 默认策略的 max_output_tokens
    - snapshot_ttl_hours: 快照保留时间
    - tool_overrides: 按工具覆盖策略字段
    """
    from dawei.tools.result_governance.policy import POLICIES, OutputPolicy

    changed: list[str] = []

    # 1. 更新默认策略
    if update.default_max_tokens is not None:
        default_policy = POLICIES.get("default", OutputPolicy())
        default_policy.max_output_tokens = update.default_max_tokens
        POLICIES["default"] = default_policy
        changed.append("default.max_output_tokens")

    # 2. 更新 snapshot TTL
    if update.snapshot_ttl_hours is not None:
        from datetime import timedelta

        from dawei.tools.result_governance.store import get_snapshot_store

        store = get_snapshot_store()
        store._default_ttl = timedelta(hours=update.snapshot_ttl_hours)
        changed.append("snapshot_ttl_hours")

    # 3. 按工具覆盖
    for override in update.tool_overrides:
        tool_name = override.tool_name
        existing = POLICIES.get(tool_name, OutputPolicy())
        policy_dict = existing.model_dump()

        if override.max_output_tokens is not None:
            policy_dict["max_output_tokens"] = override.max_output_tokens
        if override.output_type is not None:
            policy_dict["output_type"] = override.output_type
        if override.blob_max_lines is not None:
            policy_dict["blob_max_lines"] = override.blob_max_lines
        if override.list_max_items is not None:
            policy_dict["list_max_items"] = override.list_max_items
        if override.echo_max_input_chars is not None:
            policy_dict["echo_max_input_chars"] = override.echo_max_input_chars

        POLICIES[tool_name] = OutputPolicy(**policy_dict)
        changed.append(tool_name)

    return {
        "success": True,
        "message": f"配置已热加载，更新了 {len(changed)} 项",
        "changed": changed,
    }
