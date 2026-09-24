# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""对话管理 API 路由"""

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Request

from dawei.api.workspaces._deps import require_workspace_access
from dawei.logg.logging import get_logger
from dawei.workspace import workspace_manager

logger = get_logger(__name__)

router = APIRouter(
    prefix="/api/workspaces/{workspace_id}/conversations",
    tags=["conversations"],
    # 消息读写路径统一归属校验：防止仅凭 workspace_id 跨账号读写消息（IDOR）
    dependencies=[Depends(require_workspace_access)],
)


def get_chat_history_dir_for_workspace(workspace_id: str) -> Path:
    """获取给定工作区ID的.dawei/conversations目录的路径。"""
    workspace_info = workspace_manager.get_workspace_by_id(workspace_id)
    if not workspace_info:
        raise HTTPException(
            status_code=404,
            detail=f"Workspace with ID '{workspace_id}' not found.",
        )

    base_path = Path(workspace_info["path"])

    if not base_path.is_dir():
        raise HTTPException(
            status_code=404,
            detail=f"Workspace path '{base_path}' not found or is not a directory.",
        )

    # 使用新的.dawei/conversations目录（重构后的持久化路径）
    chat_history_dir = base_path / ".dawei" / "conversations"

    # 如果.dawei/conversations不存在，则创建它
    if not chat_history_dir.exists():
        chat_history_dir.mkdir(parents=True, exist_ok=True)

    return chat_history_dir


def load_conversation_file(file_path: Path) -> Dict[str, Any]:
    """加载单个对话文件"""
    with Path(file_path).open(encoding="utf-8") as f:
        data = json.load(f)

    conversation_id = file_path.stem
    title = data.get("title", f"对话 {conversation_id}")
    last_updated = datetime.fromtimestamp(file_path.stat().st_mtime)

    # 时间戳 — 会话文件存在两种键风格：旧 camelCase（createdAt/updatedAt）与新 snake_case
    # （created_at/updated_at，agent 持久化层当前写入格式）。两者都读，避免 createdAt=None。
    created = data.get("createdAt") or data.get("created_at")
    updated = data.get("updatedAt") or data.get("updated_at")

    return {
        "id": conversation_id,
        "title": title,
        "lastUpdated": last_updated,
        "messageCount": len(data.get("messages", [])),
        "path": str(file_path),
        # 新增：任务类型字段
        "task_type": data.get("task_type", "user"),
        "source_task_id": data.get("source_task_id"),
        # 元数据
        "metadata": data.get("metadata", {}),
        # 时间戳（camelCase 兼容旧消费方；snake_case 供前端 store.ts 读取）
        "createdAt": created,
        "updatedAt": updated,
        "created_at": created,
        "updated_at": updated,
    }


def _annotate_subtask_parent_conversations(conversations: List[Dict[str, Any]], workspace_id: str) -> None:
    """任务列表嵌套（2026-09-24）：为 subtask 会话计算 parent_conversation_id。

    子任务会话（task_type=subtask）不再与父任务并列平铺，前端按本字段折叠到
    父任务行内。归父优先级：
    1. 图节点链上 metadata.root_conversation_id（new_task/new_task_batch 派发时
       盖章；P2-7 指针不切换，盖章值恒为主会话）
    2. 时间窗回退（盖章上线前的旧数据）：派发发生在某用户会话活跃期内 →
       归入 created_at ≤ 派发 ≤ updated_at 且 updated_at 最新的会话；仅一个
       候选时直接归入
    3. 全部失败 → None（保持平铺，绝不丢数据）

    只读持久化 JSON，不初始化 workspace 对象（列表接口保持零副作用）。
    """
    for c in conversations:
        c.setdefault("parent_conversation_id", None)
    subs = [c for c in conversations if c.get("task_type") == "subtask" and c.get("source_task_id")]
    if not subs:
        return

    # 加载工作区任务图节点（磁盘只读；多图文件全部合并，键为 task_node_id）
    nodes: Dict[str, Dict[str, Any]] = {}
    try:
        ws_info = workspace_manager.get_workspace_by_id(workspace_id)
        graphs_dir = Path(ws_info["path"]) / ".dawei" / "task_graphs"
        for graph_file in graphs_dir.glob("*.json"):
            with graph_file.open(encoding="utf-8") as f:
                graph = json.load(f)
            for node_id, node in (graph.get("nodes") or {}).items():
                nodes[node_id] = node
    except Exception:  # noqa: BLE001 — 图不可读则退回时间窗回退
        logger.exception("Failed to load task graphs for subtask grouping: ")

    def _iso(value: Any) -> datetime | None:
        try:
            return datetime.fromisoformat(str(value)) if value else None
        except (TypeError, ValueError):
            return None

    user_convs = [c for c in conversations if c.get("task_type") != "subtask"]
    for sub in subs:
        parent_id: str | None = None
        # 1) 祖先链（含自身）找 root_conversation_id 盖章
        current = nodes.get(sub["source_task_id"])
        guard = 0
        while current is not None and guard < 32:
            guard += 1
            stamped = ((current.get("data") or {}).get("metadata") or {}).get("root_conversation_id")
            if stamped:
                parent_id = str(stamped)
                break
            parent = current.get("parent_id")
            current = nodes.get(parent) if parent else None

        # 2) 时间窗回退（旧数据）
        if parent_id is None:
            sub_created = _iso(sub.get("created_at"))
            if sub_created is not None:
                best: tuple[str, datetime] | None = None
                for u in user_convs:
                    u_created = _iso(u.get("created_at"))
                    u_updated = _iso(u.get("updated_at"))
                    if u_created and u_updated and u_created <= sub_created <= u_updated:
                        if best is None or u_updated > best[1]:
                            best = (u["id"], u_updated)
                if best:
                    parent_id = best[0]
                elif len(user_convs) == 1:
                    parent_id = user_convs[0]["id"]

        sub["parent_conversation_id"] = parent_id


@router.get("")
async def get_workspace_conversations(
    workspace_id: str,
    request: Request,
    page: int = 1,
    limit: int = 50,
    sort_by: str = "updatedAt",
    sort_order: str = "desc",
    task_type: str | None = None,  # 新增：按任务类型过滤
):
    """Get conversations from a workspace with pagination and filtering support.

    Args:
        workspace_id: Workspace identifier
        request: FastAPI request (for JWT-based user/tenant authorization)
        page: Page number (default: 1)
        limit: Items per page (default: 50)
        sort_by: Sort field (default: updatedAt)
        sort_order: Sort order asc/desc (default: desc)
        task_type: Filter by task type - "user", "scheduled", or None for all (default: None)
    """
    # 鉴权说明：归属校验由 router 级依赖 require_workspace_access 统一完成
    # （owner_user_id + tenant_id 复核），此处仅校验 workspace 存在性。
    workspace_info = workspace_manager.get_workspace_by_id(workspace_id)
    if not workspace_info:
        raise HTTPException(
            status_code=404,
            detail=f"Workspace with ID '{workspace_id}' not found.",
        )

    chat_history_dir = get_chat_history_dir_for_workspace(workspace_id)

    conversation_files = list(chat_history_dir.glob("*.json"))

    conversations = []
    for file_path in conversation_files:
        conversation = load_conversation_file(file_path)
        if conversation:
            # 按 task_type 过滤
            if task_type is None or conversation.get("task_type") == task_type:
                conversations.append(conversation)

    # 任务列表嵌套：subtask 会话标注归父（盖章优先，旧数据时间窗回退）
    _annotate_subtask_parent_conversations(conversations, workspace_id)

    # Sort conversations
    reverse_order = sort_order == "desc"
    conversations.sort(key=lambda x: x["lastUpdated"], reverse=reverse_order)

    # Pagination
    total = len(conversations)
    total_pages = (total + limit - 1) // limit if limit > 0 else 1

    # Apply pagination
    start_idx = (page - 1) * limit
    end_idx = start_idx + limit
    paginated_conversations = conversations[start_idx:end_idx]

    workspace_name = workspace_info.get("name", "default") if workspace_info else "default"

    return {
        "success": True,
        "workspace_name": workspace_name,
        "conversations": paginated_conversations,
        "page": page,
        "limit": limit,
        "total": total,
        "totalPages": total_pages,
    }


@router.post("")
async def save_or_create_workspace_conversations(workspace_id: str, request: Request):
    """Create a single conversation or bulk-save conversations to a workspace.

    Supports two request body formats:
    - **Single object** (create): ``{"title": "新任务", ...}`` — generates an id, returns the created conversation.
    - **Array** (bulk save): ``[{"id": "...", ...}, ...]`` — existing bulk-save behavior.
    """
    body = await request.json()
    chat_history_dir = get_chat_history_dir_for_workspace(workspace_id)
    workspace_info = workspace_manager.get_workspace_by_id(workspace_id)
    workspace_name = workspace_info.get("name") if workspace_info else "default"

    # Single conversation creation: body is a dict without being wrapped in a list
    if isinstance(body, dict):
        conversation_id_val = body.get("id") or str(uuid.uuid4())
        title = body.get("title", "新对话")
        now = datetime.now(UTC).isoformat()

        conversation_data = {
            "id": conversation_id_val,
            "title": title,
            "messages": body.get("messages", []),
            "messageCount": body.get("messageCount", 0),
            "metadata": body.get("metadata", {}),
            "createdAt": body.get("createdAt", now),
            "updatedAt": body.get("updatedAt", now),
        }
        # Merge with any extra fields from the request body
        for key, value in body.items():
            if key not in conversation_data:
                conversation_data[key] = value

        file_path = chat_history_dir / f"{conversation_id_val}.json"
        with file_path.open("w", encoding="utf-8") as f:
            json.dump(conversation_data, f, ensure_ascii=False, indent=2)

        return {
            "success": True,
            "message": "对话创建成功",
            "workspace_name": workspace_name,
            "id": conversation_id_val,
            "title": title,
            "createdAt": conversation_data["createdAt"],
            "updatedAt": conversation_data["updatedAt"],
        }

    # Bulk save: body is a list of conversation dicts
    if isinstance(body, list):
        saved_count = 0
        for conversation in body:
            conversation_id_val = conversation.get("id")
            if not conversation_id_val:
                continue

            file_path = chat_history_dir / f"{conversation_id_val}.json"

            existing_data = {}
            if file_path.exists():
                with Path(file_path).open(encoding="utf-8") as f:
                    existing_data = json.load(f)

            existing_data.update(conversation)

            with file_path.open("w", encoding="utf-8") as f:
                json.dump(existing_data, f, ensure_ascii=False, indent=2)

            saved_count += 1

        return {
            "success": True,
            "message": f"成功保存 {saved_count} 个对话",
            "workspace_name": workspace_name,
            "saved_count": saved_count,
        }

    raise HTTPException(status_code=422, detail="Request body must be a JSON object or array")


@router.get("/{conversation_id}")
async def get_workspace_conversation(
    workspace_id: str,
    conversation_id: str,
    skip: int = 0,
    limit: int | None = None,
    include_metadata: bool = True,
    order: str = "asc",  # 'asc' = oldest first, 'desc' = newest first
):
    """Get a specific conversation from a workspace with pagination support.

    Args:
        workspace_id: Workspace identifier
        conversation_id: Conversation identifier
        skip: Number of messages to skip (for pagination, default: 0)
        limit: Maximum number of messages to return (default: None = all messages)
        include_metadata: Whether to include conversation metadata (default: True)
        order: Message order - 'asc' for oldest first, 'desc' for newest first (default: 'asc')

    """
    chat_history_dir = get_chat_history_dir_for_workspace(workspace_id)
    conversation_file = chat_history_dir / f"{conversation_id}.json"

    if not conversation_file.exists():
        # New conversation with no history yet — return empty response
        return {
            "success": True,
            "conversation": {
                "id": conversation_id,
                "title": "",
                "messages": [],
                "messageCount": 0,
                "pagination": {
                    "skip": 0,
                    "limit": limit,
                    "returned": 0,
                    "total": 0,
                    "hasMore": False,
                },
            },
            "message": "No conversation history yet",
        }

    with Path(conversation_file).open(encoding="utf-8") as f:
        conversation_data = json.load(f)

    # Extract messages
    messages = conversation_data.get("messages", [])
    total_messages = len(messages)

    # Apply pagination based on order
    if order == "desc":
        # Load newest messages first (from the end)
        # skip=0, limit=50 -> returns last 50 messages
        # Messages are returned in chronological order (oldest first, newest last)
        end_index = total_messages - skip
        start_index = end_index - limit if limit is not None else 0
        start_index = max(start_index, 0)
        paginated_messages = messages[start_index:end_index]
        # Keep messages in chronological order (newest at the end of array)
        # This ensures frontend can display them correctly (newest at bottom)
    else:
        # Load oldest messages first (from the beginning)
        paginated_messages = messages[skip : skip + limit] if limit is not None else messages[skip:] if skip > 0 else messages
        skip + len(paginated_messages) < total_messages

    # Build response
    response_data = {
        "success": True,
        "conversation": {
            "id": conversation_data.get("id", conversation_id),
            "title": conversation_data.get("title", ""),
            "messages": paginated_messages,
            "messageCount": total_messages,
            "pagination": {
                "skip": skip,
                "limit": limit,
                "returned": len(paginated_messages),
                "total": total_messages,
                "hasMore": skip + len(paginated_messages) < total_messages,
            },
        },
        "message": f"Loaded {len(paginated_messages)}/{total_messages} messages",
    }

    # Include metadata if requested
    if include_metadata:
        response_data["conversation"]["metadata"] = conversation_data.get("metadata", {})
        response_data["conversation"]["createdAt"] = conversation_data.get("createdAt")
        response_data["conversation"]["updatedAt"] = conversation_data.get("updatedAt")

    return response_data


@router.post("/{conversation_id}")
async def save_workspace_conversation(workspace_id: str, conversation_id: str, conversation: dict):
    """Save a specific conversation to a workspace."""
    chat_history_dir = get_chat_history_dir_for_workspace(workspace_id)
    conversation_file = chat_history_dir / f"{conversation_id}.json"

    existing_data = {}
    if conversation_file.exists():
        with Path(conversation_file).open(encoding="utf-8") as f:
            existing_data = json.load(f)

    existing_data.update(conversation)

    with conversation_file.open("w", encoding="utf-8") as f:
        json.dump(existing_data, f, ensure_ascii=False, indent=2)

    workspace_info = workspace_manager.get_workspace_by_id(workspace_id)
    workspace_name = workspace_info.get("name") if workspace_info else "default"

    return {
        "success": True,
        "message": "对话保存成功",
        "workspace_name": workspace_name,
        "conversation_id": conversation_id,
    }


def _resolve_subtask_child_ids(
    chat_history_dir: Path, workspace_id: str, parent_conversation_id: str
) -> List[str]:
    """级联删除支持（2026-09-24）：解析折叠在指定父会话下的子任务会话 id 列表。

    必须在删除父会话文件**之前**调用 —— 归父计算依赖完整会话列表（父文件先
    消失会让时间窗回退误判甚至把子任务错挂到其他唯一候选上）。单个会话文件
    损坏只跳过该文件，不阻断整体解析。
    """
    conversations: List[Dict[str, Any]] = []
    for file_path in chat_history_dir.glob("*.json"):
        try:
            conversations.append(load_conversation_file(file_path))
        except Exception:  # noqa: BLE001 — 损坏文件跳过
            logger.warning("Skipping unreadable conversation file: %s", file_path)
    _annotate_subtask_parent_conversations(conversations, workspace_id)
    return [
        c["id"]
        for c in conversations
        if c.get("parent_conversation_id") == parent_conversation_id
    ]


@router.delete("/{conversation_id}")
async def delete_workspace_conversation(workspace_id: str, conversation_id: str):
    """Delete a specific conversation from a workspace.

    级联（2026-09-24）：删除父任务时，折叠其下的子任务会话一并删除
    （前端任务列表以嵌套分组呈现，子任务不是用户的独立资产）。
    """
    chat_history_dir = get_chat_history_dir_for_workspace(workspace_id)
    conversation_file = chat_history_dir / f"{conversation_id}.json"

    if not conversation_file.exists():
        raise HTTPException(status_code=404, detail=f"Conversation '{conversation_id}' not found")

    # 先解析级联子会话（父文件仍在盘，归父计算才可靠），再统一删除
    cascaded_ids: List[str] = []
    try:
        cascaded_ids = _resolve_subtask_child_ids(chat_history_dir, workspace_id, conversation_id)
    except Exception:  # noqa: BLE001 — 级联解析失败不阻断父会话删除
        logger.exception("Failed to resolve subtask children for cascade delete: ")

    conversation_file.unlink()
    for child_id in cascaded_ids:
        try:
            (chat_history_dir / f"{child_id}.json").unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to cascade delete subtask conversation %s: ", child_id)

    return {
        "success": True,
        "conversation_id": conversation_id,
        "cascaded_conversation_ids": cascaded_ids,
        "message": (
            f"Conversation deleted successfully (+{len(cascaded_ids)} subtask conversations)"
            if cascaded_ids
            else "Conversation deleted successfully"
        ),
    }


@router.delete("")
async def delete_all_workspace_conversations(workspace_id: str):
    """Delete all conversations from a workspace."""
    chat_history_dir = get_chat_history_dir_for_workspace(workspace_id)

    if not chat_history_dir.exists():
        return {
            "success": True,
            "deletedCount": 0,
            "message": "No conversations to delete",
        }

    # 获取所有对话文件
    conversation_files = list(chat_history_dir.glob("*.json"))
    deleted_count = 0

    # 删除所有对话文件
    for conversation_file in conversation_files:
        conversation_file.unlink()
        deleted_count += 1

    return {
        "success": True,
        "deletedCount": deleted_count,
        "message": f"Successfully deleted {deleted_count} conversations",
    }
