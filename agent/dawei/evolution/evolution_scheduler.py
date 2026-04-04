# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Evolution Scheduler

复用SchedulerManager，注册全局evolution检查任务。
定期检查所有workspace，如果evolution已启用且到达触发时间，则启动新cycle。
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path

from croniter import croniter

from dawei.core.datetime_compat import UTC
from dawei.evolution.evolution_lock import EvolutionLock
from dawei.evolution.evolution_manager import EvolutionCycleManager
from dawei.evolution.evolution_storage import EvolutionStorage
from dawei.workspace.workspace_manager import workspace_manager

logger = logging.getLogger(__name__)

# 合理默认调度：每天凌晨3点
DEFAULT_CRON_SCHEDULE = "0 3 * * *"


class EvolutionScheduler:
    """Evolution调度器

    定期检查所有workspace的evolution配置，如果满足触发条件则启动新cycle。

    设计原则：
    - 复用现有的SchedulerManager（不创建独立的调度器）
    - 全局单例，每60秒检查一次所有workspace
    - 每个workspace独立判断是否触发
    - 使用EvolutionLock防止并发启动
    - 缓存已初始化的UserWorkspace实例避免重复初始化

    Attributes:
        CHECK_INTERVAL: 检查间隔（秒）
        _task: 后台检查任务
        _running: 是否正在运行
        _workspace_cache: workspace_id → UserWorkspace 缓存

    """

    CHECK_INTERVAL = 60  # seconds

    def __init__(self):
        """初始化EvolutionScheduler"""
        self._task: asyncio.Task | None = None
        self._running = False
        self._workspace_cache: dict[str, object] = {}

        logger.debug("[EVOLUTION_SCHEDULER] EvolutionScheduler initialized")

    async def start(self):
        """启动调度器

        在server lifespan启动时调用。

        """
        if self._running:
            logger.warning("[EVOLUTION_SCHEDULER] Scheduler already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._loop(), name="evolution-scheduler")

        logger.info("[EVOLUTION_SCHEDULER] Started")

    async def stop(self):
        """停止调度器

        在server lifespan关闭时调用。

        """
        if not self._running:
            return

        self._running = False
        self._workspace_cache.clear()

        if self._task:
            self._task.cancel()
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except (TimeoutError, asyncio.CancelledError):
                pass

        logger.info("[EVOLUTION_SCHEDULER] Stopped")

    async def _get_or_init_workspace(self, workspace_path: str):
        """获取或初始化UserWorkspace（带缓存）

        避免每60秒重新创建和初始化UserWorkspace。

        Args:
            workspace_path: workspace路径

        Returns:
            UserWorkspace实例，如果初始化失败返回None

        """
        if workspace_path in self._workspace_cache:
            return self._workspace_cache[workspace_path]

        from dawei.workspace.user_workspace import UserWorkspace

        workspace = UserWorkspace(workspace_path)
        if not workspace.is_initialized():
            try:
                await workspace.initialize()
            except Exception as e:
                logger.warning(f"[EVOLUTION_SCHEDULER] Failed to initialize workspace {workspace_path}: {e}")
                return None

        self._workspace_cache[workspace_path] = workspace
        return workspace

    async def _loop(self):
        """主检查循环

        每CHECK_INTERVAL秒检查一次所有workspace。
        """
        try:
            while self._running:
                try:
                    await self._check_all_workspaces()
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"[EVOLUTION_SCHEDULER] Check loop error: {e}", exc_info=True)

                # 等待下次检查
                try:
                    await asyncio.sleep(self.CHECK_INTERVAL)
                except asyncio.CancelledError:
                    break

        except asyncio.CancelledError:
            logger.info("[EVOLUTION_SCHEDULER] Check loop cancelled")
            raise

        finally:
            logger.debug("[EVOLUTION_SCHEDULER] Check loop exited")

    async def _check_all_workspaces(self):
        """检查所有workspace的evolution触发条件

        对于每个workspace：
        1. 检查是否启用了evolution
        2. 检查是否已有cycle在运行
        3. 检查是否到达触发时间（基于cron表达式）
        4. 如果满足条件，启动新cycle

        """
        logger.debug("[EVOLUTION_SCHEDULER] Checking all workspaces for evolution triggers")

        # 获取所有workspace
        all_workspaces = workspace_manager.get_all_workspaces()

        triggered_count = 0

        for workspace_info in all_workspaces:
            workspace_path = workspace_info.get("path")
            if not workspace_path:
                continue

            workspace = await self._get_or_init_workspace(workspace_path)
            if workspace is None:
                continue

            # 检查evolution配置
            workspace_config = workspace.workspace_config
            if workspace_config:
                evolution_config = workspace_config.model_dump().get("evolution", {})
            else:
                evolution_config = {}

            if not evolution_config.get("enabled", False):
                # Evolution未启用
                continue

            # 检查是否应该触发
            try:
                should_trigger = await self._should_trigger_evolution(workspace, evolution_config)

                if should_trigger:
                    logger.info(f"[EVOLUTION_SCHEDULER] Triggering evolution for workspace {workspace.workspace_id}")

                    # 启动新cycle
                    manager = EvolutionCycleManager(workspace)
                    cycle_id = await manager.start_cycle()

                    logger.info(f"[EVOLUTION_SCHEDULER] Started evolution cycle {cycle_id} for workspace {workspace.workspace_id}")

                    triggered_count += 1

            except Exception as e:
                logger.error(
                    f"[EVOLUTION_SCHEDULER] Error triggering evolution for workspace {workspace.workspace_id}: {e}",
                    exc_info=True,
                )
                continue

        if triggered_count > 0:
            logger.info(f"[EVOLUTION_SCHEDULER] Triggered {triggered_count} evolution cycle(s)")

    async def _should_trigger_evolution(self, workspace, evolution_config: dict) -> bool:
        """判断是否应该触发evolution

        条件：
        1. 没有正在运行的cycle（通过EvolutionLock检查）
        2. 上一个cycle已完成（或不存在）
        3. 满足cron调度时间

        Args:
            workspace: UserWorkspace实例
            evolution_config: Evolution配置字典

        Returns:
            bool: 是否应该触发

        """
        # 1. 检查是否有cycle正在运行
        lock = EvolutionLock(workspace)
        if await lock.is_locked():
            logger.debug(f"[EVOLUTION_SCHEDULER] Evolution already running for workspace {workspace.workspace_id}")
            return False

        # 2. 检查上一个cycle的状态
        storage = EvolutionStorage(workspace)
        last_cycle = await storage.get_latest_cycle()

        if last_cycle and last_cycle.get("status") not in ("completed", "aborted", "failed"):
            # 上一个cycle还未结束
            logger.debug(f"[EVOLUTION_SCHEDULER] Last cycle status is {last_cycle.get('status')} for workspace {workspace.workspace_id}, skipping trigger")
            return False

        # 3. 检查cron调度时间
        schedule = evolution_config.get("schedule", DEFAULT_CRON_SCHEDULE)
        last_cycle_time = None

        if last_cycle:
            # 使用上一个cycle的started_at作为基准时间
            last_cycle_time_str = last_cycle.get("started_at")
            if last_cycle_time_str:
                try:
                    last_cycle_time = datetime.fromisoformat(last_cycle_time_str)
                except (ValueError, TypeError):
                    pass

        return _is_cron_due(schedule, last_cycle_time)


def _is_cron_due(cron_expression: str, last_run: datetime | None) -> bool:
    """判断是否到达cron触发时间

    当 last_run 为 None（首次运行）时，使用 get_prev() 检查当前时间
    是否已过了最近一个cron触发点。

    当 last_run 有值时，从 last_run 开始计算下次运行时间，
    如果当前时间已过则触发。

    Args:
        cron_expression: Cron表达式（如 "0 3 * * *" 表示每天凌晨3点）
        last_run: 上次运行时间

    Returns:
        bool: 是否应该触发

    """
    now = datetime.now(UTC)

    try:
        if last_run is None:
            # 首次运行：检查当前是否已过了最近一个cron触发点
            cron = croniter(cron_expression, now)
            prev_run = cron.get_prev(datetime)
            # 如果最近一个触发点在当前时间之前（或同时），说明到了触发时间
            return now >= prev_run
        # 非首次：从上次运行时间计算下次触发时间
        cron = croniter(cron_expression, last_run)
        next_run = cron.get_next(datetime)
        return now >= next_run

    except Exception as e:
        logger.error(f"[EVOLUTION_SCHEDULER] Error checking cron due: {e}", exc_info=True)
        return False


# 全局单例
evolution_scheduler = EvolutionScheduler()
