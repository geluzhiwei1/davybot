# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""定时任务数据模型
用于调度器和定时工具的核心数据结构
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone, timedelta
from enum import StrEnum
from typing import Any


class ScheduleType(StrEnum):
    """调度类型"""

    DELAY = "delay"  # 延迟执行
    AT_TIME = "at_time"  # 指定时间
    RECURRING = "recurring"  # 重复执行


class TriggerStatus(StrEnum):
    """触发状态"""

    PENDING = "pending"
    TRIGGERED = "triggered"
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

    # 执行配置
    execution_type: str = "message"  # message/tool/agent
    execution_data: dict[str, Any] | None = None

    # 状态
    status: TriggerStatus = TriggerStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    triggered_at: datetime | None = None
    last_error: str | None = None

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
        return cls(**data)

    def is_due(self) -> bool:
        """检查是否到期"""
        return self.status == TriggerStatus.PENDING and datetime.now(timezone.utc) >= self.trigger_time

    def should_repeat(self) -> bool:
        """检查是否应该重复"""
        if not self.repeat_interval:
            return False
        return not (self.max_repeats and self.repeat_count >= self.max_repeats)

    def schedule_next(self) -> None:
        """安排下一次执行"""
        self.trigger_time = datetime.now(timezone.utc) + timedelta(seconds=self.repeat_interval)
        self.repeat_count += 1
        self.status = TriggerStatus.PENDING


__all__ = [
    "ScheduleType",
    "ScheduledTask",
    "TriggerStatus",
]
