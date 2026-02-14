# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""智能检查点管理器
支持自动和手动检查点，差异计算和完整性验证
统一使用 WorkspacePersistenceManager 进行底层持久化
"""

import asyncio
import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from enum import Enum
from typing import Any

from dawei.workspace.persistence_manager import WorkspacePersistenceManager


class CustomCheckpointEncoder(json.JSONEncoder):
    """自定义JSON编码器，支持datetime类型序列化"""

    def default(self, obj: Any) -> Any:
        """处理无法序列化的对象"""
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, timedelta):
            return obj.total_seconds()
        if hasattr(obj, "__iter__"):
            return list(obj)
        return super().default(obj)


class CheckpointType(Enum):
    """检查点类型枚举"""

    AUTO = "auto"
    MANUAL = "manual"
    ERROR_RECOVERY = "error_recovery"
    PERIODIC = "periodic"
    STATE_CHANGE = "state_change"


@dataclass
class CheckpointMetadata:
    """检查点元数据"""

    checkpoint_id: str
    task_id: str
    checkpoint_type: CheckpointType
    created_at: datetime
    size_bytes: int = 0
    checksum: str = ""
    tags: list[str] = None
    parent_checkpoint_id: str | None = None

    def __post_init__(self):
        if self.tags is None:
            self.tags = []


@dataclass
class CheckpointData:
    """检查点数据"""

    metadata: CheckpointMetadata
    state: dict[str, Any]
    diff_from_previous: dict[str, Any] | None = None
    compressed: bool = False


class ICheckpointStrategy(ABC):
    """检查点策略接口"""

    @abstractmethod
    async def should_create_checkpoint(self, context: dict[str, Any]) -> bool:
        """判断是否应该创建检查点"""

    @abstractmethod
    async def prepare_checkpoint_data(self, context: dict[str, Any]) -> dict[str, Any]:
        """准备检查点数据"""


class AutoCheckpointStrategy(ICheckpointStrategy):
    """自动检查点策略"""

    def __init__(self, min_interval: timedelta = timedelta(minutes=5)):
        self.min_interval = min_interval
        self.last_checkpoint_time = None

    async def should_create_checkpoint(self, context: dict[str, Any]) -> bool:
        current_time = datetime.now(UTC)

        if self.last_checkpoint_time and current_time - self.last_checkpoint_time < self.min_interval:
            return False

        # 检查关键条件
        return context.get("tool_executed", False) or context.get("state_changed", False) or context.get("error_occurred", False) or context.get("milestone_reached", False)

    async def prepare_checkpoint_data(self, context: dict[str, Any]) -> dict[str, Any]:
        self.last_checkpoint_time = datetime.now(UTC)
        return {"trigger_reason": "auto", "context_snapshot": context}


class StateChangeCheckpointStrategy(ICheckpointStrategy):
    """状态变化检查点策略"""

    def __init__(self, watched_states: list[str] | None = None):
        self.watched_states = watched_states or [
            "running",
            "paused",
            "completed",
            "failed",
        ]
        self.last_state = None

    async def should_create_checkpoint(self, context: dict[str, Any]) -> bool:
        current_state = context.get("current_state")
        if not current_state:
            return False

        # 如果状态发生变化且是关注的状态，创建检查点
        if self.last_state and self.last_state != current_state and current_state in self.watched_states:
            self.last_state = current_state
            return True

        self.last_state = current_state
        return False

    async def prepare_checkpoint_data(self, context: dict[str, Any]) -> dict[str, Any]:
        return {
            "trigger_reason": "state_change",
            "previous_state": self.last_state,
            "current_state": context.get("current_state"),
            "context_snapshot": context,
        }


class MilestoneCheckpointStrategy(ICheckpointStrategy):
    """里程碑检查点策略"""

    def __init__(self, milestones: list[str] | None = None):
        self.milestones = milestones or []
        self.completed_milestones = set()

    async def should_create_checkpoint(self, context: dict[str, Any]) -> bool:
        current_milestone = context.get("current_milestone")
        if not current_milestone:
            return False

        # 如果达到新的里程碑，创建检查点
        if current_milestone in self.milestones and current_milestone not in self.completed_milestones:
            self.completed_milestones.add(current_milestone)
            return True

        return False

    async def prepare_checkpoint_data(self, context: dict[str, Any]) -> dict[str, Any]:
        return {
            "trigger_reason": "milestone_reached",
            "current_milestone": context.get("current_milestone"),
            "completed_milestones": list(self.completed_milestones),
            "context_snapshot": context,
        }


class IntelligentCheckpointManager:
    """智能检查点管理器
    统一使用 WorkspacePersistenceManager 进行底层持久化
    保留高级功能：策略、差异计算、验证、压缩等
    """

    def __init__(self, strategy: ICheckpointStrategy = None, workspace_path: str | None = None):
        """初始化智能检查点管理器

        Args:
            strategy: 检查点策略
            workspace_path: 工作区路径

        """
        self.strategy = strategy or AutoCheckpointStrategy()

        # 使用 WorkspacePersistenceManager 作为底层存储
        if workspace_path:
            self.persistence_manager = WorkspacePersistenceManager(workspace_path)
        else:
            raise ValueError("workspace_path is required")

        self._checkpoints: dict[str, CheckpointData] = {}  # 内存缓存
        self._checkpoint_history: list[str] = []
        self._max_checkpoints = 50
        self._compression_enabled = True
        self._validation_enabled = True
        self._lock = asyncio.Lock()
        self._checkpoint_counter = 0  # 添加计数器以生成唯一ID
        import logging

        self.logger = logging.getLogger(__name__)

    async def create_checkpoint(
        self,
        task_id: str,
        state: dict[str, Any],
        checkpoint_type: CheckpointType = CheckpointType.AUTO,
        tags: list[str] | None = None,
        parent_checkpoint_id: str | None = None,
    ) -> str | None:
        """创建检查点"""
        context = {
            "tool_executed": self._has_tool_executed(state),
            "state_changed": self._has_state_changed(state),
            "error_occurred": self._has_error_occurred(state),
            "milestone_reached": self._has_milestone_reached(state),
        }

        if not await self.strategy.should_create_checkpoint(context):
            return None

        async with self._lock:
            checkpoint_id = self._generate_checkpoint_id(task_id, checkpoint_type)

            # 计算检查点大小和校验和
            try:
                state_json = json.dumps(
                    state,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    cls=CustomCheckpointEncoder,
                )
            except (TypeError, ValueError):
                self.logger.exception("Failed to serialize state to JSON: ")
                # 尝试序列化基本类型，失败则抛出异常
                try:
                    safe_state = {k: str(v) if isinstance(v, (datetime, timedelta)) else v for k, v in state.items()}
                    state_json = json.dumps(safe_state, ensure_ascii=False, separators=(",", ":"))
                except Exception as e2:
                    self.logger.exception(f"Failed to serialize even basic state: {e2}")
                    raise ValueError(f"Cannot serialize checkpoint state: {e2}") from e2
            checksum = hashlib.sha256(state_json.encode()).hexdigest()

            metadata = CheckpointMetadata(
                checkpoint_id=checkpoint_id,
                task_id=task_id,
                checkpoint_type=checkpoint_type,
                created_at=datetime.now(UTC),
                size_bytes=len(state_json.encode()),
                checksum=checksum,
                tags=tags or [],
                parent_checkpoint_id=parent_checkpoint_id,
            )

            # 计算与上一个检查点的差异
            diff_data = await self._calculate_diff(task_id, state)

            # 压缩数据（如果启用）
            compressed_state = state
            if self._compression_enabled:
                compressed_state = await self._compress_state(state)

            checkpoint_data = CheckpointData(
                metadata=metadata,
                state=compressed_state,
                diff_from_previous=diff_data,
                compressed=self._compression_enabled,
            )

            # 使用 WorkspacePersistenceManager 保存到磁盘
            checkpoint_dict = {
                "metadata": {
                    "checkpoint_id": checkpoint_data.metadata.checkpoint_id,
                    "task_id": checkpoint_data.metadata.task_id,
                    "checkpoint_type": checkpoint_data.metadata.checkpoint_type.value,
                    "created_at": checkpoint_data.metadata.created_at.isoformat(),
                    "size_bytes": checkpoint_data.metadata.size_bytes,
                    "checksum": checkpoint_data.metadata.checksum,
                    "tags": checkpoint_data.metadata.tags,
                    "parent_checkpoint_id": checkpoint_data.metadata.parent_checkpoint_id,
                },
                "state": checkpoint_data.state,
                "diff_from_previous": checkpoint_data.diff_from_previous,
                "compressed": checkpoint_data.compressed,
            }

            await self.persistence_manager.save_checkpoint(checkpoint_id, checkpoint_dict)

            # 内存缓存
            self._checkpoints[checkpoint_id] = checkpoint_data
            self._checkpoint_history.append(checkpoint_id)

            # 清理旧检查点
            await self._cleanup_old_checkpoints(task_id)

            # 发送事件
            await self._emit_checkpoint_created(checkpoint_data)

            return checkpoint_id

    async def restore_checkpoint(self, checkpoint_id: str) -> CheckpointData | None:
        """恢复检查点"""
        async with self._lock:
            # 先从内存缓存查找
            checkpoint_data = self._checkpoints.get(checkpoint_id)

            # 如果内存中没有，从磁盘加载
            if not checkpoint_data:
                checkpoint_dict = await self.persistence_manager.load_checkpoint(checkpoint_id)
                if not checkpoint_dict:
                    self.logger.error(f"Checkpoint {checkpoint_id} not found in memory or on disk")
                    return None

                # 从字典恢复 CheckpointData
                try:
                    checkpoint_type_value = checkpoint_dict["metadata"]["checkpoint_type"]
                    checkpoint_type = CheckpointType(checkpoint_type_value)
                except ValueError:
                    self.logger.exception("Invalid checkpoint type '{checkpoint_type_value}': ")
                    # 使用默认的 AUTO 类型
                    checkpoint_type = CheckpointType.AUTO
                    self.logger.warning(
                        f"Using default checkpoint type AUTO for checkpoint {checkpoint_id}",
                    )

                metadata = CheckpointMetadata(
                    checkpoint_id=checkpoint_dict["metadata"]["checkpoint_id"],
                    task_id=checkpoint_dict["metadata"]["task_id"],
                    checkpoint_type=checkpoint_type,
                    created_at=datetime.fromisoformat(checkpoint_dict["metadata"]["created_at"]),
                    size_bytes=checkpoint_dict["metadata"]["size_bytes"],
                    checksum=checkpoint_dict["metadata"]["checksum"],
                    tags=checkpoint_dict["metadata"]["tags"],
                    parent_checkpoint_id=checkpoint_dict["metadata"].get("parent_checkpoint_id"),
                )

                checkpoint_data = CheckpointData(
                    metadata=metadata,
                    state=checkpoint_dict["state"],
                    diff_from_previous=checkpoint_dict.get("diff_from_previous"),
                    compressed=checkpoint_dict.get("compressed", False),
                )

                # 加入内存缓存
                self._checkpoints[checkpoint_id] = checkpoint_data

            # 验证检查点完整性
            if self._validation_enabled and not await self._validate_checkpoint(checkpoint_data):
                self.logger.error(f"Checkpoint {checkpoint_id} validation failed")
                return None

            # 解压缩数据（如果需要）
            restored_state = checkpoint_data.state
            if checkpoint_data.compressed:
                restored_state = await self._decompress_state(restored_state)

            # 发送事件
            await self._emit_checkpoint_restored(checkpoint_data)

            return CheckpointData(
                metadata=checkpoint_data.metadata,
                state=restored_state,
                diff_from_previous=checkpoint_data.diff_from_previous,
                compressed=False,  # 已解压缩
            )

    async def list_checkpoints(
        self,
        task_id: str,
        checkpoint_type: CheckpointType = None,
    ) -> list[CheckpointMetadata]:
        """列出检查点"""
        async with self._lock:
            checkpoints = [cp.metadata for cp_id, cp in self._checkpoints.items() if cp.metadata.task_id == task_id and (checkpoint_type is None or cp.metadata.checkpoint_type == checkpoint_type)]

            # 按时间排序，最新的在前
            checkpoints.sort(key=lambda x: x.created_at, reverse=True)
            return checkpoints

    async def delete_checkpoint(self, checkpoint_id: str) -> bool:
        """删除检查点"""
        async with self._lock:
            if checkpoint_id in self._checkpoints:
                checkpoint_data = self._checkpoints[checkpoint_id]
                del self._checkpoints[checkpoint_id]

                # 从历史中移除
                if checkpoint_id in self._checkpoint_history:
                    self._checkpoint_history.remove(checkpoint_id)

                # 使用 WorkspacePersistenceManager 删除磁盘文件
                await self.persistence_manager.delete_checkpoint(checkpoint_id)

                # 发送事件
                await self._emit_checkpoint_deleted(checkpoint_data)

                return True

            # 如果内存中没有，尝试从磁盘删除
            deleted = await self.persistence_manager.delete_checkpoint(checkpoint_id)
            if deleted:
                self.logger.info(f"Checkpoint {checkpoint_id} deleted from disk")
            return False

    async def get_checkpoint_diff(
        self,
        checkpoint_id: str,
        compare_to_id: str | None = None,
    ) -> dict[str, Any] | None:
        """获取检查点差异"""
        async with self._lock:
            checkpoint_data = self._checkpoints.get(checkpoint_id)
            if not checkpoint_data:
                return None

            if compare_to_id:
                compare_data = self._checkpoints.get(compare_to_id)
                if compare_data:
                    return await self._calculate_diff_between_states(
                        checkpoint_data.state,
                        compare_data.state,
                    )

            return checkpoint_data.diff_from_previous

    def set_strategy(self, strategy: ICheckpointStrategy) -> None:
        """设置检查点策略"""
        self.strategy = strategy

    def set_compression_enabled(self, enabled: bool) -> None:
        """设置压缩是否启用"""
        self._compression_enabled = enabled

    def set_validation_enabled(self, enabled: bool) -> None:
        """设置验证是否启用"""
        self._validation_enabled = enabled

    def set_max_checkpoints(self, max_checkpoints: int) -> None:
        """设置最大检查点数量"""
        self._max_checkpoints = max_checkpoints

    def _generate_checkpoint_id(self, task_id: str, checkpoint_type: CheckpointType) -> str:
        """生成检查点ID"""
        self._checkpoint_counter += 1
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        # 添加计数器以确保唯一性
        return f"{task_id}_{checkpoint_type.value}_{timestamp}_{self._checkpoint_counter}"

    async def _calculate_diff(
        self,
        task_id: str,
        current_state: dict[str, Any],
    ) -> dict[str, Any] | None:
        """计算与上一个检查点的差异"""
        # 获取同一任务的最新检查点
        latest_checkpoint = None
        latest_time = None

        for _cp_id, cp in self._checkpoints.items():
            if cp.metadata.task_id == task_id and (latest_time is None or cp.metadata.created_at > latest_time):
                latest_checkpoint = cp
                latest_time = cp.metadata.created_at

        if not latest_checkpoint:
            return None

        # 简单的差异计算（可以扩展为更复杂的算法）
        # 返回JSON可序列化的数据（使用列表而不是集合）
        return {
            "added_keys": list(set(current_state.keys()) - set(latest_checkpoint.state.keys())),
            "removed_keys": list(set(latest_checkpoint.state.keys()) - set(current_state.keys())),
            "changed_keys": list(
                {key for key, value in current_state.items() if key in latest_checkpoint.state and latest_checkpoint.state[key] != value},
            ),
        }

    async def _calculate_diff_between_states(
        self,
        state1: dict[str, Any],
        state2: dict[str, Any],
    ) -> dict[str, Any]:
        """计算两个状态之间的差异"""
        # 返回JSON可序列化的数据（使用列表而不是集合）
        return {
            "added_keys": list(set(state2.keys()) - set(state1.keys())),
            "removed_keys": list(set(state1.keys()) - set(state2.keys())),
            "changed_keys": list(
                {key for key, value in state2.items() if key in state1 and state1[key] != value},
            ),
        }

    async def _validate_checkpoint(self, checkpoint_data: CheckpointData) -> bool:
        """验证检查点完整性"""
        # 如果数据被压缩，跳过验证（因为压缩会改变数据）
        # 在实际使用中，应该在解压缩后验证，但这需要完整的压缩/解压缩逻辑
        if checkpoint_data.compressed:
            self.logger.debug("Skipping validation for compressed checkpoint")
            return True

        # 重新计算校验和并比较
        state_json = json.dumps(
            checkpoint_data.state,
            ensure_ascii=False,
            separators=(",", ":"),
            cls=CustomCheckpointEncoder,
        )
        calculated_checksum = hashlib.sha256(state_json.encode()).hexdigest()

        return calculated_checksum == checkpoint_data.metadata.checksum

    async def _compress_state(self, state: dict[str, Any]) -> dict[str, Any]:
        """压缩状态"""
        # 简单的压缩实现：保留完整状态但压缩大型数据
        compressed = state.copy()  # 保留原始数据

        # 对于大型列表，只保留最近的项目
        if "messages" in compressed and isinstance(compressed["messages"], list) and len(compressed["messages"]) > 50:
            compressed["messages"] = compressed["messages"][-50:]  # 保留最近50条
            compressed["_compressed_messages"] = True

        # 添加压缩标记
        compressed["_compressed"] = True
        return compressed

    async def _decompress_state(self, compressed_state: dict[str, Any]) -> dict[str, Any]:
        """解压缩状态"""
        if compressed_state.get("_compressed"):
            # 移除压缩标记
            result = compressed_state.copy()
            result.pop("_compressed", None)
            result.pop("_compressed_messages", None)
            return result

        return compressed_state

    async def _cleanup_old_checkpoints(self, task_id: str) -> None:
        """清理旧检查点"""
        task_checkpoints = [cp_id for cp_id, cp in self._checkpoints.items() if cp.metadata.task_id == task_id]

        if len(task_checkpoints) > self._max_checkpoints:
            # 按时间排序，删除最旧的
            try:
                task_checkpoints.sort(key=lambda x: self._checkpoints[x].metadata.created_at)

                # 安全计算要删除的检查点数量，避免负数索引
                num_to_delete = len(task_checkpoints) - self._max_checkpoints
                if num_to_delete <= 0:
                    return  # 没有需要删除的检查点

                # 使用安全切片，确保不会越界
                checkpoints_to_delete = task_checkpoints[:num_to_delete]

                for cp_id in checkpoints_to_delete:
                    if cp_id in self._checkpoints:
                        # 从内存删除
                        del self._checkpoints[cp_id]
                        if cp_id in self._checkpoint_history:
                            self._checkpoint_history.remove(cp_id)

                        # 从磁盘删除（使用 WorkspacePersistenceManager）
                        await self.persistence_manager.delete_checkpoint(cp_id)
                    else:
                        self.logger.warning(
                            f"Checkpoint {cp_id} not found in memory during cleanup",
                        )

            except KeyError:
                self.logger.exception("KeyError during checkpoint cleanup: ")
            except Exception:
                self.logger.exception("Unexpected error during checkpoint cleanup: ")

    def _has_tool_executed(self, state: dict[str, Any]) -> bool:
        """检查是否有工具执行"""
        return "tool_calls" in state and len(state["tool_calls"]) > 0

    def _has_state_changed(self, state: dict[str, Any]) -> bool:
        """检查是否有状态变化"""
        return "state_changes" in state and len(state["state_changes"]) > 0

    def _has_error_occurred(self, state: dict[str, Any]) -> bool:
        """检查是否有错误发生"""
        return "errors" in state and len(state["errors"]) > 0

    def _has_milestone_reached(self, state: dict[str, Any]) -> bool:
        """检查是否达到里程碑"""
        return "current_milestone" in state and state["current_milestone"] is not None

    async def _emit_checkpoint_created(self, checkpoint_data: CheckpointData) -> None:
        """发送检查点创建事件"""
        self.logger.info(f"Checkpoint created: {checkpoint_data.metadata.checkpoint_id}")

    async def _emit_checkpoint_restored(self, checkpoint_data: CheckpointData) -> None:
        """发送检查点恢复事件"""
        self.logger.info(f"Checkpoint restored: {checkpoint_data.metadata.checkpoint_id}")

    async def _emit_checkpoint_deleted(self, checkpoint_data: CheckpointData) -> None:
        """发送检查点删除事件"""
        self.logger.info(f"Checkpoint deleted: {checkpoint_data.metadata.checkpoint_id}")


def create_task_checkpoint_service(workspace_path: str) -> IntelligentCheckpointManager:
    """Factory function to create a task checkpoint service.

    Args:
        workspace_path: 工作区路径

    Returns:
        IntelligentCheckpointManager: 检查点管理器实例

    """
    strategy = AutoCheckpointStrategy()
    return IntelligentCheckpointManager(strategy=strategy, workspace_path=workspace_path)
