# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Memory Extraction API
提供UI调用的记忆提取API端点
"""

import logging
from datetime import datetime, timezone
from dawei.core.datetime_compat import UTC
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from dawei.agentic.agent import is_memory_enabled
from dawei.api.v1 import websocket_manager_dep
from dawei.websocket.ws_server import WebSocketManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/memory", tags=["memory"])


# ============================================================================
# Request/Response Models
# ============================================================================


class ExtractMemoryRequest(BaseModel):
    """手动提取记忆请求"""

    date: str | None = Field(
        None,
        description="目标日期 (格式: YYYY-MM-DD)，为空则提取今天",
        examples=["2026-02-18"],
    )
    extract_all: bool = Field(
        False,
        description="是否提取所有会话（False=仅提取未提取过的）",
    )


class ExtractMemoryResponse(BaseModel):
    """提取记忆响应"""

    success: bool
    date: str | None = None
    total_conversations: int = 0
    processed_conversations: int = 0
    extracted_memories: int = 0
    skipped: int = 0
    processed_files: list[str] = []
    error: str | None = None


class SchedulerStatusResponse(BaseModel):
    """调度器状态响应"""

    running: bool
    scheduled_time: str
    next_run: str | None = None
    workspace_path: str


# ============================================================================
# API Endpoints
# ============================================================================


@router.post("/extract", response_model=ExtractMemoryResponse)
async def extract_memories(
    request: ExtractMemoryRequest,
    ws_manager: WebSocketManager = websocket_manager_dep,
):
    """手动触发记忆提取

    从会话文件中批量提取记忆，可以指定日期或提取今天的所有会话。

    Args:
        request: 提取请求
        ws_manager: WebSocket管理器（用于获取活跃Agent实例）

    Returns:
        提取结果
    """
    try:
        # 获取活跃的Agent实例
        active_agent = ws_manager.get_active_agent()
        if not active_agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No active agent found. Please start an agent first.",
            )

        # 检查memory系统是否启用
        if not is_memory_enabled(active_agent.user_workspace):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Memory system is not enabled for this workspace",
            )

        # 检查memory_graph是否存在
        if not hasattr(active_agent, "memory_graph") or active_agent.memory_graph is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Memory system is not initialized",
            )

        # 导入批量提取器
        from dawei.memory.batch_extractor import BatchMemoryExtractor

        extractor = BatchMemoryExtractor(
            workspace_path=str(active_agent.user_workspace.absolute_path),
            memory_graph=active_agent.memory_graph,
            llm_service=getattr(
                active_agent.execution_engine, "llm_service", None
            ) if hasattr(active_agent, "execution_engine") else None,
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
            f"Manual memory extraction completed: "
            f"{result['extracted_memories']} memories from "
            f"{result['total_conversations']} conversations"
        )

        return ExtractMemoryResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Memory extraction failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Memory extraction failed: {str(e)}",
        )


@router.get("/scheduler/status", response_model=SchedulerStatusResponse)
async def get_scheduler_status(
    ws_manager: WebSocketManager = websocket_manager_dep,
):
    """获取记忆提取调度器状态

    Returns:
        调度器状态信息
    """
    try:
        # 获取活跃的Agent实例
        active_agent = ws_manager.get_active_agent()
        if not active_agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No active agent found",
            )

        # 检查是否有调度器实例
        if not hasattr(active_agent, "memory_scheduler") or active_agent.memory_scheduler is None:
            return SchedulerStatusResponse(
                running=False,
                scheduled_time="00:00",
                next_run=None,
                workspace_path=str(active_agent.user_workspace.absolute_path),
            )

        # 获取状态
        status_info = active_agent.memory_scheduler.get_status()

        return SchedulerStatusResponse(**status_info)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get scheduler status: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get scheduler status: {str(e)}",
        )


@router.post("/scheduler/start")
async def start_scheduler(
    ws_manager: WebSocketManager = websocket_manager_dep,
):
    """启动记忆提取调度器

    Returns:
        启动结果
    """
    try:
        # 获取活跃的Agent实例
        active_agent = ws_manager.get_active_agent()
        if not active_agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No active agent found",
            )

        # 检查memory系统是否启用
        if not is_memory_enabled(active_agent.user_workspace):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Memory system is not enabled",
            )

        # 检查调度器是否存在
        if not hasattr(active_agent, "memory_scheduler") or active_agent.memory_scheduler is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Memory scheduler is not initialized",
            )

        # 启动调度器
        await active_agent.memory_scheduler.start()

        logger.info("Memory extraction scheduler started")

        return {
            "success": True,
            "message": "Scheduler started successfully",
            "status": active_agent.memory_scheduler.get_status(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start scheduler: {str(e)}",
        )


@router.post("/scheduler/stop")
async def stop_scheduler(
    ws_manager: WebSocketManager = websocket_manager_dep,
):
    """停止记忆提取调度器

    Returns:
        停止结果
    """
    try:
        # 获取活跃的Agent实例
        active_agent = ws_manager.get_active_agent()
        if not active_agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No active agent found",
            )

        # 检查调度器是否存在
        if not hasattr(active_agent, "memory_scheduler") or active_agent.memory_scheduler is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Memory scheduler is not initialized",
            )

        # 停止调度器
        await active_agent.memory_scheduler.stop()

        logger.info("Memory extraction scheduler stopped")

        return {
            "success": True,
            "message": "Scheduler stopped successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to stop scheduler: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to stop scheduler: {str(e)}",
        )
