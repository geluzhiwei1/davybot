# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""对话管理 API 路由"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from dawei.logg.logging import get_logger
from dawei.workspace import workspace_manager

logger = get_logger(__name__)

router = APIRouter(prefix="/api/workspaces/{workspace_id}/conversations", tags=["conversations"])


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


def load_conversation_file(file_path: Path) -> dict[str, Any]:
    """加载单个对话文件"""
    with Path(file_path).open(encoding="utf-8") as f:
        data = json.load(f)

    conversation_id = file_path.stem
    title = data.get("title", f"对话 {conversation_id}")
    last_updated = datetime.fromtimestamp(file_path.stat().st_mtime)

    return {
        "id": conversation_id,
        "title": title,
        "lastUpdated": last_updated,
        "messageCount": len(data.get("messages", [])),
        "path": str(file_path),
    }


@router.get("")
async def get_workspace_conversations(workspace_id: str):
    """Get conversations from a workspace."""
    chat_history_dir = get_chat_history_dir_for_workspace(workspace_id)

    conversation_files = list(chat_history_dir.glob("*.json"))

    conversations = []
    for file_path in conversation_files:
        conversation = load_conversation_file(file_path)
        if conversation:
            conversations.append(conversation)

    conversations.sort(key=lambda x: x["lastUpdated"], reverse=True)

    workspace_info = workspace_manager.get_workspace_by_id(workspace_id)
    workspace_name = workspace_info.get("name") if workspace_info else "default"

    return {
        "success": True,
        "workspace_name": workspace_name,
        "conversations": conversations,
        "count": len(conversations),
    }


@router.post("")
async def save_workspace_conversations(workspace_id: str, conversations: list[dict]):
    """Save conversations to a workspace."""
    chat_history_dir = get_chat_history_dir_for_workspace(workspace_id)
    saved_count = 0

    for conversation in conversations:
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

    workspace_info = workspace_manager.get_workspace_by_id(workspace_id)
    workspace_name = workspace_info.get("name") if workspace_info else "default"

    return {
        "success": True,
        "message": f"成功保存 {saved_count} 个对话",
        "workspace_name": workspace_name,
        "saved_count": saved_count,
    }


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
        raise HTTPException(status_code=404, detail=f"Conversation '{conversation_id}' not found")

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


@router.delete("/{conversation_id}")
async def delete_workspace_conversation(workspace_id: str, conversation_id: str):
    """Delete a specific conversation from a workspace."""
    chat_history_dir = get_chat_history_dir_for_workspace(workspace_id)
    conversation_file = chat_history_dir / f"{conversation_id}.json"

    if not conversation_file.exists():
        raise HTTPException(status_code=404, detail=f"Conversation '{conversation_id}' not found")

    conversation_file.unlink()

    return {
        "success": True,
        "conversation_id": conversation_id,
        "message": "Conversation deleted successfully",
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
        try:
            conversation_file.unlink()
            deleted_count += 1
        except (OSError, PermissionError) as e:
            # Graceful degradation: Continue deleting other files if one fails
            logger.warning(
                f"Failed to delete conversation file {conversation_file}: {e}",
                exc_info=True,
            )

    return {
        "success": True,
        "deletedCount": deleted_count,
        "message": f"Successfully deleted {deleted_count} conversations",
    }
