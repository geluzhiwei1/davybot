# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""工作区分享 Owner 端点 (/api/workspaces/{wid}/share) — 方案 §5.1

全部 Depends(require_workspace_access) — owner+tenant 双比对 (IDOR 防护)。
6 端点: POST 创建/轮换 · GET 查当前(回显提取码) · POST close · PUT 改有效期 · POST open · DELETE 撤销

三段路径 /{workspace_id}/share 与 crud 的两段 /{workspace_id} 无遮蔽;
注册顺序仍放 crud_router 之前 (仓库惯例, 见 __init__.py)。
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from dawei.api.workspaces._deps import require_workspace_access
from dawei.workspace.workspace_share_manager import (
    ShareError,
    ShareNeedsExpiryError,
    ShareNotFoundError,
    ShareRevokedError,
    get_share_manager,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/workspaces/{workspace_id}/share",
    tags=["workspace-share-owner"],
    dependencies=[Depends(require_workspace_access)],
)


class ShareCreateRequest(BaseModel):
    """创建分享 — 有效期必填且仅 1/3/7 三档 (非法值 422 FAST FAIL)"""

    password: str | None = None  # 缺省自动生成 4 位提取码; 自定义 4-32 位可见字符
    expires_in_days: Literal[1, 3, 7]


class ShareExpiryRequest(BaseModel):
    """续期/改期 — 不换链接不换码"""

    expires_in_days: Literal[1, 3, 7]


class ShareOpenRequest(BaseModel):
    """重新开启 — 原链接+原提取码; 已过期须带新有效期一步复活"""

    expires_in_days: Literal[1, 3, 7] | None = None


def _share_url(share_id: str) -> str:
    return f"/share/{share_id}"


def _owner_view(share: dict, password: str | None) -> dict:
    """owner GET 响应 — 提取码明文仅此 (owner 鉴权) 可见; clone_log 脱敏 uid"""
    manager = get_share_manager()
    return {
        "share_id": share["share_id"],
        "url": _share_url(share["share_id"]),
        "password": password,  # jwt_secret 变更等导致无法回显时为 null (前端提示重新生成)
        "status": share.get("status", "active"),
        "revoked": bool(share.get("revoked")),
        "expired": manager.is_expired(share),
        "created_at": share.get("created_at"),
        "expires_at": share.get("expires_at"),
        "view_count": share.get("view_count", 0),
        "clone_count": share.get("clone_count", 0),
        "clone_log": [
            {
                "user": f"#{(entry.get('user_id') or '????')[:4]}",
                "at": entry.get("at"),
            }
            for entry in share.get("clone_log", [])
        ],
    }


def _map_share_error(e: Exception) -> HTTPException:
    if isinstance(e, ShareNotFoundError):
        return HTTPException(status_code=404, detail="该工作区尚未创建分享")
    if isinstance(e, ShareRevokedError):
        return HTTPException(status_code=409, detail="分享已撤销，无法操作，请重新生成")
    if isinstance(e, ShareNeedsExpiryError):
        return HTTPException(status_code=409, detail="分享已过期，请选择有效期 (1/3/7 天)")
    return HTTPException(status_code=400, detail=str(e))


@router.post("")
async def create_workspace_share(workspace_id: str, body: ShareCreateRequest, request: Request):
    """创建或轮换分享 — 同工作区旧 share 直接覆盖 (轮换 share_id+提取码, 旧链接立即失效)"""
    from dawei.api.auth import get_authenticated_tenant_id, get_authenticated_user_id

    owner_id = await get_authenticated_user_id(request)
    tenant_id = await get_authenticated_tenant_id(request)
    manager = get_share_manager()
    try:
        share = await run_in_threadpool(
            manager.create_share,
            workspace_id,
            owner_id,
            tenant_id,
            body.password,
            body.expires_in_days,
        )
    except ShareError as e:  # 有效期/提取码格式不合法 → 422 FAST FAIL
        raise HTTPException(status_code=422, detail=str(e)) from None
    return {
        "share_id": share["share_id"],
        "url": _share_url(share["share_id"]),
        "password": share["password"],  # 明文仅本次响应返回 (落盘为哈希+加密)
        "expires_at": share["expires_at"],
    }


@router.get("")
async def get_workspace_share(workspace_id: str):
    """查当前分享 — 提取码随时回显 (忘记码无需重新生成, 已发出的链接不作废)"""
    manager = get_share_manager()
    share = await run_in_threadpool(manager.get_share_for_workspace, workspace_id)
    if not share:
        raise HTTPException(status_code=404, detail="该工作区尚未创建分享")
    password = await run_in_threadpool(manager.reveal_password, share["share_id"])
    return _owner_view(share, password)


@router.post("/close")
async def close_workspace_share(workspace_id: str):
    """关闭分享 (可逆) — 链接/提取码保留; 关闭后 verify/只读/clone 立即 404 (含已签发 token)"""
    manager = get_share_manager()
    try:
        share = await run_in_threadpool(manager.close_share_for_workspace, workspace_id)
    except ShareNotFoundError as e:
        raise _map_share_error(e) from None
    return {"share_id": share["share_id"], "status": share["status"], "expires_at": share.get("expires_at")}


@router.put("")
async def update_workspace_share_expiry(workspace_id: str, body: ShareExpiryRequest):
    """修改有效期 (不换链接/不换码) — active/closed/已过期均可 (过期续期即复活); 仅 revoked 拒绝"""
    manager = get_share_manager()
    try:
        share = await run_in_threadpool(manager.update_expiry_for_workspace, workspace_id, body.expires_in_days)
    except (ShareNotFoundError, ShareRevokedError) as e:
        raise _map_share_error(e) from None
    return {"share_id": share["share_id"], "expires_at": share["expires_at"], "status": share.get("status")}


@router.post("/open")
async def open_workspace_share(workspace_id: str, body: ShareOpenRequest | None = None):
    """重新开启 — 原链接+原提取码继续可用; 若已过期须带有效期一步复活 (免「先 PUT 再 open」两步)"""
    manager = get_share_manager()
    days = body.expires_in_days if body else None
    try:
        share = await run_in_threadpool(manager.open_share_for_workspace, workspace_id, days)
    except (ShareNotFoundError, ShareRevokedError, ShareNeedsExpiryError) as e:
        raise _map_share_error(e) from None
    return {"share_id": share["share_id"], "status": share["status"], "expires_at": share["expires_at"]}


@router.delete("")
async def revoke_workspace_share(workspace_id: str):
    """撤销分享 (永久) — 与 close 的区别: 不可 reopen, 只能重新生成"""
    manager = get_share_manager()
    try:
        share = await run_in_threadpool(manager.revoke_share_for_workspace, workspace_id)
    except ShareNotFoundError as e:
        raise _map_share_error(e) from None
    return {"share_id": share["share_id"], "revoked": True}
