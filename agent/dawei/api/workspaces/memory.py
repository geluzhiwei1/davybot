# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Memory API Endpoints
REST API for memory system operations
"""

import csv
import io
import json
import logging
import os
from datetime import datetime, timezone
from dawei.core.datetime_compat import UTC
from pathlib import Path
from typing import List, Dict, Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

from dawei import get_dawei_home
from dawei.memory.memory_graph import MemoryEntry, MemoryGraph, MemoryType

# Router following the same pattern as files.py
router = APIRouter(tags=["memory"])


# ============================================================================
# Pydantic Models
# ============================================================================


class MemoryCreateRequest(BaseModel):
    """Request model for creating a memory"""

    subject: str
    predicate: str
    object: str
    memory_type: str = "fact"
    confidence: float = 0.8
    energy: float = 1.0
    keywords: List[str] = []


class MemoryUpdateRequest(BaseModel):
    """Request model for updating a memory"""

    predicate: str | None = None
    object: str | None = None
    valid_end: str | None = None
    confidence: float | None = None
    energy: float | None = None
    keywords: List[str] | None = None


class MemoryResponse(BaseModel):
    """Response model for a memory"""

    id: str
    subject: str
    predicate: str
    object: str
    valid_start: str
    valid_end: str | None
    confidence: float
    energy: float
    access_count: int
    memory_type: str
    keywords: List[str]
    source_event_id: str | None
    metadata: Dict[str, Any]
    created_at: str


class MemoryListResponse(BaseModel):
    """Response model for memory list"""

    items: List[MemoryResponse]
    total: int
    page: int
    page_size: int


class MemoryStatsResponse(BaseModel):
    """Response model for memory statistics"""

    total: int
    by_type: Dict[str, int]
    avg_confidence: float
    avg_energy: float


class GraphDataResponse(BaseModel):
    """Response model for graph data"""

    nodes: List[Dict[str, Any]]
    links: List[Dict[str, Any]]


class AssociativeRetrievalRequest(BaseModel):
    """Request model for associative retrieval"""

    entities: List[str]
    hops: int = 1
    min_energy: float = 0.2


# ============================================================================
# Helper Functions
# ============================================================================


def _get_memory_db_path(workspace_id: str) -> str:
    """Get path to memory database for workspace"""
    workspace_path = _get_workspace_path(workspace_id)
    if workspace_path:
        return str(workspace_path / ".dawei" / "memory.db")
    return None


def _get_workspace_path(workspace_id: str) -> Path | None:
    """Get workspace path from workspace ID by reading workspaces.json"""
    try:
        dawei_home = Path(os.getenv("DAWEI_HOME", str(Path("~/.dawei").expanduser())))
        workspaces_file = dawei_home / "workspaces.json"

        if workspaces_file.exists():
            import json

            with workspaces_file.open(encoding="utf-8") as f:
                data = json.load(f)

            for ws in data.get("workspaces", []):
                if ws.get("id") == workspace_id:
                    ws_path = Path(ws.get("path", ""))
                    if ws_path.exists():
                        return ws_path
    except Exception:
        # Workspace file not found or invalid, fallback will handle
        pass

    # Fallback: try {DAWEI_HOME}/{workspace_id}
    workspaces_root = get_dawei_home()
    fallback_path = workspaces_root / workspace_id
    if fallback_path.exists():
        return fallback_path

    return None


def _memory_to_response(memory) -> MemoryResponse:
    """Convert MemoryEntry to MemoryResponse"""
    return MemoryResponse(
        id=memory.id,
        subject=memory.subject,
        predicate=memory.predicate,
        object=memory.object,
        valid_start=memory.valid_start.isoformat(),
        valid_end=memory.valid_end.isoformat() if memory.valid_end else None,
        confidence=memory.confidence,
        energy=memory.energy,
        access_count=memory.access_count,
        memory_type=memory.memory_type.value,
        keywords=memory.keywords,
        source_event_id=memory.source_event_id,
        metadata=memory.metadata,
        created_at=(memory.created_at.isoformat() if hasattr(memory, "created_at") else datetime.now(UTC).isoformat()),
    )


# ============================================================================
# Memory CRUD Endpoints
# ============================================================================


@router.get("/{workspace_id}/memory")
async def list_memories(
    workspace_id: str,
    type: str | None = Query(None),
    min_confidence: float | None = Query(None),
    min_energy: float | None = Query(None),
    subject: str | None = Query(None),
    only_valid: bool = Query(True),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """List all memories with optional filters"""
    db_path = _get_memory_db_path(workspace_id)

    # Initialize memory graph (will create database if needed)
    graph = MemoryGraph(db_path)

    # Convert type
    memory_type = MemoryType(type) if type else None

    # Query
    memories = await graph.query_temporal(
        subject=subject,
        memory_type=memory_type,
        min_energy=min_energy,
        only_valid=only_valid,
    )

    # Apply additional filters
    if min_confidence is not None:
        memories = [m for m in memories if m.confidence >= min_confidence]

    # Pagination
    total = len(memories)
    start = (page - 1) * page_size
    end = start + page_size
    paginated = memories[start:end]

    return MemoryListResponse(
        items=[_memory_to_response(m) for m in paginated],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/{workspace_id}/memory", status_code=201)
async def create_memory(workspace_id: str, request: MemoryCreateRequest):
    """Create a new memory entry"""
    db_path = _get_memory_db_path(workspace_id)

    # Initialize memory graph (will create DB if needed)
    graph = MemoryGraph(db_path)

    import uuid

    memory = MemoryEntry(
        id=str(uuid.uuid4()),
        subject=request.subject,
        predicate=request.predicate,
        object=request.object,
        valid_start=datetime.now(UTC),
        memory_type=MemoryType(request.memory_type),
        confidence=request.confidence,
        energy=request.energy,
        keywords=request.keywords,
        metadata={"source": "api"},
    )

    memory_id = await graph.add_memory(memory)

    # Return created memory
    created = await graph.get_memory(memory_id)
    return _memory_to_response(created)


@router.get("/{workspace_id}/memory/stats")
async def get_stats(workspace_id: str):
    """Get memory statistics"""
    db_path = _get_memory_db_path(workspace_id)
    graph = MemoryGraph(db_path)
    stats = await graph.get_stats()

    return {
        "total": stats.total,
        "by_type": dict(stats.by_type),
        "avg_confidence": stats.avg_confidence,
        "avg_energy": stats.avg_energy,
    }


@router.get("/{workspace_id}/memory/graph")
async def get_graph_data(
    workspace_id: str,
    type: str | None = Query(None),
    min_energy: float | None = Query(0.3),
):
    """Get graph data for visualization"""
    db_path = _get_memory_db_path(workspace_id)

    graph = MemoryGraph(db_path)

    memories = await graph.query_temporal(
        memory_type=MemoryType(type) if type else None,
        min_energy=min_energy,
        only_valid=True,
    )

    # Build nodes and links
    nodes = []
    links = []
    node_ids = set()

    for mem in memories:
        # Create subject node
        if mem.subject not in node_ids:
            nodes.append(
                {
                    "id": mem.subject,
                    "label": mem.subject,
                    "type": mem.memory_type.value,
                    "energy": mem.energy,
                },
            )
            node_ids.add(mem.subject)

        # Create object node
        if mem.object not in node_ids:
            nodes.append(
                {
                    "id": mem.object,
                    "label": mem.object,
                    "type": mem.memory_type.value,
                    "energy": mem.energy,
                },
            )
            node_ids.add(mem.object)

        # Create link
        links.append(
            {
                "source": mem.subject,
                "target": mem.object,
                "label": mem.predicate,
                "confidence": mem.confidence,
                "id": mem.id,
            },
        )

    return GraphDataResponse(nodes=nodes, links=links)


@router.get("/{workspace_id}/memory/search")
async def search_memories(
    workspace_id: str,
    q: str = Query(...),
    type: str | None = Query(None),
    min_confidence: float | None = Query(None),
):
    """Search memories by keyword"""
    db_path = _get_memory_db_path(workspace_id)

    graph = MemoryGraph(db_path)
    memories = await graph.search_memories(q, limit=100)

    # Apply filters
    if type:
        memories = [m for m in memories if m.memory_type.value == type]
    if min_confidence:
        memories = [m for m in memories if m.confidence >= min_confidence]

    return [_memory_to_response(m) for m in memories]


@router.get("/{workspace_id}/memory/temporal")
async def query_temporal(
    workspace_id: str,
    subject: str | None = Query(None),
    predicate: str | None = Query(None),
    object: str | None = Query(None),
    at_time: str | None = Query(None),
    only_valid: bool = Query(True),
):
    """Query memories with temporal filtering"""
    db_path = _get_memory_db_path(workspace_id)

    graph = MemoryGraph(db_path)

    at_time_dt = None
    if at_time:
        at_time_dt = datetime.fromisoformat(at_time)

    memories = await graph.query_temporal(
        subject=subject,
        predicate=predicate,
        object=object,
        at_time=at_time_dt,
        only_valid=only_valid,
    )

    return [_memory_to_response(m) for m in memories]


@router.get("/{workspace_id}/memory/timeline")
async def get_timeline_data(
    workspace_id: str,
    subject: str | None = Query(None),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
):
    """Get timeline data grouped by date"""
    db_path = _get_memory_db_path(workspace_id)

    graph = MemoryGraph(db_path)
    memories = await graph.get_all_memories(limit=1000)

    # Apply filters
    if subject:
        memories = [m for m in memories if m.subject == subject]
    if start_date:
        start_dt = datetime.fromisoformat(start_date)
        memories = [m for m in memories if m.valid_start >= start_dt]
    if end_date:
        end_dt = datetime.fromisoformat(end_date)
        memories = [m for m in memories if m.valid_start <= end_dt]

    # Group by date
    timeline = {}
    for mem in memories:
        date_key = mem.valid_start.date().isoformat()
        if date_key not in timeline:
            timeline[date_key] = []
        timeline[date_key].append(_memory_to_response(mem))

    # Sort by date
    sorted_dates = sorted(timeline.keys(), reverse=True)

    return [{"date": date, "memories": timeline[date]} for date in sorted_dates]


# ============================================================================
# Export Endpoints
# ============================================================================


@router.get("/{workspace_id}/memory/export")
async def export_memories(
    workspace_id: str,
    format: str = Query("json", pattern="^(json|csv|ndjson)$"),
    type: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
):
    """Export memories in various formats"""
    db_path = _get_memory_db_path(workspace_id)

    graph = MemoryGraph(db_path)
    memories = await graph.get_all_memories()

    # Apply filters
    if type:
        memories = [m for m in memories if m.memory_type.value == type]
    if date_from:
        start_dt = datetime.fromisoformat(date_from)
        memories = [m for m in memories if m.valid_start >= start_dt]
    if date_to:
        end_dt = datetime.fromisoformat(date_to)
        memories = [m for m in memories if m.valid_start <= end_dt]

    if format == "json":
        data = [_memory_to_response(m).dict() for m in memories]
        return StreamingResponse(
            io.StringIO(json.dumps(data, indent=2)),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=memories.json"},
        )

    if format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "id",
                "subject",
                "predicate",
                "object",
                "type",
                "confidence",
                "energy",
                "valid_start",
                "valid_end",
            ],
        )
        for m in memories:
            writer.writerow(
                [
                    m.id,
                    m.subject,
                    m.predicate,
                    m.object,
                    m.memory_type.value,
                    m.confidence,
                    m.energy,
                    m.valid_start.isoformat(),
                    m.valid_end.isoformat() if m.valid_end else "",
                ],
            )
        return StreamingResponse(
            io.StringIO(output.getvalue()),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=memories.csv"},
        )

    if format == "ndjson":
        lines = [json.dumps(_memory_to_response(m).dict()) for m in memories]
        return StreamingResponse(
            io.StringIO("\n".join(lines)),
            media_type="application/x-ndjson",
            headers={"Content-Disposition": "attachment; filename=memories.ndjson"},
        )
    return None


@router.post("/{workspace_id}/memory/associative")
async def retrieve_associative(workspace_id: str, request: AssociativeRetrievalRequest):
    """Associative retrieval via graph traversal"""
    db_path = _get_memory_db_path(workspace_id)

    graph = MemoryGraph(db_path)
    memories = await graph.retrieve_associative(
        query_entities=request.entities,
        hops=request.hops,
        min_energy=request.min_energy,
    )

    return [_memory_to_response(m) for m in memories]


# ============================================================================
# Statistics and Analytics
# ============================================================================


@router.post("/{workspace_id}/memory/bulk-delete")
async def bulk_delete_memories(workspace_id: str, memory_ids: List[str]):
    """Delete multiple memories"""
    db_path = _get_memory_db_path(workspace_id)

    graph = MemoryGraph(db_path)
    deleted_count = 0

    for memory_id in memory_ids:
        if await graph.delete_memory(memory_id):
            deleted_count += 1

    return {"deleted": deleted_count}


# ============================================================================
# Search and Query Endpoints
# ============================================================================


@router.get("/{workspace_id}/memory/{memory_id}")
async def get_memory(workspace_id: str, memory_id: str):
    """Get a single memory by ID"""
    db_path = _get_memory_db_path(workspace_id)

    graph = MemoryGraph(db_path)
    memory = await graph.get_memory(memory_id)

    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")

    return _memory_to_response(memory)


@router.patch("/{workspace_id}/memory/{memory_id}")
async def update_memory(workspace_id: str, memory_id: str, request: MemoryUpdateRequest):
    """Update an existing memory entry"""
    db_path = _get_memory_db_path(workspace_id)

    graph = MemoryGraph(db_path)

    # Convert valid_end
    valid_end = None
    if request.valid_end:
        valid_end = datetime.fromisoformat(request.valid_end)

    success = await graph.update_memory(
        memory_id,
        predicate=request.predicate,
        object=request.object,
        valid_end=valid_end,
        confidence=request.confidence,
        energy=request.energy,
        keywords=request.keywords,
    )

    if not success:
        raise HTTPException(status_code=404, detail="Memory not found")

    updated = await graph.get_memory(memory_id)
    return _memory_to_response(updated)


@router.delete("/{workspace_id}/memory/{memory_id}", status_code=204)
async def delete_memory(workspace_id: str, memory_id: str):
    """Delete a memory entry"""
    db_path = _get_memory_db_path(workspace_id)

    graph = MemoryGraph(db_path)
    success = await graph.delete_memory(memory_id)

    if not success:
        raise HTTPException(status_code=404, detail="Memory not found")


# ============================================================================
# Memory Extraction Endpoint
# ============================================================================


class ExtractRequest(BaseModel):
    """请求模型"""

    text: str | None = None  # 可选的文本输入


@router.post("/{workspace_id}/memory/extract")
async def extract_memories(workspace_id: str, request: ExtractRequest | None = None):
    """从对话中提取记忆

    支持两种方式：
    1. 传入 text 参数：从指定文本提取
    2. 不传 text：从工作区对话文件提取

    """
    import re
    import uuid
    from datetime import datetime, timezone

    db_path = _get_memory_db_path(workspace_id)
    graph = MemoryGraph(db_path)

    # 获取工作区的实际路径
    workspace_path = _get_workspace_path(workspace_id)

    # 尝试从对话文件读取
    messages_text = None
    if workspace_path and workspace_path.exists():
        # 尝试加载对话
        conversation_data = None
        conversation_file = workspace_path / ".dawei" / "conversation.json"
        if conversation_file.exists():
            import json

            with conversation_file.open(encoding="utf-8") as f:
                conversation_data = json.load(f)

        if not conversation_data or "messages" not in conversation_data:
            # 尝试查找对话历史文件
            conversation_dir = workspace_path / ".dawei" / "conversations"
            if conversation_dir.exists():
                files = sorted(conversation_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)
                if files:
                    import json

                    with files[0].open(encoding="utf-8") as f:
                        conversation_data = json.load(f)

        if conversation_data and "messages" in conversation_data:
            messages = conversation_data.get("messages", [])
            if len(messages) >= 2:
                messages_text = "\n".join([f"{msg.get('role', 'unknown')}: {str(msg.get('content', ''))[:500]}" for msg in messages[-20:] if msg.get("content")])

    if not messages_text or not messages_text.strip():
        # 返回提示信息
        return {
            "success": False,
            "workspace_id": workspace_id,
            "extracted": 0,
            "method": "none",
            "details": [],
            "message": "没有找到对话记录。请先与 Agent 对话，确保对话已保存。",
            "requires_input": False,
        }

    # 使用 LLM 智能提取
    extraction_result = {"extracted": 0, "method": "llm", "details": []}

    try:
        from dawei.entity.lm_messages import UserMessage
        from dawei.llm_api.llm_provider import LLMProvider

        llm_provider = LLMProvider()

        extraction_prompt = f"""从以下对话中提取结构化事实。

要求：
1. 每行一个事实，格式为：[主体] [关系] [对象]
2. 只提取重要的事实、偏好和用户信息
3. 关系使用英文动词或短语：prefers, likes, uses, knows, works_on 等
4. 如果没有可提取的信息，返回 "无"

示例：
- User prefers Python
- Project uses FastAPI
- User dislikes JavaScript
- User works_on software development

对话：
{messages_text}

提取的事实："""

        response = await llm_provider.process_message(
            messages=[UserMessage(content=extraction_prompt)],
            max_tokens=500,
            temperature=0.3,
        )

        logger.info(f"LLM response raw type: {type(response)}, value: {response}")

        response_text = ""
        if response:
            if isinstance(response, dict):
                response_text = response.get("content", "").strip() if response.get("content") else ""
            elif isinstance(response, str):
                response_text = response.strip()

        # 调试日志
        logger.info(f"LLM response processed: {response_text[:200] if response_text else 'empty'}")

        # 检查是否有可提取的信息
        if response_text and response_text.lower() != "无" and response_text.lower() != "none":
            for line in response_text.split("\n"):
                line = line.strip()
                if not line or line.startswith("-"):
                    line = line.lstrip("-").strip()

                parts = line.split(maxsplit=2)
                if len(parts) >= 3:
                    # 推断记忆类型
                    memory_type = "fact"
                    predicate_lower = parts[1].lower()
                    if any(w in predicate_lower for w in ["prefers", "likes", "loves", "wants"]):
                        memory_type = "preference"
                    elif any(w in predicate_lower for w in ["uses", "requires", "needs"]):
                        memory_type = "procedure"
                    elif any(w in predicate_lower for w in ["learned", "discovered"]):
                        memory_type = "strategy"

                    # 提取关键词
                    keywords = []
                    for part in parts:
                        keywords.extend(re.findall(r"\b[A-Z][a-z]+\b", part))

                    memory = MemoryEntry(
                        id=str(uuid.uuid4()),
                        subject=parts[0],
                        predicate=parts[1],
                        object=parts[2],
                        valid_start=datetime.now(UTC),
                        memory_type=MemoryType(memory_type),
                        confidence=0.7,
                        energy=1.0,
                        keywords=list(set(keywords))[:5],
                        metadata={
                            "source": "llm_extraction",
                        },
                    )

                    await graph.add_memory(memory)
                    extraction_result["extracted"] += 1
                    extraction_result["details"].append(f"{parts[0]} {parts[1]} {parts[2]}")
        else:
            extraction_result["details"].append("No extractable information found")

    except Exception as e:
        logger.warning(f"LLM extraction failed: {e}", exc_info=True)
        extraction_result["details"].append(f"LLM error: {str(e)}")

    return {
        "success": True,
        "workspace_id": workspace_id,
        "extracted": extraction_result["extracted"],
        "method": extraction_result["method"],
        "details": extraction_result["details"][:10],
        "message": f"成功提取 {extraction_result['extracted']} 条记忆",
        "requires_input": False,
    }


# ============================================================================
# Batch Memory Extraction Endpoints (New)
# ============================================================================


class BatchExtractRequest(BaseModel):
    """批量提取记忆请求"""

    date: str | None = Field(
        None,
        description="目标日期 (格式: YYYY-MM-DD)，为空则提取今天",
        examples=["2026-02-18"],
    )
    extract_all: bool = Field(
        False,
        description="是否提取所有会话（False=仅提取未提取过的）",
    )


class BatchExtractResponse(BaseModel):
    """批量提取响应"""

    success: bool
    date: str | None = None
    total_conversations: int = 0
    processed_conversations: int = 0
    extracted_memories: int = 0
    skipped: int = 0
    processed_files: list[str] = []
    error: str | None = None


@router.post("/{workspace_id}/memory/extract/batch", response_model=BatchExtractResponse)
async def batch_extract_memories(
    workspace_id: str,
    request: BatchExtractRequest,
):
    """批量提取记忆（从会话文件）

    从指定日期的会话文件中批量提取记忆，支持：
    1. 指定日期提取
    2. 提取今天的所有会话

    Args:
        workspace_id: 工作空间ID
        request: 批量提取请求

    Returns:
        提取结果
    """
    try:
        # 获取工作空间路径
        workspace_path = _get_workspace_path(workspace_id)
        if not workspace_path or not workspace_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Workspace not found: {workspace_id}",
            )

        # 获取数据库路径
        db_path = _get_memory_db_path(workspace_id)
        if not db_path:
            raise HTTPException(
                status_code=500,
                detail="Failed to get memory database path",
            )

        # 初始化MemoryGraph
        graph = MemoryGraph(db_path)

        # 导入批量提取器
        from dawei.memory.batch_extractor import BatchMemoryExtractor

        # 创建批量提取器（不传LLM服务，使用规则提取）
        extractor = BatchMemoryExtractor(
            workspace_path=str(workspace_path),
            memory_graph=graph,
            llm_service=None,  # 使用规则提取，避免依赖LLM
        )

        # 确定提取日期
        target_date = request.date
        if not target_date:
            target_date = datetime.now(UTC).strftime("%Y-%m-%d")

        # 执行提取
        result = await extractor.extract_from_date(
            target_date=target_date,
            extract_all=request.extract_all,
        )

        logger.info(
            f"Batch memory extraction completed: "
            f"{result['extracted_memories']} memories from "
            f"{result['total_conversations']} conversations"
        )

        return BatchExtractResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Batch memory extraction failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Batch extraction failed: {str(e)}",
        )


@router.get("/{workspace_id}/memory/extract/scheduler/status")
async def get_extraction_scheduler_status(workspace_id: str):
    """获取记忆提取调度器状态

    Returns:
        调度器状态信息
    """
    # TODO: 实现调度器状态查询
    # 需要通过WebSocketManager获取活跃Agent实例
    return {
        "running": False,
        "scheduled_time": "00:00",
        "next_run": None,
        "workspace_id": workspace_id,
        "message": "Scheduler status not implemented yet",
    }
