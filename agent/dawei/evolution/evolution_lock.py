# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Evolution Lock - Process Lock for Evolution Cycles

基于WorkspacePersistenceManager的ResourceLock实现的evolution进程锁，
防止同一workspace同时运行多个evolution cycle。

设计原则：
- 不使用fcntl（不支持Windows）
- 复用现有的ResourceLock机制（基于asyncio.Lock）
- 每个workspace独立的锁（不同workspace可并发）
"""

import asyncio
import logging

from dawei.evolution.exceptions import EvolutionAlreadyRunningError, EvolutionError
from dawei.workspace.persistence_manager import WorkspacePersistenceManager

logger = logging.getLogger(__name__)


class EvolutionLock:
    """Evolution进程锁

    基于WorkspacePersistenceManager.ResourceLock实现的evolution进程锁。
    确保每个workspace同时只能有一个evolution cycle在运行。

    使用方式：
        ```python
        lock = EvolutionLock(workspace)

        # 方式1: 手动acquire/release
        if await lock.acquire():
            try:
                # 执行evolution
                ...
            finally:
                await lock.release()

        # 方式2: 使用async上下文管理器（推荐）
        async with lock:
            # 执行evolution
            ...
        ```

    Attributes:
        workspace: UserWorkspace实例
        _pm: WorkspacePersistenceManager实例
        _resource_key: 资源键（格式：evolution:{workspace_id}）
        _lock_holder: 是否持有锁
    """

    def __init__(self, workspace):
        """初始化EvolutionLock

        Args:
            workspace: UserWorkspace实例
        """
        from dawei.workspace.user_workspace import UserWorkspace

        if not isinstance(workspace, UserWorkspace):
            raise EvolutionError(f"workspace must be UserWorkspace, got {type(workspace)}")

        self._pm = WorkspacePersistenceManager(workspace.workspace_path)
        self._resource_key = f"evolution:{workspace.workspace_id}"
        self._lock_holder = False
        self._async_lock: asyncio.Lock | None = None

        logger.debug(f"[EVOLUTION_LOCK] Initialized for workspace {workspace.workspace_id}")

    async def acquire(self) -> bool:
        """非阻塞尝试获取锁

        如果锁已被其他进程持有，立即返回False而不等待。

        Returns:
            bool: True表示成功获取锁，False表示锁已被持有

        """
        # ResourceLock.acquire() returns an asyncio.Lock, not a bool
        self._async_lock = await self._pm._resource_lock.acquire(self._resource_key)

        # asyncio.Lock 没有 acquire_nowait()，用 locked() 检查 + acquire() 获取
        if self._async_lock.locked():
            acquired = False
        else:
            await self._async_lock.acquire()
            acquired = True

        if acquired:
            self._lock_holder = True
            logger.info(f"[EVOLUTION_LOCK] Acquired lock for {self._resource_key}")
        else:
            logger.debug(f"[EVOLUTION_LOCK] Lock already held for {self._resource_key}")

        return acquired

    async def release(self):
        """释放锁

        只有锁的持有者才能释放锁。
        如果未持有锁，此方法不执行任何操作。

        """
        if self._lock_holder and self._async_lock is not None:
            self._async_lock.release()
            self._lock_holder = False
            self._async_lock = None
            logger.info(f"[EVOLUTION_LOCK] Released lock for {self._resource_key}")
        else:
            logger.debug(f"[EVOLUTION_LOCK] Not holding lock for {self._resource_key}, skipping release")

    async def is_locked(self) -> bool:
        """检查锁是否被持有

        Returns:
            bool: True表示锁被持有，False表示锁未被持有

        """
        if self._lock_holder:
            return True

        if self._async_lock is not None:
            return self._async_lock.locked()

        return False

    async def __aenter__(self):
        """async上下文管理器入口

        自动获取锁，如果锁已被持有则抛出EvolutionAlreadyRunningError异常。

        Raises:
            EvolutionAlreadyRunningError: 当锁已被其他进程持有时

        """
        acquired = await self.acquire()
        if not acquired:
            raise EvolutionAlreadyRunningError(f"Evolution already running for workspace {self._resource_key}. Only one evolution cycle can run at a time per workspace.")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """async上下文管理器出口

        自动释放锁。

        """
        await self.release()
        return False
