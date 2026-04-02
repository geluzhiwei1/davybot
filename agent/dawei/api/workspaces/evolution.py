# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Evolution API Endpoints

提供Evolution功能的REST API接口。
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from dawei.api.workspaces.core import get_user_workspace
from dawei.evolution.evolution_lock import EvolutionLock
from dawei.evolution.evolution_manager import EvolutionCycleManager
from dawei.evolution.evolution_storage import EvolutionStorage
from dawei.evolution.exceptions import (
    EvolutionAlreadyRunningError,
    EvolutionError,
    EvolutionStateError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/{workspace_id}/evolution", tags=["evolution"])

EVOLUTION_CONFIG_FILE = "evolution.json"


def _load_evolution_config(workspace_path: Path) -> Dict[str, Any]:
    """从 .dawei/evolution.json 加载 evolution 配置"""
    config_file = workspace_path / ".dawei" / EVOLUTION_CONFIG_FILE
    if config_file.exists():
        try:
            with config_file.open(encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to load evolution config: {e}")
    return {}


def _save_evolution_config(workspace_path: Path, config: Dict[str, Any]) -> None:
    """保存 evolution 配置到 .dawei/evolution.json"""
    config_file = workspace_path / ".dawei" / EVOLUTION_CONFIG_FILE
    config_file.parent.mkdir(parents=True, exist_ok=True)
    with config_file.open("w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


# ==================== Request/Response Models ====================


class EvolutionConfigRequest(BaseModel):
    """Evolution配置请求"""

    enabled: bool
    schedule: str = "* * * * *"  # 默认每分钟
    goals: list[str] = []  # 可选的目标列表


class EvolutionStatusResponse(BaseModel):
    """Evolution状态响应"""

    enabled: bool
    is_running: bool
    is_paused: bool
    current_cycle: Dict[str, Any] | None
    all_cycles: list[Dict[str, Any]]
    config: Dict[str, Any] | None


class CycleResponse(BaseModel):
    """Cycle操作响应"""

    cycle_id: str
    status: str
    message: str | None = None


class TriggerEvolutionRequest(BaseModel):
    """手动触发evolution cycle请求"""

    dao_path: str | None = None  # 自定义dao文件路径，覆盖默认的workspace/dao.md


class CycleDetailResponse(BaseModel):
    """Cycle详情响应"""

    metadata: Dict[str, Any]
    phases: Dict[str, str]
    workspace_md: str | None


# ==================== API Endpoints ====================


@router.post("/enable")
async def enable_evolution(workspace_id: str, config: EvolutionConfigRequest):
    """启用evolution功能

    Args:
        workspace_id: Workspace ID
        config: Evolution配置

    Returns:
        {"status": "enabled", "config": {...}}

    Raises:
        HTTPException: 当workspace不存在或配置保存失败时

    """
    workspace = get_user_workspace(workspace_id)

    evolution_config = {
        "enabled": config.enabled,
        "schedule": config.schedule,
        "phase_duration": config.phase_duration,
        "max_cycles": config.max_cycles,
        "goals": config.goals,
    }

    # 保存到 .dawei/evolution.json
    _save_evolution_config(Path(workspace.absolute_path), evolution_config)

    logger.info(f"[EVOLUTION_API] Enabled evolution for workspace {workspace_id}")

    return {
        "status": "enabled",
        "workspace_id": workspace_id,
        "config": evolution_config,
    }


@router.post("/disable", response_model=Dict[str, str])
async def disable_evolution(workspace_id: str):
    """禁用evolution功能

    Args:
        workspace_id: Workspace ID

    Returns:
        {"status": "disabled", "workspace_id": "..."}

    Raises:
        HTTPException: 当workspace不存在或配置保存失败时

    """
    try:
        workspace = get_user_workspace(workspace_id)

        _save_evolution_config(Path(workspace.absolute_path), {"enabled": False})

        logger.info(f"[EVOLUTION_API] Disabled evolution for workspace {workspace_id}")

        return {"status": "disabled", "workspace_id": workspace_id}

    except Exception as e:
        logger.error(f"[EVOLUTION_API] Failed to disable evolution for workspace {workspace_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to disable evolution: {str(e)}",
        )


@router.get("/status", response_model=EvolutionStatusResponse)
async def get_evolution_status(workspace_id: str):
    """获取evolution状态

    Args:
        workspace_id: Workspace ID

    Returns:
        EvolutionStatusResponse

    Raises:
        HTTPException: 当workspace不存在时

    """
    try:
        workspace = get_user_workspace(workspace_id)

        # 从 .dawei/evolution.json 加载配置
        evolution_config = _load_evolution_config(Path(workspace.absolute_path))
        enabled = evolution_config.get("enabled", False)

        # 检查是否正在运行
        lock = EvolutionLock(workspace)
        is_running = await lock.is_locked()

        # 获取当前cycle
        storage = EvolutionStorage(workspace)
        current_cycle = await storage.get_latest_cycle()
        is_paused = current_cycle and current_cycle.get("status") == "paused"

        # 获取所有cycles
        all_cycles = await storage.get_all_cycles()

        return EvolutionStatusResponse(
            enabled=enabled,
            is_running=is_running,
            is_paused=is_paused if is_paused else False,
            current_cycle=current_cycle,
            all_cycles=all_cycles,
            config=evolution_config if enabled else None,
        )

    except Exception as e:
        logger.error(f"[EVOLUTION_API] Failed to get evolution status for workspace {workspace_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get evolution status: {str(e)}",
        )


@router.post("/trigger", response_model=CycleResponse)
async def trigger_evolution(workspace_id: str, body: TriggerEvolutionRequest | None = None):
    """手动触发evolution cycle

    Args:
        workspace_id: Workspace ID
        body: 触发请求参数（可选），包含自定义dao_path

    Returns:
        CycleResponse

    Raises:
        HTTPException: 当workspace不存在或无法启动cycle时

    """
    try:
        workspace = get_user_workspace(workspace_id)

        # 确保工作区已初始化（Agent需要llm_manager、workspace_info等）
        if not workspace.is_initialized():
            await workspace.initialize()

        # 从 .dawei/evolution.json 加载配置
        evolution_config = _load_evolution_config(Path(workspace.absolute_path))
        if not evolution_config.get("enabled", False):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Evolution is not enabled for this workspace. Enable it first.",
            )

        # 提取自定义dao_path（如果提供）
        dao_path = body.dao_path if body else None

        # 启动新cycle
        manager = EvolutionCycleManager(workspace, dao_path=dao_path)
        cycle_id = await manager.start_cycle()

        logger.info(f"[EVOLUTION_API] Triggered evolution cycle {cycle_id} for workspace {workspace_id}")

        return CycleResponse(
            cycle_id=cycle_id,
            status="started",
            message=f"Evolution cycle {cycle_id} started successfully",
        )

    except EvolutionAlreadyRunningError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"[EVOLUTION_API] Failed to trigger evolution for workspace {workspace_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to trigger evolution: {str(e)}",
        )


@router.post("/cycles/{cycle_id}/pause", response_model=CycleResponse)
async def pause_cycle(workspace_id: str, cycle_id: str):
    """暂停evolution cycle（在当前phase结束后生效）

    Args:
        workspace_id: Workspace ID
        cycle_id: Cycle ID

    Returns:
        CycleResponse

    Raises:
        HTTPException: 当workspace不存在或操作失败时

    """
    try:
        workspace = get_user_workspace(workspace_id)

        manager = EvolutionCycleManager(workspace)
        await manager.pause_cycle(cycle_id)

        logger.info(f"[EVOLUTION_API] Paused evolution cycle {cycle_id} for workspace {workspace_id}")

        return CycleResponse(
            cycle_id=cycle_id,
            status="pausing",
            message="Cycle will pause at the next phase boundary",
        )

    except EvolutionStateError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(
            f"[EVOLUTION_API] Failed to pause cycle {cycle_id} for workspace {workspace_id}: {e}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to pause cycle: {str(e)}",
        )


@router.post("/cycles/{cycle_id}/resume", response_model=CycleResponse)
async def resume_cycle(workspace_id: str, cycle_id: str):
    """恢复暂停的evolution cycle

    Args:
        workspace_id: Workspace ID
        cycle_id: Cycle ID

    Returns:
        CycleResponse

    Raises:
        HTTPException: 当workspace不存在或操作失败时

    """
    try:
        workspace = get_user_workspace(workspace_id)

        manager = EvolutionCycleManager(workspace)
        await manager.resume_cycle(cycle_id)

        logger.info(f"[EVOLUTION_API] Resumed evolution cycle {cycle_id} for workspace {workspace_id}")

        return CycleResponse(
            cycle_id=cycle_id,
            status="running",
            message="Cycle resumed successfully",
        )

    except EvolutionStateError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(
            f"[EVOLUTION_API] Failed to resume cycle {cycle_id} for workspace {workspace_id}: {e}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to resume cycle: {str(e)}",
        )


@router.post("/cycles/{cycle_id}/abort", response_model=CycleResponse)
async def abort_cycle(workspace_id: str, cycle_id: str, reason: str = ""):
    """中止evolution cycle（在当前phase结束后或下次phase边界生效）

    Args:
        workspace_id: Workspace ID
        cycle_id: Cycle ID
        reason: 中止原因（可选）

    Returns:
        CycleResponse

    Raises:
        HTTPException: 当workspace不存在或操作失败时

    """
    try:
        workspace = get_user_workspace(workspace_id)

        manager = EvolutionCycleManager(workspace)
        await manager.abort_cycle(cycle_id, reason)

        logger.info(
            f"[EVOLUTION_API] Aborted evolution cycle {cycle_id} for workspace {workspace_id}"
            + (f": {reason}" if reason else "")
        )

        return CycleResponse(
            cycle_id=cycle_id,
            status="aborting",
            message="Cycle will abort at the next phase boundary"
            + (f": {reason}" if reason else ""),
        )

    except EvolutionStateError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(
            f"[EVOLUTION_API] Failed to abort cycle {cycle_id} for workspace {workspace_id}: {e}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to abort cycle: {str(e)}",
        )


@router.get("/cycles/{cycle_id}", response_model=CycleDetailResponse)
async def get_cycle_detail(workspace_id: str, cycle_id: str):
    """获取evolution cycle详情

    Args:
        workspace_id: Workspace ID
        cycle_id: Cycle ID

    Returns:
        CycleDetailResponse

    Raises:
        HTTPException: 当workspace不存在或cycle不存在时

    """
    try:
        workspace = get_user_workspace(workspace_id)

        storage = EvolutionStorage(workspace)

        # 检查cycle是否存在
        if not await storage.cycle_exists(cycle_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cycle {cycle_id} not found",
            )

        # 加载metadata和phases
        metadata = await storage.load_metadata(cycle_id)

        phases = {}
        for phase in EvolutionCycleManager.PHASES:
            try:
                phase_content = await storage.load_phase_output(cycle_id, phase)
                phases[phase] = phase_content or ""
            except Exception:
                phases[phase] = ""

        # 加载dao.md
        workspace_md = await storage.load_workspace_md()

        return CycleDetailResponse(
            metadata=metadata, phases=phases, workspace_md=workspace_md
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"[EVOLUTION_API] Failed to get cycle detail for {cycle_id} in workspace {workspace_id}: {e}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get cycle detail: {str(e)}",
        )


@router.delete("/cycles/{cycle_id}", response_model=Dict[str, str])
async def delete_cycle(workspace_id: str, cycle_id: str):
    """删除evolution cycle（谨慎使用！）

    Args:
        workspace_id: Workspace ID
        cycle_id: Cycle ID

    Returns:
        {"status": "deleted", "cycle_id": "..."}

    Raises:
        HTTPException: 当workspace不存在或删除失败时

    """
    try:
        workspace = get_user_workspace(workspace_id)

        storage = EvolutionStorage(workspace)

        # 检查cycle是否存在
        if not await storage.cycle_exists(cycle_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cycle {cycle_id} not found",
            )

        # 删除cycle
        success = await storage.delete_cycle(cycle_id)

        if success:
            logger.info(
                f"[EVOLUTION_API] Deleted evolution cycle {cycle_id} for workspace {workspace_id}"
            )
            return {"status": "deleted", "cycle_id": cycle_id}
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to delete cycle {cycle_id}",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"[EVOLUTION_API] Failed to delete cycle {cycle_id} for workspace {workspace_id}: {e}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete cycle: {str(e)}",
        )
