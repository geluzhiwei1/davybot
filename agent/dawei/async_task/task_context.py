# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""任务上下文实现

提供任务执行过程中的状态管理、数据存储和检查点功能。
"""

import asyncio
import json
import threading
import time
from datetime import UTC, datetime, timezone
from pathlib import Path
from typing import Any

from dawei.logg.logging import get_logger

from .interfaces import ICheckpointService, ITaskContext
from .types import (
    CheckpointData,
    ProgressCallback,
    StateChangeCallback,
    TaskProgress,
    TaskStatus,
)


class TaskContext(ITaskContext):
    """任务上下文实现"""

    def __init__(
        self,
        task_id: str,
        checkpoint_service: ICheckpointService | None = None,
        auto_checkpoint_interval: int = 30,
    ):
        """初始化任务上下文

        Args:
            task_id: 任务ID
            checkpoint_service: 检查点服务
            auto_checkpoint_interval: 自动检查点间隔（秒）

        """
        self._task_id = task_id
        self._status = TaskStatus.PENDING
        self._metadata: dict[str, Any] = {}
        self._data: dict[str, Any] = {}
        self._checkpoint_service = checkpoint_service

        # 执行控制
        self._should_cancel = False
        self._should_pause = False
        self._paused_event = asyncio.Event()
        self._paused_event.set()  # 初始状态为未暂停

        # 时间跟踪
        self._created_at = datetime.now(UTC)
        self._started_at: datetime | None = None
        self._completed_at: datetime | None = None
        self._last_checkpoint_time: datetime | None = None

        # 回调函数
        self._progress_callbacks: list[ProgressCallback] = []
        self._state_change_callbacks: list[StateChangeCallback] = []

        # 自动检查点
        self._auto_checkpoint_interval = auto_checkpoint_interval
        self._last_auto_checkpoint = time.time()

        # 线程安全锁
        self._lock = threading.RLock()

        # 日志记录器
        self._logger = get_logger(__name__)

        self._logger.info(f"TaskContext initialized for task: {task_id}")

    def get_task_id(self) -> str:
        """获取任务ID"""
        return self._task_id

    def get_status(self) -> TaskStatus:
        """获取任务状态"""
        with self._lock:
            return self._status

    def set_status(self, status: TaskStatus) -> None:
        """设置任务状态

        Args:
            status: 新状态

        """
        with self._lock:
            old_status = self._status
            if old_status == status:
                return  # 状态未变化

            self._status = status

            # 更新时间戳
            if status == TaskStatus.RUNNING and self._started_at is None:
                self._started_at = datetime.now(UTC)
            elif status in [
                TaskStatus.COMPLETED,
                TaskStatus.FAILED,
                TaskStatus.CANCELLED,
                TaskStatus.TIMEOUT,
            ]:
                self._completed_at = datetime.now(UTC)

            self._logger.info(
                f"Task {self._task_id} status changed: {old_status.value} -> {status.value}",
            )

            # 异步调用状态变化回调
            for idx, callback in enumerate(self._state_change_callbacks):
                try:
                    if asyncio.iscoroutinefunction(callback):
                        asyncio.create_task(callback(self._task_id, old_status, status))
                    else:
                        callback(self._task_id, old_status, status)
                except Exception as e:
                    self._logger.error(
                        f"State change callback #{idx} failed for task {self._task_id}: {e}",
                        exc_info=True,
                    )

    def get_metadata(self, key: str | None = None) -> Any:
        """获取元数据

        Args:
            key: 元数据键，为None时返回所有元数据

        Returns:
            元数据值

        """
        with self._lock:
            if key is None:
                return self._metadata.copy()
            return self._metadata.get(key)

    def set_metadata(self, key: str, value: Any) -> None:
        """设置元数据

        Args:
            key: 元数据键
            value: 元数据值

        """
        with self._lock:
            self._metadata[key] = value
            self._logger.debug(f"Task {self._task_id} metadata set: {key} = {value}")

    def get_data(self, key: str | None = None) -> Any:
        """获取任务数据

        Args:
            key: 数据键，为None时返回所有数据

        Returns:
            数据值

        """
        with self._lock:
            if key is None:
                return self._data.copy()
            return self._data.get(key)

    def set_data(self, key: str, value: Any) -> None:
        """设置任务数据

        Args:
            key: 数据键
            value: 数据值

        """
        with self._lock:
            self._data[key] = value
            self._logger.debug(f"Task {self._task_id} data set: {key} = {value}")

    async def create_checkpoint(self, force: bool = False) -> str:
        """创建检查点

        Args:
            force: 是否强制创建

        Returns:
            检查点ID

        """
        if not self._checkpoint_service:
            self._logger.warning("No checkpoint service available")
            return ""

        # 检查是否需要创建检查点
        current_time = time.time()
        if not force and self._auto_checkpoint_interval > 0 and (current_time - self._last_auto_checkpoint < self._auto_checkpoint_interval):
            self._logger.debug("Auto checkpoint interval not reached")
            return ""

        try:
            # 准备检查点数据
            state_data = {
                "status": self._status.value,
                "metadata": self._metadata,
                "data": self._data,
                "created_at": self._created_at.isoformat(),
                "started_at": self._started_at.isoformat() if self._started_at else None,
                "execution_time": self.get_execution_time(),
            }

            # 创建检查点
            checkpoint_id = await self._checkpoint_service.create(self._task_id, state_data, force)

            if not checkpoint_id:
                raise RuntimeError(
                    f"Checkpoint service returned empty checkpoint_id for task {self._task_id}",
                )

            self._last_checkpoint_time = datetime.now(UTC)
            self._last_auto_checkpoint = current_time
            self._logger.info(f"Checkpoint created for task {self._task_id}: {checkpoint_id}")

            return checkpoint_id

        except (OSError, json.JSONDecodeError, TypeError, ValueError) as e:
            self._logger.error(
                f"Failed to create checkpoint for task {self._task_id}: {type(e).__name__}: {e}",
                exc_info=True,
            )
            raise  # Fast fail: re-raise to surface the issue immediately

    async def restore_checkpoint(self, checkpoint_id: str) -> bool:
        """恢复检查点

        Args:
            checkpoint_id: 检查点ID

        Returns:
            是否成功恢复

        """
        if not self._checkpoint_service:
            self._logger.warning("No checkpoint service available")
            return False

        try:
            if not checkpoint_id:
                raise ValueError("checkpoint_id cannot be empty")

            # 获取检查点数据
            state_data = await self._checkpoint_service.restore(checkpoint_id)

            if not state_data:
                raise ValueError(f"Checkpoint data is empty for checkpoint_id: {checkpoint_id}")

            # 恢复状态
            with self._lock:
                self._status = TaskStatus(state_data.get("status", TaskStatus.PENDING.value))
                self._metadata = state_data.get("metadata", {})
                self._data = state_data.get("data", {})

                # 恢复时间信息
                created_at_str = state_data.get("created_at")
                if created_at_str:
                    try:
                        self._created_at = datetime.fromisoformat(created_at_str)
                    except ValueError:
                        raise ValueError(f"Invalid created_at format: {created_at_str}")

                started_at_str = state_data.get("started_at")
                if started_at_str:
                    try:
                        self._started_at = datetime.fromisoformat(started_at_str)
                    except ValueError:
                        raise ValueError(f"Invalid started_at format: {started_at_str}")

            self._logger.info(f"Checkpoint restored for task {self._task_id}: {checkpoint_id}")
            return True

        except (OSError, json.JSONDecodeError, KeyError, ValueError, TypeError) as e:
            self._logger.error(
                f"Failed to restore checkpoint {checkpoint_id} for task {self._task_id}: {type(e).__name__}: {e}",
                exc_info=True,
            )
            raise  # Fast fail: re-raise to surface the issue immediately

    async def report_progress(
        self,
        progress: int,
        message: str = "",
        data: dict[str, Any] | None = None,
    ) -> None:
        """报告任务进度

        Args:
            progress: 进度百分比（0-100）
            message: 进度消息
            data: 附加数据

        """
        # 确保进度在有效范围内
        progress = max(0, min(100, progress))

        # 创建进度对象
        task_progress = TaskProgress(
            task_id=self._task_id,
            progress=progress,
            message=message,
            data=data,
        )

        # 调用进度回调
        for idx, callback in enumerate(self._progress_callbacks):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(task_progress)
                else:
                    callback(task_progress)
            except Exception as e:
                self._logger.error(
                    f"Progress callback #{idx} failed for task {self._task_id}: {type(e).__name__}: {e}",
                    exc_info=True,
                )
                # Continue with other callbacks even if one fails
                # This is intentional for progress reporting

        # 自动创建检查点
        if progress % 25 == 0:  # 每25%进度创建一次检查点
            await self.create_checkpoint()

        self._logger.debug(f"Task {self._task_id} progress: {progress}% - {message}")

    def should_cancel(self) -> bool:
        """检查是否应该取消任务"""
        with self._lock:
            return self._should_cancel

    def should_pause(self) -> bool:
        """检查是否应该暂停任务"""
        with self._lock:
            return self._should_pause

    async def wait_if_paused(self) -> None:
        """如果任务被暂停，等待恢复"""
        while self.should_pause():
            self._logger.debug(f"Task {self._task_id} is paused, waiting...")
            await self._paused_event.wait()
            self._paused_event.clear()

    def get_execution_time(self) -> float:
        """获取已执行时间（秒）"""
        with self._lock:
            if self._started_at is None:
                return 0.0

            end_time = self._completed_at or datetime.now(UTC)
            return (end_time - self._started_at).total_seconds()

    def add_progress_callback(self, callback: ProgressCallback) -> None:
        """添加进度回调

        Args:
            callback: 进度回调函数

        """
        with self._lock:
            self._progress_callbacks.append(callback)

    def remove_progress_callback(self, callback: ProgressCallback) -> None:
        """移除进度回调

        Args:
            callback: 进度回调函数

        """
        with self._lock:
            if callback in self._progress_callbacks:
                self._progress_callbacks.remove(callback)

    def add_state_change_callback(self, callback: StateChangeCallback) -> None:
        """添加状态变化回调

        Args:
            callback: 状态变化回调函数

        """
        with self._lock:
            self._state_change_callbacks.append(callback)

    def remove_state_change_callback(self, callback: StateChangeCallback) -> None:
        """移除状态变化回调

        Args:
            callback: 状态变化回调函数

        """
        with self._lock:
            if callback in self._state_change_callbacks:
                self._state_change_callbacks.remove(callback)

    def has_active_callbacks(self) -> bool:
        """检查是否有活跃的回调函数

        Returns:
            是否有活跃的回调函数

        """
        with self._lock:
            # 检查是否有进度回调或状态变化回调
            return len(self._progress_callbacks) > 0 or len(self._state_change_callbacks) > 0

    def cancel(self) -> None:
        """取消任务"""
        with self._lock:
            self._should_cancel = True
            self.set_status(TaskStatus.CANCELLED)
            self._logger.info(f"Task {self._task_id} cancelled")

    def pause(self) -> None:
        """暂停任务"""
        with self._lock:
            self._should_pause = True
            self._paused_event.clear()
            self.set_status(TaskStatus.PAUSED)
            self._logger.info(f"Task {self._task_id} paused")

    def resume(self) -> None:
        """恢复任务"""
        with self._lock:
            self._should_pause = False
            self._paused_event.set()
            if self._status == TaskStatus.PAUSED:
                self.set_status(TaskStatus.RUNNING)
            self._logger.info(f"Task {self._task_id} resumed")

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        with self._lock:
            return {
                "task_id": self._task_id,
                "status": self._status.value,
                "metadata": self._metadata,
                "data": self._data,
                "should_cancel": self._should_cancel,
                "should_pause": self._should_pause,
                "created_at": self._created_at.isoformat(),
                "started_at": self._started_at.isoformat() if self._started_at else None,
                "completed_at": self._completed_at.isoformat() if self._completed_at else None,
                "last_checkpoint_time": (self._last_checkpoint_time.isoformat() if self._last_checkpoint_time else None),
                "execution_time": self.get_execution_time(),
                "is_paused": self._should_pause,
                "is_cancelled": self._should_cancel,
            }

    def __str__(self) -> str:
        """字符串表示"""
        return f"TaskContext(id={self._task_id}, status={self._status.value})"

    def __repr__(self) -> str:
        """详细字符串表示"""
        return f"TaskContext(id={self._task_id}, status={self._status.value}, execution_time={self.get_execution_time():.2f}s)"


class SimpleCheckpointService(ICheckpointService):
    """简单的检查点服务实现（基于文件系统）"""

    def __init__(self, storage_path: str = "checkpoints"):
        """初始化检查点服务

        Args:
            storage_path: 存储路径

        """
        self.storage_path = Path(storage_path)
        self._logger = get_logger(__name__)

        # 确保存储目录存在
        self.storage_path.mkdir(parents=True, exist_ok=True)

    async def create(self, task_id: str, state_data: dict[str, Any], _force: bool = False) -> str:
        """创建检查点

        Args:
            task_id: 任务ID
            state_data: 状态数据
            force: 是否强制创建

        Returns:
            检查点ID

        Raises:
            ValueError: If task_id is empty or state_data is invalid
            OSError: If file operations fail
            TypeError: If state_data contains non-serializable objects

        """
        if not task_id:
            raise ValueError("task_id cannot be empty")

        if not state_data:
            raise ValueError("state_data cannot be empty")

        try:
            import uuid

            checkpoint_id = str(uuid.uuid4())

            # 创建检查点数据
            checkpoint_data = CheckpointData(
                checkpoint_id=checkpoint_id,
                task_id=task_id,
                state_data=state_data,
                metadata={"created_by": "SimpleCheckpointService"},
            )

            # 保存到文件
            file_path = self.storage_path / f"{checkpoint_id}.json"

            # Ensure directory exists
            self.storage_path.mkdir(parents=True, exist_ok=True)

            with file_path.open("w", encoding="utf-8") as f:
                json.dump(checkpoint_data.to_dict(), f, ensure_ascii=False, indent=2)

            self._logger.info(f"Checkpoint created: {checkpoint_id} for task: {task_id}")
            return checkpoint_id

        except OSError as e:
            self._logger.error(
                f"File I/O error creating checkpoint for task {task_id}: {type(e).__name__}: {e}",
                exc_info=True,
            )
            raise  # Fast fail: re-raise I/O errors

        except (TypeError, ValueError) as e:
            self._logger.error(
                f"Data serialization error creating checkpoint for task {task_id}: {type(e).__name__}: {e}",
                exc_info=True,
            )
            raise  # Fast fail: re-raise serialization errors

    async def restore(self, checkpoint_id: str) -> dict[str, Any] | None:
        """恢复检查点

        Args:
            checkpoint_id: 检查点ID

        Returns:
            状态数据

        Raises:
            ValueError: If checkpoint_id is empty or file not found
            OSError: If file operations fail
            json.JSONDecodeError: If JSON parsing fails

        """
        if not checkpoint_id:
            raise ValueError("checkpoint_id cannot be empty")

        try:
            file_path = self.storage_path / f"{checkpoint_id}.json"

            if not file_path.exists():
                raise FileNotFoundError(f"Checkpoint file not found: {file_path}")

            with Path(file_path).open(encoding="utf-8") as f:
                checkpoint_dict = json.load(f)

            checkpoint_data = CheckpointData(**checkpoint_dict)
            self._logger.info(f"Checkpoint restored: {checkpoint_id}")
            return checkpoint_data.state_data

        except FileNotFoundError as e:
            self._logger.error(f"Checkpoint file not found: {checkpoint_id}: {e}", exc_info=True)
            raise  # Fast fail: re-raise to surface the issue

        except OSError as e:
            self._logger.error(
                f"File I/O error restoring checkpoint {checkpoint_id}: {type(e).__name__}: {e}",
                exc_info=True,
            )
            raise  # Fast fail: re-raise I/O errors

        except json.JSONDecodeError as e:
            self._logger.error(
                f"JSON decode error restoring checkpoint {checkpoint_id}: {e}",
                exc_info=True,
            )
            raise  # Fast fail: re-raise JSON errors

        except (TypeError, ValueError) as e:
            self._logger.error(
                f"Data validation error restoring checkpoint {checkpoint_id}: {type(e).__name__}: {e}",
                exc_info=True,
            )
            raise  # Fast fail: re-raise validation errors

    async def list(self, task_id: str) -> list[CheckpointData]:
        """列出检查点

        Args:
            task_id: 任务ID

        Returns:
            检查点列表

        Raises:
            ValueError: If task_id is empty
            OSError: If directory scanning fails
            json.JSONDecodeError: If checkpoint file parsing fails

        """
        if not task_id:
            raise ValueError("task_id cannot be empty")

        if not self.storage_path.exists():
            self._logger.warning(f"Checkpoint storage path does not exist: {self.storage_path}")
            return []

        checkpoints = []

        try:
            for filename in self.storage_path.iterdir():
                if filename.suffix != ".json":
                    continue

                file_path = filename

                try:
                    with Path(file_path).open(encoding="utf-8") as f:
                        checkpoint_dict = json.load(f)

                    checkpoint_data = CheckpointData(**checkpoint_dict)

                    if checkpoint_data.task_id == task_id:
                        checkpoints.append(checkpoint_data)

                except (OSError, json.JSONDecodeError, TypeError, ValueError) as e:
                    # Log individual file errors but continue processing other files
                    self._logger.warning(
                        f"Failed to read checkpoint file {filename}: {type(e).__name__}: {e}",
                    )
                    continue

            # 按创建时间排序
            checkpoints.sort(key=lambda x: x.created_at, reverse=True)

        except OSError as e:
            self._logger.error(
                f"Failed to list checkpoints directory for task {task_id}: {type(e).__name__}: {e}",
                exc_info=True,
            )
            raise  # Fast fail: re-raise directory access errors

        return checkpoints

    async def delete(self, checkpoint_id: str) -> bool:
        """删除检查点

        Args:
            checkpoint_id: 检查点ID

        Returns:
            是否成功删除

        Raises:
            ValueError: If checkpoint_id is empty
            OSError: If file deletion fails

        """
        if not checkpoint_id:
            raise ValueError("checkpoint_id cannot be empty")

        try:
            file_path = self.storage_path / f"{checkpoint_id}.json"

            if not file_path.exists():
                self._logger.warning(f"Checkpoint file not found: {file_path}")
                return False

            file_path.unlink()
            self._logger.info(f"Checkpoint deleted: {checkpoint_id}")
            return True

        except OSError as e:
            self._logger.error(
                f"Failed to delete checkpoint {checkpoint_id}: {type(e).__name__}: {e}",
                exc_info=True,
            )
            raise  # Fast fail: re-raise file deletion errors

    async def cleanup_old_checkpoints(self, task_id: str, keep_count: int = 5) -> int:
        """清理旧检查点

        Args:
            task_id: 任务ID
            keep_count: 保留数量

        Returns:
            删除的检查点数量

        Raises:
            ValueError: If task_id is empty or keep_count is invalid
            OSError: If checkpoint operations fail

        """
        if not task_id:
            raise ValueError("task_id cannot be empty")

        if keep_count < 0:
            raise ValueError(f"keep_count must be non-negative, got {keep_count}")

        deleted_count = 0

        try:
            checkpoints = await self.list(task_id)

            if len(checkpoints) <= keep_count:
                return 0

            # 删除最旧的检查点
            for checkpoint in checkpoints[keep_count:]:
                try:
                    await self.delete(checkpoint.checkpoint_id)
                    deleted_count += 1
                except OSError as e:
                    # Log individual delete errors but continue with others
                    self._logger.warning(
                        f"Failed to delete checkpoint {checkpoint.checkpoint_id}: {type(e).__name__}: {e}",
                    )
                    continue

            self._logger.info(f"Cleaned up {deleted_count} old checkpoints for task {task_id}")

        except (OSError, ValueError) as e:
            self._logger.error(
                f"Failed to cleanup old checkpoints for task {task_id}: {type(e).__name__}: {e}",
                exc_info=True,
            )
            raise  # Fast fail: re-raise critical errors

        return deleted_count
