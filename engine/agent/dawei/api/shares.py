# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""工作区分享 Viewer 公开端点 (/api/shares) — project/docs/工作区分享功能方案.md §5.2

只读边界: verify 免登录; 其余端点全部要求 X-Share-Token (scope=workspace-share,
exp=分享有效期) 且逐请求重查校验链 — 关闭/撤销/过期即时失效。

安全要点:
- 校验链统一 404 "share not found or revoked" (防枚举/防信息泄露)
- 所有文件读取 resolve() 前缀校验 + 拒绝 dot 路径 (.dawei 里有凭据/配置)
- clone 是唯一写操作, 双凭证 (share-token + 用户 JWT), 只写 cloner 名下新目录
"""

from __future__ import annotations

import json
import logging
import mimetypes
import os
import shutil
import threading
import uuid
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from dawei.api.conversations import load_conversation_file
from dawei.workspace import workspace_manager
from dawei.workspace.workspace_share_manager import (
    SHARE_EXPIRY_DAYS,
    WorkspaceShareManager,
    decode_share_token,
    get_share_manager,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/shares", tags=["workspace-share"])

# 校验链统一 404 文案 (不存在/已关闭/已撤销/已过期/工作区已删 — 不区分)
SHARE_404_DETAIL = "share not found or revoked"

# clone 拷贝白名单 (.dawei/ 内; 其余 dot 内容一律不拷 — 配置/凭据/自动化 fail-closed)
CLONE_DAWEI_DIRS = ("conversations", "chat-history", "task_graphs", "task_nodes", "checklists")
# 新工作区 bootstrap 目录 (对齐 crud.create_workspace)
BOOTSTRAP_DAWEI_DIRS = ("chat-history", "checkpoints", "task_graphs", "task_nodes", "conversations", "checklists")

# preview=1 允许 inline 的 mimetype 白名单 (SVG/HTML 故意排除 — 存储型 XSS)
_PREVIEW_INLINE_MIMES = {
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "image/bmp",
    "application/pdf",
    "application/json",
    "text/plain",
    "text/markdown",
    "text/csv",
}


class VerifyRequest(BaseModel):
    password: str


class QuotaError(Exception):
    """克隆配额超限 → 413"""


# ================================================================
# 校验链 + share-token 守卫
# ================================================================


def _share_404() -> HTTPException:
    return HTTPException(status_code=404, detail=SHARE_404_DETAIL)


def _get_active_share_or_404(share_id: str) -> dict[str, Any]:
    """校验链 (FAST FAIL): 存在 → 未撤销未关闭 → 未过期 → 工作区存活。任何一环失败统一 404。"""
    manager = get_share_manager()
    share = manager.get_share(share_id)
    if not share or share.get("revoked") or share.get("status") != "active" or manager.is_expired(share):
        raise _share_404()
    ws = workspace_manager.get_workspace_by_id(share.get("workspace_id", ""))
    if not ws or not ws.get("path") or not Path(ws["path"]).is_dir():
        raise _share_404()
    return share


def _require_share_token(
    share_id: str,
    x_share_token: str = Header(alias="X-Share-Token", default=""),
) -> dict[str, Any]:
    """share-token 守卫: 签名/scope/sid 三查 + 逐请求重查校验链 (即时失效依赖于此)"""
    if not x_share_token:
        raise HTTPException(status_code=401, detail="X-Share-Token header required")
    try:
        payload = decode_share_token(x_share_token)
    except ValueError:
        raise HTTPException(status_code=401, detail="invalid or expired share token") from None
    if payload.get("sid") != share_id:
        raise HTTPException(status_code=401, detail="share token does not match this share")
    return _get_active_share_or_404(share_id)


def _share_root(share: dict[str, Any]) -> Path:
    ws = workspace_manager.get_workspace_by_id(share["workspace_id"])
    return Path(ws["path"]).resolve()


# ================================================================
# verify 防爆破 (进程内 limiter, 重启清零 — 单节点 demo 可接受)
# ================================================================


class _VerifyLimiter:
    FAIL_LIMIT = 5
    LOCK_SECONDS = 600  # 5 次失败锁 10 分钟
    GLOBAL_PER_MINUTE = 30  # 每 IP 全局兜底

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._fails: dict[tuple[str, str], deque[float]] = {}
        self._locked_until: dict[tuple[str, str], float] = {}
        self._ip_hits: dict[str, deque[float]] = {}

    @staticmethod
    def _prune(seq: deque[float], now: float, window: float) -> deque[float]:
        while seq and seq[0] < now - window:
            seq.popleft()
        return seq

    def locked_for(self, key: tuple[str, str]) -> float:
        """剩余锁定秒数 (0 = 未锁)"""
        import time

        with self._lock:
            until = self._locked_until.get(key, 0.0)
            if until > time.time():
                return until - time.time()
            self._locked_until.pop(key, None)
            return 0.0

    def check_global(self, ip: str) -> None:
        import time

        with self._lock:
            now = time.time()
            hits = self._prune(self._ip_hits.setdefault(ip, deque()), now, 60.0)
            if len(hits) >= self.GLOBAL_PER_MINUTE:
                raise HTTPException(status_code=429, detail="too many requests")
            hits.append(now)

    def record_fail(self, key: tuple[str, str]) -> float:
        """记一次失败; 返回本次失败后的锁定秒数 (0 = 未触发锁定)"""
        import time

        with self._lock:
            now = time.time()
            fails = self._prune(self._fails.setdefault(key, deque()), now, float(self.LOCK_SECONDS))
            fails.append(now)
            if len(fails) >= self.FAIL_LIMIT:
                self._locked_until[key] = now + self.LOCK_SECONDS
                self._fails.pop(key, None)
                return self.LOCK_SECONDS
            return 0.0

    def reset(self, key: tuple[str, str]) -> None:
        with self._lock:
            self._fails.pop(key, None)
            self._locked_until.pop(key, None)


_limiter = _VerifyLimiter()


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ================================================================
# 快照/统计/文件树 辅助 (同步, 全部走 threadpool)
# ================================================================


def _count_workspace_stats(root: Path) -> dict[str, int]:
    files = total_bytes = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for f in filenames:
            if f.startswith("."):
                continue
            files += 1
            try:
                total_bytes += (Path(dirpath) / f).stat().st_size
            except OSError:
                pass
    conversations_dir = root / ".dawei" / "conversations"
    tasks_dir = root / ".dawei" / "task_graphs"
    return {
        "files": files,
        "conversations": len(list(conversations_dir.glob("*.json"))) if conversations_dir.is_dir() else 0,
        "tasks": len(list(tasks_dir.glob("*.json"))) if tasks_dir.is_dir() else 0,
        "total_bytes": total_bytes,
    }


def _workspace_meta(share: dict[str, Any]) -> dict[str, Any]:
    ws = workspace_manager.get_workspace_by_id(share["workspace_id"]) or {}
    # sanitize: 只暴露展示字段, 绝不返回 owner uid/tenant/绝对路径
    return {
        "display_name": ws.get("display_name") or ws.get("name") or "",
        "description": ws.get("description") or "",
        "created_at": ws.get("created_at") or "",
    }


def _build_share_file_tree(root: Path, max_depth: int = 5) -> list[dict[str, Any]]:
    """只读文件树: 过滤一切 dot 项; 结构对齐现有 file-tree 响应 (前端组件复用)"""
    tree: list[dict[str, Any]] = []
    base = root.resolve()

    def walk(directory: Path, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            entries = sorted(directory.iterdir(), key=lambda p: (p.is_file(), p.name))
        except OSError:
            return
        for entry in entries:
            if entry.name.startswith("."):
                continue
            rel = entry.relative_to(base).as_posix()
            try:
                stat = entry.stat()
                updated = datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat()
                size = stat.st_size if entry.is_file() else 0
            except OSError:
                updated, size = "", 0
            tree.append(
                {
                    "id": rel,
                    "name": entry.name,
                    "path": rel,
                    "type": "directory" if entry.is_dir() else "file",
                    "level": rel.count("/"),
                    "size": size,
                    "createdAt": updated,
                    "updatedAt": updated,
                    "children": [],
                },
            )
            if entry.is_dir() and not entry.is_symlink():
                walk(entry, depth + 1)

    walk(base, 1)
    tree.sort(key=lambda x: (x["path"], x["type"] == "file"))
    return tree


def _resolve_shared_file(root: Path, rel_path: str) -> Path:
    """下载路径守卫: resolve 后必须仍在 root 内且非 dot 路径 (防穿越/symlink 逃逸/.dawei 探测)"""
    target = (root / rel_path).resolve()
    try:
        rel = target.relative_to(root)
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied: path outside workspace") from None
    if any(part.startswith(".") for part in rel.parts):
        raise HTTPException(status_code=403, detail="Access denied: hidden paths are not shared")
    return target


def _preview_media_type(path: Path) -> tuple[str, str]:
    """返回 (media_type, disposition_type); 非 白名单 类型一律 attachment 兜底"""
    guessed, _ = mimetypes.guess_type(path.name)
    media = guessed if guessed in _PREVIEW_INLINE_MIMES else "application/octet-stream"
    if media == "text/plain" and path.suffix.lower() in (".html", ".htm", ".svg"):
        media = "application/octet-stream"  # 双保险: text/html 会被猜成 text/plain 的场景
    disposition = "inline" if media in _PREVIEW_INLINE_MIMES else "attachment"
    return media, disposition


# ================================================================
# Viewer 端点
# ================================================================


@router.post("/{share_id}/verify")
async def verify_share(share_id: str, body: VerifyRequest, request: Request):
    """验证提取码 → 签发 share-token (exp=分享有效期; 浏览中途不踢人, 关闭/撤销逐请求重查)"""
    ip = _client_ip(request)
    _limiter.check_global(ip)
    key = (share_id, ip)

    remaining = _limiter.locked_for(key)
    if remaining > 0:
        raise HTTPException(
            status_code=429,
            detail=f"尝试次数过多，请 {int(remaining) // 60} 分 {int(remaining) % 60} 秒后再试",
            headers={"Retry-After": str(int(remaining) + 1)},
        )

    share = _get_active_share_or_404(share_id)

    manager = get_share_manager()
    ok = await run_in_threadpool(manager.verify_password, share_id, body.password)
    if not ok:
        locked = _limiter.record_fail(key)
        detail = f"提取码错误次数过多，已锁定 {locked // 60} 分钟" if locked else "提取码错误或分享不存在"
        raise HTTPException(
            status_code=401,
            detail=detail,
            headers={"Retry-After": str(locked + 1)} if locked else None,
        )
    _limiter.reset(key)

    await run_in_threadpool(manager.record_view, share_id)
    token, expires_at = manager.issue_share_token(share)
    root = _share_root(share)
    stats = await run_in_threadpool(_count_workspace_stats, root)
    logger.info("[WorkspaceShare] verify 通过 share_id=%s ip=%s", share_id, ip)
    return {
        "share_token": token,
        "expires_at": expires_at,
        "workspace": _workspace_meta(share),
        "stats": stats,
    }


@router.get("/{share_id}/meta")
async def share_meta(share_id: str, share: dict[str, Any] = Depends(_require_share_token)):
    """工作区元信息快照 (供刷新页面用)"""
    root = _share_root(share)
    stats = await run_in_threadpool(_count_workspace_stats, root)
    return {"workspace": _workspace_meta(share), "stats": stats}


@router.get("/{share_id}/file-tree")
async def share_file_tree(
    share_id: str,
    max_depth: int = Query(5, ge=1, le=10),
    share: dict[str, Any] = Depends(_require_share_token),
):
    """只读文件树 — 过滤一切 dot 项 (.dawei/.git/...)"""
    root = _share_root(share)
    tree = await run_in_threadpool(_build_share_file_tree, root, max_depth)
    return {"success": True, "fileTree": tree}


@router.get("/{share_id}/files/download")
async def share_download(
    share_id: str,
    path: str = Query(..., description="工作区内相对路径"),
    preview: int = Query(0, description="1=内联预览 (安全 mimetype 白名单)"),
    share: dict[str, Any] = Depends(_require_share_token),
):
    """文件下载/预览 (只读; 目录打包 zip, 均排除 dot 项)"""
    root = _share_root(share)
    target = await run_in_threadpool(_resolve_shared_file, root, path)
    if not target.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {path}")

    if target.is_file():
        if preview:
            media, disposition = _preview_media_type(target)
        else:
            media, disposition = "application/octet-stream", "attachment"
        logger.info("[WorkspaceShare] download share_id=%s path=%s preview=%d", share_id, path, preview)
        return FileResponse(
            path=str(target),
            filename=target.name,
            media_type=media,
            content_disposition_type=disposition,
        )

    if target.is_dir():
        import io
        import zipfile

        def _zip_dir() -> bytes:
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                for file_path in sorted(target.rglob("*")):
                    if not file_path.is_file():
                        continue
                    rel = file_path.relative_to(target)
                    if any(part.startswith(".") for part in rel.parts):
                        continue
                    zf.write(file_path, rel)
            return buffer.getvalue()

        data = await run_in_threadpool(_zip_dir)
        return StreamingResponse(
            io.BytesIO(data),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{target.name}.zip"'},
        )

    raise HTTPException(status_code=400, detail=f"Invalid path type: {path}")


@router.get("/{share_id}/conversations")
async def share_conversations(
    share_id: str,
    page: int = 1,
    limit: int = 50,
    sort_order: str = "desc",
    share: dict[str, Any] = Depends(_require_share_token),
):
    """对话列表 (分页参数对齐 api/conversations.py; sanitize 掉绝对路径)"""

    def _list() -> dict[str, Any]:
        conv_dir = _share_root(share) / ".dawei" / "conversations"
        conversations = []
        if conv_dir.is_dir():
            for file_path in conv_dir.glob("*.json"):
                conversation = load_conversation_file(file_path)
                if conversation:
                    conversation.pop("path", None)  # 绝对路径不外泄
                    conversations.append(conversation)
        conversations.sort(key=lambda x: x["lastUpdated"], reverse=(sort_order == "desc"))
        total = len(conversations)
        total_pages = (total + limit - 1) // limit if limit > 0 else 1
        start = (page - 1) * limit
        return {
            "success": True,
            "conversations": conversations[start : start + limit],
            "page": page,
            "limit": limit,
            "total": total,
            "totalPages": total_pages,
        }

    return await run_in_threadpool(_list)


@router.get("/{share_id}/conversations/{conversation_id}")
async def share_conversation(
    share_id: str,
    conversation_id: str,
    skip: int = 0,
    limit: int | None = None,
    order: str = "asc",
    share: dict[str, Any] = Depends(_require_share_token),
):
    """单对话消息 (分页语义对齐 api/conversations.py:235)"""

    def _load() -> dict[str, Any]:
        conv_file = _share_root(share) / ".dawei" / "conversations" / f"{conversation_id}.json"
        if not conv_file.exists():
            return {
                "success": True,
                "conversation": {
                    "id": conversation_id,
                    "title": "",
                    "messages": [],
                    "messageCount": 0,
                    "pagination": {"skip": 0, "limit": limit, "returned": 0, "total": 0, "hasMore": False},
                },
                "message": "No conversation history yet",
            }
        data = json.loads(conv_file.read_text(encoding="utf-8"))
        messages = data.get("messages", [])
        total = len(messages)
        if order == "desc":
            end = total - skip
            start = end - limit if limit is not None else 0
            start = max(start, 0)
            windowed = messages[start:end]
        else:
            windowed = messages[skip : skip + limit] if limit is not None else messages[skip:]
        return {
            "success": True,
            "conversation": {
                "id": data.get("id", conversation_id),
                "title": data.get("title", ""),
                "messages": windowed,
                "messageCount": total,
                "metadata": data.get("metadata", {}),
                "createdAt": data.get("createdAt") or data.get("created_at"),
                "updatedAt": data.get("updatedAt") or data.get("updated_at"),
                "pagination": {
                    "skip": skip,
                    "limit": limit,
                    "returned": len(windowed),
                    "total": total,
                    "hasMore": skip + len(windowed) < total,
                },
            },
            "message": f"Loaded {len(windowed)}/{total} messages",
        }

    return await run_in_threadpool(_load)


@router.get("/{share_id}/tasks")
async def share_tasks(share_id: str, share: dict[str, Any] = Depends(_require_share_token)):
    """任务图列表 + todos 摘要 (只读 .dawei/task_graphs/)"""

    def _load() -> list[dict[str, Any]]:
        graphs_dir = _share_root(share) / ".dawei" / "task_graphs"
        result = []
        if not graphs_dir.is_dir():
            return result
        for graph_file in sorted(graphs_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                data = json.loads(graph_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            nodes = data.get("nodes", {})
            if not isinstance(nodes, dict):
                nodes = {}
            tasks = [
                {
                    "task_id": node.get("id") or node.get("task_id") or nid,
                    "description": node.get("description", ""),
                    "status": node.get("status", ""),
                    "mode": node.get("mode", ""),
                    "priority": node.get("priority"),
                    "todos": node.get("todos", []),
                    "created_at": node.get("created_at"),
                    "updated_at": node.get("updated_at"),
                }
                for nid, node in nodes.items()
                if isinstance(node, dict)
            ]
            result.append(
                {
                    "graph_id": data.get("task_graph_id") or graph_file.stem,
                    "name": data.get("name") or graph_file.stem,
                    "status": data.get("status", ""),
                    "created_at": data.get("timestamp") or datetime.fromtimestamp(graph_file.stat().st_mtime, tz=UTC).isoformat(),
                    "total_tasks": len(nodes),
                    "tasks": tasks,
                },
            )
        return result

    graphs = await run_in_threadpool(_load)
    return {"success": True, "graphs": graphs}


# ================================================================
# Clone (R3) — 唯一写操作, 双凭证: share-token (依赖) + 用户 JWT
# ================================================================


def _managed_root() -> Path:
    """新工作区根 (对齐 crud.py 的服务端托管路径分配)"""
    from dawei import get_dawei_home

    base = os.environ.get("DAWEI_WORKSPACE_BASE_DIR")
    return Path(base or (Path(get_dawei_home()) / "web_workspaces")).resolve()


def _scan_clone_payload(src: Path) -> tuple[int, int]:
    """克隆前 FAST FAIL 配额扫描: (总字节, 文件数) — 只统计会被拷贝的内容"""
    total_bytes = files = 0
    # 非 dot 用户文件
    for dirpath, dirnames, filenames in os.walk(src):
        rel_parts = Path(dirpath).relative_to(src).parts
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        if any(part.startswith(".") for part in rel_parts):
            continue
        for f in filenames:
            if f.startswith("."):
                continue
            files += 1
            try:
                total_bytes += (Path(dirpath) / f).stat().st_size
            except OSError:
                pass
    # .dawei 白名单子目录
    dawei = src / ".dawei"
    for sub in CLONE_DAWEI_DIRS:
        sub_dir = dawei / sub
        if not sub_dir.is_dir():
            continue
        for dirpath, _dirnames, filenames in os.walk(sub_dir):
            for f in filenames:
                files += 1
                try:
                    total_bytes += (Path(dirpath) / f).stat().st_size
                except OSError:
                    pass
    return total_bytes, files


def _do_clone(src: Path, new_name: str, new_id: str, description: str) -> Path:
    """同步执行目录拷贝 (threadpool): 白名单拷贝 + bootstrap + 全新 workspace.json (不拷任何配置)"""
    dest = _managed_root() / "clone-tmp" / f"{new_id}"
    dest.mkdir(parents=True, exist_ok=True)
    try:
        # 1) 非 dot 顶层条目 (copytree ignore_patterns 再滤一层 dot; symlinks=True 不跟随)
        for entry in sorted(src.iterdir()):
            if entry.name.startswith("."):
                continue
            if entry.is_dir() and not entry.is_symlink():
                shutil.copytree(entry, dest / entry.name, symlinks=True, ignore=shutil.ignore_patterns(".*"))
            elif entry.is_file() or entry.is_symlink():
                shutil.copy2(entry, dest / entry.name, follow_symlinks=False)
        # 2) .dawei 白名单 (对话/任务/清单 — 两处对话存储都拷)
        src_dawei = src / ".dawei"
        for sub in CLONE_DAWEI_DIRS:
            sub_dir = src_dawei / sub
            if sub_dir.is_dir():
                shutil.copytree(sub_dir, dest / ".dawei" / sub, symlinks=True)
        # 3) bootstrap 缺失目录 (对齐 create_workspace)
        for sub in BOOTSTRAP_DAWEI_DIRS:
            (dest / ".dawei" / sub).mkdir(parents=True, exist_ok=True)
        (dest / "scheduled_tasks").mkdir(parents=True, exist_ok=True)
        (dest / "snapshots").mkdir(parents=True, exist_ok=True)
        # 4) 全新 workspace.json — 名称=原名（副本）, 无任何 LLM/MCP/plugin/security 配置
        workspace_json = {
            "id": new_id,
            "name": new_name,
            "display_name": new_name,
            "description": description or "",
            "created_at": datetime.now(UTC).isoformat(),
            "workspace_type": "user",
            "lifecycle": "persistent",
        }
        (dest / ".dawei" / "workspace.json").write_text(json.dumps(workspace_json, ensure_ascii=False, indent=2), encoding="utf-8")
        return dest
    except Exception:
        shutil.rmtree(dest, ignore_errors=True)
        raise


async def _register_clone_in_index(
    workspace_id: str,
    name: str,
    path: str,
    owner_user_id: str,
    tenant_id: str,
    cloned_from: dict[str, str],
) -> None:
    """注册进 workspaces.json (复用现有函数, 零修改) + 附加 cloned_from 键 (未知键对现有读者无害)"""
    from dawei.api.workspaces.crud import _register_workspace_in_system_index

    await _register_workspace_in_system_index(
        workspace_id=workspace_id,
        name=name,
        display_name=name,
        path=path,
        owner_user_id=owner_user_id,
        tenant_id=tenant_id,
    )

    from dawei.storage.storage_provider import StorageProvider

    system_storage = StorageProvider.get_system_storage()
    if await system_storage.exists("workspaces.json"):
        content = await system_storage.read_file("workspaces.json")
        data = json.loads(content)
        for entry in data.get("workspaces", []):
            if entry.get("id") == workspace_id:
                entry["cloned_from"] = cloned_from
                break
        await system_storage.write_file("workspaces.json", json.dumps(data, indent=2, ensure_ascii=False))
        StorageProvider.clear_system_storage_cache()
        from dawei.workspace.workspace_manager import workspace_manager as _wm

        _wm.reload()


async def _sync_clone_to_store(workspace_id: str, local_root: Path) -> None:
    """rustfs 启用时同步新工作区 (files/agents/skills 白名单自动生效); best-effort 不阻塞克隆结果"""
    if os.environ.get("WORKSPACE_STORE_BACKEND", "local").lower() == "local":
        return
    try:
        from dawei.sandbox.workspace_store import WorkspaceStore

        store = await run_in_threadpool(WorkspaceStore.create)
        stats = await run_in_threadpool(store.sync_local_to_store, workspace_id, str(local_root))
        logger.info("[WorkspaceShare] 克隆工作区 rustfs 同步完成: %s", stats.as_dict())
    except Exception as e:  # noqa: BLE001 — 同步失败不毁掉已成功的克隆
        logger.warning("[WorkspaceShare] 克隆工作区 rustfs 同步失败 (不影响克隆结果): %s", e)


@router.post("/{share_id}/clone")
async def clone_share(share_id: str, request: Request, share: dict[str, Any] = Depends(_require_share_token)):
    """复制到我的账号 — 双凭证 (X-Share-Token + 用户 Bearer JWT); 纯服务端本地拷贝, 不经浏览器"""
    from dawei.api.auth import get_authenticated_tenant_id, get_authenticated_user_id

    cloner_id = await get_authenticated_user_id(request)  # 缺登录 → 401 (FAST FAIL)
    cloner_tenant = await get_authenticated_tenant_id(request)

    ws = workspace_manager.get_workspace_by_id(share["workspace_id"]) or {}
    src = Path(ws["path"]).resolve()
    new_name = (ws.get("display_name") or ws.get("name") or "workspace") + "（副本）"
    new_id = str(uuid.uuid4())

    # FAST FAIL 配额: 不建半成品
    max_bytes = int(os.environ.get("DAWEI_SHARE_CLONE_MAX_BYTES") or 1024**3)
    max_files = int(os.environ.get("DAWEI_SHARE_CLONE_MAX_FILES") or 20000)
    total_bytes, files = await run_in_threadpool(_scan_clone_payload, src)
    if total_bytes > max_bytes or files > max_files:
        raise HTTPException(
            status_code=413,
            detail=f"工作区过大无法复制: {files} 个文件 / {total_bytes / 1024 / 1024:.1f} MB (上限 {max_files} 个 / {max_bytes / 1024 / 1024:.0f} MB)",
        )

    # 拷贝到最终位置 (web_workspaces/{cloner}/{tenant}/{uuid})
    managed_root = _managed_root()
    dest = managed_root / cloner_id / cloner_tenant / new_id
    logger.info(
        "[WorkspaceShare] clone 开始 share_id=%s %s -> %s (%d files, %.1f MB)",
        share_id,
        src,
        dest,
        files,
        total_bytes / 1024 / 1024,
    )
    tmp_dir = await run_in_threadpool(_do_clone, src, new_name, new_id, ws.get("description") or "")
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp_dir.replace(dest)  # 同一文件系统内原子落位 (managed_root/clone-tmp → web_workspaces)
    except OSError:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail="clone failed: cannot place workspace directory") from None

    try:
        await _register_clone_in_index(
            workspace_id=new_id,
            name=new_name,
            path=str(dest),
            owner_user_id=cloner_id,
            tenant_id=cloner_tenant,
            cloned_from={"workspace_id": share["workspace_id"], "share_id": share_id, "at": datetime.now(UTC).isoformat()},
        )
    except Exception:
        shutil.rmtree(dest, ignore_errors=True)
        logger.exception("[WorkspaceShare] clone 索引注册失败, 已清理 %s", dest)
        raise HTTPException(status_code=500, detail="clone failed: workspace registration error") from None

    await _sync_clone_to_store(new_id, dest)

    await run_in_threadpool(get_share_manager().record_clone, share_id, cloner_id, cloner_tenant, new_id)
    logger.info("[WorkspaceShare] clone 完成 share_id=%s cloner=%s new_workspace=%s", share_id, cloner_id, new_id)
    return {"workspace_id": new_id, "name": new_name}
