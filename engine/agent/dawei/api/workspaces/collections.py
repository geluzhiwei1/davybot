# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""工作区集合 API

工作区集合用于组织管理多个工作区，支持创建集合、添加/移除工作区。
"""

import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from dawei.core.datetime_compat import UTC
from dawei.storage.storage_provider import StorageProvider

logger = logging.getLogger(__name__)

router = APIRouter(tags=["workspaces-collections"])

COLLECTIONS_KEY = "collections"


# ==================== Pydantic 模型 ====================


class CreateCollectionRequest(BaseModel):
    """创建工作区集合请求"""

    name: str = Field(..., min_length=1, max_length=100, description="集合名称")
    description: str = Field("", max_length=500, description="集合描述")
    workspace_ids: List[str] = Field(default_factory=list, description="初始工作区ID列表")


class UpdateCollectionRequest(BaseModel):
    """更新工作区集合请求"""

    name: str | None = Field(None, min_length=1, max_length=100, description="集合名称")
    description: str | None = Field(None, max_length=500, description="集合描述")


class AddWorkspacesRequest(BaseModel):
    """向集合添加工作区"""

    workspace_ids: List[str] = Field(..., min_length=1, description="要添加的工作区ID列表")


class RemoveWorkspacesRequest(BaseModel):
    """从集合移除工作区"""

    workspace_ids: List[str] = Field(..., min_length=1, description="要移除的工作区ID列表")


# ==================== 存储辅助 ====================


async def _load_collections() -> List[Dict[str, Any]]:
    """从 workspaces.json 加载集合列表"""
    system_storage = StorageProvider.get_system_storage()

    if not await system_storage.exists("workspaces.json"):
        return []

    content = await system_storage.read_file("workspaces.json")
    data = json.loads(content)
    return data.get(COLLECTIONS_KEY, [])


async def _save_collections(collections: List[Dict[str, Any]]) -> None:
    """保存集合列表到 workspaces.json"""
    system_storage = StorageProvider.get_system_storage()

    if await system_storage.exists("workspaces.json"):
        content = await system_storage.read_file("workspaces.json")
        data = json.loads(content)
    else:
        data = {"workspaces": []}

    data[COLLECTIONS_KEY] = collections

    await system_storage.write_file(
        "workspaces.json",
        json.dumps(data, indent=2, ensure_ascii=False),
    )
    StorageProvider.clear_system_storage_cache()


def _validate_workspace_ids(workspace_ids: List[str]) -> None:
    """验证工作区ID列表中的ID是否都存在"""
    from dawei.workspace.workspace_manager import workspace_manager

    for wid in workspace_ids:
        info = workspace_manager.get_workspace_by_id(wid)
        if not info:
            raise HTTPException(status_code=404, detail=f"工作区 {wid} 不存在")


# ==================== API 路由 ====================


@router.get("/collections")
async def list_collections():
    """获取所有工作区集合"""
    collections = await _load_collections()
    return {"success": True, "collections": collections}


@router.post("/collections", status_code=201)
async def create_collection(request: CreateCollectionRequest):
    """创建工作区集合"""
    # 验证工作区ID
    if request.workspace_ids:
        _validate_workspace_ids(request.workspace_ids)

    collection_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()

    collection = {
        "id": collection_id,
        "name": request.name,
        "description": request.description,
        "workspace_ids": request.workspace_ids,
        "created_at": now,
        "updated_at": now,
    }

    collections = await _load_collections()
    collections.append(collection)
    await _save_collections(collections)

    logger.info(f"Created workspace collection: {collection_id} ({request.name})")
    return {"success": True, "collection": collection, "message": "工作区集合创建成功"}


@router.put("/collections/{collection_id}")
async def update_collection(collection_id: str, request: UpdateCollectionRequest):
    """更新工作区集合信息"""
    collections = await _load_collections()

    target = None
    for c in collections:
        if c["id"] == collection_id:
            target = c
            break

    if not target:
        raise HTTPException(status_code=404, detail="工作区集合不存在")

    if request.name is not None:
        target["name"] = request.name
    if request.description is not None:
        target["description"] = request.description

    target["updated_at"] = datetime.now(UTC).isoformat()

    await _save_collections(collections)
    logger.info(f"Updated workspace collection: {collection_id}")
    return {"success": True, "collection": target, "message": "工作区集合更新成功"}


@router.delete("/collections/{collection_id}")
async def delete_collection(collection_id: str):
    """删除工作区集合"""
    collections = await _load_collections()

    new_collections = [c for c in collections if c["id"] != collection_id]
    if len(new_collections) == len(collections):
        raise HTTPException(status_code=404, detail="工作区集合不存在")

    await _save_collections(new_collections)
    logger.info(f"Deleted workspace collection: {collection_id}")
    return {"success": True, "message": "工作区集合已删除"}


@router.post("/collections/{collection_id}/workspaces")
async def add_workspaces_to_collection(collection_id: str, request: AddWorkspacesRequest):
    """向集合中添加工作区"""
    # 验证工作区ID
    _validate_workspace_ids(request.workspace_ids)

    collections = await _load_collections()

    target = None
    for c in collections:
        if c["id"] == collection_id:
            target = c
            break

    if not target:
        raise HTTPException(status_code=404, detail="工作区集合不存在")

    # 添加不重复的工作区
    existing = set(target.get("workspace_ids", []))
    added = []
    for wid in request.workspace_ids:
        if wid not in existing:
            target.setdefault("workspace_ids", []).append(wid)
            existing.add(wid)
            added.append(wid)

    target["updated_at"] = datetime.now(UTC).isoformat()
    await _save_collections(collections)

    logger.info(f"Added {len(added)} workspaces to collection {collection_id}")
    return {"success": True, "collection": target, "added_count": len(added), "message": f"已添加 {len(added)} 个工作区"}


@router.delete("/collections/{collection_id}/workspaces")
async def remove_workspaces_from_collection(collection_id: str, workspace_ids: str = ""):
    """从集合中移除工作区

    使用 query parameter 传递工作区ID（逗号分隔）
    """
    if not workspace_ids:
        raise HTTPException(status_code=400, detail="请提供要移除的工作区ID")

    ids_to_remove = set(workspace_ids.split(","))

    collections = await _load_collections()

    target = None
    for c in collections:
        if c["id"] == collection_id:
            target = c
            break

    if not target:
        raise HTTPException(status_code=404, detail="工作区集合不存在")

    original_len = len(target.get("workspace_ids", []))
    target["workspace_ids"] = [
        wid for wid in target.get("workspace_ids", [])
        if wid not in ids_to_remove
    ]
    removed_count = original_len - len(target["workspace_ids"])

    target["updated_at"] = datetime.now(UTC).isoformat()
    await _save_collections(collections)

    logger.info(f"Removed {removed_count} workspaces from collection {collection_id}")
    return {"success": True, "collection": target, "removed_count": removed_count, "message": f"已移除 {removed_count} 个工作区"}
