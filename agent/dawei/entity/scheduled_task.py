# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""定时任务数据模型
用于调度器和定时工具的核心数据结构
"""

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta, timezone
from enum import StrEnum
from typing import Any


class ScheduleType(StrEnum):
    """调度类型"""

    DELAY = "delay"  # 延迟执行
    AT_TIME = "at_time"  # 指定时间
    RECURRING = "recurring"  # 重复执行
    CRON = "cron"  # Cron表达式调度


class TriggerStatus(StrEnum):
    """触发状态"""

    PENDING = "pending"
    TRIGGERED = "triggered"
    PAUSED = "paused"  # 已暂停
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ScheduledTask:
    """定时任务数据模型"""

    task_id: str
    workspace_id: str
    description: str
    schedule_type: ScheduleType
    trigger_time: datetime

    # 重复执行配置
    repeat_interval: int | None = None  # 秒
    max_repeats: int | None = None
    repeat_count: int = 0

    # Cron表达式配置 (当schedule_type=CRON时使用)
    cron_expression: str | None = None  # 标准Cron表达式

    # 执行配置
    execution_type: str = "message"  # 仅支持 message
    execution_data: dict[str, Any] | None = None  # 包含 message, llm, mode 等参数

    # 状态
    status: TriggerStatus = TriggerStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    triggered_at: datetime | None = None
    paused_at: datetime | None = None  # 暂停时间
    resumed_at: datetime | None = None  # 恢复时间
    updated_at: datetime | None = None  # 更新时间
    last_error: str | None = None

    # 重试配置
    retry_count: int = 0  # 当前重试次数
    max_retries: int | None = None  # 最大重试次数（0=不重试）
    retry_interval: int | None = None  # 重试间隔（秒），默认指数退避

    # 元数据
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典"""
        d = asdict(self)
        d["schedule_type"] = self.schedule_type.value
        d["status"] = self.status.value
        d["trigger_time"] = self.trigger_time.isoformat()
        d["created_at"] = self.created_at.isoformat()
        if self.triggered_at:
            d["triggered_at"] = self.triggered_at.isoformat()
        if self.paused_at:
            d["paused_at"] = self.paused_at.isoformat()
        if self.resumed_at:
            d["resumed_at"] = self.resumed_at.isoformat()
        if self.updated_at:
            d["updated_at"] = self.updated_at.isoformat()
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ScheduledTask":
        """从字典反序列化"""
        data = data.copy()
        data["schedule_type"] = ScheduleType(data["schedule_type"])
        data["status"] = TriggerStatus(data["status"])
        data["trigger_time"] = datetime.fromisoformat(data["trigger_time"])
        data["created_at"] = datetime.fromisoformat(data["created_at"])
        if data.get("triggered_at"):
            data["triggered_at"] = datetime.fromisoformat(data["triggered_at"])
        if data.get("paused_at"):
            data["paused_at"] = datetime.fromisoformat(data["paused_at"])
        if data.get("resumed_at"):
            data["resumed_at"] = datetime.fromisoformat(data["resumed_at"])
        if data.get("updated_at"):
            data["updated_at"] = datetime.fromisoformat(data["updated_at"])
        return cls(**data)

    def is_due(self) -> bool:
        """检查是否到期"""
        return self.status == TriggerStatus.PENDING and datetime.now(UTC) >= self.trigger_time

    def should_repeat(self) -> bool:
        """检查是否应该重复"""
        # Cron任务会一直重复(除非手动取消)
        if self.schedule_type == ScheduleType.CRON:
            return True
        if not self.repeat_interval:
            return False
        return not (self.max_repeats and self.repeat_count >= self.max_repeats)

    def schedule_next(self) -> None:
        """安排下一次执行"""
        if self.schedule_type == ScheduleType.CRON:
            # Cron任务使用croniter计算下一次执行时间
            try:
                from croniter import croniter

                if self.cron_expression:
                    # 基于当前trigger_time计算下一次
                    cron = croniter(self.cron_expression, self.trigger_time)
                    self.trigger_time = cron.get_next(datetime)
                    self.repeat_count += 1
                    self.status = TriggerStatus.PENDING
            except ImportError:
                # 如果croniter未安装,使用固定间隔
                self.trigger_time = datetime.now(UTC) + timedelta(seconds=3600)
                self.repeat_count += 1
                self.status = TriggerStatus.PENDING
            except Exception as e:
                # Cron表达式错误,标记为失败
                raise ValueError(f"Invalid cron expression: {self.cron_expression}, error: {e}")
        else:
            # 重复间隔任务
            self.trigger_time = datetime.now(UTC) + timedelta(seconds=self.repeat_interval)
            self.repeat_count += 1
            self.status = TriggerStatus.PENDING


__all__ = [
    "ScheduleType",
    "ScheduledTask",
    "TriggerStatus",
]
