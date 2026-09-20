# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""共享的 FastAPI 端点依赖注入函数。

避免各 router 文件重复定义 get_user_workspace（之前 8 份拷贝），统一为一份
async 实现：从 auth 自动注入 user_id（多租户隔离），确保所有 workspace 端点
使用正确的 (workspace_path, user_id) 上下文键。
"""

from fastapi import HTTPException, Request

from dawei.workspace import workspace_manager
from dawei.workspace.user_workspace import UserWorkspace


async def get_user_workspace(workspace_id: str, request: Request) -> UserWorkspace:
    """获取 UserWorkspace 实例（user_id 从 auth 注入，多租户隔离）。

    用于 FastAPI ``Depends(get_user_workspace)``——返回未初始化的 UserWorkspace，
    调用方按需 ``await workspace.initialize()``。
    """
    workspace_info = workspace_manager.get_workspace_by_id(workspace_id)
    if not workspace_info:
        raise HTTPException(status_code=404, detail=f"Workspace {workspace_id} not found")

    workspace_path = workspace_info.get("path")
    if not workspace_path:
        raise HTTPException(
            status_code=404,
            detail=f"Workspace path not found for {workspace_id}",
        )

    ws = UserWorkspace(workspace_path=workspace_path)
    from dawei.api.auth import get_authenticated_user_id

    ws.user_id = await get_authenticated_user_id(request)
    return ws


async def require_workspace_access(workspace_id: str, request: Request) -> None:
    """工作区归属校验（纵深防御，用于消息等数据读写端点）。

    列表侧的 owner/tenant 过滤只影响"列表展示"；此依赖在数据读写路径上
    复核工作区归属，防止任意已认证账号仅凭 workspace_id 读取他人消息（IDOR）。
    无认证请求在 get_authenticated_* 层直接 401（所有部署模式）；
    owner 缺失的 legacy 无主工作区对任何账号均不可见/不可访问。
    """
    workspace_info = workspace_manager.get_workspace_by_id(workspace_id)
    if not workspace_info:
        raise HTTPException(status_code=404, detail=f"Workspace {workspace_id} not found")

    from dawei.api.auth import get_authenticated_tenant_id, get_authenticated_user_id

    user_id = await get_authenticated_user_id(request)
    tenant_id = await get_authenticated_tenant_id(request)
    if (
        workspace_info.get("owner_user_id") != user_id
        or workspace_info.get("tenant_id", "personal") != tenant_id
    ):
        raise HTTPException(
            status_code=403,
            detail=f"Access denied: workspace '{workspace_id}' does not belong to current user/tenant",
        )
